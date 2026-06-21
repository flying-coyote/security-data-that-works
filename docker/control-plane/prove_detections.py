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
    # planted failed-auth burst (3002, status_id 2) for credential stuffing: 6 fails / 6 distinct users.
    auth = [{"class_uid": 3002, "category_uid": 3, "activity_id": 1, "status_id": 2,
             "src_ip": "203.0.113.99", "user": f"user{i}@acme.example"} for i in range(6)]
    auth += [{"class_uid": 3002, "category_uid": 3, "activity_id": 1, "status_id": 1,
              "src_ip": "10.0.5.5", "user": "alice@acme.example"} for _ in range(2)]   # benign successes
    # process activity (1007) for the cmd_line-keyword hunts; api activity (6003) for bulk-retrieval.
    proc = [{"class_uid": 1007, "device_hostname": "FIN-WS-07", "cmd_line": "vssadmin delete shadows /all /quiet"},
            {"class_uid": 1007, "device_hostname": "FIN-WS-07", "cmd_line": "procdump -ma lsass.exe out.dmp"},
            {"class_uid": 1007, "device_hostname": "HR-WS-02", "cmd_line": "outlook.exe /recycle"}]  # benign
    api = [{"class_uid": 6003, "actor_user": "svc_backup@acme.example", "bytes_out": 25000} for _ in range(3)]
    api += [{"class_uid": 6003, "actor_user": "analyst@acme.example", "bytes_out": 800} for _ in range(2)]
    records = landed + exfil + auth + proc + api

    print("\n=== the detections find the planted attacker ===\n")
    f = _by_id(det.scan(records))
    check("C2 beacon fires", f["c2_beacon"]["match_count"] >= 1)
    check("the beacon finding is the planted src->C2 (10.0.1.77 -> 203.0.113.66, 3 connections)",
          any("10.0.1.77" in k and "203.0.113.66" in k and m["connections"] == 3
              for k, m in f["c2_beacon"]["top"]))
    check("exfil fires on the planted high-egress source", f["exfil_egress"]["match_count"] >= 1)
    check("the exfil finding is 10.0.1.200 with total_bytes_out 15000",
          any("10.0.1.200" in k and m["total_bytes_out"] == 15000 for k, m in f["exfil_egress"]["top"]))
    check("credential stuffing fires on the failed-auth burst", f["credential_stuffing"]["match_count"] >= 1)
    check("the cred-stuffing finding is 203.0.113.99 with 6 failed attempts across 6 distinct users",
          any("203.0.113.99" in k and m["failed_attempts"] == 6 and m["distinct_users"] == 6
              for k, m in f["credential_stuffing"]["top"]))
    check("cred-stuffing surfaces a COUNT of distinct users, never a username (no '@' in the finding)",
          all("@" not in k and all(isinstance(v, int) for v in m.values())
              for k, m in f["credential_stuffing"]["top"]))
    check("findings carry the ATT&CK technique", f["c2_beacon"]["technique"] == "T1071"
          and f["exfil_egress"]["technique"] == "T1048" and f["credential_stuffing"]["technique"] == "T1110")

    print("\n=== PG-2 hunt library: the new OCSF-class hunts fire (DR-grounded) ===\n")
    check("shadow-copy deletion (T1490) fires on FIN-WS-07 via cmd_line 'vssadmin delete shadows' (count 1)",
          any("FIN-WS-07" in k and m["executions"] == 1 for k, m in f["shadow_copy_deletion"]["top"]))
    check("LSASS access (T1003.001) fires on FIN-WS-07 via cmd_line 'lsass'",
          any("FIN-WS-07" in k for k, m in f["lsass_credential_access"]["top"]))
    check("API bulk retrieval (T1530) fires on svc_backup (3 x 25000 = 75000 total_bytes)",
          any("svc_backup" in k and m["total_bytes"] == 75000 for k, m in f["api_bulk_retrieval"]["top"]))
    check("the cmd_line is MATCHED, never surfaced — no finding key carries vssadmin/procdump/lsass/shadows",
          all(all(s not in k for s in ("vssadmin", "procdump", "lsass", "delete shadows"))
              for fid in ("shadow_copy_deletion", "lsass_credential_access") for k, _m in f[fid]["top"]))
    check("benign process (HR-WS-02 outlook) does NOT fire either cmd_line hunt",
          all("HR-WS-02" not in k for fid in ("shadow_copy_deletion", "lsass_credential_access")
              for k, _m in f[fid]["top"]))
    check("benign low-volume API user does NOT fire bulk-retrieval",
          all("analyst@" not in k for k, _m in f["api_bulk_retrieval"]["top"]))
    check("every hunt in the library carries an ATT&CK tactic", all(d.get("tactic") for d in det.DETECTIONS))

    print("\n=== aggregate-safe invariant: a finding is (bounded key, numeric measures) — never a row ===\n")
    for fid, finding in f.items():
        for key, m in finding["top"]:
            check(f"{fid}: the grouping key is a string (a bounded key, not a record)", isinstance(key, str))
            check(f"{fid}: every measure is numeric (a count/sum/avg, not a field value)",
                  all(isinstance(v, numbers.Number) and not isinstance(v, bool) for v in m.values()))
            check(f"{fid}: the finding exposes ONLY the declared measures (no leaked record fields)",
                  set(m) == set(dict(det.DETECTIONS[[d['id'] for d in det.DETECTIONS].index(fid)]["measures"])))

    # attacker-controlled src_ip with control chars, a markdown code-span breakout, and an HTML payload —
    # the finding key is rendered through mo.md() (markdown + raw HTML), so it must come out inert.
    nasty = [{"class_uid": 4001, "src_ip": "10.9.9.9\n\x00`</code><img src=x onerror=alert(1)>",
              "dst_ip": "203.0.113.66", "bytes_out": 80, "bytes_in": 100} for _ in range(3)]
    nkeys = [k for k, _m in _by_id(det.scan(records + nasty))["c2_beacon"]["top"]]
    check("control chars stripped from the finding key (\\n, \\x00)",
          all("\n" not in k and "\x00" not in k for k in nkeys))
    check("the markdown code-span backtick is stripped (no breakout)", all("`" not in k for k in nkeys))
    check("HTML is escaped, not raw — no live <img and no unescaped '<' reaches the render",
          all("<img" not in k and "<" not in k for k in nkeys))
    check("the payload is rendered inert (escaped &lt; present where '<' was)",
          any("&lt;" in k for k in nkeys))

    print("\n=== safety is STRUCTURAL: scan/to_sql reject a row-leaking (free-text group) spec ===\n")
    leaky = {"id": "leaky", "title": "x", "technique": "T0", "table": "network_activity",
             "where": [("class_uid", "=", 4001)], "group": ("cmd_line",),
             "measures": {"n": ("count", None)}, "having": [("n", ">=", 1)], "rank": "n"}
    try:
        det.scan([{"class_uid": 4001, "cmd_line": "secret raw value"}], [leaky])
        check("scan() REJECTS a spec grouping on a free-text field (would leak rows)", False)
    except ValueError:
        check("scan() REJECTS a spec grouping on a free-text field (would leak rows)", True)
    try:
        det.to_sql(leaky, "t")
        check("to_sql() REJECTS the same leaky spec", False)
    except ValueError:
        check("to_sql() REJECTS the same leaky spec", True)
    check("a None/absent group value is coerced, not joined-on-None (no crash)",
          isinstance(det.scan([{"class_uid": 4001, "src_ip": None, "dst_ip": None, "bytes_out": 80}] * 3), list))

    print("\n=== non-vacuous: a benign-only table fires nothing ===\n")
    benign = [{"class_uid": 4001, "activity_id": 2, "src_ip": "10.0.0.5", "dst_ip": "10.0.0.6",
               "dst_port": 443, "bytes_out": 4000, "bytes_in": 8000}]
    fb = _by_id(det.scan(benign))
    check("benign single connection -> beacon does NOT fire", fb["c2_beacon"]["match_count"] == 0)
    check("benign low-volume -> exfil does NOT fire", fb["exfil_egress"]["match_count"] == 0)
    check("below-threshold failed logins (4 < 5) -> cred-stuffing does NOT fire",
          _by_id(det.scan([{"class_uid": 3002, "status_id": 2, "src_ip": "10.0.5.6", "user": f"u{i}"}
                           for i in range(4)]))["credential_stuffing"]["match_count"] == 0)
    check("successful logins (status_id 1) -> cred-stuffing does NOT fire (rides the failed status_id)",
          _by_id(det.scan([{"class_uid": 3002, "status_id": 1, "src_ip": "10.0.5.7", "user": f"u{i}"}
                           for i in range(10)]))["credential_stuffing"]["match_count"] == 0)
    check("empty input -> no findings, no crash", all(x["match_count"] == 0 for x in det.scan([])))

    print("\n=== to_sql emits the GROUP BY/HAVING query for the live path ===\n")
    sql = det.to_sql(det.DETECTIONS[0], "ocsf.network_activity")
    check("to_sql is a GROUP BY ... HAVING aggregate over the named table",
          "GROUP BY src_ip, dst_ip" in sql and "HAVING" in sql and "ocsf.network_activity" in sql
          and "count(*)" in sql and "ORDER BY" in sql)

    print("\n=== PG-2: the 'contains' predicate + the library catalog ===\n")
    _shadow = next(d for d in det.DETECTIONS if d["id"] == "shadow_copy_deletion")
    sql_p = det.to_sql(_shadow, "ocsf.process_activity")
    check("a cmd_line 'contains' hunt compiles to a LIKE predicate (not an invalid 'contains' token)",
          "LIKE" in sql_p and "vssadmin delete shadows" in sql_p and "contains" not in sql_p)
    cat = det.library_catalog()
    check("library_catalog lists every hunt with technique + tactic + OCSF class",
          len(cat) == len(det.DETECTIONS) and all(h["technique"] and h["tactic"] and h["class_uid"] for h in cat))

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mDetections find the planted attacker and leak nothing — aggregate-safe.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
