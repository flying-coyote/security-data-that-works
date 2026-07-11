"""ATT&CK coverage — DESIGN-TIME defensive STRUCTURE, intent-blind (PG-4).

WHAT THIS IS, AND IS NOT. This module reads three already-aggregate inputs — the
hunt inventory (detections.library_catalog), the per-class VISIBILITY signal
(analyze.analyze_table's by_class: class_uid -> COUNT), and the scan() findings
(detections.scan, aggregate-safe match counts) — and resolves a per-technique
COVERAGE STATE. The state is DESIGN-TIME STRUCTURE over a synthetic/public
preview: which OCSF classes landed (visible), which techniques a DETECTIONS spec
watches (has_detection), and which actually matched this run (fired). It is
NEVER "coverage of your telemetry" — there is no live telemetry here, and the
D3FEND edges below are intent-blind by construction.

THE FOUR STATES (precedence fired > covered > dark_spot > blind):
  fired      = visible AND has_detection AND fired      (scan() actually matched)
  covered    = visible AND has_detection AND NOT fired  (class present + a hunt exists, nothing matched)
  dark_spot  = has_detection AND NOT visible            (a hunt exists but its OCSF class never landed)
  blind      = NOT has_detection                        (no spec at all — structurally unwatched)

D3FEND STRUCTURE per record comes straight from the PG-3 bridge (d3fend_bridge):
in_corpus / is_zero_defense / the detect-band intent-blind 0.25 edges /
curated_defense_for (the SEPARATE 0.70 ontology_curated detect-defense) /
required_ocsf_classes. The weakest_trust_tier is the scg weakest-link MIN over
every D3FEND claim attached to the record, so a 0.25 intent-blind edge can never
be upgraded by a co-present 0.70 curated edge.

AGGREGATE-SAFE. Every surfaced technique / class / defense / artifact label is
routed through analyze._safe_key (the same telemetry-injection boundary
detections.scan and d3fend_bridge use). A record carries only technique ids,
tactic / title labels, class_uids (ints from the closed {1007,3002,4001,6003}
set), counts, and _safe_key'd defense labels — never a raw telemetry row.

NAVIGATOR. navigator_layer() emits an ATT&CK Navigator v4.5 JSON layer. Each
in-corpus technique carries its status and weakest_trust_tier in metadata; a
NOT-in-corpus technique (e.g. T1530) is enabled:false with NO fabricated score
or color — only the honest comment + metadata. No technique ever carries a
numeric `score` key (an invented number would read as a real coverage claim).

Pure stdlib (json only) — no marimo / duckdb / pandas. Reuses, never rebuilds:
analyze._safe_key, detections (library_catalog / scan / _class_of), d3fend_bridge.
"""
from __future__ import annotations

import datetime as _dt
import json
import os

import detections as dets
import d3fend_bridge as br
import decay
from analyze import _safe_key

# ATT&CK version pin for the Navigator layer metadata. The console names
# Sigma/ATT&CK/D3FEND/CAR freely; this is a public standards version string.
ATTACK_VERSION = "16"

# Status -> Navigator legend (color drives only off the status ENUM, never an
# invented number). score is the Navigator legend slot, NOT a coverage metric —
# it selects a fixed legend color, and is omitted entirely for not-in-corpus
# techniques so nothing reads as a fabricated coverage score.
_STATUS_EMOJI = {"fired": "🔴", "covered": "🟢", "dark_spot": "🟡", "blind": "⚪"}
_STATUS_COLOR = {
    "fired": "#c14a4a",      # red — a hunt matched this run
    "covered": "#4a8c4a",    # green — class present + a hunt exists, nothing matched
    "dark_spot": "#d9a441",  # amber — a hunt exists but its OCSF class never landed
    "blind": "#999999",      # grey — no hunt at all
}
_STATUS_LEGEND = [
    {"label": "fired — a hunt matched this run", "color": _STATUS_COLOR["fired"]},
    {"label": "covered — class present + hunt exists, no match", "color": _STATUS_COLOR["covered"]},
    {"label": "dark_spot — hunt exists, OCSF class never landed", "color": _STATUS_COLOR["dark_spot"]},
    {"label": "blind — no hunt (structurally unwatched)", "color": _STATUS_COLOR["blind"]},
]


def _norm_class(value):
    """Coerce a class_uid to int for comparison (by_class keys may be int or str)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return value


def _visible(by_class, class_uid) -> bool:
    """A class is VISIBLE iff it appears in by_class with count > 0. by_class maps
    class_uid -> COUNT (analyze.py:191); keys may be int or str, so normalize both
    sides. A class present with count 0 is NOT visible (honest dark_spot)."""
    if not isinstance(by_class, dict):
        return False
    target = _norm_class(class_uid)
    for k, n in by_class.items():
        if _norm_class(k) == target:
            try:
                return int(n) > 0
            except (TypeError, ValueError):
                return False
    return False


def assess(scan_findings, by_class, corpus=None) -> list[dict]:
    """Resolve a CoverageRecord per technique in the hunt inventory.

    scan_findings: detections.scan() output (list of {technique, match_count, ...}).
    by_class:      analyze.analyze_table()['by_class'] — {class_uid: count} VISIBILITY.
    corpus:        optional pre-loaded d3fend corpus (else the bridge loads it).

    One record per detections.library_catalog() entry (the six DETECTIONS specs).
    Each record carries the resolved status, the visibility / detection / fired
    booleans, the design-time D3FEND structure, and the weakest trust tier over
    every D3FEND claim. Every label is _safe_key'd; class_uids are closed-set ints.
    """
    corpus = corpus if corpus is not None else br.load_corpus()

    # Index findings by technique for the fired lookup (match_count > 0).
    fired_by_tech = {}
    for f in (scan_findings or []):
        tech = f.get("technique")
        if tech is not None:
            try:
                fired_by_tech[tech] = int(f.get("match_count", 0)) > 0
            except (TypeError, ValueError):
                fired_by_tech[tech] = False

    records = []
    for hunt in dets.library_catalog():
        technique = hunt["technique"]
        class_uid = hunt["class_uid"]

        visible = _visible(by_class, class_uid)
        has_detection = True  # the inventory IS the DETECTIONS specs (a hunt exists)
        fired = fired_by_tech.get(technique, False)

        # STATUS TRUTH TABLE — explicit if/elif ladder, precedence fired > covered
        # > dark_spot > blind, so exactly one status is assigned.
        if has_detection and visible and fired:
            status = "fired"
        elif has_detection and visible and not fired:
            status = "covered"
        elif has_detection and not visible:
            status = "dark_spot"
        else:  # not has_detection
            status = "blind"

        # Design-time D3FEND structure from the PG-3 bridge.
        in_corpus = br.in_corpus(technique, corpus)
        is_zero_defense = br.is_zero_defense(technique, corpus)
        edges = br.defenses_for(technique, "detect", corpus)
        inferred_edges = [e for e in edges if "reason" not in e]
        curated = br.curated_defense_for(technique)

        # required OCSF classes = union over the real inferred edges (honest [] when none).
        required = []
        for e in inferred_edges:
            for cu in br.required_ocsf_classes(e):
                if cu not in required:
                    required.append(cu)
        required = sorted(required)

        # weakest trust tier = scg weakest-link MIN over EVERY D3FEND claim on the
        # record: each inferred edge is 0.25, plus the curated 0.70 if present. A
        # 0.25 inferred edge dominates (min) — never upgraded. 0.0 when no claim.
        tiers = [0.25] * len(inferred_edges)
        if curated:
            tiers.append(curated["trust"])
        weakest_trust_tier = br.weakest_link(*tiers) if tiers else 0.0

        records.append({
            "technique": _safe_key(technique),
            "tactic": _safe_key(hunt.get("tactic", "—")),
            "title": _safe_key(hunt.get("title", "")),
            "class_uid": class_uid,  # closed-set int from {1007,3002,4001,6003}
            "visible": visible,
            "has_detection": has_detection,
            "fired": fired,
            "status": status,
            "in_corpus": in_corpus,
            "is_zero_defense": is_zero_defense,
            "required_classes": required,
            "landed_classes": [class_uid] if visible else [],
            "curated_defense": curated,  # already _safe_key'd by the bridge, or None
            "inferred_edges": len(inferred_edges),
            "weakest_trust_tier": weakest_trust_tier,
            "caveat": br.COOCCURRENCE_CAVEAT,
        })
    return records


def navigator_layer(records) -> dict:
    """An ATT&CK Navigator layer (v4.5) over the coverage records.

    HONEST FRAMING. Each technique entry carries its status + weakest_trust_tier
    in metadata. A NOT-in-corpus technique (in_corpus False, e.g. T1530) is
    enabled:false with NO score / color — only the honest comment + metadata.
    No technique entry ever carries a numeric `score` key (a fabricated number
    would read as a coverage claim); status drives any color, via a fixed legend.
    """
    techniques = []
    for rec in records:
        status = rec["status"]
        tier = rec["weakest_trust_tier"]
        comment = (
            f"{status} · weakest_trust_tier={tier} · " + rec["caveat"]
        )
        metadata = [
            {"name": "status", "value": status},
            {"name": "weakest_trust_tier", "value": str(tier)},
            {"name": "intent_blind", "value": "true"},
            {"name": "in_corpus", "value": str(rec["in_corpus"]).lower()},
            {"name": "required_ocsf_classes",
             "value": ",".join(str(c) for c in rec["required_classes"]) or "—"},
            {"name": "landed_ocsf_classes",
             "value": ",".join(str(c) for c in rec["landed_classes"]) or "—"},
        ]
        entry = {
            "techniqueID": rec["technique"],  # sub-technique dotted IDs pass through as-is
            "enabled": bool(rec["in_corpus"]),
            "comment": comment,
            "metadata": metadata,
        }
        # Color ONLY for in-corpus techniques and ONLY off the status enum — never
        # a fabricated score. Not-in-corpus stays enabled:false with no color.
        if rec["in_corpus"]:
            entry["color"] = _STATUS_COLOR.get(status, "")
        techniques.append(entry)

    return {
        "name": "MOAR design-time defensive structure",
        "versions": {"layer": "4.5", "navigator": "4.x", "attack": ATTACK_VERSION},
        "domain": "enterprise-attack",
        "description": (
            "DESIGN-TIME defensive STRUCTURE over a shared-artifact corpus — "
            "intent-blind, NOT coverage of your telemetry. status ∈ "
            "{fired, covered, dark_spot, blind}; every D3FEND edge is "
            "artifact_cooccurrence trust 0.25 unless a separate 0.70 curated "
            "detect-defense exists; the weakest_trust_tier is the scg weakest-link "
            "MIN over every claim. Not-in-corpus techniques are enabled:false with "
            "no fabricated score."
        ),
        "techniques": techniques,
        "gradient": {"colors": ["#ffffff", "#999999"], "minValue": 0, "maxValue": 1},
        "legendItems": _STATUS_LEGEND,
    }


def summarize(records) -> dict:
    """Pure-aggregate status tally + in_corpus / zero_defense counts. No labels."""
    out = {"fired": 0, "covered": 0, "dark_spot": 0, "blind": 0, "total": 0,
           "in_corpus": 0, "zero_defense": 0}
    for rec in records:
        out[rec["status"]] = out.get(rec["status"], 0) + 1
        out["total"] += 1
        if rec["in_corpus"]:
            out["in_corpus"] += 1
        if rec["is_zero_defense"]:
            out["zero_defense"] += 1
    return out


def recommend(record, corpus=None, *, ingest_code="ingest"):
    """For a DARK_SPOT CoverageRecord, the design-time "land this source" recommendation.

    FIRING RULE (intent-honest): recommend() fires ONLY for a dark_spot — a hunt
    exists (has_detection) but its OCSF class never landed (visible False), so the
    class is the gap to close. It returns None for blind / fired / covered; the
    firing rule IS the filter (status from assess()).

    WHAT IT BUILDS, all from already-aggregate inputs (invents nothing):
      - the detect-band D3FEND leads RE-DERIVED via br.defenses_for(technique,
        "detect") — assess() stores only the COUNT (:177), not the edge labels, so
        recommend re-derives them. The reason-only honest-degrade sentinels
        (not-in-corpus / zero-defense) are filtered exactly as assess does (:144).
        Each surviving lead is STAMPED intent-blind: proxy_quality
        "artifact_cooccurrence", trust 0.25, intent_blind True, and the literal
        stamp "artifact_cooccurrence — intent-blind possibility". trust /
        proxy_quality come verbatim from defenses_for (:239-240), never recomputed.
      - the OCSF classes to land = required_classes minus landed_classes. For a
        dark_spot landed_classes is [] (nothing landed), so it's the full required
        set. Cross-checked against the real edges' required_ocsf_classes and
        asserted a subset of the closed {1007,3002,4001,6003}.
      - a topology "land this source" target per class: the route NODE id
        `route_{ingest_code}` (topology.py:150) — NOT a named customer source
        (topology has no named-source model, topology.py:9,142). The action copy
        says "wire an ingest router", never claims a source exists.

    Honest degrade: a dark_spot whose technique is not-in-corpus / zero-defense
    yields defenses=[] with a degrade note carrying the sentinel reason — never a
    fabricated defense. Pure (no marimo); reuses br + the record fields.
    """
    if record.get("status") != "dark_spot":
        return None  # NEVER fires for blind / fired / covered

    corpus = corpus if corpus is not None else br.load_corpus()
    technique = record["technique"]

    # Re-derive the detect-band leads (assess kept only the count, not the labels).
    edges = br.defenses_for(technique, band="detect", corpus=corpus)
    leads = [e for e in edges if "reason" not in e]  # drop the honest-degrade sentinels (as :144)

    # OCSF classes to land = required minus landed (landed is [] for a dark_spot).
    landed = list(record.get("landed_classes") or [])
    required = list(record.get("required_classes") or [])
    classes_to_land = sorted(c for c in required if c not in landed)
    # Cross-check: every class is real and matches the edges' own derivation.
    edge_classes = sorted({cu for e in leads for cu in br.required_ocsf_classes(e)})
    assert all(cu in br._OCSF_ALLOWED for cu in classes_to_land), "fabricated class_uid"
    assert all(cu in br._OCSF_ALLOWED for cu in edge_classes), "fabricated class_uid (edge)"

    # Stamp every defense intent-blind. trust/proxy_quality verbatim from the edge.
    defenses = [{
        "d3fend_id": e["d3fend_id"],
        "def_tech": e["def_tech"],
        "phase": e["phase"],
        "shared_artifact_names": e["shared_artifact_names"],
        "proxy_quality": "artifact_cooccurrence",
        "trust": 0.25,
        "intent_blind": True,
        "stamp": "artifact_cooccurrence — intent-blind possibility",
    } for e in leads]

    # Topology "land this source" target per class: the route node id route_{code}.
    topology_targets = [{
        "class_uid": cu,
        "route_target": f"route_{ingest_code}",
        "action": (f"land OCSF class {cu} — wire an ingest router "
                   f"(route_{ingest_code}) so this class arrives"),
    } for cu in classes_to_land]

    out = {
        "technique": technique,
        "tactic": record.get("tactic", "—"),
        "class_uid": record.get("class_uid"),
        "classes_to_land": classes_to_land,
        "defenses": defenses,
        "topology_targets": topology_targets,
        "weakest_trust_tier": record.get("weakest_trust_tier"),
        "caveat": record.get("caveat", br.COOCCURRENCE_CAVEAT),
    }
    if not leads:
        # Honest "no detect-band lead": carry the sentinel reason, never a fake defense.
        out["degrade"] = edges[0]["reason"] if edges else "no detect-band lead"
    return out


def recommendation_panel(mo, ui, records, *, paid=False, partner=False, operator_data=False,
                         selection=None, source_note=""):
    """The "land-this-source" recommendation table — one row per dark spot.

    PUBLIC / PARTNER / PAID BOUNDARY. The DEFAULT (paid False, partner False) renders
    the GENERIC method on SYNTHETIC data only — "here is how you'd find what to land"
    over the synthetic stack's route codes / class_uids, every D3FEND defense stamped
    intent-blind at trust 0.25 — byte-for-byte what it rendered before partner mode
    existed. The PER-CUSTOMER recommender ("what YOUR stack should deploy") renders
    ONLY inside the `paid` or `partner` branch: paid mirrors the Matrix gate
    (control_plane.py:1051/:1081, unchanged); partner is the independent
    MOAR_PARTNER_MODE enablement gate (partner_mode.py) that unlocks the SAME
    workflow but NEVER any scored-Matrix content. `operator_data` says the records
    were assessed over the operator's own Inspector-loaded table (partner_mode
    .operator_coverage_inputs) rather than the synthetic preview, so the copy is
    honest about which data the dark spots came from. The firing rule (dark_spot
    only) and the intent-blind stamp hold in ALL modes; only the per-environment
    binding is gated.

    Every surfaced label is already _safe_key'd upstream (assess + defenses_for).
    """
    # In the paid/partner branch we MAY bind the route target to the live selection's
    # actual ingest code; in the default branch the route code stays generic.
    per_env = paid or partner
    ingest = (selection or {}).get("ingest") if isinstance(selection, dict) else None
    sel_codes = [c for c in (ingest or []) if c]
    ingest_code = sel_codes[0] if (per_env and sel_codes) else "ingest"

    recs = [r for r in (recommend(rec, ingest_code=ingest_code) for rec in records) if r]

    header = ui.header(
        mo, "Land-this-source recommendations — design-time possibilities (intent-blind)")
    if per_env and operator_data:
        intro = mo.md(
            "This is the **per-customer recommender over the operator's own landed OCSF "
            "data** — dark spots below come from YOUR table's per-class counts, not the "
            "synthetic preview. Every D3FEND defense below is an intent-blind "
            "`artifact_cooccurrence` lead at trust **0.25** (counters≠detects), a "
            "design-time possibility, **NOT** a guarantee and **NOT** coverage of your "
            "telemetry. " + br.COOCCURRENCE_CAVEAT
        )
    else:
        intro = mo.md(
            "This is the **generic method on synthetic data** — *here is how you'd find what "
            "to land*. Every D3FEND defense below is an intent-blind `artifact_cooccurrence` "
            "lead at trust **0.25** (counters≠detects), a design-time possibility, **NOT** a "
            "guarantee and **NOT** coverage of your telemetry. " + br.COOCCURRENCE_CAVEAT
        )

    if not recs:
        return ui.panel(
            mo, header, intro,
            ui.note(mo, "info", "No dark spots",
                    "Every hunt's OCSF class has landed — nothing to recommend landing."),
            mo.md(source_note),
        )

    rows = []
    for r in recs:
        land_classes = ", ".join(str(c) for c in r["classes_to_land"]) or "—"
        land_via = ", ".join(sorted({t["route_target"] for t in r["topology_targets"]})) or "—"
        if r["defenses"]:
            leads = "<br/>".join(
                f"`{d['d3fend_id']}` {d['def_tech']} [{d['stamp']}]" for d in r["defenses"])
        else:
            leads = f"*honest degrade — {r.get('degrade', 'no detect-band lead')}*"
        rows.append(
            f"| `{r['technique']}` | {r['tactic']} | {r['class_uid']} "
            f"| {land_classes} | {land_via} | {leads} | {r['weakest_trust_tier']} |"
        )
    table = mo.md(
        "| Technique | Tactic | OCSF class (dark) | Land these OCSF classes "
        "| Land via (route) | D3FEND detect leads (intent-blind 0.25) | Weakest trust |\n"
        "|---|---|---|---|---|---|---|\n"
        + "\n".join(rows)
    )

    children = [header, intro, table]
    if not per_env:
        # DEFAULT / public surface: generic-on-synthetic only. NO per-customer content.
        children.append(ui.note(
            mo, "info", "Generic method (public)",
            "This shows HOW to find what to land on synthetic data. The per-environment "
            "recommender — the one that binds these targets to a specific ingest route — is "
            "consultant IP; run with MOAR_PAID_MODE=1."))
    elif paid:
        # GATED per-customer branch: targets bound to the live selection's route code.
        children.append(ui.note(
            mo, "warn", "Per-environment recommender (paid)",
            "Targets below are bound to your selected ingest route "
            f"(`route_{ingest_code}`) — what your stack should deploy to close each dark "
            "spot. Still intent-blind possibilities at trust 0.25, never guarantees."))
    else:
        # PARTNER branch (MOAR_PARTNER_MODE): the same recommender workflow under the
        # integrator-enablement agreement. NO scored-Matrix content renders here — the
        # scored Capability Matrix stays behind MOAR_PAID_MODE and is not part of this mode.
        children.append(ui.note(
            mo, "warn", "Per-environment recommender (partner)",
            "Enabled under a partner enablement agreement (MOAR_PARTNER_MODE). Targets below "
            f"are bound to your selected ingest route (`route_{ingest_code}`) — what your "
            "stack should deploy to close each dark spot. Still intent-blind possibilities "
            "at trust 0.25, never guarantees. The scored Capability Matrix is not part of "
            "partner mode."))
        if not operator_data:
            children.append(ui.note(
                mo, "info", "No operator table loaded",
                "Showing the workflow over the synthetic preview. Load your landed OCSF "
                "table in the Iceberg Metadata Inspector to run the dark-spot technique "
                "over your own data."))
    children.append(mo.md(source_note))
    return ui.panel(mo, *children)


def zero_defense_panel(mo, ui, *, source_note=""):
    """The 27 zero-defense techniques as a standing fair-broker WARN surface (PG-6).

    DESIGN-TIME STRUCTURE, NOT telemetry. These are the band=='zero_defense'
    sentinel rows in the vendored D3FEND corpus: techniques that ARE measured
    (in_corpus True) but for which NO D3FEND technique watches the artifacts they
    produce. The set is derived at render time from the corpus band column via
    br._zero_ids(br.load_corpus()) — there is no precomputed list constant — and
    is exactly 27 (asserted in prove). Each row is rendered as a warn-note whose
    body is the bridge's own zero-defense reason string verbatim; every id is
    routed through _safe_key before interpolation (the raw off_tech_id comes
    straight off the CSV). This is a WARNING surface — "artifacts exist but no
    D3FEND control watches them" — never coverage of your telemetry.
    """
    ids = sorted(br._zero_ids(br.load_corpus()))
    notes = [
        ui.note(mo, "warn", _safe_key(i),
                "Artifacts exist but no D3FEND control watches them")
        for i in ids
    ]
    intro = mo.md(
        f"**{len(ids)} measured techniques** carry digital artifacts that some "
        "telemetry could produce, yet **no D3FEND defensive technique watches "
        "those artifacts** — they are `band==zero_defense` sentinels in the "
        "vendored corpus. This is **design-time structure** (the artifacts exist "
        "in the standards, and no D3FEND technique joins to them), **not coverage "
        "of your telemetry** and not a claim that your stack is exposed. Each line "
        "below is the bridge's own fair-broker warning, verbatim."
    )
    return ui.panel(
        mo,
        ui.header(mo, "Zero-defense — measured techniques no D3FEND control watches"),
        intro,
        *notes,
        mo.md(source_note),
    )


def detection_defense_panel(mo, ui, records, *, source_note=""):
    """For each FIRED detection, the D3FEND defensive technique it instantiates,
    at the curated 0.70 ontology_curated tier — NEVER the inferred 0.25 (PG-6).

    Reads ONLY rec["curated_defense"] (the SEPARATE hand-authored, intent-AWARE
    detect-defense map, populated by assess() via br.curated_defense_for and
    already _safe_key'd). Only records that actually FIRED this run appear
    (rec["fired"] True, equivalently status=="fired", which is match_count>0 on the
    underlying scan finding) — a covered / dark_spot / blind technique never
    surfaces. The inferred artifact_cooccurrence 0.25 edges and the weakest-link
    MIN are deliberately NOT shown here; this panel is the 0.70 curated tier on its
    own terms. When a fired technique has no curated entry (the honest T1530 gap),
    the row says so rather than fabricate a defense.
    """
    fired = [r for r in records if r.get("fired")]

    header = ui.header(
        mo, "Detection → D3FEND defense — curated detect-defense (intent-aware, 0.70)")
    intro = mo.md(
        "Each row below maps a detection that **actually fired this run** to the one "
        "D3FEND DETECT-phase technique that genuinely detects it. This is the "
        "**hand-authored, intent-AWARE** detect-defense map at trust **0.70** "
        "`ontology_curated` — a **separate source** from the 0.25 intent-blind "
        "`artifact_cooccurrence` inferred matrix (counters≠detects), and the 0.25 "
        "edges are deliberately **not** shown here. Only detections that fired "
        "appear; a covered / dark-spot / blind technique never surfaces."
    )

    if not fired:
        return ui.panel(
            mo, header, intro,
            ui.note(mo, "info", "No detections fired",
                    "Nothing matched this run — there is no fired detection to map "
                    "to a curated D3FEND defense."),
            mo.md(source_note),
        )

    rows = []
    for rec in fired:
        cur = rec.get("curated_defense")
        if cur:
            defense = f"`{cur['d3fend_id']}` {cur['def_tech']}"
            trust = cur["trust"]          # the literal 0.70 from the curated dict
            tier = cur["proxy_quality"]   # "ontology_curated"
        else:
            defense = "— (no curated detect-defense; honest gap)"
            trust = "—"
            tier = "—"
        rows.append(
            f"| `{rec['technique']}` | {rec['title']} | {defense} | {trust} | {tier} |"
        )
    table = mo.md(
        "| Technique | Detection (fired) | D3FEND defense | Trust | Tier |\n"
        "|---|---|---|---|---|\n"
        + "\n".join(rows)
    )

    return ui.panel(
        mo,
        header,
        intro,
        table,
        ui.note(mo, "info", "Separate from the inferred matrix",
                "The trust here is the curated **0.70** `ontology_curated` tier read "
                "directly from the hand-authored map — never the inferred **0.25** "
                "`artifact_cooccurrence` edge, and never lifted by a weakest-link MIN."),
        mo.md(source_note),
    )


def coverage_panel(mo, ui, records, navigator_json, *, source_note=""):
    """The ATT&CK coverage status table + the Navigator download.

    A markdown pipe-table (mirrors hunt_library_panel — no pandas) where every
    cell value is already _safe_key'd. Status rendered with a per-state emoji,
    weakest-trust as the float, curated detect-defense def_tech (or "—"). The
    Navigator download button emits navigator_layer(...) as JSON.
    """
    summ = summarize(records)
    summary_line = mo.md(
        f"**{summ['total']} techniques** · "
        f"{_STATUS_EMOJI['fired']} {summ['fired']} fired · "
        f"{_STATUS_EMOJI['covered']} {summ['covered']} covered · "
        f"{_STATUS_EMOJI['dark_spot']} {summ['dark_spot']} dark spot · "
        f"{_STATUS_EMOJI['blind']} {summ['blind']} blind &nbsp;·&nbsp; "
        f"{summ['in_corpus']} in the D3FEND corpus, {summ['zero_defense']} zero-defense."
    )

    rows = []
    for rec in records:
        cur = rec.get("curated_defense")
        cur_label = cur["def_tech"] if cur else "—"
        req = ", ".join(str(c) for c in rec["required_classes"]) or "—"
        landed = ", ".join(str(c) for c in rec["landed_classes"]) or "—"
        badge = f"{_STATUS_EMOJI.get(rec['status'], '')} {rec['status']}"
        rows.append(
            f"| `{rec['technique']}` | {rec['tactic']} | {rec['class_uid']} "
            f"| {badge} | {req} | {landed} | {'yes' if rec['in_corpus'] else 'no'} "
            f"| {rec['weakest_trust_tier']} | {cur_label} |"
        )
    table = mo.md(
        "| Technique | Tactic | OCSF class | Status | Required | Landed | In corpus | Weakest trust | Curated detect |\n"
        "|---|---|---|---|---|---|---|---|---|\n"
        + "\n".join(rows)
    )

    download_btn = mo.download(
        data=json.dumps(navigator_json, indent=2).encode("utf-8"),
        filename="moar-coverage.layer.json",
        mimetype="application/json",
        label="Download ATT&CK Navigator layer (v4.5)",
    )

    return ui.panel(
        mo,
        ui.header(mo, "ATT&CK coverage — design-time defensive structure (intent-blind)"),
        mo.md(
            "This is DESIGN-TIME STRUCTURE over a shared-artifact corpus, **not coverage "
            "of your telemetry**. A technique's status is "
            f"{_STATUS_EMOJI['fired']} **fired** (a hunt matched this run), "
            f"{_STATUS_EMOJI['covered']} **covered** (its OCSF class landed and a hunt "
            "watches it, but nothing matched), "
            f"{_STATUS_EMOJI['dark_spot']} **dark_spot** (a hunt exists but its OCSF class "
            "never landed — blind to it), or "
            f"{_STATUS_EMOJI['blind']} **blind** (no hunt at all). Every D3FEND edge is an "
            "intent-blind `artifact_cooccurrence` lead at trust **0.25** (counters≠detects) "
            "unless a separate hand-authored 0.70 `ontology_curated` detect-defense exists; "
            "the weakest-trust column is the scg weakest-link MIN over every claim, so a 0.25 "
            "edge is never upgraded by a co-present 0.70."
        ),
        summary_line,
        table,
        mo.hstack([download_btn]),
        mo.md(source_note),
    )


# ============================================================================
# PG-7 / CF-ART — the MEASURED-FIRING overlay.
#
# The Wall (PG-4 assess) maps where defenses are MAPPED; the lab's ocsf-attack-
# coverage bench (C5) measures where detections actually FIRE. This overlay joins
# the two on technique id and surfaces the DISAGREEMENT — the whole point.
#
# ISOLATION (CF-ART): this reads ONLY the vendored AGGREGATE verdicts (technique
# id + DETECTED/MISSED/NOISY + counts + precision + a public Sigma filename), NEVER
# a raw event. The console computes NO coverage number of its own — every measured
# value comes from the vendored file the generator copied from coverage.json.
#
# FAIL-CLOSED (mirrors decay.py): a technique NOT present in the measured set is
# `not_measured` — the analog of decay's `stale` ("no measured verdict exists,
# re-run the bench"), NEVER a bluffed measured-pass and NEVER a green. The same
# rule applies to the whole import: a stale coverage.json (older than the TTL)
# decays every measured verdict to not_measured rather than serve an old firing as
# current.
# ============================================================================

# Path to the vendored C5 verdicts (emitted by project1/tools/gen_c5_overlay.py).
_VERDICTS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "c5_coverage_verdicts.json")

# The C5 verdicts are a STATIC, reproducible LAB ARTIFACT — the generator copies them
# from the bench's coverage.json, and they only change when the bench is RE-RUN (a
# cadence of weeks), not minute-to-minute like live telemetry. So the import gets an
# artifact-scale TTL rather than decay.DEFAULT_TTL_SECONDS (one day, which is right for
# a live data-health verdict but wrong for a vendored bench result — at one day the
# whole measured overlay decayed to not_measured a single day after each bench run).
# The fail-closed contract is unchanged: an undatable, future-skewed, or genuinely
# past-cadence stamp still decays every verdict to not_measured.
C5_ARTIFACT_TTL_SECONDS = 30 * 86400  # 30 days — roughly one bench re-run cadence

# The measured-state -> emoji legend (kept separate from the design-time _STATUS_EMOJI).
_MEASURED_EMOJI = {"DETECTED": "🟢", "MISSED": "🔴", "NOISY": "🟠", "not_measured": "⚪"}

# Reconciliation legend — the green/red/amber/grey the disagreement panel renders.
_RECONCILIATION_EMOJI = {
    "confirmed_fired": "🟢",            # design-time covered AND measured DETECTED — prediction held
    "predicted_covered_but_missed": "🔴",  # the exposed gap — the Wall watched it, nothing fired
    "fired_but_noisy": "🟠",           # fired but with false positives (precision shown)
    "not_measured": "⚪",              # honest-degrade — no measured verdict, re-run the bench
    "measured_only": "🟡",             # the bench measured it but no design-time hunt watches it
}

# The aggregate-safe field allow-list for a reconciled record's measured side — a
# reconciled record may carry ONLY these measured fields (asserted in prove). No
# raw-event field can appear.
MEASURED_FIELD_ALLOWLIST = (
    "att_ck", "state", "ocsf_class_uid", "rule", "compiled",
    "matches", "true_positive", "false_positives", "precision",
    "threshold_T", "stage", "miss_reason",
)


def _norm_tech(technique):
    """Normalize a technique id for the join. assess() stores _safe_key'd ids and the
    vendored verdicts are _safe_key'd too, so both sides match on the plain ATT&CK id
    (sub-technique dotted ids like T1003.001 are preserved — no truncation)."""
    return str(technique or "").strip()


def load_measured_verdicts(path=None):
    """Load the vendored C5 verdicts -> (meta, {technique_id: verdict}).

    Mirrors br.load_corpus(): pure-stdlib json, reads the AGGREGATE verdicts the
    generator copied from coverage.json. The console holds NO raw events — this file
    carries only {technique id, state, counts, precision, Sigma filename, class_uid}.
    Returns the _meta provenance dict and a dict keyed by technique id.
    """
    p = path or _VERDICTS_PATH
    with open(p) as f:
        doc = json.load(f)
    meta = doc.get("_meta", {})
    measured = {}
    for v in doc.get("verdicts", []):
        tech = _norm_tech(v.get("att_ck"))
        if tech:
            measured[tech] = v
    return meta, measured


def _import_is_stale(meta, now_iso=None, ttl_seconds=C5_ARTIFACT_TTL_SECONDS):
    """Mirror decay's staleness onto the C5 import: the vendored _meta carries the
    bench run's timestamp; if that is undatable, future-skewed, or older than the TTL,
    the WHOLE measured overlay decays to "re-run the bench" rather than serve an old
    firing as current. Reuses decay.effective_status on a synthetic 'pass'."""
    now_iso = now_iso or _dt.datetime.now(_dt.timezone.utc).isoformat()
    stamp = (meta or {}).get("bench_validated_at")
    # effective_status decays a `pass` to `stale` exactly when the stamp is missing,
    # future-skewed, or older than the TTL — the same fail-closed contract.
    return decay.effective_status("pass", stamp, now_iso, ttl_seconds) != "pass"


def reconcile(records, measured, meta=None, *, now_iso=None, ttl_seconds=C5_ARTIFACT_TTL_SECONDS):
    """JOIN each design-time CoverageRecord (from assess) to the measured C5 verdict.

    For each record, key on technique id. Produce a reconciled record carrying BOTH
    the design-time status (fired/covered/dark_spot/blind) AND the measured verdict,
    plus a `reconciliation` label:

      confirmed_fired              design-time covered/fired AND measured DETECTED
                                   (the prediction held — a real measured firing)
      predicted_covered_but_missed design-time covered/fired AND measured MISSED
                                   (the honest disagreement — the Wall said a hunt
                                    watches it, the bench says nothing fired; RED)
      fired_but_noisy              design-time covered/fired AND measured NOISY
                                   (fired with false positives; precision shown)
      not_measured                 technique NOT in the measured set (FAIL-CLOSED —
                                   the decay `stale` analog; NEVER a bluffed pass)

    STALENESS: if the import is stale (meta.bench_validated_at older than the TTL,
    undatable, or future-skewed), EVERY verdict decays to not_measured — an old
    firing is never served as current (mirrors decay.effective_status).

    NO number is invented — the measured side comes only from the vendored verdict.
    The design-time record's weakest_trust_tier is carried THROUGH untouched: the
    measured join never upgrades an intent-blind 0.25 D3FEND edge.
    """
    measured = measured or {}
    import_stale = _import_is_stale(meta, now_iso=now_iso, ttl_seconds=ttl_seconds)

    out = []
    for rec in records:
        tech = _norm_tech(rec.get("technique"))
        design_status = rec.get("status")
        verdict = None if import_stale else measured.get(tech)

        if verdict is None:
            # FAIL-CLOSED: no measured verdict (absent technique, or stale import).
            reconciliation = "not_measured"
            measured_state = "not_measured"
            measured_fields = {}
        else:
            measured_state = _safe_key(verdict.get("state", ""))
            # Project ONLY the aggregate-safe measured fields onto the reconciled record.
            measured_fields = {k: verdict.get(k) for k in MEASURED_FIELD_ALLOWLIST}
            if measured_state == "DETECTED":
                reconciliation = "confirmed_fired"
            elif measured_state == "MISSED":
                reconciliation = "predicted_covered_but_missed"
            elif measured_state == "NOISY":
                reconciliation = "fired_but_noisy"
            else:
                # An unrecognized state honest-degrades rather than bluff a pass.
                reconciliation = "not_measured"
                measured_state = "not_measured"
                measured_fields = {}

        out.append({
            "technique": _safe_key(tech),
            "tactic": rec.get("tactic", "—"),
            "title": rec.get("title", ""),
            "class_uid": rec.get("class_uid"),
            "design_status": design_status,        # fired/covered/dark_spot/blind
            "measured_state": measured_state,       # DETECTED/MISSED/NOISY/not_measured
            "reconciliation": reconciliation,
            "precision": measured_fields.get("precision"),
            "true_positive": measured_fields.get("true_positive"),
            "false_positives": measured_fields.get("false_positives"),
            "matches": measured_fields.get("matches"),
            "rule": measured_fields.get("rule", ""),
            "measured_ocsf_class_uid": measured_fields.get("ocsf_class_uid"),
            "threshold_T": measured_fields.get("threshold_T"),
            # weakest_trust_tier carried THROUGH from the design-time record, untouched —
            # the measured join NEVER upgrades a 0.25 intent-blind D3FEND edge.
            "weakest_trust_tier": rec.get("weakest_trust_tier"),
            "import_stale": import_stale,
            "caveat": rec.get("caveat", br.COOCCURRENCE_CAVEAT),
        })
    return out


def reconcile_summarize(reconciled):
    """Pure-aggregate tally of the reconciliation buckets. No labels — counts only."""
    out = {k: 0 for k in _RECONCILIATION_EMOJI}
    out["total"] = 0
    for r in reconciled:
        out[r["reconciliation"]] = out.get(r["reconciliation"], 0) + 1
        out["total"] += 1
    return out


def gap_countermeasures(reconciled_record, corpus=None):
    """For a MEASURED-FN reconciled record, the design-time detect-band D3FEND leads.

    FIRING RULE (measured-honest): fires ONLY when reconciliation ==
    'predicted_covered_but_missed' — the honest disagreement where the Wall said a
    hunt watches the technique but the bench measured a miss. Returns None for every
    other bucket (confirmed_fired / fired_but_noisy / not_measured); the firing rule
    IS the filter, exactly as recommend() gates on dark_spot.

    WHAT IT BUILDS, all re-derived from the corpus (invents nothing):
      - the detect-band D3FEND leads via br.defenses_for(technique, "detect"), the
        reason-only honest-degrade sentinels filtered as recommend does (:296). Each
        surviving lead is STAMPED intent-blind: proxy_quality "artifact_cooccurrence",
        trust 0.25, intent_blind True, the literal "artifact_cooccurrence —
        intent-blind possibility" stamp — trust/proxy_quality verbatim from the edge,
        never recomputed. These are design-time LEADS for the measured miss, NOT
        coverage of the operator's telemetry.
      - ocsf_classes_to_land = the union of br.required_ocsf_classes over the leads,
        asserted a subset of the closed {1007,3002,4001,6003}.
      - weakest_trust_tier carried THROUGH from the reconciled record untouched — the
        measured-FN join never upgrades the 0.25 intent-blind edge (reconcile :795-797).

    Honest degrade: a measured-FN technique that is not-in-corpus / zero-defense
    yields countermeasures=[] with a degrade note carrying the sentinel reason —
    never a fabricated defense. Counts + technique/countermeasure IDs ONLY; NO ratio
    and no detected/total framed as environment coverage. Pure (no marimo).
    """
    if reconciled_record.get("reconciliation") != "predicted_covered_but_missed":
        return None  # NEVER fires for confirmed_fired / fired_but_noisy / not_measured

    corpus = corpus if corpus is not None else br.load_corpus()
    technique = reconciled_record["technique"]

    edges = br.defenses_for(technique, band="detect", corpus=corpus)
    leads = [e for e in edges if "reason" not in e]  # drop honest-degrade sentinels (as recommend :296)

    classes = sorted({cu for e in leads for cu in br.required_ocsf_classes(e)})
    assert all(cu in br._OCSF_ALLOWED for cu in classes), "fabricated class_uid"

    countermeasures = [{
        "d3fend_id": e["d3fend_id"],
        "def_tech": e["def_tech"],
        "phase": e["phase"],
        "shared_artifact_names": e["shared_artifact_names"],
        "proxy_quality": "artifact_cooccurrence",
        "trust": 0.25,
        "intent_blind": True,
        "stamp": "artifact_cooccurrence — intent-blind possibility",
    } for e in leads]

    out = {
        "technique": technique,
        "tactic": reconciled_record.get("tactic", "—"),
        "measured_state": reconciled_record.get("measured_state"),
        "reconciliation": reconciled_record.get("reconciliation"),
        "countermeasures": countermeasures,
        "countermeasure_count": len(countermeasures),
        "ocsf_classes_to_land": classes,
        "weakest_trust_tier": reconciled_record.get("weakest_trust_tier"),
        "caveat": reconciled_record.get("caveat", br.COOCCURRENCE_CAVEAT),
    }
    if not leads:
        # Honest "no detect-band lead": carry the sentinel reason, never a fake defense.
        out["degrade"] = edges[0]["reason"] if edges else "no detect-band lead"
    return out


def gap_countermeasures_summarize(reconciled):
    """Pure-aggregate headline for the measured-FN countermeasure panel. Counts only."""
    out = {"measured_fn": 0, "with_lead": 0, "honest_degrade": 0}
    for r in reconciled:
        g = gap_countermeasures(r)
        if g is None:
            continue
        out["measured_fn"] += 1
        if g["countermeasure_count"] > 0:
            out["with_lead"] += 1
        else:
            out["honest_degrade"] += 1
    return out

