"""Setup deploy progress (Phase E, PE-2): instead of a single Deploy button + a final status line, show the
deploy as a checklist of the containers it creates, each in its real state — up / starting / down / pending.
The pure parts (`expected_containers`, `assemble_progress`) are unit-tested; the docker-state probe degrades
honestly (a container not yet created -> 'pending', a probe error / no docker -> 'unmeasured'), and is never
a fabricated 'up' — the same honesty rule as the gate and the pre-flight."""
from __future__ import annotations

import subprocess

UP, STARTING, DOWN, PENDING, UNK = "up", "starting", "down", "pending", "unmeasured"


def expected_containers(config_dict):
    """Pure: the container names a deploy of `config_dict` creates, mirroring
    pulumi_deployer.create_moar_program — Postgres (always, the catalog backend), the chosen object store,
    the chosen catalog, and each chosen router. Returns [{name, role}]."""
    comps = (config_dict or {}).get("components", {})
    storage = (comps.get("storage", {}) or {}).get("provider", "seaweedfs")
    catalog = (comps.get("catalog", {}) or {}).get("provider", "polaris")
    pipeline = (comps.get("pipeline", {}) or {}).get("provider", ["vector"])
    if isinstance(pipeline, str):
        pipeline = [pipeline]
    out = [{"name": "postgres-db", "role": "catalog backend"},
           {"name": "minio" if storage == "minio" else "seaweedfs", "role": "object store"},
           {"name": "nessie" if catalog == "nessie" else "polaris", "role": "catalog"}]
    for p in pipeline:
        if p in ("vector", "fluentbit"):
            out.append({"name": p, "role": "router"})
    return out


def _state(name):
    """The docker State.Status of a container by name, or None if absent / no docker / probe error."""
    try:
        r = subprocess.run(["docker", "inspect", "-f", "{{.State.Status}}", name],
                           capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None
    except Exception:  # noqa: BLE001 — no docker / timeout / error all mean "can't confirm up"
        return None


_STATE_MAP = {"running": UP, "restarting": STARTING, "created": STARTING,
              "paused": DOWN, "exited": DOWN, "dead": DOWN}


def status_for(docker_state):
    """Pure: a docker State.Status string -> the progress vocabulary. None (absent / unprobeable) ->
    pending; an unknown/unexpected status -> unmeasured (never a faked 'up')."""
    if docker_state is None:
        return PENDING
    return _STATE_MAP.get(docker_state, UNK)


def check_container(name, role=""):
    """A container's progress state. Absent -> pending (not created yet); see status_for for the mapping."""
    st = _state(name)
    return {"name": name, "role": role, "status": status_for(st), "detail": st if st else "not created yet"}


def deploy_progress(config_dict):
    return [check_container(c["name"], c["role"]) for c in expected_containers(config_dict)]


def assemble_progress(results):
    """Pure: {stages, up, total, complete, pending}. complete = there ARE stages and every one is up — a
    pending/starting/unmeasured stage is never 'complete'."""
    stages = list(results or [])
    up = [s for s in stages if s.get("status") == UP]
    return {"stages": stages, "up": len(up), "total": len(stages),
            "complete": bool(stages) and len(up) == len(stages),
            "pending": [s for s in stages if s.get("status") in (PENDING, STARTING)]}


def deploy_progress_panel(mo, ui, report):
    """Render the deploy progress checklist. Never claims 'complete' unless every container is up."""
    glyph = {UP: "✅", STARTING: "🔄", DOWN: "✗", PENDING: "○", UNK: "—"}
    rows = "\n".join(f"- {glyph.get(s['status'], '—')} **{s['name']}** ({s['role']}) — {s['detail']}"
                     for s in report["stages"])
    if not report["stages"]:
        head = "*No deploy target — pick a stack first.*"
    elif report["complete"]:
        head = f"**<span style='color:#16a34a'>Deploy complete</span>** — {report['up']}/{report['total']} containers up."
    else:
        head = (f"**Deploy progress: {report['up']}/{report['total']} up** "
                f"({len(report['pending'])} pending/starting).")
    return ui.panel(mo, ui.header(mo, "Deploy progress"), mo.md(head + ("\n\n" + rows if rows else "")))
