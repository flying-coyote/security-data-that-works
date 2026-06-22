"""Proof for the CF-ART measured-firing overlay (PG-7): the console reads ONLY the vendored
AGGREGATE C5 verdicts (never a raw event), a technique absent from C5 honest-degrades to
not_measured (fail-closed), the measured number traces to the vendored verdicts (which
byte-match a fresh generator run — the staleness guard), a design-time/measured DISAGREEMENT
is surfaced (not papered over), a stale import decays the overlay, and a nasty payload comes
out inert through _safe_key.

THE INVARIANTS this asserts:
  a) NO RAW EVENTS    : the vendored verdicts file + every reconciled record carries ONLY
                        {technique id, state, counts, precision, Sigma rule, class_uid,
                        reconciliation, …} and never an event-row field (CF-ART guard 3) —
                        asserted against the measured-field allow-list.
  b) FAIL-CLOSED      : a technique NOT in the C5 set reconciles to not_measured, NEVER to
                        confirmed_fired / a measured-pass; no measured firing is claimed
                        (mirror decay: unmeasured stays unmeasured).
  c) NUMBER TRACES TO C5 : the headline detected/total equals coverage.json detected (3) /
                        techniques_total (8); the console computes NO coverage number of its
                        own — the value is read from the vendored _meta (which copied C5).
  d) STALENESS GUARD  : re-running gen_c5_overlay.py to a temp path byte-matches the checked-in
                        vendored file (excluding the _meta gen_date) — a stale/drifted file
                        FAILS; and the vendored ground_truth_fingerprint == coverage.json's, so
                        a re-run of a CHANGED bench is caught.
  e) DISAGREEMENT SURFACED : a design-time `covered` measured MISSED reconciles to
                        predicted_covered_but_missed and renders in the panel; a covered +
                        DETECTED upgrades to confirmed_fired.
  f) AGGREGATE-SAFE   : a control-char/backtick/<script> payload through the vendored-label
                        render path comes out inert (no raw '<', no backtick, '&lt;' present).
  g) STALENESS DECAY  : a vendored _meta bench_validated_at older than the TTL decays EVERY
                        measured verdict to not_measured (mirror decay.effective_status) — an
                        old firing is never served as current.
  h) TRUST PRESERVED  : the measured join never upgrades a 0.25 intent-blind D3FEND edge;
                        weakest_trust_tier on a reconciled record == the design-time record's.

Run:  /tmp/pyice-venv/bin/python prove_measured_overlay.py   (exit 0 = all invariants hold)
Pure stdlib; runs with cwd = this control-plane dir (imports the modules directly).
"""
from __future__ import annotations

import datetime as _dt
import importlib
import json
import os
import sys
import tempfile

import attack_coverage as acov
import ui_helpers as ui
from analyze import _safe_key

HERE = os.path.dirname(os.path.abspath(__file__))
VERDICTS = os.path.join(HERE, "c5_coverage_verdicts.json")
COVERAGE_JSON = os.path.normpath(
    os.path.join("/home/USER/sdw-lab-benchmarks", "ocsf-attack-coverage", "results", "coverage.json")
)
GENERATOR = os.path.normpath(os.path.join(HERE, "..", "..", "..", "project1", "tools", "gen_c5_overlay.py"))

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []

# Fields a reconciled record / vendored verdict may carry — anything else (especially an
# event-row marker) is a hard fail. The measured side is the allow-list; the design-time
# scaffolding fields are added here.
_RECORD_ALLOWLIST = set(acov.MEASURED_FIELD_ALLOWLIST) | {
    "technique", "tactic", "title", "class_uid", "design_status", "measured_state",
    "reconciliation", "precision", "true_positive", "false_positives", "matches", "rule",
    "measured_ocsf_class_uid", "threshold_T", "weakest_trust_tier", "import_stale", "caveat",
}
# Any key containing one of these markers would mean a raw event leaked in.
_EVENT_MARKERS = ("event", "raw", "row", "record", "payload", "message")


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def _strip_gen_date(path):
    """Return the JSON with the _meta gen_date normalized out, so byte-compare ignores the
    pinned date (and the bench_validated_at mtime, which moves if coverage.json is re-touched)."""
    doc = json.load(open(path))
    meta = doc.get("_meta", {})
    meta["gen_date"] = "<normalized>"
    meta["bench_validated_at"] = "<normalized>"
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


def _mk_record(technique, status, *, trust=0.25):
    """A minimal design-time CoverageRecord shaped like assess() output."""
    return {
        "technique": technique, "tactic": "—", "title": technique, "class_uid": 1007,
        "visible": True, "has_detection": True, "fired": status == "fired",
        "status": status, "in_corpus": True, "is_zero_defense": False,
        "required_classes": [], "landed_classes": [1007], "curated_defense": None,
        "inferred_edges": 1, "weakest_trust_tier": trust, "caveat": "x",
    }


def main():
    meta, measured = acov.load_measured_verdicts()
    c5 = json.load(open(COVERAGE_JSON))

    print("\n=== (a) NO RAW EVENTS: the vendored verdicts + reconciled records carry only aggregates ===\n")
    raw_doc = json.load(open(VERDICTS))
    bad_verdict_keys = []
    for v in raw_doc.get("verdicts", []):
        for k in v.keys():
            if k not in acov.MEASURED_FIELD_ALLOWLIST:
                bad_verdict_keys.append(k)
            if any(m in str(k).lower() for m in _EVENT_MARKERS):
                bad_verdict_keys.append(("event-marker", k))
    check(f"every vendored verdict carries ONLY the measured allow-list "
          f"({len(raw_doc.get('verdicts', []))} verdicts, {len(bad_verdict_keys)} stray keys)",
          not bad_verdict_keys)
    # scg_lead must NOT have been vendored (PG-3 derives the D3FEND side itself).
    check("scg_lead was NOT vendored (the console derives D3FEND edges itself)",
          all("scg_lead" not in v for v in raw_doc.get("verdicts", [])))
    # reconciled records:
    recs = acov.assess(__import__("detections").scan(__import__("detections").demo_records()),
                       {1007: 3, 3002: 1, 4001: 2, 4003: 1, 6003: 1})
    reconciled = acov.reconcile(recs, measured, meta)
    stray = set()
    for r in reconciled:
        stray |= (set(r.keys()) - _RECORD_ALLOWLIST)
        for k in r.keys():
            if any(m in str(k).lower() for m in _EVENT_MARKERS) and k not in _RECORD_ALLOWLIST:
                stray.add(("event-marker", k))
    check(f"every reconciled record carries ONLY allow-listed fields (stray: {sorted(stray)})", not stray)

    print("\n=== (b) FAIL-CLOSED: a technique NOT in C5 honest-degrades to not_measured ===\n")
    # T9999 is not in the bench — must reconcile not_measured, never a measured pass.
    absent = acov.reconcile([_mk_record("T9999", "covered")], measured, meta)[0]
    check("a not-in-C5 technique reconciles to not_measured", absent["reconciliation"] == "not_measured")
    check("not_measured claims NO measured firing (state == not_measured)",
          absent["measured_state"] == "not_measured")
    check("not_measured carries no precision / TP (no fabricated number)",
          absent["precision"] is None and absent["true_positive"] is None)
    check("not_measured is NEVER confirmed_fired",
          absent["reconciliation"] != "confirmed_fired")

    print("\n=== (c) NUMBER TRACES TO C5: headline detected/total == coverage.json's ===\n")
    check(f"vendored _meta detected == coverage.json detected (3): {meta.get('detected')}",
          meta.get("detected") == c5["detected"] == 3)
    check(f"vendored _meta techniques_total == coverage.json (8): {meta.get('techniques_total')}",
          meta.get("techniques_total") == c5["techniques_total"] == 8)
    # The console computes NO number of its own — reconcile copies the verdict state, never a count.
    detected_recon = acov.reconcile([_mk_record("T1059.001", "covered")], measured, meta)[0]
    check("reconcile reads DETECTED from the vendored verdict, computes no count",
          detected_recon["measured_state"] == "DETECTED"
          and detected_recon["reconciliation"] == "confirmed_fired")

    print("\n=== (d) STALENESS GUARD: a fresh generator run byte-matches the checked-in file ===\n")
    with tempfile.TemporaryDirectory() as td:
        tmp_out = os.path.join(td, "c5_coverage_verdicts.json")
        sys.path.insert(0, os.path.dirname(GENERATOR))
        gen = importlib.import_module("gen_c5_overlay")
        importlib.reload(gen)
        gen.OUT = tmp_out
        rc = gen.main()
        check("generator re-run exits 0", rc == 0)
        fresh = _strip_gen_date(tmp_out)
        checked_in = _strip_gen_date(VERDICTS)
        check("regenerated verdicts byte-match the checked-in vendored file (gen_date excluded)",
              fresh == checked_in)
    check("vendored ground_truth_fingerprint == coverage.json's (a changed bench is caught)",
          meta.get("ground_truth_fingerprint") == c5["corpus"]["ground_truth_fingerprint"])

    print("\n=== (e) DISAGREEMENT SURFACED: covered+MISSED -> predicted_covered_but_missed ===\n")
    # T1110 is measured MISSED in C5; a design-time `covered` over it is the honest disagreement.
    miss = acov.reconcile([_mk_record("T1110", "covered")], measured, meta)[0]
    check("design-time covered + measured MISSED -> predicted_covered_but_missed (the exposed gap)",
          miss["reconciliation"] == "predicted_covered_but_missed")
    # and it renders in the panel as a RED row (mock mo/ui collect the markdown).
    rendered = _render_panel([miss], meta)
    check("the disagreement renders in the panel (predicted-covered-but-missed row present)",
          "predicted covered, MISSED" in rendered and "T1110" in rendered)
    # the upgrade direction: T1059.001 is DETECTED -> confirmed_fired.
    up = acov.reconcile([_mk_record("T1059.001", "covered")], measured, meta)[0]
    check("design-time covered + measured DETECTED -> confirmed_fired (the upgrade)",
          up["reconciliation"] == "confirmed_fired")
    # noisy: T1021 is NOISY -> fired_but_noisy with precision shown.
    noisy = acov.reconcile([_mk_record("T1021", "covered")], measured, meta)[0]
    check("design-time covered + measured NOISY -> fired_but_noisy with precision",
          noisy["reconciliation"] == "fired_but_noisy" and noisy["precision"] is not None)

    print("\n=== (f) AGGREGATE-SAFE: a nasty payload through the render path comes out inert ===\n")
    payload = "T1071\n\x00`</code><img src=x onerror=alert(1)>"
    safe = _safe_key(payload)
    check("control chars stripped (\\n, \\x00)", "\n" not in safe and "\x00" not in safe)
    check("markdown code-span backtick stripped", "`" not in safe)
    check("no raw '<' / live <img reaches the render", "<img" not in safe and "<" not in safe)
    check("payload rendered inert (&lt; present where '<' was)", "&lt;" in safe)
    # through the real reconcile + panel path (every label _safe_key'd on the way out):
    nasty_measured = {"T1071": {"att_ck": "T1071", "state": payload, "rule": payload,
                                "precision": 0.0, "ocsf_class_uid": 4003, "threshold_T": 0.9,
                                "matches": 0, "true_positive": 0, "false_positives": 0,
                                "compiled": None, "stage": payload, "miss_reason": ""}}
    nrec = acov.reconcile([_mk_record("T1071", "covered")], nasty_measured, meta)[0]
    rendered_nasty = _render_panel([nrec], meta)
    check("nasty state/rule rendered inert through reconcile+panel (no raw '<', no backtick)",
          "<img" not in rendered_nasty and "`</code>" not in rendered_nasty)

    print("\n=== (g) STALENESS DECAY: an old bench_validated_at decays every verdict to not_measured ===\n")
    old_meta = dict(meta)
    old_meta["bench_validated_at"] = "2000-01-01T00:00:00+00:00"  # far past the TTL
    decayed = acov.reconcile([_mk_record("T1059.001", "covered")], measured, old_meta)
    check("a stale import decays a DETECTED technique to not_measured (never an old firing as current)",
          decayed[0]["reconciliation"] == "not_measured" and decayed[0]["import_stale"] is True)
    # an undatable stamp also decays.
    nodate_meta = dict(meta)
    nodate_meta["bench_validated_at"] = None
    nd = acov.reconcile([_mk_record("T1059.001", "covered")], measured, nodate_meta)
    check("an undatable bench stamp decays to not_measured (fail-closed)",
          nd[0]["reconciliation"] == "not_measured")
    # a future-skewed stamp decays too.
    future_meta = dict(meta)
    future_meta["bench_validated_at"] = (
        _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(hours=2)).isoformat()
    fu = acov.reconcile([_mk_record("T1059.001", "covered")], measured, future_meta)
    check("a future-skewed bench stamp decays to not_measured", fu[0]["reconciliation"] == "not_measured")

    print("\n=== (h) TRUST PRESERVED: the measured join never upgrades a 0.25 intent-blind edge ===\n")
    rec_025 = _mk_record("T1059.001", "covered", trust=0.25)  # DETECTED in C5
    joined = acov.reconcile([rec_025], measured, meta)[0]
    check("weakest_trust_tier on the reconciled record == the design-time 0.25 (unchanged)",
          joined["weakest_trust_tier"] == 0.25)
    check("even a confirmed_fired upgrade keeps the intent-blind trust at 0.25",
          joined["reconciliation"] == "confirmed_fired" and joined["weakest_trust_tier"] == 0.25)

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mMeasured-firing overlay: aggregate-only (no raw events), fail-closed not_measured, "
          "number traces to C5, fresh vendored file, disagreement surfaced, staleness decays, "
          "intent-blind trust preserved — all invariants hold.\033[0m")
    return 0


# --- a tiny headless mo/ui shim so the panel can be rendered to a string in the proof ---
class _MD:
    def __init__(self, text):
        self.text = text
    def style(self, *_a, **_k):
        return self


class _MoShim:
    def md(self, text):
        return _MD(text)
    def vstack(self, children, *a, **k):
        return _MD("\n".join(getattr(c, "text", str(c)) for c in children))
    def hstack(self, children, *a, **k):
        return _MD("\n".join(getattr(c, "text", str(c)) for c in children))
    def Html(self, text):
        return _MD(text)


def _render_panel(reconciled, meta):
    mo = _MoShim()
    out = ui.disagreement_panel(mo, ui, reconciled, meta, source_note="*src*")
    return getattr(out, "text", str(out))


if __name__ == "__main__":
    sys.exit(main())
