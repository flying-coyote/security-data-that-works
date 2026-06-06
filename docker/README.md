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
| **engine-starrocks** | **E** | StarRocks (MPP, all-in-one) over the same Iceberg — in the verify gate | +8 GB | ✅ | open |
| **engine-dremio** *(opt-in)* | **E** | Dremio OSS via a Nessie source — off the gate, see swaps | +6 GB | ✅ | open |
| **route** | **R** | Vector (→Tenzir/Fluent Bit) + OCSF normalization | +0.5–1 GB | ✅ | open |
| **detection** | (analysis) | marimo notebooks + SigmaHQ + pySigma→engine | +0.3 GB | ✅ | open |
| **ai** *(extension)* | — | Ollama (local weights) + self-hosted stdio MCP + code-action loop | +CPU; GPU-opt | ✅ | open |
| **graph** | **G** | Grafana + Prometheus + Loki + Promtail | +1–2 GB | ✅ | open |
| **baselines** *(foil)* | — | Graylog / OpenSearch / LogScale (Splunk: reference-only, EULA) | +8–16 GB | ⚠ | mixed |

Always include `core`; every other tier reads its lakehouse. Catalog and engine are genuinely swappable —
that's the point of an open table format under one read contract (`SPEC.md` §5).

## Component selection & swaps (bake-offs)

Because the stack is open under one read contract, components are genuinely swappable — and a swap is
*verifiable*: same Iceberg data, different backend, identical answers (`./moar verify`). The tested swaps and
the remaining candidates, each with a reason, drawing on the peers' choices (Lisa Cao, Jiahong Que, Zach Schmerber):

| Tier | default | swap candidates | reason to swap | status |
|---|---|---|---|---|
| **L** object store | MinIO | **SeaweedFS** (Lisa, q3) · RustFS · Ceph | footprint, since SeaweedFS is **~10× lighter** | **tested: identical answers, 34 MiB vs MinIO ~256-512 MB → use for the laptop tier** |
| **I** catalog | iceberg-rest-fixture | **Nessie** (Java, git-branching) · **Lakekeeper** (Rust, Postgres-backed) · Polaris/Unity (governance) | production-readiness / footprint / governance | **tested: all three (iceberg-rest, Nessie, Lakekeeper) return the identical 125 RDP over the same MinIO — `./moar swap-catalog`** |
| **I** table format | Iceberg | **DuckLake** (SQL-catalog + Parquet on the same store) | a different format, not a catalog drop-in | **tested: DuckLake writes the same OCSF batch and returns the identical 125 RDP — `./moar swap-format`** |
| **E** engine | DuckDB + Trino + ClickHouse | **StarRocks** (MPP) · Dremio (opt-in) | workload fit (real-time vs federation vs MPP) | **tested: 4-engine `moar verify` green (DuckDB, Trino, ClickHouse, StarRocks all 1000/125); Dremio is an opt-in Nessie-source overlay, off the gate** |
| **R** router | Vector | **Tenzir** (security-native: Sigma/OCSF/STIX) · **Fluent Bit** (lightest) | security-awareness vs footprint | **tested: all three (Vector, Tenzir, Fluent Bit) emit the identical OCSF Authentication record on the same raw Okta event — `./moar swap-router`** |

The discipline is to never swap blind: the answer has to stay identical across the swap. Every swap above now
ships as a one-command check that writes or reads the same OCSF data through the alternative backend and
asserts the answer doesn't move — the MinIO→SeaweedFS object-store bake-off, `./moar swap-catalog` across three
catalog implementations, `./moar swap-format` across Iceberg and DuckLake, `./moar verify` across four engines,
and `./moar swap-router` across three routers. Trino's S3 endpoint is templated via `${ENV:S3_INTERNAL_ENDPOINT}`
so a store swap flows through to Trino as well, and the whole core/lab/detection/engine path follows
`S3_INTERNAL_ENDPOINT`.

**Why three or four of each, not one.** A single alternative proves a swap is possible; agreement across
several independent codebases proves the read contract is real rather than a quirk of one implementation. The
catalog check runs the Java reference fixture, Nessie (Java/Quarkus, with git-style branching), and Lakekeeper
(Rust, Postgres-backed), and all three return the same 125 RDP. The engine gate spans DuckDB (embedded), Trino
(JVM/MPP), ClickHouse (C++ OLAP), and StarRocks (C++/MPP), and all four return 1000/125. The router check spans
Vector (Rust/VRL), Tenzir (C++, security-native TQL), and Fluent Bit (C, with a Lua transform), and all three
emit the identical OCSF Authentication record. DuckLake is the deliberately different case, because it isn't an
Iceberg REST catalog at all but a SQL-catalog table format, so `swap-format` proves the weaker and more honest
claim that the data and the answer survive a format change, not that the catalog is a drop-in.

**Dremio is the one exception, and an honest one.** Dremio OSS doesn't ship the Iceberg REST catalog source,
since that's gated to Enterprise and Cloud, so it can't read the iceberg-rest catalog the other four engines
read. The path that does work on OSS is a Nessie source, set up through an imperative REST choreography
(`config/dremio/setup-dremio.sh`) rather than the declarative boot-time catalog every other engine uses, and it
only proves equality on the Nessie-written copy of the table. So Dremio ships as a documented opt-in overlay
(`--profile engine-dremio`) rather than a participant in `./moar verify`, because four engines already carry the
gate and wiring a JVM container with an acquisition-clouded OSS roadmap into the automated check would buy
little. If Dremio-on-Iceberg-REST ever lands in OSS, it flips to a clean gate participant.

**What stays in the lab.** Some of what the `/writing` essays compare isn't a stack-service swap at
all. The codec and encoder read-lever (`lakehouse/encoder-is-the-read-lever`, `same-codec-different-sizes`) is a
write-config knob, and Arrow Flight / ADBC vs JDBC (`lakehouse/arrow-flight-sql`, `arrow-adbc`) is an
engine↔client transport concern, so both live in `sdw-lab-benchmarks`, where the variable can be isolated,
rather than as a profile here.

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
| **engine-clickhouse** | ClickHouse reads the *same* Iceberg table via `icebergS3` (snapshot-correct), answer identical to DuckDB + Trino (1000/125) |
| **engine-starrocks** | StarRocks reads the *same* Iceberg table via an Iceberg REST external catalog, answer identical to the other three, so `moar verify` agrees across **four** independent engine codebases (1000/125) |
| **detection** | a SigmaHQ rule → pySigma→SQL → run over the OCSF lakehouse, detected 125 RDP (the planted count) |
| **ai** | a *local* model (Ollama) ran a code-action hunt over the lakehouse, found the 125 RDP conns, fully air-gapped |
| **graph** | Prometheus + Grafana + Loki + Pushgateway up healthy (prometheus.yml a real file, loki readable) |
| **route** | Vector/VRL raw→OCSF transform proven by `vector test` (Okta auth → class_uid 3002, activity_id, user, src_ip) |
| **baselines** | OpenSearch foil stands up as the schema-on-read SIEM to benchmark against (opt-in, staggered) |
| **swap: L** | **MinIO→SeaweedFS bake-off: identical answers, 34 MiB vs ~256-512 MB → laptop-tier object store** |
| **swap: I (catalog)** | **iceberg-rest, Nessie, and Lakekeeper all return the identical 125 RDP over the same MinIO (`./moar swap-catalog`) — three independent catalog codebases under one read contract** |
| **swap: I (format)** | **Iceberg and DuckLake return the identical 125 RDP for the same OCSF batch on the same MinIO (`./moar swap-format`) — the data and the answer survive a table-format change** |
| **swap: R** | **Vector, Tenzir, and Fluent Bit all emit the identical OCSF Authentication record (class_uid 3002, activity 1/2, user, src_ip) on the same raw Okta event (`./moar swap-router`)** |

The central claim is proven end-to-end: write once via pyiceberg, read through any engine, and **verify the
answers agree** — across four engines, across an object-store swap, across three catalog implementations and a
DuckLake format swap, and across three routers that normalize the same raw Okta event to the identical OCSF
Authentication record.

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

The stack is the runnable form of the architecture the essays argue; the [SDW Lab](https://securitydataworks.com/lab/)
is the measured evidence each tier ships with.

- the architecture — [MOAR](https://securitydataworks.com/thesis/moar/) · the differentiator — [The query engine returned the wrong answer](https://securitydataworks.com/writing/detection/silent-wrong-answer/) (why `./moar verify` exists)
- **L/I (lakehouse + catalog)** — [Iceberg vs Delta](https://securitydataworks.com/writing/lakehouse/iceberg-vs-delta/) · [V4 vs DuckLake](https://securitydataworks.com/writing/lakehouse/v4-vs-ducklake/) · [the encoder is the read lever](https://securitydataworks.com/writing/lakehouse/encoder-is-the-read-lever/) · catalogs: [decision](https://securitydataworks.com/writing/catalogs/catalog-decision/) / [governance](https://securitydataworks.com/writing/catalogs/catalog-governance/)
- **E (engines)** — [ClickHouse at petabyte](https://securitydataworks.com/writing/engines/clickhouse-petabyte/) · [DuckDB threat hunting](https://securitydataworks.com/writing/engines/duckdb-threat-hunting/) · [push vs pull engines](https://securitydataworks.com/writing/engines/push-pull-engines/)
- **R (route)** — [Vector](https://securitydataworks.com/writing/pipelines/vector-data-router/) · [Tenzir](https://securitydataworks.com/writing/pipelines/tenzir-pipe-layer/) · [Cribl vs Tenzir](https://securitydataworks.com/writing/pipelines/cribl-vs-tenzir/)
- **detection / Sigma** — [Sigma portability](https://securitydataworks.com/writing/sigma/sigma-portability/)
- **methodology behind the bake-offs** — [How to run a benchmark that doesn't lie](https://securitydataworks.com/writing/economics/how-to-run-a-benchmark-that-doesnt-lie/) · [Independent measurement](https://securitydataworks.com/writing/economics/independent-measurement/)
