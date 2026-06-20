"""Paid Capability Matrix scoring for the MOAr console — PAID_MODE only.

The per-criterion 1-5 scores, weighted archetype totals, and claim-vs-shipped
deltas ARE paid SDW IP. They must never live in this public repo. This module loads
them at runtime ONLY when `MOAR_PAID_MODE` is set, and ONLY from a path OUTSIDE this
repository (default: the private project1 vault's `scoring/` dir). A pre-flight
assertion refuses to read scores from anywhere inside the public repo, so a paid
score can never be sourced from a committed file.

The public console (PAID_MODE off — what any clone gets) shows zero scores: method,
pros/cons, and provenance chips only, and links to /matrix for the scored version.
This is the §5 owner decision in MOAR-CONTROL-PLANE-EXTENSION-DESIGN.md, made
operational: a runtime flag that physically loads a different data file.

Env:
  MOAR_PAID_MODE      truthy (1/true/yes/on) to enable the scored view
  MOAR_SCORING_PATH   override the scoring dir; default $VAULT_PATH/02-projects/securitydataworks/scoring
  VAULT_PATH          the private project1 vault root (default ~/project1)
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
    return os.environ.get("MOAR_PAID_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


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
# catalogs, ingest = C4 pipelines. The PUBLIC view shows the component model + reversibility
# for these; the per-criterion 1-5 scores + weighted ranking stay paid (load_scores above).
_PUBLIC_CATEGORIES = ("query", "catalog", "ingest")


def public_context(picks: dict) -> list[dict]:
    """The PUBLIC-safe Capability Matrix context — the free counterpart to load_scores().

    Where load_scores() yields the paid per-criterion 1-5 scores (PAID_MODE only), this
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
