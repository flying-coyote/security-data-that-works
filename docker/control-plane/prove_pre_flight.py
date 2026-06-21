"""Proof for pre_flight — the Setup pre-flight diagnostics (Phase E).

Pure: ports_for + assemble_report against synthetic configs/results (no IO). The IO probes are tested
against a real-but-controlled local socket (a listener we bind = 'blocked'; the freed port = 'ok') and an
unreachable endpoint ('blocked'), plus the honest-degrade shape (a bad port -> 'unmeasured', never a faked
pass). No stack, no network beyond localhost.

Run:  python3 prove_pre_flight.py
"""
from __future__ import annotations

import socket
import sys

import pre_flight as pf

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def main():
    print("\n=== ports_for (pure) ===\n")
    minio_cfg = {"components": {"storage": {"provider": "minio", "port": 9100, "bucket_name": "warehouse"},
                                "catalog": {"port": 8181}}}
    names = {p["name"]: p["port"] for p in pf.ports_for(minio_cfg)}
    check("minio config -> storage(9100) + catalog(8181) + postgres(5432) + MinIO console(9001)",
          names.get("object store (S3)") == 9100 and names.get("catalog (REST)") == 8181
          and names.get("Postgres (catalog backend)") == 5432 and names.get("MinIO console") == 9001)
    check("seaweedfs config -> no MinIO console port",
          not any(p["name"] == "MinIO console" for p in pf.ports_for({"components": {"storage": {"provider": "seaweedfs", "port": 8333}}})))
    check("empty config -> defaults (8333 / 8181 / 5432)",
          {p["port"] for p in pf.ports_for({})} == {8333, 8181, 5432})

    print("\n=== check_docker (pure given the bool) ===\n")
    check("docker available -> ok", pf.check_docker(True)["status"] == pf.OK)
    check("docker unavailable -> blocked (never a faked pass)", pf.check_docker(False)["status"] == pf.BLOCKED)

    print("\n=== check_port_free (real local socket) ===\n")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    check("a port with a live listener -> blocked (in use)",
          pf.check_port_free("test", port)["status"] == pf.BLOCKED)
    srv.close()
    check("the same port after the listener is gone -> ok (free)",
          pf.check_port_free("test", port)["status"] == pf.OK)
    check("a non-integer port -> unmeasured (probe error, never a faked pass)",
          pf.check_port_free("test", "not-a-port")["status"] == pf.UNK)

    print("\n=== check_s3 (unreachable -> blocked; honest) ===\n")
    check("an unreachable endpoint -> blocked (never 'serving')",
          pf.check_s3("http://127.0.0.1:1", "warehouse")["status"] == pf.BLOCKED)

    print("\n=== assemble_report (pure verdict) ===\n")
    check("all checks ok -> ready", pf.assemble_report([{"status": pf.OK}, {"status": pf.OK}])["ready"] is True)
    check("a blocker -> not ready",
          pf.assemble_report([{"status": pf.OK}, {"status": pf.BLOCKED, "name": "x"}])["ready"] is False)
    check("an unmeasured check -> NOT ready (no green-light on an unprobed check)",
          pf.assemble_report([{"status": pf.OK}, {"status": pf.UNK}])["ready"] is False)
    check("no checks -> not ready (nothing proven)", pf.assemble_report([])["ready"] is False)

    print()
    if _failures:
        print(f"\033[91m{len(_failures)} assertion(s) FAILED:\033[0m " + "; ".join(_failures))
        return 1
    print("\033[92mAll pre_flight assertions held.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
