"""Detection-as-code over the open lakehouse: compile SigmaHQ rules to SQL, run over the OCSF Iceberg table.

Portable Sigma rule -> pySigma -> SQL -> executed over the same OCSF table the lakehouse holds (read via
pyiceberg into DuckDB). This is the detection tier's proof: a detection that lives as code, runs on any
engine over the open store, and is verifiable. Reports matches per rule (precision is the analyst's job;
this measures that the round trip fires).
"""
import glob
import os
import sys

import duckdb
from pyiceberg.catalog.rest import RestCatalog
from sigma.backends.sqlite import sqliteBackend
from sigma.collection import SigmaCollection

REST = os.environ.get("ICEBERG_REST_URI", "http://iceberg-rest:8181")
S3 = os.environ.get("S3_ENDPOINT", "http://minio:9000")
AK = os.environ.get("AWS_ACCESS_KEY_ID", "moar")
SK = os.environ.get("AWS_SECRET_ACCESS_KEY", "moar-dev-secret")
HERE = os.path.dirname(os.path.abspath(__file__))

cat = RestCatalog("moar", **{
    "uri": REST, "warehouse": "s3://warehouse/", "s3.endpoint": S3,
    "s3.access-key-id": AK, "s3.secret-access-key": SK,
    "s3.path-style-access": "true", "s3.region": "us-east-1"})

events = cat.load_table("ocsf.network_activity").scan().to_arrow()
con = duckdb.connect()
con.register("events", events)
total = con.execute("SELECT count(*) FROM events").fetchone()[0]

backend = sqliteBackend()
rows, fired = [], 0
for rf in sorted(glob.glob(os.path.join(HERE, "rules", "*.yml"))):
    coll = SigmaCollection.from_yaml(open(rf).read())
    rule = coll.rules[0]
    sql = backend.convert(coll)[0]
    run = sql.replace("SELECT *", "SELECT count(*)").replace("<TABLE_NAME>", "events")
    try:
        n = int(con.execute(run).fetchone()[0])
        ok = True
    except Exception as e:  # noqa: BLE001
        n, ok = 0, False
        run += f"  -- ERROR: {str(e)[:80]}"
    fired += 1 if (ok and n > 0) else 0
    tags = ",".join(str(t) for t in rule.tags)
    rows.append({"rule": rule.title, "tags": tags, "matches": n, "compiled": ok})
    print(f"  {rule.title:42} matches={n:<6} [{tags}]")

print(f"\n{fired}/{len(rows)} Sigma rules fired over {total} OCSF events on the open lakehouse")
sys.exit(0 if fired == len(rows) else 1)
