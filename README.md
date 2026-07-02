# security-data-that-works

A small, runnable demo of one idea: the wrong field mapping that silently kills a detection
is catchable by a reasoner, before it ever reaches production, with no machine-learning model
in the loop. Clone it, run one command, and watch a correct mapping pass and a deliberately
wrong one fail.

## The problem this is about

The worst detection failure isn't a rule that fires wrong. It's a rule that never fires at all
and does it quietly. Someone writes a reasonable detection, it passes review, it deploys clean,
and it sits there for months matching nothing, because the field it keys on was mapped somewhere
upstream to a path that holds the wrong kind of thing. No error, no exception, no red text. The
query compiles, the search runs, it returns zero results every time, and zero results from a
detection looks exactly like a quiet network.

The reason this is so hard to catch is that schema validation only checks the *shape* of a
field, not its *meaning*. A mapping can put an IP address in a field that is typed to hold an IP
address and still be wrong, because it put the *source* address where the schema meant the
*destination*, or mapped a user account onto a field that means a process. The shape is right and
the meaning is crossed, and nothing in the normal toolchain objects.

This repo is the check that objects. It is also the flagship runnable example of something larger: a public
statement of what good looks like across the five categories of security data ([SPEC.md](SPEC.md)), and the
case plus the curated references for building your own MCP server rather than adopting a vendor's black box
([build-your-own-mcp/](build-your-own-mcp/)). The check below is the data-health-validation category made
executable; the rest of the spec grows the same way, evidence first.

## Quickstart

```bash
git clone <this repo> && cd security-data-that-works
./gate/run.sh
```

That runs everything in Docker, so you don't install Java or ROBOT. If you already have a ROBOT
jar and a JDK and would rather skip the container, run `LOCAL=1 ./gate/run.sh` (it reads
`$ROBOT_JAR`, default `/tmp/robot.jar`).

## What you just saw

The demo runs the same wrong mapping twice, once without the check and once with it. The contrast
is the whole point.

**Scenario 1 — a correct mapping, with the disjointness layer.** Seven type-consistent mappings;
nothing flagged; the build passes.

```
checked 7 mappings · 7 type-testable · 0 type-crossing flagged (with disjointness layer)
=> exit 0  PASS
```

**Scenario 2 — a wrong mapping, without the layer.** This is the off-the-shelf situation: D3FEND
ships only three disjointness assertions in the whole ontology, and none of them cover the
artifacts your core mappings touch, so the reasoner has no grounds to object and the wrong mapping
slips through silently. The exit code is zero. That silence is the bug.

```
checked 3 mappings · 3 type-testable · 0 type-crossing flagged (WITHOUT disjointness layer)
  (nothing flagged — off the shelf, the reasoner has no basis to object; the wrong mapping passes silently)
=> exit 0  PASS (silently)
```

**Scenario 3 — the same wrong mapping, with the layer.** Now each type-crossing becomes a class
that can't logically exist, the reasoner flags it, and the build breaks.

```
checked 3 mappings · 3 type-testable · 3 type-crossing flagged (with disjointness layer)
  ✗ username  →  process.name   (source is UserAccount, target is Process — disjoint)
  ✗ file_path  →  src_endpoint.ip   (source is File, target is NetworkNode — disjoint)
  ✗ process_name  →  actor.user.name   (source is Process, target is UserAccount — disjoint)
=> exit 1  FAIL — caught
```

The same mapping that passed silently in Scenario 2 fails the build in Scenario 3, because the
disjointness layer gives the reasoner something to object to. Run it against your own mappings by
pointing the validator at a two-column CSV of `source_field,ocsf_path`:

```bash
LOCAL=1 python3 gate/validate_ocsf_mapping.py your_mappings.csv
```

## What each piece is

- **`gate/validate_ocsf_mapping.py`** — the check. It grounds every mapping two independent ways:
  the type of the OCSF path it targets, and the type of the source field itself. Then it asks an
  OWL reasoner (ELK, run through ROBOT) whether the two groundings can both be true. A
  type-preserving mapping stays *satisfiable*; a type-crossing one becomes *unsatisfiable* (a class
  that can't have any members) and fails the build. No model is in that loop, so the verdict is the
  same whoever or whatever produced the mapping.
- **The disjointness layer** (inside the validator, and proposed upstream — see CONTRIBUTING).
  Eight D3FEND digital artifacts asserted pairwise-disjoint at the identity level: a process is not
  the file it was executed from, a credential is not the file it's stored in, and so on. The
  judgment that "executed-from" and "stored-in" are *relations*, not identity, is what makes the
  disjointness sound rather than an over-claim. A `--selfcheck` mode proves the layer is internally
  consistent (it catches the one real trap, that `NetworkSession` is a subclass of `Session`, so
  those two are deliberately not asserted disjoint).
- **`gate/mappings/`** — a correct example and a wrong one, so the demo has something to pass and
  something to fail. **`gate/expected/`** — what a pass and a fail look like, captured.
- **`glossary.md`** — plain-language definitions of the handful of terms (ontology, semantics,
  grounding, disjointness, reasoner, unsatisfiable) if any are unfamiliar.

## Honest limits

This is a strong first-pass check, not a certification, and it's worth being precise about the
evidence. It's Tier B: a hand-authored disjointness layer over eight artifacts, validated on a
925-row six-schema crosswalk corpus (231 of 231 injected type-crossings caught, zero
over-disjointness false positives) and on a separate 83-field mapping it had never seen (22 of 22
caught, zero false positives). The catch rate is measured on *injected* corruptions, not a
held-out set of confirmed human errors, so it's a strong first-pass validation rather than a field
trial. The disjointness adjudication is the hard part and the place this could break at scale: a
credential can be stored in a file, so asserting that a credential is never a file would break a
valid mapping and manufacture a false alarm, and the false-positive risk rises as the artifact set
widens. Treat the eight-artifact layer as a starting set to extend carefully, not a finished
ontology.

## What this is not

This check answers one yes/no question per mapping: *is this type-consistent?* It does not score a
vendor, rank fidelity, or measure how much of a claimed schema is actually covered. The method around it
is open and lives alongside it — [SPEC.md](SPEC.md) states what good looks like across all five categories,
and [build-your-own-mcp/](build-your-own-mcp/) makes the build-your-own case with curated references. What
stays out of this public repo is the per-vendor *scoring*: applying the method to score specific vendors is
the Capability Matrix, which is paid. So the check is open and runnable, the spec around it is open, and the
per-vendor scores are the paid part. This repo is a front door to the open projects underneath (D3FEND,
OCSF, Sigma, the ROBOT/ELK toolchain), not a fork of them.

## The runnable demos in this repo

Each demo makes one part of the spec executable, evidence-first:

- **[`gate/`](gate/)** — the OCSF field-mapping type-consistency check (the silent-wrong-mapping catcher
  above). The data-validation category, made executable.
- **[`docker/`](docker/)** — the **MOAR Reference Stack**: an open, tiered, swappable security-data lakehouse
  you stand up in layers, with a `verify` gate that cross-checks every running engine returns the *same*
  answer over the same Iceberg table.
- **[`foundation-healthcheck/`](foundation-healthcheck/)** — a scoped demonstrator of the four-layer
  data-health gate (source health → flow health → data quality → cross-tool gaps) on synthetic data.
- **[`build-your-own-mcp/`](build-your-own-mcp/)** — the case plus curated references for building your own
  security-data MCP server rather than adopting a vendor black box.
- **[`SPEC.md`](SPEC.md)** — what good looks like across the five categories of security data, the frame the
  demos above grow into.

## Read it alongside the writing (securitydataworks.com)

The code here is the runnable half of an argument the [essays](https://securitydataworks.com/writing/) make in
full, and the [SDW Lab](https://securitydataworks.com/lab/) is the measured evidence behind both. The map:

**The whole repo**
- [The query engine returned the wrong answer](https://securitydataworks.com/writing/detection/silent-wrong-answer/) — the silent-failure thesis these demos embody
- [Foundation · Data health](https://securitydataworks.com/thesis/foundation/) — the gate every downstream project assumes
- [Independent measurement](https://securitydataworks.com/writing/economics/independent-measurement/) · [How to run a benchmark that doesn't lie](https://securitydataworks.com/writing/economics/how-to-run-a-benchmark-that-doesnt-lie/) — why the verification, not the speed, is the product

**`gate/` — OCSF field-mapping validation**
- [The field-mapping anti-pattern](https://securitydataworks.com/writing/ocsf/field-mapping-anti-pattern/) · [What your data means](https://securitydataworks.com/writing/detection/what-your-data-means/)
- [Six schemas into OCSF](https://securitydataworks.com/writing/ocsf/six-schemas-into-ocsf/) · [OCSF × D3FEND](https://securitydataworks.com/writing/ocsf/ocsf-d3fend/) · [LLM OCSF mapping](https://securitydataworks.com/writing/ocsf/llm-ocsf-mapping/)

**`docker/` — the MOAR Stack**
- [MOAR](https://securitydataworks.com/thesis/moar/) · [Iceberg vs Delta](https://securitydataworks.com/writing/lakehouse/iceberg-vs-delta/) · [V4 vs DuckLake](https://securitydataworks.com/writing/lakehouse/v4-vs-ducklake/) · [the encoder is the read lever](https://securitydataworks.com/writing/lakehouse/encoder-is-the-read-lever/)
- [ClickHouse at petabyte](https://securitydataworks.com/writing/engines/clickhouse-petabyte/) · [DuckDB threat hunting](https://securitydataworks.com/writing/engines/duckdb-threat-hunting/) · the route tier: [Vector](https://securitydataworks.com/writing/pipelines/vector-data-router/) / [Tenzir](https://securitydataworks.com/writing/pipelines/tenzir-pipe-layer/) · catalogs: [decision](https://securitydataworks.com/writing/catalogs/catalog-decision/) / [governance](https://securitydataworks.com/writing/catalogs/catalog-governance/) · [Sigma portability](https://securitydataworks.com/writing/sigma/sigma-portability/)

**`foundation-healthcheck/`** — see [its README](foundation-healthcheck/) for the per-layer essay links (foundation, the downstream MOAR / DetectFlow / MLOps-hunting projects, the lab).

**`build-your-own-mcp/`**
- [MCP for data engineering](https://securitydataworks.com/writing/ai/mcp-for-data-engineering/) · [the MCP-server landscape (research)](https://securitydataworks.com/research/)

## Contribute back

The pieces underneath are all open: D3FEND, OCSF, Sigma and the pySigma OCSF pipeline, and the
ROBOT/ELK reasoner toolchain. If the gate flags a coarse mapping in your data, or you find an
artifact pair that should be disjoint and isn't, the fix belongs upstream rather than in a private
patch. See [CONTRIBUTING.md](CONTRIBUTING.md) for where each kind of fix goes. This repo is a front
door to those projects, not a fork of them.

## License

Apache-2.0. See [LICENSE](LICENSE).
