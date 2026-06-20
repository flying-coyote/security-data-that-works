"""Proof that the cost advisor reproduces the cost-to-serve-retention lab numbers.

The published essay's cost table (1 TB/day, AWS us-east-1 list) is the oracle:
30d index $1,200 vs warm $81 (~14.8x); 7y ~$95k/mo gap; cold ~96.7x. This asserts the
advisor lands on those within rounding.

Run:  python3 prove_cost_advisor.py     (exit 0 = every assertion held)
Pure stdlib.
"""
from __future__ import annotations

import sys

import cost_advisor as ca

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def near(a, b, tol=0.03):
    return abs(a - b) <= tol * max(abs(b), 1.0)


def main():
    print("\n=== 1 TB/day, 30 days (essay reference row) ===\n")
    e30 = ca.estimate(1, 30)
    check(f"hot index ~ $1,200/mo (got ${e30['index_hot_monthly']:,.0f})", near(e30["index_hot_monthly"], 1200, 0.02))
    check(f"warm lakehouse ~ $81/mo (got ${e30['warm_lakehouse_monthly']:,.0f})", near(e30["warm_lakehouse_monthly"], 81, 0.03))
    check(f"warm multiple ~ 14.8x (got {e30['warm_multiple']:.2f})", near(e30["warm_multiple"], 14.8, 0.02))
    check(f"cold multiple ~ 96.7x (got {e30['cold_multiple']:.1f})", near(e30["cold_multiple"], 96.7, 0.02))

    print("\n=== 1 TB/day, 7 years (the existential gap) ===\n")
    e7y = ca.estimate(1, 2555)
    check(f"7y monthly gap ~ $95k (got ${e7y['monthly_gap']:,.0f})", near(e7y["monthly_gap"], 95000, 0.03))
    check("the multiple is retention-invariant (linear in days)",
          near(e7y["warm_multiple"], e30["warm_multiple"], 0.001))

    print("\n=== scaling + edge cases ===\n")
    e10 = ca.estimate(10, 30)
    check("10x volume scales monthly cost 10x", near(e10["warm_lakehouse_monthly"], 10 * e30["warm_lakehouse_monthly"], 0.001))
    z = ca.estimate(0, 30)
    check("zero volume → zero cost, no divide-by-zero", z["warm_lakehouse_monthly"] == 0 and z["warm_multiple"] == 0)
    check("summary_md handles the zero case", "Set a non-zero" in ca.summary_md(z))
    check("summary_md renders the reference read", "14.8x" in ca.summary_md(e30) or "14.8" in ca.summary_md(e30))

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mAll cost-advisor assertions held — reproduces the lab numbers.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
