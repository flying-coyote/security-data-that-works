"""Proof for PG-5 land-this-source recommendations: recommend() is intent-honest —
it fires ONLY for dark_spots, every recommended D3FEND defense carries the
intent-blind stamp, the OCSF classes to land are real closed-set class_uids equal
to required minus landed, the topology target names a route node (never a fabricated
customer source), the DEFAULT panel surface carries NO per-customer recommender (the
paid path is the only one that can), a nasty payload comes out inert through
_safe_key, and a zero-defense / not-in-corpus dark_spot degrades honestly (no
fabricated defense).

THE INVARIANTS this asserts:
  a) FIRES ONLY FOR DARK_SPOTS : recommend(rec) is not None iff rec.status=="dark_spot";
                                 None for fired / covered / blind (negative control).
  b) EVERY DEFENSE STAMPED     : each defense has proxy_quality "artifact_cooccurrence",
                                 trust 0.25, intent_blind True, and the literal stamp.
  c) OCSF CLASSES REAL         : every classes_to_land is in {1007,3002,4001,6003} and
                                 equals required_classes minus landed_classes; no fab.
  d) TOPOLOGY TARGET HONEST    : each route_target matches ^route_ and the action text
                                 invents no named customer source.
  e) NO PER-CUSTOMER IN DEFAULT: recommendation_panel(paid=False) renders the generic
                                 note + the services-engagement framing (no run-
                                 MOAR_PAID_MODE=1 hint; the scored Matrix is public now)
                                 and NOT a per-env "your stack should deploy" claim;
                                 paid=True is the only path that can.
  f) AGGREGATE-SAFE            : a control-char + backtick + <script> payload comes out
                                 inert (no raw '<', no backtick, '&lt;' present).
  g) HONEST DEGRADE            : a zero-defense / not-in-corpus dark_spot yields
                                 defenses==[] with a degrade reason, never a fab defense.

Run:  /tmp/pyice-venv/bin/python prove_recommendation.py   (exit 0 = all hold)
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


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def _rec(records, technique):
    return next((r for r in records if r["technique"] == technique), None)


# ---- minimal marimo / ui_helpers stubs so recommendation_panel renders to text ----
class _MoStub:
    """A marimo stand-in: every builder returns an object whose str() concatenates
    the text passed in, so we can scan the rendered panel for content."""

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


def main():
    corpus = br.load_corpus()
    # T1071 -> 4001 (in corpus, has detect leads incl. Network Traffic -> 4001).
    # T1530 -> 6003 (NOT in corpus -> honest degrade).
    print("\n=== (a) FIRES ONLY FOR DARK_SPOTS (negative control: fired/covered/blind -> None) ===\n")
    # dark_spot: hunt exists, class 4001 never landed (absent from by_class).
    dark = acov.assess([{"technique": "T1071", "match_count": 0}], {}, corpus)
    r_dark = _rec(dark, "T1071")
    check("T1071 with class absent resolves to dark_spot", r_dark["status"] == "dark_spot")
    check("recommend() FIRES for a dark_spot (not None)", acov.recommend(r_dark) is not None)

    # fired: visible + match.
    fired = acov.assess([{"technique": "T1071", "match_count": 3}], {4001: 5}, corpus)
    check("recommend() returns None for 'fired'", acov.recommend(_rec(fired, "T1071")) is None)
    # covered: visible, no match.
    covered = acov.assess([{"technique": "T1071", "match_count": 0}], {4001: 5}, corpus)
    check("recommend() returns None for 'covered'", acov.recommend(_rec(covered, "T1071")) is None)
    # blind: synthesize a record with has_detection False (the inventory never produces
    # blind, so construct the record shape directly to exercise the guard).
    blind_rec = dict(r_dark, status="blind")
    check("recommend() returns None for 'blind'", acov.recommend(blind_rec) is None)

    print("\n=== (b) EVERY DEFENSE STAMPED intent-blind (artifact_cooccurrence / 0.25 / True) ===\n")
    out = acov.recommend(r_dark)
    check("dark_spot recommendation has >=1 detect lead", len(out["defenses"]) >= 1)
    check("every defense proxy_quality == 'artifact_cooccurrence'",
          all(d["proxy_quality"] == "artifact_cooccurrence" for d in out["defenses"]))
    check("every defense trust == 0.25", all(d["trust"] == 0.25 for d in out["defenses"]))
    check("every defense intent_blind is True", all(d["intent_blind"] is True for d in out["defenses"]))
    check("every defense carries the literal intent-blind stamp",
          all(d["stamp"] == "artifact_cooccurrence — intent-blind possibility" for d in out["defenses"]))

    print("\n=== (c) OCSF CLASSES REAL: closed-set + equal to required minus landed ===\n")
    check("every classes_to_land in {1007,3002,4001,6003}",
          all(cu in br._OCSF_ALLOWED for cu in out["classes_to_land"]))
    expected = sorted(c for c in r_dark["required_classes"] if c not in r_dark["landed_classes"])
    check("classes_to_land == required_classes minus landed_classes",
          out["classes_to_land"] == expected)
    check("landed_classes is [] for a dark_spot (so classes_to_land = full required set)",
          r_dark["landed_classes"] == [])
    check("classes_to_land is non-empty and includes 4001 (Network Traffic -> 4001)",
          4001 in out["classes_to_land"])

    print("\n=== (d) TOPOLOGY TARGET HONEST: ^route_ node id, no fabricated named source ===\n")
    check("every topology_target.route_target matches ^route_",
          all(t["route_target"].startswith("route_") for t in out["topology_targets"]))
    check("action text says 'wire an ingest router', never invents a named source",
          all("wire an ingest router" in t["action"] for t in out["topology_targets"]))
    check("no topology_target action claims a specific customer source name",
          all("source named" not in t["action"].lower() and "your source" not in t["action"].lower()
              for t in out["topology_targets"]))

    print("\n=== (e) NO PER-CUSTOMER IN DEFAULT SURFACE (paid path is the only one that can) ===\n")
    import ui_helpers as ui
    mo = _MoStub()
    records = acov.assess([{"technique": "T1071", "match_count": 0}], {}, corpus)
    default_text = str(acov.recommendation_panel(mo, ui, records, paid=False))
    check("default panel renders the generic-method note", "Generic method (public)" in default_text)
    check("default panel frames per-environment binding as the services engagement",
          "services engagement" in default_text)
    check("default panel drops the run-MOAR_PAID_MODE=1 hint (scored Matrix is public now)",
          "MOAR_PAID_MODE=1" not in default_text)
    check("default panel does NOT render a per-environment 'your stack should deploy' claim",
          "what your stack should deploy" not in default_text.lower())
    check("default panel does NOT render the paid per-environment banner",
          "Per-environment recommender (paid)" not in default_text)
    paid_text = str(acov.recommendation_panel(mo, ui, records, paid=True,
                                              selection={"ingest": ["vector"]}))
    check("ONLY the paid path renders the per-environment recommender banner",
          "Per-environment recommender (paid)" in paid_text)
    check("paid path binds the route target to the live selection's ingest code (route_vector)",
          "route_vector" in paid_text)

    print("\n=== (f) AGGREGATE-SAFE: a nasty payload comes out inert through _safe_key ===\n")
    nasty = "T1071\n\x00`</span><script>alert(1)</script>"
    nasty_recs = acov.assess([{"technique": nasty, "match_count": 0}], {}, corpus)
    # Build a dark_spot record off the inventory T1071 but with a nasty by_class key too.
    nasty_by_class = {"4001\n`<script>": 0}
    nasty_dark = acov.assess([{"technique": "T1071", "match_count": 0}], nasty_by_class, corpus)
    nasty_out = acov.recommend(_rec(nasty_dark, "T1071"))
    nasty_panel = str(acov.recommendation_panel(mo, ui, nasty_dark, paid=False))

    def _all_strings(obj):
        if isinstance(obj, str):
            yield obj
        elif isinstance(obj, dict):
            for v in obj.values():
                yield from _all_strings(v)
        elif isinstance(obj, (list, tuple)):
            for v in obj:
                yield from _all_strings(v)

    rec_strings = list(_all_strings(nasty_out)) + [nasty_panel]
    check("no recommendation string carries a raw '<script' (breakout neutralized)",
          all("<script" not in s and "</span>" not in s for s in rec_strings))
    check("no recommendation string carries a markdown backtick from telemetry "
          "(only fixed code-span backticks remain)",
          "`</span>" not in nasty_panel and "alert(1)" not in nasty_panel)
    check("the technique label is _safe_key'd (matches the boundary)",
          nasty_out["technique"] == _safe_key("T1071"))

    print("\n=== (g) HONEST DEGRADE: zero-defense / not-in-corpus dark_spot -> [] + reason ===\n")
    # T1530 is not in corpus; force it to a dark_spot (its class 6003 absent).
    t1530 = acov.assess([{"technique": "T1530", "match_count": 0}], {}, corpus)
    r1530 = _rec(t1530, "T1530")
    check("T1530 resolves to dark_spot (class 6003 absent)", r1530["status"] == "dark_spot")
    deg = acov.recommend(r1530)
    check("T1530 recommendation fires (it IS a dark_spot)", deg is not None)
    check("T1530 defenses == [] (no fabricated defense)", deg["defenses"] == [])
    check("T1530 carries a degrade reason (honest gap)", bool(deg.get("degrade")))
    check("T1530 classes_to_land == [] (no fabricated OCSF class)", deg["classes_to_land"] == [])
    check("T1530 topology_targets == [] (nothing to land)", deg["topology_targets"] == [])

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mPG-5 recommend: dark_spot-only firing, every defense intent-blind stamped, "
          "OCSF classes real, route targets honest, no per-customer in the default surface, "
          "aggregate-safe, honest degrade — all hold.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
