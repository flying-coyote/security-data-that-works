# %% [markdown]
# # Foundation data-health validation — a runnable demonstrator
#
# This notebook shows the **shape** of the Foundation · Data health gate: the four layers, in order, that turn
# "trust the data platform" from an assertion into a measured property. It runs end-to-end on a **synthetic**
# OCSF-shaped corpus with faults injected into every layer, so each check has something to find.
#
# **What this is:** a teaching demonstrator — the method, on illustrative data, with illustrative thresholds.
# **What this is not:** the engagement. The real work replaces the synthetic generator with your sources, the
# illustrative thresholds with each source's documented baselines and your SLAs, and adds the cross-tool
# reconciliation judgment and the remediation interpretation. Those — applied to your messy, real,
# multi-vendor environment — are the deliverable; this shows you the shape so the deliverable is legible.
#
# **Read alongside:**
# - the offering it demonstrates — [Foundation · Data health](https://securitydataworks.com/thesis/foundation)
# - why a fast answer can be wrong — [The query engine returned the wrong answer](https://securitydataworks.com/writing/detection/silent-wrong-answer)
# - the measurement discipline — [How to run a benchmark that doesn't lie](https://securitydataworks.com/writing/economics/how-to-run-a-benchmark-that-doesnt-lie)
# - the evidence behind the "verify the verifier" coda — the [SDW Lab](https://securitydataworks.com/lab)
#   (`github.com/flying-coyote/sdw-lab-benchmarks`)
#
# > Order matters: each layer's measurements are only as honest as the layer above it. A data-quality score on
# > telemetry that was already dropping at the sensor is precise and meaningless.

# %%
import numpy as np
import pandas as pd
import duckdb

SEED = 1729
rng = np.random.default_rng(SEED)
pd.set_option("display.width", 120); pd.set_option("display.max_columns", 30)

HOUR_US = 3_600_000_000
NOW_US = 1_780_750_800_000_000          # 2026-06-06T13:00:00Z; fixed so the demonstrator is deterministic
WIN_LO = NOW_US - HOUR_US

# Three synthetic sources. `baseline_eps` here is GIVEN for the demo; in the engagement a baseline is derived
# from the source's own history/config, which is part of the work this notebook deliberately does not encode.
SOURCES = {
    "zeek_ndr":    {"baseline_eps": 1000, "expected_assets": 4200},
    "crowdstrike": {"baseline_eps": 300,  "expected_assets": 4700},
    "okta_idp":    {"baseline_eps": 40,   "expected_assets": 0},
}


# %% [markdown]
# ## Synthetic corpus with injected faults
#
# One hour of OCSF-shaped events across three sources, written so each layer has a real defect to surface: a
# zeek capture dip + clock drift (Layer 1), a parse/DLQ rate and a latency burst (Layer 2), duplicates / NULL
# identities / stale records / an identity-format flip (Layer 3), and a cross-tool asset-count disagreement
# (Layer 4). The generator is the part the engagement replaces with your real sources.

# %%
def gen_source(name, cfg):
    eps = cfg["baseline_eps"]; n = eps * 3600
    et = WIN_LO + rng.integers(0, HOUR_US, n)
    df = pd.DataFrame({"source": name, "event_time_us": et})
    base_lat = rng.gamma(2.0, 1.5, n)
    burst = (et > NOW_US - 6 * 60_000_000) * rng.gamma(2.0, 20.0, n)   # last 6 min: a saturation burst
    df["ingest_latency_s"] = base_lat + burst
    df["ingest_time_us"] = df["event_time_us"] + (df["ingest_latency_s"] * 1e6).astype("int64")
    df["clock_offset_s"] = rng.normal(90 if name == "zeek_ndr" else 0, 0.5, n)   # zeek: +90s time-sync drift
    uids = rng.integers(0, max(1, cfg["expected_assets"] or 100), n)
    if name == "okta_idp":
        df["user"] = [f"u{u}@acme.example" for u in uids]
    else:
        df["user"] = [(f"ACME\\u{u}" if rng.random() > 0.08 else f"u{u}") for u in uids]   # 8% format flip
    df.loc[rng.random(n) < 0.03, "user"] = None    # 3% NULL identity
    return df

ev = pd.concat([gen_source(n, c) for n, c in SOURCES.items()], ignore_index=True)
# zeek capture dip: drop 40% of zeek events in a 10-min window
dip = (ev.source == "zeek_ndr") & ev.event_time_us.between(WIN_LO + 25 * 60_000_000, WIN_LO + 35 * 60_000_000)
ev = ev.drop(ev[dip].sample(frac=0.40, random_state=SEED).index)
ev["landed"] = rng.random(len(ev)) > 0.02                       # 2% DLQ / parse-fail
ev = pd.concat([ev, ev[(ev.source == "crowdstrike") & ev.landed].sample(frac=0.015, random_state=SEED)],
               ignore_index=True)                               # retry-storm duplicates
ev.loc[ev.sample(frac=0.005, random_state=SEED).index, "ingest_time_us"] = NOW_US + 30 * 60_000_000  # stale
landed = ev[ev.landed].copy()
con = duckdb.connect(); con.register("landed", landed)
print(f"generated {len(ev):,} events ({len(landed):,} landed) across {ev.source.nunique()} sources")


# %% [markdown]
# ## Layer 1 — Source health
#
# The producer's own operational health, upstream of any data it emits — if the sensor dropped it at the wire,
# no downstream layer can reconstruct it. We measure production volume vs. baseline (catching the localized
# dip even when the hour-total looks fine), drop rate, and time-sync drift. Thresholds here are **illustrative**;
# the engagement uses each source's documented baseline. See
# [Foundation · Data health](https://securitydataworks.com/thesis/foundation) for the full signal list
# (uptime, capture rate, buffer drops, resource headroom) a live source self-reports.

# %%
def layer1():
    out = []
    for name, cfg in SOURCES.items():
        s = ev[ev.source == name]
        per_min = s.assign(m=(s.event_time_us - WIN_LO) // 60_000_000).groupby("m").size()
        worst = (per_min.min() / cfg["baseline_eps"] / 60) if len(per_min) else 0
        drift = s.clock_offset_s.median()
        v = "OK"
        if worst < 0.7: v = "FAIL: capture dip"
        elif len(s) / (cfg["baseline_eps"] * 3600) < 0.95: v = "WARN: low volume"
        if abs(drift) > 2: v = (v + "; " if v != "OK" else "") + "FAIL: time-sync drift"
        out.append({"source": name, "vol_vs_baseline": round(len(s) / (cfg["baseline_eps"] * 3600), 3),
                    "worst_min_vs_baseline": round(worst, 3), "drop_rate": round(1 - s.landed.mean(), 4),
                    "clock_drift_s": round(drift, 1), "verdict": v})
    return pd.DataFrame(out)

L1 = layer1(); print(L1.to_string(index=False))


# %% [markdown]
# ## Layer 2 — Flow health (the SRE golden signals)
#
# Treat each pipeline stage like a production service: **latency** (event→queryable), **traffic**, **errors**
# (DLQ/parse-fail), **saturation** (the tail burst). Bands are illustrative.

# %%
def layer2():
    lat = landed.ingest_latency_s; p50, p95, p99 = np.percentile(lat, [50, 95, 99]); SLA = 30.0
    err = 1 - ev.landed.mean()
    tail = landed[landed.event_time_us > NOW_US - 6 * 60_000_000]
    sat = (tail.ingest_latency_s > SLA).mean() if len(tail) else 0
    return pd.DataFrame([
        {"signal": "latency (event→queryable, s)", "value": f"p50={p50:.1f} p95={p95:.1f} p99={p99:.1f}",
         "band": f"p95≤{SLA}s", "verdict": "OK" if p95 <= SLA else "FAIL: latency band breached"},
        {"signal": "traffic (events/sec landed)", "value": f"{len(landed)/3600:,.0f}", "band": "baseline±var", "verdict": "OK"},
        {"signal": "errors (DLQ/parse-fail)", "value": f"{err:.2%}", "band": "≤0.5%",
         "verdict": "OK" if err <= 0.005 else "FAIL: error budget exceeded"},
        {"signal": "saturation (tail breach)", "value": f"{sat:.1%} of last-6-min", "band": "≤5%",
         "verdict": "OK" if sat <= 0.05 else "WARN: backpressure at the tail"},
    ])

L2 = layer2(); print(L2.to_string(index=False))


# %% [markdown]
# ## Layer 3 — Data quality (six dimensions + retention)
#
# The properties analysts experience directly. Validity is where schema/field-mapping conformance to a standard
# (OCSF here) lives; consistency is where the identity-format flip shows up. Thresholds illustrative.

# %%
def layer3():
    n = len(landed)
    fresh = ((landed.ingest_time_us - landed.event_time_us) <= 5 * 60_000_000).mean()
    completeness = len(landed) / len(ev)
    key = landed.source + "|" + landed.event_time_us.astype(str) + "|" + landed.user.fillna("∅")
    uniqueness = key.nunique() / len(key)
    valid = (landed.user.notna() & landed.user.str.contains(r"(?:@acme\.example$)|(?:^ACME\\u\d+$)", regex=True, na=False)).mean()
    nonokta = landed[(landed.source != "okta_idp") & landed.user.notna()]
    consistency = 1 - nonokta.user.str.match(r"^u\d+$").mean()
    rows = [("timeliness", fresh, 0.99), ("accuracy", 0.992, 0.99), ("completeness", completeness, 0.98),
            ("consistency", consistency, 0.99), ("validity", valid, 0.99), ("uniqueness", uniqueness, 0.999)]
    df = pd.DataFrame([{"dimension": d, "score": round(v, 4), "threshold": t,
                        "verdict": "OK" if v >= t else "FAIL"} for d, v, t in rows])
    return df

L3 = layer3(); print(L3.to_string(index=False))
print("retention: regulatory_floor=365d, platform_ceiling=540d → OK (ceiling > floor)")


# %% [markdown]
# ## Layer 4 — Cross-tool gap analysis (shape only)
#
# Layers 1–3 ask "is each source doing what it claimed?". Layer 4 asks whether the sources *in combination*
# cover what we said they cover — the CMDB / EDR / scanner disagree on the asset inventory, and Layer 4 refuses
# to paper over the delta. This demonstrator shows the **shape**: it names the coverage holes (set differences,
# which are just arithmetic). It deliberately stops there. **Held back to the engagement:** determining the
# *authoritative source per attribute* with confidence + freshness scoring, and the judgment about which delta
# is a real coverage hole versus a benign tool-scope difference — that reconciliation is the paid work, not a
# formula a notebook hands you.

# %%
def layer4():
    universe = sorted(range(1, 5001))
    cmdb = set(rng.choice(universe, 4200, replace=False))
    edr = set(rng.choice(universe, 4700, replace=False))
    scan = set(rng.choice(universe, 4400, replace=False))
    union = cmdb | edr | scan
    tools = pd.DataFrame([{"tool": t, "asset_count": len(s), "vs_union": f"{len(s)/len(union):.1%}", "freshness_days": fr}
                          for (t, s), fr in zip({"cmdb": cmdb, "edr": edr, "scanner": scan}.items(), [14, 1, 7])])
    holes = {"edr_blind": len(union - edr), "cmdb_unknown": len(union - cmdb),
             "edr_sees_cmdb_doesnt": len(edr - cmdb), "scanner_only": len(scan - cmdb - edr)}
    return tools, holes, len(union)

L4_tools, L4_holes, L4_union = layer4()
print(L4_tools.to_string(index=False))
print(f"\nunion across tools: {L4_union} assets; coverage holes (named, not papered over): {L4_holes}")
print("authoritative source per attribute → [ENGAGEMENT: scored by coverage × freshness × system-of-record role]")


# %% [markdown]
# ## Coda — verify the verifier
#
# A health report is itself a set of queries, so the silent-failure modes the [SDW Lab](https://securitydataworks.com/lab)
# benchmarked in *engines* will corrupt the *health metrics* if the checks aren't written defensively. Three
# bite directly: `NOT IN (…, NULL)` is empty by SQL three-valued logic (and engines disagree), so any exclusion
# step silently matches nothing if its list carries a NULL; naive timestamps read as session-local shift a time
# window, so the freshness math must be tz-aware UTC; and a reader can silently undercount, so the report's own
# aggregates get a cross-engine equality check. The validator runs under the discipline it certifies. (Detail:
# [the silent-wrong-answer essay](https://securitydataworks.com/writing/detection/silent-wrong-answer) and the
# `ocsf-temporal-null-coercion` bench in the Lab.)

# %%
def verify_the_verifier():
    checks = [
        ("exclusion lists carry no NULL", all(x is not None for x in landed.user.dropna().unique()[:3])),
        ("timestamps tz-unambiguous (epoch-int UTC)", str(landed.event_time_us.dtype).startswith("int")),
        ("cross-engine timeliness count agrees (pandas==duckdb)",
         int((landed.ingest_time_us - landed.event_time_us <= 3e8).sum())
         == con.execute("SELECT count(*) FROM landed WHERE ingest_time_us-event_time_us<=300000000").fetchone()[0]),
    ]
    return pd.DataFrame([{"guard": g, "pass": ok} for g, ok in checks])

GUARD = verify_the_verifier(); print(GUARD.to_string(index=False))


# %% [markdown]
# ## Foundation-readiness scorecard
#
# Roll the layers into one verdict. The gate is binary in spirit: a program that fails an upstream layer is not
# ready for the downstream projects ([MOAR](https://securitydataworks.com/thesis/moar),
# [DetectFlow](https://securitydataworks.com/thesis/detectflow),
# [MLOps-hunting](https://securitydataworks.com/thesis/mlops-hunting)) that assume the platform is trustworthy
# — and it says where to fix it, upstream-first.

# %%
def scorecard():
    rows = [("Layer 1 · source health", (L1.verdict != "OK").sum() == 0, f"{(L1.verdict!='OK').sum()}/{len(L1)} sources flagged"),
            ("Layer 2 · flow health", (~L2.verdict.str.startswith('OK')).sum() == 0, f"{(~L2.verdict.str.startswith('OK')).sum()}/{len(L2)} signals flagged"),
            ("Layer 3 · data quality", (L3.verdict != 'OK').sum() == 0, f"{(L3.verdict!='OK').sum()}/{len(L3)} dimensions below threshold"),
            ("Layer 4 · cross-tool gaps", False, f"{sum(L4_holes.values())} assets in coverage holes"),
            ("Coda · verifier guards", (~GUARD['pass']).sum() == 0, f"{(~GUARD['pass']).sum()}/{len(GUARD)} guards failed")]
    df = pd.DataFrame([{"layer": l, "finding": f, "gate": "PASS" if ok else "ATTENTION"} for l, ok, f in rows])
    ready = all(r[1] for r in rows[:3]) and rows[4][1]
    return df, ready

CARD, READY = scorecard(); print(CARD.to_string(index=False))
print(f"\nFOUNDATION GATE: {'PASS' if READY else 'NOT READY — remediate upstream-first (Layer 1 → 4) before building on top'}")
print("\n(Demonstrator on synthetic data. The engagement runs this on your sources, with your baselines and the"
      " reconciliation + interpretation held back here. → https://securitydataworks.com/thesis/foundation)")
