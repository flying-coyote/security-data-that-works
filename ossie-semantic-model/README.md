# Security-operations semantic model (Apache Ossie, draft)

A draft semantic model for security operations, written in the Apache Ossie (incubating) core
spec: OCSF event tables as fact datasets, MITRE ATT&CK, MITRE ATLAS, D3FEND and Sigma as
dimension and bridge datasets, and SOC metrics defined once in governed ANSI SQL so a BI tool or an
agent reads the same definition of "false-positive rate" instead of each dashboard re-deriving it.
Security has schemas, metric catalogs and coverage scores, and as far as I could find no open,
machine-readable layer that binds the metric definitions to the schemas, which is the gap this
file is a first attempt at. The argument is written up at
<https://securitydataworks.com/writing/ai/security-semantic-layer>.

- `security-operations.ossie.yaml` — 9 datasets, 7 relationships, 11 metrics (alert volume,
  false-positive rate, mean time to detect, and coverage metrics over ATT&CK, D3FEND and ATLAS).

## Status, read before using

- **Draft against a draft spec.** Written for Ossie core spec `0.3.0.dev0` (`core-spec/ossie-schema.json`
  on `apache/ossie` main at `a0d15d2`), which is explicitly mutable until the first `0.3.0-incubating`
  release. First written 2026-07-23 against `0.2.0.dev0`, then migrated on 2026-11-17 to the
  one-model-per-document root layout (apache/ossie#383) and the new version constant (#691). It passes
  the upstream validator (`validation/validate.py`: JSON Schema, name uniqueness, relationship
  references, SQL parse) at that commit.
- **Version pins.** OCSF 1.8.0, D3FEND 1.4.0, ATLAS v2026.06, pySigma-pipeline-ocsf v0.1.2.
- **Live versus declared tables.** `moar.ocsf.authentication` and `moar.ocsf.network_activity` are
  live Iceberg tables in this repo's `docker/` stack. `detection_finding`, `sigma_rules` and the
  `moar.ref.*` reference tables are declared targets whose content exists as files and has not
  been materialized as tables yet, so metrics over them won't compute until it is.
- **Coverage is structure, not efficacy.** Every coverage metric describes what detection content
  and defenses exist at design time, never what would have stopped an attack, and the model's
  `ai_context` tells consuming agents to keep that distinction.
- **Dialects.** Ossie's dialect list has no ClickHouse, DuckDB or Trino entry, so the MOAR engines
  read these definitions through `ANSI_SQL` only.
- Not a production dependency: Ossie had no ASF-blessed release as of 2026-07-23.

## Validate it yourself

```bash
git clone https://github.com/apache/ossie
cd ossie && uv run validation/validate.py ../ossie-semantic-model/security-operations.ossie.yaml
```

Check the validator's own README for its current arguments and dependencies, since the spec and
tooling are moving.
