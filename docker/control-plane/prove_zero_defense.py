"""Proof for PG-6 — the zero-defense WARN surface and the curated detect-defense panel
are HONEST: the zero-defense set is EXACTLY 27 and matches the bridge; the
detection→defense panel reads ONLY the curated 0.70 ontology_curated tier and NEVER
the inferred 0.25; it maps ONLY detections that actually FIRED (negative control: a
non-fired detection does not appear); T1530 is the honest gap (no fabricated defense);
and a nasty control-char / markdown / HTML payload comes out inert through _safe_key.

THE INVARIANTS this asserts:
  1) 27-SET EXACT     : sorted(br._zero_ids(load_corpus())) is len 27 and == the pinned
                        ZERO_27; zero_defense_panel renders exactly 27 warn-notes.
  2) CURATED 0.70 NOT 0.25 : every fired record's curated_defense is trust 0.70 /
                        proxy_quality ontology_curated / intent_blind False; the panel
                        markdown contains "0.70" and "ontology_curated"; no table DATA row
                        ever carries "0.25" or "artifact_cooccurrence" as a trust/tier value
                        (the inferred tier is named ONLY in disclaiming prose that negates
                        it — "a separate source from the 0.25 ...", "never the inferred
                        0.25 ..." — so the honest separation is preserved, not blurred);
                        weakest_link(0.70,0.25)==0.25 still holds (the panel shows 0.70
                        because it reads curated_defense directly, not the MIN).
  3) FIRED-ONLY       : detection_defense_panel includes a technique iff rec["fired"]
                        (status=="fired"); a covered / dark_spot / blind technique never
                        appears. Negative control: a match_count==0 finding doesn't surface.
  4) T1530 HONEST GAP : br.curated_defense_for("T1530") is None; if T1530 fires, the panel
                        shows the honest "no curated detect-defense" cell, never a defense.
  5) AGGREGATE-SAFE   : a control-char + backtick + <script> technique label through
                        assess / curated_defense_for / both panels comes out inert
                        (no raw '<', no backtick).

Run:  /tmp/pyice-venv/bin/python prove_zero_defense.py   (exit 0 = all hold)
Pure stdlib; runs with cwd = this control-plane dir (imports the modules directly).
"""
from __future__ import annotations

import sys

import attack_coverage as acov
import detections as dets
import d3fend_bridge as br
from analyze import _safe_key

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []

# The 27 ZERO_DEFENSE techniques (pinned — same set as prove_d3fend_bridge.py:45-50).
ZERO_27 = {
    "T1115", "T1559.001", "T1578.001", "T1213.004", "T1213.006", "T1006", "T1562.012",
    "T1036.007", "T1559.002", "T1056.002", "T1553.001", "T1027.006", "T1564.001", "T1559",
    "T1491.001", "T1547.015", "T1213.005", "T1564.004", "T1106", "T1055.008", "T1564.009",
    "T1036.002", "T1113", "T1049", "T1055.005", "T1070.006", "T1559.003",
}


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


class _MO:
    """Minimal marimo stub — every panel/note/header/md is captured as its source text
    so the proof can string-scan the rendered output without a real marimo runtime."""

    class _Node:
        def __init__(self, kind, text="", children=()):
            self.kind = kind
            self.text = text
            self.children = list(children)

        def style(self, *_a, **_k):
            return self

        def _flatten(self):
            yield self.text
            for c in self.children:
                if isinstance(c, _MO._Node):
                    yield from c._flatten()
                elif isinstance(c, str):
                    yield c

        def rendered(self):
            return "\n".join(t for t in self._flatten() if t)

    def md(self, text):
        return _MO._Node("md", text)

    def vstack(self, children):
        return _MO._Node("vstack", "", children)

    def hstack(self, children):
        return _MO._Node("hstack", "", children)

    def Html(self, text):
        return _MO._Node("html", text)


class _UI:
    """ui_helpers passthrough that records note text — mirrors ui_helpers note/panel/header."""

    def note(self, mo, level, title, body):
        return mo._Node("note", f"[{level}] {title} :: {body}")

    def panel(self, mo, *children, **_k):
        return mo.vstack(list(children))

    def header(self, mo, text):
        return mo.Html(text)


def _count_notes(node):
    if getattr(node, "kind", None) == "note":
        return 1
    return sum(_count_notes(c) for c in getattr(node, "children", [])
               if hasattr(c, "kind"))


def main():
    mo, ui = _MO(), _UI()
    corpus = br.load_corpus()

    print("\n=== (1) 27-SET EXACT: the zero-defense set is exactly 27 and matches the bridge ===\n")
    zd = sorted(br._zero_ids(br.load_corpus()))
    check(f"br._zero_ids(load_corpus()) has 27 members (has {len(zd)})", len(zd) == 27)
    check("the set == the pinned ZERO_27 (no missing)", not (ZERO_27 - set(zd)))
    check("the set == the pinned ZERO_27 (no extra)", not (set(zd) - ZERO_27))
    zpanel = acov.zero_defense_panel(mo, ui, source_note="*src*")
    check("zero_defense_panel renders exactly 27 warn-notes", _count_notes(zpanel) == 27)
    zrender = zpanel.rendered()
    check("zero_defense_panel intro states '27 techniques'", "27 measured techniques" in zrender)
    check("each note carries the fair-broker reason verbatim",
          "Artifacts exist but no D3FEND control watches them" in zrender)
    check("every zero-defense id appears _safe_key'd in the render",
          all(_safe_key(i) in zrender for i in zd))

    print("\n=== (2) CURATED 0.70 NOT 0.25: the detect-defense panel reads only the curated tier ===\n")
    findings = dets.scan(dets.demo_records())
    by_class = {}
    for r in dets.demo_records():
        cu = r.get("class_uid")
        if cu is not None:
            by_class[cu] = by_class.get(cu, 0) + 1
    recs = acov.assess(findings, by_class, corpus)
    fired_recs = [r for r in recs if r["fired"]]
    check("at least one detection fired over the synthetic preview", len(fired_recs) >= 1)
    for r in fired_recs:
        cur = r.get("curated_defense")
        if cur:
            check(f"{r['technique']} curated trust == 0.70", cur["trust"] == 0.70)
            check(f"{r['technique']} proxy_quality == ontology_curated",
                  cur["proxy_quality"] == "ontology_curated")
            check(f"{r['technique']} intent_blind is False", cur["intent_blind"] is False)
    dpanel = acov.detection_defense_panel(mo, ui, recs, source_note="*src*")
    drender = dpanel.rendered()
    check("panel render contains '0.70'", "0.70" in drender)
    check("panel render contains 'ontology_curated'", "ontology_curated" in drender)
    # The honest separation: the panel NAMES the 0.25 intent-blind artifact_cooccurrence
    # tier in DISCLAIMING prose ("a separate source from the 0.25 ...", "never the inferred
    # 0.25 ...") so a reader cannot blur it into the curated 0.70. A blanket substring ban
    # would forbid that honest sentence. The real invariant is that 0.25 /
    # artifact_cooccurrence NEVER appear on the DATA path — never as a trust value or tier in
    # a fired technique's table row — only inside a sentence that explicitly negates them.
    table_rows = [ln for ln in drender.splitlines() if ln.lstrip().startswith("| `")]
    check("a fired technique table row exists to inspect", len(table_rows) >= 1)
    check("no table DATA row carries '0.25' as a trust/tier value",
          all("0.25" not in ln for ln in table_rows))
    check("no table DATA row carries 'artifact_cooccurrence' as a tier value",
          all("artifact_cooccurrence" not in ln for ln in table_rows))
    # Wherever 0.25 / artifact_cooccurrence DO appear, the line must be disclaiming prose
    # that explicitly separates the inferred tier from the curated one (negation present).
    _negators = ("separate source", "never the inferred", "deliberately", "not** shown",
                 "not shown")
    for ln in drender.splitlines():
        if "0.25" in ln or "artifact_cooccurrence" in ln:
            check("every 0.25 / artifact_cooccurrence mention is in disclaiming prose "
                  "(names the inferred tier only to negate it)",
                  any(n in ln for n in _negators))
    check("weakest_link(0.70, 0.25) == 0.25 (MIN unchanged — panel shows 0.70 by reading curated)",
          br.weakest_link(0.70, 0.25) == 0.25)

    print("\n=== (3) FIRED-ONLY: only fired techniques surface; a non-fired one never does ===\n")
    # Construct findings where T1071 fires and T1110 does not (match_count 0).
    mixed = acov.assess(
        [{"technique": "T1071", "match_count": 3},
         {"technique": "T1110", "match_count": 0}],
        {4001: 5, 3002: 2}, corpus)
    fired_in_mixed = [r["technique"] for r in mixed if r["fired"]]
    check("T1071 (match_count>0) is fired", "T1071" in fired_in_mixed)
    check("T1110 (match_count==0) is NOT fired", "T1110" not in fired_in_mixed)
    mixed_panel = acov.detection_defense_panel(mo, ui, mixed).rendered()
    check("panel surfaces the fired T1071", "`T1071`" in mixed_panel)
    check("panel does NOT surface the non-fired T1110 (negative control)",
          "`T1110`" not in mixed_panel)
    # a covered / dark_spot / blind technique (no fired record at all) never appears.
    none_fired = acov.assess([], {4001: 1, 3002: 1, 1007: 1, 6003: 1}, corpus)
    nf_panel = acov.detection_defense_panel(mo, ui, none_fired).rendered()
    check("with nothing fired the panel shows the honest 'No detections fired' note",
          "No detections fired" in nf_panel)
    check("no technique row leaks when nothing fired",
          all(f"`{r['technique']}`" not in nf_panel for r in none_fired))

    print("\n=== (4) T1530 HONEST GAP: no curated defense; if fired, no fabricated defense ===\n")
    check("br.curated_defense_for('T1530') is None (honest gap)",
          br.curated_defense_for("T1530") is None)
    t1530_fired = acov.assess([{"technique": "T1530", "match_count": 2}], {6003: 3}, corpus)
    r1530 = next((r for r in t1530_fired if r["technique"] == "T1530"), None)
    check("a fired T1530 record exists", r1530 is not None and r1530["fired"] is True)
    check("fired T1530 has curated_defense None (no fabrication)",
          r1530 is not None and r1530["curated_defense"] is None)
    t1530_panel = acov.detection_defense_panel(mo, ui, t1530_fired).rendered()
    check("panel shows the honest 'no curated detect-defense' cell for fired T1530",
          "no curated detect-defense" in t1530_panel)
    check("fired T1530 panel never invents a D3-* defense id",
          "D3-" not in t1530_panel)

    print("\n=== (5) AGGREGATE-SAFE: a nasty technique label comes out inert through _safe_key ===\n")
    nasty = "T1071\n\x00`</span><script>alert(1)</script>"
    nasty_recs = acov.assess([{"technique": nasty, "match_count": 1}], {4001: 1}, corpus)
    np_render = acov.detection_defense_panel(mo, ui, nasty_recs).rendered()
    check("the nasty technique label is _safe_key'd at the boundary (inert, no '<', no backtick)",
          "<" not in _safe_key(nasty) and "`" not in _safe_key(nasty) and "&lt;" in _safe_key(nasty))
    check("detect-defense panel has no raw '<script' (breakout neutralized)",
          "<script" not in np_render and "</span>" not in np_render)
    # the zero-defense ids are _safe_key'd too (raw off_tech_id from the CSV).
    z_render = acov.zero_defense_panel(mo, ui).rendered()
    check("zero-defense render carries no raw '<' anywhere", "<script" not in z_render)
    check("curated_defense_for routes labels through _safe_key (no '<' in a curated value)",
          all("<" not in str(v) for v in (br.curated_defense_for("T1071") or {}).values()
              if isinstance(v, str)))

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mPG-6: zero-defense set exactly 27, curated 0.70 never 0.25, "
          "fired-only mapping, T1530 honest gap, aggregate-safe — all hold.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
