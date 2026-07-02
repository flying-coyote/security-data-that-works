"""Proof for CF-SAMPLEVAULT — the bundled synthetic vault demos consultant mode, leaks nothing.

The public kit ships a SYNTHETIC OKF sample vault (`sample-vault/`, fictional notes with a
realistic frontmatter shape) so consultant mode is demonstrable from a public clone. That
widening must not move anything across the paid/public firewall, so this harness asserts
four things: the sample bundle actually loads and satisfies the consultant gate; every note
is explicitly marked synthetic; the bundle carries ZERO scored-Matrix content (no scoring
yamls, no score/weight/weighted_total keys); and the PaidScoreLeak guard still refuses to
source paid Matrix scores from the sample vault (or anywhere else inside the public repo).

Run:  python3 prove_sample_vault.py     (exit 0 = every assertion held)
Static — reads only files in this repo; touches no private vault, needs no stack.
"""
from __future__ import annotations

import os
import re
import sys

import okf_reader as okf
import paid_scoring as paid

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []

# The subdirs the console's vault cell reads (control_plane.py) — the sample bundle must
# populate the same shape.
_CONSOLE_SUBDIRS = [
    "02-projects/securitydataworks/decisions",
    "02-projects/securitydataworks/assumptions",
    "01-knowledge-base/hypotheses",
    "01-knowledge-base/contradictions",
]

# Scored-Matrix vocabulary that must never appear in the sample vault: the YAML keys the
# paid scoring files are made of (paid_scoring.load_scores reads exactly these).
_SCORED_KEYS = re.compile(
    r"^\s*(score|scores|weight|weighted_total|evidence_tier|shipped_vs_claim_delta|"
    r"candidates|candidate_pairs)\s*:",
    re.MULTILINE,
)


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def main():
    print("\n=== the sample vault is a loadable OKF bundle in the console's shape ===\n")
    check("sample vault directory ships with the repo", okf.SAMPLE_VAULT.is_dir())
    notes = okf.load_bundle(okf.SAMPLE_VAULT, subdirs=_CONSOLE_SUBDIRS)
    check("bundle loads notes from the console's subdirs", len(notes) >= 4)
    types = set(okf.by_type(notes))
    check("bundle carries MDR decision records", "MDR" in types)
    check("bundle carries Assumption records", "Assumption" in types)
    all_notes = okf.load_bundle(okf.SAMPLE_VAULT)
    check("every note is explicitly marked synthetic: true",
          all_notes and all(n.frontmatter.get("synthetic") is True for n in all_notes))
    check("every note title declares itself a sample",
          all(n.title.startswith("Sample —") for n in all_notes))
    check("notes link each other (the OKF relationship graph is demonstrable)",
          any(n.links for n in all_notes))

    print("\n=== resolve_vault_path: explicit VAULT_PATH wins; no vault -> sample fallback ===\n")
    _saved_vp, _saved_home = os.environ.get("VAULT_PATH"), os.environ.get("HOME")
    try:
        os.environ["VAULT_PATH"] = "/tmp/sdw-somewhere-else"
        p, is_sample = okf.resolve_vault_path()
        check("explicit VAULT_PATH is respected verbatim",
              str(p) == "/tmp/sdw-somewhere-else" and is_sample is False)
        os.environ.pop("VAULT_PATH", None)
        os.environ["HOME"] = "/tmp/sdw-no-such-home"  # no ~/project1 here
        p, is_sample = okf.resolve_vault_path()
        check("no VAULT_PATH + no private vault -> bundled sample vault (is_sample=True)",
              p == okf.SAMPLE_VAULT and is_sample is True)
        check("the fallback bundle satisfies the consultant gate (demonstrable from a clone)",
              paid.consultant_mode(vault_readable=True, has_notes=bool(notes)) is True)
    finally:
        for k, v in (("VAULT_PATH", _saved_vp), ("HOME", _saved_home)):
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    print("\n=== zero scored-Matrix content ships in the sample vault ===\n")
    files = [p for p in okf.SAMPLE_VAULT.rglob("*") if p.is_file()]
    check("sample vault contains no YAML files at all (scoring files are YAML)",
          not [p for p in files if p.suffix in (".yaml", ".yml")])
    check("no file matches the paid scoring filename shape (matrix-*.yaml)",
          not [p for p in files if p.name.startswith("matrix-")])
    dirty = [p.name for p in files if _SCORED_KEYS.search(p.read_text(encoding="utf-8"))]
    check(f"no scored-Matrix YAML keys anywhere in the bundle {dirty or ''}", not dirty)

    print("\n=== the PaidScoreLeak firewall still holds against the sample vault ===\n")
    try:
        paid._assert_outside_public_repo(okf.SAMPLE_VAULT)
        check("firewall RAISES on the sample vault (it is inside the public repo)", False)
    except paid.PaidScoreLeak:
        check("firewall RAISES PaidScoreLeak on the sample vault path", True)
    _saved = {k: os.environ.get(k) for k in ("MOAR_PAID_MODE", "MOAR_SCORING_PATH", "VAULT_PATH")}
    try:
        os.environ["MOAR_PAID_MODE"] = "1"
        os.environ.pop("MOAR_SCORING_PATH", None)
        os.environ["VAULT_PATH"] = str(okf.SAMPLE_VAULT)
        try:
            paid.load_scores("A")
            check("PAID_MODE on + VAULT_PATH at the sample vault -> load_scores refuses", False)
        except paid.PaidScoreLeak:
            check("PAID_MODE on + VAULT_PATH at the sample vault -> PaidScoreLeak raised", True)
        os.environ.pop("MOAR_PAID_MODE", None)
        check("PAID_MODE off over the sample vault -> zero scores, no error",
              paid.load_scores("A") == {})
    finally:
        for k, v in _saved.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mSample vault is synthetic, consultant-demonstrable, and leaks zero scored-Matrix content.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
