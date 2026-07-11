"""Cost-to-serve advisor — the storage-floor economics, per the selected volume.

The book argues retention economics, not feature checklists, decide the platform at
scale, and the cost-to-serve-retention lab measured the storage floor: a hot search
index stores ~4.2x the bytes at ~3.5x the price, so it costs ~14.8x a warm Iceberg-on-S3
lakehouse for the same events, and ~96.7x against a cold tier. This module reproduces
that model so the console can price the selected open stack against the hot-index anchor
for a given ingest volume and retention window.

Storage floor ONLY: no compute, license, ops labor, egress, or IOPS add-ons. The byte
ratios are parameters of the lab's sha256-pinned 10M-row Zeek conn corpus (flat 16-col
schema) and should be re-measured per workload. Source:
sdw-lab-benchmarks/cost-to-serve-retention (AWS us-east-1 list, read 2026-06-10,
re-checked 2026-06-14).
"""
from __future__ import annotations

import os

# AWS us-east-1 list prices, $/GB-month.
PRICE_GP3 = 0.08          # block storage a hot search index must run on
PRICE_S3 = 0.023          # S3 Standard, warm lakehouse
PRICE_GLACIER_IR = 0.004  # Glacier Instant Retrieval, cold (excludes $0.03/GB retrieval)

# Footprint as bytes/event over the lab corpus.
BYTES_RAW = 374.3
BYTES_INDEX = 186.8       # OpenSearch 2.18.0, best_compression, force-merged
BYTES_WARM = 44.0         # Iceberg Parquet, pyiceberg zstd defaults
BYTES_COLD = 38.6         # single-file Parquet, zstd-19


def _stored_gb(raw_gb, bytes_per_event):
    return raw_gb * (bytes_per_event / BYTES_RAW)


def estimate(tb_per_day, retention_days) -> dict:
    """Monthly storage floor at steady state for `tb_per_day` raw ingest held
    `retention_days`. Returns per-realization monthly cost, the index-vs-lakehouse and
    cold multiples, and the absolute monthly gap."""
    raw_gb = max(0.0, tb_per_day) * 1000.0 * max(0.0, retention_days)
    index = _stored_gb(raw_gb, BYTES_INDEX) * PRICE_GP3
    warm = _stored_gb(raw_gb, BYTES_WARM) * PRICE_S3
    cold = _stored_gb(raw_gb, BYTES_COLD) * PRICE_GLACIER_IR
    warm_multiple = (index / warm) if warm else 0.0
    cold_multiple = (index / cold) if cold else 0.0
    return {
        "tb_per_day": tb_per_day,
        "retention_days": retention_days,
        "index_hot_monthly": index,
        "warm_lakehouse_monthly": warm,
        "cold_archive_monthly": cold,
        "warm_multiple": warm_multiple,
        "cold_multiple": cold_multiple,
        "monthly_gap": index - warm,
    }


def summary_md(est) -> str:
    """A one-paragraph read of an estimate(), in the console's plain register."""
    if est["warm_lakehouse_monthly"] <= 0:
        return "*Set a non-zero ingest volume and retention to price the storage floor.*"
    d = est["retention_days"]
    horizon = (f"{d/365:.0f}-year" if d >= 365 else f"{d:.0f}-day")
    return (
        f"At **{est['tb_per_day']:g} TB/day** held **{horizon}**, the storage floor for an "
        f"Iceberg-on-S3 lakehouse is about **${est['warm_lakehouse_monthly']:,.0f}/mo**, against "
        f"about **${est['index_hot_monthly']:,.0f}/mo** for the same events on a hot search "
        f"index — roughly **{est['warm_multiple']:.1f}x**, a **${est['monthly_gap']:,.0f}/mo** gap. "
        f"A cold Glacier-IR tier widens it to about **{est['cold_multiple']:.0f}x** (storage only, "
        f"excludes retrieval). Storage floor, not a TCO model; ratios are corpus-specific."
    )


# CF-COST — commonly-cited operator retention windows (days). NOT legal advice; verify your own
# obligation. Used only to price the storage floor at a realistic horizon.
RETENTION_PRESETS = {
    "PCI_DSS_1yr": 365,
    "HIPAA_6yr": 2190,
    "FINRA_7yr": 2555,
}

# CF-COST — the named-SIEM list-price ANCHOR. Verified public rate card, list price NOT a Matrix
# score. Source: reference_splunk_gcloud_pricing (project1 memory) + the UK Digital Marketplace PDF.
NAMED_SIEM_LIST_PRICE = {
    "vendor": "Splunk",
    "product": "Enterprise SE-T-LIC-ST (platform, annual subscription)",
    "source": "UK G-Cloud 14 Splunk End Customer Pricelist – EMEA DISTRIBUTOR",
    "published": "2024-04-23",
    "basis": "list price, per GB/day ingest, annual subscription (declining-volume curve)",
    # Verified endpoints of the published declining-volume curve, $/GB/day/year:
    "price_gb_day_year_low": 575.0,     # high-volume floor
    "price_gb_day_year_high": 2277.0,   # low-volume ceiling
    # Verified representative anchor: full SOC stack (platform + ES) at 10 TB/day.
    "anchor_full_stack_gb_day_year": 1196.0,
    "anchor_full_stack_note": "platform $764.75 + ES $431.25 at 10 TB/day (full SOC stack)",
}


def sample_bytes_per_event(source, *, samples_dir=None):
    """Measured raw + OCSF-landed bytes/event for one sample-library source, computed as
    file_size / n_events using config_preview's own readers. Returns
    {source, n_events, raw_bytes_per_event, ocsf_bytes_per_event} or {source, error}
    (honest degrade — never raises)."""
    try:
        import config_preview as cpv
        xw = cpv.CROSSWALK.get(source)
        if not xw:
            return {"source": source, "error": f"unknown source '{source}'"}
        base = samples_dir or cpv._DEFAULT_SAMPLES
        raw_path = os.path.join(base, xw["raw_file"])
        gold_path = os.path.join(base, xw["gold_file"])
        reader = cpv._read_zeek_tsv if xw["raw_kind"] == "zeek_tsv" else cpv._read_ndjson
        n = len(reader(raw_path))
        if n == 0:
            return {"source": source, "error": "no events in sample"}
        return {
            "source": source,
            "n_events": n,
            "raw_bytes_per_event": os.path.getsize(raw_path) / n,
            "ocsf_bytes_per_event": os.path.getsize(gold_path) / n,
        }
    except OSError as e:  # unreadable sample — degrade, don't crash the panel
        return {"source": source, "error": str(e)}


def estimate_per_source(source, tb_per_day, retention_days, *, samples_dir=None):
    """The storage-floor estimate() for a volume, annotated with THIS source's measured
    event weight (raw + OCSF bytes/event). The $ stays volume-driven (raw_gb is given);
    the per-source block lets the operator convert their EVENT COUNT to TB. HONEST: the
    index/warm/cold multiples are the Zeek-corpus lab ratios — re-measure per workload.
    Degrades to a plain estimate() with a note if the sample is unreadable."""
    est = estimate(tb_per_day, retention_days)
    m = sample_bytes_per_event(source, samples_dir=samples_dir)
    if "error" in m:
        est["per_source"] = {"source": source, "degraded": m["error"],
                             "ratios_note": "index/warm/cold multiples are Zeek-corpus ratios"}
    else:
        est["per_source"] = {
            "source": source,
            "n_events": m["n_events"],
            "raw_bytes_per_event": m["raw_bytes_per_event"],
            "ocsf_bytes_per_event": m["ocsf_bytes_per_event"],
            "ratios_note": "index/warm/cold multiples are the Zeek-corpus lab ratios — "
                           "re-measure per workload",
        }
    return est


def named_siem_compare(est):
    """A DATED list-price magnitude anchor: the open-stack storage floor vs the Splunk
    G-Cloud 14 ingest LIST price for the same daily volume. Different bases (Splunk is an
    ingest license that includes the platform; the open figure is storage floor only), so
    this is a magnitude anchor, never a scored comparison. Provenance + counts only; the
    list price is NOT a Matrix score."""
    p = NAMED_SIEM_LIST_PRICE
    gb_day = max(0.0, est.get("tb_per_day", 0.0)) * 1000.0
    return {
        "provenance": p,
        "ingest_gb_day": gb_day,
        "open_stack_storage_floor_annual": est.get("warm_lakehouse_monthly", 0.0) * 12.0,
        "splunk_list_annual_low": gb_day * p["price_gb_day_year_low"],
        "splunk_list_annual_high": gb_day * p["price_gb_day_year_high"],
        "splunk_list_annual_full_stack_anchor": gb_day * p["anchor_full_stack_gb_day_year"],
        "basis": "list price",
        "caveat": ("Splunk is an ingest LICENSE (platform included) on the G-Cloud 14 "
                   "declining-volume curve; the open figure is STORAGE FLOOR only. A magnitude "
                   "anchor, not a like-for-like TCO comparison."),
    }


def summary_md_per_source(est) -> str:
    """summary_md() plus the per-source event weight and the dated Splunk list-price anchor."""
    base = summary_md(est)
    ps = est.get("per_source") or {}
    cmp = named_siem_compare(est)
    if "degraded" in ps:
        weight = f" Per-source sample unreadable ({ps['degraded']})."
    elif ps:
        weight = (f" A **{ps['source']}** event weighs about **{ps['raw_bytes_per_event']:.0f} raw "
                  f"bytes** and lands as about **{ps['ocsf_bytes_per_event']:.0f} OCSF bytes** "
                  f"(measured over {ps['n_events']} sample events; {ps['ratios_note']}).")
    else:
        weight = ""
    if cmp["ingest_gb_day"] > 0:
        splunk = (f" For scale, the Splunk list price (UK G-Cloud 14, published "
                  f"{cmp['provenance']['published']}) for this **{cmp['ingest_gb_day']:,.0f} GB/day** "
                  f"is about **${cmp['splunk_list_annual_low']:,.0f}–${cmp['splunk_list_annual_high']:,.0f}/year** "
                  f"(ingest license, declining-volume curve) — {cmp['caveat']}")
    else:
        splunk = ""
    return base + weight + splunk
