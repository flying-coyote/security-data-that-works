"""Detection-suite regression — the fire/silent verdict pattern shouldn't move under you.

A detection suite regresses silently: someone edits a rule, a mapping drifts, a corpus shifts, and a
hunt that used to fire goes quiet (or a quiet one starts firing) with nothing failing. This module
persists the per-rule VERDICT (FIRED / SILENT) and asserts a later run matches a committed baseline —
so a flip is a caught regression, not a surprise in an incident.

Two verdict sources, one shape ({id|rule, technique, verdict}):
  - verdicts_from_scan(): the PURE path over detections.DETECTIONS via detections.scan(demo_records) —
    fully unit-testable, no stack, the deterministic regression oracle for the declarative specs.
  - verdicts_from_run(stdout): parse the LIVE path — run_detections.py's per-rule stdout over the
    landed Iceberg table (SigmaHQ→SQL). stdout carries matches only, so a rule that fails to COMPILE
    prints matches=0 and reads SILENT — indistinguishable from a genuine no-match, which is the right
    conservative call: either way a FIRED→SILENT flip vs the baseline is a caught regression.

Telemetry-injection rule: a verdict is a LABEL (FIRED/SILENT) + an id/technique + a match COUNT —
never a raw event, a grouping key, or a matched value. This module handles labels and counts only.
"""
from __future__ import annotations

import json
import os
import re

import detections as det

_FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

FIRED, SILENT = "FIRED", "SILENT"

# a run_detections.py per-rule line: "  <title>  matches=<n>    [<tags>]" (run_detections.py L49).
_RUN_LINE = re.compile(r"^\s*(?P<title>.+?)\s+matches=(?P<n>\d+)\b")
_TAGS = re.compile(r"\[([^\]]*)\]")
_TECH = re.compile(r"attack\.t(\d+(?:\.\d+)?)", re.IGNORECASE)


def _key(v):
    """The stable identity of a verdict row across both sources: the declarative id, else the rule
    title (the run path has no id)."""
    return v.get("id") or v.get("rule")


def verdicts_from_scan(records=None):
    """Per-rule verdicts over the PURE detections path (no stack): FIRED when a spec produced any
    aggregate finding, SILENT otherwise. Deterministic over a fixed corpus — the regression oracle for
    the declarative DETECTIONS specs. Returns a list of {id, technique, verdict} sorted by id."""
    recs = det.demo_records() if records is None else records
    scan = det.scan(recs)
    out = [{"id": s["id"], "technique": s["technique"],
            "verdict": FIRED if s["match_count"] > 0 else SILENT} for s in scan]
    return sorted(out, key=lambda v: v["id"])


def verdicts_from_run(run_detections_output):
    """Parse run_detections.py's stdout into the same verdict shape. A line with matches>0 is FIRED;
    matches=0 (a genuine no-match OR a rule that failed to compile — stdout can't tell them apart, and
    conservatively shouldn't) is SILENT. The trailing summary line ("N/M Sigma rules fired ...") has no
    'matches=' token, so it's skipped. Returns {rule, technique, verdict, matches} sorted by rule."""
    out = []
    for line in (run_detections_output or "").splitlines():
        m = _RUN_LINE.match(line)
        if not m:
            continue
        title = m.group("title").strip()
        n = int(m.group("n"))
        tag_m = _TAGS.search(line)
        tech_m = _TECH.search(tag_m.group(1)) if tag_m else None
        technique = ("T" + tech_m.group(1).upper()) if tech_m else "—"
        out.append({"rule": title, "technique": technique,
                    "verdict": FIRED if n > 0 else SILENT, "matches": n})
    return sorted(out, key=lambda v: v["rule"])


def counts(verdicts):
    """FIRED/SILENT/total counts for a verdict list — the aggregate-safe headline."""
    fired = sum(1 for v in verdicts if v.get("verdict") == FIRED)
    return {"fired": fired, "silent": len(verdicts) - fired, "total": len(verdicts)}


def snapshot(verdicts, *, ran_at, corpus_fingerprint):
    """A persistable regression snapshot: the verdict labels + counts + provenance (never a raw event).
    corpus_fingerprint is a short caller-supplied provenance string ('demo_records (pure)' /
    'ocsf.network_activity @ 1000 rows') so a comparison across a moved corpus is legible, not silent."""
    return {"ran_at": ran_at, "corpus_fingerprint": corpus_fingerprint,
            "counts": counts(verdicts), "verdicts": verdicts}


def assert_equality(before, after):
    """Compare two verdict lists (from either source) and return {equal, changed, status}. A flip
    (FIRED↔SILENT), a rule that appears, or a rule that vanishes is a `changed` entry naming the rule
    and both verdicts. status: pass (identical verdict set) / fail (any change) / unmeasured (either
    side empty — nothing measured, never a bluffed pass). THIS is the regression assertion."""
    b = {_key(v): v.get("verdict") for v in (before or [])}
    a = {_key(v): v.get("verdict") for v in (after or [])}
    if not b or not a:
        return {"equal": False, "changed": [], "status": "unmeasured"}
    changed = []
    for k in sorted(set(b) | set(a)):
        if b.get(k) != a.get(k):
            changed.append({"rule": k, "before": b.get(k, "—absent—"), "after": a.get(k, "—absent—")})
    equal = not changed
    return {"equal": equal, "changed": changed, "status": "pass" if equal else "fail"}


def load_baseline(name="detection-verdicts-baseline.json", *, fixtures_dir=None):
    """Load a committed baseline snapshot; {} on any read/parse problem (honest degrade)."""
    fd = fixtures_dir or _FIXTURES
    try:
        with open(os.path.join(fd, name)) as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def load_run_fixture(name="run-detections-sample-stdout.txt", *, fixtures_dir=None):
    """Load the captured run_detections.py stdout (for the parser proof); '' on any read problem."""
    fd = fixtures_dir or _FIXTURES
    try:
        with open(os.path.join(fd, name)) as f:
            return f.read()
    except Exception:  # noqa: BLE001
        return ""


def demo_regression(*, fixtures_dir=None):
    """The regression the panel shows with no stack: fresh pure scan verdicts vs the committed baseline
    snapshot. Equal on a clean tree; a `changed` list the moment a DETECTIONS spec or the demo corpus
    moves. Unmeasured if the baseline is missing."""
    base = load_baseline(fixtures_dir=fixtures_dir)
    fresh = verdicts_from_scan()
    eq = assert_equality(base.get("verdicts", []), fresh)
    return {"equality": eq, "baseline": base, "current_counts": counts(fresh),
            "corpus_fingerprint": base.get("corpus_fingerprint", "—")}


# --- panel ------------------------------------------------------------------ #

def _icon(st):
    return {"pass": "🟢", "fail": "🔴", "unmeasured": "⚪"}.get(st, "⚪")


def regress_panel(mo, ui, demo, *, source_note=""):
    """Render the detection-suite regression verdict: baseline vs current, counts + any flips (rule
    name + before/after label only — never a raw event)."""
    eq = demo.get("equality", {})
    st = eq.get("status", "unmeasured")
    cur = demo.get("current_counts", {})
    if st == "unmeasured":
        return ui.panel(mo, ui.header(mo, "Detection-suite regression (CF-REGRESS)"),
                        mo.md("*⚪ Unmeasured — no committed baseline to compare against.*"))
    if eq.get("changed"):
        flips = "\n".join(f"| `{c['rule']}` | {c['before']} | {c['after']} |" for c in eq["changed"])
        body = ("**A verdict changed vs the committed baseline** — a regression:\n\n"
                "| Rule | Baseline | Current |\n|---|---|---|\n" + flips)
    else:
        body = (f"Every rule's verdict matches the committed baseline — no regression. "
                f"**{cur.get('fired', 0)} FIRED · {cur.get('silent', 0)} SILENT** "
                f"over {cur.get('total', 0)} rule(s).")
    chip = f"{_icon(st)} **Detection regression: {st.upper()}** — {'baseline holds' if st == 'pass' else 'a verdict flipped'}"
    return ui.panel(
        mo, ui.header(mo, "Detection-suite regression (CF-REGRESS)"),
        mo.md("Persist each hunt's **FIRED / SILENT** verdict over a fixed corpus and assert a later "
              "run matches the committed baseline — a rule edit, a mapping drift, or a corpus shift "
              "that silently flips a verdict is caught here, not in an incident. "
              + source_note),
        mo.md(body),
        ui.note(mo, "warn" if st == "fail" else "info", "", chip),
        mo.md("*Verdict labels + match counts only — never a raw event or a matched value. Pure "
              "verdicts over the demo corpus; the live suite runs via `./moar regress` over the landed "
              "Iceberg table.*"),
    )
