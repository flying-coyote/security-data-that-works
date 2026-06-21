"""Proof that the source sample library maps each raw event to OCSF correctly (PA-2).

The sample library under ../config/samples/ pairs a synthetic RAW event file with an
OCSF-expected gold file, per source. The gold doubles as the landed-table contract and as
the round-trip's `expected`. This harness re-derives the expected OCSF from each raw event
*independently* (its own mapping logic, grounded on schema.ocsf.io v1.8.0) and asserts the
gold matches — so a gold authored with the byte-direction backwards, or the Sysmon
actor/target swapped, FAILS here rather than silently shipping a wrong contract. The two
semantic traps are asserted as traps: a name-based mapper that got them wrong would not pass.

Sources covered (this iteration): Zeek conn.log -> Network Activity (4001); Sysmon EventID-1
-> Process Activity (1007). CloudTrail/Okta Authentication (3002) waits on the status_id
convention decision (the existing Okta path conflates success/failure into activity_id; OCSF
carries it in status_id).

Run:  python3 prove_sample_library.py     (exit 0 = every gold faithful to its raw)
Pure stdlib; reads the sample files, no stack, no network.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.normpath(os.path.join(HERE, "..", "config", "samples"))

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


# --- independent mapping logic (the expectation the gold is checked against) ---

_PROTO_NUM = {"tcp": 6, "udp": 17, "icmp": 1}
# Zeek conn_state -> OCSF 4001 activity_id, the CANONICAL case table from ocsf/examples
# (mappings/markdown/Zeek/v1.4.0/conn_log/README.md conditional table): a completed/closed
# connection is Close (2); S0 -> Fail (4); REJ -> Refuse (5); OTH/S1/S2/S3/else -> Traffic (6).
_CONN_STATE_ACTIVITY = {"SF": 2, "RSTO": 2, "RSTR": 2, "RSTRH": 2, "SH": 2, "SHR": 2,
                        "S0": 4, "REJ": 5, "OTH": 6, "S1": 6, "S2": 6, "S3": 6}


def _read_zeek_tsv(path):
    """Parse a Zeek conn.log TSV: #fields gives the column order, data rows are tab-split."""
    fields, rows = [], []
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("#fields"):
                fields = line.split("\t")[1:]
            elif line.startswith("#") or not line.strip():
                continue
            else:
                rows.append(dict(zip(fields, line.split("\t"))))
    return rows


def _read_ndjson(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def main():
    print("\n=== Zeek conn.log -> OCSF Network Activity (4001) ===\n")
    raws = _read_zeek_tsv(os.path.join(SAMPLES, "zeek_conn.sample.tsv"))
    gold = _read_ndjson(os.path.join(SAMPLES, "zeek_conn.ocsf.expected.ndjson"))
    check("one gold record per raw conn.log row", len(raws) == len(gold) and len(raws) == 8)
    direction_trap_rows = 0
    for i, (r, g) in enumerate(zip(raws, gold)):
        ob, rb = int(r["orig_bytes"]), int(r["resp_bytes"])
        # CANONICAL direction (ocsf/examples Zeek conn_log): traffic is from src_endpoint's view, and
        # orig_h -> src_endpoint, so the originator's SENT bytes are bytes_OUT and the responder's are
        # bytes_IN. bytes_in <- resp_bytes, bytes_out <- orig_bytes.
        ok_dir = g["bytes_in"] == rb and g["bytes_out"] == ob
        check(f"row {i} byte direction (canonical): bytes_in=resp({rb}) bytes_out=orig({ob})", ok_dir)
        if ob != rb:
            direction_trap_rows += 1
            # the perspective-inversion trap: a confused map would put orig_bytes in bytes_in.
            check(f"row {i} inversion avoided: bytes_in != orig_bytes ({g['bytes_in']} != {ob})",
                  g["bytes_in"] != ob)
        check(f"row {i} class_uid 4001", g["class_uid"] == 4001)
        check(f"row {i} activity_id derived from conn_state '{r['conn_state']}'",
              g["activity_id"] == _CONN_STATE_ACTIVITY.get(r["conn_state"], 6))
        check(f"row {i} endpoints src<-orig, dst<-resp",
              g["src_ip"] == r["id.orig_h"] and g["dst_ip"] == r["id.resp_h"]
              and g["src_port"] == int(r["id.orig_p"]) and g["dst_port"] == int(r["id.resp_p"]))
        check(f"row {i} protocol_num from proto '{r['proto']}'",
              g["protocol_num"] == _PROTO_NUM.get(r["proto"]))
        check(f"row {i} packets_in<-resp_pkts, packets_out<-orig_pkts",
              g["packets_in"] == int(r["resp_pkts"]) and g["packets_out"] == int(r["orig_pkts"]))
    check("the byte-direction trap is actually exercised (>=1 asymmetric row)", direction_trap_rows >= 1)
    check("the planted C2 beacon is present (rare dst 203.0.113.66, low bytes_OUT — small outbound check-in)",
          any(g["dst_ip"] == "203.0.113.66" and g["bytes_out"] < 100 for g in gold))
    check("conn_state derivation spans multiple activity_ids (not a constant)",
          len({g["activity_id"] for g in gold}) >= 3)

    print("\n=== Sysmon EventID-1 -> OCSF Process Activity (1007) ===\n")
    sraw = _read_ndjson(os.path.join(SAMPLES, "sysmon_process.sample.ndjson"))
    sgold = _read_ndjson(os.path.join(SAMPLES, "sysmon_process.ocsf.expected.ndjson"))
    check("one gold record per raw Sysmon event", len(sraw) == len(sgold) and len(sraw) == 5)
    for i, (r, g) in enumerate(zip(sraw, sgold)):
        check(f"row {i} class_uid 1007, activity_id 1 (Launch)",
              g["class_uid"] == 1007 and g["activity_id"] == 1)
        # The actor/target resolution: the NEW process is `process.*`; the parent/user is `actor.*`.
        check(f"row {i} the new process is `process` (process_path<-Image, pid<-ProcessId)",
              g["process_path"] == r["Image"] and g["process_pid"] == r["ProcessId"])
        check(f"row {i} the parent is the actor's process (parent_path<-ParentImage)",
              g["parent_path"] == r["ParentImage"] and g["parent_pid"] == r["ParentProcessId"])
        check(f"row {i} the launcher is the actor's user (user<-User '{r['User']}')",
              g["user"] == r["User"])
        # the actor/target trap: process and actor.process must NOT be the same field (no swap).
        check(f"row {i} actor/target NOT swapped: process_path != parent_path",
              g["process_path"] != g["parent_path"])
        check(f"row {i} process_name is the Image basename",
              g["process_name"] == r["Image"].replace("/", "\\").split("\\")[-1])
    check("the encoded-PowerShell red flag is present (office->powershell -enc)",
          any("powershell" in g["process_path"].lower() and "-enc" in g["cmd_line"].lower()
              and "winword" in g["parent_path"].lower() for g in sgold))

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mAll sample-library golds are faithful to their raw events — the traps are encoded.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
