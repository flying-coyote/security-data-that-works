"""Proof that every reference preset references real components and covers the archetypes.

Run:  python3 prove_reference_presets.py     (exit 0 = every assertion held)
Pure stdlib.
"""
from __future__ import annotations

import sys

import providers as P
import reference_presets as rp

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def main():
    print("\n=== preset component codes resolve against the provider catalog ===\n")
    bad = rp.invalid_codes(P.CATEGORIES)
    check(f"no preset references an unknown component (found: {bad})", bad == [])

    print("\n=== every preset is complete and well-formed ===\n")
    for preset in rp.PRESETS:
        comp = preset["components"]
        has_all = all(k in comp for k in ("storage", "catalog", "schema", "ingest", "query"))
        check(f"{preset['code']}: has all five categories + when/cost/cite",
              has_all and preset["when_it_wins"] and preset["cost_profile"] and preset["cite"])
        check(f"{preset['code']}: at least one ingest and one query engine",
              len(comp["ingest"]) >= 1 and len(comp["query"]) >= 1)

    print("\n=== the archetypes the book leans on are represented ===\n")
    codes = {p["code"] for p in rp.PRESETS}
    check("a lean single-engine archetype exists", "lean_single_engine" in codes)
    check("a workload-optimized multi-engine archetype exists", "hybrid_multi_engine" in codes)
    check("an air-gapped / on-prem archetype exists", "airgap_onprem" in codes)
    check("a cost-aggressive route-by-value archetype exists", "cost_aggressive" in codes)

    print("\n=== lookups ===\n")
    check("by_code round-trips", rp.by_code("lean_single_engine")["name"] == "Lean single-engine lakehouse")
    check("by_name round-trips", rp.by_name("Air-gapped on-prem")["code"] == "airgap_onprem")
    check("names() lists every preset", len(rp.names()) == len(rp.PRESETS))

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mAll reference-preset assertions held.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
