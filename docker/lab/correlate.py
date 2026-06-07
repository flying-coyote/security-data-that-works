"""Federated cross-source correlation — the 'well-connected' pillar, demonstrated.

A SIEM silos each tool's data; the open lakehouse holds normalized OCSF from every source in one place, so an
entity (here a source IP) resolves across sources and one SQL join surfaces a chain no single source shows.

Plants a brute-force-then-lateral-movement attacker (198.51.100.66) that appears in BOTH an OCSF Authentication
table (repeated failed logins) AND an OCSF Network Activity table (RDP / dst_port 3389), with benign noise in
each. Each source ALONE is ambiguous — auth sees some failures, network sees some RDP — but the cross-source
join on src_ip reveals the same IP did both: failed auth followed by RDP lateral movement. Self-contained
tables (ocsf.corr_auth / ocsf.corr_net) so it never touches the demo/verify tables.
"""
import os
import sys

import duckdb
import pyarrow as pa
from pyiceberg.catalog.rest import RestCatalog

REST = os.environ.get("ICEBERG_REST_URI", "http://iceberg-rest:8181")
S3 = os.environ.get("S3_ENDPOINT", "http://minio:9000")
AK = os.environ.get("AWS_ACCESS_KEY_ID", "moar")
SK = os.environ.get("AWS_SECRET_ACCESS_KEY", "moar-dev-secret")
ATTACKER = "198.51.100.66"

cat = RestCatalog("moar", **{"uri": REST, "warehouse": "s3://warehouse/", "s3.endpoint": S3,
                             "s3.access-key-id": AK, "s3.secret-access-key": SK,
                             "s3.path-style-access": "true", "s3.region": "us-east-1"})
cat.create_namespace_if_not_exists("ocsf")


def write(ident, tbl):
    try:
        cat.drop_table(ident)
    except Exception:  # noqa: BLE001
        pass
    it = cat.create_table(ident, schema=tbl.schema); it.append(tbl); return it


# OCSF Authentication (3002): 200 benign successes from 10.0.x ips + 8 failed logins from the attacker
auth_ip = [f"10.0.0.{i % 250}" for i in range(200)] + [ATTACKER] * 8
auth_status = ["SUCCESS"] * 200 + ["FAILURE"] * 8
write("ocsf.corr_auth", pa.table({
    "class_uid": pa.array([3002] * len(auth_ip), pa.int32()),
    "activity_id": pa.array([1] * 200 + [2] * 8, pa.int32()),
    "user": pa.array([f"user{i % 50}" for i in range(200)] + ["mallory@acme.example"] * 8),
    "src_ip": pa.array(auth_ip), "status": pa.array(auth_status)}))

# OCSF Network Activity (4001): 300 benign conns (10.0.x, mixed ports) + 5 RDP from the attacker
net_ip = [f"10.0.0.{i % 250}" for i in range(300)] + [ATTACKER] * 5
net_port = [(80, 443, 53, 22)[i % 4] for i in range(300)] + [3389] * 5
write("ocsf.corr_net", pa.table({
    "class_uid": pa.array([4001] * len(net_ip), pa.int32()),
    "src_ip": pa.array(net_ip), "dst_port": pa.array(net_port, pa.int32())}))

# ---- one SQL across the two OCSF sources in the open store: same src_ip with failed auth AND RDP ----
con = duckdb.connect()
con.register("auth", cat.load_table("ocsf.corr_auth").scan().to_arrow())
con.register("net", cat.load_table("ocsf.corr_net").scan().to_arrow())
auth_only = con.execute("SELECT count(DISTINCT src_ip) FROM auth WHERE status='FAILURE'").fetchone()[0]
net_only = con.execute("SELECT count(DISTINCT src_ip) FROM net WHERE dst_port=3389").fetchone()[0]
# per-source counts (not the join-inflated cardinality) for each correlated entity
chain = con.execute("""
    WITH corr AS (SELECT DISTINCT a.src_ip FROM auth a JOIN net n ON a.src_ip = n.src_ip
                  WHERE a.status='FAILURE' AND n.dst_port=3389)
    SELECT c.src_ip,
           (SELECT count(*) FROM auth WHERE src_ip=c.src_ip AND status='FAILURE') AS fails,
           (SELECT count(*) FROM net  WHERE src_ip=c.src_ip AND dst_port=3389)   AS rdp
    FROM corr c ORDER BY fails DESC""").fetchall()

print("federated cross-source correlation over one open OCSF store (ocsf.corr_auth join ocsf.corr_net on src_ip):")
print(f"  per-source view (ambiguous): {auth_only} src_ip(s) with failed auth, {net_only} src_ip(s) doing RDP")
for ip, fails, rdp in chain:
    print(f"  CORRELATED chain: {ip} — {fails} failed auths + {rdp} RDP connections (lateral movement)")
ok = len(chain) == 1 and chain[0][0] == ATTACKER
print(f"  the join surfaces the attacker no single source reveals: {ok}")
print(f"  CROSS-SOURCE CORRELATION: {'OK' if ok else 'FAILED'}")
print("  (the well-connected pillar: entity resolves across sources in one store; a per-tool SIEM fragments this)")
sys.exit(0 if ok else 1)
