"""Streaming commit-tax bench (H-DUCKLAKE-02 / latency-tiers / write-pattern-is-architectural).

Security telemetry arrives as a tiny-frequent-commit stream, which is exactly the cadence Iceberg's
file-per-commit floor punishes: every commit writes a data file + a manifest + a manifest-list + a new
metadata.json, and query planning then has to walk all of them. DuckLake keeps commit metadata in a SQL
catalog (so the per-commit metadata.json/manifest proliferation never happens) and can inline small commits
into the catalog instead of writing a Parquet file per commit at all.

This ingests the SAME total rows two ways — one batch commit vs N streaming commits — into Iceberg and into
DuckLake (inlining off, then on), on the real MinIO object store (the write-pattern essay's named open
follow-up: real object storage, not local disk), and reports the metadata footprint and the planning cost.
The point is the SHAPE of the tax, not the absolute ms; single host.
"""
import os, sys, time

import pyarrow as pa
from pyarrow.fs import S3FileSystem
from pyiceberg.catalog.rest import RestCatalog

ROWS = int(os.environ.get("COMMIT_TAX_ROWS", "100000"))
NCOMMITS = int(os.environ.get("COMMIT_TAX_STREAM_COMMITS", "100"))
REST = os.environ.get("ICEBERG_REST_URI", "http://iceberg-rest:8181")
S3 = os.environ.get("S3_ENDPOINT", "http://minio:9000")
AK = os.environ.get("AWS_ACCESS_KEY_ID", "moar")
SK = os.environ.get("AWS_SECRET_ACCESS_KEY", "moar-dev-secret")
endpoint = S3.split("://", 1)[-1]
chunk = ROWS // NCOMMITS

ports = [80, 443, 22, 53, 3389, 445, 8080, 3306, 1433, 8443]


def batch(n, off):
    return pa.table({
        "time": pa.array([1767225600000 + off + i for i in range(n)], pa.int64()),
        "class_uid": pa.array([4001] * n, pa.int32()),
        "activity_id": pa.array([((off + i) % 6) + 1 for i in range(n)], pa.int32()),
        "src_ip": pa.array([f"10.0.{(off + i) % 256}.{((off + i) * 7) % 256}" for i in range(n)]),
        "dst_port": pa.array([ports[(off + i) % 10] for i in range(n)], pa.int32()),
        "bytes_out": pa.array([((off + i) * 131) % 1_000_000 for i in range(n)], pa.int64()),
    })


fs = S3FileSystem(access_key=AK, secret_key=SK, endpoint_override=endpoint,
                  scheme=S3.split("://")[0], region="us-east-1")


def s3_footprint(prefix, suffixes=None):
    """count files (optionally by suffix) and total bytes under a bucket/prefix."""
    from pyarrow.fs import FileSelector
    try:
        infos = fs.get_file_info(FileSelector(prefix, recursive=True))
    except Exception:
        return (0, 0, 0)
    files = [i for i in infos if i.type.name == "File"]
    n = len(files); nbytes = sum(i.size for i in files)
    nmeta = len([i for i in files if suffixes and any(i.path.endswith(s) for s in suffixes)])
    return (n, nbytes, nmeta)


def purge(prefix):
    try:
        fs.delete_dir_contents(prefix, missing_dir_ok=True)
    except Exception:
        pass


cat = RestCatalog("moar", **{"uri": REST, "warehouse": "s3://warehouse/", "s3.endpoint": S3,
                             "s3.access-key-id": AK, "s3.secret-access-key": SK,
                             "s3.path-style-access": "true", "s3.region": "us-east-1"})
cat.create_namespace_if_not_exists("ocsf")


def iceberg_run(label, ncommits):
    ident = "ocsf.commit_tax"
    try:
        cat.drop_table(ident)
    except Exception:
        pass
    purge("warehouse/ocsf/commit_tax")
    per = ROWS // ncommits
    t0 = time.perf_counter()
    it = cat.create_table(ident, schema=batch(per, 0).schema)
    for c in range(ncommits):
        it.append(batch(per, c * per))
    ingest = time.perf_counter() - t0
    it = cat.load_table(ident)
    # planning cost: walk the manifests
    t1 = time.perf_counter()
    nfiles = len(list(it.scan().plan_files()))
    plan_ms = (time.perf_counter() - t1) * 1000
    data = s3_footprint("warehouse/ocsf/commit_tax/data")
    meta = s3_footprint("warehouse/ocsf/commit_tax/metadata",
                        suffixes=[".metadata.json", ".avro"])
    return dict(label=label, commits=ncommits, ingest_s=round(ingest, 2),
                data_files=data[0], meta_files=meta[0],
                meta_kb=round(meta[1] / 1024, 1), plan_ms=round(plan_ms, 1), planned_files=nfiles)


def ducklake_run(label, ncommits, inline_limit):
    import duckdb
    catfile = f"/tmp/dl_ct_{inline_limit}.ducklake"
    for ext in ("", ".wal"):
        try: os.remove(catfile + ext)
        except OSError: pass
    purge(f"warehouse/ducklake_ct_{inline_limit}")
    con = duckdb.connect()
    con.execute("INSTALL ducklake; LOAD ducklake; INSTALL httpfs; LOAD httpfs;")
    con.execute(f"CREATE OR REPLACE SECRET minio (TYPE s3, PROVIDER config, KEY_ID '{AK}', SECRET '{SK}',"
                f" REGION 'us-east-1', ENDPOINT '{endpoint}', URL_STYLE 'path', USE_SSL false)")
    con.execute(f"ATTACH 'ducklake:{catfile}' AS dl (DATA_PATH 's3://warehouse/ducklake_ct_{inline_limit}/',"
                f" DATA_INLINING_ROW_LIMIT {inline_limit})")
    per = ROWS // ncommits
    t0 = time.perf_counter()
    con.execute("CREATE TABLE dl.commit_tax (time BIGINT, class_uid INT, activity_id INT, src_ip VARCHAR, dst_port INT, bytes_out BIGINT)")
    for c in range(ncommits):
        con.register("chunk", batch(per, c * per))
        con.execute("INSERT INTO dl.commit_tax SELECT * FROM chunk")
        con.unregister("chunk")
    ingest = time.perf_counter() - t0
    t1 = time.perf_counter()
    nrows = con.execute("SELECT count(*) FROM dl.commit_tax").fetchone()[0]
    plan_ms = (time.perf_counter() - t1) * 1000
    con.close()
    data = s3_footprint(f"warehouse/ducklake_ct_{inline_limit}")
    cat_kb = round(os.path.getsize(catfile) / 1024, 1) if os.path.exists(catfile) else 0
    return dict(label=label, commits=ncommits, ingest_s=round(ingest, 2),
                data_files=data[0], meta_files="(in catalog DB)",
                meta_kb=f"cat {cat_kb}", plan_ms=round(plan_ms, 1), planned_files=nrows)


print(f"streaming commit-tax: {ROWS:,} rows total, batch (1 commit) vs streaming ({NCOMMITS} commits), MinIO object store")
rows = [
    iceberg_run("iceberg  batch", 1),
    iceberg_run("iceberg  stream", NCOMMITS),
    ducklake_run("ducklake stream (inline off)", NCOMMITS, 0),
    ducklake_run("ducklake stream (inline on)", NCOMMITS, max(chunk * 2, 10000)),
]
print(f"  {'config':30} {'commits':>7} {'ingest_s':>8} {'data_files':>10} {'meta_files':>12} {'meta/cat_KB':>12} {'plan_ms':>8}")
for r in rows:
    print(f"  {r['label']:30} {r['commits']:>7} {r['ingest_s']:>8} {r['data_files']:>10} {str(r['meta_files']):>12} {str(r['meta_kb']):>12} {r['plan_ms']:>8}")

ib, isb = rows[0], rows[1]
print(f"\n  the commit tax (Iceberg batch -> {NCOMMITS}-commit stream): "
      f"data files {ib['data_files']}->{isb['data_files']}, metadata files {ib['meta_files']}->{isb['meta_files']}, "
      f"metadata {ib['meta_kb']}->{isb['meta_kb']} KB, plan {ib['plan_ms']}->{isb['plan_ms']} ms.")
print("  DuckLake keeps commit metadata in the catalog DB (no per-commit metadata.json/manifest proliferation), "
      "and with inlining on the small commits don't each write a Parquet file. Real MinIO object store, single host; "
      "the shape of the tax is the finding.")
