"""Proof for CF-FREE-SHORTLIST: the free-mode shortlist never touches paid scores.

shortlist_from_yaml.py --mode free is the public-clone data path: it must read ONLY
fixtures/shortlist-free.yaml, never import/call paid_scoring.load_scores, never open a
matrix-*.yaml, and emit output that carries no per-vendor score or weighted total. This
harness asserts, in order: the fixture parses and carries only the public allow-list of
fields (no score/weight/weighted/criteria/delta key, anywhere, recursively); the fixture
is in lockstep with providers.py's QUERY/CATALOG/INGEST catalogs (full two-way coverage,
so a future provider added/removed there can't silently drift from what free mode shows);
free mode runs end-to-end even if paid_scoring.load_scores is monkeypatched to explode;
free-mode output (both the in-process render() and a subprocess CLI run) leaks no score;
--mode free is paid-mode-proof (MOAR_PAID_MODE=1 doesn't change what it reads); and paid
mode still behaves exactly as paid_scoring.py promises (zero scores with PAID_MODE off,
PaidScoreLeak if pointed inside the repo).

A note on the no-score OUTPUT check: render()'s own header prose legitimately says
"NO per-vendor scores or weighted totals" (it explains the free/paid split to the reader),
so a bare substring check for "score" or "weighted" in the rendered text would false-positive
on that sentence, not on a real leak. The fixture's pros/cons strings were also grep-checked
(see the module docstring's sibling design note) and happen not to contain those words today,
but the check should not depend on that being permanently true. So the OUTPUT-shape checks
instead assert: (1) no NUMERIC score pattern anywhere (e.g. "4/5", "3.5/5"), and (2) no line
of output presents a paid field name as a structural key (a line starting with
"score:"/"weight:"/"weighted:"/"weighted_total:"/"criteria:"/"delta:", case-insensitive,
ignoring leading whitespace) — i.e. paid fields never appear as an output COLUMN, only
(harmlessly) as English prose describing the split. The dict-level leak-set check on the
fixture/rows above is the real structural guarantee; these output checks are a second,
independent line of defense against a future render() regression.

Run:  python3 prove_free_shortlist.py     (exit 0 = every assertion held)
Requires PyYAML (already a dependency of shortlist_from_yaml.py / paid_scoring.py).
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import paid_scoring as paid
import providers as P
import shortlist_from_yaml as sl

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []

_HERE = Path(__file__).resolve().parent
_FIXTURE = _HERE / "fixtures" / "shortlist-free.yaml"
_PUBLIC_FIELDS = {"category", "code", "label", "pros", "cons", "swap_cost", "claims"}
_LEAK_KEYS = {"score", "scores", "weight", "weighted", "weighted_total", "criteria", "delta"}
_NUMERIC_SCORE_RE = re.compile(r"\b[1-5](\.\d)?\s*/\s*5\b")
_KEY_LEAK_RE = re.compile(
    r"^\s*(score|scores|weight|weighted|weighted_total|criteria|delta)\s*:", re.IGNORECASE | re.MULTILINE
)


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def _find_leak_keys(obj) -> set:
    """Recursively collect any key name in obj (dict/list nesting) that matches the
    paid leak-set, so a nested/renamed leak can't slip past a shallow dict.keys() check."""
    found = set()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if str(k).lower() in _LEAK_KEYS:
                found.add(str(k).lower())
            found |= _find_leak_keys(v)
    elif isinstance(obj, list):
        for item in obj:
            found |= _find_leak_keys(item)
    return found


def main():
    print("\n=== the fixture parses and carries ONLY the public allow-list of fields ===\n")
    rows = sl.load_free_fixture(_FIXTURE)
    check("the fixture is non-empty", len(rows) > 0)
    check("every row's key set is exactly the public allow-list",
          all(set(r.keys()) == _PUBLIC_FIELDS for r in rows))
    check("no row (recursively) contains a paid leak-set key",
          _find_leak_keys(rows) == set())
    check("every row's category is one of the three scored categories",
          all(r["category"] in ("query", "catalog", "ingest") for r in rows))

    print("\n=== the fixture is in lockstep with providers.py (no drift, either direction) ===\n")
    groups = {"query": P.QUERY, "catalog": P.CATALOG, "ingest": P.INGEST}
    fixture_keys = {(r["category"], r["code"]) for r in rows}
    provider_keys = {(cat, p.code) for cat, grp in groups.items() for p in grp}
    check("every fixture (category, code) exists in providers.py", fixture_keys <= provider_keys)
    check("every providers.py QUERY/CATALOG/INGEST entry is present in the fixture (full coverage)",
          provider_keys <= fixture_keys)
    label_mismatches = []
    for r in rows:
        p = P.find(groups[r["category"]], r["code"])
        if p and p.label != r["label"]:
            label_mismatches.append((r["category"], r["code"]))
    check("every fixture row's label matches providers.py's label for that code",
          label_mismatches == [])

    print("\n=== free mode NEVER touches the paid loader ===\n")
    _orig_load_scores = paid.load_scores

    def _boom(*a, **kw):
        raise AssertionError("free path called paid_scoring.load_scores() — firewall breach")

    paid.load_scores = _boom
    try:
        end_to_end_rows = sl.load_free_fixture(_FIXTURE)
        end_to_end_rows = sl.free_shortlist(end_to_end_rows, category="query")
        text = sl.render(end_to_end_rows)
        check("free path (load + shortlist + render) completes with load_scores patched to explode",
              bool(text) and len(end_to_end_rows) > 0)
    except AssertionError as e:
        check(f"free path (load + shortlist + render) completes with load_scores patched to explode ({e})", False)
    finally:
        paid.load_scores = _orig_load_scores

    print("\n=== free-mode output leaks no per-vendor score (in-process render) ===\n")
    all_rows = sl.load_free_fixture(_FIXTURE)
    rendered = sl.render(all_rows)
    check("render() output has no numeric score pattern (e.g. 4/5, 3.5/5)",
          _NUMERIC_SCORE_RE.search(rendered) is None)
    check("render() output has no paid field name presented as a structural output key",
          _KEY_LEAK_RE.search(rendered) is None)
    check("render() output does point at the scored version (securitydataworks.com/matrix)",
          "securitydataworks.com/matrix" in rendered)

    print("\n=== free-mode output leaks no per-vendor score (subprocess CLI run) ===\n")
    proc = subprocess.run(
        [sys.executable, str(_HERE / "shortlist_from_yaml.py"), "--mode", "free"],
        capture_output=True, text=True, cwd=str(_HERE),
    )
    check("subprocess `--mode free` exits 0", proc.returncode == 0)
    check("subprocess output has no numeric score pattern",
          _NUMERIC_SCORE_RE.search(proc.stdout) is None)
    check("subprocess output has no paid field name presented as a structural output key",
          _KEY_LEAK_RE.search(proc.stdout) is None)

    print("\n=== --mode free is paid-mode-proof (MOAR_PAID_MODE=1 changes nothing it reads) ===\n")
    env_on = dict(os.environ)
    env_on["MOAR_PAID_MODE"] = "1"
    proc_on = subprocess.run(
        [sys.executable, str(_HERE / "shortlist_from_yaml.py"), "--mode", "free"],
        capture_output=True, text=True, cwd=str(_HERE), env=env_on,
    )
    check("`--mode free` with MOAR_PAID_MODE=1 exits 0", proc_on.returncode == 0)
    check("`--mode free` output is IDENTICAL whether or not MOAR_PAID_MODE is set",
          proc_on.stdout == proc.stdout)

    print("\n=== paid mode still behaves exactly as paid_scoring.py promises ===\n")
    _saved_paid_mode = os.environ.get("MOAR_PAID_MODE")
    os.environ["MOAR_PAID_MODE"] = "off"  # explicit-off: the default is now on, so exercise off here
    _saved_scoring_path = os.environ.pop("MOAR_SCORING_PATH", None)
    try:
        paid_off_text = sl._run_paid("A")
        check("paid mode with PAID_MODE off prints zero scores",
              "No scores available" in paid_off_text)
        check("paid mode with PAID_MODE off has no numeric score pattern either",
              _NUMERIC_SCORE_RE.search(paid_off_text) is None)

        os.environ["MOAR_PAID_MODE"] = "1"
        os.environ["MOAR_SCORING_PATH"] = str(_HERE)  # inside the public repo — must be refused
        try:
            sl._run_paid("A")
            check("paid mode with MOAR_SCORING_PATH inside the repo raises PaidScoreLeak", False)
        except paid.PaidScoreLeak:
            check("paid mode with MOAR_SCORING_PATH inside the repo raises PaidScoreLeak", True)
    finally:
        os.environ.pop("MOAR_PAID_MODE", None)
        os.environ.pop("MOAR_SCORING_PATH", None)
        if _saved_paid_mode is not None:
            os.environ["MOAR_PAID_MODE"] = _saved_paid_mode
        if _saved_scoring_path is not None:
            os.environ["MOAR_SCORING_PATH"] = _saved_scoring_path

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mAll CF-FREE-SHORTLIST assertions held — free mode never sources paid scores.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
