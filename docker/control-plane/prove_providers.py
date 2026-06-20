"""Proof that the picker vocabulary lines up with the Matrix C0-C8 taxonomy (T6).

providers.py drives the console's five component pickers. T6 maps each picker onto the
Capability Matrix's nine scored components (C0-C8, per MATRIX.md / the website components
page) so the console reads legibly against the Matrix + site, and notes the components that
are NOT pickers rather than inventing new ones. This harness asserts the mapping is complete
(every picker mapped; all nine C-numbers accounted for) and non-overlapping, plus a couple of
base providers invariants — the first proof this core module has carried.

Run:  python3 prove_providers.py     (exit 0 = every assertion held)
Pure stdlib.
"""
from __future__ import annotations

import sys

import providers as P

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def main():
    print("\n=== every picker category maps to a Matrix component (T6) ===\n")
    check("the five picker categories are exactly the mapped set",
          set(P.CATEGORIES) == set(P.MATRIX_COMPONENT))

    print("\n=== the mapping is the published C-numbers (grounded in the component defs) ===\n")
    check("storage -> C6 (the object-store/tier layer: S3/MinIO/Wasabi/Dell ECS)",
          P.MATRIX_COMPONENT["storage"][0] == "C6")
    check("catalog -> C2", P.MATRIX_COMPONENT["catalog"][0] == "C2")
    check("ingest  -> C4", P.MATRIX_COMPONENT["ingest"][0] == "C4")
    check("query   -> C3", P.MATRIX_COMPONENT["query"][0] == "C3")
    check("schema is cross-cutting, not a single C-number (C1 = table format)",
          P.MATRIX_COMPONENT["schema"][0] == "—")

    print("\n=== all nine components C0-C8 are accounted for (picker or noted), no overlap ===\n")
    mapped = {c for c, _name in P.MATRIX_COMPONENT.values() if c != "—"}
    omitted = {c for c, _name, _why in P.MATRIX_OMITTED}
    check("mapped C-numbers {C2,C3,C4,C6} are exactly the picker ones",
          mapped == {"C2", "C3", "C4", "C6"})
    check("mapped and omitted C-numbers do not overlap", mapped.isdisjoint(omitted))
    check("mapped ∪ omitted == the full C0-C8 set (nothing dropped, nothing invented)",
          (mapped | omitted) == {f"C{i}" for i in range(9)})
    check("each omitted component carries a reason it isn't a picker",
          all(why for _c, _name, why in P.MATRIX_OMITTED))

    print("\n=== component_tag formatting ===\n")
    check("component_tag('storage') == 'C6 · Storage tier'",
          P.component_tag("storage") == "C6 · Storage tier")
    check("component_tag of an unknown category is empty", P.component_tag("nope") == "")

    print("\n=== base providers invariants (first proof for this module) ===\n")
    for _cat, _val in P.DEFAULTS.items():
        codes = _val if isinstance(_val, list) else [_val]
        for _c in codes:
            check(f"default {_cat} '{_c}' exists in its catalog",
                  P.find(P.CATEGORIES[_cat], _c) is not None)
    check("every provider code is unique within its category",
          all(len({p.code for p in grp}) == len(grp) for grp in P.CATEGORIES.values()))
    check("label_for round-trips through code_for on a sample",
          P.code_for(P.QUERY, P.label_for(P.QUERY, "duckdb")) == "duckdb")

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mAll providers assertions held — the picker vocabulary maps cleanly to C0-C8.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
