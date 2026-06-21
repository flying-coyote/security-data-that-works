"""Durable record of the stack-UP value-moment captures — the build-loop guard's evidence
(CONSOLE-LOOP-STATE §3/§5).

Each `prove_*_live.py`, when its live (stack-UP) arm actually runs, records its result here via
`record_arm` — a read-merge-write keyed by arm name, so running any one live proof updates only its
arm and the file accumulates the full trust+verify picture (the four value-moment arms: detections,
answer_equality, ocsf_roundtrip, flow_reconcile). A recorded arm is the committed, human-citable
proof that a B/C/D value moment was actually MEASURED with the stack up, not asserted in prose or
inferred from the fallback path.

Two invariants this module exists to hold:
  - Telemetry-injection rule: arms carry counts / statuses / low-cardinality keys (engine names,
    OCSF class ids) only — never raw telemetry rows. The callers pass already-aggregated payloads;
    this module does no row handling.
  - Honesty: nothing here writes a `pass` on its own. A caller records its arm only inside its
    live, stack-UP branch after a real pass — a stack-down or degraded run records nothing, so a
    stale file never reads as a fresh measurement (the ran_at each arm carries is decayed by the
    gate's own `decay.effective_status`).

Nothing READS this at console runtime — the data-health gate computes its rows from live,
button-triggered runs in the marimo app. This file is the out-of-band record the loop cites.
"""
from __future__ import annotations

import json
import os

PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live-evidence.json")

# the four trust+verify value-moment arms (declaration order, for readers); record_arm accepts any.
ARMS = ("detections", "answer_equality", "ocsf_roundtrip", "flow_reconcile")


def load(path: str = PATH) -> dict:
    """Return the recorded evidence as a dict, or {} when absent/corrupt. A legacy top-level
    detections object (the pre-keyed single-arm format) migrates once into its `detections` arm."""
    try:
        with open(path) as f:
            d = json.load(f)
    except (FileNotFoundError, ValueError):
        return {}
    if not isinstance(d, dict):
        return {}
    if "detections" not in d and "findings" in d and "ran_at" in d:
        # one-time migration of the original single-object format -> the keyed arm.
        return {"detections": d}
    return d


def record_arm(arm: str, payload: dict, *, path: str = PATH) -> dict:
    """Read-merge-write `payload` under key `arm`, leaving the other arms intact. Returns the full
    evidence dict. The caller owns telemetry-safety of `payload` (counts / statuses only)."""
    d = load(path)
    d[arm] = payload
    with open(path, "w") as f:
        json.dump(d, f, indent=2, sort_keys=True)
        f.write("\n")
    return d
