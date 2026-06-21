"""Proof for live_evidence — the build-loop guard's evidence recorder (CONSOLE-LOOP-STATE §3/§5).

Pure: every assertion runs against a temp file, never the committed live-evidence.json and never a
stack. Asserts the read-merge-write keeps arms independent (recording one never clobbers another),
the legacy single-object detections format migrates once into its arm, a corrupt/absent file loads
as {} (never raises), and the on-disk form is stable (sorted keys, trailing newline).

Run:  python3 prove_live_evidence.py   (pure stdlib — no venv, no stack)
"""
from __future__ import annotations

import json
import os
import sys
import tempfile

import live_evidence as le

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def main():
    print("\n=== live_evidence: read-merge-write + honesty ===\n")
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "live-evidence.json")

        check("absent file -> load() is {} (never raises)", le.load(p) == {})

        d = le.record_arm("detections", {"ran_at": "2026-06-21T00:00:00", "findings": {"c2_beacon": 1}}, path=p)
        check("record_arm writes the arm and returns the full dict", d.get("detections", {}).get("findings") == {"c2_beacon": 1})
        check("the arm round-trips through load()", le.load(p)["detections"]["findings"]["c2_beacon"] == 1)

        le.record_arm("answer_equality", {"ran_at": "2026-06-21T00:01:00", "status": "pass"}, path=p)
        both = le.load(p)
        check("recording a second arm does NOT clobber the first",
              "detections" in both and "answer_equality" in both)
        check("the second arm carries its own payload", both["answer_equality"]["status"] == "pass")

        # re-recording an arm replaces only that arm.
        le.record_arm("detections", {"ran_at": "2026-06-21T00:02:00", "findings": {"exfil_egress": 2}}, path=p)
        after = le.load(p)
        check("re-recording an arm replaces only that arm", after["detections"]["findings"] == {"exfil_egress": 2})
        check("re-recording leaves the other arm intact", after["answer_equality"]["status"] == "pass")

        # on-disk form is stable: sorted keys + trailing newline (clean diffs).
        raw = open(p).read()
        check("on-disk JSON ends in a newline", raw.endswith("\n"))
        check("on-disk keys are sorted (stable diffs)",
              list(json.loads(raw).keys()) == sorted(json.loads(raw).keys()))

    # legacy single-object detections format migrates once into its arm.
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "live-evidence.json")
        json.dump({"ran_at": "2026-06-20T22:51:12", "table": "ocsf.network_activity_demo",
                   "landed_rows": 11, "findings": {"c2_beacon": 1, "exfil_egress": 1}}, open(p, "w"))
        migrated = le.load(p)
        check("legacy top-level detections object migrates into the `detections` arm",
              "detections" in migrated and migrated["detections"]["landed_rows"] == 11)
        check("migration does not invent other arms", set(migrated) == {"detections"})
        # recording another arm over a legacy file keeps the migrated detections arm.
        le.record_arm("flow_reconcile", {"ran_at": "x", "status": "pass"}, path=p)
        check("recording over a legacy file preserves the migrated detections arm",
              le.load(p)["detections"]["landed_rows"] == 11 and "flow_reconcile" in le.load(p))

    # corrupt file -> {} (fail-closed, never raises).
    with tempfile.TemporaryDirectory() as tmp:
        p = os.path.join(tmp, "live-evidence.json")
        open(p, "w").write("{not json")
        check("corrupt file -> load() is {} (never raises)", le.load(p) == {})

    print()
    if _failures:
        print(f"\033[91m{len(_failures)} assertion(s) FAILED:\033[0m " + "; ".join(_failures))
        return 1
    print("\033[92mAll live_evidence assertions held.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
