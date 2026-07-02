"""Proof for KIT-3 (CF-SCORING-SCHEMA) — the public Capability Matrix scoring
machinery ships EMPTY, and the linter that enforces its shape actually bites.

scoring-template.yaml is the schema half of the paid/public Matrix split: three
categories (query/catalog/ingest, mirroring paid_scoring._CATEGORY_FILE), each a
list of generic scoring dimensions with a name, an integer weight, and a
description. It must ship with zero vendor names and zero numeric scores — the
scored instances are paid Security Data Works IP that live only in the private
vault (see paid_scoring.py, the PaidScoreLeak firewall). scoring_lint.py is the
one piece of code that knows what a valid scoring file looks like; this harness
asserts three things about it: the shipped template actually satisfies its own
schema (dimension band, weight sum, zero scores/vendors); the template is
genuinely empty (no provider label from providers.py appears anywhere in it, and
none of the paid-only YAML keys do either); and — the part that would let a
regression slip through silently — the linter actually CATCHES every violation
this harness can think to construct, in both public and scored mode.

Run:  python3 prove_scoring_template.py     (exit 0 = every assertion held)
Pure stdlib + PyYAML; reads only the shipped template, touches no private vault.
"""
from __future__ import annotations

import copy
import re
import sys
from pathlib import Path

import yaml

import providers as P
import scoring_lint as lint_mod

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []

_HERE = Path(__file__).resolve().parent
_TEMPLATE_PATH = _HERE / "scoring-template.yaml"

# The paid-only YAML keys, matched as an actual mapping key (line starts with the key,
# optionally indented) so prose in the head comment that merely *names* these keys
# (explaining why they're absent) doesn't trip the check — only a real key: would.
_PAID_ONLY_KEYS_RE = re.compile(
    r"^\s*(candidates|candidate_pairs|weighted_total|evidence_tier|shipped_vs_claim_delta)\s*:",
    re.MULTILINE,
)


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def _all_labels() -> list[str]:
    labels: list[str] = []
    for group in P.CATEGORIES.values():
        labels.extend(p.label for p in group)
    return labels


def main():
    raw = _TEMPLATE_PATH.read_text(encoding="utf-8")
    doc = yaml.safe_load(raw)

    print("\n=== the shipped template parses and lints clean in public mode ===\n")
    check("scoring-template.yaml exists", _TEMPLATE_PATH.is_file())
    check("template parses as a mapping", isinstance(doc, dict))
    check("template lints CLEAN in public (default) mode", lint_mod.lint(doc, scored=False) == [])

    print("\n=== per category: 3-14 dimensions, weights sum to exactly 100 ===\n")
    categories = doc.get("categories", {})
    check("template defines all three categories (query/catalog/ingest)",
          {"query", "catalog", "ingest"} <= set(categories))
    for name in ("query", "catalog", "ingest"):
        dims = categories[name]["dimensions"]
        n = len(dims)
        check(f"category '{name}' has 3 <= {n} <= 14 dimensions", 3 <= n <= 14)
        total = sum(d["weight"] for d in dims)
        check(f"category '{name}' weights sum to exactly 100 (got {total})", total == 100)

    print("\n=== zero vendor names anywhere in the template ===\n")
    raw_lower = raw.lower()
    labels = _all_labels()
    check("providers.py yielded a non-empty label set to check against", len(labels) > 10)
    # Word-boundary match: a short label like "CEF" must not false-positive on a
    # substring of an unrelated word (e.g. "gracefully" contains "cef").
    leaked = [lbl for lbl in labels if re.search(rf"\b{re.escape(lbl.lower())}\b", raw_lower)]
    check(f"no provider label appears in the template {leaked or ''}", leaked == [])

    print("\n=== zero paid-only YAML keys anywhere in the template ===\n")
    leaked_keys = _PAID_ONLY_KEYS_RE.findall(raw)
    check(f"no paid-only key text appears as a real YAML key in the template {leaked_keys or ''}",
          leaked_keys == [])
    check("linter's own recursive scan finds nothing forbidden",
          lint_mod._scan_forbidden_keys(doc) == [])

    print("\n=== zero numeric scores anywhere in the template ===\n")
    all_scores = [d.get("score") for cat in categories.values() for d in cat["dimensions"]]
    check("every dimension's score is null/None", all(s is None for s in all_scores))
    check("no dimension carries a numeric score",
          not any(isinstance(s, (int, float)) and not isinstance(s, bool) for s in all_scores))

    print("\n=== the linter CATCHES violations (mutated in-memory copies) ===\n")

    bad_sum = copy.deepcopy(doc)
    dims = bad_sum["categories"]["query"]["dimensions"]
    dims[0]["weight"] = dims[0]["weight"] - 1  # 100 -> 99
    errs = lint_mod.lint(bad_sum, scored=False)
    check("weights summing to 99 lints DIRTY", any("sum" in e for e in errs))

    too_few = copy.deepcopy(doc)
    too_few["categories"]["catalog"]["dimensions"] = too_few["categories"]["catalog"]["dimensions"][:2]
    errs = lint_mod.lint(too_few, scored=False)
    check("a category with only 2 dimensions lints DIRTY", any("dimensions outside allowed band" in e for e in errs))

    too_many = copy.deepcopy(doc)
    extra = copy.deepcopy(too_many["categories"]["ingest"]["dimensions"][0])
    for _ in range(15 - len(too_many["categories"]["ingest"]["dimensions"])):
        too_many["categories"]["ingest"]["dimensions"].append(copy.deepcopy(extra))
    check("mutation actually produced 15 dimensions",
          len(too_many["categories"]["ingest"]["dimensions"]) == 15)
    errs = lint_mod.lint(too_many, scored=False)
    check("a category with 15 dimensions lints DIRTY", any("dimensions outside allowed band" in e for e in errs))

    injected_score = copy.deepcopy(doc)
    injected_score["categories"]["query"]["dimensions"][0]["score"] = 3
    errs = lint_mod.lint(injected_score, scored=False)
    check("an injected numeric score lints DIRTY in public mode",
          any("must not carry a numeric score" in e for e in errs))

    vendor_row = copy.deepcopy(doc)
    vendor_row["categories"]["catalog"]["candidates"] = [
        {"candidate": "Acme Catalog", "scores": {}}
    ]
    errs = lint_mod.lint(vendor_row, scored=False)
    check("a vendor 'candidates' entry lints DIRTY in public mode",
          any("paid-only key" in e for e in errs))

    print("\n=== scored mode: valid 1-5 scores lint clean; an out-of-range score fails ===\n")
    scored_doc = copy.deepcopy(doc)
    for cat in scored_doc["categories"].values():
        for d in cat["dimensions"]:
            d["score"] = 3
    errs = lint_mod.lint(scored_doc, scored=True)
    check("a fully-scored (1-5) doc lints CLEAN under --scored", errs == [])

    out_of_range = copy.deepcopy(scored_doc)
    out_of_range["categories"]["query"]["dimensions"][0]["score"] = 6
    errs = lint_mod.lint(out_of_range, scored=True)
    check("a score of 6 lints DIRTY under --scored", any("requires a score in 1..5" in e for e in errs))

    unscored_under_scored = copy.deepcopy(scored_doc)
    unscored_under_scored["categories"]["ingest"]["dimensions"][0]["score"] = None
    errs = lint_mod.lint(unscored_under_scored, scored=True)
    check("a null score lints DIRTY under --scored (nothing left unscored)",
          any("requires a score in 1..5" in e for e in errs))

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mThe public scoring schema ships empty, and the linter that guards it actually bites.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
