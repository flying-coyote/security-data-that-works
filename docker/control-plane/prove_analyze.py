"""Proof for analyze.py — the Analyze (log analysis) pane's aggregate-only logic.

Run (needs pyarrow/duckdb):  /tmp/pyice-venv/bin/python prove_analyze.py
Exit 0 = every assertion held.

No mocks: a real PyArrow table with a KNOWN distribution, run through the same
`analyze_table` the console calls on its `.scan().to_arrow()` output. The two
load-bearing assertions are correctness of the counts AND the safety invariant —
that the returned structure contains nothing but counts, the low-cardinality
grouping keys, and capped top-N (value, count) aggregates, with no full record /
row object / free-text field leaking into the output (the telemetry-injection
rule that the Iceberg Metadata Inspector also enforces).
"""
from __future__ import annotations

import sys

import pyarrow as pa

import analyze

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def build_table():
    """Synthetic OCSF-ish table with a known distribution.

    - class_uid: 12x 3002, 8x 4001                       -> by_class {3002:12, 4001:8}
    - activity_id: 14x 1, 6x 2                            -> by_activity {1:14, 2:6}
    - src_ip: 1.1.1.1 x9, 2.2.2.2 x6, then 5 singletons   -> top_sources, 9 then 6 ...
    - status: SUCCESS/FAILURE free-text-ish (NOT a grouping field here -> must NOT leak)
    - time: 100..119                                      -> time_span min 100 max 119
    Plus one carefully-crafted src with a control char + an over-long value to
    prove the source key is sanitised and length-bounded.
    """
    n = 20
    class_uid = [3002] * 12 + [4001] * 8
    activity_id = [1] * 14 + [2] * 6
    # 9 of 1.1.1.1, 6 of 2.2.2.2, then 5 distinct singletons -> 20 total.
    src_ip = ["1.1.1.1"] * 9 + ["2.2.2.2"] * 6 + [
        "3.3.3.3", "4.4.4.4", "5.5.5.5",
        "6.6.6.6\x07INJECT",                 # control char must be stripped
        "7." + "9" * 80,                      # over-long must be truncated
    ]
    status = (["SUCCESS"] * 14) + (["FAILURE"] * 6)   # free text — must never be surfaced
    time = list(range(100, 120))
    assert len(class_uid) == len(activity_id) == len(src_ip) == len(status) == len(time) == n
    return pa.table({
        "class_uid": pa.array(class_uid, pa.int32()),
        "activity_id": pa.array(activity_id, pa.int32()),
        "src_ip": pa.array(src_ip),
        "status": pa.array(status),
        "time": pa.array(time, pa.int64()),
    })


def _is_count_like(v):
    return isinstance(v, int) and not isinstance(v, bool)


def main():
    print("\n=== analyze.py — aggregate-only log analysis ===\n")
    t = build_table()
    r = analyze.analyze_table(t)

    # --- correctness of the counts/aggregates ---
    check("row_count is correct (20)", r["row_count"] == 20)
    check("by_class counts correct {3002:12, 4001:8}",
          r.get("by_class") == {3002: 12, 4001: 8})
    check("by_activity counts correct {1:14, 2:6}",
          r.get("by_activity") == {1: 14, 2: 6})

    top = r.get("top_sources")
    check("top_sources present and is a list", isinstance(top, list) and len(top) > 0)
    check("top_sources_field identifies src_ip", r.get("top_sources_field") == "src_ip")
    check("top source is (1.1.1.1, 9)", top[0] == ("1.1.1.1", 9))
    check("second source is (2.2.2.2, 6)", top[1] == ("2.2.2.2", 6))
    check("every top_sources entry is a (value, count) pair",
          all(isinstance(x, tuple) and len(x) == 2 and _is_count_like(x[1]) for x in top))

    # field population — counts only, every field accounted for, no values.
    fp = {row["field"]: row for row in r["field_population"]}
    check("field_population covers all 5 columns", len(fp) == 5)
    check("field_population is counts only (non_null + null == row_count)",
          all(_is_count_like(row["non_null"]) and _is_count_like(row["null"])
              and row["non_null"] + row["null"] == 20 for row in r["field_population"]))

    # time span — two scalar bounds.
    ts = r.get("time_span")
    check("time_span min/max correct (100/119)",
          ts is not None and ts["min"] == 100 and ts["max"] == 119)

    # --- the cap + sanitisation safety properties ---
    check("top_sources is capped at TOP_N_SOURCES",
          len(top) <= analyze.TOP_N_SOURCES)
    src_values = [v for v, _ in top]
    check("control char stripped from a source value",
          all("\x07" not in (v or "") for v in src_values))
    check("over-long source value truncated to <= _MAX_KEY_LEN+1",
          all(len(v or "") <= analyze._MAX_KEY_LEN + 1 for v in src_values))

    # --- partial/honest: a missing grouping field is skipped, not a crash ---
    t_min = pa.table({"class_uid": pa.array([3002, 3002], pa.int32())})
    rm = analyze.analyze_table(t_min)  # no activity_id, no src_ip, no time
    check("missing fields recorded in 'skipped' (not crashed)",
          set(rm.get("skipped", [])) >= {"activity_id", "top_sources", "time_span"})
    check("present field still computed on a partial table",
          rm.get("by_class") == {3002: 2})
    check("absent views simply omitted",
          "by_activity" not in rm and "top_sources" not in rm and "time_span" not in rm)

    # --- the load-bearing invariant: NO full rows / free-text leakage ---
    # The only string values anywhere in the output must be (a) the top_sources
    # keys (the one high-card field we surface as capped aggregates) and (b) the
    # field NAMES (schema, not data) and the time field name. Crucially, the
    # free-text 'status' field's VALUES ("SUCCESS"/"FAILURE") must appear nowhere.
    # The result's own structural keys are the output CONTRACT (schema of the
    # dict), not telemetry — they're allowed. What must never leak is a data VALUE.
    structural_keys = {
        "row_count", "field_population", "field", "non_null", "null",
        "by_class", "by_activity", "top_sources", "top_sources_field",
        "time_span", "min", "max", "skipped",
    }
    allowed_strings = set(structural_keys)
    allowed_strings |= {v for v, _ in top if v is not None}            # top-N source keys (capped aggregate)
    allowed_strings |= {row["field"] for row in r["field_population"]}  # column names (schema)
    allowed_strings |= {r["top_sources_field"], ts["field"]}           # field names
    allowed_strings |= set(rm.get("skipped", []))                      # skip labels (from second table)
    allowed_strings |= {"class_uid", "activity_id", "src_ip", "status", "time"}  # column names again

    def walk_strings(obj):
        if isinstance(obj, str):
            yield obj
        elif isinstance(obj, dict):
            for k, v in obj.items():
                # keys that are ints (class_uid/activity_id grouping keys) are fine; only str keys count
                if isinstance(k, str):
                    yield k
                yield from walk_strings(v)
        elif isinstance(obj, (list, tuple)):
            for x in obj:
                yield from walk_strings(x)

    leaked = [s for s in walk_strings(r) if s not in allowed_strings]
    check("status free-text values never appear in output (no SUCCESS/FAILURE)",
          "SUCCESS" not in leaked and "FAILURE" not in leaked)
    check("no unexpected free-text string leaks into the result structure",
          leaked == [],
          )
    if leaked:
        print("    leaked strings:", leaked[:10])

    # every dict-key grouping value is low-card categorical (int) or the <null> bucket;
    # no row-object / record dict anywhere.
    def has_record_object(obj):
        # a "record" would be a dict whose keys are the column names together
        cols = {"class_uid", "activity_id", "src_ip", "status", "time"}
        if isinstance(obj, dict) and cols.issubset(set(map(str, obj.keys()))):
            return True
        if isinstance(obj, dict):
            return any(has_record_object(v) for v in obj.values())
        if isinstance(obj, (list, tuple)):
            return any(has_record_object(x) for x in obj)
        return False

    check("no full-row / record object anywhere in the output",
          not has_record_object(r))
    check("by_class keys are low-card categorical ints only",
          all(_is_count_like(k) for k in r["by_class"].keys()))
    check("by_activity keys are low-card categorical ints only",
          all(_is_count_like(k) for k in r["by_activity"].keys()))

    print()
    if _failures:
        print(f"\033[91m{len(_failures)} assertion(s) FAILED:\033[0m " + "; ".join(_failures))
        return 1
    print("\033[92mAll assertions held — analyze_table returns correct counts/aggregates over a known "
          "distribution, caps + sanitises the high-cardinality top-N, skips absent fields without "
          "crashing, and leaks no full rows or free-text field values (telemetry-injection rule).\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
