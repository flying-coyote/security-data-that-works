"""Proof for deploy_progress — the Setup deploy-progress checklist (Phase E, PE-2).

Pure: expected_containers (config -> container set), status_for (docker state -> progress vocabulary),
assemble_progress (verdict). The one IO path (check_container on an absent container -> pending) is
stack-independent (a non-existent name inspects as absent whether docker is up or down). No stack needed.

Run:  python3 prove_deploy_progress.py
"""
from __future__ import annotations

import sys

import deploy_progress as dp

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def main():
    print("\n=== expected_containers (pure) ===\n")
    cfg = {"components": {"storage": {"provider": "minio"}, "catalog": {"provider": "nessie"},
                          "pipeline": {"provider": ["vector", "fluentbit"]}}}
    names = [c["name"] for c in dp.expected_containers(cfg)]
    check("minio + nessie + [vector,fluentbit] -> postgres-db, minio, nessie, vector, fluentbit",
          names == ["postgres-db", "minio", "nessie", "vector", "fluentbit"])
    sw = [c["name"] for c in dp.expected_containers({"components": {"storage": {"provider": "seaweedfs"},
                                                                    "catalog": {"provider": "polaris"}}})]
    check("seaweedfs + polaris (default pipeline=vector) -> postgres-db, seaweedfs, polaris, vector",
          sw == ["postgres-db", "seaweedfs", "polaris", "vector"])
    check("empty config -> defaults (postgres-db, seaweedfs, polaris, vector)",
          [c["name"] for c in dp.expected_containers({})] == ["postgres-db", "seaweedfs", "polaris", "vector"])
    check("a string pipeline provider is tolerated (not just a list)",
          any(c["name"] == "fluentbit" for c in dp.expected_containers({"components": {"pipeline": {"provider": "fluentbit"}}})))

    print("\n=== status_for (pure docker-state mapping) ===\n")
    check("running -> up", dp.status_for("running") == dp.UP)
    check("created / restarting -> starting", dp.status_for("created") == dp.STARTING and dp.status_for("restarting") == dp.STARTING)
    check("exited / dead -> down", dp.status_for("exited") == dp.DOWN and dp.status_for("dead") == dp.DOWN)
    check("None (absent / unprobeable) -> pending", dp.status_for(None) == dp.PENDING)
    check("an unknown status -> unmeasured (never a faked up)", dp.status_for("weird") == dp.UNK)

    print("\n=== check_container on an absent container (stack-independent) ===\n")
    r = dp.check_container("moar-no-such-container-xyz", "test")
    check("a non-existent container -> pending (not created yet)", r["status"] == dp.PENDING)

    print("\n=== assemble_progress (pure verdict) ===\n")
    allup = [{"status": dp.UP}, {"status": dp.UP}]
    check("every container up -> complete", dp.assemble_progress(allup)["complete"] is True and dp.assemble_progress(allup)["up"] == 2)
    check("a pending container -> NOT complete",
          dp.assemble_progress([{"status": dp.UP}, {"status": dp.PENDING}])["complete"] is False)
    check("a starting container -> NOT complete, counted in pending",
          dp.assemble_progress([{"status": dp.UP}, {"status": dp.STARTING}])["complete"] is False
          and len(dp.assemble_progress([{"status": dp.UP}, {"status": dp.STARTING}])["pending"]) == 1)
    check("no stages -> not complete (nothing deployed)", dp.assemble_progress([])["complete"] is False)

    print()
    if _failures:
        print(f"\033[91m{len(_failures)} assertion(s) FAILED:\033[0m " + "; ".join(_failures))
        return 1
    print("\033[92mAll deploy_progress assertions held.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
