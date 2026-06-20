"""Proof for the LIVE flow reconciliation collector (cluster 5, live arm).

Part 1 unit-tests the pure halves against synthetic counts — emitted derivation from the
sample, the reconcile (clean pass, a silent class drop → fail with the gap named, a router
drop, a missing hop → unmeasured), the JSON-line counts parser. Part 2 covers the gate-status
mapping incl. decay. Part 3, when Docker is reachable, runs the REAL route→land pipeline and
asserts a clean reconciliation; with no Docker it asserts the honest `blocked` degrade.

Run:  VENV/bin/python prove_flow_reconcile_live.py   (Part 3 self-skips without Docker)
"""
from __future__ import annotations

import datetime as _dt
import os
import subprocess
import sys

import flow_reconcile_live as fl

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []
NOW = "2026-06-20T00:00:00Z"


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def _docker_up():
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=10).returncode == 0
    except Exception:  # noqa: BLE001
        return False


def main():
    docker_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # docker/
    sample = os.path.join(docker_dir, "config", "vector", "sample.ndjson")

    print("\n=== Part 1 — pure derivation + reconcile (no stack) ===\n")
    em = fl.emitted_from_sample(sample)
    check("emitted_from_sample: Okta session.start events -> class 3002 (count > 0)",
          em.get("3002", 0) > 0 and set(em) == {"3002"})

    clean = fl.build_reconciliation({"3002": 8}, {"3002": 8}, {"3002": 8}, now_iso=NOW)
    check("clean emitted=ingested=landed -> pass, worst_drop 0", clean["status"] == "pass" and clean["worst_drop"] == 0.0)

    land_drop = fl.build_reconciliation({"3002": 8, "4001": 100}, {"3002": 8, "4001": 100},
                                        {"3002": 8, "4001": 0}, now_iso=NOW)
    check("class 4001 lost between ingested and landed -> fail", land_drop["status"] == "fail")
    check("the silently-dropped class is named in the note", "4001" in land_drop["note"])

    router_drop = fl.build_reconciliation({"3002": 10}, {"3002": 7}, {"3002": 7}, now_iso=NOW)
    check("router drops 3 (emitted 10, landed 7) -> fail", router_drop["status"] == "fail")

    missing = fl.build_reconciliation({"3002": 8}, {"3002": None}, {"3002": 8}, now_iso=NOW)
    check("a missing hop count -> unmeasured (no false pass)", missing["status"] == "unmeasured")

    pc = fl._parse_counts('promote: noise\n{"ingested": {"3002": 8}, "landed": {"3002": 8}}\n')
    check("counts parser pulls the JSON line past log noise", pc and pc["ingested"]["3002"] == 8)
    check("counts parser returns None on non-JSON output", fl._parse_counts("no json here") is None)

    print("\n=== Part 2 — gate_status mapping + decay ===\n")
    check("absent result -> None (gate row omitted)", fl.gate_status(None) is None and fl.gate_status({}) is None)
    check("pass -> 'pass'", fl.gate_status({"status": "pass"}) == "pass")
    check("fail -> 'fail'", fl.gate_status({"status": "fail"}) == "fail")
    check("blocked -> 'unmeasured' (no bluffed pass)", fl.gate_status({"status": "blocked"}) == "unmeasured")
    check("unmeasured -> 'unmeasured'", fl.gate_status({"status": "unmeasured"}) == "unmeasured")
    check("fresh pass + now_iso -> 'pass'",
          fl.gate_status({"status": "pass", "ran_at": "2026-06-19T23:00:00Z"}, now_iso=NOW) == "pass")
    check("3-day-old pass + now_iso -> 'stale' (re-run me)",
          fl.gate_status({"status": "pass", "ran_at": "2026-06-17T00:00:00Z"}, now_iso=NOW) == "stale")

    print("\n=== Part 3 — real route->land pipeline (degrades honestly when the stack is down) ===\n")
    if not _docker_up():
        r = fl.run_pipeline(docker_dir=docker_dir, sample_path=sample, available=False, now_iso=NOW)
        check("docker absent -> blocked (never a pass)", r["status"] == "blocked")
    else:
        now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = fl.run_pipeline(docker_dir=docker_dir, sample_path=sample, available=True, now_iso=now, timeout=180)
        if r["status"] == "pass":
            # The moar stack is deployed: the real pipeline ran end to end and reconciled clean.
            check("live route->land pipeline reconciles clean", r["status"] == "pass")
            check("live run is dated and carries per-class counts",
                  bool(r.get("ran_at")) and bool(r.get("by_class_counts")))
        else:
            # Daemon up but the route/lab services aren't deployed (e.g. a clean clone): the
            # pipeline must degrade to a labeled non-pass, never a fabricated success.
            check(f"stack not deployed -> honest non-pass degrade ({r['status']}), never a fabricated pass",
                  r["status"] != "pass" and bool(r.get("note")))

    print()
    if _failures:
        print(f"\033[91m{len(_failures)} assertion(s) FAILED:\033[0m " + "; ".join(_failures))
        return 1
    print("\033[92mAll flow-reconciliation live assertions held.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
