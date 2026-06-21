"""Proof that the detections find the planted attacker, stay aggregate-safe, and don't false-fire (PD).

detections.scan() runs the declarative detection specs over landed OCSF records. This seeds a synthetic
network_activity table (the corrected Zeek 4001 gold + a planted high-egress source) and asserts: the C2
beacon is found, the exfil aggregate fires, a benign-only table fires NOTHING (non-vacuous), and — the
security-critical part — every finding is an AGGREGATE (bounded key + numeric measures), never a raw
record or an unsanitized high-cardinality value, even when a source field carries injection bytes.

Run:  python3 prove_detections.py     (exit 0 = found the attacker, leaked nothing)
Pure stdlib; reads the sample gold, no stack.
"""
from __future__ import annotations

import json
import numbers
import os
import sys

import detections as det

HERE = os.path.dirname(os.path.abspath(__file__))
ZEEK_GOLD = os.path.normpath(os.path.join(HERE, "..", "config", "samples", "zeek_conn.ocsf.expected.ndjson"))

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def _by_id(findings):
    return {f["id"]: f for f in findings}


def main():
    landed = [json.loads(line) for line in open(ZEEK_GOLD) if line.strip()]
    # plant a high-egress exfil source (3 flows, 5000 bytes_out each = 15000 outbound).
    exfil = [{"class_uid": 4001, "activity_id": 6, "src_ip": "10.0.1.200", "dst_ip": "198.51.100.9",
              "dst_port": 443, "bytes_in": 100, "bytes_out": 5000, "packets_out": 50, "packets_in": 5}
             for _ in range(3)]
    records = landed + exfil

    print("\n=== the detections find the planted attacker ===\n")
    f = _by_id(det.scan(records))
    check("C2 beacon fires", f["c2_beacon"]["match_count"] >= 1)
    check("the beacon finding is the planted src->C2 (10.0.1.77 -> 203.0.113.66, 3 connections)",
          any("10.0.1.77" in k and "203.0.113.66" in k and m["connections"] == 3
              for k, m in f["c2_beacon"]["top"]))
    check("exfil fires on the planted high-egress source", f["exfil_egress"]["match_count"] >= 1)
    check("the exfil finding is 10.0.1.200 with total_bytes_out 15000",
          any("10.0.1.200" in k and m["total_bytes_out"] == 15000 for k, m in f["exfil_egress"]["top"]))
    check("findings carry the ATT&CK technique", f["c2_beacon"]["technique"] == "T1071"
          and f["exfil_egress"]["technique"] == "T1048")

    print("\n=== aggregate-safe invariant: a finding is (bounded key, numeric measures) — never a row ===\n")
    for fid, finding in f.items():
        for key, m in finding["top"]:
            check(f"{fid}: the grouping key is a string (a bounded key, not a record)", isinstance(key, str))
            check(f"{fid}: every measure is numeric (a count/sum/avg, not a field value)",
                  all(isinstance(v, numbers.Number) and not isinstance(v, bool) for v in m.values()))
            check(f"{fid}: the finding exposes ONLY the declared measures (no leaked record fields)",
                  set(m) == set(dict(det.DETECTIONS[[d['id'] for d in det.DETECTIONS].index(fid)]["measures"])))

    # injection bytes in an attacker-controlled src_ip must be stripped by the bounded key.
    nasty = [{"class_uid": 4001, "src_ip": "10.9.9.9\n\x00; DROP TABLE", "dst_ip": "203.0.113.66",
              "bytes_out": 80, "bytes_in": 100} for _ in range(3)]
    fn = _by_id(det.scan(records + nasty))
    check("injection bytes in src_ip are stripped from the finding key (control-char-safe)",
          all("\n" not in k and "\x00" not in k for k, _m in fn["c2_beacon"]["top"]))

    print("\n=== non-vacuous: a benign-only table fires nothing ===\n")
    benign = [{"class_uid": 4001, "activity_id": 2, "src_ip": "10.0.0.5", "dst_ip": "10.0.0.6",
               "dst_port": 443, "bytes_out": 4000, "bytes_in": 8000}]
    fb = _by_id(det.scan(benign))
    check("benign single connection -> beacon does NOT fire", fb["c2_beacon"]["match_count"] == 0)
    check("benign low-volume -> exfil does NOT fire", fb["exfil_egress"]["match_count"] == 0)
    check("empty input -> no findings, no crash", all(x["match_count"] == 0 for x in det.scan([])))

    print("\n=== to_sql emits the GROUP BY/HAVING query for the live path ===\n")
    sql = det.to_sql(det.DETECTIONS[0], "ocsf.network_activity")
    check("to_sql is a GROUP BY ... HAVING aggregate over the named table",
          "GROUP BY src_ip, dst_ip" in sql and "HAVING" in sql and "ocsf.network_activity" in sql
          and "count(*)" in sql and "ORDER BY" in sql)

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mDetections find the planted attacker and leak nothing — aggregate-safe.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
