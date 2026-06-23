# The MOAR console — documentation

The console is the marimo control plane that sits over the [MOAR reference stack](../README.md). It is not a
catalog of every component's features — each tool already has good vendor documentation, and this page links
you straight to it. What the console documents instead is the part no vendor ships: how an open, swappable
security-data lakehouse actually behaves once you wire these components together, where the integrations break,
and how to prove the foundation is sound before you trust an answer that comes out of it. So this page is three
things — how the console works, why it exists, and an extensively-evidenced catalog of the integration problems
between the components — and then it hands you to the vendor docs, noting the specific places where we measured
something the vendor docs don't tell you.

For the deploy-gate's internal contract (what each audit layer returns and how the verdict composes), see
[`CONTRACT.md`](CONTRACT.md). For the measured numbers behind every claim here, see the public
[`sdw-lab-benchmarks`](https://github.com/flying-coyote/sdw-lab-benchmarks) repository.

## How it works

The console threads one operator workflow end to end: pick the components your constraints allow, configure and
validate the OCSF transform, land data per OCSF class, let the data-health gate certify the foundation, run a
hunt over the landed OCSF, and read off the swap-cost when you want to change any component. The visual
flip-through below is a real screenshot of each view captured from the live app (regenerate it with
`bash flipthrough/build.sh` after a console change); with the demo stack down, the data-driven panels honestly
show their pre-audit states, because the gate never bluffs a pass.

### The guided walkthrough — the golden path

![Walkthrough](flipthrough/img/walkthrough.png)

The walkthrough is the operator workflow in one view: the OCSF mapping is validated, data lands per OCSF class,
the data-health gate certifies it, every engine agrees on the same query, a hunt fires over the landed OCSF, and
any component can be swapped with its cost read off. Everything below is one stage of this path.

### Startup › Strategy › Pick components

![Pick components](flipthrough/img/pick.png)

The constraint filter takes your hard limits (air-gap required, RAM budget, JVM-free, on-prem only) and scores
each candidate per layer with a caution/favor read, a reachable-N/M count, and a best-fit pick. It is the front
door of the architecture decision: you don't choose a component in the abstract, you choose the one your
constraints actually reach.

### Startup › Strategy › Vault & Matrix

![Vault and Matrix](flipthrough/img/vault.png)

Two consultant-mode surfaces plus the evidence runner: the Strategy Vault (typed OKF notes) and the
per-criterion scored Capability Matrix loaded from the private vault — never the repo, so the paid scoring stays
paid. The evidence runner ties a recommendation back to the lab result that supports it.

### Startup › Configuration

![Configuration](flipthrough/img/config.png)

Configure the stack spec, validate the OCSF transform (the Vector VRL) *before* provisioning, and read the
data-health gate as a compact verdict chip. You cannot deploy onto an incoherent selection — the gate blocks a
provision when the configuration can't cohere, which is the cheapest place to catch the mistake.

### Flow › Land

![Land](flipthrough/img/land.png)

Land data into the lakehouse per OCSF class. This is where the ingestion path (Vector / Tenzir / Fluent Bit →
OCSF → Iceberg) actually writes, and where the mapping fidelity the gate later checks is established or lost.

### Flow › Health — the center of gravity

![Health](flipthrough/img/health.png)

The data-health gate is the console's center of gravity. It refuses to certify the foundation GREEN until each
measurable layer actually passes: source health (L1), stack reachable (L2, catalog live), data quality (L3 —
freshness, small-files, orphans, schema-conformance), and cross-tool gap (L4, exact-match entity reconciliation
across sources). The honesty of the gate is in its vocabulary — a layer with no data to run against reads
`unmeasured`, a check with no machinery reads `unwired`, a proven layer whose TTL elapsed decays to `stale`, and
none of those is ever shown as a pass. A clean foundation reads AMBER by design until the audits have something
real to measure. The full per-layer contract is in [`CONTRACT.md`](CONTRACT.md).

### Flow › Migrate

![Migrate](flipthrough/img/migrate.png)

The intent-driven migration cockpit: pick one of six migration intents and the panel reads off each component's
reversibility, the swap-cost of changing it, and a live data-health check that proves the swap preserved the
answer. This is where "open and swappable" stops being a slogan and becomes a number you can show a board.

### Analyze

![Analyze](flipthrough/img/analyze.png)

Coverage analysis grounded in measurement, not inventory: the dark-spot recommendations (which OCSF classes to
land next), the measured-firing detection coverage, and the D3FEND leads for missed techniques carried with
their provenance — intent-blind co-occurrence leads (trust 0.25) are never laundered into the coverage count.
This view is the design-time companion to the measured C5 coverage bench.

## Why it exists

OCSF + Iceberg + Parquet on object storage is table stakes now — plenty of vendors write OCSF to your S3. Almost
none ship an open-all-the-way-down, self-hostable stack, and *none* ship the operational knowledge of what
breaks when you actually compose these open components yourself. That knowledge is the reason this console
exists and the reason this page is mostly a catalog of integration problems rather than a feature tour: a vendor
documents its own product working in isolation, and has no incentive to document the place where its product
quietly disagrees with the next one in the chain. The data-health gate is the standing instrument that catches
those disagreements before they become a wrong answer in an investigation; the catalog below is the accumulated
record of the specific disagreements we have measured.

## The integration-problems catalog

Each entry is a place where composing two open components produced behavior that neither component's
documentation predicts. Every one is version-bound and traces to a primary source (a GitHub issue we verified at
the source, or a reproducible lab bench). These are friction-and-maturity findings, not refutations — the
components are genuinely worth running — and several are the kind a point release fixes, so re-check the version
before repeating them. They are grouped by the layer where the friction concentrates.

### Catalog / metadata layer

- **Project Nessie silently downgrades Iceberg V3 tables to V2.** On Nessie 0.107.5 the OSS pyiceberg + Nessie
  path cannot exercise Iceberg V3 row-lineage at all: the catalog silently downgrades a V3 table to V2
  (pyiceberg [#1551](https://github.com/apache/iceberg-python/issues/1551) open; DuckDB `iceberg_scan()` does not
  expose `_row_id`; pyiceberg overwrite/upsert collapses snapshot history). The vendor material presents V3 as
  available; the OSS catalog path takes it away without an error. Row-lineage is reachable on Spark/Java writers
  plus managed catalogs (recent Polaris, Unity, Snowflake-Polaris), not on the fully-open path today. First-party
  smoke 2026-05-25.
- **DuckLake `CREATE TABLE` past 1,600 columns fails on a Postgres catalog.** DuckLake
  [#1184](https://github.com/duckdb/ducklake/issues/1184) (open) — the OLTP 1,600-column wall, hit by a
  fully-flattened OCSF event with all profiles and observables, or a wide normalized EDR/firewall table. The
  catalog's SQL design is what buys DuckLake its flat planning cost and also where this ceiling lives.
- **DuckLake cross-store delete conflict resurrects deleted rows.** DuckLake
  [#1215](https://github.com/duckdb/ducklake/issues/1215) (open) — concurrent inlined-delete and parquet-delete
  on the same row both commit when the sizes straddle `data_inlining_row_limit`, so a correctly-deleted row
  reappears on the next scan. This is the class of bug that matters most for retention expiry or a tombstoned
  false-positive that you need to *stay* gone.
- **DuckLake Postgres connection-pool exhaustion — fixed in a point release.** DuckLake
  [#1031](https://github.com/duckdb/ducklake/issues/1031): "all 8 connections in use," wrong on DuckDB 1.5.2 +
  DuckLake 1.0, **fixed 1.5.2 → 1.5.3**. The reason answer-equality and the gate stay *standing* controls: a bug
  a point release fixes is one a later release can reintroduce.
- **DuckLake concurrent CREATE-OR-REPLACE crashes on aarch64.** DuckLake
  [#1248](https://github.com/duckdb/ducklake/issues/1248) — SIGSEGV on Linux aarch64 under concurrent
  CREATE-OR-REPLACE; clean on x86_64 / DuckDB 1.5.2. An architecture-specific failure mode that a single-arch CI
  never surfaces.
- **DuckLake commit fails after a transient catalog disconnect.** DuckLake
  [#1023](https://github.com/duckdb/ducklake/issues/1023) — a commit fails after a transient TCP/metadata-catalog
  disconnect; the Postgres-MVCC long-connection dependency makes batch jobs brittle against a flaky network.
- **ClickHouse catalog-less `icebergS3()` can serve a stale snapshot.** Reading Iceberg directly via
  `icebergS3()` without a live catalog can return data from an older snapshot than the table's current one,
  because there is no catalog to resolve the latest metadata pointer — a correctness trap that looks like a
  successful read.

### Engine / reader layer

- **A fast reader can return a silently wrong answer.** This is the finding that made cross-engine
  answer-equality a standing control rather than a one-off. Across twelve distinct publishable Parquet readers
  reading the byte-identical 10M-row file, **ten agreed and two were silently wrong** — chDB's Bloom-filter
  undercount (wrong on 4.1.8, **fixed in 4.1.9**) and fastparquet's `PLAIN_DICTIONARY` mis-decode (**still wrong
  on 2026.5.0**). No error in either case; the dashboard looks green. `moar verify` exists because of exactly
  this. Source: `sdw-lab-benchmarks/clickhouse-vs-duckdb/results/MULTI-ENGINE-CORRECTNESS.md`, first-party Tier B.
- **Dremio Reflections do not persist over a Nessie-versioned Iceberg table.** On Dremio OSS 26.0 a reflection
  materializes and then reports `available_until` = epoch 0 (`1969-12-31T23:59:59.999Z`), so it never accelerates.
  The root cause is documented Dremio behavior, not a bug to fix blindly: epoch 0 is a **sentinel** Dremio writes
  whenever a reflection is running/failing/disabled, and `CAN_ACCELERATE` is gated on
  `AVAILABILITY_STATUS == AVAILABLE`; over an external Iceberg table the refresh completes as a no-op
  ("successful materialization already exists") that never reaches AVAILABLE. The workaround documented for
  S3-promoted datasets (`FORGET METADATA` → `REFRESH METADATA` → refresh the reflection → poll `sys.reflections`
  for `acceleration_status = CAN_ACCELERATE` before trusting it) is **not verified for the native
  Iceberg-via-Nessie path** — that stays an open question. This is a functional integration anomaly, stated
  without any performance figures.
- **StarRocks async-materialized-view refresh evaluates against stale state.** StarRocks' MV layer is
  async-refresh (the default refresh interval is not real-time-incremental), so a correlation detection built on
  an MV can fire against state that is up to a refresh-interval old — a silent-degradation path for any temporal
  rule that assumes current data.

### Storage format layer

- **Parquet is not byte-reproducible by default.** A DuckDB → Parquet write is not byte-identical across runs
  because parallel execution does not fix the row order; pin `threads=1` or add an `ORDER BY` if you need a stable
  content hash (e.g. to prove an air-gapped mirror matches). The default looks deterministic and isn't.
- **Format read-performance is confounded by the writer, not the codec.** A naïve format comparison attributes
  speed to the compression codec when the dominant variable is which engine *wrote* the Parquet (row-group
  sizing, dictionary and statistics decisions). A fair comparison pins the writer; otherwise you measure the
  writer and call it the format.

### Ingestion / mapping layer

- **Positional log formats cascade a single omission silently; self-describing formats fail loud and
  localized.** On the real published specs of three vendors, a mid-record version change in a positional format
  (PAN-OS) put **35 of 47 fields silently wrong** — every field after the inserted one shifts, and nothing errors
  — while a self-describing header (Zeek `#fields`) and a JSON format (CloudTrail) showed **zero silent**
  misalignments. The security consequence is concrete: a parser keyed on a documented field name can map the
  wrong value with full confidence. Source: `sdw-lab-benchmarks/spec-vs-emitted-integrity/`, Tier B, three named
  real vendors.
- **A populated OCSF field is not a correct OCSF field.** OCSF normalization guarantees the *shape*, not that the
  value in a field is the right value — the context-collapse failure mode. The data-health gate's L2 mapping
  check exists because a green "field present" count is exactly the signal that hides a class-right /
  activity-wrong mapping.

### Detection layer

- **pySigma compiles a correlation rule windowless on backends without a window primitive.** A Sigma
  `event_count` correlation with a `timespan` compiles to `… GROUP BY … HAVING count >= N` with the time window
  silently dropped on OpenSearch PPL and on a second SQLite backend — it then over-fires (PPL precision 0.286
  against 50 decoy actors). A rule that "ported" by compiling can have lost its window, which is the worst kind of
  coverage loss because it looks deployed. Whether the SQL lakehouse engines preserve the window (they have the
  primitive) is the open question the SIGMA-EXEC lakehouse leg is pre-registered to measure. Source:
  `sdw-lab-benchmarks/ocsf-sigma-detection/`.

### Startup / orchestration

- **The Iceberg REST catalog accepts connections before auth is ready.** On a cold start the REST endpoint opens
  before authentication is fully initialized, so an engine that connects in that window fails in a way that reads
  like a measurement disagreement rather than the orchestration race it is — a draw-1/2 artifact we traced to
  startup ordering, not to the engines. `moar` staggers the heavy tiers on bring-up so a cold start doesn't OOM,
  a lesson learned the hard way.

## Component → vendor documentation

The console does not re-document these tools; configure each from its own docs. URLs verified 2026-06-22.

| Layer | Component | Official documentation | Iceberg integration page |
|-------|-----------|------------------------|--------------------------|
| Object store | MinIO | see anomaly note below | — |
| Object store | SeaweedFS | [github.com/seaweedfs/seaweedfs/wiki](https://github.com/seaweedfs/seaweedfs/wiki) | — |
| Table format | Apache Iceberg | [iceberg.apache.org/docs/latest](https://iceberg.apache.org/docs/latest/) · [REST catalog spec](https://iceberg.apache.org/rest-catalog-spec/) | — |
| Catalog | Project Nessie | [projectnessie.org/nessie-latest](https://projectnessie.org/nessie-latest/) | see Nessie/V3 anomaly above |
| Catalog | Lakekeeper | [docs.lakekeeper.io](https://docs.lakekeeper.io/) | — |
| Engine | Trino | [trino.io/docs/current](https://trino.io/docs/current/) | [Iceberg connector](https://trino.io/docs/current/connector/iceberg.html) |
| Engine | ClickHouse | [clickhouse.com/docs](https://clickhouse.com/docs) | [Iceberg table engine](https://clickhouse.com/docs/engines/table-engines/integrations/iceberg) |
| Engine | StarRocks | [docs.starrocks.io](https://docs.starrocks.io/) | [Iceberg catalog](https://docs.starrocks.io/docs/data_source/catalog/iceberg/iceberg_catalog/) |
| Engine | Dremio | [docs.dremio.com](https://docs.dremio.com/) | Iceberg-native (no discrete connector page) |
| Engine | DuckDB | [duckdb.org/docs/current](https://duckdb.org/docs/current/) | [iceberg extension](https://duckdb.org/docs/current/core_extensions/iceberg/overview) |
| Route | Vector | [vector.dev/docs](https://vector.dev/docs/) | — |
| Route | Tenzir | [docs.tenzir.com](https://docs.tenzir.com/) | — |
| Route | Fluent Bit | [docs.fluentbit.io/manual](https://docs.fluentbit.io/manual) | — |
| Observability | Prometheus | [prometheus.io/docs](https://prometheus.io/docs/) | — |
| Observability | Grafana | [grafana.com/docs/grafana/latest](https://grafana.com/docs/grafana/latest/) | — |
| Observability | Grafana Loki | [grafana.com/docs/loki/latest](https://grafana.com/docs/loki/latest/) | — |

### Vendor-documentation anomalies (the exceptions worth knowing before you go read the docs)

- **MinIO's open-source documentation is no longer hosted.** Around October 2025 MinIO pulled the hosted
  community docs; `docs.min.io` now serves **AIStor**, the commercial enterprise product under the MinIO Software
  License, not the AGPL object store. The community docs path renders AIStor content too. The honest pointers for
  OSS MinIO are the source repositories — [github.com/minio/minio](https://github.com/minio/minio) and the docs
  source at [github.com/minio/docs](https://github.com/minio/docs) (MinIO's own guidance is now "build and host
  it yourself"). We link the repos rather than hand you the AIStor URL as if it were the community docs.
- **SeaweedFS has no docs site by design** — the GitHub wiki is the canonical documentation; `seaweedfs.com` is
  the enterprise upsell.
- **Iceberg V3 row-lineage reads as available but is not, on the OSS Nessie path** — see the catalog-layer entry
  above. Read the Iceberg V3 docs with that caveat: the spec describes the feature; the open catalog path does
  not yet deliver it.
- **Dremio has no discrete Iceberg-connector page** because it treats Iceberg as a native table format rather
  than an external connector — don't go hunting for a connector page that doesn't exist; the integration is
  documented throughout the main docs.

---

The honest version of this document is that it will go stale at the version boundary — several of the issues
above are open and may close the way DuckLake #1031 did, so the discipline is the same one the gate enforces on
the data: re-check the version before you repeat the claim. Where a claim here carries a measured number, the
number lives in the lab, not in this prose, so the chain from "we found X" to the bench that found it is always
one click away.
