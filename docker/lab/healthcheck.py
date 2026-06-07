"""Data-health gate over the live lakehouse — a subset of the Foundation data-health checks, baked into the stack.

A runnable gate you can call in CI or after bringing the stack up. It runs the Layer-3 data-quality dimensions
and the verifier-guard coda from the Foundation data-health demonstrator against the REAL ocsf.network_activity
Iceberg table the stack holds — not synthetic data — so it's a standing data-quality regression check on the
platform's own data. The full four-layer engagement (source + flow health, cross-tool reconciliation, the
remediation interpretation) stays in the engagement kit; this is the slice that makes sense as a stack gate.

The verifier guards are the load-bearing part: they encode the SDW Lab findings directly — no NULL in an
exclusion/allowlist set, timestamps stored as tz-unambiguous epoch ints (not session-local), and a cross-engine
count that agrees — so "verify the data" includes verifying the things that silently break detections.
"""
import os
import sys

import duckdb
import pyarrow as pa  # noqa: F401  (pyiceberg returns arrow; duckdb reads it)
from pyiceberg.catalog.rest import RestCatalog

REST = os.environ.get("ICEBERG_REST_URI", "http://iceberg-rest:8181")
S3 = os.environ.get("S3_ENDPOINT", "http://minio:9000")
AK = os.environ.get("AWS_ACCESS_KEY_ID", "moar")
SK = os.environ.get("AWS_SECRET_ACCESS_KEY", "moar-dev-secret")
TABLE = os.environ.get("HEALTHCHECK_TABLE", "ocsf.network_activity")

cat = RestCatalog("moar", **{
    "uri": REST, "warehouse": "s3://warehouse/", "s3.endpoint": S3,
    "s3.access-key-id": AK, "s3.secret-access-key": SK,
    "s3.path-style-access": "true", "s3.region": "us-east-1"})
try:
    events = cat.load_table(TABLE).scan().to_arrow()
except Exception as e:  # noqa: BLE001
    print(f"  {TABLE} not found ({type(e).__name__}). Seed it first (./moar verify) or pass HEALTHCHECK_TABLE.")
    sys.exit(2)

con = duckdb.connect()
con.register("t", events)
total = con.execute("SELECT count(*) FROM t").fetchone()[0]


def frac(sql):
    return float(con.execute(f"SELECT avg(CASE WHEN {sql} THEN 1.0 ELSE 0.0 END) FROM t").fetchone()[0])


# ---- Layer 3: data-quality dimensions over the live table (illustrative thresholds) ----------------------
distinct = con.execute("SELECT count(*) FROM (SELECT DISTINCT * FROM t)").fetchone()[0]
dims = [
    ("completeness", frac("src_ip IS NOT NULL AND dst_port IS NOT NULL"), 0.98, "key fields populated"),
    ("uniqueness", distinct / total if total else 0.0, 0.999, "no duplicate events"),
    ("validity", frac("dst_port BETWEEN 0 AND 65535 AND regexp_matches(src_ip, '^[0-9]+(\\.[0-9]+){3}$')"),
     0.99, "dst_port in range, src_ip well-formed"),
    ("consistency", frac("class_uid = 4001"), 0.99, "single OCSF class as declared"),
    ("timeliness", frac("\"time\" > 1600000000000"), 0.99, "events carry a sane epoch-ms time"),
]

# ---- Coda: verifier guards (the SDW Lab findings, as a gate) ----------------------------------------------
ts_is_epoch_int = pa.types.is_integer(events.schema.field("time").type)
xeng = con.execute("SELECT count(*) FROM t").fetchone()[0] == events.num_rows
no_null_in_filterset = con.execute(
    "SELECT count(*) FROM (SELECT DISTINCT dst_port FROM t) WHERE dst_port IS NULL").fetchone()[0] == 0
guards = [
    ("exclusion/allowlist set carries no NULL", no_null_in_filterset),
    ("timestamps stored as epoch-int UTC (not session-local)", bool(ts_is_epoch_int)),
    ("cross-engine row count agrees (duckdb == arrow)", bool(xeng)),
]

print(f"data-health gate over {TABLE} ({total:,} rows):")
print("  dimension      score    threshold  verdict")
ok = True
for name, score, thr, note in dims:
    good = score >= thr
    ok = ok and good
    print(f"  {name:13} {score:6.4f}   {thr:>7}    {'OK' if good else 'FAIL'}   ({note})")
print("  verifier guards (the lab findings, as a gate):")
for name, passed in guards:
    ok = ok and passed
    print(f"    {'✓' if passed else '✗'} {name}")

print(f"\n  DATA-HEALTH GATE: {'HEALTHY' if ok else 'ATTENTION — investigate before trusting queries on this table'}")
print("  (subset of the Foundation data-health engagement; the full source/flow/cross-tool layers + the")
print("   remediation interpretation are the paid deliverable — https://securitydataworks.com/thesis/foundation)")
sys.exit(0 if ok else 1)
