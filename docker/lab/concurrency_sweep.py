"""Concurrency sweep (the other half of H-ARCH-02 the scale runs only hinted at).

The 1M/10M/100M bench fires queries sequentially, so it measures per-query latency, not what happens when
C analysts hit the same engine at once. This drives C concurrent clients running the same scan-aggregate over
the shared OCSF table and reports aggregate throughput (queries/sec) and p50/p95 latency as C rises. The
architectural reality it models: the embedded engine (DuckDB) is one engine per client — each concurrent
client is its own in-process connection sharing the host's cores — while the server engines (ClickHouse,
StarRocks, Trino) take C concurrent connections to one shared service with its own scheduler. The question is
which model holds throughput and bounded latency as concurrency climbs.

SCOPE: single host (so this measures engine *scheduling models* under contention, not multi-node cluster
concurrency, which still needs a real cluster). The shape — does throughput scale with C or flatten while p95
blows up — is the finding, not the absolute numbers.
"""
import os, time, json, threading, statistics, urllib.request
from concurrent.futures import ThreadPoolExecutor

import duckdb
from pyiceberg.catalog.rest import RestCatalog

LEVELS = [int(x) for x in os.environ.get("CONC_LEVELS", "1,2,4,8,16").split(",")]
T = "ocsf.network_activity_bench"
REST = os.environ.get("ICEBERG_REST_URI", "http://iceberg-rest:8181")
S3 = os.environ.get("S3_ENDPOINT", "http://minio:9000")
AK = os.environ.get("AWS_ACCESS_KEY_ID", "moar")
SK = os.environ.get("AWS_SECRET_ACCESS_KEY", "moar-dev-secret")
SQL = "SELECT dst_port, count(*) c FROM {T} GROUP BY dst_port ORDER BY dst_port"

cat = RestCatalog("moar", **{"uri": REST, "warehouse": "s3://warehouse/", "s3.endpoint": S3,
                             "s3.access-key-id": AK, "s3.secret-access-key": SK,
                             "s3.path-style-access": "true", "s3.region": "us-east-1"})
NROWS = cat.load_table(T).scan().to_arrow().num_rows
_files = [task.file.file_path for task in cat.load_table(T).scan().plan_files()]

_tl = threading.local()


def duck():
    if not getattr(_tl, "duck", None):
        c = duckdb.connect()
        c.execute("INSTALL httpfs; LOAD httpfs;")
        c.execute(f"CREATE OR REPLACE SECRET s (TYPE s3, PROVIDER config, KEY_ID '{AK}', SECRET '{SK}',"
                  f" REGION 'us-east-1', ENDPOINT '{S3.split('://')[-1]}', URL_STYLE 'path', USE_SSL false)")
        _tl.duck = c
    _tl.duck.execute(SQL.format(T=f"read_parquet({_files})")).fetchall()


def ch():
    q = SQL.format(T=f"icebergS3('{S3}/warehouse/ocsf/network_activity_bench','{AK}','{SK}')") + " FORMAT JSONCompact"
    req = urllib.request.Request("http://clickhouse:8123/", data=q.encode(), headers={"X-ClickHouse-User": "default"})
    urllib.request.urlopen(req, timeout=120).read()


def trino():
    doc = json.loads(urllib.request.urlopen(urllib.request.Request(
        "http://trino:8080/v1/statement", data=SQL.format(T=f"iceberg.{T}").encode(),
        headers={"X-Trino-User": "moar"}), timeout=120).read())
    while doc.get("nextUri"):
        doc = json.loads(urllib.request.urlopen(doc["nextUri"], timeout=120).read())


def sr():
    if not getattr(_tl, "sr", None):
        import pymysql
        _tl.sr = pymysql.connect(host="starrocks", port=9030, user="root", connect_timeout=20)
    with _tl.sr.cursor() as cur:
        cur.execute(SQL.format(T=f"iceberg.{T}"))
        cur.fetchall()


ENGINES = {"duckdb": duck, "clickhouse": ch, "trino": trino, "starrocks": sr}


def measure(fn, C):
    n_q = max(C * 3, 12)            # enough queries to keep C workers busy
    lat = []
    lock = threading.Lock()

    def one():
        t = time.perf_counter()
        fn()
        with lock:
            lat.append((time.perf_counter() - t) * 1000)

    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=C) as ex:
        list(ex.map(lambda _: one(), range(n_q)))
    wall = time.perf_counter() - t0
    lat.sort()
    p50 = lat[len(lat) // 2]
    p95 = lat[min(len(lat) - 1, int(len(lat) * 0.95))]
    return round(n_q / wall, 1), round(p50, 1), round(p95, 1)


print(f"concurrency sweep over iceberg.{T} ({NROWS:,} rows), scan-aggregate (group by dst_port), single host")
print(f"  throughput = queries/sec at concurrency C; p50/p95 = per-query latency (ms). C = {LEVELS}")
for name, fn in ENGINES.items():
    try:
        fn()  # warm
    except Exception as e:
        print(f"  {name:12} unavailable: {str(e)[:70]}"); continue
    cells = []
    for C in LEVELS:
        try:
            qps, p50, p95 = measure(fn, C)
            cells.append(f"C{C}: {qps}q/s p95={p95}ms")
        except Exception as e:
            cells.append(f"C{C}: ERR")
    print(f"  {name:12} " + "  |  ".join(cells))
print("  reading: a server engine with its own scheduler should grow queries/sec as C rises and hold p95;")
print("  an embedded engine (one process per client, sharing the host's cores) saturates sooner — p95 climbs")
print("  while throughput flattens. Single host: this is the engine concurrency MODEL, not cluster behavior.")
