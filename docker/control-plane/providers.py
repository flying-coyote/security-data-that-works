"""Single source of truth for MOAr stack component options.

Replaces the label<->code maps and the per-tool pros/cons that were duplicated
across several marimo cells. Each component category is an ordered list of
`Provider` records; the UI renders labels, the spec file stores codes, and the
pros/cons + operational notes are read straight off the registry.

Notes are deliberately conservative and sourced. Cross-component
incompatibilities (the reactive warnings) live in `compat_notes()`.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Provider:
    code: str          # value written to moar-spec.yaml
    label: str         # value shown in the UI
    pros: str = ""
    cons: str = ""


# --- Component catalogs -------------------------------------------------------

STORAGE = [
    Provider("seaweedfs", "SeaweedFS",
             pros="Fast small-file lookups, lightweight, built-in volume replication; fits local S3 testing.",
             cons="AWS STS credential vending isn't served, so REST catalogs need static S3 keys + path-style."),
    Provider("minio", "MinIO",
             pros="Standard S3 compliance, robust console, rich developer ecosystem.",
             cons="Higher memory/CPU footprint than SeaweedFS in multi-node setups."),
    Provider("aws_s3", "AWS S3",
             pros="Managed, durable, zero-ops object storage; the cloud baseline.",
             cons="Network latency and egress/retention cost at scale; ties you to AWS."),
    Provider("wasabi", "Wasabi",
             pros="S3-compatible, flat low-cost storage with no egress fees.",
             cons="Fewer native integrations; single-vendor SaaS dependency."),
    Provider("dell_ecs", "Dell ECS",
             pros="On-prem S3-compatible object store for regulated/air-gapped sites.",
             cons="Appliance/licensing overhead; slower feature cadence than cloud S3."),
]

CATALOG = [
    Provider("polaris", "Polaris",
             pros="Multi-vendor-backed Iceberg REST catalog, pluggable RBAC/OPA/Ranger, ASF top-level governance.",
             cons="Needs an external relational backend (Postgres) for persistence."),
    Provider("nessie", "Nessie",
             pros="Git-like data versioning: branch, merge, and tag table snapshots.",
             cons="Performance limits under heavy concurrent writes; Dremio reflections don't persist on OSS 26.0."),
    Provider("lakekeeper", "Lakekeeper",
             pros="Rust Iceberg REST catalog with OpenFGA authz and a Vue admin console.",
             cons="Younger, single-origin project; its STS path also fails SeaweedFS multipart (use static keys)."),
    Provider("hive_metastore", "Hive Metastore (HMS)",
             pros="Universally supported by engines; the long-standing default.",
             cons="Thrift/JVM operational overhead; not REST-native."),
    Provider("unity_catalog_oss", "Unity Catalog OSS",
             pros="Open-sourced governance catalog with table/volume/function objects and lineage hooks.",
             cons="Self-hosted OSS edition lags the managed Databricks one; Iceberg REST support still maturing."),
    Provider("aws_glue", "AWS Glue",
             pros="Managed, zero-ops catalog tightly integrated with the AWS analytics stack.",
             cons="AWS-native: expects S3 and AWS IAM; not a fit for local/non-AWS object stores."),
]

INGEST = [
    Provider("vector", "Vector",
             pros="Rust-native, fast, declarative GitOps config, built-in VRL test harness.",
             cons="Read-only observability API (no config-push/control API; #24020)."),
    Provider("fluentbit", "Fluent Bit",
             pros="Tiny footprint (~20MB), ideal for Kubernetes sidecars and edge collection.",
             cons="Parser config is more fiddly than Vector's VRL."),
    Provider("nifi", "Apache NiFi",
             pros="Visual flow canvas, record-level data provenance, native Iceberg REST-catalog writes, preserves nested OCSF.",
             cons="Heavy JVM heap (24-32GB sweet spot); flows live in NiFi's registry, not git config-as-code."),
    Provider("cribl", "Cribl Stream",
             pros="Mature routing/reduction UI with strong enterprise pipeline ergonomics.",
             cons="Commercial licensing; SaaS/agent lock-in relative to open config-as-code."),
    Provider("tenzir", "Tenzir",
             pros="Security-native pipeline engine with an OCSF-aware data model.",
             cons="OCSF fidelity unaudited at scale (A-03); smaller ecosystem."),
]

QUERY = [
    Provider("datafusion", "DataFusion",
             pros="Embeddable Rust engine, no JVM, zero-copy Arrow-native; reads Polaris-Iceberg via iceberg-rust.",
             cons="One narrow edge: additive List<Struct> schema evolution across mixed-version Parquet (#20835)."),
    Provider("clickhouse", "ClickHouse",
             pros="Very fast aggregations and group-by threat hunts, low memory footprint.",
             cons="Reads Iceberg via icebergS3() not the REST catalog, so catalog-less reads can serve a stale snapshot."),
    Provider("starrocks", "StarRocks",
             pros="Graceful degradation under load, strong multi-table joins, native Arrow Flight SQL.",
             cons="Iceberg REST-catalog integration with Polaris is not yet stable/complete."),
    Provider("dremio", "Dremio",
             pros="Reflections-based acceleration, semantic layer, Arrow Flight native.",
             cons="Reflections don't persist over an external Nessie catalog on OSS 26.0; de-selected from the SDW reference stack."),
    Provider("duckdb", "DuckDB",
             pros="Zero-config single-process file-query champion; an excellent local correctness oracle.",
             cons="Single-process only (~10-analyst ceiling, A-14); DuckLake/Postgres delete-resurrection #1215 / wide-schema #1184."),
    Provider("trino", "Trino",
             pros="Mature distributed MPP SQL with broad connector coverage and federation.",
             cons="JVM coordinator/worker footprint; tuning effort for low-latency hunts."),
]

SCHEMA = [
    Provider("ocsf", "OCSF",
             pros="Vendor-backed cybersecurity schema (AWS, Splunk, CrowdStrike); nested, no flattening required.",
             cons="List-of-struct columns (e.g. observables[]) stress some engines (see DataFusion #20835)."),
    Provider("ecs", "ECS",
             pros="Flat key-value taxonomy optimized for keyword search and inverted-index speed.",
             cons="Limited structural depth, so nested joins/hunts get awkward."),
    Provider("splunk_cim", "Splunk CIM",
             pros="The de-facto field model across Splunk estates; rich, well-documented datamodels.",
             cons="Splunk-centric and search-time; needs mapping work to land cleanly in an open lakehouse."),
    Provider("asim", "ASIM",
             pros="Microsoft Sentinel's normalized schema, well-suited to Azure-native telemetry.",
             cons="Tied to the Microsoft ecosystem; mapping required for multi-vendor sources."),
    Provider("cef", "CEF",
             pros="Long-established, widely emitted by legacy appliances; simple to parse.",
             cons="Flat and lossy; poor fit for modern nested event detail."),
    Provider("raw", "Raw",
             pros="No normalization tax; preserves the source exactly for schema-on-read.",
             cons="Pushes all parsing/normalization cost to query time and to the analyst."),
]

CATEGORIES = {
    "storage": STORAGE,
    "catalog": CATALOG,
    "ingest": INGEST,
    "query": QUERY,
    "schema": SCHEMA,
}

# Defaults: the SeaweedFS + Polaris + Vector + DataFusion + OCSF reference stack.
# DataFusion leads (no-JVM, Arrow-native, and the Dremio reference pick was
# removed under the DeWitt clause); Dremio stays selectable.
DEFAULTS = {
    "storage": "seaweedfs",
    "catalog": "polaris",
    "ingest": ["vector"],
    "query": ["datafusion"],
    "schema": "ocsf",
}


# --- Lookups ------------------------------------------------------------------

def labels(group) -> list[str]:
    return [p.label for p in group]


def find(group, code) -> Provider | None:
    return next((p for p in group if p.code == code), None)


def label_for(group, code) -> str:
    p = find(group, code)
    return p.label if p else str(code)


def code_for(group, label) -> str | None:
    p = next((p for p in group if p.label == label), None)
    return p.code if p else None


def default_label(category) -> str:
    return label_for(CATEGORIES[category], DEFAULTS[category])


def default_labels(category) -> list[str]:
    group = CATEGORIES[category]
    return [label_for(group, c) for c in DEFAULTS[category]]


# --- Reactive compatibility / operational notes -------------------------------

def compat_notes(storage, catalog, query_codes, ingest_codes, schema):
    """Return [(level, title, body)] for the current selection.

    level == "warn"  -> a real cross-component incompatibility (rendered red)
    level == "info"  -> a single-component operational caveat (rendered muted)
    """
    q = set(query_codes or [])
    notes: list[tuple[str, str, str]] = []

    # Cross-component incompatibilities (the genuine "don't pair these" warnings).
    if catalog == "polaris" and "starrocks" in q:
        notes.append((
            "warn", "Polaris + StarRocks",
            "StarRocks' Iceberg REST-catalog integration with Apache Polaris isn't yet "
            "stable/complete. Validate catalog sync at deployment, or pair StarRocks with "
            "Hive Metastore / Glue (verify at engagement time).",
        ))
    if catalog == "nessie" and "dremio" in q:
        notes.append((
            "warn", "Nessie + Dremio",
            "Dremio Reflections do not persist over an Iceberg table on an external Nessie "
            "catalog on Dremio OSS 26.0 (materialization expires instantly). Use a Dremio-native "
            "catalog for reflections, or query Nessie with another engine.",
        ))
    if catalog == "aws_glue" and storage != "aws_s3":
        notes.append((
            "warn", "AWS Glue + non-AWS storage",
            "AWS Glue is AWS-native and expects S3 + IAM. Pair it with AWS S3, or pick "
            "Polaris / Nessie / Lakekeeper for a local or S3-compatible store.",
        ))

    # Single-component operational caveats (informational, not blocking).
    if catalog in ("polaris", "lakekeeper") and storage == "seaweedfs":
        notes.append((
            "info", "Polaris / Lakekeeper + SeaweedFS — use static keys",
            "AWS STS credential vending (AssumeRole) isn't served by SeaweedFS, so set the "
            "warehouse to static S3 keys + a path-style endpoint (Polaris #3640/#3742, "
            "Lakekeeper #8312). Pin Polaris >= 1.4.1 (CVE-2026-42810).",
        ))
    if "datafusion" in q:
        notes.append((
            "info", "DataFusion + nested OCSF",
            "DataFusion reads nested structs/lists/maps natively. The one known edge is "
            "*additive schema evolution* on List<Struct>: if a struct inside a list (e.g. "
            "observables[]) gains a new nullable field and you scan across mixed-version "
            "Parquet, planning can fail (apache/datafusion#20835, open, seen on 52.1.0). A "
            "single-schema OCSF table is unaffected — pin an explicit schema.",
        ))
    if "clickhouse" in q:
        notes.append((
            "info", "ClickHouse catalog-less reads",
            "ClickHouse reads Iceberg via icebergS3() rather than the REST catalog, which can "
            "serve a stale snapshot after a compaction rewrite. Route reads through the catalog "
            "or refresh the snapshot pointer.",
        ))
    if "duckdb" in q:
        notes.append((
            "info", "DuckDB scale ceiling",
            "DuckDB is single-process: roughly 10 concurrent analysts before S3 read-quota "
            "saturation (A-14). Ideal as a local oracle, not a shared engine. On DuckLake/Postgres "
            "watch delete-resurrection #1215 and wide-schema #1184.",
        ))
    if "dremio" in q:
        notes.append((
            "info", "Dremio note",
            "Dremio adds reflections + a semantic layer (Arrow Flight native), but reflections "
            "don't persist over external Nessie on OSS 26.0. The SDW reference stack leads with "
            "DataFusion; Dremio is selectable, not the default.",
        ))
    return notes
