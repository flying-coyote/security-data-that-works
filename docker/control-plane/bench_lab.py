"""Bench-Lab runner — run SDW Lab benchmarks unattended, gate each on MECHANICAL
WELL-FORMEDNESS, and write one manifest + one full log per run.

This runs on the HOST, not in a container: it shells each bench out to the lab venv
(reg.LAB_VENV_PYTHON), captures the exit code, loads the bench's own results.json +
RESULTS.md, and asks a per-bench adapter whether the result is structurally complete and
didn't contradict its own correctness/determinism invariants. It is STDLIB-ONLY, because
the host python3 lacks pyiceberg/duckdb/chdb — the heavy deps live only in the lab venv.

The gate is NOT scientific promotion. A clean run means "well-formed", nothing more;
promotion to hypothesis evidence is a separate human gate (karen-evaluator ->
hypothesis-validator -> contradiction-detector). Tier-2/3 timing on a host without a
High-Performance power plan is invalid-environment, not a result — a pass on such a host
is downgraded.

Telemetry hygiene: synthetic security telemetry is a prompt-injection + control-char
surface, so every bench-output excerpt embedded in a manifest is bounded + sanitized via
the two helpers below. The full, unbounded stdout+stderr goes to a separate .log file,
never inlined.

Vocabulary note: this runner's verdicts are bench-specific (well-formedness, power-plan
validity, timeout) and are NOT the data-health gate statuses in CONTRACT.md
(pass/fail/unmeasured/unwired/stale). Don't conflate the two.
"""
from __future__ import annotations

import argparse
import datetime
import glob
import hashlib
import json
import os
import platform
import re
import subprocess
import sys

import bench_lab_registry as reg

_HERE = os.path.dirname(os.path.abspath(__file__))
BENCH_RUNS_DIR = os.path.join(_HERE, "bench-runs")

# ANSI tally colors (match prove_evidence.py's pattern).
_GREEN, _RED, _YELLOW, _RESET = "\033[92m", "\033[91m", "\033[93m", "\033[0m"

# Hardcoded honesty note stamped into every manifest.
_PROMOTION_NOTE = (
    "Mechanical well-formedness only. Promotion to hypothesis evidence is a separate "
    "human gate (karen-evaluator -> hypothesis-validator -> contradiction-detector). "
    "Tier-2/3 timing on a non-power-planned host is invalid-environment, not a result."
)


# --- copied VERBATIM from docker/control-plane/evidence_runner.py lines 52-67 ---------
# (telemetry-injection + control-char hygiene; the same rule applies to bench output read
#  back into context.)
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def _sanitize(text: str) -> str:
    """Strip ANSI escapes and control chars (keep \n and \t). Output is read back into
    context, so it gets the same hygiene as telemetry. (copied from evidence_runner.py)"""
    text = _ANSI.sub("", text)
    return "".join(ch for ch in text if ch in "\n\t" or ord(ch) >= 32)


def _bounded(text: str, max_lines: int = 15, max_chars: int = 1800) -> str:
    """Keep only the tail (the verdict lives at the end) and cap length. (copied from evidence_runner.py)"""
    lines = _sanitize(text).strip().splitlines()
    out = "\n".join(lines[-max_lines:])
    return ("…" + out[-max_chars:]) if len(out) > max_chars else out
# --- end copied helpers --------------------------------------------------------------


def _utcnow():
    return datetime.datetime.now(datetime.timezone.utc)


def precheck(name):
    """(ok, msg). Verify the lab venv python, the bench, and its dir are all present."""
    if not os.path.exists(reg.LAB_VENV_PYTHON):
        return (False, f"lab venv python missing at {reg.LAB_VENV_PYTHON} — create the lab venv first "
                       f"(cd {reg.LAB_ROOT} && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt)")
    spec = reg.BENCHES.get(name)
    if spec is None:
        return (False, f"unknown bench '{name}' — not in the registry")
    bench_dir = os.path.join(reg.LAB_ROOT, spec["dir"])
    if not os.path.isdir(bench_dir):
        return (False, f"bench dir missing: {bench_dir}")
    return (True, "ok")


def env_snapshot():
    """Host/lab environment fingerprint stamped into every manifest."""
    snap = {
        "python": sys.version.split()[0],
        "lab_duckdb": "unavailable",
        "lab_chdb": "unavailable",
        "cpu": os.cpu_count(),
        "ram_gb": "unknown",
        "power_plan": "unknown",
        "os": platform.platform(),
    }
    # lab venv versions of the two timing-relevant deps
    try:
        p = subprocess.run(
            [reg.LAB_VENV_PYTHON, "-c", "import duckdb,chdb;print(duckdb.__version__);print(chdb.__version__)"],
            capture_output=True, text=True, timeout=20,
        )
        if p.returncode == 0:
            lines = p.stdout.strip().splitlines()
            if len(lines) >= 2:
                snap["lab_duckdb"], snap["lab_chdb"] = lines[0].strip(), lines[1].strip()
    except Exception:
        pass
    # RAM from /proc/meminfo
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    snap["ram_gb"] = round(kb / (1024 * 1024), 1)
                    break
    except Exception:
        pass
    # Windows power plan (WSL host); scheme name is in parens, e.g. "(High performance)"
    try:
        p = subprocess.run(
            ["/mnt/c/Windows/System32/powercfg.exe", "/getactivescheme"],
            capture_output=True, text=True, timeout=10,
        )
        if p.returncode == 0:
            m = re.search(r"\(([^)]+)\)", p.stdout)
            snap["power_plan"] = m.group(1).strip() if m else _sanitize(p.stdout).strip() or "unknown"
    except Exception:
        pass
    return snap


def is_high_performance(power_plan_str):
    s = (power_plan_str or "").lower()
    return ("high performance" in s) or ("ultimate performance" in s)


def git_head(repo_path):
    """READ-ONLY git only: short HEAD + dirty flag. Never mutates. On any failure ->
    {"head": "unknown", "dirty": None}."""
    try:
        head = subprocess.run(["git", "-C", repo_path, "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10)
        if head.returncode != 0:
            return {"head": "unknown", "dirty": None}
        status = subprocess.run(["git", "-C", repo_path, "status", "--porcelain"],
                                capture_output=True, text=True, timeout=10)
        dirty = bool(status.stdout.strip()) if status.returncode == 0 else None
        return {"head": head.stdout.strip(), "dirty": dirty}
    except Exception:
        return {"head": "unknown", "dirty": None}


def _spoke_repo():
    """The security-data-that-works repo root: two dirs up from control-plane is docker/,
    three up is the repo. Verify it has a .git; else fall back to the hardcoded path."""
    candidate = os.path.dirname(os.path.dirname(os.path.dirname(_HERE)))
    if os.path.isdir(os.path.join(candidate, ".git")):
        return candidate
    return os.path.expanduser("~/security-data-that-works")


def run_bench(name, timeout):
    """(exit_code, stdout, stderr, duration_s). exit_code is None on timeout."""
    spec = reg.BENCHES[name]
    bench_dir = os.path.join(reg.LAB_ROOT, spec["dir"])
    start = _utcnow()
    try:
        p = subprocess.run([reg.LAB_VENV_PYTHON, *spec["entry"]],
                           cwd=bench_dir, capture_output=True, text=True, timeout=timeout)
        dur = (_utcnow() - start).total_seconds()
        return (p.returncode, p.stdout, p.stderr, dur)
    except subprocess.TimeoutExpired as e:
        dur = (_utcnow() - start).total_seconds()
        out = e.stdout or ""
        err = (e.stderr or "") + f"\n[bench_lab] TIMEOUT after {timeout}s"
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        if isinstance(err, bytes):
            err = err.decode("utf-8", "replace")
        return (None, out, err, dur)
    except FileNotFoundError as e:
        dur = (_utcnow() - start).total_seconds()
        return (127, "", f"[bench_lab] cannot launch bench: {e} "
                         f"(entry={spec['entry']}, venv={reg.LAB_VENV_PYTHON})", dur)


def load_results(name):
    """(results_dict_or_None, raw_bytes_or_None, has_results_md). RESULTS.md presence is
    checked in BOTH <dir>/results/RESULTS.md and any top-level <dir>/RESULTS*.md (glob),
    since some benches write RESULTS to the top level."""
    spec = reg.BENCHES[name]
    bench_dir = os.path.join(reg.LAB_ROOT, spec["dir"])
    results_dict, raw = None, None
    if spec["results"] is not None:
        rp = os.path.join(bench_dir, spec["results"])
        try:
            with open(rp, "rb") as f:
                raw = f.read()
            results_dict = json.loads(raw.decode("utf-8"))
        except Exception:
            results_dict, raw = None, None
    nested_md = os.path.exists(os.path.join(bench_dir, "results", "RESULTS.md"))
    toplevel_md = bool(glob.glob(os.path.join(bench_dir, "RESULTS*.md")))
    return (results_dict, raw, nested_md or toplevel_md)


def gate(name, results, exit_code, has_results_md):
    spec = reg.BENCHES[name]
    adapter = reg.ADAPTERS[spec["adapter"]]
    return adapter(results, exit_code=exit_code, has_results_md=has_results_md)


def classify_failure(stderr_tail, exit_code):
    """Bucket a failure into an actionable class. Operates on the already
    sanitized+bounded stderr tail."""
    low = (stderr_tail or "").lower()
    if exit_code is None or "timeout after" in low:
        return {"class": "timeout",
                "message": "bench exceeded the time limit — raise --timeout or reduce the scale"}
    if exit_code == 137:
        return {"class": "oom", "message": "killed (exit 137) — out of memory; lower the scale or free RAM"}
    if "warehouse not found" in low:
        return {"class": "cold-start", "message": "warehouse not found — cold catalog; seed once and retry"}
    if (":9000" in low and ("refused" in low or "connection" in low)) or "failed to get iceberg metadata" in low:
        return {"class": "tier3-misroute",
                "message": "needs the compose stack (MinIO :9000 / iceberg catalog) — bring up ./moar, not a host run"}
    if "assertionerror" in low and "determinism" in low:
        return {"class": "nondeterminism",
                "message": "determinism assertion failed — DO NOT publish; the result is non-reproducible"}
    if "modulenotfounderror" in low:
        m = re.search(r"no module named ['\"]([^'\"]+)['\"]", low)
        mod = m.group(1) if m else "?"
        return {"class": "missing-prereq",
                "message": f"missing python module '{mod}' in the lab venv — pip install it into {reg.LAB_VENV_PYTHON}"}
    return {"class": "unknown", "message": "unrecognized failure; see log. tail: " + (stderr_tail or "")[-400:]}


def results_sha256(raw_bytes):
    if raw_bytes is None:
        return None
    return hashlib.sha256(raw_bytes).hexdigest()


def assemble_manifest(*, run_id, name, exit_code, duration_s, verdict, notes, failure,
                      env, git_info, results_path, sha, results_md_present,
                      stdout, stderr, log_basename):
    spec = reg.BENCHES[name]
    return {
        "run_id": run_id,
        "bench": name,
        "tier": spec["tier"],
        "adapter": spec["adapter"],
        "exit_code": exit_code,
        "duration_s": round(duration_s, 3) if duration_s is not None else None,
        "gate": {"verdict": verdict, "notes": notes},
        "failure": failure,  # dict only when exit!=0 or verdict in {fail, invalid-environment}; else None
        "env": env,
        "git": git_info,
        "results_path": results_path,
        "results_sha256": sha,
        "results_md_present": results_md_present,
        "stdout_excerpt": _bounded(stdout or ""),
        "stderr_excerpt": _bounded(stderr or ""),
        "ran_at": _utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "log_path": log_basename,
        "notes": _PROMOTION_NOTE,
    }


def _color_for(verdict):
    if verdict == "pass":
        return _GREEN
    if verdict == "fail":
        return _RED
    return _YELLOW  # invalid-environment | blocked | not-wired


def _write_and_tally(manifest, full_log):
    """Persist <run_id>.json + <run_id>.log, print the one-line colored tally."""
    os.makedirs(BENCH_RUNS_DIR, exist_ok=True)
    run_id = manifest["run_id"]
    with open(os.path.join(BENCH_RUNS_DIR, run_id + ".json"), "w") as f:
        json.dump(manifest, f, indent=2)
    with open(os.path.join(BENCH_RUNS_DIR, run_id + ".log"), "w") as f:
        f.write(full_log)
    v = manifest["gate"]["verdict"]
    dur = manifest["duration_s"]
    dur_s = f"{dur:.1f}s" if isinstance(dur, (int, float)) else "—"
    c = _color_for(v)
    print(f"  {c}{v:>20}{_RESET}  {manifest['bench']:<32} {dur_s:>8}  {manifest['gate']['notes']}")


def _stub_manifest(name, verdict, notes):
    """Manifest for a bench that never ran (blocked precheck / not-wired)."""
    run_id = f"{name}-{_utcnow():%Y%m%dT%H%M%SZ}"
    return assemble_manifest(
        run_id=run_id, name=name, exit_code=None, duration_s=None,
        verdict=verdict, notes=notes, failure=None,
        env=env_snapshot(), git_info={"spoke": git_head(_spoke_repo()), "lab": git_head(reg.LAB_ROOT)},
        results_path=reg.BENCHES[name]["results"], sha=None, results_md_present=False,
        stdout="", stderr="", log_basename=run_id + ".log",
    )


def run_one(name, timeout, power_plan=None):
    """Run a single bench end to end and return its manifest (already written to disk)."""
    spec = reg.BENCHES.get(name)
    if spec is None:
        m = _stub_manifest(name, "blocked", f"unknown bench '{name}'")
        _write_and_tally(m, "")
        return m

    ok, msg = precheck(name)
    if not ok:
        m = _stub_manifest(name, "blocked", msg)
        _write_and_tally(m, "")
        return m

    if spec.get("runnable") is False:
        note = spec.get("note")
        if spec["tier"] == 3:
            reason = "tier-3 needs the docker compose stack — registered but not auto-runnable; run it under ./moar up"
        elif note:
            reason = note
        else:
            reason = "not auto-runnable"
        m = _stub_manifest(name, "not-wired", reason)
        _write_and_tally(m, "")
        return m

    if power_plan is None:
        power_plan = env_snapshot().get("power_plan", "unknown")

    exit_code, stdout, stderr, duration = run_bench(name, timeout)

    # cold-start retry ONCE
    if exit_code not in (0, None):
        cls = classify_failure(_bounded(stderr), exit_code)
        if cls["class"] == "cold-start":
            exit_code, stdout, stderr, duration = run_bench(name, timeout)

    results, raw, has_md = load_results(name)
    verdict, notes = gate(name, results, exit_code, has_md)

    # power-plan guard: a tier->=2 timing pass on a non-power-planned host is not trustworthy.
    if spec["tier"] >= 2 and verdict == "pass" and not is_high_performance(power_plan):
        verdict = "invalid-environment"
        notes += (f" [tier-≥2 pass downgraded: power plan '{power_plan}' is not High-Performance — "
                  "re-run on a power-planned host]")

    failure = None
    if exit_code not in (0,) or verdict in ("fail", "invalid-environment"):
        failure = classify_failure(_bounded(stderr), exit_code)

    run_id = f"{name}-{_utcnow():%Y%m%dT%H%M%SZ}"
    manifest = assemble_manifest(
        run_id=run_id, name=name, exit_code=exit_code, duration_s=duration,
        verdict=verdict, notes=notes, failure=failure,
        env=env_snapshot(), git_info={"spoke": git_head(_spoke_repo()), "lab": git_head(reg.LAB_ROOT)},
        results_path=spec["results"], sha=results_sha256(raw), results_md_present=has_md,
        stdout=stdout, stderr=stderr, log_basename=run_id + ".log",
    )
    full_log = (f"# bench={name} run_id={run_id} exit_code={exit_code} verdict={verdict}\n"
                f"# ===== STDOUT =====\n{stdout or ''}\n# ===== STDERR =====\n{stderr or ''}\n")
    _write_and_tally(manifest, full_log)
    return manifest


def _already_ran(name):
    return bool(glob.glob(os.path.join(BENCH_RUNS_DIR, f"{name}-*.json")))


def run_target(target, timeout, cont=False):
    """Run a bench name, a tier (tier1|tier2|tier3), or all. Returns the manifest list."""
    if target in reg.BENCHES:
        names = [target]
    elif target in ("tier1", "tier2", "tier3"):
        names = list(reg.TIERS[int(target[-1])])
    elif target == "all":
        names = list(reg.TIERS[1]) + list(reg.TIERS[2]) + list(reg.TIERS[3])
    else:
        valid = "  benches: " + ", ".join(sorted(reg.BENCHES)) + "\n  groups: tier1, tier2, tier3, all"
        print(f"unknown target '{target}'. valid targets:\n{valid}")
        sys.exit(2)

    # Snapshot the power plan ONCE up front (avoid one powercfg call per bench).
    power_plan = env_snapshot().get("power_plan", "unknown")
    print(f"power plan: {power_plan}  (High-Performance: {is_high_performance(power_plan)})")

    manifests = []
    for name in names:
        if cont and _already_ran(name):
            print(f"  {_YELLOW}{'skipped (--continue)':>20}{_RESET}  {name}")
            continue
        manifests.append(run_one(name, timeout, power_plan=power_plan))

    # final summary tally
    counts = {}
    for m in manifests:
        v = m["gate"]["verdict"]
        counts[v] = counts.get(v, 0) + 1
    parts = []
    for v in ("pass", "fail", "invalid-environment", "blocked", "not-wired"):
        if counts.get(v):
            parts.append(f"{_color_for(v)}{v}={counts[v]}{_RESET}")
    print("\nsummary: " + ("  ".join(parts) if parts else "no benches run"))
    return manifests


def main():
    ap = argparse.ArgumentParser(
        prog="bench_lab",
        description="Run SDW Lab benchmarks unattended with mechanical well-formedness gating + manifests.")
    ap.add_argument("target", help="a bench name, a tier (tier1|tier2|tier3), or all")
    ap.add_argument("--timeout", type=int, default=1800, help="per-bench timeout in seconds (default 1800)")
    ap.add_argument("--continue", dest="cont", action="store_true",
                    help="skip benches that already have a manifest in bench-runs/")
    args = ap.parse_args()

    manifests = run_target(args.target, args.timeout, cont=args.cont)
    # invalid-environment / blocked / not-wired are honest non-results, NOT script failures.
    return 1 if any(m["gate"]["verdict"] == "fail" for m in manifests) else 0


if __name__ == "__main__":
    sys.exit(main())
