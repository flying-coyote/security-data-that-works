---
type: design
title: "Data-health gate contract — L1 / L2 / L3 / L4 → compute_gate verdict"
created: 2026-06-19
tags: [moar, control-plane, data-health-gate, contract, layer1, layer3, layer4]
---

# Data-health gate — cross-module contract

The console's spine is a composite data-health verdict that decides whether a deploy
is authorized and whether the stack may be certified GREEN. The verdict is a pure
function (`gate_logic.compute_gate`) so the proof harnesses exercise the exact logic
the UI renders. This note states the cross-module contract — what each audit returns,
how the gate combines them, and why a clean foundation reads AMBER today by design —
so a reader of the code understands the gate without reconstructing it from
`MOAR-CONTROL-PLANE-EXTENSION-DESIGN.md`.

Each audit module already carries a thorough top-of-file docstring; this is the
one-page composition view across them.

## What each layer returns

Every layer reports a status string drawn from a shared vocabulary:

- `pass` / `fail` — measured, real number behind it.
- `unmeasured` — the machinery exists but had nothing to run against (no table, store
  unlistable, never-written source). Never a pass, never a fail.
- `unwired` — no machinery exists for this check at all (e.g. Parquet CRC bit-flip,
  DuckLake tombstone). Never counts toward pass or fail.
- `stale` — a measured `pass` whose TTL elapsed without re-validation (`decay.py`).
  Not green, but not a failure: "re-run me," not "broken."

| Layer | Module | Returns | Aggregation rule |
|---|---|---|---|
| **L1 source health** | `layer1_audit.py` | per-source `{status, rows, checks, completeness}`; layer `status` | `fail` if any source fails; `pass` if ≥1 source measured and all pass; else `unmeasured`. A never-written source (no fresh snapshot) is `unmeasured`, never a pass. |
| **L2 stack reachable** | observed in `control_plane.py` (not an audit module) | derived inside `compute_gate` from `docker_up` + `catalog_live` | `pass` if catalog live; `fail` if Docker up but catalog not; `unmeasured` if no Docker. |
| **L3 data quality** | `layer3_audit.py` | `{checks:[CheckResult], status}` over freshness / small-files / orphans / schema-conformance | `fail` if any measured check fails; `pass` if ≥1 measured check ran and all pass; else `unmeasured`. `unwired` checks never pass or fail the layer. |
| **L4 cross-tool gap** | `layer4_audit.py` (exact-match, wired) · `layer4_deep.py` (entity resolution, built+proven, **not wired**) | `{primary, status, gaps[], note}` | `unmeasured` if the primary is unreadable or <2 sources readable; `fail` if any gap exceeds tolerance; else `pass`. Counts only — identities are never rendered (telemetry-injection rule). |

Config integrity (a compatible component selection) and "spec persisted"
(`moar-spec.yaml` exists) are not audit layers — they are HARD deploy gates evaluated
directly inside `compute_gate`.

`decay.py` is applied by the *caller* (the readers feed `effective_status` into the
gate) before the statuses reach `compute_gate`, so a measured pass past its TTL arrives
as `stale`.

## How the gate combines them (`gate_logic.compute_gate`)

`compute_gate(*, warns, spec_saved, docker_up, catalog_live, layer1_status, layer3_status, layer4_status)`
builds a six-row layer table:

1. Config integrity — `fail` if any incompatible-selection warning, else `pass`.
2. Spec persisted — `pass`/`fail` on whether `moar-spec.yaml` exists.
3. Layer 1 — source health (from `layer1_audit`).
4. Layer 2 — stack reachable (derived from `docker_up` + `catalog_live`).
5. Layer 3 — data-quality audit (from `layer3_audit`).
6. Layer 4 — cross-tool gap (from `layer4_audit`).

It then derives:

- `deploy_ok` = **no** config-integrity blockers (incompatible selection or missing
  spec). The data layers do NOT block the first deploy — they can only be measured
  after a stack is up and data has landed, so gating the first deploy on them is a
  chicken-and-egg. A measured-layer `fail` is a *certification* blocker, not a deploy
  blocker.
- `all_green` = `deploy_ok` AND every one of the six rows is `pass`.
- `cert_blockers` = the named rows currently `fail`.
- `unmeasured` / `stale` = the named rows in those states.

`verdict_line(gate)` renders the headline:

- 🟢 GREEN — every measurable layer passes.
- 🔴 Deploy blocked — clear the config-integrity blockers or log an override.
- 🔴 Not certified — a required layer **failed** (names them).
- 🟡 Deploy permitted but stale — a proven layer's TTL elapsed; re-run it.
- 🟡 Deploy permitted but unproven — config integrity holds, but a required layer is
  still `unmeasured` so the gate refuses to certify GREEN.

The deploy button consumes `deploy_ok` as a boolean guard; a blocked deploy needs the
logged `gate_override` switch.

## Why the gate is AMBER (🟡) by design until the layers run

The gate will not bluff GREEN for a layer it has not actually measured. On a freshly
loaded console, Layers 1/3/4 default to `unmeasured` — their audits only run when the
operator presses the corresponding run button (the audits do live work against the
deployed Iceberg tables + object store, so they are deferred off the reactive tick to
avoid eager `load_table` on every namespace change). Until those buttons are pressed,
a perfectly clean foundation correctly reads 🟡 "deploy permitted, cannot certify
GREEN," and a real Layer-3 failure flips it 🔴 — the RED-on-data-failure transition is
the demo moment, and a true GREEN is reachable only after all four measurable layers
have been run and pass. The console refusing to show green on its own unproven layers
is the empirical-skepticism thesis made into a runtime fact, not a UI quirk to "fix."

One precision the design doc's earlier "AMBER until Layer-4 is built" framing predates:
Layer 4 *is* built and wired — `control_plane.py` imports `layer4_audit` (exact-match
set membership) and feeds it to the gate. What is **not** wired is the DEEP version,
`layer4_deep.py` (authoritative-source-per-attribute entity resolution): it is built and
proven (`prove_layer4_deep.py`, 33 assertions) but `control_plane.py` does not import it,
so the gate currently runs on the exact-match Layer-4 only. Wiring a deep-mode toggle is
the open owner item (see `LAYER4-DEEP-BRANCH.md` and the design doc §LATER). So the
honest "amber-by-design" statement today is: AMBER until the operator runs the four
measurable audits; the exact-match Layer-4 participates, the DEEP Layer-4 is an
owner-gated upgrade, not the reason for amber.

## Proof harnesses (the contract is tested, not asserted)

- `prove_gate.py` — `compute_gate` through a healthy → broken (real orphan injected) →
  remediated arc.
- `prove_layers.py` — Layers 1–4 against real Iceberg tables, including the all-four-
  measured GREEN and the never-written-source false-green regression.
- `prove_layer4_deep.py` — both resolution directions (declared-rule matches close the
  false `web-01` vs `web-01.corp` gap; every unsafe match stays a gap).
- `prove_evidence.py`, `prove_vector_metrics.py` — the Evidence Runner and Vector
  Layer-2 counters.
- `prove_constraint_filter.py`, `prove_anti_patterns.py`, `prove_cost_advisor.py`,
  `prove_reference_presets.py` — the book-decision-framework engines.
- `prove_flow_reconcile.py`, `prove_ocsf_roundtrip.py` — the cluster-5 deepening engines.
- `prove_panels_smoke.py` — headless construction of the Startup-tab panels.

## Cluster-5 deepening (2026-06-20) — logic built + proven, live wiring deferred

Three deepenings extend the gate beyond Layers 1–4, each a pure engine with a proof; the
live-data collection needs a running stack and is wired in `control_plane` later, exactly
as Layers 1/3/4 already are (logic proven against fixtures, live audit deferred):

- **Cross-engine answer equality** — `compute_gate` gains an optional seventh row
  (`answer_equality_status`, default `None` = omitted for back-compat). When supplied it is
  a cert-bearing row: a `fail` (an engine returns a filtered count short of the others over
  byte-identical data — the silent-wrong-answer mode) blocks GREEN. Feed it the
  `./moar verify` result.
- **Flow reconciliation** (`flow_reconcile.py`) — counts events hop-to-hop per OCSF class
  (emitted → ingested → landed) and fails on a silent drop beyond tolerance, so a pipeline
  that quietly loses a fraction of one class surfaces rather than hiding behind a reachable
  Layer 2.
- **OCSF round-trip** (`ocsf_roundtrip.py`) — value-level check on top of schema conformance:
  known-good test events run through the transform must produce the expected OCSF field
  values, catching a mapping that is schema-valid but semantically wrong.
