"""CF-FREE-SHORTLIST: the free/paid Capability Matrix shortlist CLI.

Two data paths, structurally separated:

  --mode free (default)  Reads ONLY fixtures/shortlist-free.yaml — the committed,
                          no-scores fixture checked into this public repo. Every
                          row carries public fields alone: category, code, label,
                          pros, cons, swap_cost, claims. There is no numeric score,
                          weight, or weighted total anywhere on this path, and no
                          code on this path opens a matrix-*.yaml or imports
                          paid_scoring.load_scores — the free path is structurally
                          incapable of reading scored data, not merely configured
                          not to. This is what any public clone gets: a shortlist
                          of components with pros/cons/reversibility, and a pointer
                          to the scored version at securitydataworks.com/matrix.

  --mode paid             Delegates to paid_scoring.load_scores(), which itself
                          enforces MOAR_PAID_MODE and refuses (PaidScoreLeak) to
                          source scores from inside this repo. In a public clone
                          this either prints nothing (PAID_MODE off, the default)
                          or raises if MOAR_SCORING_PATH is pointed inside the
                          repo. This CLI does not weaken either guarantee — it
                          just prints what load_scores() returns.

The free fixture is derived from providers.py's QUERY/CATALOG/INGEST catalogs
(the three Capability-Matrix-scored component categories this console picks
among) and is kept in lockstep with providers.py by prove_free_shortlist.py.

Run:
  python3 shortlist_from_yaml.py                       # free mode, all categories
  python3 shortlist_from_yaml.py --mode free --category query
  python3 shortlist_from_yaml.py --mode paid            # needs MOAR_PAID_MODE=1

Pure stdlib + PyYAML.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

_FIXTURE_DEFAULT = Path(__file__).resolve().parent / "fixtures" / "shortlist-free.yaml"
_PUBLIC_FIELDS = ("category", "code", "label", "pros", "cons", "swap_cost", "claims")
_MATRIX_URL = "securitydataworks.com/matrix"


def load_free_fixture(path: Path | str = _FIXTURE_DEFAULT) -> list[dict]:
    """Load the no-scores shortlist fixture and return its rows verbatim (as plain
    dicts, one per candidate). Does not filter, does not touch paid_scoring, does
    not open anything other than the single YAML file at `path`. Raises FileNotFoundError
    / yaml.YAMLError on a bad fixture rather than silently degrading, since a public
    clone's free path depends entirely on this file being present and well-formed."""
    text = Path(path).read_text(encoding="utf-8")
    doc = yaml.safe_load(text)
    rows = (doc or {}).get("shortlist") or []
    return [dict(r) for r in rows]


def free_shortlist(rows: list[dict], category: str | None = None) -> list[dict]:
    """Filter fixture rows to one category (query/catalog/ingest), or return all
    rows if category is None. Pure — no I/O, no paid_scoring import."""
    if category is None:
        return list(rows)
    return [r for r in rows if r.get("category") == category]


def render(rows: list[dict]) -> str:
    """Render a readable free-mode shortlist: one section per category, one line
    per candidate (label, one-line pros, swap_cost, claim refs), plus a header
    stating plainly that free mode carries no per-vendor scores and pointing at
    the scored version. Never prints a score/weight field because `rows` never
    carries one (see load_free_fixture / free_shortlist)."""
    lines = []
    lines.append("=== CF-FREE-SHORTLIST (free mode) ===")
    lines.append(
        f"Free mode carries NO per-vendor scores or weighted totals — pros/cons, "
        f"reversibility (swap_cost), and provenance claims only. "
        f"Scored Capability Matrix rankings: https://{_MATRIX_URL}"
    )
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        by_cat.setdefault(r.get("category", "?"), []).append(r)
    for cat in sorted(by_cat):
        lines.append("")
        lines.append(f"-- {cat} --")
        for r in by_cat[cat]:
            pros_line = (r.get("pros") or "").strip()
            swap = (r.get("swap_cost") or "").strip()
            claims = r.get("claims") or []
            claims_str = f" [claims: {', '.join(claims)}]" if claims else ""
            lines.append(f"  * {r.get('label')} ({r.get('code')})")
            lines.append(f"      pros: {pros_line}")
            lines.append(f"      swap_cost: {swap}{claims_str}")
    return "\n".join(lines)


def _run_free(category: str | None, fixture: Path) -> str:
    rows = load_free_fixture(fixture)
    rows = free_shortlist(rows, category=category)
    return render(rows)


def _run_paid(archetype: str = "A") -> str:
    # Imported lazily and ONLY on the paid path — the free path above never
    # references paid_scoring at all, let alone load_scores.
    import paid_scoring

    scores = paid_scoring.load_scores(archetype)
    if not scores:
        return (
            "=== CF-FREE-SHORTLIST (paid mode) ===\n"
            "No scores available (MOAR_PAID_MODE is off, or the scoring dir has no files "
            "for this archetype). Set MOAR_PAID_MODE=1 and MOAR_SCORING_PATH to the "
            "private vault's scoring dir to see the weighted ranking."
        )
    lines = ["=== CF-FREE-SHORTLIST (paid mode — weighted ranking) ==="]
    for name, rec in sorted(scores.items(), key=lambda kv: (kv[1].get("weighted") or 0), reverse=True):
        lines.append(f"  * {rec['name']} [{rec['category']}] weighted={rec['weighted']}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="CF-FREE-SHORTLIST: free/paid Capability Matrix shortlist")
    ap.add_argument("--mode", choices=("free", "paid"), default="free")
    ap.add_argument("--category", choices=("query", "catalog", "ingest"), default=None)
    ap.add_argument("--fixture", default=str(_FIXTURE_DEFAULT), help="path to the no-scores fixture (free mode only)")
    ap.add_argument("--archetype", default="A", help="scoring archetype A/B/C (paid mode only)")
    args = ap.parse_args(argv)

    if args.mode == "free":
        print(_run_free(args.category, Path(args.fixture)))
    else:
        print(_run_paid(args.archetype))
    return 0


if __name__ == "__main__":
    sys.exit(main())
