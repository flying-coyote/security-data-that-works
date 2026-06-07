"""L-tier store swap check: the SAME OCSF batch written to and read from two object stores, same answer.

The object store is interchangeable under the open read contract — MinIO and SeaweedFS both speak S3, so the
same Iceberg/Parquet data and the same query return the same answer regardless of which one is underneath.
This writes the identical OCSF Network Activity batch lab/smoke_core.py uses (1000 rows, dst_port=3389 -> 125)
to each store via DuckDB's httpfs and reads it back. One DuckDB connection per store, because DuckDB routes an
`s3://` path by the matching secret's scope, not by endpoint, so two endpoints for the same bucket name need
separate connections. Prints a `store <name> ... -> N` line per store for `./moar swap-store` to compare.
"""
import os
import sys

import duckdb
import pyarrow as pa

AK = os.environ.get("AWS_ACCESS_KEY_ID", "moar")
SK = os.environ.get("AWS_SECRET_ACCESS_KEY", "moar-dev-secret")
STORES = {"minio": "minio:9000", "seaweedfs": "seaweedfs:8333"}   # in-network host:port per store

# the IDENTICAL OCSF Network Activity batch lab/smoke_core.py writes (so the answer is comparable by construction)
ports = [80, 443, 22, 53, 3389, 445, 8080, 3306]
tbl = pa.table({
    "time": pa.array([1767225600000 + i for i in range(1000)], pa.int64()),
    "class_uid": pa.array([4001] * 1000, pa.int32()),
    "activity_id": pa.array([(i % 6) + 1 for i in range(1000)], pa.int32()),
    "src_ip": pa.array([f"10.0.{i % 256}.{(i * 7) % 256}" for i in range(1000)]),
    "dst_port": pa.array([ports[i % 8] for i in range(1000)], pa.int32()),
    "bytes_out": pa.array([(i * 131) % 1_000_000 for i in range(1000)], pa.int64()),
})
truth_rdp = sum(1 for i in range(1000) if ports[i % 8] == 3389)

results = {}
ok = True
for name, endpoint in STORES.items():
    try:
        con = duckdb.connect()
        con.execute("INSTALL httpfs; LOAD httpfs;")
        con.execute(f"""CREATE OR REPLACE SECRET s (TYPE s3, PROVIDER config, KEY_ID '{AK}', SECRET '{SK}',
                        REGION 'us-east-1', ENDPOINT '{endpoint}', URL_STYLE 'path', USE_SSL false)""")
        con.register("src", tbl)
        path = "s3://warehouse/storeswap/oa.parquet"
        con.execute(f"COPY src TO '{path}' (FORMAT parquet)")
        total = con.execute(f"SELECT count(*) FROM read_parquet('{path}')").fetchone()[0]
        rdp = con.execute(f"SELECT count(*) FROM read_parquet('{path}') WHERE dst_port = 3389").fetchone()[0]
        con.close()
        results[name] = (total, rdp)
        print(f"  store {name} (http://{endpoint}): {total} rows; dst_port=3389 -> {rdp} (truth {truth_rdp})")
        ok = ok and total == 1000 and rdp == truth_rdp
    except Exception as e:  # noqa: BLE001
        results[name] = ("ERR", str(e)[:80])
        print(f"  store {name} (http://{endpoint}): ERROR {type(e).__name__}: {str(e)[:80]}")
        ok = False

print(f"  STORE ROUND-TRIP: {'OK' if ok else 'FAILED'}")
sys.exit(0 if ok else 1)
