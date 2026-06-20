"""Constraint-first decision filter — the book's "the constraint chooses the platform".

Ch3 of the MOAR book argues organizational constraints override technical merit: you
identify the binding constraint first, and a platform that violates a hard (Tier-1)
constraint is eliminated regardless of its strengths ("no detailed evaluation, no POC,
no negotiating it away"). This module encodes that front half of the decision as a pure
function over the console's component catalog, so the picker can surface what a declared
constraint rules out rather than letting an architect choose cold.

Scope. The book's rules name platforms this console does not deploy (Splunk SIEM, Athena,
Sentinel, PostgreSQL). This module translates those rules onto the OPEN-STACK components
in providers.py. Where the book disqualifies "cloud-native managed," that maps to AWS S3 /
Glue / Wasabi here; where it wants "columnar MPP," that maps to Trino / StarRocks / Dremio /
ClickHouse, and so on. Rules that have no open-stack analog are omitted rather than invented.

Verdicts, from the book's own language:
  - disqualify : a hard Tier-1 constraint rules this component out.
  - caution    : a real risk worth a flag, the book's heavy penalty, not an elimination.
  - favor      : the constraint actively prefers this component.
  - neutral    : the constraint says nothing about this component.
Precedence when several constraints touch one component: disqualify > caution > favor
(hard rules win; a surfaced risk beats a preference).

The three-tier weights (mandatory disqualifies / preferred x3 / nice-to-have x1) live in
TIER_WEIGHTS for the scoring pass that builds on this; this module implements the Tier-1
filter (the part that does ~70-87% of the funnel reduction in Ch3).
"""
from __future__ import annotations

# Three-tier requirement weights (Ch3 §3.1). Tier 1 is a hard gate (handled by the
# disqualify rules below); Tiers 2/3 are for the follow-on weighted-scoring pass.
TIER_WEIGHTS = {"mandatory": None, "preferred": 3, "nice_to_have": 1}

# Constraint categories the architect declares. Each: label, options [(code, label)],
# default code, and whether it is multi-select.
CONSTRAINTS = {
    "deployment": {
        "label": "Deployment",
        "multi": False,
        "default": "cloud_ok",
        "options": [
            ("cloud_ok", "Cloud is fine"),
            ("on_prem_airgap", "On-prem / air-gapped"),
            ("multi_region_sovereignty", "Multi-region data sovereignty"),
        ],
    },
    "team": {
        "label": "Team capacity",
        "multi": False,
        "default": "t_3_5",
        "options": [
            ("t_0_1", "0-1 engineers"),
            ("t_2_3", "2-3 engineers"),
            ("t_3_5", "3-5 engineers"),
            ("t_5plus", "5+ engineers"),
        ],
    },
    "vendor": {
        "label": "Vendor posture",
        "multi": False,
        "default": "open_first",
        "options": [
            ("open_first", "Open-source first"),
            ("aws_committed", "AWS-committed"),
            ("low_oss_tolerance", "Low OSS tolerance (need SLAs)"),
        ],
    },
    "workload": {
        "label": "Primary workload",
        "multi": False,
        "default": "balanced",
        "options": [
            ("balanced", "Balanced / mixed"),
            ("real_time_detection", "Real-time detection"),
            ("threat_hunting", "Threat hunting"),
            ("forensics", "Forensic deep-dive"),
            ("compliance_retention", "Compliance retention"),
            ("pipeline_routing", "Pipeline / data routing"),
        ],
    },
    "compliance": {
        "label": "Compliance",
        "multi": True,
        "default": [],
        "options": [
            ("immutable_audit", "Immutable / WORM audit trail"),
            ("long_retention_queryable", "7-year queryable retention"),
        ],
    },
    "cost": {
        "label": "Cost priority",
        "multi": False,
        "default": "balanced",
        "options": [
            ("balanced", "Balanced"),
            ("aggressive_reduction", "Aggressive cost reduction"),
        ],
    },
}

# Rules: (constraint_category, constraint_code, component_code, verdict, reason).
# Each reason cites the book section it comes from. Component codes are providers.py codes.
_C = "Ch3 §3.2"   # organizational constraints
_W = "Ch3 §3.3"   # workload-to-capability
RULES = [
    # --- Deployment: on-prem / air-gap knocks out cloud-managed (C3) ---
    ("deployment", "on_prem_airgap", "aws_s3", "disqualify",
     f"On-prem/air-gap rules out cloud-managed object storage ({_C}: an on-prem requirement knocks out cloud-native entirely). Use SeaweedFS / MinIO / Dell ECS."),
    ("deployment", "on_prem_airgap", "aws_glue", "disqualify",
     f"AWS Glue is AWS-managed and IAM-bound; air-gap rules it out ({_C}). Use Polaris / Nessie / Lakekeeper."),
    ("deployment", "on_prem_airgap", "wasabi", "disqualify",
     f"Wasabi is a cloud SaaS object store; air-gap rules it out ({_C})."),
    ("deployment", "on_prem_airgap", "dell_ecs", "favor",
     "Dell ECS is an on-prem S3-compatible appliance built for air-gapped sites."),
    ("deployment", "on_prem_airgap", "seaweedfs", "favor",
     "Self-hosted, runs fully on-prem / air-gapped."),
    ("deployment", "on_prem_airgap", "minio", "favor",
     "Self-hosted S3, runs fully on-prem / air-gapped."),
    # --- Deployment: multi-region sovereignty (C3, GDPR) ---
    ("deployment", "multi_region_sovereignty", "aws_s3", "caution",
     f"Single-region cloud consolidation can violate residency law ({_C}, GDPR/multi-region); keep regional lakes or federate."),
    ("deployment", "multi_region_sovereignty", "aws_glue", "caution",
     f"A region-bound managed catalog fights multi-region sovereignty; favor a portable open catalog + federation ({_C})."),
    ("deployment", "multi_region_sovereignty", "trino", "favor",
     f"Federates the shared catalog across regions without moving data ({_C}: the data-virtualization path for sovereignty)."),
    # --- Team capacity: 0-1 engineers can't run heavy self-hosted infra (C1) ---
    ("team", "t_0_1", "nifi", "caution",
     f"0-1 engineers: NiFi's heavy JVM and registry-managed flows need operators ({_C}: 0-1 engineers can't run self-hosted infra). Favor a lighter ingest or a managed service."),
    ("team", "t_0_1", "trino", "caution",
     f"0-1 engineers: a Trino cluster needs ops and tuning ({_C})."),
    ("team", "t_0_1", "starrocks", "caution",
     f"0-1 engineers: StarRocks is a cluster to operate ({_C})."),
    ("team", "t_0_1", "datafusion", "favor",
     "Embeddable, no JVM or cluster — the lightest query option for a tiny team."),
    ("team", "t_0_1", "duckdb", "favor",
     "Zero-config single process — runs with effectively no ops."),
    ("team", "t_0_1", "vector", "favor",
     "One declarative config, light footprint."),
    ("team", "t_0_1", "fluentbit", "favor",
     "~20MB footprint, minimal ops."),
    # --- Vendor posture (C4) ---
    ("vendor", "aws_committed", "aws_s3", "favor",
     f"AWS-committed: native S3 fits the existing commitment ({_C})."),
    ("vendor", "aws_committed", "aws_glue", "favor",
     f"AWS-committed: Glue is the AWS-native catalog ({_C})."),
    ("vendor", "low_oss_tolerance", "trino", "caution",
     f"Low OSS tolerance: Trino is community Apache; the book flags pure-OSS-without-a-vendor for orgs needing SLAs/accountability ({_C})."),
    ("vendor", "low_oss_tolerance", "datafusion", "caution",
     f"Low OSS tolerance: DataFusion is an Apache library with no single commercial owner ({_C})."),
    ("vendor", "low_oss_tolerance", "cribl", "favor",
     "Commercially licensed and supported pipeline — fits a low-OSS-tolerance accountability need."),
    ("vendor", "low_oss_tolerance", "dremio", "favor",
     "Backed by a commercial vendor with support SLAs."),
    # --- Compliance: immutability / WORM (Workload 4) ---
    ("compliance", "immutable_audit", "clickhouse", "caution",
     f"Immutable-audit requirement: ClickHouse MergeTree supports DELETE and isn't append-only by default — an audit risk ({_W} Workload 4). Iceberg snapshots are the safer base."),
    ("compliance", "immutable_audit", "cef", "caution",
     "CEF is flat and lossy — a poor base for an evidentiary, reconstructable audit trail."),
    ("compliance", "immutable_audit", "raw", "caution",
     "Raw defers all parsing to query time; an immutable audit trail wants structured OCSF landed once."),
    ("compliance", "immutable_audit", "ocsf", "favor",
     "Structured, nested OCSF preserves the detail an audit reconstruction needs."),
    # --- Compliance: 7-year queryable retention (Workload 4) ---
    ("compliance", "long_retention_queryable", "clickhouse", "caution",
     f"7-year queryable retention: ClickHouse cold-tier query transparency is manual/limited ({_W} Workload 4); the Iceberg-on-S3 tiering path keeps cold data queryable."),
    ("compliance", "long_retention_queryable", "datafusion", "favor",
     f"Reads immutable Iceberg snapshots; tiered S3->cold stays queryable ({_W} Workload 4)."),
    ("compliance", "long_retention_queryable", "trino", "favor",
     f"Queries tiered Iceberg including cold without an 'archive offline' break ({_W} Workload 4)."),
    # --- Workload: real-time detection (Workload 1) ---
    ("workload", "real_time_detection", "clickhouse", "favor",
     f"Real-time detection: materialized views give ~sub-5s aggregations ({_W} Workload 1)."),
    ("workload", "real_time_detection", "starrocks", "favor",
     f"Real-time detection: degrades gracefully under load for low-latency serving ({_W} Workload 1)."),
    ("workload", "real_time_detection", "duckdb", "caution",
     f"Real-time detection: DuckDB is batch / single-process, not a low-latency serving engine ({_W} Workload 1)."),
    ("workload", "real_time_detection", "datafusion", "caution",
     f"Real-time detection: DataFusion is batch-analytic; a <30s mandate needs a streaming engine this open-stack picker doesn't include ({_W} Workload 1)."),
    # --- Workload: threat hunting (Workload 2) ---
    ("workload", "threat_hunting", "trino", "favor",
     f"Threat hunting: distributed MPP over columnar Iceberg/Parquet ({_W} Workload 2)."),
    ("workload", "threat_hunting", "starrocks", "favor",
     f"Threat hunting: MPP joins over columnar storage ({_W} Workload 2)."),
    ("workload", "threat_hunting", "dremio", "favor",
     f"Threat hunting: MPP plus Arrow/Parquet predicate pushdown ({_W} Workload 2)."),
    ("workload", "threat_hunting", "clickhouse", "favor",
     f"Threat hunting: fast group-by / aggregation scans ({_W} Workload 2)."),
    ("workload", "threat_hunting", "duckdb", "caution",
     f"Threat hunting: DuckDB is single-process (~10-analyst ceiling, A-14) — a local oracle, not a shared hunt engine ({_W} Workload 2)."),
    # --- Workload: forensics (Workload 3) ---
    ("workload", "forensics", "clickhouse", "favor",
     f"Forensics: primary-key index gives sub-second point retrieval of full events ({_W} Workload 3)."),
    ("workload", "forensics", "duckdb", "favor",
     f"Forensics: an excellent single-incident local oracle for full-event retrieval ({_W} Workload 3)."),
    # --- Workload: compliance retention (Workload 4) ---
    ("workload", "compliance_retention", "datafusion", "favor",
     f"Compliance retention: reads immutable Iceberg snapshots over tiered S3 ({_W} Workload 4)."),
    ("workload", "compliance_retention", "trino", "favor",
     f"Compliance retention: queries tiered Iceberg including cold ({_W} Workload 4)."),
    ("workload", "compliance_retention", "clickhouse", "caution",
     f"Compliance retention: cold-tier query transparency is limited and DELETE is an audit risk ({_W} Workload 4)."),
    # --- Workload: pipeline routing / route-by-value (Workload 5) ---
    ("workload", "pipeline_routing", "cribl", "favor",
     f"Pipeline routing: route-by-value plus multi-destination writes at scale ({_W} Workload 5)."),
    ("workload", "pipeline_routing", "tenzir", "favor",
     f"Pipeline routing: OCSF-native route-by-value pipeline ({_W} Workload 5)."),
    ("workload", "pipeline_routing", "fluentbit", "caution",
     f"Pipeline routing: Fluent Bit's basic filtering is insufficient when route-by-value is a Tier-1 mandate ({_W} Workload 5)."),
    ("workload", "pipeline_routing", "vector", "caution",
     f"Pipeline routing: capable, but route-by-value cost reduction at scale is where Cribl/Tenzir lead ({_W} Workload 5)."),
    # --- Cost: aggressive reduction ---
    ("cost", "aggressive_reduction", "cribl", "favor",
     f"Aggressive cost reduction: route-by-value drops 70-90% of low-value volume ({_W} Workload 5)."),
    ("cost", "aggressive_reduction", "tenzir", "favor",
     f"Aggressive cost reduction: OCSF-native route-by-value reduction ({_W} Workload 5)."),
    ("cost", "aggressive_reduction", "wasabi", "favor",
     "Aggressive cost reduction: flat low-cost storage with no egress fees."),
]

_RANK = {"disqualify": 3, "caution": 2, "favor": 1, "neutral": 0}


# --- UI helpers (label <-> code), so the marimo cells stay thin --------------- #

def option_labels(category) -> list[str]:
    return [lbl for _c, lbl in CONSTRAINTS[category]["options"]]


def default_label(category) -> str:
    cfg = CONSTRAINTS[category]
    return _label_for(category, cfg["default"]) if not cfg["multi"] else ""


def _label_for(category, code) -> str:
    return next((lbl for c, lbl in CONSTRAINTS[category]["options"] if c == code), str(code))


def code_for_label(category, label) -> str | None:
    return next((c for c, lbl in CONSTRAINTS[category]["options"] if lbl == label), None)


# --- The filter --------------------------------------------------------------- #

def _active_pairs(selection) -> list[tuple]:
    """Flatten the declared selection into (category, code) pairs, dropping any
    single-select left on its category default — that means "not constraining on this".
    Multi-select values (compliance) are always active when present."""
    pairs = []
    for cat, val in (selection or {}).items():
        cfg = CONSTRAINTS.get(cat)
        default = cfg["default"] if cfg else None
        codes = val if isinstance(val, list) else [val]
        for code in codes:
            if not code:
                continue
            if not isinstance(default, list) and code == default:
                continue
            pairs.append((cat, code))
    return pairs


def verdict_for(component_code, selection) -> dict:
    """Resolve a single component against the declared constraints.
    Returns {verdict, reasons:[...]} with disqualify > caution > favor precedence."""
    hits = [(v, reason) for cat, code in _active_pairs(selection)
            for (rc, rv, comp, v, reason) in RULES
            if rc == cat and rv == code and comp == component_code]
    if not hits:
        return {"verdict": "neutral", "reasons": []}
    top = max(_RANK[v] for v, _ in hits)
    verdict = next(k for k, r in _RANK.items() if r == top)
    reasons = [reason for v, reason in hits if v == verdict]
    return {"verdict": verdict, "reasons": reasons}


# Three-tier requirement model (Ch3 §3.1): each constraint category maps to a tier.
# deployment + compliance are Tier-1 (hard/mandatory), workload is Tier-2 (strongly
# preferred), vendor/cost/team are Tier-3 (nice-to-have). Tier-1 and Tier-2 favors/cautions
# weigh x3; Tier-3 weighs x1 (the book's "3x for preferred", "1x / tiebreaker" for nice-to-have).
CONSTRAINT_TIER = {"deployment": 1, "compliance": 1, "workload": 2,
                   "vendor": 3, "cost": 3, "team": 3}
_TIER_WEIGHT = {1: 3, 2: 3, 3: 1}


def _verdict_of_one(component_code, cat, code) -> str:
    """The verdict a SINGLE declared constraint (cat=code) places on a component."""
    hits = [v for (rc, rv, comp, v, _r) in RULES
            if rc == cat and rv == code and comp == component_code]
    if not hits:
        return "neutral"
    top = max(_RANK[v] for v in hits)
    return next(k for k, r in _RANK.items() if r == top)


def score_component(component_code, selection):
    """Three-tier weighted score (Ch3). Returns None if a hard (Tier-1) constraint
    disqualifies the component; otherwise sums, over each declared constraint that touches
    it, tier_weight * (+1 favor / -1 caution / 0 neutral). Higher is a better fit."""
    total = 0
    for cat, code in _active_pairs(selection):
        v = _verdict_of_one(component_code, cat, code)
        if v == "disqualify":
            return None
        total += _TIER_WEIGHT[CONSTRAINT_TIER.get(cat, 3)] * (1 if v == "favor" else -1 if v == "caution" else 0)
    return total


def funnel(selection, catalogs) -> dict:
    """Ch3's filtering funnel made concrete over the open-stack catalog. For each category,
    drop the components a hard constraint disqualifies and rank the rest by three-tier
    weighted score (score_component). catalogs: {category: [component_code, ...]}. Returns
    {category: {total, reachable, top, order:[(code, verdict, score), ...]}} — how many of M
    options each category narrows to, the best-fit pick, and the ranked order to consider."""
    out = {}
    for cat, codes in (catalogs or {}).items():
        ranked = []
        for code in codes:
            score = score_component(code, selection)
            if score is None:  # disqualified by a hard constraint
                continue
            ranked.append((code, verdict_for(code, selection)["verdict"], score))
        ranked.sort(key=lambda e: -e[2])  # best-fit (highest weighted score) first
        out[cat] = {"total": len(codes), "reachable": len(ranked),
                    "top": ranked[0][0] if ranked else None, "order": ranked}
    return out


def evaluate(selection, picked) -> dict:
    """Evaluate declared constraints against the current picks.

    selection: {category: code | [codes]} from CONSTRAINTS.
    picked: {component_category: [component_codes]} currently selected in the picker.
    Returns picked_verdicts (one row per picked component that a constraint touches),
    a catalog-wide disqualified set, and a summary_md line.
    """
    picked_rows = []
    counts = {"disqualify": 0, "caution": 0, "favor": 0}
    for codes in (picked or {}).values():
        for code in codes:
            r = verdict_for(code, selection)
            if r["verdict"] == "neutral":
                continue
            counts[r["verdict"]] += 1
            picked_rows.append({"code": code, "verdict": r["verdict"],
                                "reason": " ".join(r["reasons"])})
    # Catalog-wide disqualifications (components ruled out whether or not picked).
    all_comp_codes = {comp for (_c, _v, comp, _vd, _r) in RULES}
    catalog_disq = sorted(c for c in all_comp_codes
                          if verdict_for(c, selection)["verdict"] == "disqualify")
    picked_disq = sorted({row["code"] for row in picked_rows if row["verdict"] == "disqualify"})

    order = {"disqualify": 0, "caution": 1, "favor": 2}
    picked_rows.sort(key=lambda r: (order[r["verdict"]], r["code"]))

    active = _active_pairs(selection)
    if not active:
        summary = "No binding constraint declared — every component is reachable. Declare a constraint to filter."
    else:
        summary = (f"**{len(active)} constraint(s) declared.** Of your picks that a constraint touches: "
                   f"{counts['disqualify']} disqualified, {counts['caution']} cautioned, {counts['favor']} favored. "
                   f"Across the full catalog, {len(catalog_disq)} component(s) are disqualified by these constraints.")
        if picked_disq:
            summary += f" **You have picked a disqualified component: {', '.join(picked_disq)}.**"

    return {
        "picked_verdicts": picked_rows,
        "catalog_disqualified": catalog_disq,
        "picked_disqualified": picked_disq,
        "counts": counts,
        "summary_md": summary,
        "active_constraints": active,
    }
