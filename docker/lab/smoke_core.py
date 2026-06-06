"""Core-tier smoke: prove the open lakehouse round-trips an OCSF table over REST catalog + S3.

Writes a small OCSF Network Activity (class_uid 4001) batch into an Iceberg table via the REST catalog
(data lands in MinIO/S3), then reads it back and asserts the count + a filtered count. If this passes, the
L+I+embedded-E foundation works: object store + table format + catalog + DuckDB/pyiceberg, all open.

Runs both in the lab container (service-name endpoints) and from the host (localhost), via env defaults.
"""
import os
import sys

import pyarrow as pa
from pyiceberg.catalog.rest import RestCatalog

REST = os.environ.get("ICEBERG_REST_URI", "http://localhost:8181")
S3 = os.environ.get("S3_ENDPOINT", "http://localhost:9000")
AK = os.environ.get("AWS_ACCESS_KEY_ID", "moar")
SK = os.environ.get("AWS_SECRET_ACCESS_KEY", "moar-dev-secret")

cat = RestCatalog("moar", **{
    "uri": REST, "warehouse": "s3://warehouse/",
    "s3.endpoint": S3, "s3.access-key-id": AK, "s3.secret-access-key": SK,
    "s3.path-style-access": "true", "s3.region": "us-east-1",
})

# a tiny OCSF Network Activity (4001) batch — the columns a SOC filters/aggregates on
tbl = pa.table({
    "time": pa.array([1767225600000 + i for i in range(1000)], pa.int64()),
    "class_uid": pa.array([4001] * 1000, pa.int32()),
    "activity_id": pa.array([(i % 6) + 1 for i in range(1000)], pa.int32()),
    "src_ip": pa.array([f"10.0.{i % 256}.{(i * 7) % 256}" for i in range(1000)]),
    "dst_port": pa.array([[80, 443, 22, 53, 3389, 445, 8080, 3306][i % 8] for i in range(1000)], pa.int32()),
    "bytes_out": pa.array([(i * 131) % 1_000_000 for i in range(1000)], pa.int64()),
})

cat.create_namespace_if_not_exists("ocsf")
ident = "ocsf.network_activity"
try:
    cat.drop_table(ident)
except Exception:
    pass
it = cat.create_table(ident, schema=tbl.schema)
it.append(tbl)

scanned = it.scan().to_arrow()
total = scanned.num_rows
rdp = scanned.filter(pa.compute.equal(scanned["dst_port"], 3389)).num_rows
truth_rdp = sum(1 for i in range(1000) if [80, 443, 22, 53, 3389, 445, 8080, 3306][i % 8] == 3389)

ok = total == 1000 and rdp == truth_rdp
print(f"  catalog: {REST}  store: {S3}")
print(f"  wrote+read ocsf.network_activity: {total} rows; dst_port=3389 -> {rdp} (truth {truth_rdp})")
print(f"  CORE ROUND-TRIP: {'OK' if ok else 'FAILED'}")
sys.exit(0 if ok else 1)
