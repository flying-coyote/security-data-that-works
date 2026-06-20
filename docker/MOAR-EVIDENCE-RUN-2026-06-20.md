# MOAR evidence-run — answer-equality + reversibility, 2026-06-20

Live `./moar` validation pass on the MOAR docker stack (Ryzen 5800H / WSL2, single host; moar-*
compose project). This run exercises the *reversibility* claim end to end: the same OCSF answer
survives a swap at each tier (store, catalog, format, route), and every running query engine agrees
over the same Iceberg table. Profiles up for the run: `core` (iceberg-rest + DuckDB-in-lab),
`store-minio`, `store-seaweedfs`, `index-nessie`, `index-lakekeeper`, `engine-trino`,
`engine-clickhouse`, and the `route-*` one-shot routers. The durable record is the Evidence Update
attached to the project1 hypothesis tracker; raw outputs are captured here because the stack is
regenerated on teardown. Tier B, single host, synthetic/structured data only.

## 1. `verify` — cross-engine answer-equality (every engine returns the same answer)

```
cross-engine answer-equality over iceberg.ocsf.network_activity:
  duckdb (lab)     total,rdp = 1000 125
  trino            total,rdp = 1000 125
  clickhouse       total,rdp = 1000 125
  ✓ all running engines agree
```

DuckDB (embedded), Trino (JVM coordinator/worker) and ClickHouse (C++ server) each read the same
Iceberg table through the REST catalog and return the identical row count (1000) and the identical
filtered count (dst_port=3389 → 125). ClickHouse read cleanly through the catalog, not a catalog-less
`icebergS3()` path (which can serve a stale snapshot). The differentiator claim — verify the answer,
don't trust it — holds across three independent engine implementations. As of this session `verify`
also feeds the console data-health gate as its cert-bearing seventh row (pass/fail, decayed to `stale`
past the one-day TTL, never a bluffed pass). Maps to the answer-equality claim under H-ARCH-02.

## 2. `swap-store` — L-tier store swap (MinIO vs SeaweedFS)

```
L-tier store swap check (MinIO vs SeaweedFS), same OCSF batch:
  store minio (http://minio:9000): 1000 rows; dst_port=3389 -> 125 (truth 125)
  store seaweedfs (http://seaweedfs:8333): 1000 rows; dst_port=3389 -> 125 (truth 125)
  ✓ store swap clean — identical answer (rdp=125) on MinIO and SeaweedFS
```

Both stores speak S3, so the lakehouse is indifferent to which sits underneath; the store-footprint
choice (SeaweedFS is the lighter footprint) does not move the answer. Maps to reversibility · L-tier.

## 3. `swap-catalog` — I-tier catalog swap (iceberg-rest vs Nessie vs Lakekeeper)

```
I-tier catalog swap check (iceberg-rest vs nessie vs lakekeeper), same MinIO store:
  iceberg-rest: rdp=125   nessie: rdp=125   lakekeeper: rdp=125
  ✓ catalog swap clean — identical answer across three independent catalog implementations
```

Three independent codebases implement the same Iceberg REST spec — iceberg-rest (Java reference
fixture), Nessie (Java/Quarkus, git-style branching), Lakekeeper (Rust, Postgres-backed) — over the
same MinIO store, and all three return rdp=125. Agreement across three implementations is a portability
signal, not a single-implementation coincidence. Maps to reversibility · I-tier (catalog).

## 4. `swap-format` — I-tier format swap (Iceberg vs DuckLake)

```
I-tier format swap check (Iceberg vs DuckLake), same OCSF batch, same MinIO store:
  iceberg: rdp=125   ducklake: rdp=125
  ✓ format swap clean — identical answer across Iceberg and DuckLake on the same object store
```

The same logical OCSF batch written through a different table format (DuckLake — a SQL-database catalog
plus Parquet on the same MinIO) returns the identical answer as the Iceberg path. DuckLake is not an
Iceberg REST catalog, so this is not a drop-in catalog swap; it is the stronger "the data and the
answer outlive the format." Maps to reversibility · I-tier (format), and to the DuckLake direction
under H-DUCKLAKE-02.

## 5. `swap-router` — R-tier route swap (Vector vs Tenzir vs Fluent Bit)

```
R-tier route swap check (Vector vs Tenzir vs Fluent Bit), same raw Okta sample -> OCSF Authentication:
  vector  (vector test):    PASS — okta_auth_to_ocsf
  tenzir  (okta-ocsf.tql):  PASS — class_uid 3002, activity 1/2, user, src_ip
  fluentbit (ocsf.lua):     PASS — class_uid 3002, activity 1/2, user, src_ip
  ✓ router swap clean — all three routers emit the identical OCSF Authentication contract
```

Vector/VRL (Rust), Tenzir/TQL (C++, security-native) and Fluent Bit/Lua (C, CNCF) turn the same raw
Okta event into the same OCSF Authentication record (class_uid 3002, activity_id 1/2, the two users,
the two src_ips). Key order differs across routers, so the check matches on field/value presence, not
byte-identical lines. Maps to reversibility · R-tier (route/normalization).

## Caveats (all five)

Single host (engine and component *model*, not cluster behavior); synthetic/structured corpora; the
swap legs assert answer-equality / OCSF-contract presence, which proves portability of the answer, not
performance parity across the swapped components. Tier B, first-party. Engines and components at the
versions pinned in the moar compose (Trino 481, ClickHouse server `latest`, DuckDB-in-lab, Nessie,
Lakekeeper, Vector, Tenzir, Fluent Bit). Reproduce with `./moar verify` and `./moar swap-{store,
catalog,format,router}` after `docker compose --profile core --profile store-minio up -d`; each swap
verb self-provisions the profiles it needs.
