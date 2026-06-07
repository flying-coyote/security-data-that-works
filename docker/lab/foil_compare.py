"""Head-to-head: the open lakehouse vs a schema-on-read SIEM foil, same OCSF data, same queries.

The fair-broker move the `baselines` tier exists for: don't replace the incumbent blind, benchmark against it.
This loads the SAME deterministic OCSF Network Activity corpus into both the open lakehouse (Parquet on MinIO,
queried by DuckDB) and the SIEM foil (OpenSearch, the open schema-on-read representative — Splunk is
reference-only per EULA), runs the SAME three queries on each, and reports the things that actually differ:

  1. ANSWER EQUALITY — verify-the-answer applied across the architectures: both must return the same count,
     the same needle (dst_port=3389), and the same dst_port distribution. (Approximate aggregations like
     OpenSearch's cardinality HLL are deliberately excluded from the equality gate; they're a known divergence.)
  2. STORAGE FOOTPRINT — columnar Parquet vs an inverted index + _source + doc values. The lakehouse's
     structural advantage, measured rather than asserted.
  3. LATENCY SHAPE — the honest tradeoff: a low-selectivity needle favors the SIEM's term index, a scan-heavy
     aggregation favors the lakehouse's columnar layout. Reported as hot median + CV over trials.

Tier B, single host, illustrative. Caveat stated in the output: DuckDB is in-process while OpenSearch is
queried over HTTP, so the SIEM latencies carry an HTTP round-trip the lakehouse doesn't — read the *shape*
(needle vs scan), not the absolute milliseconds. Size scales with FOIL_N (default 200,000).
"""
import json
import os
import statistics
import sys
import time
import urllib.error
import urllib.request

import duckdb
import pyarrow as pa

N = int(os.environ.get("FOIL_N", "200000"))
OS_URL = os.environ.get("OPENSEARCH_URL", "http://opensearch:9200")
IDX = "ocsf-network-activity"
S3 = os.environ.get("S3_ENDPOINT", "http://minio:9000")
AK = os.environ.get("AWS_ACCESS_KEY_ID", "moar")
SK = os.environ.get("AWS_SECRET_ACCESS_KEY", "moar-dev-secret")
ENDPOINT = S3.split("://", 1)[-1]
PORTS = [80, 443, 22, 53, 3389, 445, 8080, 3306]


def http(method, path, body=None, ndjson=False):
    data = None
    if body is not None:
        data = (body if ndjson else json.dumps(body)).encode()
    req = urllib.request.Request(
        OS_URL + path, data=data, method=method,
        headers={"Content-Type": "application/x-ndjson" if ndjson else "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return {"_error": e.code, "_body": e.read().decode()[:200]}


def trials(fn, warmup=2, n=5):
    """Hot median (ms) + coefficient of variation over n trials, after warmup — the methodology's stability metric."""
    for _ in range(warmup):
        fn()
    xs = []
    for _ in range(n):
        t = time.perf_counter(); fn(); xs.append((time.perf_counter() - t) * 1000.0)
    xs.sort()
    med = xs[len(xs) // 2]
    mean = sum(xs) / len(xs)
    cv = (statistics.pstdev(xs) / mean * 100.0) if mean else 0.0
    return round(med, 1), round(cv, 1)


def mb(b):
    return round(b / 1024 / 1024, 1)


# ---- the deterministic OCSF Network Activity corpus (same generator family as lab/smoke_core.py, scaled to N)
print(f"corpus: {N:,} OCSF Network Activity (4001) events; dst_port=3389 (the needle) = {N // 8:,}")
tbl = pa.table({
    "time": pa.array([1767225600000 + i for i in range(N)], pa.int64()),
    "class_uid": pa.array([4001] * N, pa.int32()),
    "activity_id": pa.array([(i % 6) + 1 for i in range(N)], pa.int32()),
    "src_ip": pa.array([f"10.0.{i % 256}.{(i * 7) % 256}" for i in range(N)]),
    "dst_port": pa.array([PORTS[i % 8] for i in range(N)], pa.int32()),
    "bytes_out": pa.array([(i * 131) % 1_000_000 for i in range(N)], pa.int64()),
})
truth_total, truth_rdp = N, sum(1 for i in range(N) if PORTS[i % 8] == 3389)

# ---- lakehouse side: write Parquet to MinIO (the real object store), query via DuckDB over httpfs -----------
con = duckdb.connect()
con.execute("INSTALL httpfs; LOAD httpfs;")
con.execute(f"""CREATE OR REPLACE SECRET s (TYPE s3, PROVIDER config, KEY_ID '{AK}', SECRET '{SK}',
                REGION 'us-east-1', ENDPOINT '{ENDPOINT}', URL_STYLE 'path', USE_SSL false)""")
con.register("src", tbl)
PQ = "s3://warehouse/foil/oa.parquet"
t = time.perf_counter()
con.execute(f"COPY src TO '{PQ}' (FORMAT parquet)")
lake_load = (time.perf_counter() - t) * 1000.0
con.execute(f"CREATE VIEW lake AS SELECT * FROM read_parquet('{PQ}')")
lake_bytes = con.execute(f"SELECT sum(total_compressed_size) FROM parquet_metadata('{PQ}')").fetchone()[0]

# ---- SIEM side: create a typed index (schema-on-write) + bulk-load into OpenSearch ------------------------
http("DELETE", f"/{IDX}")
http("PUT", f"/{IDX}", {
    "settings": {"index": {"number_of_replicas": 0, "refresh_interval": "-1"}},
    "mappings": {"properties": {
        "time": {"type": "long"}, "class_uid": {"type": "integer"}, "activity_id": {"type": "integer"},
        "src_ip": {"type": "ip"}, "dst_port": {"type": "integer"}, "bytes_out": {"type": "long"}}}})
rows = tbl.to_pylist()
t = time.perf_counter()
B = 5000
for i in range(0, N, B):
    buf = []
    for r in rows[i:i + B]:
        buf.append('{"index":{}}')
        buf.append(json.dumps(r))
    http("POST", f"/{IDX}/_bulk", "\n".join(buf) + "\n", ndjson=True)
http("POST", f"/{IDX}/_refresh")
siem_load = (time.perf_counter() - t) * 1000.0
st = http("GET", f"/{IDX}/_stats/store")
siem_bytes = st["indices"][IDX]["primaries"]["store"]["size_in_bytes"]

# ---- the shared query battery: same question, each system's native form --------------------------------------
def lake_total(): return con.execute("SELECT count(*) FROM lake").fetchone()[0]
def siem_total(): return http("GET", f"/{IDX}/_count")["count"]
def lake_rdp(): return con.execute("SELECT count(*) FROM lake WHERE dst_port=3389").fetchone()[0]
def siem_rdp(): return http("GET", f"/{IDX}/_count", {"query": {"term": {"dst_port": 3389}}})["count"]
def lake_grp(): return sorted((int(p), int(c)) for p, c in
                              con.execute("SELECT dst_port,count(*) FROM lake GROUP BY dst_port").fetchall())
def siem_grp():
    r = http("GET", f"/{IDX}/_search", {"size": 0, "aggs": {"p": {"terms": {"field": "dst_port", "size": 50}}}})
    return sorted((int(b["key"]), int(b["doc_count"])) for b in r["aggregations"]["p"]["buckets"])

QUERIES = [
    ("count(*)", "full scan / total", lake_total, siem_total, truth_total),
    ("dst_port=3389 (needle)", "low-selectivity point lookup", lake_rdp, siem_rdp, truth_rdp),
    ("group by dst_port", "scan-heavy aggregation", lake_grp, siem_grp, None),
]

print(f"\nload:    lakehouse (Parquet→MinIO) {lake_load:8.0f} ms   |   siem (OpenSearch bulk) {siem_load:8.0f} ms")
print(f"storage: lakehouse Parquet {mb(lake_bytes):8} MB   |   siem index {mb(siem_bytes):8} MB"
      f"   → SIEM index is {siem_bytes / lake_bytes:.1f}× the columnar footprint")
print("\n  query                       shape                          lakehouse        siem      agree   lake ms (cv)   siem ms (cv)")
print("  " + "-" * 116)

all_agree = True
lat = []
for label, shape, lf, sf, truth in QUERIES:
    la, sa = lf(), sf()
    if isinstance(la, list):  # group-by: compare the full distribution
        agree = la == sa
        show_l, show_s = f"{len(la)} buckets", f"{len(sa)} buckets"
    else:
        agree = (la == sa) and (truth is None or la == truth)
        show_l, show_s = f"{la:,}", f"{sa:,}"
    all_agree = all_agree and agree
    lm, lcv = trials(lf)
    sm, scv = trials(sf)
    lat.append((label, lm, sm))
    print(f"  {label:26}  {shape:30} {show_l:>12}  {show_s:>10}     "
          f"{'✓' if agree else '✗'}    {lm:7.1f} ({lcv:>3.0f}%)  {sm:7.1f} ({scv:>3.0f}%)")

print("  " + "-" * 116)
# data-driven summary — report what was actually measured, not an asserted architecture expectation
lake_wins = sum(1 for _, lm, sm in lat if lm < sm)
ratio = siem_bytes / lake_bytes
needle = next((lm, sm) for label, lm, sm in lat if "needle" in label)
print(f"\n  answer-equality across the lakehouse and the SIEM foil: {'✓ all queries agree' if all_agree else '✗ DIVERGENCE'}")
print(f"  measured here ({N:,} rows): identical answers, the lakehouse at {ratio:.1f}× less storage, and faster on "
      f"{lake_wins}/{len(lat)} queries (needle {needle[0]:.1f} vs {needle[1]:.1f} ms).")
print("  read with care: at this corpus size DuckDB's columnar scan is already sub-10ms, and OpenSearch is queried")
print("  over HTTP while DuckDB is in-process, so the SIEM carries a round-trip the lakehouse doesn't. The term")
print("  index's advantage is on highly selective needles at much larger scale — which this single-host run does")
print("  not isolate. The robust, scale-independent findings are the answer-equality and the storage ratio.")
sys.exit(0 if all_agree else 1)
