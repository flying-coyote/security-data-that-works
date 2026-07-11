"""Capability Matrix scoring for the MOAR console.

The scored Matrix is a public flagship-evidence asset: the per-criterion 1-5 scores, the
weighted archetype totals, and the claim-vs-shipped deltas surface by default, so
`MOAR_PAID_MODE` now defaults on and an unset var means the scored view is shown. What a
company pays for is the services engagement (assess, design, migrate, operate) that runs
against a Matrix finding when it deploys MOAR, not the scores.

The per-criterion scoring FILES still live in the project1 vault's `scoring/` dir rather
than in this repo, and this module reads them from that authored source at runtime. A
pre-flight assertion refuses to read scores from anywhere inside this public repo, so a
score is always sourced from its vault file and never from a stale copy committed here.
Set `MOAR_PAID_MODE` to a falsy value (0/false/off) to render the public component-model
half without the scored view (the free counterpart is `public_context`).

Env:
  MOAR_PAID_MODE      defaults on; set falsy (0/false/off) to hide the scored view
  MOAR_SCORING_PATH   override the scoring dir; default $VAULT_PATH/02-projects/securitydataworks/scoring
  VAULT_PATH          the project1 vault root that holds the scoring files (default ~/project1)
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

# Scored Matrix categories -> the per-archetype scoring file (A/B/C).
_CATEGORY_FILE = {
    "query": "matrix-c3-engines-{a}.yaml",
    "catalog": "matrix-c1c2-formats-catalogs-{a}.yaml",
    "ingest": "matrix-c4-pipelines-{a}.yaml",
}


class PaidScoreLeak(RuntimeError):
    """Raised if paid scores would be sourced from inside the public repo."""


def _public_repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / ".git").exists():
            return parent
    return p.parent


def paid_mode() -> bool:
    return os.environ.get("MOAR_PAID_MODE", "on").strip().lower() in {"1", "true", "yes", "on"}


def consultant_mode(*, vault_readable: bool, has_notes: bool) -> bool:
    """True when the console should lead the Strategy surface with the consultant overlay (the
    OKF strategy vault) rather than the public Matrix view. Consultant iff PAID_MODE is on OR a
    readable private vault with notes is present; a public clone (PAID_MODE off and no vault)
    is False and leads with the public Matrix context instead. The gate for T5 — the consultant
    surface no longer frames a public clone's Strategy tab. Pure: the caller supplies the two
    vault facts, so this stays a one-line boundary decision with no I/O."""
    return paid_mode() or (vault_readable and has_notes)


def scoring_dir() -> Path:
    explicit = os.environ.get("MOAR_SCORING_PATH")
    if explicit:
        return Path(explicit).expanduser()
    vault = Path(os.environ.get("VAULT_PATH", Path.home() / "project1")).expanduser()
    return vault / "02-projects" / "securitydataworks" / "scoring"


def _norm(s) -> str:
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def find(scores: dict, label: str):
    """Resolve a picker label to a scored record. The scoring yamls name catalogs in
    full ("Apache Polaris", "Project Nessie") while the picker uses short labels
    ("Polaris", "Nessie"), so match exact-normalized first, then substring either way."""
    n = _norm(label)
    if not n:
        return None
    if n in scores:
        return scores[n]
    for key, rec in scores.items():
        if n in key or key in n:
            return rec
    return None


def _candidate_name(cand: dict) -> str:
    # c3/c4 use `candidate`; c1c2 identifies the row by its catalog (and table_format).
    return str(cand.get("candidate") or cand.get("catalog") or cand.get("table_format") or "")


def _assert_outside_public_repo(sdir: Path) -> None:
    pub = _public_repo_root().resolve()
    sdir = sdir.resolve()
    if sdir == pub or pub in sdir.parents:
        raise PaidScoreLeak(
            f"Refusing to read paid Matrix scores from inside the public repo ({sdir}). "
            f"Point MOAR_SCORING_PATH at the private vault scoring dir."
        )


def load_scores(archetype: str = "A") -> dict:
    """Return {normalized_name: {category, name, weighted, criteria:[...]}} for one
    archetype. Empty dict when PAID_MODE is off. Raises PaidScoreLeak if the source
    path resolves inside the public repo (the zero-paid-scores-in-public guard)."""
    if not paid_mode():
        return {}
    sdir = scoring_dir()
    _assert_outside_public_repo(sdir)
    out: dict = {}
    a = archetype.upper()
    for category, tmpl in _CATEGORY_FILE.items():
        f = sdir / tmpl.format(a=a)
        if not f.exists():
            continue
        try:
            docs = list(yaml.safe_load_all(f.read_text(encoding="utf-8")))
        except (OSError, yaml.YAMLError):
            continue
        for d in docs:
            if not isinstance(d, dict):
                continue
            # c3/c4 engines+pipelines use `candidates`; c1c2 formats+catalogs use
            # `candidate_pairs` (one row per table_format+catalog pairing).
            rows = (d.get("candidates") or []) + (d.get("candidate_pairs") or [])
            for cand in rows:
                name = _candidate_name(cand)
                scores = cand.get("scores") or {}
                if not name or not scores:
                    continue
                criteria = []
                num = den = 0.0
                for cname, c in scores.items():
                    if not isinstance(c, dict):
                        continue
                    sc, w = c.get("score"), c.get("weight", 0)
                    if isinstance(sc, (int, float)) and isinstance(w, (int, float)):
                        num += sc * w
                        den += w
                    criteria.append({
                        "name": cname,
                        "score": c.get("score"),
                        "weight": c.get("weight"),
                        "tier": c.get("evidence_tier"),
                        "delta": c.get("shipped_vs_claim_delta"),
                    })
                # Prefer the file's authoritative weighted_total (c1c2) over a recompute.
                wt = cand.get("weighted_total")
                weighted = (round(float(wt), 2) if isinstance(wt, (int, float))
                            else (round(num / den, 2) if den else None))
                out[_norm(name)] = {
                    "category": category,
                    "name": name,
                    "weighted": weighted,
                    "criteria": criteria,
                }
    return out


# The Matrix-scored component categories: query = C3 engines, catalog = C1/C2 formats +
# catalogs, ingest = C4 pipelines. public_context shows the component model + reversibility
# for these; the per-criterion 1-5 scores + weighted ranking come from load_scores above (the
# public scored view, sourced from the vault scoring files).
_PUBLIC_CATEGORIES = ("query", "catalog", "ingest")


def public_context(picks: dict) -> list[dict]:
    """The PUBLIC-safe Capability Matrix context — the free counterpart to load_scores().

    Where load_scores() yields the per-criterion 1-5 scores (the scored view), this
    yields the half the public console gives away: the component model + reversibility for
    the picked scored components. picks: {category: code | [codes]} from the picker. Returns
    one row per picked scored component with ONLY public fields — category, label, pros,
    cons, swap_cost (reversibility), claims (provenance refs) — and NEVER a numeric score,
    weight, or weighted total. The no-score guarantee is structural: this function copies a
    fixed public allow-list of fields off providers.py and cannot reach a score. Pure; works
    with PAID_MODE off (it IS the public view) and ignores non-scored categories
    (storage/schema) even if present in `picks`."""
    import providers as _P  # one-directional; providers does not import this module
    groups = {"query": _P.QUERY, "catalog": _P.CATALOG, "ingest": _P.INGEST}
    rows: list[dict] = []
    for cat in _PUBLIC_CATEGORIES:
        val = (picks or {}).get(cat)
        if val is None:
            continue
        codes = val if isinstance(val, list) else [val]
        for code in codes:
            if not code:
                continue
            p = _P.find(groups[cat], code)
            if not p:
                continue
            rows.append({
                "category": cat,
                "label": p.label,
                "pros": p.pros,
                "cons": p.cons,
                "swap_cost": p.swap_cost,
                "claims": list(p.claims),
            })
    return rows
