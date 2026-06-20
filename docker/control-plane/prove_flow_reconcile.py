"""Proof for per-OCSF-class flow reconciliation (cluster 5).

Run:  python3 prove_flow_reconcile.py     (exit 0 = every assertion held)
Pure stdlib.
"""
from __future__ import annotations

import sys

import flow_reconcile as fr

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def main():
    print("\n=== per-class reconciliation ===\n")
    ok = fr.reconcile_class("3002", {"emitted": 1000, "ingested": 1000, "landed": 1000})
    check("fully reconciled -> pass, zero drop", ok["status"] == "pass" and ok["drop"] == 0)
    lost = fr.reconcile_class("3002", {"emitted": 4000, "ingested": 3998, "landed": 3990})
    check("a silent drop -> fail", lost["status"] == "fail")
    check("the gap is named in the note", "dropped 10" in lost["note"] and lost["drop"] == 10)
    miss = fr.reconcile_class("4001", {"emitted": 1000, "ingested": None, "landed": 1000})
    check("a missing hop count -> unmeasured", miss["status"] == "unmeasured")
    zero = fr.reconcile_class("4001", {"emitted": 0, "ingested": 0, "landed": 0})
    check("nothing emitted -> unmeasured (no false pass)", zero["status"] == "unmeasured")

    print("\n=== tolerance ===\n")
    within = fr.reconcile_class("3002", {"emitted": 1000, "ingested": 1000, "landed": 999}, tolerance_frac=0.01)
    check("a drop within tolerance -> pass", within["status"] == "pass")
    beyond = fr.reconcile_class("3002", {"emitted": 1000, "ingested": 1000, "landed": 980}, tolerance_frac=0.01)
    check("a drop beyond tolerance -> fail", beyond["status"] == "fail")
    boundary = fr.reconcile_class("3002", {"emitted": 1000, "ingested": 1000, "landed": 990}, tolerance_frac=0.01)
    check("drop exactly at the tolerance threshold -> pass (strict >)", boundary["status"] == "pass")
    check("negative emitted -> unmeasured (invalid input)",
          fr.reconcile_class("3002", {"emitted": -100, "ingested": 100, "landed": 100})["status"] == "unmeasured")
    check("negative ingested -> unmeasured",
          fr.reconcile_class("3002", {"emitted": 1000, "ingested": -5, "landed": 1000})["status"] == "unmeasured")

    print("\n=== aggregate across classes ===\n")
    a_pass = fr.reconcile({"3002": {"emitted": 100, "ingested": 100, "landed": 100},
                           "4001": {"emitted": 50, "ingested": 50, "landed": 50}})
    check("all classes reconcile -> pass", a_pass["status"] == "pass")
    a_fail = fr.reconcile({"3002": {"emitted": 100, "ingested": 100, "landed": 100},
                           "4001": {"emitted": 50, "ingested": 50, "landed": 40}})
    check("any class drops -> fail", a_fail["status"] == "fail")
    check("worst_drop is surfaced", a_fail["worst_drop"] == 0.2)
    a_unm = fr.reconcile({"3002": {"emitted": None, "ingested": None, "landed": None}})
    check("no measured class -> unmeasured", a_unm["status"] == "unmeasured")
    check("empty input -> unmeasured", fr.reconcile({})["status"] == "unmeasured")

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mAll flow-reconciliation assertions held.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
