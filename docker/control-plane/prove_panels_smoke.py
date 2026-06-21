"""Headless smoke test for the new Startup-tab panels.

The marimo dataflow graph is validated separately via `marimo export script`, and the
engines have their own proofs. This executes the actual PANEL-CONSTRUCTION code paths the
cells run (mo.ui widgets + ui.panel/ui.note/ui.card with real engine outputs), which the
engine proofs don't touch — so a bad widget kwarg or a panel-build error surfaces here
rather than only at `marimo run`. Visual layout still needs a human `marimo run`; this
proves the cells execute without raising.

Run (needs marimo):  VENV/bin/python prove_panels_smoke.py    (exit 0 = all panels built)
"""
from __future__ import annotations

import sys

import marimo as mo

import ui_helpers as ui
import providers as P
import constraint_filter as cf
import anti_patterns as antip
import cost_advisor as ca
import reference_presets as rp
import config_preview as cpv
import detections as dets

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def attempt(label, fn):
    try:
        obj = fn()
        assert obj is not None
        print(f"  [{PASS}] {label}")
    except Exception as e:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        _failures.append(f"{label}: {e}")
        print(f"  [{FAIL}] {label}")


def build_constraints_input():
    def _dd(cat):
        return mo.ui.dropdown(options=cf.option_labels(cat), value=cf.default_label(cat),
                              label=cf.CONSTRAINTS[cat]["label"])
    con_compliance = mo.ui.multiselect(options=cf.option_labels("compliance"), value=[],
                                       label=cf.CONSTRAINTS["compliance"]["label"])
    return ui.panel(mo, ui.header(mo, "Constraints — declare these first"), mo.md("intro"),
                    mo.hstack([_dd("deployment"), _dd("team"), _dd("vendor")], gap=1, justify="start"),
                    mo.hstack([_dd("workload"), con_compliance, _dd("cost")], gap=1, justify="start"))


def build_verdict_panel():
    sel = {"deployment": "on_prem_airgap", "team": "t_3_5", "vendor": "open_first",
           "workload": "threat_hunting", "cost": "balanced", "compliance": ["immutable_audit"]}
    picked = {"storage": ["aws_s3"], "catalog": ["polaris"], "ingest": ["vector"],
              "query": ["clickhouse", "duckdb"], "schema": ["ocsf"]}
    report = cf.evaluate(sel, picked)
    funnel = cf.funnel(sel, {c: [p.code for p in g] for c, g in P.CATEGORIES.items()})
    fmd = "**Reachable after constraints:** " + " · ".join(
        f"{c} {f['reachable']}/{f['total']}" for c, f in funnel.items())
    labels = {p.code: p.label for g in P.CATEGORIES.values() for p in g}
    rows = [ui.note(mo, "warn" if r["verdict"] in ("disqualify", "caution") else "info",
                    f"{labels.get(r['code'], r['code'])} — {r['verdict'].upper()}", r["reason"])
            for r in report["picked_verdicts"]]
    return ui.panel(mo, ui.header(mo, "verdict"), mo.md(report["summary_md"]), mo.md(fmd),
                    *(rows or [mo.md("none")]))


def build_funnel_viz_panel():
    # The constraint funnel viz (T2). This renderer has an f-string format spec ({cat:<8}) that
    # a `marimo export script` graph-check does NOT execute — only running the panel catches a
    # bad spec (an HTML-over-escaped `&lt;8` shipped once and blanked the whole app). Smoke it
    # across both the constrained and the no-constraint (full-catalog) shapes.
    cats = {c: [p.code for p in g] for c, g in P.CATEGORIES.items()}
    labels = {p.code: p.label for g in P.CATEGORIES.values() for p in g}
    lf = lambda _c, code: labels.get(code, code)
    air = cf.funnel_viz({"deployment": "on_prem_airgap"}, cats)
    none = cf.funnel_viz({}, cats)
    return mo.vstack([cf.funnel_viz_panel(mo, ui, air, label_for=lf),
                      cf.funnel_viz_panel(mo, ui, none, label_for=lf)])


def build_config_preview_panel():
    # PB-1 Configuration raw->OCSF preview renderer — execute it for both sources (markdown table
    # + json blocks), the path a graph-check doesn't run.
    return mo.vstack([cpv.config_preview_panel(mo, ui, cpv.build_preview(s))
                      for s in ("zeek", "sysmon", "cloudtrail", "nope")])  # incl. nested-path + error path


def build_detections_panel():
    # PD-network detections renderer over the worked sample (beacon + exfil fire).
    return dets.detections_panel(mo, ui, dets.scan(dets.demo_records()), source_note="*sample*")


def build_presets_panel():
    cards = []
    for pr in rp.PRESETS:
        c = pr["components"]
        line = f"Storage {c['storage']} · Query {', '.join(c['query'])} · Schema {c['schema']}"
        cards.append(ui.card(mo, ui.header(mo, pr["name"]),
                             mo.md(f"{pr['when_it_wins']}\n\n{line}\n\n*{pr['cost_profile']}* `{pr['cite']}`")))
    return ui.panel(mo, ui.header(mo, "Reference architectures"), mo.md("intro"),
                    mo.hstack(cards, gap=2, justify="start", align="start"))


def build_anti_panel():
    flags = antip.detect({"storage": "aws_s3", "catalog": "aws_glue", "schema": "cef",
                          "ingest": [], "query": ["datafusion", "trino", "clickhouse", "starrocks"]})
    assert flags, "expected anti-pattern flags for this deliberately bad selection"
    return ui.panel(mo, ui.header(mo, "Design anti-patterns"),
                    *[ui.note(mo, lvl, t, b) for lvl, t, b in flags])


def build_cost_panel():
    tb = mo.ui.number(start=0.0, stop=1000.0, step=0.5, value=1.0, label="Raw ingest TB/day")
    days = mo.ui.dropdown(options=["30 days", "90 days", "1 year", "7 years"],
                          value="7 years", label="Retention window")
    est = ca.estimate(1.0, 2555)
    return ui.panel(mo, ui.header(mo, "Cost-to-serve"), mo.hstack([tb, days], gap=1, justify="start"),
                    mo.md(ca.summary_md(est)))


def main():
    print("\n=== panel construction smoke test ===\n")
    attempt("constraints_input", build_constraints_input)
    attempt("constraints_verdict_panel (+ funnel)", build_verdict_panel)
    attempt("funnel_viz_panel (T2 renderer — the f-string format-spec path)", build_funnel_viz_panel)
    attempt("config_preview_panel (PB-1 — zeek/sysmon/cloudtrail/error)", build_config_preview_panel)
    attempt("detections_panel (PD-network — beacon/exfil findings)", build_detections_panel)
    attempt("reference_presets_panel", build_presets_panel)
    attempt("anti_patterns_panel", build_anti_panel)
    attempt("cost_panel (+ widgets)", build_cost_panel)
    if _failures:
        print(f"\n\033[91m{len(_failures)} panel(s) failed to build:\033[0m " + "; ".join(_failures))
        return 1
    print("\n\033[92mAll new panels build headlessly — cells execute without raising.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
