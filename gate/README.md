# `gate/` — the OCSF field-mapping type-consistency check

The runnable check at the heart of this repo: it catches the wrong field mapping that silently kills a
detection — *before* it reaches production, with no machine-learning model in the loop. It grounds every
`source_field → ocsf_path` mapping two independent ways (the type of the OCSF path, and the type of the source
field) and asks an OWL reasoner (ELK, via ROBOT) whether both can be true. A type-preserving mapping stays
*satisfiable*; a type-crossing one becomes *unsatisfiable* and fails the build. The full walkthrough — the
three scenarios, the disjointness layer, and the honest limits — is in the [top-level README](../README.md).

```bash
./run.sh                                        # the demo, in Docker (no Java/ROBOT install)
LOCAL=1 python3 validate_ocsf_mapping.py your_mappings.csv   # run it on your own two-column CSV
```

## What's here

- `validate_ocsf_mapping.py` — the check (grounding + the eight-artifact disjointness layer + `--selfcheck`)
- `run.sh` — runs all three scenarios in Docker
- `mappings/` — a correct example and a wrong one · `expected/` — captured pass/fail output
- plain-language terms (ontology, grounding, disjointness, reasoner, unsatisfiable) → [`../glossary.md`](../glossary.md)

## Read alongside (securitydataworks.com)

- [The field-mapping anti-pattern](https://securitydataworks.com/writing/ocsf/field-mapping-anti-pattern/) — the failure mode this check objects to
- [The query engine returned the wrong answer](https://securitydataworks.com/writing/detection/silent-wrong-answer/) · [What your data means](https://securitydataworks.com/writing/detection/what-your-data-means/) — the broader silent-failure thesis
- [Six schemas into OCSF](https://securitydataworks.com/writing/ocsf/six-schemas-into-ocsf/) — the crosswalk corpus this was validated on · [OCSF × D3FEND](https://securitydataworks.com/writing/ocsf/ocsf-d3fend/) — where the disjointness artifacts come from · [LLM OCSF mapping](https://securitydataworks.com/writing/ocsf/llm-ocsf-mapping/)
- measured evidence: the OCSF-mapping-fidelity and deterministic-mapper benches in the [SDW Lab](https://securitydataworks.com/lab/) (`github.com/flying-coyote/sdw-lab-benchmarks`)
- the per-vendor *scoring* this check deliberately leaves out is the paid [Capability Matrix](https://securitydataworks.com/matrix/)
