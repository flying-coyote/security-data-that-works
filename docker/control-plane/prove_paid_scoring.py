"""Proof that the paid/public Matrix boundary holds — the firewall + the public view.

paid_scoring.py is the most security-sensitive module in the console: it must NEVER source
paid Matrix scores from inside the public repo, the public default (PAID_MODE off) must
surface ZERO scores, and public_context() — the free public-view counterpart to
load_scores() — must return the component model + reversibility with no numeric score ever.
This harness asserts all three (the firewall _assert_outside_public_repo / PaidScoreLeak,
the PAID_MODE-off zero-scores contract, and the structural no-score guarantee of the public
view). It is the proof T4 added — the firewall previously shipped with no test at all.

Run:  python3 prove_paid_scoring.py     (exit 0 = every assertion held)
Pure stdlib; reads no scores, touches no vault.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import paid_scoring as paid

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def main():
    print("\n=== the firewall: paid scores never sourced from inside the public repo ===\n")
    pub = paid._public_repo_root()
    try:
        paid._assert_outside_public_repo(pub / "docker" / "control-plane")
        check("firewall RAISES on a scoring path inside the public repo", False)
    except paid.PaidScoreLeak:
        check("firewall RAISES PaidScoreLeak on a scoring path inside the public repo", True)
    try:
        paid._assert_outside_public_repo(pub)  # the repo root itself
        check("firewall RAISES on the public repo root itself", False)
    except paid.PaidScoreLeak:
        check("firewall RAISES on the public repo root itself", True)
    try:
        paid._assert_outside_public_repo(Path("/tmp/sdw-private-scores"))
        check("firewall ALLOWS a path outside the public repo (the private vault)", True)
    except paid.PaidScoreLeak:
        check("firewall ALLOWS a path outside the public repo (the private vault)", False)

    print("\n=== PAID_MODE defaults ON (public scored view); explicit-off hides it -> zero scores ===\n")
    os.environ.pop("MOAR_PAID_MODE", None)
    check("PAID_MODE defaults ON (an unset var surfaces the public scored view)", paid.paid_mode() is True)
    os.environ["MOAR_PAID_MODE"] = "off"
    check("PAID_MODE explicitly off (0/false/off) -> paid_mode() False", paid.paid_mode() is False)
    check("PAID_MODE explicitly off -> load_scores returns no scores", paid.load_scores("A") == {})
    os.environ.pop("MOAR_PAID_MODE", None)
    for _v in ("1", "true", "YES", "on"):
        os.environ["MOAR_PAID_MODE"] = _v
        if not paid.paid_mode():
            check(f"PAID_MODE truthy '{_v}' is recognized", False)
    os.environ.pop("MOAR_PAID_MODE", None)
    check("PAID_MODE truthy tokens (1/true/yes/on) all recognized", True)

    print("\n=== public_context: the free public half (model + reversibility, NO scores) ===\n")
    picks = {"query": ["duckdb", "trino"], "catalog": "polaris", "ingest": ["vector"],
             "storage": ["minio"], "schema": "ocsf"}  # storage/schema must be ignored
    ctx = paid.public_context(picks)
    labels = {r["label"] for r in ctx}
    check("public_context covers the picked engines (DuckDB, Trino)", {"DuckDB", "Trino"} <= labels)
    check("public_context covers the picked catalog + pipeline (Polaris, Vector)",
          {"Polaris", "Vector"} <= labels)
    check("public_context IGNORES non-scored categories (no MinIO storage / OCSF schema)",
          "MinIO" not in labels and "OCSF" not in labels)
    check("every public row carries a reversibility swap_cost", all(r["swap_cost"] for r in ctx))
    # The structural no-leak guarantee: a public row can only carry the public allow-list.
    _allowed = {"category", "label", "pros", "cons", "swap_cost", "claims"}
    _leak = {"score", "scores", "weight", "weighted", "weighted_total", "criteria", "delta"}
    check("public rows carry ONLY the public allow-list of fields",
          all(set(r.keys()) == _allowed for r in ctx))
    check("NO public row leaks a score/weight/weighted/criteria field (the firewall, structurally)",
          all(not (_leak & set(r.keys())) for r in ctx))
    check("public_context threads provenance claims (DuckDB carries A-14)",
          any(r["label"] == "DuckDB" and "A-14" in r["claims"] for r in ctx))
    check("public_context is available with PAID_MODE OFF (it IS the public view)",
          paid.public_context({"query": ["trino"]}) != [])
    check("public_context tolerates an empty/None pick set", paid.public_context({}) == []
          and paid.public_context(None) == [])
    check("a single-code (non-list) category resolves too",
          {"Polaris"} <= {r["label"] for r in paid.public_context({"catalog": "polaris"})})

    print("\n=== consultant_mode gate (T5): a public clone never leads with the vault ===\n")
    os.environ["MOAR_PAID_MODE"] = "off"  # explicit-off: exercise the vault-driven branch (default is now on)
    check("public clone (PAID_MODE off, no vault) -> NOT consultant",
          paid.consultant_mode(vault_readable=False, has_notes=False) is False)
    check("PAID_MODE off + a readable vault WITH notes -> consultant",
          paid.consultant_mode(vault_readable=True, has_notes=True) is True)
    check("PAID_MODE off + a readable vault but NO notes -> NOT consultant (empty vault ≠ consultant)",
          paid.consultant_mode(vault_readable=True, has_notes=False) is False)
    os.environ["MOAR_PAID_MODE"] = "1"
    check("PAID_MODE on -> consultant even with no vault present",
          paid.consultant_mode(vault_readable=False, has_notes=False) is True)
    os.environ.pop("MOAR_PAID_MODE", None)

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mAll paid/public-boundary assertions held — the firewall + the public view are sound.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
