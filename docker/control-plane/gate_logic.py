"""The composite data-health gate verdict — a pure function.

This is the spine of the console: the verdict that consumes the per-layer results
and decides whether the stack may be certified GREEN and whether a deploy is
authorized. It was inline in the marimo gate cell; pulling it into a pure function
lets the cell render it AND lets the proof harnesses exercise the exact same logic
through healthy -> broken -> healthy arcs, so the proof tests what the UI runs,
not a paraphrase of it.

The layer model (THESIS "Layers 1-4 are the gate"):
  - Config integrity (compatible selection) + spec persisted are HARD deploy
    gates — you cannot deploy onto an incoherent selection.
  - Layer 1 (source health) and Layers 3/4 (data-quality audit, cross-tool gap)
    are measured by their own machinery; until they return a real result they are
    `unmeasured`, and the gate refuses to certify GREEN rather than bluff a pass.
  - Layer 2 (stack reachable) is observed.
  - A measured `pass` can decay to `stale` (see decay.py) when it has not been
    re-validated within its TTL — stale is not-green but not a failure ("re-run
    me," not "broken"). The caller applies decay before passing statuses in.

Deploy vs certify: a measured layer FAIL keeps the gate from GREEN and is surfaced
as a certification blocker, but it does not retroactively block the initial deploy —
the data layers can only be measured after a stack is up and data has landed, so
gating the first deploy on them would be a chicken-and-egg.
"""
from __future__ import annotations

ICON = {"pass": "🟢", "fail": "🔴", "unmeasured": "⚪", "unwired": "⚫", "stale": "⏳"}


def compute_gate(*, warns, spec_saved, docker_up, catalog_live,
                 layer1_status="unmeasured", layer3_status="unmeasured",
                 layer4_status="unmeasured", answer_equality_status=None,
                 ocsf_roundtrip_status=None, flow_reconcile_status=None,
                 schema_drift_status=None) -> dict:
    """Return the gate verdict dict.

    warns: list of incompatible-selection warning titles (config-integrity blockers).
    spec_saved: a moar-spec.yaml exists.
    docker_up / catalog_live: stack reachability observations (Layer 2).
    layer1/3/4_status: pass | fail | unmeasured | stale from the audits (decay applied
    by the caller).
    answer_equality_status: optional cross-engine answer-equality result (`./moar verify`).
    An engine that returns a filtered count short of the others over byte-identical data is
    a silent-wrong-answer, so a `fail` here blocks certification. `None` omits the row
    entirely (back-compat); any status value adds it as a seventh, cert-bearing gate row.
    ocsf_roundtrip_status: optional value-level mapping-fidelity result (the deployed router
    transform turns known raw events into OCSF records that carry the contract values). A
    mapping can be schema-valid yet semantically wrong, so a `fail` here blocks certification.
    `None` omits the row (back-compat); any status adds it as an eighth, cert-bearing row.
    flow_reconcile_status: optional per-class hop-count reconciliation (emitted → ingested →
    landed across the live source→route→land pipeline). A class the pipeline silently drops is
    a coverage hole a reachable Layer 2 can't see, so a `fail` here blocks certification. `None`
    omits the row (back-compat); any status adds it as a ninth, cert-bearing row.
    schema_drift_status: optional raw→OCSF field-coverage result (an incoming source's field set vs
    the deployed crosswalk). A dropped/renamed raw field that leaves a hunt's required OCSF field
    unpopulated silences that detection with no error — invisible to Layer 2 and the round-trip — so
    a `fail` here blocks certification. `None` omits the row (back-compat); any status adds it as a
    tenth, cert-bearing row.
    """
    blockers = [f"Incompatible selection: {w}" for w in warns]
    if not spec_saved:
        blockers.append("No moar-spec.yaml saved yet (Configuration → Save Configuration Spec).")

    l2 = "pass" if catalog_live else ("fail" if docker_up else "unmeasured")
    layers = [
        ("Config integrity (compatible selection)", "fail" if warns else "pass"),
        ("Spec persisted", "pass" if spec_saved else "fail"),
        ("Layer 1 — source health", layer1_status),
        ("Layer 2 — stack reachable", l2),
        ("Layer 3 — data-quality audit", layer3_status),
        ("Layer 4 — cross-tool gap analysis", layer4_status),
    ]
    if answer_equality_status is not None:
        layers.append(("Cross-engine answer equality", answer_equality_status))
    if ocsf_roundtrip_status is not None:
        layers.append(("OCSF round-trip (mapping fidelity)", ocsf_roundtrip_status))
    if flow_reconcile_status is not None:
        layers.append(("Flow reconciliation (hop counts)", flow_reconcile_status))
    if schema_drift_status is not None:
        layers.append(("Schema drift (raw → OCSF field coverage)", schema_drift_status))

    deploy_ok = not blockers
    all_green = deploy_ok and all(s == "pass" for _n, s in layers)
    cert_blockers = [n for n, s in layers if s == "fail"]

    return {
        "deploy_ok": deploy_ok,
        "all_green": all_green,
        "blockers": blockers,
        "cert_blockers": cert_blockers,
        "layers": layers,
        "unmeasured": [n for n, s in layers if s == "unmeasured"],
        "stale": [n for n, s in layers if s == "stale"],
    }


def verdict_line(gate: dict) -> tuple[str, str]:
    """(message, css-color) for the headline verdict — shared by the UI panel."""
    if gate["all_green"]:
        return "🟢 Gate GREEN — every measurable layer passes.", "var(--color-teal-500)"
    if not gate["deploy_ok"]:
        return "🔴 Deploy blocked — clear the config-integrity blockers, or log an override.", "#c14a4a"
    if gate["cert_blockers"]:
        return ("🔴 Not certified — a required layer failed: "
                + "; ".join(gate["cert_blockers"]) + ".", "#c14a4a")
    if gate.get("stale"):
        return ("🟡 Deploy permitted — proven layers have gone stale and need re-running: "
                + "; ".join(gate["stale"]) + ".", "var(--color-orange-500)")
    return ("🟡 Deploy permitted — config integrity holds, but the gate cannot certify GREEN "
            "until the unproven layers run.", "var(--color-orange-500)")


def verdict_chip(gate: dict) -> tuple[str, str]:
    """A compact one-line verdict for secondary surfaces — the full layer breakdown lives in
    Flow › Health. Same colour key as verdict_line, shorter text."""
    if gate["all_green"]:
        return "🟢 Data-health gate: GREEN", "var(--color-teal-500)"
    if not gate["deploy_ok"]:
        return "🔴 Data-health gate: deploy blocked", "#c14a4a"
    if gate["cert_blockers"]:
        return "🔴 Data-health gate: not certified", "#c14a4a"
    if gate.get("stale"):
        return "🟡 Data-health gate: stale — re-run", "var(--color-orange-500)"
    return "🟡 Data-health gate: amber — unproven layers", "var(--color-orange-500)"
