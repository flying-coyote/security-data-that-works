"""Proof for the PARTNER-MODE gate (KIT-4) — MOAR_PARTNER_MODE is an independent third
mode that unlocks the per-customer recommender WORKFLOW (dark-spot technique ->
detect-band D3FEND leads -> OCSF classes to land -> land-this-source route binding)
over the operator's own data, and NOTHING else: never the scored Matrix, never a
change to the public surface, never a relaxation of the telemetry-injection boundary.

THE INVARIANTS this asserts (the KIT-4 proof battery):
  a) PUBLIC UNCHANGED          : with both keys off, the default panel is byte-identical
                                 to a call that never mentions partner kwargs, and renders
                                 the public surface (generic note + services-engagement
                                 framing, no run-MOAR_PAID_MODE=1 hint). (The rest of proof
                                 (a) is the existing battery staying green — run it.)
  b) PARTNER-OFF HIDES ALL     : partner_mode() is False with the key unset/falsy, and is
                                 NEVER implied by MOAR_PAID_MODE — not by paid off, not by
                                 paid on. No partner surface renders when the flag is off.
  c) PARTNER-ON = WORKFLOW ONLY: partner_mode() truthy-token parsing matches the house
                                 gate; the partner panel renders the per-environment
                                 recommender (route bound to the live selection) and the
                                 partner banner, but NO scored-Matrix content — no paid
                                 banner, no weighted totals/deltas — and the paid gate
                                 stays cold: paid_mode() False, consultant_mode() False,
                                 load_scores() == {} while partner mode is on.
  d) INJECTION GUARDS HOLD     : operator_coverage_inputs() returns ONLY aggregates
                                 (match counts, _safe_key'd group keys, {class_uid: count});
                                 a poisoned operator row (control char + backtick +
                                 <script> + a free-text secret) never reaches the findings,
                                 the by_class keys, or the rendered partner panel.

Run:  /tmp/pyice-venv/bin/python prove_partner_mode.py   (exit 0 = all hold)
Needs pyarrow/duckdb (part d builds a real Arrow table); runs with cwd = this
control-plane dir (imports the modules directly).
"""
from __future__ import annotations

import os
import sys

import attack_coverage as acov
import d3fend_bridge as br
import paid_scoring as paid
import partner_mode as pm

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def _env(**kv):
    """Set/clear the mode keys for one assertion block (None = unset)."""
    for k, v in kv.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


# ---- minimal marimo stub so recommendation_panel renders to text (prove_recommendation pattern) ----
class _MoStub:
    class _Node:
        def __init__(self, text=""):
            self._text = text

        def style(self, *_a, **_k):
            return self

        def __str__(self):
            return self._text

    def md(self, text):
        return self._Node(str(text))

    def Html(self, text):
        return self._Node(str(text))

    def vstack(self, children):
        return self._Node("\n".join(str(c) for c in children))

    def hstack(self, children):
        return self._Node("\n".join(str(c) for c in children))


def _all_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _all_strings(k)
            yield from _all_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _all_strings(v)


def main():
    import ui_helpers as ui
    mo = _MoStub()
    corpus = br.load_corpus()
    # A dark-spot fixture: T1071's class 4001 never landed -> the recommender fires.
    records = acov.assess([{"technique": "T1071", "match_count": 0}], {}, corpus)
    sel = {"ingest": ["vector"]}

    print("\n=== (b) INDEPENDENCE: MOAR_PARTNER_MODE is its own key — never implied by paid ===\n")
    _env(MOAR_PARTNER_MODE=None, MOAR_PAID_MODE=None)
    check("both keys unset -> partner_mode() False", pm.partner_mode() is False)
    _env(MOAR_PAID_MODE="0")
    check("MOAR_PAID_MODE=0 (explicitly off) does NOT imply partner mode", pm.partner_mode() is False)
    _env(MOAR_PAID_MODE="1")
    check("MOAR_PAID_MODE=1 (paid on) does NOT imply partner mode either", pm.partner_mode() is False)
    _env(MOAR_PAID_MODE=None)
    for tok in ("1", "true", "YES", " on "):
        _env(MOAR_PARTNER_MODE=tok)
        check(f"MOAR_PARTNER_MODE={tok!r} -> True (house truthy set)", pm.partner_mode() is True)
    for tok in ("0", "false", "", "off-ish-garbage"):
        _env(MOAR_PARTNER_MODE=tok)
        check(f"MOAR_PARTNER_MODE={tok!r} -> False", pm.partner_mode() is False)
    import ast
    _tree = ast.parse(open(pm.__file__, encoding="utf-8").read())
    _imports = {a.name for n in ast.walk(_tree) if isinstance(n, ast.Import) for a in n.names} \
        | {n.module for n in ast.walk(_tree) if isinstance(n, ast.ImportFrom) and n.module}
    check("partner_mode.py never imports paid_scoring (no code path can touch the paid gate)",
          "paid_scoring" not in _imports)

    print("\n=== (a) PUBLIC UNCHANGED: both keys off -> byte-identical default panel ===\n")
    _env(MOAR_PARTNER_MODE=None, MOAR_PAID_MODE=None)
    legacy = str(acov.recommendation_panel(mo, ui, records, paid=False, selection=sel))
    explicit = str(acov.recommendation_panel(mo, ui, records, paid=False, partner=False,
                                             operator_data=False, selection=sel))
    check("default call == explicit partner=False call, byte-for-byte", legacy == explicit)
    check("public surface renders the generic-method note", "Generic method (public)" in legacy)
    check("public surface frames per-environment binding as the services engagement",
          "services engagement" in legacy)
    check("public surface renders NO partner surface at all",
          "partner" not in legacy.lower() and "MOAR_PARTNER_MODE" not in legacy)
    check("public surface renders NO per-environment recommender",
          "Per-environment recommender" not in legacy)
    check("public surface does NOT bind the live selection's route (route_vector)",
          "route_vector" not in legacy)

    print("\n=== (c) PARTNER-ON: recommender workflow exposed, scored Matrix stays cold ===\n")
    _env(MOAR_PARTNER_MODE="1", MOAR_PAID_MODE="off")  # explicit-off: paid default is now on
    check("partner on: paid_mode() stays False (partner never unlocks paid)",
          paid.paid_mode() is False)
    check("partner on: consultant_mode() stays False for a public clone",
          paid.consultant_mode(vault_readable=False, has_notes=False) is False)
    check("partner on: load_scores() == {} (zero scored-Matrix content loadable)",
          paid.load_scores() == {})
    ptext = str(acov.recommendation_panel(mo, ui, records, paid=paid.paid_mode(),
                                          partner=pm.partner_mode(), selection=sel))
    check("partner panel renders the partner banner",
          "Per-environment recommender (partner)" in ptext)
    check("partner panel names its own gate key (MOAR_PARTNER_MODE)", "MOAR_PARTNER_MODE" in ptext)
    check("partner panel binds the route target to the live selection (route_vector)",
          "route_vector" in ptext)
    check("partner panel renders the honest no-operator-table note when data is synthetic",
          "No operator table loaded" in ptext)
    check("partner panel does NOT render the paid banner",
          "Per-environment recommender (paid)" not in ptext)
    check("partner panel carries no weighted totals / claim-vs-shipped deltas",
          "weighted" not in ptext.lower() and "delta" not in ptext.lower())
    check("partner panel keeps the intent-blind stamp (0.25, artifact_cooccurrence)",
          "0.25" in ptext and "artifact_cooccurrence" in ptext)
    _env(MOAR_PARTNER_MODE=None)

    print("\n=== (d) INJECTION GUARDS HOLD: operator data feed is aggregates only ===\n")
    import pyarrow as pa
    secret = "RAW-ROW-SECRET-cc0ffee"
    nasty = "6.6.6.6\x07INJECT`</span><script>alert(1)</script>"
    rows = [
        {"class_uid": 4001, "activity_id": 1, "src_ip": nasty, "message": secret,
         "dst_port": 443, "bytes_out": 10},
        {"class_uid": 4001, "activity_id": 1, "src_ip": "10.0.0.7", "message": secret,
         "dst_port": 443, "bytes_out": 20},
        {"class_uid": 4001, "activity_id": 2, "src_ip": "10.0.0.8", "message": secret,
         "dst_port": 53, "bytes_out": 30},
    ]
    tbl = pa.Table.from_pylist(rows)
    findings, by_class = pm.operator_coverage_inputs(tbl)
    check("by_class is the aggregate {class_uid: count} view (4001 -> 3)",
          {int(k): v for k, v in by_class.items() if k != "<null>"} == {4001: 3})
    fstrings = list(_all_strings(findings))
    check("no finding string carries the free-text secret (raw rows never leave scan())",
          all(secret not in s for s in fstrings))
    check("no finding string carries a raw '<script' or control char",
          all("<script" not in s and "\x07" not in s for s in fstrings))
    check("no finding string carries a markdown backtick from telemetry",
          all("`" not in s for s in fstrings))
    check("by_class keys are class_uid values only, never row content",
          all(secret not in s and "<script" not in s for s in _all_strings(by_class)))
    # OCSF-shaped guard: a table without class_uid must be refused, not faked into dark spots.
    try:
        pm.operator_coverage_inputs(pa.Table.from_pylist([{"message": secret}]))
        refused = False
    except ValueError:
        refused = True
    check("a table without class_uid is refused (ValueError -> honest synthetic fallback)", refused)
    # End-to-end: assess over the poisoned operator inputs, render the partner panel.
    _env(MOAR_PARTNER_MODE="1", MOAR_PAID_MODE="off")  # explicit-off: paid default is now on
    op_records = acov.assess(findings, by_class, corpus)
    op_text = str(acov.recommendation_panel(mo, ui, op_records, paid=paid.paid_mode(),
                                            partner=pm.partner_mode(), operator_data=True,
                                            selection=sel))
    check("partner panel over operator data says so (per-customer over operator's own data)",
          "operator's own landed OCSF data" in op_text)
    check("operator-data panel drops the no-operator-table note", "No operator table loaded" not in op_text)
    check("rendered partner panel never carries the free-text secret", secret not in op_text)
    check("rendered partner panel never carries a raw '<script' or control char",
          "<script" not in op_text and "\x07" not in op_text)
    _env(MOAR_PARTNER_MODE=None, MOAR_PAID_MODE=None)

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mPARTNER MODE: key independent of paid (off and on), public surface "
          "byte-identical with both keys off, partner-on exposes the recommender workflow "
          "with zero scored-Matrix content, and the operator-data feed stays aggregates-only "
          "under a poisoned row — all hold.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
