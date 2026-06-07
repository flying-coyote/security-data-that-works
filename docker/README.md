# The MOAR reference stack — a tiered, composable, open security-data lakehouse

A runnable reference implementation of the **Modular Open Architecture (MOAR)**: an open, swappable
security-data lakehouse you stand up in **tiers**, running only the layers your box and your question need.
The deployment tiers *are* the book's canonical **L-I-G-E-R** component model made independently deployable,
plus two extensions this kit adds and an opt-in incumbent foil.

```
./moar up soc-10gb        # ~6-8GB:  small SOC (~10 GB/day) — open lakehouse + detection-as-code, no JVM engines
./moar up soc-100gb       # ~16-24GB: mid SOC (~100 GB/day) — + Trino federation + local agentic AI
./moar up soc-1tb         # ~32-40GB: large SOC (~1 TB/day) — + ClickHouse + StarRocks + OCSF ingest + dashboards
./moar up soc-10tb        # heavy:   + the schema-on-read SIEM foil for buy-vs-build
./moar verify             # answer-equality across DuckDB / Trino / ClickHouse / StarRocks / Dremio
```

Presets are named by the SOC ingest scale they map to (10× steps); the old RAM-budget names
(`laptop`/`workstation`/`server`/`compare`) still work as aliases.

## Why this exists (the four things nobody else ships)

OCSF + Iceberg + Parquet on object storage is now table stakes — Databricks Lakewatch, AWS Security Lake,
Snowflake, Cribl all write OCSF to your S3. What almost none of them ship is an *open-all-the-way-down*,
self-hostable stack. MOAR's reference stack leads with the four gaps:

1. **Fully self-hostable / air-gappable.** No cloud control plane, no vendor SaaS — object store, catalog,
   engines, ingestion, detection, and the AI layer all run on your hardware, mirror-able for an air gap.
2. **Tiering by SOC ingest scale, as a first-class feature.** Presets map to the ingest scale a SOC actually
   plans around (~10 GB/day → ~10 TB/day in 10× steps) and bring up only the components that scale calls for;
   `moar` staggers heavy tiers so a cold start doesn't OOM (a lesson learned the hard way). A single host
   demonstrates the architecture; the throughput numbers come from the SDW Lab's measured scale sweeps. No one
   else in this category ships ingest-scale presets.
3. **Verify the answer, don't trust it.** `moar verify` cross-checks that every running engine returns the
   *same* answer over the *same* Iceberg table — five engines today (DuckDB, Trino, ClickHouse, StarRocks,
   Dremio). The SDW Lab finding that a fast engine can be silently wrong (chDB's Bloom-filter undercount) is
   what made this a standing control rather than a one-off.
4. **The incumbent as an opt-in foil, in the same compose.** The schema-on-read SIEM baselines live in a
   `baselines` profile you benchmark *against*, rather than a thing you replace blind — the fair-broker move.
   `./moar compare` runs the head-to-head (same OCSF data into both, same queries): the answers come back
   identical, and the lakehouse holds them in ~7× less storage than the SIEM's index.

## The tiers (L-I-G-E-R + extensions + foil)

| Tier (profile) | L-I-G-E-R | Components (default → swaps) | ~Working RAM | Air-gap | License |
|---|---|---|---|--:|:--:|:--:|
| **core** | **L**+**I**+embedded **E** | MinIO (→SeaweedFS) · Iceberg REST catalog (→Nessie/Polaris/Lakekeeper/DuckLake) · DuckDB lab | 2–4 GB | ✅ | open |
| **engine-trino** | **E** | Trino over the same Iceberg | +4 GB | ✅ | open |
| **engine-clickhouse** | **E** | ClickHouse (real-time OLAP) | +2–4 GB | ✅ | open |
| **engine-starrocks** | **E** | StarRocks (MPP, all-in-one) over the same Iceberg — in `verify`, enters at the soc-1tb tier | +8 GB | ✅ | open |
| **engine-dremio** | **E** | Dremio OSS (federation) via a Nessie source — verified, folds into `verify` (`./moar verify-dremio`) | +6 GB | ✅ | open |
| **route** | **R** | Vector (→Tenzir/Fluent Bit) + OCSF normalization | +0.5–1 GB | ✅ | open |
| **detection** | (analysis) | marimo notebooks + SigmaHQ + pySigma→engine | +0.3 GB | ✅ | open |
| **ai** *(extension)* | — | Ollama (local weights) + self-hosted stdio MCP + code-action loop | +CPU; GPU-opt | ✅ | open |
| **graph** | **G** | Grafana + Prometheus + Loki + Promtail | +1–2 GB | ✅ | open |
| **baselines** *(foil)* | — | Graylog / OpenSearch / LogScale (Splunk: reference-only, EULA) | +8–16 GB | ⚠ | mixed |

Always include `core`; every other tier reads its lakehouse. Catalog and engine are genuinely swappable —
that's the point of an open table format under one read contract (`SPEC.md` §5).

**Presets bundle these tiers by SOC ingest scale** (10× steps), so you pick by the scale you plan around:
`soc-10gb` (small SOC, core + detection) → `soc-100gb` (mid, + Trino federation +
agentic AI) → `soc-1tb` (large, + ClickHouse + StarRocks + OCSF route + dashboards) → `soc-10tb` (+ the SIEM
foil for buy-vs-build). The old RAM-budget names (`laptop`/`workstation`/`server`/`compare`) still work as
aliases. The preset picks the architecture that ingest scale calls for; the single host proves the
architecture, while the SDW Lab carries the measured scale sweeps to 100M+ rows.

## Component selection & swaps (bake-offs)

Because the stack is open under one read contract, components are genuinely swappable — and a swap is
*verifiable*: same Iceberg data, different backend, identical answers (`./moar verify`). The tested swaps and
the remaining candidates, each with a reason, drawing on the peers' choices (Lisa Cao, Jiahong Que, Zach Schmerber):

| Tier | default | swap candidates | reason to swap | status |
|---|---|---|---|---|
| **L** object store | MinIO | **SeaweedFS** (Lisa, q3) · RustFS · Ceph | footprint, since SeaweedFS is **~10× lighter** | **tested: identical 125 RDP on both, same OCSF batch — `./moar swap-store`** |
| **I** catalog | iceberg-rest-fixture | **Nessie** (Java, git-branching) · **Lakekeeper** (Rust, Postgres-backed) · Polaris/Unity (governance) | production-readiness / footprint / governance | **tested: all three (iceberg-rest, Nessie, Lakekeeper) return the identical 125 RDP over the same MinIO — `./moar swap-catalog`** |
| **I** table format | Iceberg | **DuckLake** (SQL-catalog + Parquet on the same store) | a different format, not a catalog drop-in | **tested: DuckLake writes the same OCSF batch and returns the identical 125 RDP — `./moar swap-format`** |
| **E** engine | DuckDB + Trino + ClickHouse | **StarRocks** (MPP) · **Dremio** (federation, via Nessie) | workload fit (real-time vs MPP vs federation) | **tested: 5-engine `moar verify` green — DuckDB, Trino, ClickHouse, StarRocks, Dremio all 1000/125** |
| **R** router | Vector | **Tenzir** (security-native: Sigma/OCSF/STIX) · **Fluent Bit** (lightest) | security-awareness vs footprint | **tested: all three (Vector, Tenzir, Fluent Bit) emit the identical OCSF Authentication record on the same raw Okta event — `./moar swap-router`** |

The discipline is to never swap blind: the answer has to stay identical across the swap. Every swap above now
ships as a one-command check that writes or reads the same OCSF data through the alternative backend and
asserts the answer doesn't move — `./moar swap-store` across MinIO and SeaweedFS, `./moar swap-catalog` across
three catalog implementations, `./moar swap-format` across Iceberg and DuckLake, `./moar swap-router` across
three routers, and `./moar verify` across five engines. Trino's S3 endpoint is templated via
`${ENV:S3_INTERNAL_ENDPOINT}` so a store swap flows through to Trino as well, and the whole
core/lab/detection/engine path follows `S3_INTERNAL_ENDPOINT`.

**Why several independent implementations of each.** A single alternative proves a swap is possible; agreement
across several independent codebases proves the read contract is real rather than a quirk of one implementation.
The catalog check runs the Java reference fixture, Nessie (Java/Quarkus, with git-style branching), and
Lakekeeper (Rust, Postgres-backed), and all three return the same 125 RDP. The engine gate spans DuckDB
(embedded), Trino (JVM/MPP), ClickHouse (C++ OLAP), StarRocks (C++/MPP), and Dremio (JVM federation), and all
five return 1000/125. The router check spans Vector (Rust/VRL), Tenzir (C++, security-native TQL), and Fluent
Bit (C, with a Lua transform), and all three emit the identical OCSF Authentication record. DuckLake is the
deliberately different case, because it isn't an Iceberg REST catalog at all but a SQL-catalog table format, so
`swap-format` proves the weaker and more honest claim that the data and the answer survive a format change, not
that the catalog is a drop-in.

**Dremio takes a different path to the same answer.** Dremio OSS doesn't ship the Iceberg REST catalog source,
since that's gated to Enterprise and Cloud, so it can't read the iceberg-rest catalog the other four engines
read. The path that does work on OSS is a Nessie source, set up through an idempotent REST choreography
(`config/dremio/setup-dremio.sh`: bootstrap → login → source → query) rather than the declarative boot-time
catalog every other engine uses. So Dremio reads the Nessie-written copy of the table — the same logical OCSF
data, independently committed through a second catalog — and `./moar verify` folds it in when it's running
(or `./moar verify-dremio` runs it on its own). It returns the identical 1000/125, so answer-equality now spans
five engines and two catalogs. The honest caveat is that the
equality holds on the Nessie copy, not the byte-identical iceberg-rest files, so if Dremio-on-Iceberg-REST ever
lands in OSS it becomes a cleaner same-table check. (Getting it working took three corrections over the
documented config: `secure:false` because MinIO is plain HTTP and Dremio otherwise attempts TLS, an
`awsRootPath` with no leading slash, and the real object-store credentials.)

**What stays in the lab.** Some of what the `/writing` essays compare isn't a stack-service swap at
all. The codec and encoder read-lever (`lakehouse/encoder-is-the-read-lever`, `same-codec-different-sizes`) is a
write-config knob, and Arrow Flight / ADBC vs JDBC (`lakehouse/arrow-flight-sql`, `arrow-adbc`) is an
engine↔client transport concern, so both live in `sdw-lab-benchmarks`, where the variable can be isolated,
rather than as a profile here.

## Head-to-head vs the SIEM foil

The swaps prove the open components are interchangeable; the foil tier asks the buy-vs-build question directly.
`./moar compare` loads the same OCSF corpus into the open lakehouse (Parquet on MinIO, queried by DuckDB) and
into OpenSearch — the open schema-on-read SIEM representative, since Splunk is reference-only under its EULA —
then runs the same three queries on each (`lab/foil_compare.py`). The verify-the-answer discipline extends to
the incumbent: the total, the `dst_port=3389` needle, and the `dst_port` distribution come back identical from
both. What differs is what you'd expect once it's measured. At 200,000 events the lakehouse holds the same data
in **1.6 MB of columnar Parquet against OpenSearch's 11.5 MB index, a ~7× footprint gap** that comes from the
inverted index plus the retained `_source`, and it holds near 7× at smaller scale too. Latency at this size is
close on all three and the lakehouse edges most, but the one query the SIEM wins is the low-selectivity needle,
which is the term index doing its job, and that's the shape the architecture predicts even though a single host
with the SIEM queried over HTTP can't isolate the magnitude. The two findings that don't depend on scale or
transport are the ones to carry: the answers agree, and the columnar store is several times smaller.

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
4. **Vortex vs Parquet** — the one real new sub-Parquet format; footprint+read, correctness-gated. **Built +
   tested** (`sdw-lab-benchmarks/ocsf-vortex-format`): the "install-blocked" turned out to be a rename — the
   PyPI `vortex-array` is yanked with the note "Renamed to vortex-data," and `vortex-data` (0.74.0, now an LF
   AI & Data project) installs fine. On a seeded-random OCSF corpus Vortex reads faster (decode-to-Arrow
   ~1.7–2.6×, the `dst_port=3389` needle ~3.3–4×) at a write cost and a **scale-dependent** size cost (~9%
   smaller than zstd-Parquet at 100K, ~26% larger at 1M), with identical answers across formats — a single-
   digit× read win, not the vendor's 10–100×. Honest scoping: each format read by its native reader (no engine
   on DuckDB 1.5.3 reads Vortex; the extension targets 1.4 LTS), and Vortex is **not yet an Iceberg data file
   format** (Iceberg 1.11.0 shipped the pluggable File Format API; the Vortex plugin is open issue
   apache/iceberg#15416), so it stays a standalone-format datapoint, not a swap-in for the table format here.
5. **SIMD-dispatch determinism** (force NONE/AVX2/AVX512, byte-identical results) and **Parquet modular
   encryption interop**. **Built + tested** (`sdw-lab-benchmarks/parquet-determinism-encryption`): SIMD is
   byte-identical across vector widths (not a risk), but the cross-engine *float* aggregate splits 3 ways
   (DuckDB / pyarrow-Polars-DataFusion / chDB) while int-sum/count/min/max stay bit-identical — so exact-typed
   answers are hashable for chain-of-custody, float-derived ones need a tolerance. And a PME-encrypted Parquet
   file is readable only by the implementer-with-key — every other engine is locked out, so at-rest encryption
   *inside* the file revokes the open read contract the swap story rests on (keep encryption at the volume/SSE
   layer for regulated data, or standardize on one PME engine + KMS).

Net-new #1 through #5 are all built, tested, and pushed (`sdw-lab-benchmarks`) — the Vortex arm (#4) is no
longer blocked now that the package is found under its renamed name. The Vortex-inside-Iceberg arm stays
future work, gated on the Iceberg File Format API plugin (apache/iceberg#15416).

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
| **engine-starrocks** | StarRocks reads the *same* Iceberg table via an Iceberg REST external catalog (enters at the soc-1tb tier), answer identical to the others (1000/125) |
| **engine-dremio** | Dremio (federation) reads the Nessie-written copy via a Nessie source + idempotent REST setup, answer identical (1000/125) — `moar verify` now agrees across **five** independent engine codebases |
| **detection** | a SigmaHQ rule → pySigma→SQL → run over the OCSF lakehouse, detected 125 RDP (the planted count) |
| **ai** | a *local* model (Ollama `gemma4:e4b`) ran a code-action hunt over the lakehouse via `./moar hunt`: it wrote `SELECT count(*) … WHERE dst_port=3389`, saw 125, and answered — fully air-gapped (only endpoint is the local model) |
| **graph** | functional via `./moar observe`: Prometheus scraping (2 targets up), Grafana DB ok, Loki ready, and a metric flows the full **push→pushgateway→Prometheus** round-trip — observability proven, not just "containers up" |
| **route** | Vector/VRL raw→OCSF transform proven by `vector test` (Okta auth → class_uid 3002, activity_id, user, src_ip) |
| **pipeline (end-to-end)** | `./moar pipeline`: raw Okta → Tenzir route → OCSF → landed in `ocsf.authentication` Iceberg (8 rows) → brute-force detection flags the planted source 198.51.100.66 (6 failed auths) — the full raw-to-detection chain, not tiers in isolation |
| **healthcheck (data-health gate)** | `./moar healthcheck`: a subset of the Foundation data-health checks (Layer-3 quality dims + the verifier-guard coda — no NULL in a filter set, epoch-UTC timestamps, cross-engine count agrees) run over the live `ocsf.network_activity` → HEALTHY on clean data; the same checks caught every injected fault in the demonstrator |
| **bench (workload × engine)** | `./moar bench`: same Iceberg table, four workload shapes, each engine over its persistent protocol (answers gated first). At 1M/single-host **DuckDB sweeps every gated workload** (4–14ms; ClickHouse close, then StarRocks, Trino) — H-ARCH-02's per-workload specialization is a scale/concurrency property a single host doesn't surface; the scale crossover is the clickhouse-vs-duckdb lab bench |
| **correlate (well-connected)** | `./moar correlate`: two OCSF sources (auth + network) in one open store, joined on `src_ip` — surfaces a brute-force→RDP attacker (8 failed auths + 5 RDP) that each source alone can't (1 ambiguous IP each); the well-connected pillar a per-tool SIEM fragments (H-NDR-FEDERATION-01) |
| **baselines (foil)** | head-to-head vs OpenSearch (schema-on-read SIEM) via `./moar compare`: same OCSF data + queries → **identical answers**, lakehouse **~7× less storage** (1.6 vs 11.5 MB at 200K), SIEM term index edges the needle while the columnar scan favors the lakehouse |
| **swap: L** | **MinIO and SeaweedFS return the identical 125 RDP for the same OCSF batch (`./moar swap-store`) — the object store is interchangeable; SeaweedFS ~10× lighter for the small tier** |
| **swap: I (catalog)** | **iceberg-rest, Nessie, and Lakekeeper all return the identical 125 RDP over the same MinIO (`./moar swap-catalog`) — three independent catalog codebases under one read contract** |
| **swap: I (format)** | **Iceberg and DuckLake return the identical 125 RDP for the same OCSF batch on the same MinIO (`./moar swap-format`) — the data and the answer survive a table-format change** |
| **swap: R** | **Vector, Tenzir, and Fluent Bit all emit the identical OCSF Authentication record (class_uid 3002, activity 1/2, user, src_ip) on the same raw Okta event (`./moar swap-router`)** |

The central claim is proven end-to-end: write once via pyiceberg, read through any engine, and **verify the
answers agree** — across five engines, across a MinIO/SeaweedFS store swap, across three catalog implementations
and a DuckLake format swap, and across three routers that normalize the same raw Okta event to the identical
OCSF Authentication record.

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

The **ai tier** needs a local Ollama serving a model on the host, bound beyond loopback
(`OLLAMA_HOST=0.0.0.0:11434`) so a container can reach it. The agent then auto-resolves the endpoint — it tries
`OLLAMA_URL`, the WSL host IP (`./moar` injects it as `OLLAMA_HOST_IP`), then `host.docker.internal` and
`localhost`, using the first that answers — so it works whether Ollama runs on the Docker host or in a separate
WSL2 distro, under NAT or mirrored networking. `./moar hunt` and a plain `docker compose exec ai python
/ai/agent.py` both work; override with `OLLAMA_URL` / `OLLAMA_MODEL`.

## Read alongside (securitydataworks.com)

The stack is the runnable form of the architecture the essays argue; the [SDW Lab](https://securitydataworks.com/lab/)
is the measured evidence each tier ships with.

- the architecture — [MOAR](https://securitydataworks.com/thesis/moar/) · the differentiator — [The query engine returned the wrong answer](https://securitydataworks.com/writing/detection/silent-wrong-answer/) (why `./moar verify` exists)
- **L/I (lakehouse + catalog)** — [Iceberg vs Delta](https://securitydataworks.com/writing/lakehouse/iceberg-vs-delta/) · [V4 vs DuckLake](https://securitydataworks.com/writing/lakehouse/v4-vs-ducklake/) · [the encoder is the read lever](https://securitydataworks.com/writing/lakehouse/encoder-is-the-read-lever/) · catalogs: [decision](https://securitydataworks.com/writing/catalogs/catalog-decision/) / [governance](https://securitydataworks.com/writing/catalogs/catalog-governance/)
- **E (engines)** — [ClickHouse at petabyte](https://securitydataworks.com/writing/engines/clickhouse-petabyte/) · [DuckDB threat hunting](https://securitydataworks.com/writing/engines/duckdb-threat-hunting/) · [push vs pull engines](https://securitydataworks.com/writing/engines/push-pull-engines/)
- **R (route)** — [Vector](https://securitydataworks.com/writing/pipelines/vector-data-router/) · [Tenzir](https://securitydataworks.com/writing/pipelines/tenzir-pipe-layer/) · [Cribl vs Tenzir](https://securitydataworks.com/writing/pipelines/cribl-vs-tenzir/)
- **detection / Sigma** — [Sigma portability](https://securitydataworks.com/writing/sigma/sigma-portability/)
- **methodology behind the bake-offs** — [How to run a benchmark that doesn't lie](https://securitydataworks.com/writing/economics/how-to-run-a-benchmark-that-doesnt-lie/) · [Independent measurement](https://securitydataworks.com/writing/economics/independent-measurement/)
