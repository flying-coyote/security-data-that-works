"""Proof that the data-health gate carries the demo.

This is the evidence behind the claim that the console's gate refuses to certify a
foundation GREEN when the data underneath it is actually unhealthy. It does NOT
mock anything: it stands up real Apache Iceberg tables on a local SqlCatalog with a
filesystem warehouse, writes real Parquet data files, then runs the SAME
`layer3_audit` checks and the SAME `gate_logic.compute_gate` verdict the marimo
console runs. The only difference from the live path is the object store (local FS
vs SeaweedFS) and the catalog (SQLite vs Polaris) — the audit logic operating on
`table.inspect.files()`, `table.schema()`, and `table.current_snapshot()` is
identical.

Two parts:
  1. Each measured check shown failing on a real injected fault and passing clean,
     plus crc/tombstone reported as unwired (never a pass).
  2. The integrated arc — healthy -> broken (orphan injected) -> remediated.
     As-built, with Layer 4 unmeasured by design, the gate flips amber -> RED -> amber;
     with the other layers forced green (Part 2b) it flips GREEN -> not-GREEN -> GREEN.
     Either way compute_gate tracks real audit input rather than a paraphrase.

Run:  VENV/bin/python prove_gate.py      (exit 0 = every assertion held)
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

import pyarrow as pa
from pyiceberg.catalog.sql import SqlCatalog

import gate_logic as gl
import layer3_audit as l3

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def make_table(cat, name, schema, batches):
    t = cat.create_table(name, schema=schema)
    for b in batches:
        t.append(b)
    return t


def main():
    wh = tempfile.mkdtemp(prefix="moar_gate_proof_")
    try:
        cat = SqlCatalog("proof", **{"uri": f"sqlite:///{wh}/cat.db", "warehouse": f"file://{wh}"})
        cat.create_namespace("ocsf")
        schema = pa.schema([("time", pa.int64()), ("user", pa.string()), ("action", pa.string())])

        # A healthy table: one append => one data file, recent snapshot, clean store.
        good = make_table(cat, "ocsf.authentication", schema,
                          [pa.table({"time": [1, 2], "user": ["a", "b"], "action": ["login", "logout"]}, schema=schema)])
        snap_ms = good.current_snapshot().timestamp_ms
        good_dir = good.location().replace("file://", "")
        refs = {l3._basename(p) for p in good.inspect.files().column("file_path").to_pylist()}

        print("\n=== Part 1 — each measured check on a real fault ===\n")

        print("freshness (snapshot age vs threshold):")
        check("recent snapshot passes", l3.check_freshness(snap_ms, snap_ms + 10_000).status == "pass")
        check("stale snapshot (>1h) fails", l3.check_freshness(snap_ms, snap_ms + 7_200_000).status == "fail")

        print("small_files (compaction pressure):")
        good_sizes = good.inspect.files().column("file_size_in_bytes").to_pylist()
        check("few files passes", l3.check_small_files(good_sizes).status == "pass")
        noisy = make_table(cat, "ocsf.noisy", schema,
                           [pa.table({"time": [i], "user": ["x"], "action": ["a"]}, schema=schema) for i in range(12)])
        noisy_sizes = noisy.inspect.files().column("file_size_in_bytes").to_pylist()
        _sf = l3.check_small_files(noisy_sizes)
        check(f"12 small files fails (measured {_sf.measured})", _sf.status == "fail")

        print("orphans (store files not referenced by the snapshot):")
        store_clean = l3.list_local_parquet_basenames(good_dir)
        check("clean store passes", l3.check_orphans(refs, store_clean).status == "pass")
        # Inject a real stray parquet into the data dir.
        data_dir = os.path.join(good_dir, "data")
        src = next(os.path.join(data_dir, f) for f in os.listdir(data_dir) if f.endswith(".parquet"))
        stray = os.path.join(data_dir, "00000-0-orphaned-deadbeefcafe.parquet")
        shutil.copy(src, stray)
        _orph = l3.check_orphans(refs, l3.list_local_parquet_basenames(good_dir))
        check(f"injected orphan fails (measured {_orph.measured})", _orph.status == "fail")
        os.remove(stray)  # remediate for the arc below

        print("schema_conformance (expected columns present):")
        names = [f.name for f in good.schema().fields]
        reqd = [f.name for f in good.schema().fields if f.required]
        check("all expected columns present passes",
              l3.check_schema_conformance(names, reqd, [], expected_columns={"time", "user"}).status == "pass")
        check("missing expected column fails",
              l3.check_schema_conformance(names, reqd, [], expected_columns={"time", "user", "src_ip"}).status == "fail")

        print("unwired checks (must NEVER be a pass):")
        _au = l3.audit_table(good, store_basenames=store_clean, now_ms=snap_ms + 10_000,
                             enabled={"crc", "tombstone"})
        _crc = next(c for c in _au["checks"] if c.name == "crc")
        _tomb = next(c for c in _au["checks"] if c.name == "tombstone")
        check("crc reported unwired (not pass)", _crc.status == "unwired")
        check("tombstone reported unwired (not pass)", _tomb.status == "unwired")
        # The aggregation rule itself: unwired/unmeasured never make a layer pass.
        # (A live audit also always runs freshness, so it is never unwired-only.)
        check("unwired-only checks aggregate to unmeasured (no pass)",
              l3.layer3_status([l3.CheckResult("crc", "unwired", ""),
                                l3.CheckResult("tombstone", "unwired", "")]) == "unmeasured")

        print("\n=== Part 2 — integrated gate arc (the demo moment) ===\n")
        enabled = {"small_files", "orphans", "schema_conformance", "crc", "tombstone"}

        def audit_now():
            return l3.audit_table(good, store_basenames=l3.list_local_parquet_basenames(good_dir),
                                  now_ms=snap_ms + 10_000, enabled=enabled, expected_columns={"time", "user"})

        def gate_for(status, **over):
            base = dict(warns=[], spec_saved=True, docker_up=True, catalog_live=True)
            base.update(over)
            return gl.compute_gate(layer3_status=status, **base)

        def is_red(g):
            return gl.verdict_line(g)[1] == "#c14a4a"

        # As-built, Layer 4 is honestly still unmeasured, so a clean foundation sits
        # at amber ("deploy permitted, cannot certify GREEN until Layer 4 runs") and a
        # Layer-3 data-quality failure flips it RED. The RED transition is the demo
        # moment with what is actually built — the gate won't even bluff green for its
        # own unbuilt layer.
        print("Part 2a — as-built (Layer 4 unmeasured): amber -> RED on data failure -> amber")
        h = audit_now()
        g_h = gate_for(h["status"])
        print("  healthy   →", gl.verdict_line(g_h)[0])
        check("healthy: Layer 3 passes", h["status"] == "pass")
        check("healthy: not RED (deploy permitted, amber)", g_h["deploy_ok"] and not is_red(g_h))

        shutil.copy(src, stray)  # inject the real orphan
        b = audit_now()
        g_b = gate_for(b["status"])
        print("  broken    →", gl.verdict_line(g_b)[0])
        check("broken: Layer 3 fails", b["status"] == "fail")
        check("broken: verdict RED", is_red(g_b))
        check("broken: Layer 3 named a certification blocker",
              any(x.startswith("Layer 3") for x in g_b["cert_blockers"]))

        os.remove(stray)  # remediate
        f = audit_now()
        g_f = gate_for(f["status"])
        print("  remediated→", gl.verdict_line(g_f)[0])
        check("remediated: Layer 3 passes again", f["status"] == "pass")
        check("remediated: back to not RED", g_f["deploy_ok"] and not is_red(g_f))

        # Isolating Layer 3: hold every other layer green and Layer 3 alone flips the
        # GREEN certification on and off — proof that Layer 3 controls all_green.
        print("\nPart 2b — isolating Layer 3 (all other layers green): GREEN <-> not-GREEN")
        _others = dict(layer1_status="pass", layer4_status="pass")
        check("healthy + others green -> gate GREEN",
              gate_for(h["status"], **_others)["all_green"] is True)
        check("broken + others green -> NOT green",
              gate_for(b["status"], **_others)["all_green"] is False)
        check("remediated + others green -> GREEN again",
              gate_for(f["status"], **_others)["all_green"] is True)

        # Part 2c — the optional 7th row: cross-engine answer equality (./moar verify).
        # Omitted by default (6 rows, back-compat); present, a fail blocks certification.
        print("\nPart 2c — cross-engine answer-equality row (optional 7th gate row)")
        g6 = gate_for(h["status"], **_others)
        check("answer_equality omitted -> 6 rows, GREEN reachable",
              len(g6["layers"]) == 6 and g6["all_green"] is True)
        g7p = gate_for(h["status"], **_others, answer_equality_status="pass")
        check("answer_equality=pass -> 7 rows, still GREEN",
              len(g7p["layers"]) == 7 and g7p["all_green"] is True)
        g7f = gate_for(h["status"], **_others, answer_equality_status="fail")
        check("answer_equality=fail -> NOT green, named a cert blocker",
              g7f["all_green"] is False and "Cross-engine answer equality" in g7f["cert_blockers"])
        g7u = gate_for(h["status"], **_others, answer_equality_status="unmeasured")
        check("answer_equality=unmeasured -> not green, listed unmeasured (no bluff)",
              g7u["all_green"] is False and "Cross-engine answer equality" in g7u["unmeasured"])

        # Part 2d — the optional 8th row: OCSF round-trip (mapping fidelity). Same rules:
        # omitted by default, a fail blocks certification, unmeasured is never a bluffed pass.
        print("\nPart 2d — OCSF round-trip mapping-fidelity row (optional 8th gate row)")
        _g7 = gate_for(h["status"], **_others, answer_equality_status="pass")
        check("roundtrip omitted -> stays at 7 rows", len(_g7["layers"]) == 7)
        _g8p = gate_for(h["status"], **_others, answer_equality_status="pass", ocsf_roundtrip_status="pass")
        check("roundtrip=pass -> 8 rows, still GREEN", len(_g8p["layers"]) == 8 and _g8p["all_green"] is True)
        _g8f = gate_for(h["status"], **_others, ocsf_roundtrip_status="fail")
        check("roundtrip=fail -> NOT green, named a cert blocker",
              _g8f["all_green"] is False and "OCSF round-trip (mapping fidelity)" in _g8f["cert_blockers"])
        _g8u = gate_for(h["status"], **_others, ocsf_roundtrip_status="unmeasured")
        check("roundtrip=unmeasured -> not green, listed unmeasured (no bluff)",
              _g8u["all_green"] is False and "OCSF round-trip (mapping fidelity)" in _g8u["unmeasured"])

        # Part 2e — the optional 9th row: flow reconciliation (hop counts). Same rules: a
        # silent class drop is a fail that blocks certification; unmeasured never bluffs a pass.
        print("\nPart 2e — flow reconciliation hop-count row (optional 9th gate row)")
        _g9p = gate_for(h["status"], **_others, answer_equality_status="pass",
                        ocsf_roundtrip_status="pass", flow_reconcile_status="pass")
        check("flow=pass -> 9 rows, still GREEN", len(_g9p["layers"]) == 9 and _g9p["all_green"] is True)
        _g9f = gate_for(h["status"], **_others, flow_reconcile_status="fail")
        check("flow=fail -> NOT green, named a cert blocker",
              _g9f["all_green"] is False and "Flow reconciliation (hop counts)" in _g9f["cert_blockers"])
        _g9u = gate_for(h["status"], **_others, flow_reconcile_status="unmeasured")
        check("flow=unmeasured -> not green, listed unmeasured (no bluff)",
              _g9u["all_green"] is False and "Flow reconciliation (hop counts)" in _g9u["unmeasured"])

        # Part 3 — verdict_chip: the compact verdict for secondary surfaces (full breakdown in Health).
        print("\nPart 3 — verdict_chip (compact verdict for secondary surfaces)")
        check("chip GREEN when all_green", gl.verdict_chip(gate_for(h["status"], **_others))[0].startswith("🟢"))
        check("chip red (blocked) on a config-integrity blocker",
              gl.verdict_chip(gate_for(h["status"], warns=["x"]))[0].startswith("🔴"))
        check("chip red (not certified) on a measured-layer fail",
              gl.verdict_chip(gate_for("fail", **_others))[0].startswith("🔴"))
        check("chip amber when an unproven layer keeps it from GREEN",
              "🟡" in gl.verdict_chip(gate_for(h["status"]))[0])

        print()
        if _failures:
            print(f"\033[91m{len(_failures)} assertion(s) FAILED:\033[0m " + "; ".join(_failures))
            return 1
        print("\033[92mAll assertions held — the gate tracks real foundation health.\033[0m")
        return 0
    finally:
        shutil.rmtree(wh, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
