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

# the trust+verify value-moment arms (declaration order, for readers); record_arm accepts any.
ARMS = ("detections", "answer_equality", "ocsf_roundtrip", "flow_reconcile", "schema_drift")


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


def _trustworthy_stamp(s):
    """True iff `s` is a string that parses to a timezone-AWARE ISO datetime with a time component — the
    only stamp whose freshness can be trusted. A naive (no-tz) stamp would be silently treated as UTC by
    datetime arithmetic (reading a stale measurement as fresh on a non-UTC host — the faked-green path the
    adversarial review found); a date-only / integer / garbage stamp parses to midnight or not at all. All
    are rejected so none can ever read as a fresh green."""
    if not isinstance(s, str) or "T" not in s:
        return False
    try:
        from datetime import datetime
        return datetime.fromisoformat(s.replace("Z", "+00:00")).tzinfo is not None
    except (ValueError, TypeError):
        return False


def recorded_at(arm, path=PATH):
    """The `ran_at` of a recorded arm IF it is a trustworthy tz-aware ISO stamp, else None — so the
    'last measured @ran_at' provenance line never renders a naive / date-only / non-string stamp as if it
    were an authoritative measurement time."""
    d = load(path).get(arm)
    if not isinstance(d, dict):
        return None
    ran_at = d.get("ran_at")
    return ran_at if _trustworthy_stamp(ran_at) else None


def gate_status(arm, now_iso, ttl_seconds=None, path=PATH):
    """A recorded arm mapped into the data-health gate's status vocabulary — the 'last measured' FALLBACK
    used when no interactive run exists this session. Honesty is by construction:

    - arm absent / not a dict / missing status or ran_at -> None (the gate row is OMITTED, never a faked
      green);
    - a ran_at that is not a trustworthy tz-aware ISO datetime (naive / date-only / integer / garbage) is
      treated as undatable: a recorded `pass` decays to 'stale' (visible, never green), a non-pass passes
      through. This closes the naive-stamp-on-a-non-UTC-host faked-green path the adversarial review found;
    - a trustworthy `pass` is run through `decay.effective_status`: genuinely fresh -> 'pass', older than
      the TTL (default one day) -> 'stale'.

    Nothing here can manufacture a pass the recorder didn't write, and only a real stack-UP pass is ever
    recorded in the first place."""
    import decay
    d = load(path).get(arm)
    if not isinstance(d, dict):
        return None
    status, ran_at = d.get("status"), d.get("ran_at")
    if not status or not ran_at:
        return None
    if not _trustworthy_stamp(ran_at):
        return "stale" if status == "pass" else status
    ttl = decay.DEFAULT_TTL_SECONDS if ttl_seconds is None else ttl_seconds
    return decay.effective_status(status, ran_at, now_iso, ttl)
