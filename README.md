# security-data-that-works

A small, runnable demo of one idea: the wrong field mapping that silently kills a detection is catchable by a
reasoner before it reaches production, with no machine-learning model in the loop. Clone it, run one command, and
watch a correct mapping pass and a deliberately wrong one fail. Around that check sit a public statement of what
good looks like across five categories of security data ([SPEC.md](SPEC.md)) and three more runnable demos,
listed under [What's in the repo](#whats-in-the-repo).

## The problem this is about

The worst detection failure is the rule that never fires at all, and does it quietly. Someone writes a
reasonable detection, it passes review, it deploys clean, and it sits there for months matching nothing, because
the field it keys on was mapped somewhere upstream to a path that holds the wrong kind of thing. There's no error
and no exception; the query compiles, the search runs, it returns zero results every time, and zero results from
a detection looks exactly like a quiet network.

This is hard to catch because schema validation checks the *shape* of a field and says nothing about its
*meaning*. A mapping can put an IP address in a field typed to hold an IP address and still be wrong, because it
put the *source* address where the schema meant the *destination*, or mapped a user account onto a field that
means a process. The shape is right and the meaning is crossed, and nothing in the normal toolchain objects, so
this repo adds the check that does.

## What this is, and what it is not

The check answers one yes/no question per mapping row: *is this mapping type-consistent?* It catches one class of
error, an actor-versus-object type crossing such as a user value landing in a process slot or a file path landing
in a network-endpoint slot, and it gives the same verdict whoever or whatever produced the mapping, because the
verdict comes from an OWL reasoner rather than a model.

It does not score a vendor, rank fidelity, or measure how much of a claimed schema is actually covered, and it
doesn't catch enum narrowing, structure collapse or taxonomy mismatch, which are a different fidelity axis. The
method around it is open and lives alongside it: [SPEC.md](SPEC.md) states what good looks like across all five
categories, and [build-your-own-mcp/](build-your-own-mcp/) makes the build-your-own case with curated references.
What stays out of this public repo is the per-vendor *scoring*: applying the method to score specific vendors is
the Capability Matrix, which is paid. So the check is open and runnable, the spec around it is open, and the
per-vendor scores are the paid part. This repo is a front door to the open projects underneath (D3FEND, OCSF,
Sigma, the ROBOT/ELK toolchain), and it doesn't fork any of them.

## Quickstart

```bash
git clone https://github.com/flying-coyote/security-data-that-works.git
cd security-data-that-works
./gate/run.sh
```

That runs everything in Docker, so you don't install Java or ROBOT; the first run builds a small image from
[`docker/Dockerfile`](docker/Dockerfile). If you already have a ROBOT jar and a JDK and would rather skip the
container, run `LOCAL=1 ./gate/run.sh`, which reads `$ROBOT_JAR` (default `/tmp/robot.jar`).

To check your own mappings, point the validator at a two-column CSV of `source_field,ocsf_path`:

```bash
ROBOT_JAR=/path/to/robot.jar python3 gate/validate_ocsf_mapping.py your_mappings.csv
```

The validator exits 0 when every type-testable row is consistent, 1 when at least one row is a type crossing, and
2 when the reasoner itself failed or the input could not be used (Java missing, a corrupt jar, a parse error, a
timeout, a missing or empty CSV), so a broken toolchain
stops a CI job instead of reading as a pass. `./gate/test_gate.sh` is the regression test: it diffs the three
scenarios below against [`gate/expected/`](gate/expected/) and checks that a broken jar exits 2 from both the
validator and `run.sh`.

## What you just saw

The demo runs the same wrong mapping twice, once without the check and once with it, and the contrast between
those two runs is what the demo is for.

The samples below are trimmed to the validator's output and `run.sh`'s verdict line; the scenario headers and
the JVM warnings are left out.

**Scenario 1: a correct mapping, with the disjointness layer.** Seven type-consistent mappings, nothing flagged,
and the build passes.

```text
[selfcheck] disjointness layer consistent? YES
checked 7 mappings · 7 type-testable · 0 type-crossing flagged (with disjointness layer)
    => exit 0  PASS
```

**Scenario 2: a wrong mapping, without the layer.** This models the off-the-shelf situation. D3FEND 1.6.0 does
carry some disjointness axioms, but none of them separates any two of the eight artifacts these mappings touch
(see [Evidence and limits](#evidence-and-limits)), so the reasoner has no grounds to object, the wrong mapping
slips through, and the exit code is zero. That silence is the bug.

```text
checked 3 mappings · 3 type-testable · 0 type-crossing flagged (WITHOUT disjointness layer)
  (nothing flagged — off the shelf, the reasoner has no basis to object; the wrong mapping passes silently)
    => exit 0  PASS (silently: the wrong mapping slips through)
```

**Scenario 3: the same wrong mapping, with the layer.** Now each type crossing becomes a class that can't
logically exist, the reasoner flags it, and the build breaks.

```text
[selfcheck] disjointness layer consistent? YES
checked 3 mappings · 3 type-testable · 3 type-crossing flagged (with disjointness layer)
  ✗ username  →  process.name   (source is UserAccount, target is Process — disjoint)
  ✗ file_path  →  src_endpoint.ip   (source is File, target is NetworkNode — disjoint)
  ✗ process_name  →  actor.user.name   (source is Process, target is UserAccount — disjoint)
    => exit 1  FAIL, caught, as it should be
```

The same mapping that passed silently in Scenario 2 fails the build in Scenario 3, because the disjointness layer
gives the reasoner something to object to.

## How the check works

![The gate grounds each mapping row twice, once by its OCSF path and once by its source field, and asks the ELK reasoner whether both groundings can hold given the disjointness layer: satisfiable exits 0, unsatisfiable exits 1, and a reasoner failure exits 2.](docs/img/gate-flow.svg)

[`gate/validate_ocsf_mapping.py`](gate/validate_ocsf_mapping.py) grounds every mapping two independent ways: the
D3FEND artifact the OCSF path targets (resolved by its deepest entity segment, so `process.name` is a Process) and
the D3FEND artifact the source field names (a regex typer over the field's tokens, so `username` is a
UserAccount). It then writes each testable row as an OWL class that is a subclass of both artifacts and asks ELK,
run through ROBOT, whether that class can have members. A type-preserving mapping stays *satisfiable*; a
type-crossing one becomes *unsatisfiable*, a class that can't have any members, and fails the build. Rows the
typer can't ground are counted but not tested, which is why the output reports how many rows were type-testable.

The disjointness layer lives inside the validator and is proposed upstream (see [CONTRIBUTING.md](CONTRIBUTING.md)).
It asserts eight D3FEND digital artifacts pairwise disjoint at the identity level: a process is not the file it was
executed from, a credential is not the file it's stored in, and so on. The judgment that "executed-from" and
"stored-in" are *relations* rather than identity is what makes the disjointness sound rather than an over-claim.
A `--selfcheck` mode reasons over the layer alone and confirms it is internally consistent, and it catches the one
real trap, that `NetworkSession` is a subclass of `Session`, which is why those two are deliberately not asserted
disjoint. Every run with the layer starts with that selfcheck.

The validator does not load D3FEND itself. It declares the artifact classes it needs plus the single
`NetworkSession ⊑ Session` axiom, which keeps the demo to a few seconds and is why Scenario 2 *models* the
off-the-shelf ontology rather than running it; the separate check against the real D3FEND 1.6.0 release is
described below.

## Evidence and limits

This is a strong first-pass check, not a certification, and the evidence is Tier B. The numbers below come from
two validation runs recorded with the check's development, and both measure the false-positive side; the catch
side is true by construction, for the reason each paragraph gives.

On a 925-row, six-schema crosswalk corpus, 231 of 231 injected type crossings were flagged. That figure follows
from how the corruptions were built (each correctly typed mapping was remapped to a disjoint artifact, which the
layer then rejects by definition), so it shows the check runs end to end rather than measuring a catch rate. The
measured result on that corpus is zero over-disjointness false positives, with about 7 false alarms from the
approximate field-typer.

On a separate 83-field mapping the check had never seen, 22 of the 83 fields were type-testable, because the regex
typer grounds only field names that match its rules. The 22 injected crossings on those fields were again flagged
by construction, and the measured result is zero false positives on the 22 sound mappings. Neither run uses a
held-out set of confirmed human mapping errors, so what this evidence supports is that the layer didn't
manufacture false alarms on real, presumed-correct mappings, and it says nothing yet about how many real-world
mapping errors the check would catch.

The off-the-shelf claim in Scenario 2 was checked against the D3FEND 1.6.0 release (tag `1.6.0` of
[d3fend/d3fend-ontology](https://github.com/d3fend/d3fend-ontology), commit `91629ab`). Its source ontology
(`src/ontology/d3fend-protege.ttl`) carries three pairwise `owl:disjointWith` assertions and six
`owl:AllDisjointClasses` groups, plus one more group in the catalog extension (`src/ontology/extensions/d3fend-catalog.ttl`);
the counts are unchanged at tags 1.4.0 and 1.5.0. None of them separates any two of the eight artifacts. Reasoning
both files with ELK (ROBOT 1.9.6) plus a probe class under each of the 28 artifact pairs leaves every probe
satisfiable, while the two positive-control probes, under the disjoint pairs `Agent`/`Artifact` and
`FastSymbolicLink`/`SlowSymbolicLink`, come back unsatisfiable. [`gate/probe_d3fend.sh`](gate/probe_d3fend.sh)
reruns that check against any tag.

The disjointness adjudication is the hard part and the place this could break at scale. A credential can be stored
in a file, so asserting that a credential is never a file would break a valid mapping and manufacture a false
alarm, and the false-positive risk rises as the artifact set widens. Treat the eight-artifact layer as a starting
set to extend carefully rather than a finished ontology.

## What's in the repo

Each demo makes one part of the spec executable, evidence first.

| Path | What it is |
| ---- | ---------- |
| [`gate/`](gate/) | the OCSF field-mapping type-consistency check described above, which is the data-health-validation category of [SPEC.md §1](SPEC.md#1-data-health-validation-does-the-data-mean-what-the-schema-says) made executable, with its demo, regression test and captured output |
| [`docker/`](docker/) | the MOAR Reference Stack: an open, tiered, swappable security-data lakehouse you stand up in layers, with a `verify` command that checks every running engine returns the same answer over the same Iceberg table |
| [`foundation-healthcheck/`](foundation-healthcheck/) | a scoped demonstrator of the four-layer data-health gate (source health, flow health, data quality, cross-tool gaps) on synthetic data |
| [`build-your-own-mcp/`](build-your-own-mcp/) | the case, plus curated references, for building your own security-data MCP server rather than adopting a vendor black box |
| [`SPEC.md`](SPEC.md) | what good looks like across the five categories of security data, the frame the demos grow into |
| [`glossary.md`](glossary.md) | plain-language definitions of ontology, semantics, grounding, disjointness, reasoner and unsatisfiable |
| [`docs/READING.md`](docs/READING.md) | the essays on securitydataworks.com that argue each demo in full, mapped per directory |
| [`SELF-AUDIT-2026-06.md`](SELF-AUDIT-2026-06.md) | a dated intent self-audit of this repo (2026-06-21) |

## Versioning and reproducibility

The repo has no tagged releases yet, so cite or pin a commit SHA; [CHANGELOG.md](CHANGELOG.md) records dated
changes. The gate's toolchain is pinned in [`docker/Dockerfile`](docker/Dockerfile): ROBOT 1.9.6, downloaded from
the ontodev/robot GitHub release, on the `eclipse-temurin:17-jre-jammy` base image, and the build checks the jar against its sha256. That base is a tag
rather than a digest, so the JRE patch level can move between builds; as of 2026-11-17 the regression test passes
on both that image and a host OpenJDK 25 with the same ROBOT jar. The validator's D3FEND class IRIs use the
`http://d3fend.mitre.org/ontologies/d3fend.owl#` namespace, and the OCSF side is grounded by path segment, so it
isn't tied to one OCSF schema version, which also means a renamed OCSF object would need a new entry in the
validator's segment table.

## Contributing

The pieces underneath are open: D3FEND, OCSF, Sigma and the pySigma OCSF pipeline, and the ROBOT/ELK reasoner
toolchain. If the gate flags a coarse mapping in your data, or you find an artifact pair that should be disjoint
and isn't, the fix belongs upstream rather than in a private patch. [CONTRIBUTING.md](CONTRIBUTING.md) says where
each kind of fix goes and what a pull request to this repo should keep true; run `./gate/test_gate.sh` before
opening one that touches `gate/`.

## Citation

If you use the gate or the spec in your work, [CITATION.cff](CITATION.cff) carries the citation metadata, and
GitHub's "Cite this repository" button reads it. Cite the commit SHA you used, since there are no tagged releases.

## License

Apache-2.0. See [LICENSE](LICENSE).
