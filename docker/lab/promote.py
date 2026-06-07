"""Pipeline silver+detect stage: promote route-tier OCSF Authentication into Iceberg, then detect over it.

This is the hop the route tier didn't have — it reads OCSF Authentication records (NDJSON on stdin, produced by
the route tier normalizing raw Okta) and lands them in the `ocsf.authentication` Iceberg table, then runs a
detection over the landed table. End to end: raw Okta -> route (OCSF) -> lakehouse (Iceberg) -> detection.

The detection is a credential-stuffing / brute-force check: a source IP with >= 5 failed authentications. The
sample plants one (198.51.100.66, 6 failures); jdoe and svc are benign. Asserts the planted source is found and
no benign source trips it, so the whole chain is verified, not just that records moved.
"""
import json
import os
import sys

import duckdb
import pyarrow as pa
from pyiceberg.catalog.rest import RestCatalog

REST = os.environ.get("ICEBERG_REST_URI", "http://iceberg-rest:8181")
S3 = os.environ.get("S3_ENDPOINT", "http://minio:9000")
AK = os.environ.get("AWS_ACCESS_KEY_ID", "moar")
SK = os.environ.get("AWS_SECRET_ACCESS_KEY", "moar-dev-secret")
FAIL_THRESHOLD = 5

# 1. read the route tier's OCSF Authentication records off stdin (skip any non-JSON log lines)
recs = []
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        o = json.loads(line)
    except ValueError:
        continue
    if o.get("class_uid") == 3002:
        recs.append(o)

if not recs:
    print("  promote: no OCSF Authentication records on stdin (did the route tier run?)")
    sys.exit(1)

tbl = pa.table({
    "class_uid": pa.array([3002] * len(recs), pa.int32()),
    "class_name": pa.array([o.get("class_name") or "Authentication" for o in recs]),
    "activity_id": pa.array([int(o.get("activity_id") or 0) for o in recs], pa.int32()),
    "user": pa.array([o.get("user") for o in recs]),
    "src_ip": pa.array([o.get("src_ip") for o in recs]),
    "status": pa.array([o.get("status") for o in recs]),
})

# 2. land it in the ocsf.authentication Iceberg table (the bronze->silver promotion)
cat = RestCatalog("moar", **{
    "uri": REST, "warehouse": "s3://warehouse/", "s3.endpoint": S3,
    "s3.access-key-id": AK, "s3.secret-access-key": SK,
    "s3.path-style-access": "true", "s3.region": "us-east-1"})
cat.create_namespace_if_not_exists("ocsf")
ident = "ocsf.authentication"
try:
    cat.drop_table(ident)
except Exception:  # noqa: BLE001
    pass
it = cat.create_table(ident, schema=tbl.schema)
it.append(tbl)
landed = it.scan().to_arrow()
print(f"  promote: {landed.num_rows} OCSF Authentication rows -> {ident} "
      f"({sum(1 for s in landed['status'].to_pylist() if s == 'FAILURE')} failures)")

# 3. detection over the landed lakehouse table: a src_ip with >= threshold failed auths (brute force)
con = duckdb.connect()
con.register("auth", landed)
hits = con.execute(
    f"SELECT src_ip, count(*) AS fails FROM auth WHERE status='FAILURE' "
    f"GROUP BY src_ip HAVING count(*) >= {FAIL_THRESHOLD} ORDER BY fails DESC").fetchall()
for ip, n in hits:
    print(f"  detect: brute-force source {ip} — {n} failed auths (>= {FAIL_THRESHOLD})")

ok = len(hits) == 1 and hits[0][0] == "198.51.100.66"
print(f"  PIPELINE (raw Okta -> route -> Iceberg -> detection): {'OK' if ok else 'FAILED'}")
sys.exit(0 if ok else 1)
