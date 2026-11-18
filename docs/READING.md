# Reading list: the essays behind each demo

The code in this repo is the runnable half of an argument the [essays on securitydataworks.com](https://securitydataworks.com/writing/) make in full, and the
[SDW Lab](https://securitydataworks.com/lab/) is the measured evidence behind both. This page maps each directory
to the essays that argue it; the repo's front page is [README.md](../README.md).

## The whole repo

- [The query engine returned the wrong answer](https://securitydataworks.com/writing/detection/silent-wrong-answer/): the silent-failure thesis these demos embody
- [Foundation · Data health](https://securitydataworks.com/thesis/foundation/): the gate every downstream project assumes
- [Independent measurement](https://securitydataworks.com/writing/economics/independent-measurement/) · [How to run a benchmark that doesn't lie](https://securitydataworks.com/writing/economics/how-to-run-a-benchmark-that-doesnt-lie/): why the verification, not the speed, is the product

## `gate/`: OCSF field-mapping validation

- [The field-mapping anti-pattern](https://securitydataworks.com/writing/ocsf/field-mapping-anti-pattern/) · [What your data means](https://securitydataworks.com/writing/detection/what-your-data-means/)
- [Six schemas into OCSF](https://securitydataworks.com/writing/ocsf/six-schemas-into-ocsf/) · [OCSF × D3FEND](https://securitydataworks.com/writing/ocsf/ocsf-d3fend/) · [LLM OCSF mapping](https://securitydataworks.com/writing/ocsf/llm-ocsf-mapping/)

## `docker/`: the MOAR Reference Stack

- [MOAR](https://securitydataworks.com/thesis/moar/) · [Iceberg vs Delta](https://securitydataworks.com/writing/lakehouse/iceberg-vs-delta/) · [V4 vs DuckLake](https://securitydataworks.com/writing/lakehouse/v4-vs-ducklake/) · [the encoder is the read lever](https://securitydataworks.com/writing/lakehouse/encoder-is-the-read-lever/)
- [ClickHouse at petabyte](https://securitydataworks.com/writing/engines/clickhouse-petabyte/) · [DuckDB threat hunting](https://securitydataworks.com/writing/engines/duckdb-threat-hunting/) · the route tier: [Vector](https://securitydataworks.com/writing/pipelines/vector-data-router/) / [Tenzir](https://securitydataworks.com/writing/pipelines/tenzir-pipe-layer/) · catalogs: [decision](https://securitydataworks.com/writing/catalogs/catalog-decision/) / [governance](https://securitydataworks.com/writing/catalogs/catalog-governance/) · [Sigma portability](https://securitydataworks.com/writing/sigma/sigma-portability/)

## `foundation-healthcheck/`

See [its README](../foundation-healthcheck/) for the per-layer essay links (foundation, the downstream MOAR / DetectFlow / MLOps-hunting projects, the lab).

## `build-your-own-mcp/`

- [MCP for data engineering](https://securitydataworks.com/writing/ai/mcp-for-data-engineering/) · [the MCP-server landscape (research)](https://securitydataworks.com/research/)
