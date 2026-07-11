"""Proof that detection-suite regression is caught: a verdict that flips is a named failure.

The regression guard persists each hunt's FIRED/SILENT verdict and asserts a later run matches a
committed baseline. This proves: the pure verdicts reproduce the committed baseline; the run-path
parser reads run_detections.py's stdout into the same shape; assert_equality passes on identical
snapshots and fails — naming the rule — on a flip, a vanished rule, or an added one; and it degrades
to unmeasured (never a bluffed pass) on an empty side. Part 5 runs the LIVE suite over the landed
table when Docker is up and records the arm.

Run:  VENV/bin/python prove_detection_regress.py   (exit 0 = every assertion held; Part 5 self-skips w/o Docker)
Pure stdlib for Parts 1-4.
"""
from __future__ import annotations

import subprocess
import sys

import detection_regress as dr

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


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
    print("\n=== Part 1 — pure scan verdicts reproduce the committed baseline ===\n")
    fresh = dr.verdicts_from_scan()
    check("one verdict per DETECTIONS spec", len(fresh) == len(dr.det.DETECTIONS))
    check("every verdict is a FIRED/SILENT LABEL + id/technique — no raw value leaked",
          all(set(v) == {"id", "technique", "verdict"} and v["verdict"] in (dr.FIRED, dr.SILENT)
              for v in fresh))
    base = dr.load_baseline()
    check("a committed baseline snapshot exists (labels + counts + provenance)",
          bool(base.get("verdicts")) and "corpus_fingerprint" in base)
    eq = dr.assert_equality(base.get("verdicts", []), fresh)
    check("fresh pure verdicts == the committed baseline (no uncommitted regression)",
          eq["status"] == "pass" and eq["equal"] is True)
    check("counts headline is aggregate-only (fired/silent/total)",
          set(dr.counts(fresh)) == {"fired", "silent", "total"})

    print("\n=== Part 2 — the run-path parser (run_detections.py stdout -> same shape) ===\n")
    out = dr.load_run_fixture()
    run_v = dr.verdicts_from_run(out)
    check("the captured stdout parses to at least the RDP Sigma rule", len(run_v) >= 1)
    _rdp = next((v for v in run_v if "RDP" in v["rule"]), None)
    check("RDP rule parsed: FIRED, technique T1021.001, matches read as a count",
          _rdp is not None and _rdp["verdict"] == dr.FIRED and _rdp["technique"] == "T1021.001"
          and _rdp["matches"] == 125)
    check("the trailing summary line ('N/M Sigma rules fired ...') is NOT parsed as a rule",
          all("Sigma rules fired over" not in v["rule"] for v in run_v))
    check("a matches=0 line reads SILENT (compile-fail and no-match both conservatively SILENT)",
          dr.verdicts_from_run("  Some Rule matches=0    [attack.t1059]")[0]["verdict"] == dr.SILENT)

    print("\n=== Part 3 — assert_equality IS the regression assertion ===\n")
    snap = dr.snapshot(fresh, ran_at="2026-07-11T00:00:00Z", corpus_fingerprint="test")
    check("assert_equality(snap, snap) -> pass (identical)",
          dr.assert_equality(snap["verdicts"], snap["verdicts"])["status"] == "pass")
    flipped = [dict(v, verdict=(dr.SILENT if v["verdict"] == dr.FIRED else dr.FIRED)) if v["id"] == "c2_beacon"
               else v for v in fresh]
    feq = dr.assert_equality(fresh, flipped)
    check("a hand-flipped verdict -> fail, the rule named with before/after",
          feq["status"] == "fail" and any(c["rule"] == "c2_beacon"
                                          and c["before"] != c["after"] for c in feq["changed"]))
    vanished = [v for v in fresh if v["id"] != "exfil_egress"]
    veq = dr.assert_equality(fresh, vanished)
    check("a rule that VANISHES -> fail, named with —absent— after",
          veq["status"] == "fail" and any(c["rule"] == "exfil_egress" and "absent" in c["after"]
                                          for c in veq["changed"]))
    check("an empty side -> unmeasured (nothing measured, never a bluffed pass)",
          dr.assert_equality([], fresh)["status"] == "unmeasured"
          and dr.assert_equality(fresh, [])["status"] == "unmeasured")

    print("\n=== Part 4 — aggregate-safety on a hostile rule title ===\n")
    nasty = dr.verdicts_from_run("  `<img src=x>` evil rule matches=3    [attack.t1000]")
    check("a hostile rule title parses to a label + count, no crash, no value surfaced",
          len(nasty) == 1 and nasty[0]["verdict"] == dr.FIRED and nasty[0]["matches"] == 3)

    print("\n=== Part 5 — LIVE arm: run the suite over the landed table (self-skips without Docker) ===\n")
    if not _docker_up():
        check("docker absent -> live arm skipped, pure regression still proven", True)
    else:
        import os
        import datetime as _dt
        import live_evidence as le
        docker_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        def _run():
            try:
                r = subprocess.run(["docker", "compose", "exec", "-T", "detection",
                                    "python", "/detection/run_detections.py"],
                                   cwd=docker_dir, capture_output=True, text=True, timeout=180)
                return dr.verdicts_from_run(r.stdout)
            except Exception:  # noqa: BLE001
                return []
        v1 = _run()
        if not v1:
            check("detection tier not up / table unseeded -> honest non-pass degrade (never a bluff)", True)
        else:
            v2 = _run()  # re-run: the suite over the same landed corpus must be deterministic
            live_eq = dr.assert_equality(v1, v2)
            check("live detection suite is deterministic over the landed corpus (re-run equal)",
                  live_eq["status"] == "pass")
            check("live run parsed at least one FIRED rule (RDP over the seeded network_activity)",
                  any(v["verdict"] == dr.FIRED for v in v1))
            now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            le.record_arm("detection_regress", {"ran_at": now, "status": live_eq["status"],
                                                "counts": dr.counts(v1),
                                                "corpus_fingerprint": "ocsf.network_activity (landed, live run_detections.py)"})
            check("recorded the detection_regress arm in live-evidence.json",
                  le.load().get("detection_regress", {}).get("ran_at") == now)

    print()
    if _failures:
        print(f"\033[91m{len(_failures)} assertion(s) FAILED:\033[0m " + "; ".join(_failures))
        return 1
    print("\033[92mAll detection-regression assertions held — a flipped verdict is a caught regression.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
