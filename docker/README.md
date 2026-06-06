# The MOAR reference stack — a tiered, composable, open security-data lakehouse

A runnable reference implementation of the **Modular Open Architecture (MOAR)**: an open, swappable
security-data lakehouse you stand up in **tiers**, running only the layers your box and your question need.
The deployment tiers *are* the book's canonical **L-I-G-E-R** component model made independently deployable,
plus two extensions this kit adds and an opt-in incumbent foil.

```
./moar up laptop          # ~6-8GB:  open lakehouse + detection-as-code, no JVM engines
./moar up workstation     # ~16-24GB: + a distributed engine + local agentic AI
./moar up server          # ~32-48GB: + a 2nd engine + OCSF ingest + dashboards
./moar up compare         # heavy:   + the schema-on-read SIEM foil for head-to-heads
./moar verify             # cross-engine answer-equality over the lakehouse
```

## Why this exists (the four things nobody else ships)

OCSF + Iceberg + Parquet on object storage is now table stakes — Databricks Lakewatch, AWS Security Lake,
Snowflake, Cribl all write OCSF to your S3. What almost none of them ship is an *open-all-the-way-down*,
self-hostable stack. MOAR's reference stack leads with the four gaps:

1. **Fully self-hostable / air-gappable.** No cloud control plane, no vendor SaaS — object store, catalog,
   engines, ingestion, detection, and the AI layer all run on your hardware, mirror-able for an air gap.
2. **Resource-budgeted tiering as a first-class feature.** Every tier has a measured RAM budget and a scale
   preset; `moar` brings heavy tiers up staggered so a cold start doesn't OOM (a lesson learned the hard way).
   No one else in this category publishes laptop / workstation / server / compare presets.
3. **Verify the answer, don't trust it.** `moar verify` cross-checks that every running engine returns the
   *same* answer over the *same* Iceberg table (the SDW Lab finding that a fast engine can be silently wrong —
   chDB's Bloom-filter undercount — made a standing control, not a one-off).
4. **The incumbent as an opt-in foil, in the same compose.** The schema-on-read SIEM baselines live in a
   `baselines` profile you benchmark *against*, rather than a thing you replace blind — the fair-broker move.

## The tiers (L-I-G-E-R + extensions + foil)

| Tier (profile) | L-I-G-E-R | Components (default → swaps) | ~Working RAM | Air-gap | License |
|---|---|---|---|--:|:--:|:--:|
| **core** | **L**+**I**+embedded **E** | MinIO (→SeaweedFS) · Iceberg REST catalog (→Nessie/Polaris/Lakekeeper/DuckLake) · DuckDB lab | 2–4 GB | ✅ | open |
| **engine-trino** | **E** | Trino over the same Iceberg | +4 GB | ✅ | open |
| **engine-clickhouse** | **E** | ClickHouse (real-time OLAP) | +2–4 GB | ✅ | open |
| **engine-starrocks** / **-dremio** | **E** | StarRocks (FE+BE) / Dremio | +8 / +6 GB | ✅ | open |
| **route** | **R** | Vector (→Tenzir/Fluent Bit) + OCSF normalization | +0.5–1 GB | ✅ | open |
| **detection** | (analysis) | marimo notebooks + SigmaHQ + pySigma→engine | +0.3 GB | ✅ | open |
| **ai** *(extension)* | — | Ollama (local weights) + self-hosted stdio MCP + code-action loop | +CPU; GPU-opt | ✅ | open |
| **graph** | **G** | Grafana + Prometheus + Loki + Promtail | +1–2 GB | ✅ | open |
| **baselines** *(foil)* | — | Graylog / OpenSearch / LogScale (Splunk: reference-only, EULA) | +8–16 GB | ⚠ | mixed |

Always include `core`; every other tier reads its lakehouse. Catalog and engine are genuinely swappable —
that's the point of an open table format under one read contract (`SPEC.md` §5).

## Component selection & swaps (bake-offs)

Because the substrate is open under one read contract, components are genuinely swappable — and a swap is
*verifiable*: same Iceberg data, different backend, identical answers (`./moar verify`). Tested and roadmapped
swaps, each with a reason, drawing on the peers' choices (Lisa Cao, Jiahong Que, Zach Schmerber):

| Tier | default | swap candidates | reason to swap | status |
|---|---|---|---|---|
| **L** object store | MinIO | **SeaweedFS** (Lisa, q3) · RustFS · Ceph | footprint — SeaweedFS is **~10× lighter** | **tested: identical answers, 34 MiB vs MinIO ~256-512 MB → use for the laptop tier** |
| **I** catalog | iceberg-rest-fixture | **Nessie** (git-branching) · Lakekeeper (Rust, ~50-150 MB) · Polaris/Unity (governance) · DuckLake (embedded) | production-readiness / footprint / governance | **tested: Nessie (in-memory) returns the identical answer (125 RDP) over the same MinIO — `./moar swap-catalog`**; Lakekeeper/DuckLake roadmap |
| **E** engine | DuckDB + Trino + ClickHouse | StarRocks · Dremio | workload fit (real-time vs federation vs reflections) | **tested: 3-engine `moar verify` green (DuckDB, Trino, ClickHouse all 1000/125 over the same Iceberg table)**; StarRocks/Dremio from the legacy engine block |
| **R** router | Vector | **Tenzir** (security-native: Sigma/OCSF/STIX) · Fluent Bit (lightest) | security-awareness vs footprint | **tested: Tenzir emits the identical OCSF Authentication mapping as Vector on the same raw Okta event — `./moar swap-router`** |

The discipline: **never swap blind — the answer must stay identical across the swap.** Two worked examples now
ship: the MinIO→SeaweedFS object-store swap, and the iceberg-rest→Nessie *catalog* swap (`./moar swap-catalog`
writes+reads the same OCSF table through both catalogs over the same MinIO and asserts the identical answer —
verify-the-answer applied to a component swap). Trino's S3 endpoint is now templated via
`${ENV:S3_INTERNAL_ENDPOINT}` as well, so a store swap flows through to Trino too — the whole
core/lab/detection/engine path follows `S3_INTERNAL_ENDPOINT`. The router swap now ships too: `./moar
swap-router` runs the security-native Tenzir pipeline and the Vector transform over the same raw Okta event
and confirms both produce the identical OCSF Authentication record, so the route tier is swap-clean under one
OCSF contract.

**Other essay-highlighted components, considered.** Four of the five L-I-G-E-R tiers now have a *tested* swap
(store, catalog, engine ×3, route); the rest of what the `/writing` essays compare falls into two buckets.
Some are component swaps still worth wiring but deferred with a reason: **StarRocks / Dremio** (the
`engines/` essays — present in the legacy engine block, not yet on the answer-equality gate), **DuckLake** as
an alternative to Iceberg (`lakehouse/v4-vs-ducklake`, `iceberg-vs-delta` — it's a SQL-catalog + read path,
not an Iceberg-REST drop-in, so it's a larger stack change than a profile swap), **Lakekeeper / Polaris**
catalogs (footprint / governance), and **Fluent Bit** as the lightest router. Others are not stack-service
swaps at all but *lab* comparisons already measured: the **codec / encoder** read-lever
(`lakehouse/encoder-is-the-read-lever`, `same-codec-different-sizes`) is a write-config knob, and **Arrow
Flight / ADBC vs JDBC** (`lakehouse/arrow-flight-sql`, `arrow-adbc`) is an engine↔client transport concern —
both live in `sdw-lab-benchmarks` rather than here. So the stack ships the swaps that are genuinely
profile-swappable-and-verifiable; the format/transport/codec questions the essays raise are answered in the
lab, where the variable can be isolated.

### Lower-level (sub-Parquet) bake-offs — where a swap silently changes the *answer*

The horizontal swaps above are about which box; the deeper, correctness-flavored bake-offs are where the
SDW Lab earns its keep (both silent-wrong-answer findings this year — chDB's Bloom-pushdown undercount and
fastparquet's `PLAIN_DICTIONARY` mis-decode — lived in the Parquet *library* layer, not the engine).

Already benchmarked in `sdw-lab-benchmarks`: Parquet **reader** answer-equivalence (8 readers, 2 silently
wrong), Parquet **writer/encoder** as a read-lever, **codec** (zstd/snappy + schema-trained dict),
**catalog DB** (sqlite vs postgres under concurrency), **spill medium** (ext4 vs drvfs).

Net-new, prioritized (all gated on "the answer is identical"):
1. **Parquet page-checksum (CRC32) write-vs-verify asymmetry** — most readers don't verify CRCs by default,
   so a bit-flip in a checksummed page returns a confident wrong value rather than an error. **Built + tested**
   (`sdw-lab-benchmarks/parquet-checksum-integrity`): a three-way split — chDB verifies by default and catches
   it, pyarrow/Polars are capable but off by default (one keyword arg away), DuckDB/DataFusion expose no
   read-side verification at all; with no checksum *all five* return the wrong sum. The strongest extension of
   the reader-correctness thesis, and the integrity backstop for evidence-grade logs: "verify the answer" has
   to include verifying the bytes, not just cross-checking engines.
2. **Parquet-library correctness matrix** — encoding × library grid (PLAIN/RLE_DICTIONARY/DELTA/BYTE_STREAM_SPLIT
   × pyarrow/DuckDB/Polars/DataFusion/chDB/fastparquet), the home for the bug-class, against the Apache
   implementation-status matrix. **Built + tested** (`sdw-lab-benchmarks/parquet-library-matrix`): on current
   versions there are *no silent-wrong cells* — the exotic encodings fail safe (fastparquet errors on the DELTA
   byte-array family + BYTE_STREAM_SPLIT, DuckDB on BYTE_STREAM_SPLIT-for-int), and at default settings every
   writer's output round-trips through every reader, including DuckDB's deprecated PLAIN_DICTIONARY strings.
   The contrast with #1 (same libs decoded *corruption* silently) is the finding: failure mode is per-layer.
3. **Bloom/stats/encoding × pruning correctness** — the exact layer the chDB bug lived in; needle-in-haystack
   detection queries are the security case. **Built + tested** (`sdw-lab-benchmarks/ocsf-pruning-correctness`):
   a sorted-vs-shuffled A/B (identical 1M-key data, only row order differs, so any disagreement isolates a
   pruning bug) plus a chDB-written bloom file, across 5 engines. All sound on current versions — the chDB-bug
   class does not reproduce, so the bench's value is as a standing regression guard for the pushdown paths.
4. **Vortex vs Parquet** — the one real new sub-Parquet format; footprint+read, correctness-gated. *Still
   install-blocked* (re-checked 2026-06-06): the Python `vortex-array` is yanked on PyPI and the DuckDB
   community `vortex` extension has no build for DuckDB 1.5.3 (download 404). Design recorded in
   `sdw-lab-benchmarks/ocsf-vortex-format`; builds when either path ships. Not yet readable inside Iceberg, so
   it stays a parallel-store experiment.
5. **SIMD-dispatch determinism** (force NONE/AVX2/AVX512, byte-identical results) and **Parquet modular
   encryption interop**. **Built + tested** (`sdw-lab-benchmarks/parquet-determinism-encryption`): SIMD is
   byte-identical across vector widths (not a risk), but the cross-engine *float* aggregate splits 3 ways
   (DuckDB / pyarrow-Polars-DataFusion / chDB) while int-sum/count/min/max stay bit-identical — so exact-typed
   answers are hashable for chain-of-custody, float-derived ones need a tolerance. And a PME-encrypted Parquet
   file is readable only by the implementer-with-key — every other engine is locked out, so at-rest encryption
   *inside* the file revokes the open read contract the swap story rests on (keep encryption at the volume/SSE
   layer for regulated data, or standardize on one PME engine + KMS).

Net-new #1, #2, #3, and #5 are built, tested, and pushed (`sdw-lab-benchmarks`); #4 is blocked upstream. So the
prioritized lower-level set is complete except for Vortex's availability.

Also mapped, lower priority: FileIO/S3-client (S3FileIO vs pyarrow vs s3fs against MinIO/SeaweedFS),
native-vs-JVM footprint/cold-start, persistent-store filesystem (ext4 vs drvfs spill — already measured in
`ocsf-read-scan`/`ocsf-storage-endurance`). Engine↔client transport (Arrow Flight/ADBC vs JDBC) is already its
own benchmark (`sdw-lab-benchmarks/ocsf-arrow-transport`), so it's done, not pending.

## Status — all tiers built + tested

| Tier | what was validated |
|---|---|
| **core** | OCSF table round-trips MinIO↔Iceberg-REST↔DuckDB/pyiceberg (1000 rows; RDP→125=truth) |
| **engine-trino** | Trino reads the *same* Iceberg table, answers identical to DuckDB (`moar verify` green) |
| **engine-clickhouse** | ClickHouse reads the *same* Iceberg table via `icebergS3` (snapshot-correct), answer identical to DuckDB + Trino — `moar verify` now agrees across **three** engines (1000/125) |
| **detection** | a SigmaHQ rule → pySigma→SQL → run over the OCSF lakehouse, detected 125 RDP (the planted count) |
| **ai** | a *local* model (Ollama) ran a code-action hunt over the lakehouse, found the 125 RDP conns, fully air-gapped |
| **graph** | Prometheus + Grafana + Loki + Pushgateway up healthy (prometheus.yml a real file, loki readable) |
| **route** | Vector/VRL raw→OCSF transform proven by `vector test` (Okta auth → class_uid 3002, activity_id, user, src_ip) |
| **baselines** | OpenSearch foil stands up as the schema-on-read SIEM to benchmark against (opt-in, staggered) |
| **swap: L** | **MinIO→SeaweedFS bake-off: identical answers, 34 MiB vs ~256-512 MB → laptop-tier object store** |
| **swap: I** | **iceberg-rest→Nessie catalog swap: identical answer (125 RDP) over the same MinIO (`./moar swap-catalog`) — the open table format makes the catalog replaceable** |
| **swap: R** | **Vector→Tenzir route swap: the security-native pipeline emits the identical OCSF Authentication record (class_uid 3002, activity 1/2, user, src_ip) on the same raw Okta event (`./moar swap-router`)** |

The central claim is proven end-to-end: write once via pyiceberg, read via any engine, **verify the answers
agree** — across engines, across an object-store swap, and across a catalog swap — and the same
verify-the-answer discipline now covers the route tier, where Vector and the security-native Tenzir normalize
the same raw event to the identical OCSF record.

## How it relates to peers (what's borrowed, what's different)

The open-lakehouse-on-a-laptop genre is real; this stack stands on it and adds the security + verification
layers the generic ones leave open.

- **Lisa Cao — `lakehouse-at-home`** (SeaweedFS + Iceberg + switchable catalog + Spark, six compose
  profiles, a `./lakehouse` CLI): the profile-based tiering and operator-CLI ergonomics are borrowed here.
  It's Spark-only and generic data-eng — no security primitives.
- **Jiahong Que — `SoloLakehouse`** (MinIO + Trino-read/DuckDB-write + Dagster + OpenMetadata, single-host):
  the write/read-path split and the lineage-as-evidence chain (→ SOC chain-of-custody) are borrowed. Batch-only.
- **Zach Schmerber — the OCSF-lab repo cluster** (`ocsf-semantic-layer`, `ocsf-web-ide`, `matryoshka`, on
  Tangent): the raw→transform→validated-OCSF-with-coverage% authoring loop, WASM transforms over a DSL, and
  LLM-generates-parser/regex-executes (zero LLM in the hot path) inform the `route`/`detection` tiers.
- **Category OSS** — Matano (Iceberg+VRL+Sigma, but AWS-CDK-locked), Tenzir (open-core security router),
  OpenObserve (Rust single-binary), Quesma (ClickHouse-as-Elasticsearch). MOAR's originality is not open
  storage (lost ground) but the four differentiators above.

## Validation suite

Each tier is exercised by a corresponding SDW Lab benchmark, so the stack ships with its proof:
`core`+`engine` ↔ the multi-engine answer-equivalence probe; `route`+`detection` ↔ the OCSF context-collapse
de-gaming (real APT29 + upstream SigmaHQ); `ai` ↔ the air-gapped agentic hunt. See `sdw-lab-benchmarks`.

## Conventions

Ports are on the `91xx`/`80xx`-avoiding range so MOAR coexists with other local stacks. Dev credentials are
`moar` / `moar-dev-secret` (override via `MINIO_USER`/`MINIO_PASSWORD`); rotate for anything real. The
warehouse bucket uses a bronze/silver/gold medallion layout (peer convention; OCSF normalization slots at
raw→bronze→silver).

## Read alongside (securitydataworks.com)

The stack is the runnable form of the architecture the essays argue; the [SDW Lab](https://securitydataworks.com/lab)
is the measured evidence each tier ships with.

- the architecture — [MOAR](https://securitydataworks.com/thesis/moar) · the differentiator — [The query engine returned the wrong answer](https://securitydataworks.com/writing/detection/silent-wrong-answer) (why `./moar verify` exists)
- **L/I (lakehouse + catalog)** — [Iceberg vs Delta](https://securitydataworks.com/writing/lakehouse/iceberg-vs-delta) · [V4 vs DuckLake](https://securitydataworks.com/writing/lakehouse/v4-vs-ducklake) · [the encoder is the read lever](https://securitydataworks.com/writing/lakehouse/encoder-is-the-read-lever) · catalogs: [decision](https://securitydataworks.com/writing/catalogs/catalog-decision) / [governance](https://securitydataworks.com/writing/catalogs/catalog-governance)
- **E (engines)** — [ClickHouse at petabyte](https://securitydataworks.com/writing/engines/clickhouse-petabyte) · [DuckDB threat hunting](https://securitydataworks.com/writing/engines/duckdb-threat-hunting) · [push vs pull engines](https://securitydataworks.com/writing/engines/push-pull-engines)
- **R (route)** — [Vector](https://securitydataworks.com/writing/pipelines/vector-data-router) · [Tenzir](https://securitydataworks.com/writing/pipelines/tenzir-pipe-layer) · [Cribl vs Tenzir](https://securitydataworks.com/writing/pipelines/cribl-vs-tenzir)
- **detection / Sigma** — [Sigma portability](https://securitydataworks.com/writing/sigma/sigma-portability)
- **methodology behind the bake-offs** — [How to run a benchmark that doesn't lie](https://securitydataworks.com/writing/economics/how-to-run-a-benchmark-that-doesnt-lie) · [Independent measurement](https://securitydataworks.com/writing/economics/independent-measurement)
