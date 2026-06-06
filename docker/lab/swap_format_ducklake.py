"""I-tier swap (format portability): write the SAME OCSF data as the Iceberg path into DuckLake, same answer.

DuckLake is not an Iceberg REST catalog — it keeps catalog metadata in a SQL database (here a local DuckDB
file) and data files in object storage (here the SAME MinIO bucket the Iceberg tables use). So this is a
*format-portability* claim, not a drop-in catalog swap like nessie/lakekeeper: the same logical OCSF batch,
written through a different table format, must return the identical answer. It runs inside the existing lab
container (DuckDB 1.5.3 + the ducklake extension) — no new service.

This writes the byte-for-byte same OCSF Network Activity (4001) batch as lab/smoke_core.py (the Iceberg path)
and prints the same `dst_port=3389 -> N` line, so `./moar swap-format` greps both and asserts they agree.
"""
import os
import sys

import duckdb
import pyarrow as pa

S3 = os.environ.get("S3_ENDPOINT", "http://localhost:9000")
AK = os.environ.get("AWS_ACCESS_KEY_ID", "moar")
SK = os.environ.get("AWS_SECRET_ACCESS_KEY", "moar-dev-secret")
endpoint = S3.split("://", 1)[-1]            # CREATE SECRET wants host:port, no scheme
use_ssl = "true" if S3.startswith("https://") else "false"

# the IDENTICAL OCSF Network Activity batch lab/smoke_core.py writes to Iceberg — same data, different format
ports = [80, 443, 22, 53, 3389, 445, 8080, 3306]
tbl = pa.table({
    "time": pa.array([1767225600000 + i for i in range(1000)], pa.int64()),
    "class_uid": pa.array([4001] * 1000, pa.int32()),
    "activity_id": pa.array([(i % 6) + 1 for i in range(1000)], pa.int32()),
    "src_ip": pa.array([f"10.0.{i % 256}.{(i * 7) % 256}" for i in range(1000)]),
    "dst_port": pa.array([ports[i % 8] for i in range(1000)], pa.int32()),
    "bytes_out": pa.array([(i * 131) % 1_000_000 for i in range(1000)], pa.int64()),
})

con = duckdb.connect()
con.execute("INSTALL ducklake; LOAD ducklake; INSTALL httpfs; LOAD httpfs;")
con.execute(f"""
    CREATE OR REPLACE SECRET minio (
        TYPE s3, PROVIDER config, KEY_ID '{AK}', SECRET '{SK}',
        REGION 'us-east-1', ENDPOINT '{endpoint}', URL_STYLE 'path', USE_SSL {use_ssl})
""")
# local DuckDB-file catalog, data files on S3; inlining off so every row lands in Parquet on MinIO
con.execute("ATTACH 'ducklake:/tmp/dl_meta.ducklake' AS dl "
            "(DATA_PATH 's3://warehouse/ducklake/', DATA_INLINING_ROW_LIMIT 0)")
con.execute("DROP TABLE IF EXISTS dl.network_activity")
con.register("src", tbl)
con.execute("CREATE TABLE dl.network_activity AS SELECT * FROM src")

total = con.execute("SELECT count(*) FROM dl.network_activity").fetchone()[0]
rdp = con.execute("SELECT count(*) FROM dl.network_activity WHERE dst_port = 3389").fetchone()[0]
truth_rdp = sum(1 for i in range(1000) if ports[i % 8] == 3389)

ok = total == 1000 and rdp == truth_rdp
print(f"  format: ducklake (catalog=/tmp/dl_meta.ducklake, data=s3://warehouse/ducklake/)  store: {S3}")
print(f"  wrote+read ducklake network_activity: {total} rows; dst_port=3389 -> {rdp} (truth {truth_rdp})")
print(f"  FORMAT ROUND-TRIP: {'OK' if ok else 'FAILED'}")
sys.exit(0 if ok else 1)
