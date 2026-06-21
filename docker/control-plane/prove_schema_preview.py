"""Proof for schema_preview — the Setup schema preview (Phase E, PE-3). Pure; no stack.

Covers classes_for (standard + source scoping), the OCSF-only behaviour, and a CON-AUTH-1 canonical
regression guard (the preview must show the CORRECTED Authentication shape — outcome in status_id,
activity_id = the operation — and CloudTrail API as 6003 not 3005).

Run:  python3 prove_schema_preview.py
"""
from __future__ import annotations

import sys

import schema_preview as sp

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def main():
    print("\n=== classes_for (pure) ===\n")
    allc = sp.classes_for("ocsf")
    check("OCSF -> all four classes the routers produce (1007, 3002, 4001, 6003)",
          [c["class_uid"] for c in allc] == [1007, 3002, 4001, 6003])
    check("OCSF is case-insensitive ('OCSF' works)", len(sp.classes_for("OCSF")) == 4)
    check("OCSF + sources=[zeek] -> [4001]",
          [c["class_uid"] for c in sp.classes_for("ocsf", ["zeek"])] == [4001])
    check("OCSF + sources=[cloudtrail] -> [3002, 6003]",
          [c["class_uid"] for c in sp.classes_for("ocsf", ["cloudtrail"])] == [3002, 6003])
    check("OCSF + sources=[zeek, sysmon] -> [1007, 4001] (sorted, deduped)",
          [c["class_uid"] for c in sp.classes_for("ocsf", ["zeek", "sysmon"])] == [1007, 4001])
    check("a non-OCSF standard -> [] (the console normalizes to OCSF only)", sp.classes_for("delta") == [])
    check("None standard -> []", sp.classes_for(None) == [])
    check("an unknown source -> contributes no class (no crash)", sp.classes_for("ocsf", ["nope"]) == [])

    print("\n=== CON-AUTH-1 canonical grounding (regression guard) ===\n")
    auth = next(c for c in allc if c["class_uid"] == 3002)
    af = " ".join(auth["key_fields"])
    check("Authentication 3002 shows status_id (outcome) + activity_id=1 Logon (CON-AUTH-1), category 3",
          "status_id" in af and "Logon" in af and auth["category_uid"] == 3)
    cloud = next(c for c in sp.classes_for("ocsf", ["cloudtrail"]) if c["class_uid"] == 6003)
    check("CloudTrail API Activity is 6003 / category 6 (CON-AUTH-1), NOT 3005", cloud["category_uid"] == 6)

    print()
    if _failures:
        print(f"\033[91m{len(_failures)} assertion(s) FAILED:\033[0m " + "; ".join(_failures))
        return 1
    print("\033[92mAll schema_preview assertions held.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
