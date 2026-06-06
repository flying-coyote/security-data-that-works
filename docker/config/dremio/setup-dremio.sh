#!/usr/bin/env bash
# Dremio OSS — opt-in cross-engine answer-equality participant (NOT in `./moar verify`).
#
# Why opt-in and not in the automated gate: Dremio OSS does not have the Iceberg REST catalog source (that
# source type is Enterprise/Cloud only), so it cannot read the iceberg-rest catalog the other engines read.
# The viable OSS path is the Nessie source, which works but needs an imperative REST choreography
# (bootstrap -> login -> create-source -> submit -> poll) instead of the declarative boot-time catalog every
# other engine uses, and it only proves equality on the Nessie-written copy of the table. So Dremio is shipped
# as a documented manual overlay: bring up the engine-dremio profile, write the table THROUGH Nessie, then run
# this script. Four engines (DuckDB/Trino/ClickHouse/StarRocks) already cover the automated gate.
#
#   docker compose --profile core --profile index-nessie --profile engine-dremio up -d
#   # ... write ocsf.network_activity through Nessie (see README: the swap-catalog path uses Nessie) ...
#   bash config/dremio/setup-dremio.sh
#
# Host port for Dremio is remapped to 9147 (legacy stacks hold 9047). Adjust DREMIO below if you changed it.
set -euo pipefail
DREMIO="${DREMIO:-http://localhost:9147}"
USER="admin"; PASS="dremioAdmin123"

echo "→ waiting for Dremio to accept connections at $DREMIO ..."
for i in $(seq 1 60); do curl -fsS "$DREMIO/apiv2/login" >/dev/null 2>&1 && break || true; sleep 3; done

# (1) first-user bootstrap (fresh container only; ignored if the user already exists)
curl -s -X PUT "$DREMIO/apiv2/bootstrap/firstuser" \
  -H 'Content-Type: application/json' -H 'Authorization: null' \
  --data-raw "{\"userName\":\"$USER\",\"firstName\":\"a\",\"lastName\":\"d\",\"email\":\"admin@example.com\",\"createdAt\":1694089769453,\"password\":\"$PASS\"}" >/dev/null || true

# (2) login -> token (the token MUST be prefixed with _dremio in the auth header)
TOKEN=$(curl -s -X POST "$DREMIO/apiv2/login" -H 'Content-Type: application/json' \
  --data-raw "{\"userName\":\"$USER\",\"password\":\"$PASS\"}" | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
AUTH="Authorization: _dremio$TOKEN"

# (3) create the Nessie source over the SAME MinIO (path-style, http). NOTE: field names below are the
# documented shape; if create fails, configure the source once in the UI and GET /api/v3/source/{id} to copy
# the exact config your version expects (the NESSIE config schema is not fully quotable from public docs).
curl -s -X POST "$DREMIO/api/v3/catalog" -H "$AUTH" -H 'Content-Type: application/json' \
  --data-raw '{
    "entityType":"source","name":"nessie","type":"NESSIE",
    "config":{
      "nessieEndpoint":"http://nessie:19120/api/v2","nessieAuthType":"NONE",
      "awsRootPath":"/warehouse","credentialType":"ACCESS_KEY",
      "awsAccessKey":"moar","awsAccessSecret":"moar-dev-secret",
      "propertyList":[
        {"name":"fs.s3a.path.style.access","value":"true"},
        {"name":"fs.s3a.endpoint","value":"minio:9000"},
        {"name":"dremio.s3.compat","value":"true"},
        {"name":"fs.s3a.connection.ssl.enabled","value":"false"}
      ]}}' >/dev/null || true

# (4) submit the equality query, (5) poll to a final state, (6) fetch the count
JOB=$(curl -s -X POST "$DREMIO/api/v3/sql" -H "$AUTH" -H 'Content-Type: application/json' \
  --data-raw '{"sql":"SELECT count(*) AS total, count(CASE WHEN dst_port=3389 THEN 1 END) AS rdp FROM nessie.ocsf.network_activity"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
for i in $(seq 1 40); do
  st=$(curl -s "$DREMIO/api/v3/job/$JOB" -H "$AUTH" | python3 -c 'import sys,json;print(json.load(sys.stdin)["jobState"])')
  [[ "$st" == "COMPLETED" || "$st" == "FAILED" || "$st" == "CANCELED" ]] && break || sleep 3
done
echo "  dremio job $JOB -> $st"
curl -s "$DREMIO/api/v3/job/$JOB/results?offset=0&limit=1" -H "$AUTH"
echo
echo "Compare total,rdp against ./moar verify (DuckDB/Trino/ClickHouse/StarRocks). Equality holds on the"
echo "Nessie-written copy of ocsf.network_activity."
