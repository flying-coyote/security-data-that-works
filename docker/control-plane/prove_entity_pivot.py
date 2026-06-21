"""Proof for entity_pivot — the entity-pivot investigation profile (analyst-value, Phase G flagship).

Covers: the pivotable allow-list; scan_entity correctness over a known distribution; the cross-path
AGREEMENT guard (the pure scan_entity and the duckdb-over-arrow profile_entity return the same
aggregates, so the preview and the live SQL path can't drift); the telemetry-injection guards (a
crafted counterpart key is sanitized via analyze._safe_key; pivoting is only by an allow-listed entity
type, never a free-text field); to_sql parameterization (the entity value is bound, never interpolated);
and honest-degrade (absent field/class skipped, unknown type raises).

Run:  python3 prove_entity_pivot.py   (needs duckdb + pyarrow — runs via /tmp/pyice-venv)
"""
from __future__ import annotations

import sys

import entity_pivot as ep

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


# A known synthetic OCSF distribution (aggregate assertions are exact).
#   10.0.1.5  : src in 4 network flows (3 -> 10.0.2.9, 1 -> 10.0.2.10) + 2 auths (user alice)
#   203.0.113.9: src in 5 failed auths (user bob)
#   10.0.1.99 : 1 network flow to a CRAFTED dst_ip (injection probe)
RECS = (
    [{"class_uid": 4001, "activity_id": 6, "src_ip": "10.0.1.5", "dst_ip": "10.0.2.9",
      "time": f"2026-06-21T10:0{i}:00Z"} for i in range(3)]
    + [{"class_uid": 4001, "activity_id": 6, "src_ip": "10.0.1.5", "dst_ip": "10.0.2.10",
        "time": "2026-06-21T10:05:00Z"}]
    + [{"class_uid": 3002, "category_uid": 3, "activity_id": 1, "status_id": 2,
        "src_ip": "10.0.1.5", "user": "alice", "time": f"2026-06-21T09:0{i}:00Z"} for i in range(2)]
    + [{"class_uid": 3002, "category_uid": 3, "activity_id": 1, "status_id": 2,
        "src_ip": "203.0.113.9", "user": "bob", "time": f"2026-06-21T08:0{i}:00Z"} for i in range(5)]
    + [{"class_uid": 4001, "activity_id": 6, "src_ip": "10.0.1.99", "dst_ip": "9.9.9.9`x<b>",
        "time": "2026-06-21T11:00:00Z"}]
)


def _arrow(records):
    import pyarrow as pa
    allk = sorted(set().union(*(r.keys() for r in records)))
    return pa.Table.from_pylist([{k: r.get(k) for k in allk} for r in records])


def _agg_view(p):
    """The comparable aggregate core of a profile (order-independent)."""
    return (p["total_events"], p["by_class"], p["by_activity"], p["distinct_counterparts"],
            sorted(p["counterparts"]), p["time_span"])


def main():
    print("\n=== pivotable allow-list (pure) ===\n")
    check("pivotable types are ip + user (identifier-shaped, not free-text)",
          set(ep.pivotable_types()) == {"ip", "user"})
    check("an unknown / free-text entity type raises (can't pivot on cmd_line/url/message)",
          _raises(lambda: ep.scan_entity(RECS, "cmd_line", "x")))

    print("\n=== scan_entity over a known distribution (pure) ===\n")
    ip = ep.scan_entity(RECS, "ip", "10.0.1.5")
    check("ip 10.0.1.5 -> 6 events across 2 classes (Network 4001:4, Auth 3002:2)",
          ip["total_events"] == 6 and ip["by_class"] == {4001: 4, 3002: 2})
    check("ip 10.0.1.5 counterparts: 10.0.2.9:3, 10.0.2.10:1 (distinct 2), auth rows add none (no dst_ip)",
          set(ip["counterparts"]) == {("10.0.2.9", 3), ("10.0.2.10", 1)} and ip["distinct_counterparts"] == 2)
    check("ip 10.0.1.5 first_seen/last_seen bound present", ip["time_span"] and ip["time_span"]["min"] <= ip["time_span"]["max"])
    usr = ep.scan_entity(RECS, "user", "alice")
    check("user alice -> 2 auth events, counterpart src_ip 10.0.1.5:2",
          usr["total_events"] == 2 and usr["by_class"] == {3002: 2}
          and sorted(usr["counterparts"]) == [("10.0.1.5", 2)])
    check("a user pivot does NOT bleed across entities (alice != bob's 5 events)",
          ep.scan_entity(RECS, "user", "bob")["total_events"] == 5)

    print("\n=== cross-path agreement: scan_entity (pure) == profile_entity (duckdb/arrow) ===\n")
    at = _arrow(RECS)
    for et, val in [("ip", "10.0.1.5"), ("user", "alice"), ("ip", "203.0.113.9"), ("user", "bob")]:
        check(f"agree on {et}={val}", _agg_view(ep.scan_entity(RECS, et, val)) == _agg_view(ep.profile_entity(at, et, val)))

    print("\n=== telemetry-injection: a crafted counterpart key is sanitized ===\n")
    probe = ep.scan_entity(RECS, "ip", "10.0.1.99")
    pk = probe["counterparts"][0][0] if probe["counterparts"] else ""
    check("crafted dst_ip counterpart has NO backtick and NO live <b> markup (analyze._safe_key)",
          "`" not in pk and "<b>" not in pk and "9.9.9.9" in pk)
    probe2 = ep.profile_entity(at, "ip", "10.0.1.99")
    check("the duckdb path sanitizes the crafted key identically",
          probe2["counterparts"] and "`" not in probe2["counterparts"][0][0] and "<b>" not in probe2["counterparts"][0][0])
    vv = ep.scan_entity(RECS, "ip", "1.2.3.4`<script>")
    check("the echoed entity selector itself is sanitized (no backtick / raw <script>)",
          "`" not in vv["value"] and "<script>" not in vv["value"])

    print("\n=== to_sql parameterization (live path) ===\n")
    sql, params = ep.to_sql("ip", "10.0.1.5", "ocsf.network_activity")
    check("the entity value is a BOUND parameter, never interpolated into the SQL string",
          "10.0.1.5" not in sql and params == ["10.0.1.5"] * 3 and sql.count("?") == 3)
    check("to_sql shape: filtered per-class GROUP BY over the named table",
          "GROUP BY class_uid" in sql and "ocsf.network_activity" in sql and "count(*)" in sql)

    print("\n=== demo data self-demonstrates (the preview/flip-through shows a real profile) ===\n")
    dr = ep.demo_records()
    check("every suggested demo entity resolves to >0 events",
          all(ep.scan_entity(dr, et, val)["total_events"] > 0 for et, val, _ in ep.demo_entities()))
    cross = ep.scan_entity(dr, "ip", "10.0.1.50")
    check("the flagship cross-source story holds: 10.0.1.50 spans Network 4001 AND Auth 3002",
          4001 in cross["by_class"] and 3002 in cross["by_class"])

    print("\n=== honest-degrade ===\n")
    none_table = ep.scan_entity([{"class_uid": 4001, "src_ip": "10.0.0.1"}], "ip", "10.9.9.9")
    check("an entity absent from the data -> 0 events, nothing fabricated", none_table["total_events"] == 0)
    no_time = ep.scan_entity([{"class_uid": 3002, "user": "x"}], "user", "x")
    check("a dataset with no time field -> time_span skipped + reported (not crashed)",
          no_time["time_span"] is None and "time_span" in no_time["skipped"])

    print()
    if _failures:
        print(f"\033[91m{len(_failures)} assertion(s) FAILED:\033[0m " + "; ".join(_failures))
        return 1
    print("\033[92mAll entity_pivot assertions held.\033[0m")
    return 0


def _raises(fn):
    try:
        fn()
        return False
    except Exception:  # noqa: BLE001
        return True


if __name__ == "__main__":
    sys.exit(main())
