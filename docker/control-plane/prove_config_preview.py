"""Proof that the Configuration raw->OCSF preview maps faithfully and flags the traps (PB-1).

config_preview.build_preview pairs a raw sample event to its OCSF gold field-by-field for the
Configuration value moment. This asserts the preview resolves real values on both sides, carries
the right class, and FLAGS the semantic traps (Zeek byte-direction, Sysmon actor/target) — so the
"watch the mapping get applied" screen can't quietly drop the one thing it exists to show.

Run:  python3 prove_config_preview.py     (exit 0 = preview faithful + traps flagged)
Pure stdlib; reads the sample library, no stack.
"""
from __future__ import annotations

import sys

import config_preview as cpv

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def main():
    print("\n=== Zeek conn.log -> Network Activity (4001) preview ===\n")
    z = cpv.build_preview("zeek")
    check("zeek preview builds without error", z.get("error") is None and z["rows"])
    check("zeek class_uid 4001", z["class_uid"] == 4001)
    check("every zeek row resolves a raw value and an OCSF value",
          all(r["raw_value"] is not None and r["ocsf_value"] is not None for r in z["rows"]))
    zmap = {r["ocsf_field"]: r for r in z["rows"]}
    check("the byte-direction trap is FLAGGED on orig_bytes -> bytes_out (canonical)",
          zmap["bytes_out"]["trap"] and zmap["bytes_out"]["raw_field"] == "orig_bytes")
    check("bytes_out value comes from orig_bytes (canonical direction in the preview)",
          str(zmap["bytes_out"]["ocsf_value"]) == str(z["raw"]["orig_bytes"]))
    check("the conn_state -> activity_id row is annotated as derived (not a plain copy)",
          "derived" in zmap["activity_id"]["note"].lower())

    print("\n=== Sysmon EventID-1 -> Process Activity (1007) preview ===\n")
    s = cpv.build_preview("sysmon")
    check("sysmon preview builds without error", s.get("error") is None and s["rows"])
    check("sysmon class_uid 1007, activity_id 1 (Launch)",
          s["class_uid"] == 1007 and s["activity_id"] == 1)
    smap = {r["ocsf_field"]: r for r in s["rows"]}
    check("the actor/target trap is FLAGGED on User -> user (actor.user)",
          smap["user"]["trap"] and smap["user"]["raw_field"] == "User")
    check("the new process maps to process_path (the target), parent to parent_path (the actor)",
          smap["process_path"]["raw_field"] == "Image" and smap["parent_path"]["raw_field"] == "ParentImage")
    check("default row is the office->powershell event (the demonstrative one)",
          "powershell" in str(s["ocsf"].get("process_path", "")).lower())

    print("\n=== exactly the intended traps are flagged; degrades honestly ===\n")
    check("each source flags >=1 trap and not every row (the flags are meaningful)",
          0 < sum(r["trap"] for r in z["rows"]) < len(z["rows"])
          and 0 < sum(r["trap"] for r in s["rows"]) < len(s["rows"]))
    bad = cpv.build_preview("nope")
    check("an unknown source returns an error structure, does not raise",
          bad.get("error") and bad["rows"] == [])

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mThe Configuration preview is faithful and flags the semantic traps.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
