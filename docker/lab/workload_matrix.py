"""Workload x engine latency matrix over the same Iceberg table — does the open lakehouse actually specialize?

The cross-engine answer-equality gate proves the five engines AGREE; this asks the other half of the MOAR
claim (H-ARCH-02/06): that no single engine wins every workload, so you pick the engine for the shape of the
query. The same OCSF table (ocsf.network_activity_bench), four workloads with different shapes — a full-scan
count, a low-selectivity needle, a scan-heavy group-by, a high-cardinality distinct — run on DuckDB (embedded),
Trino (JVM/MPP), ClickHouse (C++ OLAP), and StarRocks (C++/MPP), each over its persistent protocol so the
timing is the engine's, not a per-query client/JVM cold start.

Answers are gated for equality on the exact workloads (count / needle / group-by) before any latency is
trusted — a fast wrong number is not a win. Single host, illustrative; the transferable result is the per-
workload winner pattern, not absolute milliseconds.
"""
import json
import os
import statistics
import sys
import time
import urllib.request

import duckdb
from pyiceberg.catalog.rest import RestCatalog

REST = os.environ.get("ICEBERG_REST_URI", "http://iceberg-rest:8181")
S3 = os.environ.get("S3_ENDPOINT", "http://minio:9000")
AK = os.environ.get("AWS_ACCESS_KEY_ID", "moar")
SK = os.environ.get("AWS_SECRET_ACCESS_KEY", "moar-dev-secret")
T = "ocsf.network_activity_bench"
CH_TABLE = f"icebergS3('{S3}/warehouse/ocsf/network_activity_bench','{AK}','{SK}')"


def trials(fn, warmup=1, n=4):
    for _ in range(warmup):
        fn()
    xs = []
    for _ in range(n):
        t0 = time.perf_counter(); fn(); xs.append((time.perf_counter() - t0) * 1000.0)
    xs.sort()
    med = xs[len(xs) // 2]
    mean = sum(xs) / len(xs)
    cv = (statistics.pstdev(xs) / mean * 100.0) if mean else 0.0
    return round(med, 1), round(cv, 1)


# ---- DuckDB (embedded): scan the lake's Parquet from S3 per query (httpfs), NOT a pre-loaded in-memory copy,
# so it's reading the lakehouse like the server engines do — otherwise DuckDB "wins" by querying RAM. ----------
cat = RestCatalog("moar", **{"uri": REST, "warehouse": "s3://warehouse/", "s3.endpoint": S3,
                             "s3.access-key-id": AK, "s3.secret-access-key": SK,
                             "s3.path-style-access": "true", "s3.region": "us-east-1"})
_files = [task.file.file_path for task in cat.load_table(T).scan().plan_files()]
_dcon = duckdb.connect()
_dcon.execute("INSTALL httpfs; LOAD httpfs;")
_dcon.execute(f"""CREATE OR REPLACE SECRET s (TYPE s3, PROVIDER config, KEY_ID '{AK}', SECRET '{SK}',
                  REGION 'us-east-1', ENDPOINT '{S3.split('://')[-1]}', URL_STYLE 'path', USE_SSL false)""")
_DUCK_T = f"read_parquet({_files})"


def duck(sql):
    return _dcon.execute(sql.replace("$T", _DUCK_T)).fetchall()


# ---- ClickHouse over HTTP (icebergS3 table function) -------------------------------------------------------
def ch(sql):
    q = sql.replace("$T", CH_TABLE) + " FORMAT JSONCompact"
    req = urllib.request.Request("http://clickhouse:8123/", data=q.encode(), headers={"X-ClickHouse-User": "default"})
    return json.loads(urllib.request.urlopen(req, timeout=120).read())["data"]


# ---- Trino over HTTP (poll the statement protocol) ---------------------------------------------------------
def trino(sql):
    req = urllib.request.Request("http://trino:8080/v1/statement", data=sql.replace("$T", f"iceberg.{T}").encode(),
                                 headers={"X-Trino-User": "moar"})
    rows, doc = [], json.loads(urllib.request.urlopen(req, timeout=120).read())
    while True:
        rows += doc.get("data", []) or []
        nxt = doc.get("nextUri")
        if not nxt:
            return rows
        doc = json.loads(urllib.request.urlopen(nxt, timeout=120).read())


# ---- StarRocks over MySQL (pymysql, lazy + guarded so a missing engine just yields ERR cells) --------------
_sr = {}


def sr(sql):
    if "c" not in _sr:
        import pymysql  # installed at bench time by ./moar bench
        _sr["c"] = pymysql.connect(host="starrocks", port=9030, user="root", connect_timeout=20)
    with _sr["c"].cursor() as c:
        c.execute(sql.replace("$T", f"iceberg.{T}"))
        return c.fetchall()


ENGINES = {"duckdb": duck, "trino": trino, "clickhouse": ch, "starrocks": sr}

# workload | SQL (with $T placeholder) | extractor -> a comparable scalar/tuple for the equality gate | gated?
WORKLOADS = [
    ("count(*) [full scan]", "SELECT count(*) FROM $T", lambda r: int(r[0][0]), True),
    ("dst_port=3389 [needle]", "SELECT count(*) FROM $T WHERE dst_port=3389", lambda r: int(r[0][0]), True),
    ("group by dst_port [scan-agg]", "SELECT dst_port, count(*) c FROM $T GROUP BY dst_port ORDER BY dst_port",
     lambda r: tuple(sorted((int(a), int(b)) for a, b in r)), True),
    ("distinct src_ip [high-card]", "SELECT count(DISTINCT src_ip) FROM $T", lambda r: int(r[0][0]), False),
]


def main():
    nrows = int(duck("SELECT count(*) FROM $T")[0][0])
    print(f"workload x engine latency over iceberg.{T} ({nrows:,} rows), median ms of 4 trials (CV%):")
    eng = list(ENGINES)
    header = "  workload                          " + "".join(f"{e:>16}" for e in eng) + "   winner"
    print(header); print("  " + "-" * (len(header) - 2))
    gate_ok = True
    winners = []
    for label, sql, extract, gated in WORKLOADS:
        cells, lat, answers = [], {}, {}
        for e, fn in ENGINES.items():
            try:
                answers[e] = extract(fn(sql))
                med, cv = trials(lambda fn=fn: fn(sql))
                lat[e] = med
                cells.append(f"{med:>9.1f}({cv:>3.0f})")
            except Exception as ex:  # noqa: BLE001
                answers[e] = None; lat[e] = None
                cells.append(f"{'ERR':>13}")
        ok = gated and len({v for v in answers.values() if v is not None}) <= 1
        if gated and len({str(v) for v in answers.values() if v is not None}) > 1:
            gate_ok = False
        winner = min((e for e in eng if lat[e] is not None), key=lambda e: lat[e], default="?")
        if gated:
            winners.append(winner)
        flag = "" if not gated else ("✓" if len({str(v) for v in answers.values() if v is not None}) <= 1 else "✗DIVERGE")
        print(f"  {label:32}" + "".join(f"{c:>16}" for c in cells) + f"   {winner} {flag}")
    print("  " + "-" * (len(header) - 2))
    print(f"  answer-equality on the gated workloads (count/needle/group-by): {'✓ all engines agree' if gate_ok else '✗ DIVERGENCE'}")
    distinct_winners = sorted(set(winners))
    if len(distinct_winners) == 1:
        print(f"  reading: at this scale ({nrows:,} rows, single host) {distinct_winners[0]} is fastest on every gated workload —")
        print("  the embedded engine's lack of a coordinator/network hop dominates on small batch queries. H-ARCH-02's")
        print("  per-workload specialization is a SCALE + CONCURRENCY property this snapshot doesn't surface; the scale")
        print("  crossover (where the columnar/MPP engines overtake) is the clickhouse-vs-duckdb lab bench's territory.")
    else:
        print(f"  reading: the fastest engine differs by workload ({', '.join(distinct_winners)}) — 'no single engine wins',")
        print("  measured: you pick the engine for the query shape. That's the H-ARCH-02 specialization claim, on our data.")
    print("  (distinct src_ip is latency-only — ClickHouse count(distinct) is approximate by default. Single host,")
    print("  persistent protocol per engine, end-to-end incl. the Iceberg S3 scan; relative pattern is the finding.)")
    sys.exit(0 if gate_ok else 1)


if __name__ == "__main__":
    main()
