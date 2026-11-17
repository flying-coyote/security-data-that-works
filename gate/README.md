# `gate/`: the OCSF field-mapping type-consistency check

This is the runnable check at the center of the repo. It catches the wrong field mapping that silently kills a
detection, before it reaches production and with no machine-learning model in the loop, by grounding every
`source_field → ocsf_path` mapping two independent ways (the type of the OCSF path, and the type of the source
field) and asking an OWL reasoner (ELK, via ROBOT) whether both can be true. A type-preserving mapping stays
*satisfiable*, and a type-crossing one becomes *unsatisfiable* and fails the build. The full walkthrough, with the
three scenarios, the disjointness layer, a diagram and the evidence and limits, is in the
[top-level README](../README.md).

```bash
./run.sh                                                             # the demo, in Docker (no Java/ROBOT install)
ROBOT_JAR=/path/to/robot.jar python3 validate_ocsf_mapping.py your_mappings.csv  # your own two-column CSV
./test_gate.sh                                                       # regression test, in Docker
LOCAL=1 ROBOT_JAR=/path/to/robot.jar ./test_gate.sh                  # same, with a local Java + ROBOT
UPDATE=1 ./test_gate.sh                                              # rewrite expected/*.out after an intended output change
```

The validator exits 0 when every type-testable row is consistent, 1 when at least one row is a type crossing, and
2 when the reasoner itself failed or the input CSV is missing, empty or unparseable, so a broken Java or ROBOT
install stops a CI job instead of reading as a pass.

## What's here

- `validate_ocsf_mapping.py`: the check (grounding, the eight-artifact disjointness layer, and `--selfcheck`)
- `run.sh`: runs all three scenarios in Docker, or locally with `LOCAL=1`
- `test_gate.sh`: diffs the three scenarios against `expected/` and checks that a corrupt or missing ROBOT jar
  exits 2 from both the validator and `run.sh`, and that a missing, empty or semicolon-delimited CSV exits 2
- `probe_d3fend.sh`: re-derives the Scenario 2 claim, that D3FEND's own disjointness axioms separate none of
  the eight artifacts, against a D3FEND release tag (needs network access)
- `mappings/`: a correct example and a wrong one
- `expected/`: captured output for the correct mapping, the wrong mapping with the layer, and the wrong mapping
  without it (`wrong-nolayer.out`)
- plain-language terms (ontology, grounding, disjointness, reasoner, unsatisfiable) are in
  [`../glossary.md`](../glossary.md)

## Read alongside (securitydataworks.com)

- [The field-mapping anti-pattern](https://securitydataworks.com/writing/ocsf/field-mapping-anti-pattern/), the failure mode this check objects to
- [The query engine returned the wrong answer](https://securitydataworks.com/writing/detection/silent-wrong-answer/) and [What your data means](https://securitydataworks.com/writing/detection/what-your-data-means/), the broader silent-failure argument
- [Six schemas into OCSF](https://securitydataworks.com/writing/ocsf/six-schemas-into-ocsf/), the crosswalk corpus this was validated on; [OCSF × D3FEND](https://securitydataworks.com/writing/ocsf/ocsf-d3fend/), where the disjointness artifacts come from; [LLM OCSF mapping](https://securitydataworks.com/writing/ocsf/llm-ocsf-mapping/)
- measured evidence: the OCSF-mapping-fidelity and deterministic-mapper benches in the [SDW Lab](https://securitydataworks.com/lab/) (`github.com/flying-coyote/sdw-lab-benchmarks`)
- the per-vendor *scoring* this check deliberately leaves out is the paid [Capability Matrix](https://securitydataworks.com/matrix/)
