"""Setup pre-flight diagnostics (Phase E): before a deploy, catch the things that silently fail a stack —
Docker unreachable, a port the deploy will bind already in use (a second stack, a stale container), the
object store not serving its bucket. The pure parts (`ports_for`, `assemble_report`) are unit-tested; each
IO probe (Docker / port / S3) degrades to 'unmeasured' on a probe error and is NEVER a fabricated pass —
the same honesty rule as the data-health gate (we don't green-light a deploy on an unprobed check)."""
from __future__ import annotations

import socket
import urllib.error
import urllib.request

OK, BLOCKED, UNK = "ok", "blocked", "unmeasured"


def ports_for(config_dict):
    """Pure: the host ports a deploy of `config_dict` will bind, as [{name, port}]. Mirrors
    pulumi_deployer.create_moar_program — the config-driven storage/catalog ports, the fixed Postgres
    catalog-backend, and the MinIO console when MinIO is the store. These are the ports that, already in
    use, make a deploy fail to bind."""
    comps = (config_dict or {}).get("components", {})
    storage = comps.get("storage", {}) or {}
    storage_port = int(storage.get("port", 8333))
    catalog_port = int((comps.get("catalog", {}) or {}).get("port", 8181))
    ports = [
        {"name": "object store (S3)", "port": storage_port},
        {"name": "catalog (REST)", "port": catalog_port},
        {"name": "Postgres (catalog backend)", "port": 5432},
    ]
    if storage.get("provider") == "minio":
        ports.append({"name": "MinIO console", "port": 9001})
    return ports


def check_docker(available):
    """Shape the Docker check from deployer.is_docker_available() (the caller owns the probe)."""
    return {"name": "Docker daemon", "status": OK if available else BLOCKED,
            "detail": "reachable" if available else "not reachable — start Docker before deploying"}


def check_port_free(name, port, host="127.0.0.1", timeout=0.4):
    """A port is FREE (ok) when nothing accepts a TCP connection on it, in-use (blocked) when something
    does, unmeasured when the probe itself errors. `connect_ex == 0` means a listener accepted -> in use."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            in_use = s.connect_ex((host, int(port))) == 0
        return {"name": f"port {port} — {name}", "status": BLOCKED if in_use else OK,
                "detail": "already in use (another stack? a stale container?)" if in_use else "free"}
    except (OSError, ValueError) as e:  # noqa: BLE001
        return {"name": f"port {port} — {name}", "status": UNK, "detail": f"probe error: {e}"}


def check_s3(endpoint, bucket, timeout=2.0):
    """The object store is serving: a HEAD on <endpoint>/<bucket> the server ANSWERS (any HTTP status,
    incl. 403/404 = up but bucket maybe-not-init) -> ok; a connection error -> blocked; anything else ->
    unmeasured. Never reads a body, so no telemetry surface."""
    url = f"{str(endpoint).rstrip('/')}/{bucket}"
    try:
        urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=timeout)
        return {"name": f"object store @ {endpoint}", "status": OK, "detail": f"serving (bucket '{bucket}')"}
    except urllib.error.HTTPError as e:
        return {"name": f"object store @ {endpoint}", "status": OK,
                "detail": f"serving (HTTP {e.code}; bucket '{bucket}' may need init)"}
    except (urllib.error.URLError, OSError) as e:
        return {"name": f"object store @ {endpoint}", "status": BLOCKED, "detail": f"unreachable: {getattr(e, 'reason', e)}"}
    except Exception as e:  # noqa: BLE001 — surface any probe failure honestly, never a faked pass
        return {"name": f"object store @ {endpoint}", "status": UNK, "detail": f"probe error: {e}"}


def run_preflight(config_dict, docker_available, s3_endpoint=None):
    """Orchestrate the checks into a results list. s3_endpoint defaults to localhost:<storage_port>."""
    results = [check_docker(docker_available)]
    for p in ports_for(config_dict):
        results.append(check_port_free(p["name"], p["port"]))
    storage = (config_dict or {}).get("components", {}).get("storage", {}) or {}
    endpoint = s3_endpoint or f"http://localhost:{int(storage.get('port', 8333))}"
    results.append(check_s3(endpoint, storage.get("bucket_name", "moar-warehouse")))
    return results


def assemble_report(results):
    """Pure: combine check results into {checks, ready, blockers, unmeasured}. ready = there ARE checks and
    every one is ok — an unmeasured check is NOT ready (we never green-light a deploy on an unprobed
    check, the gate's honesty rule)."""
    checks = list(results or [])
    blockers = [c for c in checks if c.get("status") == BLOCKED]
    unmeasured = [c for c in checks if c.get("status") == UNK]
    return {"checks": checks, "ready": bool(checks) and not blockers and not unmeasured,
            "blockers": blockers, "unmeasured": unmeasured}


def preflight_panel(mo, ui, report):
    """Render the pre-flight report. Never claims 'ready' unless every check is a measured pass."""
    glyph = {OK: "✅", BLOCKED: "⛔", UNK: "—"}
    rows = "\n".join(f"- {glyph.get(c['status'], '—')} **{c['name']}** — {c['detail']}" for c in report["checks"])
    if report["ready"]:
        head = "**<span style='color:#16a34a'>Pre-flight: ready to deploy</span>** — every check passed."
    elif report["blockers"]:
        head = (f"**<span style='color:#dc2626'>Pre-flight: not ready</span>** — "
                f"{len(report['blockers'])} blocker(s) to resolve before deploy.")
    elif report["unmeasured"]:
        head = "**<span style='color:#d97706'>Pre-flight: unproven</span>** — a check could not be measured; not green-lit."
    else:
        head = "*No pre-flight checks run yet.*"
    return ui.panel(mo, ui.header(mo, "Deploy pre-flight"), mo.md(head + ("\n\n" + rows if rows else "")))
