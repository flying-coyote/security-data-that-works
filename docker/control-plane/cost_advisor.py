"""Cost-to-serve advisor — the storage-floor economics, per the selected volume.

The book argues retention economics, not feature checklists, decide the platform at
scale, and the cost-to-serve-retention lab measured the storage floor: a hot search
index stores ~4.2x the bytes at ~3.5x the price, so it costs ~14.8x a warm Iceberg-on-S3
lakehouse for the same events, and ~96.7x against a cold tier. This module reproduces
that model so the console can price the selected open stack against the hot-index foil
for a given ingest volume and retention window.

Storage floor ONLY: no compute, license, ops labor, egress, or IOPS add-ons. The byte
ratios are parameters of the lab's sha256-pinned 10M-row Zeek conn corpus (flat 16-col
schema) and should be re-measured per workload. Source:
sdw-lab-benchmarks/cost-to-serve-retention (AWS us-east-1 list, read 2026-06-10,
re-checked 2026-06-14).
"""
from __future__ import annotations

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
