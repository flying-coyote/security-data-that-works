"""Proof for Layer 4 DEEP — deterministic entity resolution.

The point of this layer is to close the false gaps the exact-match layer over-reports
(web-01 vs web-01.corp) WITHOUT ever closing a real gap on a guess. So the assertions
below prove both directions: declared-rule matches resolve, and every unsafe case
(different host, stale record, ambiguous match, in-source collision, undatable) is counted
as a gap and never silently merged.

Mostly pure-logic (no catalog needed); one real-Iceberg test for the extractor. Exit 0 =
every assertion held.
"""
from __future__ import annotations

import shutil
import sys
import tempfile

import pyarrow as pa
from pyiceberg.catalog.sql import SqlCatalog

import gate_logic as gl
import layer4_deep as ld

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []

NOW = "2026-06-19T00:00:00+00:00"
FRESH = "2026-06-18T18:00:00+00:00"   # 6h old — within the 1d TTL
STALE = "2026-05-01T00:00:00+00:00"   # ~7 weeks old — past TTL


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def main():
    R = ld.default_rules()

    # --- the normalization ladder reports honest confidences ---
    print("match-confidence ladder")
    check("identical -> 1.0", ld.match_confidence("web-01", "web-01", R) == 1.0)
    check("case-only -> 0.99", ld.match_confidence("Web-01", "web-01", R) == 0.99)
    check("domain-suffix -> 0.9", ld.match_confidence("web-01", "web-01.corp", R) == 0.9)
    check("different hosts -> 0.0 (no merge)", ld.match_confidence("web-01", "web-02", R) == 0.0)
    check("different + suffix -> 0.0", ld.match_confidence("web-01", "web-02.corp", R) == 0.0)

    # --- resolution closes the FALSE gaps the exact-match layer over-reports ---
    print("resolution (fresh source)")
    cmdb = {"web-01": FRESH, "db-01": FRESH, "app-01": FRESH}
    edr = {"web-01.corp": FRESH, "DB-01": FRESH, "app-01": FRESH}  # fqdn, case, exact
    r = ld.resolve_against(cmdb, edr, rules=R, now_iso=NOW)
    check("all three resolve via declared rules -> covered=3", r["covered"] == 3)
    check("no gap / stale / unresolved", r["uncovered_total"] == 0)
    check("mean confidence in (0.9..1.0]", 0.9 <= (r["mean_confidence"] or 0) <= 1.0)
    check("freshness measured", r["freshness"] == "measured")

    # --- a genuinely-missing host stays a gap (the layer's real job) ---
    print("real gap survives resolution")
    edr_missing = {"web-01.corp": FRESH, "DB-01": FRESH}  # app-01 absent
    r = ld.resolve_against(cmdb, edr_missing, rules=R, now_iso=NOW)
    check("covered=2, gap=1 (app-01 truly missing)", r["covered"] == 2 and r["gap"] == 1)

    # --- THE anti-bluff core: a different host is never merged into coverage ---
    print("different host is never falsely covered")
    edr_wronghost = {"web-02.corp": FRESH, "db-01": FRESH, "app-01": FRESH}  # web-02 != web-01
    r = ld.resolve_against(cmdb, edr_wronghost, rules=R, now_iso=NOW)
    check("web-01 stays a gap despite a similar-looking web-02", r["gap"] == 1 and r["covered"] == 2)

    # --- freshness fail-closed: a confident-but-stale match does NOT cover ---
    print("stale match counted as gap, not coverage")
    edr_stale = {"web-01.corp": STALE, "db-01": FRESH, "app-01": FRESH}
    r = ld.resolve_against(cmdb, edr_stale, rules=R, now_iso=NOW)
    check("stale=1 (web-01 too old), covered=2", r["stale"] == 1 and r["covered"] == 2)
    check("stale rolls into uncovered_total", r["uncovered_total"] == 1)
    edr_undatable = {"web-01.corp": None, "db-01": FRESH, "app-01": FRESH}  # None in a dated source
    r = ld.resolve_against(cmdb, edr_undatable, rules=R, now_iso=NOW)
    check("undatable record in a dated source -> stale (fail-closed)", r["stale"] == 1)

    # --- ambiguity is left UNRESOLVED, never silently coalesced ---
    print("ambiguous matches stay unresolved")
    edr_ambig = {"web-01.corp": FRESH, "web-01.local": FRESH, "db-01": FRESH, "app-01": FRESH}
    r = ld.resolve_against(cmdb, edr_ambig, rules=R, now_iso=NOW)
    check("web-01 matches two source ids -> unresolved=1 (not covered)", r["unresolved"] == 1)
    check("ambiguous web-01 not counted as covered", r["covered"] == 2)
    # primary self-collision
    cmdb_dup = {"web-01": FRESH, "web-01.corp": FRESH, "app-01": FRESH}  # two rows, same entity
    r = ld.resolve_against(cmdb_dup, {"app-01": FRESH, "x": FRESH}, rules=R, now_iso=NOW)
    check("primary self-collision -> both unresolved", r["unresolved"] == 2)

    # --- confidence-only when a source carries no timestamps at all ---
    print("freshness unmeasured (source has no timestamps)")
    edr_nots = {"web-01.corp": None, "db-01": None, "app-01": None}
    r = ld.resolve_against(cmdb, edr_nots, rules=R, now_iso=NOW)
    check("covers on confidence alone", r["covered"] == 3)
    check("freshness flagged unmeasured (not a clean green)", r["freshness"] == "unmeasured")

    # --- cross_tool_gap_deep aggregation + status + unmeasured guards ---
    print("cross_tool_gap_deep status")
    g = ld.cross_tool_gap_deep("cmdb", {"cmdb": cmdb, "edr": edr}, now_iso=NOW)
    check("all resolved -> pass", g["status"] == "pass")
    g = ld.cross_tool_gap_deep("cmdb", {"cmdb": cmdb, "edr": edr_missing}, now_iso=NOW)
    check("a real gap -> fail", g["status"] == "fail")
    g = ld.cross_tool_gap_deep("cmdb", {"cmdb": cmdb}, now_iso=NOW)
    check("single source -> unmeasured", g["status"] == "unmeasured")
    g = ld.cross_tool_gap_deep("cmdb", {"cmdb": None, "edr": edr}, now_iso=NOW)
    check("primary unreadable -> unmeasured", g["status"] == "unmeasured")
    g = ld.cross_tool_gap_deep("cmdb", {"cmdb": {}, "edr": edr}, now_iso=NOW)
    check("empty primary inventory -> unmeasured (not a vacuous pass)", g["status"] == "unmeasured")
    g = ld.cross_tool_gap_deep("cmdb", {"cmdb": cmdb, "edr": edr_nots}, now_iso=NOW)
    check("confidence-only cover passes but carries freshness_caveat", g["status"] == "pass" and g["freshness_caveat"] is True)

    # --- the deep status drives the gate exactly like the exact-match one ---
    print("gate integration")
    gate = gl.compute_gate(warns=[], spec_saved=True, docker_up=True, catalog_live=True,
                           layer1_status="pass", layer3_status="pass",
                           layer4_status=ld.cross_tool_gap_deep("cmdb", {"cmdb": cmdb, "edr": edr}, now_iso=NOW)["status"])
    check("deep pass -> a real GREEN is reachable", gate["all_green"] is True)
    gate = gl.compute_gate(warns=[], spec_saved=True, docker_up=True, catalog_live=True,
                           layer1_status="pass", layer3_status="pass",
                           layer4_status=ld.cross_tool_gap_deep("cmdb", {"cmdb": cmdb, "edr": edr_missing}, now_iso=NOW)["status"])
    check("deep fail -> gate is not green", gate["all_green"] is False)

    # --- the Iceberg extractor pulls id + latest-timestamp, fail-soft on a missing column ---
    print("iceberg extractor (real table)")
    wh = tempfile.mkdtemp(prefix="moar_l4deep_")
    try:
        cat = SqlCatalog("p", **{"uri": f"sqlite:///{wh}/c.db", "warehouse": f"file://{wh}"})
        cat.create_namespace("inv")
        schema = pa.schema([("hostname", pa.string()), ("last_seen", pa.string())])
        data = pa.table({"hostname": ["h1", "h1", "h2"],
                         "last_seen": ["2026-06-01T00:00:00+00:00", "2026-06-18T00:00:00+00:00", "2026-06-10T00:00:00+00:00"]},
                        schema=schema)
        t = cat.create_table("inv.edr", schema=schema)
        t.append(data)
        m = ld.extract_ids_with_freshness(t, "hostname", "last_seen")
        check("extractor dedups to latest ts per id", m == {"h1": "2026-06-18T00:00:00+00:00", "h2": "2026-06-10T00:00:00+00:00"})
        check("missing id column -> None (unmeasured upstream)", ld.extract_ids_with_freshness(t, "nope", "last_seen") is None)
        m2 = ld.extract_ids_with_freshness(t, "hostname")  # no ts column -> all None
        check("no ts column -> ids map to None", m2 == {"h1": None, "h2": None})
    finally:
        shutil.rmtree(wh, ignore_errors=True)

    print()
    if _failures:
        print(f"\033[91m{len(_failures)} FAILED:\033[0m " + "; ".join(_failures))
        sys.exit(1)
    print("\033[92mall layer4-deep assertions held\033[0m")


if __name__ == "__main__":
    main()
