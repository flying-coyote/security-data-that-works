"""Evidence Runner — run the MOAR ./moar verbs as gate-feeding, hypothesis-bound proofs.

Each verb re-proves a thesis claim against the live stack — empirical skepticism made
operational, "challenged with data, not assertion." This module shells out to
`./moar <verb>` reusing the VRL tester's subprocess + timeout + exit-code pattern,
captures the exit code plus a BOUNDED, SANITIZED summary, UTC-dates and Tier-B-stamps
the result, and degrades to a labeled `blocked` state when no Docker daemon is
reachable rather than hanging or faking a pass.

Two safety rules ride every result:
  - The telemetry-injection rule applies to verb output too: never pipe raw stdout
    rows into context. `_bounded` keeps only the tail and caps the length; `_sanitize`
    strips ANSI escapes and control characters. The verbs print verdict text, not raw
    security rows, but the summary is bounded and sanitized regardless.
  - Honest labeling: a verb is `pass`/`fail` only on a real exit code; with no Docker
    it is `blocked` (never a pass), and a timeout/crash is `error` (never a pass).

The starting set is the read-only, hypothesis-declaring verbs from the design — the
answer-equality check, the four portability (swap) proofs that pair with the
console's per-component swap-cost field, and four single-hypothesis verbs.
"""
from __future__ import annotations

import re
import subprocess

import decay

# verb -> what it re-proves. `hypothesis` is the tracker id where there is one, else a
# short claim name. `timeout` is a backstop; verbs only run when Docker is reachable.
VERBS = [
    {"verb": "verify", "hypothesis": "answer-equality (cross-engine)",
     "desc": "every running engine returns the same answer over the same Iceberg table", "timeout": 300},
    {"verb": "swap-store", "hypothesis": "reversibility · L-tier",
     "desc": "identical answer on MinIO and SeaweedFS", "timeout": 300},
    {"verb": "swap-catalog", "hypothesis": "reversibility · I-tier",
     "desc": "identical answer via iceberg-rest, Nessie and Lakekeeper", "timeout": 300},
    {"verb": "swap-format", "hypothesis": "reversibility · I-tier format",
     "desc": "identical answer via Iceberg and DuckLake", "timeout": 300},
    {"verb": "swap-router", "hypothesis": "reversibility · R-tier",
     "desc": "identical OCSF out from Vector, Tenzir and Fluent Bit", "timeout": 300},
    {"verb": "correlate", "hypothesis": "H-NDR-FEDERATION-01",
     "desc": "federated cross-source correlation over the open OCSF store", "timeout": 300},
    {"verb": "governance", "hypothesis": "H-SEC-CATALOG-01",
     "desc": "catalog audit trail + time-travel + lineage a mutable SIEM index can't keep", "timeout": 300},
    {"verb": "variant-mfa", "hypothesis": "H-OCSF-CONTEXT-COLLAPSE-01",
     "desc": "absence-vs-NULL: nested catches absent-MFA logins that flattening hides", "timeout": 300},
    {"verb": "commit-tax", "hypothesis": "H-DUCKLAKE-02",
     "desc": "streaming commit-tax: Iceberg per-commit metadata floor vs DuckLake", "timeout": 600},
]

VERB_INDEX = {v["verb"]: v for v in VERBS}

_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _sanitize(text: str) -> str:
    """Strip ANSI escapes and control chars (keep \\n and \\t) — verb output is shown
    in the UI and read back into context, so it gets the same hygiene as telemetry."""
    text = _ANSI.sub("", text)
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


def _bounded(text: str, max_lines: int = 15, max_chars: int = 1800) -> str:
    """Keep only the tail of the output (the verdict lives at the end) and cap length —
    never return the full stdout."""
    lines = _sanitize(text).strip().splitlines()
    out = "\n".join(lines[-max_lines:])
    return ("…" + out[-max_chars:]) if len(out) > max_chars else out


def _result(verb, hypothesis, status, *, exit_code, summary, now_iso):
    return {"verb": verb, "hypothesis": hypothesis, "status": status,
            "exit_code": exit_code, "summary": summary, "ran_at": now_iso,
            "tier": "Tier B, single host"}


def run_verb(verb: str, *, docker_dir: str, available: bool, now_iso: str, timeout=None) -> dict:
    """Run one ./moar verb. `available` is deployer.is_docker_available() — when False
    the verb is not executed and returns `blocked` (the honest degrade). Returns a
    result dict; status is pass | fail | blocked | error."""
    spec = VERB_INDEX.get(verb)
    if spec is None:
        return _result(verb, "?", "error", exit_code=None,
                       summary=f"unknown verb '{verb}'", now_iso=now_iso)
    if not available:
        return _result(verb, spec["hypothesis"], "blocked", exit_code=None,
                       summary="No Docker daemon reachable — deploy the stack (Manage → Infrastructure) to run this verb.",
                       now_iso=now_iso)
    try:
        res = subprocess.run(
            ["./moar", verb], cwd=docker_dir,
            capture_output=True, text=True, timeout=timeout or spec["timeout"],
        )
        status = "pass" if res.returncode == 0 else "fail"
        return _result(verb, spec["hypothesis"], status, exit_code=res.returncode,
                       summary=_bounded(res.stdout + res.stderr), now_iso=now_iso)
    except subprocess.TimeoutExpired:
        return _result(verb, spec["hypothesis"], "error", exit_code=None,
                       summary=f"timed out after {timeout or spec['timeout']}s", now_iso=now_iso)
    except FileNotFoundError:
        return _result(verb, spec["hypothesis"], "error", exit_code=None,
                       summary="./moar not found in the docker dir", now_iso=now_iso)
    except Exception as e:  # noqa: BLE001 - surface any runner failure honestly
        return _result(verb, spec["hypothesis"], "error", exit_code=None,
                       summary=_sanitize(str(e))[:200], now_iso=now_iso)


def summarize(results) -> dict:
    """Aggregate run results for the gate's informational evidence line."""
    by = {"pass": 0, "fail": 0, "blocked": 0, "error": 0}
    last = None
    for r in results or []:
        by[r.get("status", "error")] = by.get(r.get("status", "error"), 0) + 1
        last = r.get("ran_at") or last
    return {"passing": by["pass"], "failing": by["fail"], "blocked": by["blocked"],
            "errored": by["error"], "total": len(results or []), "last_run": last}


def answer_equality_status(results, *, now_iso=None, ttl_seconds=None):
    """Lift the cross-engine answer-equality verdict (the `verify` verb) out of the
    evidence-verb results and into the gate's status vocabulary. `verify` is the
    differentiator claim — every running engine returns the SAME answer over the same
    Iceberg table — so once it has been run it earns a cert-bearing gate row, not just a
    count in the informational verb line.

    Returns None when verify was never run (the 7th gate row is omitted — back-compat);
    'pass' or 'fail' on a real exit code; 'unmeasured' when the run was blocked (no Docker)
    or errored (timeout/crash). A tried-but-couldn't-measure is labeled, never a bluffed
    pass — the same honesty rule the gate applies to every measured layer.

    When `now_iso` is supplied, a `pass` is aged through the same last-validated decay the
    gate applies to layers 1/3/4 (decay.effective_status): a verify pass older than the TTL
    (default one day) — or one that cannot be dated — decays to 'stale', which is not-green
    but not a failure ('re-run me'). So a days-old answer-equality run cannot keep the gate
    falsely GREEN. Omit `now_iso` for the raw mapping (pure status tests, or callers that
    decay separately).
    """
    r = next((x for x in (results or []) if x.get("verb") == "verify"), None)
    if r is None:
        return None
    status = r["status"] if r.get("status") in ("pass", "fail") else "unmeasured"
    if status == "pass" and now_iso is not None:
        return decay.effective_status("pass", r.get("ran_at"), now_iso,
                                      ttl_seconds if ttl_seconds is not None else decay.DEFAULT_TTL_SECONDS)
    return status
