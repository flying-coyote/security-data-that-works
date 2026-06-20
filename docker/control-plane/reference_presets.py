"""Reference architectures as presets — Appendix C, mapped to the open-stack catalog.

The book's Appendix C ships validated reference architectures, each with the conditions
under which it actually wins and a cost profile. This module carries them as presets over
the console's components (providers.py codes), so the picker can show a known-good
starting point with its validity window and cost shape rather than a blank choice. The
presets are advisory starting points; the constraint filter and anti-pattern guards still
apply to whatever you land on.
"""
from __future__ import annotations

PRESETS = [
    {
        "code": "lean_single_engine",
        "name": "Lean single-engine lakehouse",
        "components": {"storage": "seaweedfs", "catalog": "polaris", "schema": "ocsf",
                       "ingest": ["vector"], "query": ["datafusion"]},
        "when_it_wins": "A small team (2-3 engineers), cost-led, mixed analyst workloads with "
                        "no heavy concurrency. One engine over shared Iceberg covers most of "
                        "what a SOC asks before a second engine earns its keep.",
        "cost_profile": "Lowest: warm Iceberg-on-S3 storage floor, one engine to run.",
        "cite": "Appendix C; Ch5 (single-engine over shared Iceberg).",
    },
    {
        "code": "hybrid_multi_engine",
        "name": "Workload-optimized multi-engine",
        "components": {"storage": "seaweedfs", "catalog": "polaris", "schema": "ocsf",
                       "ingest": ["vector"], "query": ["datafusion", "clickhouse"]},
        "when_it_wins": "Mixed real-time detection and threat hunting with 3-5 engineers: a "
                        "fast aggregation engine (ClickHouse) beside the Iceberg-native default "
                        "(DataFusion), both over the same tables.",
        "cost_profile": "Warm storage floor plus a second engine's compute and on-call. Add the "
                        "second engine only for a workload the first can't serve.",
        "cite": "Appendix C; Ch3 Workload 1+2.",
    },
    {
        "code": "airgap_onprem",
        "name": "Air-gapped on-prem",
        "components": {"storage": "dell_ecs", "catalog": "polaris", "schema": "ocsf",
                       "ingest": ["nifi"], "query": ["trino"]},
        "when_it_wins": "An on-prem or data-sovereignty mandate that rules out cloud-managed "
                        "services. Self-hosted object store + REST catalog + a federating MPP "
                        "engine, all inside the boundary.",
        "cost_profile": "Appliance + self-hosted compute; no cloud egress, but you own the ops.",
        "cite": "Appendix C; Ch3 §3.2 C3 (on-prem / sovereignty).",
    },
    {
        "code": "cost_aggressive",
        "name": "Cost-aggressive route-by-value",
        "components": {"storage": "wasabi", "catalog": "polaris", "schema": "ocsf",
                       "ingest": ["cribl"], "query": ["datafusion"]},
        "when_it_wins": "High-volume, low-value-heavy telemetry where the binding constraint is "
                        "cost: route-by-value at ingest drops 70-90% of the volume before it "
                        "lands, on flat no-egress storage.",
        "cost_profile": "Lowest end to end: most volume never lands, and what does sits on the "
                        "cheapest warm tier.",
        "cite": "Appendix C; Ch3 Workload 5 (route-by-value).",
    },
]


def by_code(code):
    return next((p for p in PRESETS if p["code"] == code), None)


def names() -> list[str]:
    return [p["name"] for p in PRESETS]


def by_name(name):
    return next((p for p in PRESETS if p["name"] == name), None)


def invalid_codes(catalogs) -> list[tuple]:
    """Cross-check every preset's component codes against the live provider catalogs
    ({category: [Provider]}). Returns [(preset_code, [bad 'category:code', ...])] —
    empty when every preset references only real components."""
    out = []
    for preset in PRESETS:
        bad = []
        for category, val in preset["components"].items():
            codes = val if isinstance(val, list) else [val]
            valid = {p.code for p in catalogs.get(category, [])}
            bad += [f"{category}:{c}" for c in codes if c not in valid]
        if bad:
            out.append((preset["code"], bad))
    return out
