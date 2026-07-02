"""Linter for the KIT-3 (CF-SCORING-SCHEMA) Capability Matrix scoring shape.

scoring-template.yaml is the public schema a scored Matrix file must follow: three
categories (query/catalog/ingest), each a list of scoring dimensions with a name, an
integer weight, and a description. This module is the single place that shape is
checked, so both the shipped-empty public template and the private scored files (the
paid vault's matrix-*.yaml, loaded by paid_scoring.py) are validated against the same
rules instead of two hand-maintained copies of "what a scoring file looks like."

Two invariants hold in every mode: each category carries between 3 and 14 dimensions
(the dimension band — enough to be meaningful, few enough to stay legible), and each
category's weights are positive numbers summing to exactly 100. What differs is the
score column. The public template (default mode) must carry NO numeric scores and NO
vendor/candidate rows — that's the paid/public boundary made checkable, not just
promised in a docstring. Pass --scored to validate a private scored file instead,
where every dimension must instead carry a numeric score in 1-5.

CLI:
    python3 scoring_lint.py [FILE ...]     # public/template mode (default)
    python3 scoring_lint.py --scored FILE  # private scored-file mode

Exit 0 if every file lints clean, 1 otherwise (with the violations printed).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

MIN_DIMENSIONS = 3
MAX_DIMENSIONS = 14
WEIGHT_TOTAL = 100
REQUIRED_CATEGORIES = ("query", "catalog", "ingest")

# YAML keys that belong only to a SCORED Matrix file (paid_scoring._CATEGORY_FILE's
# vendor rows) and must never appear in the public template.
_FORBIDDEN_PUBLIC_KEYS = (
    "candidates",
    "candidate_pairs",
    "weighted_total",
    "evidence_tier",
    "shipped_vs_claim_delta",
)


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _scan_forbidden_keys(node, path: str = "") -> list[str]:
    """Recursively find any of the paid-only keys anywhere in the document."""
    hits: list[str] = []
    if isinstance(node, dict):
        for key, val in node.items():
            here = f"{path}.{key}" if path else str(key)
            if key in _FORBIDDEN_PUBLIC_KEYS:
                hits.append(here)
            hits.extend(_scan_forbidden_keys(val, here))
    elif isinstance(node, list):
        for i, item in enumerate(node):
            hits.extend(_scan_forbidden_keys(item, f"{path}[{i}]"))
    return hits


def lint(doc, scored: bool = False) -> list[str]:
    """Validate a parsed scoring document. Returns a list of violation messages
    (empty means clean). Never raises on a malformed doc — a bad shape is itself
    a violation to report, not a crash."""
    errors: list[str] = []
    if not isinstance(doc, dict):
        return ["top-level document must be a mapping"]

    categories = doc.get("categories")
    if not isinstance(categories, dict):
        return ["missing top-level 'categories' mapping"]

    for cat in REQUIRED_CATEGORIES:
        if cat not in categories:
            errors.append(f"missing required category '{cat}'")

    for cat_name, cat_body in categories.items():
        prefix = f"category '{cat_name}'"
        if not isinstance(cat_body, dict):
            errors.append(f"{prefix}: must be a mapping")
            continue
        dims = cat_body.get("dimensions")
        if not isinstance(dims, list):
            errors.append(f"{prefix}: missing 'dimensions' list")
            continue

        n = len(dims)
        if not (MIN_DIMENSIONS <= n <= MAX_DIMENSIONS):
            errors.append(
                f"{prefix}: {n} dimensions outside allowed band [{MIN_DIMENSIONS}, {MAX_DIMENSIONS}]"
            )

        weight_sum = 0.0
        for i, dim in enumerate(dims):
            name = dim.get("name", "?") if isinstance(dim, dict) else "?"
            dprefix = f"{prefix} dimension #{i} ({name})"
            if not isinstance(dim, dict):
                errors.append(f"{dprefix}: must be a mapping")
                continue

            weight = dim.get("weight")
            if not _is_number(weight) or weight <= 0:
                errors.append(f"{dprefix}: weight must be a positive number, got {weight!r}")
            else:
                weight_sum += weight

            score = dim.get("score")
            if scored:
                if not _is_number(score) or not (1 <= score <= 5):
                    errors.append(f"{dprefix}: scored mode requires a score in 1..5, got {score!r}")
            else:
                if score is not None:
                    errors.append(
                        f"{dprefix}: public template must not carry a numeric score, got {score!r}"
                    )

        if abs(weight_sum - WEIGHT_TOTAL) > 1e-9:
            errors.append(f"{prefix}: weights sum to {weight_sum}, must sum to exactly {WEIGHT_TOTAL}")

    if not scored:
        for hit in _scan_forbidden_keys(doc):
            errors.append(f"public template must not carry paid-only key at '{hit}'")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Lint a Capability Matrix scoring YAML file against the KIT-3 schema."
    )
    parser.add_argument(
        "files", nargs="*", help="YAML file(s) to lint (default: scoring-template.yaml next to this script)"
    )
    parser.add_argument(
        "--scored",
        action="store_true",
        help="Lint as a private SCORED file (scores 1-5 required) instead of the public empty template",
    )
    args = parser.parse_args(argv)

    files = [Path(f) for f in args.files] or [Path(__file__).resolve().parent / "scoring-template.yaml"]

    exit_code = 0
    for f in files:
        try:
            text = f.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"{f}: cannot read ({exc})")
            exit_code = 1
            continue
        try:
            doc = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            print(f"{f}: YAML parse error: {exc}")
            exit_code = 1
            continue

        errors = lint(doc, scored=args.scored)
        if errors:
            exit_code = 1
            print(f"{f}: {len(errors)} violation(s)")
            for err in errors:
                print(f"  - {err}")
        else:
            print(f"{f}: OK")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
