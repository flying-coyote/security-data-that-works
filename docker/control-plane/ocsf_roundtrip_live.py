"""Live OCSF round-trip check — run the deployed router transform on the known raw Okta
sample and assert each produced OCSF record carries the contract values.

`ocsf_roundtrip.py` is the pure value-level logic over {expected, produced} pairs; this is
its live arm. The `produced` side comes from actually shelling out to a deployed router
(Tenzir by default — it emits OCSF JSON to stdout, 1:1 with the raw sample), and the
`expected` side is derived from the raw event through the OCSF Authentication contract
specified HERE — independently of any router's transform — so a transform that regresses
(drops src_ip, mis-maps the class/activity, loses the identity) is caught against the spec,
not against a copy of its own output. Schema-shape conformance (Layer 3) is necessary but
not sufficient; this is the meaning check on top.

Same safety + honesty rules as evidence_runner: output is bounded/sanitized (telemetry-
injection rule), the run is `blocked` with no Docker (never a pass) and `error` on a
timeout/crash. The pure half (`validate_against_contract`) is unit-tested; the subprocess
half is verified live against the real router.
"""
from __future__ import annotations

import json
import re
import subprocess

import decay
import ocsf_roundtrip as rt

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# router name -> compose service that emits OCSF JSON to stdout.
ROUTERS = {"tenzir": "route-tenzir", "fluentbit": "route-fluentbit"}


def expected_ocsf(raw):
    """The OCSF Authentication contract for an Okta `user.session.start` event, specified
    independently of any router's transform. class_uid 3002 (Authentication) is required;
    the actor's id must land in `user` and the client IP in `src_ip` (the identity/source
    that flattening or a sloppy map would drop); SUCCESS->activity_id 1, FAILURE->2 is the
    stack's established convention (all three routers agree, per swap-router)."""
    outcome = (raw.get("outcome") or {}).get("result")
    return {
        "class_uid": 3002,
        "activity_id": 1 if outcome == "SUCCESS" else 2,
        "user": (raw.get("actor") or {}).get("alternateId"),
        "src_ip": (raw.get("client") or {}).get("ipAddress"),
        "status": outcome,
    }


def _sanitize(text):
    text = _ANSI.sub("", text or "")
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


def parse_ocsf_lines(text):
    """Pull OCSF JSON objects out of router stdout — one per line, skipping any log noise.
    Bounded by the caller's input; never returns raw non-JSON rows."""
    out = []
    for line in _sanitize(text).splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            out.append(obj)
    return out


def validate_against_contract(raws, produced, *, now_iso):
    """Pure: pair each raw event to its produced OCSF record by index, derive the expected
    record from the contract, and validate. A count mismatch is itself a fail (the transform
    dropped or duplicated events). No produced records -> unmeasured (never a false pass)."""
    if not produced:
        return {"status": "unmeasured", "ran_at": now_iso, "events": [],
                "note": "router produced no OCSF records"}
    if len(produced) != len(raws):
        return {"status": "fail", "ran_at": now_iso, "events": [], "fail_count": abs(len(produced) - len(raws)),
                "note": f"{len(produced)} OCSF records for {len(raws)} raw events — count mismatch"}
    pairs = [{"expected": expected_ocsf(r), "produced": p} for r, p in zip(raws, produced)]
    result = rt.validate(pairs)  # {status, events, fail_count}
    result["ran_at"] = now_iso
    result["note"] = (f"{len(pairs)} events faithful to the OCSF Authentication contract"
                      if result["status"] == "pass"
                      else f"{result.get('fail_count', 0)}/{len(pairs)} events mismatched the contract")
    return result


def run_roundtrip(*, docker_dir, sample_path, available, now_iso,
                  router="tenzir", compose_file="compose.yml", timeout=120):
    """Run a deployed router over its raw sample and validate the produced OCSF against the
    contract. Returns {status, ran_at, events, note, router}. `blocked` with no Docker
    (never a pass); `error` on a timeout/crash/unreadable sample."""
    svc = ROUTERS.get(router)
    if svc is None:
        return {"status": "error", "ran_at": now_iso, "events": [], "note": f"unknown router '{router}'"}
    if not available:
        return {"status": "blocked", "ran_at": now_iso, "events": [],
                "note": "No Docker daemon reachable — deploy the route profile to run this check."}
    try:
        with open(sample_path) as f:
            raws = [json.loads(line) for line in f if line.strip()]
    except Exception as e:  # noqa: BLE001 - surface honestly
        return {"status": "error", "ran_at": now_iso, "events": [],
                "note": f"raw sample unreadable: {_sanitize(str(e))[:160]}"}
    try:
        res = subprocess.run(["docker", "compose", "-f", compose_file, "run", "--rm", "-T", svc],
                             cwd=docker_dir, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "error", "ran_at": now_iso, "events": [], "note": f"router timed out after {timeout}s"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "ran_at": now_iso, "events": [], "note": _sanitize(str(e))[:200]}
    produced = parse_ocsf_lines(res.stdout)
    out = validate_against_contract(raws, produced, now_iso=now_iso)
    out["router"] = router
    return out


def gate_status(result, *, now_iso=None, ttl_seconds=None):
    """Map a run_roundtrip result into the gate's status vocabulary, with the same
    last-validated decay the gate applies to layers 1/3/4.

    None when no run is present (the gate row is omitted — back-compat); 'pass'/'fail' on a
    real verdict; 'unmeasured' when blocked/errored or nothing was produced (never a bluffed
    pass); and a stale pass (older than the TTL, or undatable) decays to 'stale' when
    `now_iso` is supplied."""
    if not result:
        return None
    status = result.get("status")
    if status not in ("pass", "fail"):
        return "unmeasured"
    if status == "pass" and now_iso is not None:
        return decay.effective_status("pass", result.get("ran_at"), now_iso,
                                      ttl_seconds if ttl_seconds is not None else decay.DEFAULT_TTL_SECONDS)
    return status
