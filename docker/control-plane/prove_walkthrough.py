"""Proof for walkthrough — the guided golden-path walkthrough (Phase F, PF-1). Pure; no stack.

Covers the step catalog (the demo spine, in order), step_status over present/absent signals, the
assemble/progress shape, and the honesty guard that matters most: with NO live signal, the
measurement-backed steps (land / gate / analyze) read WAITING, never a fabricated LIVE — and progress
counts only genuinely-demonstrated (LIVE) value moments.

Run:  python3 prove_walkthrough.py
"""
from __future__ import annotations

import sys

import walkthrough as wt

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def main():
    print("\n=== the demo spine (step catalog, pure) ===\n")
    keys = [s["key"] for s in wt.STEPS]
    check("six steps in golden-path order (setup→config→land→gate→analyze→migrate)",
          keys == ["setup", "config", "land", "gate", "analyze", "migrate"])
    check("every step names its tab + value moment + what-you'll-see",
          all(s.get("tab") and s.get("value") and s.get("see") for s in wt.STEPS))
    check("steps are numbered 1..6", [s["n"] for s in wt.STEPS] == [1, 2, 3, 4, 5, 6])

    print("\n=== honesty guard: NO signal -> never a fabricated 'live' ===\n")
    for k in ["land", "gate", "analyze"]:
        st, _ = wt.step_status(k, {})
        check(f"'{k}' with no signal -> WAITING (not LIVE)", st == wt.WAITING)
    check("'setup'/'config' with no signal -> READY (available without a run)",
          wt.step_status("setup", {})[0] == wt.READY and wt.step_status("config", {})[0] == wt.READY)
    check("empty/None signals never raise", isinstance(wt.assemble(None), list) and len(wt.assemble({})) == 6)

    print("\n=== step_status lights up only on a real signal ===\n")
    check("land + landed counts -> LIVE with the per-class counts in the note",
          wt.step_status("land", {"landed": {"3002": 8}}) == (wt.LIVE, "landed 3002:8"))
    check("gate green + answer-equality pass -> LIVE, notes engines agree",
          wt.step_status("gate", {"gate_green": True, "answer_equality": "pass"})
          == (wt.LIVE, "gate GREEN · engines agree on the count"))
    check("gate green WITHOUT answer-equality -> still LIVE but no false 'engines agree'",
          wt.step_status("gate", {"gate_green": True})[0] == wt.LIVE
          and "engines agree" not in wt.step_status("gate", {"gate_green": True})[1])
    check("gate unmeasured (amber) -> WAITING", wt.step_status("gate", {"gate_unmeasured": True})[0] == wt.WAITING)
    check("analyze + recorded detection pass -> LIVE; stale -> STALE; absent -> WAITING",
          wt.step_status("analyze", {"detections": "pass"})[0] == wt.LIVE
          and wt.step_status("analyze", {"detections": "stale"})[0] == wt.STALE
          and wt.step_status("analyze", {})[0] == wt.WAITING)
    check("migrate + answer-equality pass -> LIVE; absent -> READY (reversibility is a property)",
          wt.step_status("migrate", {"answer_equality": "pass"})[0] == wt.LIVE
          and wt.step_status("migrate", {})[0] == wt.READY)

    print("\n=== assemble + progress ===\n")
    cold = wt.assemble({})
    check("a cold console (no signals) -> 0 LIVE value moments demonstrated", wt.progress(cold) == (0, 6))
    check("assemble carries status + note + a chip per step",
          all(st.get("status") and "note" in st and st.get("chip") for st in cold))
    warm = wt.assemble({"spec_saved": True, "schema": "ocsf", "landed": {"3002": 8},
                        "gate_green": True, "answer_equality": "pass", "detections": "pass"})
    done, total = wt.progress(warm)
    check("a warm console -> land+gate+analyze+migrate demonstrated LIVE (4 of 6)", (done, total) == (4, 6))
    check("progress counts ONLY live (setup/config are READY, not counted)",
          done == sum(1 for st in warm if st["status"] == wt.LIVE))

    print()
    if _failures:
        print(f"\033[91m{len(_failures)} assertion(s) FAILED:\033[0m " + "; ".join(_failures))
        return 1
    print("\033[92mAll walkthrough assertions held.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
