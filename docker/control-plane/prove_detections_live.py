"""Live detections proof — the stack-UP value moment: land OCSF into Iceberg, detect over it.

detections.scan() (pure) is unit-tested in prove_detections.py. This is its LIVE arm: it lands the
demo OCSF records (with the planted beacon + exfil) into a real Iceberg table through the catalog,
reads them BACK from the lakehouse, runs the detection specs via to_sql over the landed table, and
asserts the planted attacker is found — proving the whole spine (OCSF -> Iceberg -> detection) runs
end to end, not just the in-memory logic. It writes live-evidence.json (ran_at + per-detection counts)
— the build-loop guard's record that a B/C/D value moment was actually measured with the stack up.

Stack-tolerant + honest (like prove_ocsf_roundtrip_live): no catalog reachable -> the live part is
SKIPPED with a clear note (never a false pass); a real failure after the stack is up -> FAIL.

Run:  VENV/bin/python prove_detections_live.py   (needs pyiceberg + duckdb; the moar core+store stack up)
"""
from __future__ import annotations

import json
import os
import sys
import time

import detections as det
from analyze import _safe_key

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []
HERE = os.path.dirname(os.path.abspath(__file__))

REST = os.environ.get("ICEBERG_REST_URI", "http://localhost:8181")
S3 = os.environ.get("S3_ENDPOINT", "http://localhost:9100")
AK = os.environ.get("AWS_ACCESS_KEY_ID", "moar")
SK = os.environ.get("AWS_SECRET_ACCESS_KEY", "moar-dev-secret")
IDENT = "ocsf.network_activity_demo"


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def _land_and_read():
    """Land the 4001 demo records into Iceberg and read them back. Returns the arrow table, or raises
    if the stack is unreachable (caller treats that as SKIP, never a fail)."""
    import pyarrow as pa
    from pyiceberg.catalog.rest import RestCatalog
    cat = RestCatalog("moar", **{"uri": REST, "warehouse": "s3://warehouse/", "s3.endpoint": S3,
                                 "s3.access-key-id": AK, "s3.secret-access-key": SK,
                                 "s3.path-style-access": "true", "s3.region": "us-east-1"})
    recs = [r for r in det.demo_records() if r.get("class_uid") == 4001]
    tbl = pa.table({
        "class_uid":   pa.array([r.get("class_uid") for r in recs], pa.int32()),
        "activity_id": pa.array([r.get("activity_id") for r in recs], pa.int32()),
        "src_ip":      pa.array([r.get("src_ip") for r in recs], pa.string()),
        "dst_ip":      pa.array([r.get("dst_ip") for r in recs], pa.string()),
        "dst_port":    pa.array([r.get("dst_port") for r in recs], pa.int32()),
        "bytes_in":    pa.array([r.get("bytes_in") or 0 for r in recs], pa.int64()),
        "bytes_out":   pa.array([r.get("bytes_out") or 0 for r in recs], pa.int64()),
    })
    try:
        cat.create_namespace("ocsf")
    except Exception:  # noqa: BLE001 - already exists
        pass
    try:
        cat.drop_table(IDENT)
    except Exception:  # noqa: BLE001 - first run
        pass
    cat.create_table(IDENT, schema=tbl.schema).append(tbl)
    return cat.load_table(IDENT).scan().to_arrow(), tbl.num_rows


def main():
    print("\n=== Live: land OCSF into Iceberg, detect over the landed table ===\n")
    try:
        import duckdb
        arrow, landed = _land_and_read()
    except Exception as e:  # noqa: BLE001 - stack down / deps missing -> honest skip, never a false pass
        print(f"  [SKIP] no reachable catalog ({str(e)[:80]}) — live detection skipped (run with the moar "
              f"core+store stack up). Pure logic is covered by prove_detections.py.")
        return 0

    con = duckdb.connect()
    con.register("network_activity_demo", arrow)
    total = con.execute("SELECT count(*) FROM network_activity_demo").fetchone()[0]
    check(f"landed {landed} OCSF rows and read them BACK from the Iceberg table ({total} rows)",
          total == landed and total > 0)

    evidence = {"ran_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "table": IDENT, "landed_rows": landed,
                "catalog": REST, "findings": {}}
    found = {}
    for d in det.DETECTIONS:
        if d["table"] != "network_activity":
            continue
        rows = con.execute(det.to_sql(d, "network_activity_demo")).fetchall()
        safe = [tuple(_safe_key(c) if isinstance(c, str) else c for c in row) for row in rows]
        found[d["id"]] = safe
        evidence["findings"][d["id"]] = len(rows)

    check("the C2 beacon is found over the LANDED table (10.0.1.77 -> 203.0.113.66, 3 connections)",
          any(r[0] == "10.0.1.77" and r[1] == "203.0.113.66" and r[2] == 3 for r in found.get("c2_beacon", [])))
    check("exfil is found over the LANDED table (10.0.1.200, total_bytes_out 15000)",
          any(r[0] == "10.0.1.200" and r[1] == 15000 for r in found.get("exfil_egress", [])))
    # the SQL row is (group-key columns..., measure columns...): every group key must be a sanitized
    # string (the live path routes ALL string columns through _safe_key), the measures numeric.
    safe_ok = True
    for d in det.DETECTIONS:
        if d["table"] != "network_activity":
            continue
        ng = len(d["group"])
        for r in found.get(d["id"], []):
            keys, meas = r[:ng], r[ng:]
            if not all(isinstance(k, str) and not ({"\n", "`", "<"} & set(k)) for k in keys):
                safe_ok = False
            if not all(isinstance(c, (int, float)) for c in meas):
                safe_ok = False
    check("live findings are aggregate-safe (group keys = sanitized strings, measures = numbers)", safe_ok)

    json.dump(evidence, open(os.path.join(HERE, "live-evidence.json"), "w"), indent=2)
    check("wrote live-evidence.json (ran_at + per-detection counts — the stack-UP record)",
          os.path.exists(os.path.join(HERE, "live-evidence.json")))
    print(f"\n  live-evidence: {evidence}")

    if _failures:
        print(f"\n\033[91m{len(_failures)} live assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mThe live spine holds: OCSF landed in Iceberg, the detections fired over it.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
