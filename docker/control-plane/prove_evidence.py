"""Proof that the Evidence Runner is honest: real exit codes, bounded/sanitized
output, a clean Docker-absent degrade, and timeout handling.

Part 1 drives `evidence_runner.run_verb` against a controllable fake `./moar` (so we
can force exit 0, exit 1, a flood of output, ANSI/control chars, and a hang) — no
real stack is ever invoked. Part 2 points the runner at the REAL ./moar with
`available=False` to prove every registry verb degrades to `blocked` without
executing anything. Exit 0 = every assertion held.
"""
from __future__ import annotations

import os
import stat
import sys
import tempfile

import evidence_runner as er

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []
NOW = "2026-06-18T00:00:00Z"


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


FAKE_MOAR = r"""#!/usr/bin/env bash
case "$1" in
  verify)
    # 50 noisy lines + ANSI + a control char, then succeed — exercises bounding/sanitize.
    for i in $(seq 1 50); do printf '\033[32mrow %d\twith\ttabs\x07\033[0m\n' "$i"; done
    echo "VERDICT: all engines agree"; exit 0;;
  correlate) echo "VERDICT: mismatch across sources"; exit 1;;
  commit-tax) sleep 5; exit 0;;
  *) echo "unknown"; exit 2;;
esac
"""


def main():
    d = tempfile.mkdtemp(prefix="moar_evidence_proof_")
    try:
        moar = os.path.join(d, "moar")
        with open(moar, "w") as f:
            f.write(FAKE_MOAR)
        os.chmod(moar, os.stat(moar).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

        print("\n=== Part 1 — runner logic against a controllable fake ./moar ===\n")

        # Docker absent → blocked, and nothing is executed.
        r_block = er.run_verb("verify", docker_dir=d, available=False, now_iso=NOW)
        check("docker absent → status blocked", r_block["status"] == "blocked")
        check("blocked result carries the hypothesis tag", r_block["hypothesis"] != "?")
        check("blocked result is Tier-B stamped + dated", r_block["tier"].startswith("Tier B") and r_block["ran_at"] == NOW)

        # Exit 0 → pass; output is bounded and sanitized.
        r_pass = er.run_verb("verify", docker_dir=d, available=True, now_iso=NOW)
        check("exit 0 → status pass", r_pass["status"] == "pass" and r_pass["exit_code"] == 0)
        check("summary bounded to <= 15 lines", len(r_pass["summary"].splitlines()) <= 16)  # 15 + possible "…"
        check("summary keeps the trailing verdict", "VERDICT: all engines agree" in r_pass["summary"])
        check("ANSI escapes stripped", "\x1b[" not in r_pass["summary"])
        check("control chars (BEL \\x07) stripped", "\x07" not in r_pass["summary"])

        # Exit non-zero → fail (never a pass).
        r_fail = er.run_verb("correlate", docker_dir=d, available=True, now_iso=NOW)
        check("exit 1 → status fail", r_fail["status"] == "fail" and r_fail["exit_code"] == 1)

        # Timeout → error (never a pass), via the 5s-sleeping verb with a 1s timeout.
        r_to = er.run_verb("commit-tax", docker_dir=d, available=True, now_iso=NOW, timeout=1)
        check("timeout → status error", r_to["status"] == "error" and "timed out" in r_to["summary"])

        # Unknown verb → error.
        r_unk = er.run_verb("does-not-exist", docker_dir=d, available=True, now_iso=NOW)
        check("unknown verb → status error", r_unk["status"] == "error")

        # Aggregate.
        agg = er.summarize([r_pass, r_fail, r_block, r_to])
        check("summarize counts pass/fail/blocked", agg["passing"] == 1 and agg["failing"] == 1 and agg["blocked"] == 1)

        print("\n=== Part 2 — real ./moar, Docker absent: every verb degrades to blocked ===\n")
        real_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # docker/
        has_real = os.path.exists(os.path.join(real_dir, "moar"))
        check("real ./moar present", has_real)
        if has_real:
            blocked = [er.run_verb(v["verb"], docker_dir=real_dir, available=False, now_iso=NOW) for v in er.VERBS]
            check(f"all {len(er.VERBS)} registry verbs degrade to blocked (no execution)",
                  all(r["status"] == "blocked" for r in blocked))
            check("every verb carries a hypothesis/claim tag",
                  all(r["hypothesis"] and r["hypothesis"] != "?" for r in blocked))

        print()
        if _failures:
            print(f"\033[91m{len(_failures)} assertion(s) FAILED:\033[0m " + "; ".join(_failures))
            return 1
        print("\033[92mAll assertions held — the Evidence Runner reports honestly and never fakes a pass.\033[0m")
        return 0
    finally:
        import shutil
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
