# Security-operations semantic model (Apache Ossie, draft)

A draft semantic model for security operations, written in the Apache Ossie (incubating) core
spec: OCSF event tables as fact datasets, MITRE ATT&CK, MITRE ATLAS, D3FEND and Sigma as
dimension and bridge datasets, and SOC metrics defined once in Ossie's portable SQL (`OSSIE_SQL_2026`) so a BI tool or an
agent reads the same definition of "false-positive rate" instead of each dashboard re-deriving it.
Security has schemas, metric catalogs and coverage scores, and as far as I could find no open,
machine-readable layer that binds the metric definitions to the schemas, which is the gap this
file is a first attempt at. The argument is written up at
<https://securitydataworks.com/writing/ai/security-semantic-layer>.

- `security-operations.ossie.yaml` — 9 datasets, 7 relationships, 11 metrics (alert volume,
  false-positive rate, mean time to detect, and coverage metrics over ATT&CK, D3FEND and ATLAS).

## Status, read before using

- **Draft against a draft spec.** Written for Ossie core spec `0.3.0.dev0`, which is explicitly
  mutable until the first `0.3.0-incubating` release. First written 2026-07-23 against `0.2.0.dev0`,
  migrated on 2026-11-17 (at `apache/ossie` main `a0d15d2`) to the one-model-per-document root layout
  (apache/ossie#383) and the new version constant (#691), and moved on 2026-11-25 to portable
  expressions, as the next section explains. All three files pass the upstream validator
  (`validation/validate.py`: JSON Schema, name uniqueness, relationship references, SQL parse) at
  main `7b8ed65` and at the head of the pending PR #817 (`8e92f42`), both as read on 2026-11-25.
- **Version pins.** OCSF 1.8.0, D3FEND 1.4.0, ATLAS v2026.06, pySigma-pipeline-ocsf v0.1.2.
- **Live versus declared tables.** `moar.ocsf.authentication` and `moar.ocsf.network_activity` are
  live Iceberg tables in this repo's `docker/` stack. `detection_finding`, `sigma_rules` and the
  `moar.ref.*` reference tables are declared targets whose content exists as files and has not
  been materialized as tables yet, so metrics over them won't compute until it is.
- **Coverage is structure, not efficacy.** Every coverage metric describes what detection content
  and defenses exist at design time, never what would have stopped an attack, and the model's
  `ai_context` tells consuming agents to keep that distinction.
- **Expression language.** Every field and metric expression is the top-level `sql`, written in
  `OSSIE_SQL_2026`, the one expression language the spec defines, and there are no per-dialect
  blocks. An engine-specific variant could be added later, but see the next section before doing so,
  because the key that holds such variants is about to be renamed.
- **Ontology layer.** `security-ontology.ossie.yaml` expresses D3FEND's offense–artifact–defense
  shape as Ossie ontology concepts, and `security-ontology.mapping.ossie.yaml` maps three of its
  concepts onto this model's reference datasets, as separate documents per apache/ossie#458. Both
  pass the validator at every commit named above, but the validator does not parse `derived_by` expressions, so a
  pass says nothing about the two derivations, which are illustrative.
- Not a production dependency: Ossie had no ASF-blessed release as of 2026-11-25.

## Change on 2026-11-25: portable expressions, so the model survives the `dialects` rename

Until this change every expression sat in a `dialects` list with a single `ANSI_SQL` entry. Ossie
PR #817, which goes to lazy consensus on the dev list on 2026-12-01, renames that key to
`nonportable_dialects` with no alias, so the model as it stood would fail the validator with 98
errors the day the PR merges, while a plain rename of the key fails on today's main. The two keys
can't both be valid at once, and an expression that carries the portable `sql` alongside either of
them passes on one side of the merge and fails on the other (I tested both combinations), so the
only form that validates before and after #817 is `sql` on its own. That is what the model now uses
for all 38 fields and 11 metrics.

For the 38 fields and four of the metrics the text of each expression is unchanged and only its
key moved, so nothing they compute changes. The other seven metrics were rewritten slightly, and
in each case the new form says what the metric's description already claimed:

- The six rate metrics (`false_positive_rate`, `detection_content_coverage_rate`,
  `detect_phase_coverage_rate`, `telemetry_reachable_technique_rate`, `atlas_attack_bridge_rate`,
  `failed_authentication_rate`) divide one integer count by another, which under a bare `ANSI_SQL`
  label left the result to the engine, and an engine that truncates integer division (Trino or
  PostgreSQL, for example) would have returned 0 for any rate below 1. `OSSIE_SQL_2026` defines `/`
  as true division (apache/ossie#687), so the rates are now fractions on every engine, and I also
  cast each numerator to `DOUBLE`, which the spec doesn't require but which keeps the expression
  right for anything that passes the text to an engine without translating it.
- `mean_time_to_detect_hours` was `AVG(DATEDIFF(HOUR, ...))`, which averaged whole hours, either
  truncated or counted as clock-hour boundaries depending on the engine, so a finding raised 10:59
  to 11:01 counted as 0 hours on some engines and 1 on others. It is now
  `AVG(DATEDIFF(second, ...) / 3600.0)`, which averages fractional hours exact to within a second
  per finding. PR #816, also closing on 2026-12-01, would define `DATEDIFF` as counting the
  boundaries of the unit crossed, and its own text recommends this same seconds-then-divide form
  for elapsed time, so the metric means the same thing whether or not #816 merges. The number it
  returns does change from before, by up to an hour per finding, which is the correction rather
  than a side effect.

The other metrics (`alert_volume`, `techniques_with_detection_content`,
`detection_blind_technique_count`, `atlas_realized_technique_count`) are counts and sums whose text
is unchanged. A validator pass is a parse check, not an evaluation, so the meaning comparison above
comes from reading each expression against `core-spec/expression_language.md` rather than from
running the metrics, and the #816 part of it rests on that PR's text, because #816 changes
documentation only and the validator behaves the same with or without it.

| Ossie commit (read 2026-11-25) | `security-operations` | `security-ontology` | mapping |
|---|---|---|---|
| main `7b8ed65` | passes | passes | passes |
| PR #817 head `8e92f42` | passes | passes | passes |
| main + #817 + PR #816 head `0b13bc9`, merged locally | passes | passes | passes |
| the pre-change model on #817, for comparison | 98 errors | passes | fails, because it validates the model first |

Both PRs could still change before they merge, so the run is worth repeating once they land.

## Validate it yourself

```bash
git clone https://github.com/apache/ossie
cd ossie && uv run validation/validate.py ../ossie-semantic-model/security-operations.ossie.yaml
uv run validation/validate.py --schema ontology/ontology.json ../ossie-semantic-model/security-ontology.ossie.yaml
uv run validation/validate.py --schema ontology/mapping.json ../ossie-semantic-model/security-ontology.mapping.ossie.yaml
```

Check the validator's own README for its current arguments and dependencies, since the spec and
tooling are moving.
