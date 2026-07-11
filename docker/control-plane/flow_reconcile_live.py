"""Live flow reconciliation — run the real source→route→land pipeline and reconcile
per-OCSF-class event counts hop to hop (emitted → ingested → landed).

`flow_reconcile.py` is the pure reconciliation logic; this is its live collector. The
routers are one-shot emitters and the land hop is `docker/lab/flow_counts.py` (which reuses
promote.py's land pattern). This runs the router, pipes its OCSF into the lab's land+count
helper, and feeds three per-class counts into `flow_reconcile.reconcile()`:
  - emitted  — ground truth from the raw sample (not a meter): what the source put in.
  - ingested — the router's OCSF output by class_uid: did the transform drop a raw event?
  - landed   — what survived into the Iceberg table by class_uid: did the land hop lose any?
A class the pipeline silently loses at either hop surfaces as a drop the gate can name —
the failure a reachable Layer 2 (stack-is-up) is blind to.

Same honesty rules as the other live arms: `blocked` with no Docker (never a pass), `error`
on a timeout/crash/unparseable helper output, bounded/sanitized. The pure half (count
derivation + reconcile) is unit-tested; the subprocess half is verified live.
"""
from __future__ import annotations

import collections
import json
import re
import subprocess

import decay
import flow_reconcile as fr

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# raw eventType -> resulting OCSF class_uid (the contract the routers implement). Extend as
# more source types are added so emitted stays ground-truth per class.
_EVENT_TO_CLASS = {"user.session.start": 3002}


def _sanitize(text):
    text = _ANSI.sub("", text or "")
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


def emitted_from_sample(sample_path):
    """Ground-truth emitted counts per resulting OCSF class, read from the raw sample."""
    counts = collections.Counter()
    with open(sample_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line)
            except ValueError:
                continue
            cls = _EVENT_TO_CLASS.get(o.get("eventType"))
            if cls is not None:
                counts[cls] += 1
    return {str(k): v for k, v in counts.items()}


def build_reconciliation(emitted, ingested, landed, *, now_iso, tolerance_frac=0.0):
    """Pure: assemble the per-class hop counts and reconcile. emitted/ingested/landed are
    {class_str: int}. Returns flow_reconcile.reconcile()'s dict plus ran_at, the per-class
    counts, and a one-line note."""
    classes = set(emitted) | set(ingested) | set(landed)
    by_class = {c: {"emitted": emitted.get(c), "ingested": ingested.get(c), "landed": landed.get(c)}
                for c in classes}
    result = fr.reconcile(by_class, tolerance_frac=tolerance_frac)
    result["ran_at"] = now_iso
    result["by_class_counts"] = by_class
    if result["status"] == "pass":
        parts = []
        for c in sorted(by_class):
            h = by_class[c]
            parts.append(f"{c}: {h['emitted']}/{h['ingested']}/{h['landed']}")
        result["note"] = (f"{len(by_class)} class(es) reconciled clean — emitted/ingested/landed agree "
                          f"({'; '.join(parts)})")
    elif result["status"] == "fail":
        drops = [f"{r['class']} dropped {r['drop']} ({r['drop_frac']:.1%})"
                 for r in result["classes"] if r["status"] == "fail"]
        result["note"] = "silent drop — " + "; ".join(drops)
    else:
        result["note"] = "a hop count was missing — nothing measured"
    return result


def run_pipeline(*, docker_dir, sample_path, available, now_iso,
                 router="route-tenzir", compose_file="compose.yml", timeout=180):
    """Run router→land and reconcile the per-class counts. `blocked` with no Docker (never a
    pass); `error` on timeout/crash/unreadable sample/unparseable helper output."""
    if not available:
        return {"status": "blocked", "ran_at": now_iso,
                "note": "No Docker reachable — deploy the core + route profiles to run the pipeline."}
    try:
        emitted = emitted_from_sample(sample_path)
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "ran_at": now_iso, "note": f"raw sample unreadable: {_sanitize(str(e))[:160]}"}
    if not emitted:
        return {"status": "unmeasured", "ran_at": now_iso, "note": "no mappable source events in the sample"}
    try:
        rt = subprocess.run(["docker", "compose", "-f", compose_file, "run", "--rm", "-T", router],
                            cwd=docker_dir, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "error", "ran_at": now_iso, "note": f"router timed out after {timeout}s"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "ran_at": now_iso, "note": _sanitize(str(e))[:200]}
    try:
        land = subprocess.run(["docker", "compose", "-f", compose_file, "exec", "-T", "lab",
                               "python", "/lab/flow_counts.py"],
                              cwd=docker_dir, input=rt.stdout, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"status": "error", "ran_at": now_iso, "note": f"land step timed out after {timeout}s"}
    except Exception as e:  # noqa: BLE001
        return {"status": "error", "ran_at": now_iso, "note": _sanitize(str(e))[:200]}
    counts = _parse_counts(land.stdout)
    if counts is None:
        return {"status": "error", "ran_at": now_iso,
                "note": f"land helper output unparseable: {_sanitize(land.stdout + land.stderr)[-160:]}"}
    ingested = {str(k): int(v) for k, v in (counts.get("ingested") or {}).items()}
    landed = {str(k): int(v) for k, v in (counts.get("landed") or {}).items()}
    result = build_reconciliation(emitted, ingested, landed, now_iso=now_iso)
    result["router"] = router
    return result


def _parse_counts(text):
    """Pull the single JSON line the land helper prints (skip any incidental log lines)."""
    for line in reversed(_sanitize(text).splitlines()):
        line = line.strip()
        if line.startswith("{") and "ingested" in line:
            try:
                return json.loads(line)
            except ValueError:
                continue
    return None


def gate_status(result, *, now_iso=None, ttl_seconds=None):
    """Map a run_pipeline result into the gate's status vocabulary, with the same decay the
    gate applies to layers 1/3/4.

    None when no run is present (gate row omitted — back-compat); 'pass'/'fail' on a real
    verdict; 'unmeasured' when blocked/errored or a hop count was missing (never a bluffed
    pass); a stale pass (older than the TTL, or undatable) decays to 'stale' when `now_iso`
    is supplied."""
    if not result:
        return None
    status = result.get("status")
    if status not in ("pass", "fail"):
        return "unmeasured"
    if status == "pass" and now_iso is not None:
        return decay.effective_status("pass", result.get("ran_at"), now_iso,
                                      ttl_seconds if ttl_seconds is not None else decay.DEFAULT_TTL_SECONDS)
    return status
