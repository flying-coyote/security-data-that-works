"""Proof for OCSF round-trip semantic validation (cluster 5).

Run:  python3 prove_ocsf_roundtrip.py     (exit 0 = every assertion held)
Pure stdlib.
"""
from __future__ import annotations

import sys

import ocsf_roundtrip as rt

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def main():
    print("\n=== per-event value check ===\n")
    produced = {"activity_id": 1, "src_endpoint": {"ip": "192.0.2.1", "port": 443}, "severity_id": 3}
    faithful = rt.check_event({"activity_id": 1, "src_endpoint.ip": "192.0.2.1", "severity_id": 3}, produced)
    check("a faithful event -> pass", faithful["status"] == "pass" and not faithful["mismatches"])

    missing = rt.check_event({"src_endpoint.ip": "192.0.2.1", "dst_endpoint.ip": "10.0.0.1"}, produced)
    check("a missing field -> fail", missing["status"] == "fail")
    check("the missing field is named with why=missing",
          any(m["path"] == "dst_endpoint.ip" and m["why"] == "missing" for m in missing["mismatches"]))

    # schema-valid but WRONG value — the meaning is wrong though the shape is fine.
    wrong = rt.check_event({"severity_id": 5}, produced)
    check("a schema-valid wrong value -> fail (meaning, not shape)", wrong["status"] == "fail")
    check("the wrong value is reported (got 3, expected 5)",
          any(m["why"] == "wrong-value" and m["got"] == 3 and m["expected"] == 5 for m in wrong["mismatches"]))

    check("nested dotted path resolves", rt.check_event({"src_endpoint.port": 443}, produced)["status"] == "pass")
    check("expected False, produced 0 -> fail (no 0==False trap)",
          rt.check_event({"flag": False}, {"flag": 0})["status"] == "fail")
    check("expected 1, produced True -> fail (no 1==True trap)",
          rt.check_event({"n": 1}, {"n": True})["status"] == "fail")
    check("present None matches expected None -> pass",
          rt.check_event({"opt": None}, {"opt": None})["status"] == "pass")
    check("present falsy 0 matches expected 0 -> pass",
          rt.check_event({"count": 0}, {"count": 0})["status"] == "pass")

    print("\n=== aggregate over a source's test events ===\n")
    a_pass = rt.validate([{"expected": {"activity_id": 1}, "produced": produced},
                          {"expected": {"severity_id": 3}, "produced": produced}])
    check("all events faithful -> pass", a_pass["status"] == "pass")
    a_fail = rt.validate([{"expected": {"activity_id": 1}, "produced": produced},
                          {"expected": {"activity_id": 9}, "produced": produced}])
    check("any event wrong -> fail, count surfaced", a_fail["status"] == "fail" and a_fail["fail_count"] == 1)
    check("no test events -> unmeasured (no false pass)", rt.validate([])["status"] == "unmeasured")

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mAll OCSF round-trip assertions held.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
