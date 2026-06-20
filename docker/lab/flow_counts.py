"""Flow-reconciliation count helper — land OCSF on stdin into Iceberg and report per-class
ingested + landed counts as one JSON line.

The route tier emits OCSF NDJSON; this reuses promote.py's land idiom (drop+recreate
`ocsf.authentication`, keeping the Authentication class_uid 3002 records the silver stage
keeps) and reports the per-class counts at the two hops the console's flow_reconcile needs:
`ingested` = what the router produced, by class_uid, BEFORE the silver filter; `landed` =
what survived into the table, by class_uid, counted through the catalog (not a catalog-less
icebergS3 read, which can serve a stale snapshot). A class the router emits but the silver
stage drops shows up as ingested > landed — the silent class-drop the flow gate exists to
catch. Prints exactly one JSON line and nothing else on stdout; no detection (promote.py's job).

Runs inside the lab container:  ... | docker compose exec -T lab python /lab/flow_counts.py
"""
import collections
import json
import os
import sys

import pyarrow as pa
from pyiceberg.catalog.rest import RestCatalog

REST = os.environ.get("ICEBERG_REST_URI", "http://iceberg-rest:8181")
S3 = os.environ.get("S3_ENDPOINT", "http://minio:9000")
AK = os.environ.get("AWS_ACCESS_KEY_ID", "moar")
SK = os.environ.get("AWS_SECRET_ACCESS_KEY", "moar-dev-secret")

ingested = collections.Counter()
recs = []
for line in sys.stdin:
    line = line.strip()
    if not line:
        continue
    try:
        o = json.loads(line)
    except ValueError:
        continue  # skip log noise; only OCSF JSON counts
    cu = o.get("class_uid")
    if cu is None:
        continue
    ingested[int(cu)] += 1
    if cu == 3002:  # the silver stage keeps Authentication (mirrors promote.py's filter)
        recs.append(o)

landed = collections.Counter()
if recs:
    tbl = pa.table({
        "class_uid": pa.array([3002] * len(recs), pa.int32()),
        "class_name": pa.array([o.get("class_name") or "Authentication" for o in recs]),
        "activity_id": pa.array([int(o.get("activity_id") or 0) for o in recs], pa.int32()),
        "user": pa.array([o.get("user") for o in recs]),
        "src_ip": pa.array([o.get("src_ip") for o in recs]),
        "status": pa.array([o.get("status") for o in recs]),
    })
    cat = RestCatalog("moar", **{
        "uri": REST, "warehouse": "s3://warehouse/", "s3.endpoint": S3,
        "s3.access-key-id": AK, "s3.secret-access-key": SK,
        "s3.path-style-access": "true", "s3.region": "us-east-1"})
    cat.create_namespace_if_not_exists("ocsf")
    ident = "ocsf.authentication"
    try:
        cat.drop_table(ident)  # drop+recreate so landed == this run's append exactly
    except Exception:  # noqa: BLE001
        pass
    it = cat.create_table(ident, schema=tbl.schema)
    it.append(tbl)
    arrow = it.scan().to_arrow()  # count through the catalog — avoids the icebergS3 stale-snapshot trap
    for cu in arrow["class_uid"].to_pylist():
        landed[int(cu)] += 1

print(json.dumps({"ingested": {str(k): v for k, v in ingested.items()},
                  "landed": {str(k): v for k, v in landed.items()}}))
