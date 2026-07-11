"""Schema drift — an incoming raw event's FIELD SET vs the deployed crosswalk baseline.

The Configuration tab shows the mapping the deployed router runs (`config_preview.CROSSWALK`): which
raw fields become which OCSF fields. A source's schema drifts — a vendor renames a field, drops one,
adds one — and the mapping silently stops populating an OCSF field, so a detection that keys on that
field goes quiet with no error anywhere. Layer 2 (stack reachable) can't see it; the round-trip proof
only checks the fields it knows about. This module makes the drift visible BEFORE it reaches a
detection: diff the incoming raw field-NAME set against the crosswalk's expected set, name the OCSF
fields left unpopulated, and cross-reference `detections.DETECTIONS` for the hunts that lose a
required field. It is the tenth data-health gate row.

Telemetry-injection rule (this module handles NAMES and COUNTS only, never a raw field VALUE): the
input is a set of field NAMES, and every name that reaches an output cell is routed through
`analyze._safe_key` (printable-ASCII only, backticks dropped, HTML-escaped, length-bounded), so a
hostile field name can't inject through the marimo `mo.md()` render. A field's value never enters at
all — diffing is over the header, not the payload.

No stack: the pure diff runs over a synthetic drifted-header fixture (labeled as such). The live arm
— the real router's produced field set vs the crosswalk — is recorded by `prove_schema_drift.py`'s
Part 3 with the moar stack up (arm `schema_drift`).
"""
from __future__ import annotations

import json
import os

from analyze import _safe_key
import config_preview as cpv
import detections as det

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def _expected_raw(source, crosswalk):
    """Ordered-unique raw field names the crosswalk expects for `source` (crosswalk order, for a
    stable display; a raw field may map to more than one OCSF field, so de-dup)."""
    seen, out = set(), []
    for rf, _of, _note in crosswalk[source]["fields"]:
        if rf not in seen:
            seen.add(rf)
            out.append(rf)
    return out


def _producers(source, crosswalk):
    """OCSF field -> the set of raw fields that populate it. A field can have more than one producer
    (CloudTrail `eventName` -> class_uid AND activity_id), so an OCSF field is only left unpopulated
    when EVERY one of its producing raw fields goes missing."""
    prod = {}
    for rf, of, _note in crosswalk[source]["fields"]:
        prod.setdefault(of, set()).add(rf)
    return prod


def _required_ocsf_fields(d):
    """The OCSF fields a detection depends on: its where-clause fields (minus the class/category
    selectors, which the router sets, not a crosswalk raw field), its group keys, and the fields its
    measures aggregate. This is what a drift can take out from under a hunt."""
    fields = set()
    for f, _op, _v in d.get("where", []):
        if f not in ("class_uid", "category_uid"):
            fields.add(f)
    for g in d.get("group", ()):
        fields.add(g)
    for _name, (_agg, field) in d.get("measures", {}).items():
        if field:
            fields.add(field)
    return fields


def diff_fields(incoming_raw_fields, source, *, crosswalk=None):
    """Diff an incoming raw FIELD-NAME set vs the crosswalk baseline for `source`.

    incoming_raw_fields: an iterable of raw field NAMES observed on the incoming event (NAMES only —
    pass field names, never values). Returns a dict of names + counts (never a value):
      {source, class_uid, missing_raw, unexpected_raw, unpopulated_ocsf, detections_at_risk, status}.
    - missing_raw: expected raw fields absent from the incoming header.
    - unexpected_raw: incoming fields the crosswalk doesn't know — a rename shows up here (its old
      name in missing_raw, its new name here) alongside genuinely new fields; the two can't be told
      apart without a mapping, so this stays honestly "unexpected", not a fabricated rename pairing.
    - unpopulated_ocsf: OCSF fields whose every producing raw field is missing (the real damage).
    - detections_at_risk: hunts over this source's OCSF class that key on an unpopulated field.
    Unknown source or empty incoming -> honest 'unmeasured' degrade, never a raise and never a bluffed
    pass."""
    crosswalk = crosswalk if crosswalk is not None else cpv.CROSSWALK
    if source not in crosswalk:
        return {"source": _safe_key(source), "error": "unknown source", "status": "unmeasured",
                "missing_raw": [], "unexpected_raw": [], "unpopulated_ocsf": [], "detections_at_risk": []}
    class_uid = crosswalk[source]["class_uid"]
    incoming = {str(f) for f in (incoming_raw_fields or [])}
    if not incoming:
        return {"source": _safe_key(source), "class_uid": class_uid, "status": "unmeasured",
                "missing_raw": [], "unexpected_raw": [], "unpopulated_ocsf": [], "detections_at_risk": [],
                "note": "no incoming fields — nothing to diff (unmeasured, never a bluffed pass)"}

    expected = _expected_raw(source, crosswalk)
    expected_set = set(expected)
    missing = [rf for rf in expected if rf not in incoming]
    unexpected = sorted(f for f in incoming if f not in expected_set)
    missing_set = set(missing)

    producers = _producers(source, crosswalk)
    unpopulated = sorted(of for of, prods in producers.items() if prods and prods <= missing_set)
    unpop_set = set(unpopulated)

    at_risk = []
    for d in det.DETECTIONS:
        if det._class_of(d) != class_uid:
            continue  # a source's drift only touches detections over that source's OCSF class
        lost = _required_ocsf_fields(d) & unpop_set
        if lost:
            at_risk.append({"id": d["id"], "technique": d["technique"], "lost_fields": sorted(lost)})

    # Detection-scoped verdict: the gate certifies DETECTION health, so a drift fails the gate only
    # when a hunt actually loses a field it keys on. An OCSF field left unpopulated that no current
    # hunt uses (e.g. packets_out) is real information — it's reported in unpopulated_ocsf for
    # visibility — but it breaks nothing the stack certifies, so it stays a pass rather than an alarm.
    st = "fail" if at_risk else "pass"
    # _safe_key every NAME that renders. missing/unpopulated come from the code-defined crosswalk (already
    # clean, _safe_key is idempotent on them); unexpected comes from the untrusted incoming header, so this
    # is the boundary that neutralizes a hostile field name before mo.md() ever sees it.
    return {
        "source": _safe_key(source), "class_uid": class_uid,
        "missing_raw": [_safe_key(x) for x in missing],
        "unexpected_raw": [_safe_key(x) for x in unexpected],
        "unpopulated_ocsf": [_safe_key(x) for x in unpopulated],
        "detections_at_risk": [
            {"id": _safe_key(a["id"]), "technique": _safe_key(a["technique"]),
             "lost_fields": [_safe_key(x) for x in a["lost_fields"]]}
            for a in at_risk],
        "status": st,
    }


def status(diff):
    """The gate status for a diff: pass | fail | unmeasured. Mirrors the diff's own verdict so the
    gate row and the panel chip read the same thing (kept as a function to match the gate-row
    contract used by the other optional rows)."""
    return diff.get("status", "unmeasured")


def load_incoming_fixture(name, *, fixtures_dir=None):
    """Load a synthetic drifted-header fixture: {source, incoming_raw_fields:[names]}. Field NAMES
    only (telemetry-injection rule) — a fixture carrying values would be a test that leaks. Returns
    {} on any read/parse problem so the panel degrades to unmeasured rather than crashing."""
    fd = fixtures_dir or _FIXTURES
    try:
        with open(os.path.join(fd, name)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001 - honest degrade, never crash the tab
        return {}


def demo_diff(*, fixtures_dir=None):
    """The drift the panel demonstrates with no stack: the vendored drifted-Zeek header fixture diffed
    against the live crosswalk. Clearly synthetic; the live arm computes the real router field set."""
    fx = load_incoming_fixture("schema-drift-zeek-drifted.json", fixtures_dir=fixtures_dir)
    if not fx:
        return {"source": "zeek", "status": "unmeasured", "missing_raw": [], "unexpected_raw": [],
                "unpopulated_ocsf": [], "detections_at_risk": [], "note": "drift fixture unreadable"}
    return diff_fields(fx.get("incoming_raw_fields", []), fx.get("source", "zeek"))


# --- panel ------------------------------------------------------------------ #

def _icon(st):
    return {"pass": "🟢", "fail": "🔴", "unmeasured": "⚪"}.get(st, "⚪")


def schema_drift_panel(mo, ui, diff, *, source_note=""):
    """Render a schema-drift diff as a NAMES-only table (Missing raw · Renamed/new raw · Unpopulated
    OCSF · Detections at risk) plus a gate chip. Counts and field names only — no raw event value."""
    st = diff.get("status", "unmeasured")
    if diff.get("error"):
        return ui.panel(mo, ui.header(mo, "Schema drift — raw → OCSF field coverage"),
                        mo.md(f"*Drift check unavailable: {diff['error']} (unmeasured).*"))
    if st == "unmeasured":
        return ui.panel(mo, ui.header(mo, "Schema drift — raw → OCSF field coverage"),
                        mo.md(f"*{_icon(st)} Unmeasured — {diff.get('note', 'no incoming header to diff')}.*"))
    missing = diff.get("missing_raw", [])
    unexpected = diff.get("unexpected_raw", [])
    unpop = diff.get("unpopulated_ocsf", [])
    at_risk = diff.get("detections_at_risk", [])
    at_risk_cell = "<br/>".join(
        f"`{a['technique']}` {a['id']} — loses {', '.join('`' + lf + '`' for lf in a['lost_fields'])}"
        for a in at_risk) or "—"
    row = (f"| {', '.join('`' + m + '`' for m in missing) or '—'} "
           f"| {', '.join('`' + u + '`' for u in unexpected) or '—'} "
           f"| {', '.join('`' + p + '`' for p in unpop) or '—'} "
           f"| {at_risk_cell} |")
    table = ("| Missing raw | Renamed/new raw | Unpopulated OCSF | Detections at risk |\n"
             "|---|---|---|---|\n" + row)
    if st == "fail":
        chip_tail = f"{len(unpop)} OCSF field(s) unpopulated, {len(at_risk)} hunt(s) at risk"
    elif unpop:
        chip_tail = f"no hunt loses a field ({len(unpop)} unpopulated, unused by any hunt)"
    else:
        chip_tail = "incoming header covers every mapped field"
    chip = f"{_icon(st)} **Schema drift: {st.upper()}** — {chip_tail}"
    return ui.panel(
        mo, ui.header(mo, f"Schema drift — raw → OCSF field coverage · {diff.get('source', '')} "
                          f"(class {diff.get('class_uid', '—')})"),
        mo.md("Diff an incoming raw event's **field names** against the deployed crosswalk. A dropped "
              "or renamed raw field silently stops populating an OCSF field, and a hunt that keys on it "
              "goes quiet with no error — this row catches that before a detection does. "
              + source_note),
        mo.md(table),
        ui.note(mo, "warn" if st == "fail" else "info", "", chip),
        mo.md("*Field names and counts only — never a raw event value (real telemetry is a "
              "prompt-injection surface). Renders a synthetic drifted header unless the live router "
              "field set has been captured (Flow › Health).*"),
    )
