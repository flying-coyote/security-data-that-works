"""AI tier — an air-gapped, practitioner-owned agentic hunt over the open lakehouse.

A ~code-action loop: a LOCAL model (Ollama) is given a hunt task + a read-only SQL tool over the OCSF
Iceberg table (loaded via pyiceberg into DuckDB), emits a query, sees the rows, iterates, and concludes.
Every component is on-box: local weights (Ollama on the host), the lakehouse, the agent. The only network
call is the loopback to the model server — nothing phones home. This is the MOAR answer to the SaaS agentic
SIEM: own the whole loop, run it air-gapped (cf. the lab's ocsf-airgap-agent / H-PRACTITIONER-OWNED-AGENTIC-01).

    docker compose --profile core --profile ai exec ai python /ai/agent.py
"""
import os
import re
import sys
import time

import duckdb
import requests
from pyiceberg.catalog.rest import RestCatalog

def _resolve_ollama():
    """Find the reachable Ollama base URL across networking modes — where the model server sits depends on how
    the host runs it. Under Docker Desktop on WSL2 with Ollama in a SEPARATE distro, host.docker.internal does
    NOT reach it (Docker's host gateway can't route into the distro); the distro's own IP does. Under mirrored
    WSL networking (or a Docker-host Ollama), host.docker.internal / localhost work. So probe candidates and use
    the first that answers instead of hardcoding one. OLLAMA_URL (explicit) and OLLAMA_HOST_IP (the WSL host IP,
    injected by `./moar`) are tried first."""
    cands, seen = [], set()
    for c in (os.environ.get("OLLAMA_URL", "").rstrip("/"),
              (f"http://{os.environ['OLLAMA_HOST_IP']}:11434" if os.environ.get("OLLAMA_HOST_IP", "").strip() else ""),
              "http://host.docker.internal:11434", "http://localhost:11434"):
        if c and c not in seen:
            seen.add(c); cands.append(c)
    for c in cands:
        try:
            requests.get(c + "/api/tags", timeout=4)
            return c
        except Exception:  # noqa: BLE001
            continue
    return cands[0] if cands else "http://host.docker.internal:11434"


OLLAMA_BASE = _resolve_ollama()
OLLAMA = OLLAMA_BASE + "/api/chat"
MODEL = os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
REST = os.environ.get("ICEBERG_REST_URI", "http://iceberg-rest:8181")
S3 = os.environ.get("S3_ENDPOINT", "http://minio:9000")
AK = os.environ.get("AWS_ACCESS_KEY_ID", "moar")
SK = os.environ.get("AWS_SECRET_ACCESS_KEY", "moar-dev-secret")
MAX_STEPS = 5

cat = RestCatalog("moar", **{"uri": REST, "warehouse": "s3://warehouse/", "s3.endpoint": S3,
                             "s3.access-key-id": AK, "s3.secret-access-key": SK,
                             "s3.path-style-access": "true", "s3.region": "us-east-1"})
con = duckdb.connect()
con.register("events", cat.load_table("ocsf.network_activity").scan().to_arrow())

TASK = ("Determine whether there is RDP lateral-movement traffic (destination port 3389) in the network "
        "activity, and report exactly how many such connections there are.")
SYSTEM = """You are a SOC hunt assistant in an AIR-GAPPED network. You query a local OCSF event store with
read-only SQL (DuckDB). Table `events` columns: time, class_uid, activity_id, src_ip, dst_port, bytes_out.
Reply with EXACTLY ONE of:
ACTION: <one read-only SELECT over events>
ANSWER: <your finding>
After an ACTION you get OBSERVATION: <rows>. Investigate, then ANSWER."""


def chat(messages):
    r = requests.post(OLLAMA, json={"model": MODEL, "stream": False, "messages": messages,
                                    "options": {"temperature": 0}}, timeout=300)
    return r.json()["message"]["content"]


def extract(kind, text):
    m = re.search(rf"{kind}:\s*(.+?)(?:\n\n|\Z)", text, re.S | re.I)
    if not m:
        return None
    return re.sub(r"^```\w*\s*|\s*```$", "", m.group(1).strip(), flags=re.S).strip()


def main():
    print(f"  model: {MODEL} @ {OLLAMA_BASE} (local, auto-resolved)")
    try:
        requests.get(OLLAMA_BASE + "/api/tags", timeout=5)
    except Exception as e:  # noqa: BLE001
        print("  ✗ no local model server reachable (tried OLLAMA_URL / OLLAMA_HOST_IP / host.docker.internal / localhost).")
        print(f"    Is 'ollama serve' up and bound to 0.0.0.0 (OLLAMA_HOST=0.0.0.0:11434)?  detail: {type(e).__name__}")
        sys.exit(2)
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": f"TASK: {TASK}"}]
    final = None
    for step in range(MAX_STEPS):
        reply = chat(msgs)
        msgs.append({"role": "assistant", "content": reply})
        ans, act = extract("ANSWER", reply), extract("ACTION", reply)
        if ans:
            final = ans
            print(f"  [step {step}] ANSWER: {ans[:200]}")
            break
        if act and re.match(r"(?i)^\s*select", act):
            q = act.rstrip(";").splitlines()[0]
            try:
                rows = con.execute(q + (" LIMIT 20" if "limit" not in q.lower() else "")).fetchall()
                obs = "\n".join(str(r) for r in rows[:15]) or "(no rows)"
            except Exception as e:  # noqa: BLE001
                obs = f"ERROR: {str(e)[:120]}"
            print(f"  [step {step}] ACTION: {q[:90]}  -> {obs.splitlines()[0][:60]}")
            msgs.append({"role": "user", "content": f"OBSERVATION:\n{obs[:1200]}"})
        else:
            msgs.append({"role": "user", "content": "Reply with one ACTION: or ANSWER: line."})
    found = bool(final and re.search(r"125", final))
    print(f"\n  air-gap ledger: only endpoint = {OLLAMA} (local model, loopback); lakehouse + agent on-box.")
    print(f"  hunt success (found 125 RDP conns): {found}")
    sys.exit(0 if found else 1)


if __name__ == "__main__":
    main()
