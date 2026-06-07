#!/usr/bin/env bash
# Dremio OSS as a VERIFIED cross-engine answer-equality participant (via a Nessie source).
#
# Why a Nessie source and not the iceberg-rest catalog the other four engines read: Dremio OSS does not ship
# the Iceberg REST catalog source (that type is Enterprise/Cloud only), so Dremio reads the Nessie-written copy
# of the table — the SAME logical OCSF data (same generator, same MinIO), independently committed through a
# second catalog. Confirmed live 2026-06-07: Dremio returns total=1000, dst_port=3389 -> 125, identical to
# DuckDB / Trino / ClickHouse / StarRocks. So the answer-equality claim actually strengthens — it spans five
# engines AND two catalogs.
#
# This is run from the `docker/` dir (cwd holds compose.yml) by `./moar verify-dremio`, or standalone. It is
# idempotent: it re-uses the bootstrapped admin and an existing source, and ensures its own read target.
#
# The config below is the WORKING one (the research draft missed three things): secure:false because MinIO is
# plain HTTP and Dremio's S3 client otherwise attempts TLS ("Unsupported or unrecognized SSL message");
# awsRootPath with no leading slash; and the real moar / moar-dev-secret creds.
set -euo pipefail
DREMIO="${DREMIO:-http://localhost:9147}"
DUSER="admin"; DPASS="dremioAdmin123"
DC="docker compose"

say() { echo "$@"; }

# 0. wait for Dremio's API (a GET to /apiv2/login returns 403 when up — any HTTP response means ready)
for i in $(seq 1 60); do
  code=$(curl -s -o /dev/null -w '%{http_code}' "$DREMIO/apiv2/login" 2>/dev/null || echo 000)
  [ "$code" != "000" ] && break || sleep 3
done

# 1. ensure the Nessie copy of ocsf.network_activity exists (Dremio's read target; same generator as the
#    iceberg-rest copy the gate reads). Idempotent drop+recreate; harmless if it already matches.
$DC exec -T -e ICEBERG_REST_URI=http://nessie:19120/iceberg/ -e WAREHOUSE=warehouse lab \
  python /lab/smoke_core.py >/dev/null 2>&1 || true

# 2. first-user bootstrap (ignored once the user exists)
curl -s -X PUT "$DREMIO/apiv2/bootstrap/firstuser" -H 'Content-Type: application/json' -H 'Authorization: _dremionull' \
  --data-raw "{\"userName\":\"$DUSER\",\"firstName\":\"a\",\"lastName\":\"d\",\"email\":\"a@e.com\",\"createdAt\":1694089769453,\"password\":\"$DPASS\"}" \
  >/dev/null 2>&1 || true

# 3. login -> token (the auth header value must be prefixed with _dremio)
TOKEN=$(curl -s -X POST "$DREMIO/apiv2/login" -H 'Content-Type: application/json' \
  --data-raw "{\"userName\":\"$DUSER\",\"password\":\"$DPASS\"}" \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')
AUTH="Authorization: _dremio$TOKEN"

# 4. create the Nessie source if absent (the verified working config). Reads the SAME MinIO as everything else.
exists=$(curl -s -o /dev/null -w '%{http_code}' "$DREMIO/api/v3/catalog/by-path/nessie" -H "$AUTH" 2>/dev/null || echo 000)
if [ "$exists" != "200" ]; then
  curl -s -X POST "$DREMIO/api/v3/catalog" -H "$AUTH" -H 'Content-Type: application/json' --data-raw '{
    "entityType":"source","name":"nessie","type":"NESSIE",
    "config":{"nessieEndpoint":"http://nessie:19120/api/v2","nessieAuthType":"NONE",
      "awsRootPath":"warehouse","credentialType":"ACCESS_KEY",
      "awsAccessKey":"moar","awsAccessSecret":"moar-dev-secret","secure":false,
      "propertyList":[{"name":"fs.s3a.path.style.access","value":"true"},
        {"name":"fs.s3a.endpoint","value":"minio:9000"},
        {"name":"dremio.s3.compat","value":"true"},
        {"name":"fs.s3a.connection.ssl.enabled","value":"false"}]}}' >/dev/null
fi

# 5. submit the equality query, poll to a final state, fetch the row
JOB=$(curl -s -X POST "$DREMIO/api/v3/sql" -H "$AUTH" -H 'Content-Type: application/json' \
  --data-raw '{"sql":"SELECT count(*) AS total, count(CASE WHEN dst_port=3389 THEN 1 END) AS rdp FROM nessie.ocsf.network_activity"}' \
  | python3 -c 'import sys,json;print(json.load(sys.stdin)["id"])')
state="?"
for i in $(seq 1 40); do
  state=$(curl -s "$DREMIO/api/v3/job/$JOB" -H "$AUTH" | python3 -c 'import sys,json;print(json.load(sys.stdin).get("jobState","?"))')
  [[ "$state" == COMPLETED || "$state" == FAILED || "$state" == CANCELED ]] && break || sleep 3
done
RES=$(curl -s "$DREMIO/api/v3/job/$JOB/results?offset=0&limit=1" -H "$AUTH")
read -r TOTAL RDP < <(echo "$RES" | python3 -c 'import sys,json
try:
    r=json.load(sys.stdin)["rows"][0]; print(r["total"], r["rdp"])
except Exception:
    print("ERR ERR")')

say "  dremio (nessie)  total,rdp = $TOTAL $RDP   [job $state]"
if [ "$TOTAL" = "1000" ] && [ "$RDP" = "125" ]; then
  say "  ✓ dremio agrees (reads the Nessie-written copy; same logical OCSF data as the iceberg-rest gate)"
  exit 0
else
  say "  ✗ dremio answer unexpected (expected 1000 125) — check the source + the Nessie table"
  exit 1
fi
