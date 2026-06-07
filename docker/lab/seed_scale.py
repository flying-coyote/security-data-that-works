"""Seed ocsf.network_activity_bench (N rows) for the workload x engine latency matrix (./moar bench).

A separate, larger table so the matrix has real work to differentiate engines on, without clobbering the
1000-row ocsf.network_activity the verify/detection/healthcheck demos rely on. Deterministic (seeded), so the
table — and therefore the answers each engine returns — is reproducible run to run; only the latency varies.
Pure-Python generation (the lab image carries pyarrow + pyiceberg, not numpy).
"""
import os
import random
import sys

import pyarrow as pa
from pyiceberg.catalog.rest import RestCatalog

N = int(os.environ.get("BENCH_N", "1000000"))
REST = os.environ.get("ICEBERG_REST_URI", "http://iceberg-rest:8181")
S3 = os.environ.get("S3_ENDPOINT", "http://minio:9000")
AK = os.environ.get("AWS_ACCESS_KEY_ID", "moar")
SK = os.environ.get("AWS_SECRET_ACCESS_KEY", "moar-dev-secret")

rng = random.Random(20260601)
ports, weights = [80, 443, 22, 53, 3389, 445, 8080, 3306, 1433, 8443], [20, 25, 8, 10, 5, 7, 6, 4, 3, 2]
tbl = pa.table({
    "time": pa.array(sorted(1767225600000 + rng.randrange(0, 86_400_000) for _ in range(N)), pa.int64()),
    "class_uid": pa.array([4001] * N, pa.int32()),
    "activity_id": pa.array([rng.randint(1, 6) for _ in range(N)], pa.int32()),
    "src_ip": pa.array([f"10.{rng.randrange(256)}.{rng.randrange(256)}.{rng.randrange(256)}" for _ in range(N)]),
    "dst_port": pa.array(rng.choices(ports, weights=weights, k=N), pa.int32()),
    "bytes_out": pa.array([rng.randrange(5_000_000) for _ in range(N)], pa.int64()),
})

cat = RestCatalog("moar", **{
    "uri": REST, "warehouse": "s3://warehouse/", "s3.endpoint": S3,
    "s3.access-key-id": AK, "s3.secret-access-key": SK,
    "s3.path-style-access": "true", "s3.region": "us-east-1"})
cat.create_namespace_if_not_exists("ocsf")
ident = "ocsf.network_activity_bench"
try:
    cat.drop_table(ident)
except Exception:  # noqa: BLE001
    pass
# Purge the table's object-store prefix after dropping the catalog entry. drop_table leaves the old
# metadata.json + data files behind, and a catalog-LESS reader (ClickHouse's icebergS3 path function) then
# resolves a STALE metadata file after a reseed — a silent 10x undercount the answer-equality gate catches.
# Catalog-mediated engines are unaffected, but purging keeps the catalog-less reader honest too.
try:
    from pyarrow.fs import S3FileSystem
    _fs = S3FileSystem(access_key=AK, secret_key=SK, endpoint_override=S3.split("://")[-1],
                       scheme=S3.split("://")[0], region="us-east-1")
    _fs.delete_dir_contents("warehouse/ocsf/network_activity_bench", missing_dir_ok=True)
except Exception:  # noqa: BLE001
    pass
it = cat.create_table(ident, schema=tbl.schema)
it.append(tbl)
print(f"  seeded {ident}: {it.scan().to_arrow().num_rows:,} rows", file=sys.stderr)
print(N)
