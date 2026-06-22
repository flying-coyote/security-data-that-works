"""D3FEND bridge — design-time defensive STRUCTURE over the vendored coverage corpus (PG-3).

WHAT THIS ANSWERS. Given an ATT&CK technique, "what design-time D3FEND defensive
STRUCTURE *possibly* addresses it" — strictly as DESIGN-TIME POSSIBILITY-OF-COVERAGE,
NEVER "coverage of your telemetry". The matrix corpus is built from ARTIFACT
CO-OCCURRENCE: an attack and a defense share a digital artifact. That edge is
INTENT-BLIND — counters != detects — so it is ALWAYS trust 0.25 /
proxy_quality="artifact_cooccurrence", the scg taxonomy's weakest traversable
tier. defenses_for() can NEVER emit a hard claim from a matrix edge; it only ever
returns tier-0.25 leads, each carrying intent_blind=True and the caveat.

TRUST TAXONOMY is vendored VERBATIM from
  sdw-lab-benchmarks/security-context-graph/scg_mcp.py (the TRUST dict, lines 42-54)
plus the weakest-link MIN rule (scg_mcp.py:176-179 / :288): a multi-hop chain is
only as sound as its least-trustworthy edge, so a path's trust = min(edge trust).
An intent-blind 0.25 edge can NEVER be upgraded by MINing it against a higher tier
— weakest_link(0.70, 0.25) == 0.25, weakest_link(1.00, 0.25) == 0.25.

TWO disjoint sources, never blurred:
  - the inferred corpus (artifact_cooccurrence, 0.25, intent-blind) loaded from
    d3fend_coverage.csv, and
  - CURATED_DETECTION_DEFENSE (ontology_curated, 0.70), a small hand-authored,
    intent-AWARE map of each in-corpus console detection technique to the one
    D3FEND technique that genuinely DETECTS it. Because it is editorial and
    intent-aware, it is allowed to read as a real claim at 0.70 — but it is kept
    in a SEPARATE dict so the 0.25 inferred edges and the 0.70 curated edges never
    blur. T1530 deliberately has NO curated entry (honest gap).

SAFETY. Every surfaced technique / defense / artifact label is routed through
analyze._safe_key before it is returned, exactly as detections.scan() does — the
vendored CSV is already sanitized at generate time, and this re-sanitizes at
render so a hand-passed label is neutralized too.

Pure stdlib (csv only) — no marimo / duckdb / pandas. Synthetic/public standards
content only (ATT&CK / D3FEND ids + artifact labels); only Sigma / ATT&CK / D3FEND
/ CAR are ever named, never a commercial engine beside a number.
"""
from __future__ import annotations

import csv
import os

from analyze import _safe_key

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS_PATH = os.path.join(HERE, "d3fend_coverage.csv")

# ---------------------------------------------------------------------------
# TRUST taxonomy — VERBATIM from scg_mcp.py:42-54 (do not edit the values).
# ---------------------------------------------------------------------------
TRUST = {
    "measured": 1.00,            # (1) first-party measured field->OCSF mapping
    "skos_typed": 0.90,          # (5) D3FEND->800-53/CCI typed SKOS relation
    "ontology_axiom": 0.85,      # (3) ontology subclass / restriction axiom (logical)
    "doc_link": 0.80,            # (2) OCSF<->D3FEND maintainer hyperlink (seeAlso)
    "ontology_curated": 0.70,    # (3) ontology-authored artifact tag
    "curated": 0.65,             # (4') hand-authored ATT&CK mitigation / in-tactic
    "ctid_reroute": 0.50,        # (5') SCF->ATT&CK = CTID 800-53->ATT&CK re-routed
    "scf_strm": 0.45,            # SCF->framework STRM crosswalk
    "derived": 0.40,             # rollup / derived statistic
    "artifact_cooccurrence": 0.25,  # (4) offense<->defense INFERRED, intent-blind -- WEAK
    "unmapped": 0.00,            # explicit honest gap (a null mapping), not traversable
}

# scg PROXY_NOTE for the inferred edge (scg_mcp.py:65-66).
PROXY_NOTE = (
    "INFERRED from shared digital artifact, intent-blind -- do NOT state as an "
    "established relationship; counters!=detects"
)

# The caveat every matrix-sourced edge carries on its way out.
COOCCURRENCE_CAVEAT = (
    "DESIGN-TIME possibility-of-coverage, intent-blind; counters!=detects; "
    "NOT coverage of your telemetry."
)

# Unknown-proxy fallback (scg_mcp.py:72): any pq not in TRUST -> 0.30.
_UNKNOWN_PROXY = 0.30


def _trust(proxy_quality: str) -> float:
    """Trust score for a proxy_quality, with the scg unknown-proxy fallback (0.30)."""
    return TRUST.get(proxy_quality, _UNKNOWN_PROXY)


def weakest_link(*tiers: float) -> float:
    """The scg weakest-link MIN rule (scg_mcp.py:288 `min(h["trust"] for h in hops)`).

    A multi-hop chain is only as sound as its least-trustworthy edge. An
    intent-blind 0.25 edge can NEVER be upgraded by MINing it against a higher
    tier: weakest_link(0.70, 0.25) == 0.25, weakest_link(1.00, 0.25) == 0.25.
    """
    if not tiers:
        return 0.0
    return min(tiers)


# ---------------------------------------------------------------------------
# CURATED detection -> defense map (ontology_curated, 0.70). SEPARATE from the
# inferred 0.25 corpus and intent-AWARE by construction. Each d3fend_id is a
# DETECT-phase technique that actually appears in wall_columns.csv and that
# genuinely detects the technique. T1530 deliberately has NO entry (honest gap).
# ---------------------------------------------------------------------------
CURATED_DETECTION_DEFENSE = {
    "T1071": {  # C2 over application-layer protocol
        "d3fend_id": "D3-NTSA", "def_tech": "Network Traffic Signature Analysis",
        "proxy_quality": "ontology_curated", "trust": 0.70,
    },
    "T1048": {  # Exfiltration over alternative protocol
        "d3fend_id": "D3-NTCD", "def_tech": "Network Traffic Community Deviation",
        "proxy_quality": "ontology_curated", "trust": 0.70,
    },
    "T1110": {  # Brute force / credential stuffing
        "d3fend_id": "D3-CCSA", "def_tech": "Credential Compromise Scope Analysis",
        "proxy_quality": "ontology_curated", "trust": 0.70,
    },
    "T1490": {  # Inhibit system recovery (shadow-copy deletion)
        "d3fend_id": "D3-EFA", "def_tech": "Emulated File Analysis",
        "proxy_quality": "ontology_curated", "trust": 0.70,
    },
    "T1003.001": {  # LSASS memory credential dumping
        "d3fend_id": "D3-PLA", "def_tech": "Process Lineage Analysis",
        "proxy_quality": "ontology_curated", "trust": 0.70,
    },
}

# ---------------------------------------------------------------------------
# ARTIFACT_OCSF — SMALL curated map from a D3FEND artifact LABEL to the OCSF
# class_uid(s) a console ROUTER actually produces. The RHS is drawn ONLY from
# {1007, 3002, 4001, 6003} — the four class_uids detections.py _class_of emits
# (no other class_uid may appear). When a D3FEND artifact has no console
# producer, required_ocsf_classes returns [] (honest "no telemetry produces this
# artifact"); it NEVER invents a class_uid.
#
#   4001 Network Activity  : c2_beacon (detections.py:34), exfil_egress (:45)
#   3002 Authentication    : credential_stuffing (:57)  -- keys on src_ip+user
#   1007 Process Activity  : shadow_copy_deletion (:69), lsass (:82) -- keys on device_hostname
#   6003 API Activity       : api_bulk_retrieval (:95)  -- keys on actor_user
# ---------------------------------------------------------------------------
ARTIFACT_OCSF = {
    "Network Traffic": [4001],
    "Network Flow": [4001],
    "Credential": [3002],
    "User Account": [3002],
    "Session": [3002],
    "Process": [1007],
    "Process Tree": [1007],
    "Cloud Storage": [6003],
    "Database": [6003],
    "Document File": [6003],
}
_OCSF_ALLOWED = {1007, 3002, 4001, 6003}

# Module-level provenance, populated by load_corpus from the _meta row.
CORPUS_META: dict = {}


def load_corpus(path: str | None = None) -> list[dict]:
    """Read the vendored d3fend_coverage.csv; drop the _meta row into CORPUS_META.

    Returns the data rows (covered cells + zero-defense sentinels) with the int
    columns coerced. Pure-stdlib csv; no stack.
    """
    global CORPUS_META
    p = path or CORPUS_PATH
    rows = []
    with open(p, newline="") as f:
        for r in csv.DictReader(f):
            if r["off_tech_id"] == "_meta":
                CORPUS_META = dict(r)
                continue
            r["shared_artifacts"] = int(r["shared_artifacts"] or 0)
            r["trust"] = float(r["trust"] or 0.0)
            rows.append(r)
    return rows


def _covered_rows(corpus):
    return [r for r in corpus if r["band"] not in ("zero_defense", "_meta")]


def _zero_ids(corpus):
    return {r["off_tech_id"] for r in corpus if r["band"] == "zero_defense"}


def in_corpus(technique: str, corpus: list[dict] | None = None) -> bool:
    """True iff the technique is measured — appears as a covered off_tech_id OR is
    in the zero_defense set. Distinguishes "no defense watches it" (zero-defense,
    still in_corpus) from "not measured at all" (e.g. T1530 -> False)."""
    corpus = corpus if corpus is not None else load_corpus()
    covered = {r["off_tech_id"] for r in _covered_rows(corpus)}
    return technique in covered or technique in _zero_ids(corpus)


def is_zero_defense(technique: str, corpus: list[dict] | None = None) -> bool:
    """True iff the technique is one of the 27 band=='zero_defense' sentinel rows."""
    corpus = corpus if corpus is not None else load_corpus()
    return technique in _zero_ids(corpus)


def defenses_for(technique: str, band: str = "detect", corpus: list[dict] | None = None) -> list[dict]:
    """D3FEND defenses whose wall phase == band that share artifacts with the technique.

    EVERY returned edge is an INTENT-BLIND artifact_cooccurrence lead: tagged
    proxy_quality="artifact_cooccurrence", trust=0.25, intent_blind=True, with the
    COOCCURRENCE_CAVEAT. This can NEVER return a hard claim.

    Honest degrade:
      - is_zero_defense -> [] with reason "zero-defense: artifacts exist but no
        D3FEND technique watches them".
      - not in_corpus   -> [] with reason "not in corpus (no shared-artifact join
        exists)".
    On a degrade, returns a single-element list carrying ONLY the reason (no
    fabricated empty-but-claimed defense), so the caller can surface the honest gap.
    """
    corpus = corpus if corpus is not None else load_corpus()

    if not in_corpus(technique, corpus):
        return [{"reason": "not in corpus (no shared-artifact join exists)",
                 "technique": technique, "edges": 0}]
    if is_zero_defense(technique, corpus):
        return [{"reason": "zero-defense: artifacts exist but no D3FEND technique watches them",
                 "technique": technique, "edges": 0}]

    out = []
    for r in _covered_rows(corpus):
        if r["off_tech_id"] != technique:
            continue
        if band and r["band"] != band:
            continue
        out.append({
            "off_tech_id": _safe_key(r["off_tech_id"]),
            "d3fend_id": _safe_key(r["d3fend_id"]),
            "def_tech": _safe_key(r["def_tech"]),
            "phase": _safe_key(r["phase"]),
            "tactic": _safe_key(r["tactic"]),
            "shared_artifacts": int(r["shared_artifacts"]),
            "shared_artifact_names": _safe_key(r["shared_artifact_names"]),
            "proxy_quality": "artifact_cooccurrence",
            "trust": 0.25,
            "intent_blind": True,
            "caveat": COOCCURRENCE_CAVEAT,
        })
    return out


def curated_defense_for(technique: str) -> dict | None:
    """The hand-authored, intent-AWARE detect-defense for a console detection
    technique (tier 0.70 ontology_curated), or None if there is no curated entry
    (e.g. T1530 — honest gap). Kept separate from the 0.25 inferred corpus."""
    c = CURATED_DETECTION_DEFENSE.get(technique)
    if not c:
        return None
    return {
        "off_tech_id": _safe_key(technique),
        "d3fend_id": _safe_key(c["d3fend_id"]),
        "def_tech": _safe_key(c["def_tech"]),
        "proxy_quality": "ontology_curated",
        "trust": 0.70,
        "intent_blind": False,
    }


def required_ocsf_classes(defense_or_artifact) -> list[int]:
    """OCSF class_uids a console router produces for a defense's shared artifacts.

    Accepts either an artifact LABEL (str, possibly pipe-joined as in
    shared_artifact_names) or a defense dict carrying shared_artifact_names. Looks
    each artifact up in the SMALL curated ARTIFACT_OCSF map and unions the real
    class_uids (only ever from {1007,3002,4001,6003}). Returns [] (honest) when no
    console router produces the artifact — never fabricates a class_uid.
    """
    if isinstance(defense_or_artifact, dict):
        names = defense_or_artifact.get("shared_artifact_names", "")
    else:
        names = defense_or_artifact or ""
    labels = [n.strip() for n in str(names).split("|") if n.strip()]
    out: list[int] = []
    for label in labels:
        for cu in ARTIFACT_OCSF.get(label, []):
            if cu in _OCSF_ALLOWED and cu not in out:
                out.append(cu)
    return sorted(out)
