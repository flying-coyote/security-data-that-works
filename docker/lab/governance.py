"""Catalog governance — the audit-trail + time-travel a mutable SIEM index can't give you (H-SEC-CATALOG-01).

A schema-on-read SIEM stores telemetry in a mutable index: there's no tamper-evident record of what the data
said at query time, and a deletion or backfill leaves no trace. An Iceberg table behind the catalog is the
opposite — every commit appends an immutable snapshot to a linked history (parent → child), so you can list the
full audit trail and time-travel to the exact state as of any snapshot. This proves the governance leg: the
catalog makes the data's history *verifiable*, which is what regulated evidence (Reg SCI / 17a-4(f)) needs.

Makes three appends to a fresh table, then (1) reads the snapshot history (the audit trail), (2) time-travels
to each snapshot and confirms the row count is the cumulative state as of that commit, (3) checks the snapshots
form an unbroken parent→child chain. Self-contained table (ocsf.gov_audit).
"""
import os
import sys

import pyarrow as pa
from pyiceberg.catalog.rest import RestCatalog

REST = os.environ.get("ICEBERG_REST_URI", "http://iceberg-rest:8181")
S3 = os.environ.get("S3_ENDPOINT", "http://minio:9000")
AK = os.environ.get("AWS_ACCESS_KEY_ID", "moar")
SK = os.environ.get("AWS_SECRET_ACCESS_KEY", "moar-dev-secret")
K = 100  # rows per commit

cat = RestCatalog("moar", **{"uri": REST, "warehouse": "s3://warehouse/", "s3.endpoint": S3,
                             "s3.access-key-id": AK, "s3.secret-access-key": SK,
                             "s3.path-style-access": "true", "s3.region": "us-east-1"})
cat.create_namespace_if_not_exists("ocsf")
ident = "ocsf.gov_audit"
try:
    cat.drop_table(ident)
except Exception:  # noqa: BLE001
    pass


def batch(start):
    return pa.table({"id": pa.array(list(range(start, start + K)), pa.int64()),
                     "class_uid": pa.array([4001] * K, pa.int32())})


schema = batch(0).schema
tbl = cat.create_table(ident, schema=schema)
for b in range(3):                     # three commits = three immutable snapshots
    tbl.append(batch(b * K))
tbl = cat.load_table(ident)

# (1) the audit trail — every commit recorded, immutable, timestamped
snaps = list(tbl.metadata.snapshots)
print(f"catalog audit trail for {ident}: {len(snaps)} immutable snapshots from 3 commits")
for s in snaps:
    added = (s.summary.additional_properties.get("added-records") if s.summary else "?")
    print(f"  snapshot {s.snapshot_id}  parent={s.parent_snapshot_id}  +{added} records")

# (2) time-travel: state as of each snapshot is the cumulative commit state (audit-replayable)
counts = [tbl.scan(snapshot_id=s.snapshot_id).to_arrow().num_rows for s in snaps]
print(f"  time-travel row counts as of each snapshot: {counts}  (expect {[K, 2 * K, 3 * K]})")

# (3) unbroken parent->child chain (tamper-evidence: a removed/edited commit breaks the chain)
ids = [s.snapshot_id for s in snaps]
chain_ok = all(snaps[i].parent_snapshot_id == ids[i - 1] for i in range(1, len(snaps)))

ok = counts == [K, 2 * K, 3 * K] and len(snaps) == 3 and chain_ok
print(f"  history complete + replayable + unbroken parent chain: {ok}")
print(f"  CATALOG GOVERNANCE (audit trail + time-travel + lineage): {'OK' if ok else 'FAILED'}")
print("  (the governance leg: the catalog makes the data's history verifiable — a mutable SIEM index can't;")
print("   what Reg SCI / 17a-4(f) evidence needs. The open table format is the same audit trail under any catalog.)")
sys.exit(0 if ok else 1)
