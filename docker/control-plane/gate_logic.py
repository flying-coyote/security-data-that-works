"""The composite data-health gate verdict — a pure function.

This is the spine of the console: the verdict that consumes the per-layer results
and decides whether the stack may be certified GREEN and whether a deploy is
authorized. It was inline in the marimo gate cell; pulling it into a pure function
lets the cell render it AND lets `prove_gate.py` exercise the exact same logic
through a healthy -> broken -> healthy arc, so the proof tests what the UI runs,
not a paraphrase of it.

The layer model (THESIS "Layers 1-4 are the gate"):
  - Config integrity (compatible selection) + spec persisted are HARD deploy
    gates — you cannot deploy onto an incoherent selection.
  - Layer 1-2 (stack reachable) is observed.
  - Layer 3 (data-quality audit) and Layer 4 (cross-tool gap) are measured by
    their own machinery; until they return a real result they are `unmeasured`,
    and the gate refuses to certify GREEN rather than bluff a pass.

Deploy vs certify: a measured Layer-3 FAIL keeps the gate from GREEN and is
surfaced as a blocking reason for certification, but it does not retroactively
block the initial deploy — Layer 3 can only be measured after a stack is up and
data has landed, so gating the first deploy on it would be a chicken-and-egg.
"""
from __future__ import annotations

ICON = {"pass": "🟢", "fail": "🔴", "unmeasured": "⚪", "unwired": "⚫"}


def compute_gate(*, warns, spec_saved, docker_up, catalog_live,
                 layer3_status="unmeasured", layer4_status="unmeasured") -> dict:
    """Return the gate verdict dict.

    warns: list of incompatible-selection warning titles (config-integrity blockers).
    spec_saved: a moar-spec.yaml exists.
    docker_up / catalog_live: stack reachability observations.
    layer3_status / layer4_status: pass | fail | unmeasured from the audits.
    """
    blockers = [f"Incompatible selection: {w}" for w in warns]
    if not spec_saved:
        blockers.append("No moar-spec.yaml saved yet (Configuration → Save Configuration Spec).")

    l12 = "pass" if catalog_live else ("fail" if docker_up else "unmeasured")
    layers = [
        ("Config integrity (compatible selection)", "fail" if warns else "pass"),
        ("Spec persisted", "pass" if spec_saved else "fail"),
        ("Layer 1-2 — stack reachable", l12),
        ("Layer 3 — data-quality audit", layer3_status),
        ("Layer 4 — cross-tool gap analysis", layer4_status),
    ]

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
    }


def verdict_line(gate: dict) -> tuple[str, str]:
    """(message, css-color) for the headline verdict — shared by the UI panel."""
    if gate["all_green"]:
        return "🟢 Gate GREEN — every measurable layer passes.", "var(--color-teal-500)"
    failed = gate.get("cert_blockers") or []
    data_failed = [f for f in failed if f.startswith("Layer 3") or f.startswith("Layer 4")]
    if not gate["deploy_ok"]:
        return "🔴 Deploy blocked — clear the config-integrity blockers, or log an override.", "#c14a4a"
    if data_failed:
        return ("🔴 Not certified — a data-health audit failed: "
                + "; ".join(data_failed) + ".", "#c14a4a")
    return ("🟡 Deploy permitted — config integrity holds, but the gate cannot certify GREEN "
            "until the unproven layers run.", "var(--color-orange-500)")
