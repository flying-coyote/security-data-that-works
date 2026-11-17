# Changelog

This repo has no tagged releases, so entries are grouped by date rather than version. Each dated entry is taken
from a dated record that ships in the repo, named in the entry, and an undated change is left out rather than given
a guessed date. The format loosely follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The entries
before 2026-11-17 are dated evidence records that ship in the repo rather than a full history of changes to it.

## 2026-11-17

### Fixed

- `gate/validate_ocsf_mapping.py` failed open when the reasoner broke. It ignored ROBOT's exit code and treated a
  missing unsatisfiable-class dump as "nothing flagged", so a corrupt jar printed `selfcheck YES` and
  `0 type-crossing flagged` and exited 0 on the wrong mapping. It now exits 2 with the reasoner's error on any tool
  failure (corrupt or missing jar, Java not found, a non-zero ROBOT exit without a dump, a timeout). A missing,
  unreadable or empty mapping CSV, or one that parses to zero rows (a semicolon delimiter, say), also exits 2
  rather than passing on zero rows or reading as a caught crossing.
- `gate/run.sh` treated any non-zero exit in Scenario 3 as a successful catch. It now branches on the exact exit
  code, stops with exit 2 when the reasoner fails, and exits 0 only when all three scenarios behave as described.
- `docker/README.md`: the tier table's delimiter row had one more cell than its header, which stops GitHub
  rendering it as a table.
- `docker/control-plane/README.md`: removed eight image embeds that pointed at screenshots not in the tree, and
  merged two launch sections that disagreed about whether `./moar console` exists.
- `MOAR_PAID_MODE` has defaulted off since the 2026-07-19 fail-closed change in `paid_scoring.paid_mode()`, but the
  console's component view said the scored half "surfaces by default" and several `prove_*.py` comments said the
  default was on; both now match the code, and `prove_paid_scoring.py` asserts the off default.

### Added

- `gate/test_gate.sh`, a regression test that diffs the three scenarios against `gate/expected/` and checks that a
  corrupt or missing jar exits 2 from both the validator and `run.sh`, and that a bad input CSV exits 2;
  `UPDATE=1` rewrites the goldens.
- `gate/probe_d3fend.sh`, which re-derives the D3FEND off-the-shelf claim behind Scenario 2 against a release tag.
- `docker/Dockerfile` checks the ROBOT 1.9.6 jar against its sha256.
- `gate/expected/wrong-nolayer.out`, the captured Scenario 2 output.
- `docs/img/gate-flow.svg` and `docs/img/moar-tiers.svg`, diagrams of the gate and the MOAR presets.
- `docs/READING.md` (the essay index, moved out of the README), `CITATION.cff` and this changelog.

### Changed

- The "22 of 22" result on the 83-field mapping is restated as what it is: 22 of the 83 fields were
  type-testable, the 22 injected crossings are flagged by construction, and the measured result is zero false
  positives on the 22 sound mappings.
- "D3FEND ships only three disjointness assertions" is replaced by the counts at D3FEND 1.6.0 (three pairwise
  assertions, six multi-class groups, one more in the catalog extension) and the checked claim that none of them
  separates any two of the gate's eight artifacts.
- The README is restructured (what it is and is not, quickstart with the clone URL, how it works, evidence and
  limits, repo map, versioning, contributing, citation), and the prose in the main docs had a clarity pass.

## 2026-07-11

- `docker/control-plane/live-evidence.json` records passing live runs of detection regression, the Tenzir OCSF
  round-trip and the schema-drift check (`ran_at` 2026-07-11).

## 2026-06-21

- `docker/control-plane/live-evidence.json` records five-engine answer equality (DuckDB, Trino, ClickHouse,
  StarRocks, Dremio all returning 1000 rows and 125 RDP; `ran_at` 2026-06-21).
- [SELF-AUDIT-2026-06.md](SELF-AUDIT-2026-06.md), an intent self-audit of the repo.

## 2026-06-20

- [docker/MOAR-EVIDENCE-RUN-2026-06-20.md](docker/MOAR-EVIDENCE-RUN-2026-06-20.md): three-engine answer equality and
  the store, catalog, format and router swap checks.

## 2026-06-15

- [docker/MOAR-EVIDENCE-RUN-2026-06-15.md](docker/MOAR-EVIDENCE-RUN-2026-06-15.md): the `flow-gate`,
  `variant-mfa`, `commit-tax`, `cidr` and `concurrency-sweep` verbs, run and recorded.
