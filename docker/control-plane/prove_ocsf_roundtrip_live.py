"""Proof for the LIVE OCSF round-trip check (cluster 5, live arm).

Part 1 unit-tests the pure halves against synthetic produced records — the contract
deriver, the JSON-line parser, the pairing/validation, count-mismatch and dropped-field
fails — with NO stack. Part 2 covers the gate-status mapping including decay. Part 3, when
Docker is reachable, runs the REAL deployed Tenzir router and asserts the live transform is
faithful to the contract; with no Docker it asserts the honest `blocked` degrade.

Run:  VENV/bin/python prove_ocsf_roundtrip_live.py   (or python3 — Part 3 self-skips live)
"""
from __future__ import annotations

import datetime as _dt
import os
import subprocess
import sys

import ocsf_roundtrip_live as rl

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []
NOW = "2026-06-20T00:00:00Z"

RAW_OK = {"outcome": {"result": "SUCCESS"}, "actor": {"alternateId": "jdoe@acme.example"},
          "client": {"ipAddress": "10.10.1.21"}}
RAW_FAIL = {"outcome": {"result": "FAILURE"}, "actor": {"alternateId": "svc@acme.example"},
            "client": {"ipAddress": "203.0.113.7"}}


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
    print("\n=== Part 1 — pure contract + validation (no stack) ===\n")
    exp = rl.expected_ocsf(RAW_OK)
    check("contract: SUCCESS -> class 3002, activity 1, user + src_ip carried",
          exp["class_uid"] == 3002 and exp["activity_id"] == 1
          and exp["user"] == "jdoe@acme.example" and exp["src_ip"] == "10.10.1.21")
    check("contract: FAILURE -> activity 2", rl.expected_ocsf(RAW_FAIL)["activity_id"] == 2)

    parsed = rl.parse_ocsf_lines('noise line\n{"class_uid":3002,"user":"a"}\nlog: hi\n'
                                 '{"bad json\n{"class_uid":3002,"user":"b"}\n[1,2]')
    check("parser keeps only valid JSON objects, drops noise / bad-json / non-dict",
          len(parsed) == 2 and parsed[0]["user"] == "a" and parsed[1]["user"] == "b")

    faithful = [rl.expected_ocsf(RAW_OK), rl.expected_ocsf(RAW_FAIL)]
    v = rl.validate_against_contract([RAW_OK, RAW_FAIL], faithful, now_iso=NOW)
    check("faithful produced -> pass", v["status"] == "pass")

    wrong_class = [dict(rl.expected_ocsf(RAW_OK), class_uid=9999), rl.expected_ocsf(RAW_FAIL)]
    vb = rl.validate_against_contract([RAW_OK, RAW_FAIL], wrong_class, now_iso=NOW)
    check("wrong class_uid -> fail (meaning, not shape)", vb["status"] == "fail" and vb.get("fail_count") == 1)

    drop_ip = [{"class_uid": 3002, "activity_id": 1, "user": "jdoe@acme.example", "status": "SUCCESS"}]
    vd = rl.validate_against_contract([RAW_OK], drop_ip, now_iso=NOW)
    check("transform drops src_ip -> fail (missing required field)", vd["status"] == "fail")

    vc = rl.validate_against_contract([RAW_OK, RAW_FAIL], [rl.expected_ocsf(RAW_OK)], now_iso=NOW)
    check("count mismatch (1 produced for 2 raw) -> fail", vc["status"] == "fail")

    ve = rl.validate_against_contract([RAW_OK], [], now_iso=NOW)
    check("no produced records -> unmeasured (no false pass)", ve["status"] == "unmeasured")

    print("\n=== Part 2 — gate_status mapping + decay ===\n")
    check("absent result -> None (gate row omitted)", rl.gate_status(None) is None and rl.gate_status({}) is None)
    check("pass -> 'pass'", rl.gate_status({"status": "pass"}) == "pass")
    check("fail -> 'fail'", rl.gate_status({"status": "fail"}) == "fail")
    check("blocked -> 'unmeasured' (no bluffed pass)", rl.gate_status({"status": "blocked"}) == "unmeasured")
    check("error -> 'unmeasured' (no bluffed pass)", rl.gate_status({"status": "error"}) == "unmeasured")
    check("unmeasured -> 'unmeasured'", rl.gate_status({"status": "unmeasured"}) == "unmeasured")
    check("fresh pass + now_iso -> 'pass'",
          rl.gate_status({"status": "pass", "ran_at": "2026-06-19T23:00:00Z"}, now_iso=NOW) == "pass")
    check("3-day-old pass + now_iso -> 'stale' (re-run me)",
          rl.gate_status({"status": "pass", "ran_at": "2026-06-17T00:00:00Z"}, now_iso=NOW) == "stale")
    check("undatable pass + now_iso -> 'stale' (fail-closed)",
          rl.gate_status({"status": "pass"}, now_iso=NOW) == "stale")

    print("\n=== Part 3 — real Tenzir router (if Docker up) ===\n")
    docker_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # docker/
    sample = os.path.join(docker_dir, "config", "vector", "sample.ndjson")
    if not _docker_up():
        r = rl.run_roundtrip(docker_dir=docker_dir, sample_path=sample, available=False, now_iso=NOW)
        check("docker absent -> blocked (never a pass)", r["status"] == "blocked")
    else:
        now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        r = rl.run_roundtrip(docker_dir=docker_dir, sample_path=sample, available=True, now_iso=now)
        check(f"live tenzir transform faithful to the OCSF contract (status={r['status']})", r["status"] == "pass")
        check("live run is dated and carries per-event results", bool(r.get("ran_at")) and bool(r.get("events")))

    print()
    if _failures:
        print(f"\033[91m{len(_failures)} assertion(s) FAILED:\033[0m " + "; ".join(_failures))
        return 1
    print("\033[92mAll OCSF round-trip live assertions held.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
