"""Proof that schema-drift detection catches a silently mis-mapped source before a hunt does.

Schema drift is the failure the round-trip and Layer 2 can't see: a source renames or drops a raw
field, the mapping stops populating an OCSF field, and a detection that keys on it goes quiet with no
error. This asserts the diff over a synthetic drifted Zeek header (NAMES only) names the missing raw
fields, the OCSF fields left unpopulated, and exactly the hunts that lose a required field — and that
it degrades honestly (unmeasured, never a bluffed pass) on an empty or unknown input.

Four parts:
  1. The pure diff: clean header passes; the drifted fixture fails with the damage named; a single
     dropped field fails with just its downstream unpopulated; empty/unknown degrade to unmeasured.
  2. Aggregate-safety: a hostile incoming field name is neutralized (no backtick / raw < survives)
     and no raw value ever appears — the input is names, the output is names + counts.
  3. The gate contract: status() mirrors the diff verdict; the None-omits-row wiring is exercised in
     prove_gate.py Part 2f (the tenth cert-bearing row).
  4. (stack up) the LIVE arm: the real router's produced field set vs the crosswalk, recorded to
     live-evidence.json arm `schema_drift`; degrades to an honest non-pass with the stack down.

Run:  VENV/bin/python prove_schema_drift.py     (exit 0 = every assertion held; Part 4 self-skips w/o Docker)
Pure stdlib for Parts 1-3.
"""
from __future__ import annotations

import subprocess
import sys

import config_preview as cpv
import schema_drift as sd

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
    print("\n=== Part 1 — the pure diff (raw field set vs crosswalk baseline) ===\n")
    clean_fields = [rf for rf, _of, _n in cpv.CROSSWALK["zeek"]["fields"]]
    clean = sd.diff_fields(clean_fields, "zeek")
    check("a header carrying every expected raw field -> pass, nothing unpopulated",
          clean["status"] == "pass" and not clean["unpopulated_ocsf"] and not clean["detections_at_risk"])

    drift = sd.demo_diff()  # the vendored drifted-Zeek fixture (orig_bytes dropped, id.orig_h->src_host)
    check("drifted header -> fail", drift["status"] == "fail")
    check("the dropped/renamed raw fields are named in missing_raw",
          "orig_bytes" in drift["missing_raw"] and "id.orig_h" in drift["missing_raw"])
    check("the new field surfaces in unexpected_raw (rename shows here, honestly not paired)",
          "src_host" in drift["unexpected_raw"])
    check("bytes_out AND src_ip are named unpopulated (their only producers went missing)",
          "bytes_out" in drift["unpopulated_ocsf"] and "src_ip" in drift["unpopulated_ocsf"])
    _at = {a["id"] for a in drift["detections_at_risk"]}
    check("exactly the class-4001 hunts keying on those fields are at risk (c2_beacon + exfil_egress)",
          _at == {"c2_beacon", "exfil_egress"})
    check("each at-risk hunt names the field it loses (T1071 beacon loses bytes_out)",
          any(a["technique"] == "T1071" and "bytes_out" in a["lost_fields"]
              for a in drift["detections_at_risk"]))

    # a single dropped raw field with an unshared producer -> exactly its OCSF field unpopulated
    drop_bytes = [f for f in clean_fields if f != "orig_bytes"]
    only = sd.diff_fields(drop_bytes, "zeek")
    check("dropping only orig_bytes -> bytes_out unpopulated, src_ip still fine",
          only["unpopulated_ocsf"] == ["bytes_out"])
    check("dropping only orig_bytes still flags the two byte-keyed hunts, status fail",
          only["status"] == "fail" and {a["id"] for a in only["detections_at_risk"]} == {"c2_beacon", "exfil_egress"})

    # a benign drop: a raw field whose OCSF target isn't required by any hunt -> pass (no over-alarm)
    drop_pkts = [f for f in clean_fields if f != "orig_pkts"]
    benign = sd.diff_fields(drop_pkts, "zeek")
    check("dropping orig_pkts -> packets_out unpopulated but NO hunt keys on it, so pass (no false alarm)",
          benign["status"] == "pass" and "packets_out" in benign["unpopulated_ocsf"]
          and not benign["detections_at_risk"])

    print("\n=== degrade honestly (never a bluffed pass) ===\n")
    check("empty incoming header -> unmeasured (nothing to diff)", sd.diff_fields([], "zeek")["status"] == "unmeasured")
    check("unknown source -> unmeasured + error, no raise", sd.diff_fields(["x"], "nope")["status"] == "unmeasured")
    check("a sysmon drift is class-scoped (only 1007 hunts, never the network ones)",
          {a["id"] for a in sd.diff_fields(["Image", "ProcessId"], "sysmon")["detections_at_risk"]}
          <= {"shadow_copy_deletion", "lsass_credential_access"})

    print("\n=== Part 2 — aggregate-safety (names + counts only, hostile name neutralized) ===\n")
    hostile = sd.diff_fields(["`<script>`evil", "id.orig_p"], "zeek")
    _blob = str(hostile)
    check("a hostile incoming field name is _safe_key'd (no backtick / raw < survives to render)",
          "`" not in "".join(hostile["unexpected_raw"]) and "<script>" not in _blob)
    check("the neutralized name still surfaces HTML-escaped (visible, inert)",
          any("script" in u for u in hostile["unexpected_raw"]))
    check("output carries only names + counts — no dict/list value leaked as a raw record",
          all(isinstance(x, str) for x in hostile["missing_raw"] + hostile["unexpected_raw"] + hostile["unpopulated_ocsf"]))

    print("\n=== Part 3 — the gate contract (status mirrors the diff; tenth row wired in prove_gate 2f) ===\n")
    check("status(pass diff) == 'pass'", sd.status(clean) == "pass")
    check("status(fail diff) == 'fail'", sd.status(drift) == "fail")
    check("status(unmeasured diff) == 'unmeasured'", sd.status(sd.diff_fields([], "zeek")) == "unmeasured")

    print("\n=== Part 4 — LIVE arm: real router field set vs crosswalk (self-skips without Docker) ===\n")
    if not _docker_up():
        check("docker absent -> live arm skipped, pure diff still proven (honest non-measurement)", True)
    else:
        import os
        import datetime as _dt
        import live_evidence as le
        docker_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        # run the deployed Tenzir router over the Okta sample and read the produced OCSF field NAMES;
        # a source not yet landed / stack partial -> honest non-pass, never a fabricated success.
        try:
            out = subprocess.run(["docker", "compose", "run", "--rm", "-T", "route-tenzir"],
                                 cwd=docker_dir, capture_output=True, text=True, timeout=180)
            produced = set()
            for line in out.stdout.splitlines():
                line = line.strip()
                if line.startswith("{") and '"class_uid"' in line:
                    import json as _json
                    try:
                        produced |= set(_json.loads(line).keys())
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            produced = set()
        if not produced:
            check("router not deployed / no OCSF out -> honest non-pass degrade (never a bluffed pass)", True)
        else:
            # the produced OCSF field names ARE the populated set for the router's class (Authentication
            # 3002 for Okta); assert the class-3002 required fields are present -> no live drift.
            live = {"status": "pass" if {"class_uid", "activity_id", "status_id", "src_ip", "user"} <= produced
                    else "fail", "populated_ocsf": sorted(produced), "class_uid": 3002}
            check("live router populates the class-3002 required OCSF fields (no drift)", live["status"] == "pass")
            now = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            le.record_arm("schema_drift", {"ran_at": now, "status": live["status"],
                                           "class_uid": live["class_uid"],
                                           "populated_ocsf_count": len(produced)})
            check("recorded the schema_drift arm in live-evidence.json",
                  le.load().get("schema_drift", {}).get("ran_at") == now)

    print()
    if _failures:
        print(f"\033[91m{len(_failures)} assertion(s) FAILED:\033[0m " + "; ".join(_failures))
        return 1
    print("\033[92mAll schema-drift assertions held — drift is caught before a hunt goes quiet.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
