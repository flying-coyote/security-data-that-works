"""Layer 4 DEEP — deterministic entity resolution with confidence + freshness.

The exact-match cross-tool gap (`layer4_audit.cross_tool_gap`) reads `web-01` and
`web-01.corp` as two different assets, so it over-reports gaps. This resolves them —
the part Service 4 actually sells — but only through DECLARED, deterministic
normalization rules, and only when the match is both confident AND fresh.

The honesty floor the whole gate rests on applies hardest here, because a *wrong* merge
does not over-report a gap, it HIDES one: collapse two genuinely-different hosts into one
entity and a real blind spot disappears from the count — a false pass, the worst outcome
this console can produce. So the rule is fail-closed in the resolution direction:

  - a match only closes a gap when its confidence clears a declared threshold AND the
    matched record is fresh within a TTL (reusing the same `decay` contract every other
    layer uses);
  - anything ambiguous (a primary id that matches two source ids, or two primary ids that
    collapse together, or an in-source collision) is left UNRESOLVED and counted toward
    the gap, never silently coalesced;
  - a stale match (the source has timestamps but this record is too old, or undatable) is
    counted as a gap, not as coverage — a host the EDR last reported six weeks ago is not
    "covered."

Counts only; raw identities are never rendered (the telemetry-injection rule — an asset id
set is still data pulled from the lake).

Resolution is intentionally NOT machine-learning fuzzy matching. Every rule is explicit and
auditable; the layer would rather report an honest gap than guess a host into coverage.
"""
from __future__ import annotations

import decay

DEFAULT_MIN_CONFIDENCE = 0.9
DEFAULT_TTL_SECONDS = decay.DEFAULT_TTL_SECONDS


def _strip_suffixes(value, suffixes):
    for suf in suffixes:  # suffixes pre-sorted longest-first by the caller
        if value.endswith(suf):
            return value[: -len(suf)]
    return value


def default_rules(domain_suffixes=(".corp", ".local", ".internal")):
    """Declared normalization ladder, most-conservative first. Each entry is
    (name, transform, confidence-that-the-transform-preserves-identity).

    Deliberately omits aggressive moves that would cause false merges — e.g. stripping a
    trailing numeric index would collapse `web-01` and `web-02` (different hosts) and is
    NOT included. Case-folding and a declared domain-suffix strip are the safe, common
    real-world cases; add rules here, with an honest confidence, never inline guesses.
    """
    sufs = tuple(sorted((s.lower() for s in domain_suffixes), key=len, reverse=True))
    return [
        ("exact", lambda s: s, 1.0),
        ("case-insensitive", lambda s: s.lower(), 0.99),
        ("strip-domain-suffix", lambda s: _strip_suffixes(s.lower(), sufs), 0.9),
    ]


def canonical_forms(raw, rules):
    """Ordered (confidence, key) forms for one raw id, highest confidence first."""
    return [(conf, fn(raw)) for (_name, fn, conf) in rules]


def match_confidence(a, b, rules) -> float:
    """Highest rule confidence at which two raw ids share a normalized form, else 0.0."""
    best = 0.0
    for (conf, ka), (_cb, kb) in zip(canonical_forms(a, rules), canonical_forms(b, rules)):
        if ka == kb and conf > best:
            best = conf
    return best


def _self_colliding(ids, rules, min_confidence):
    """Raw ids within one inventory that resolve to each other at/above threshold — we
    cannot tell them apart, so they are ambiguous by construction (never auto-merged)."""
    ids = list(ids)
    bad = set()
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            if match_confidence(ids[i], ids[j], rules) >= min_confidence:
                bad.add(ids[i])
                bad.add(ids[j])
    return bad


def _source_has_freshness(meta) -> bool:
    return any(v is not None for v in meta.values())


def resolve_against(primary_meta, source_meta, *, rules, now_iso,
                    min_confidence=DEFAULT_MIN_CONFIDENCE, ttl_seconds=DEFAULT_TTL_SECONDS):
    """Classify every primary entity against one source inventory.

    primary_meta / source_meta: {raw_id: last_seen_iso_or_None}.

    Returns counts only: covered / gap / stale / unresolved (+ confidence-only flag when
    the source carries no timestamps at all, so freshness could not be assessed). The four
    non-covered buckets are mutually exclusive per entity; gap+stale+unresolved are all
    coverage holes the operator must act on, separated only so the *reason* is legible.
    """
    rules = rules or default_rules()
    source_fresh_known = _source_has_freshness(source_meta)
    primary_ambiguous = _self_colliding(primary_meta.keys(), rules, min_confidence)
    source_ambiguous = _self_colliding(source_meta.keys(), rules, min_confidence)
    source_ids = list(source_meta.keys())

    covered = stale = gap = unresolved = 0
    confidence_sum = 0.0
    for p in primary_meta:
        if p in primary_ambiguous:
            unresolved += 1
            continue
        matches = [(s, match_confidence(p, s, rules)) for s in source_ids]
        matches = [(s, c) for (s, c) in matches if c >= min_confidence]
        if not matches:
            gap += 1
            continue
        if len(matches) > 1 or any(s in source_ambiguous for s, _ in matches):
            unresolved += 1  # one primary id maps to multiple / ambiguous source entities
            continue
        s, conf = matches[0]
        if source_fresh_known:
            fresh = decay.effective_status("pass", source_meta[s], now_iso, ttl_seconds) == "pass"
            if not fresh:
                stale += 1
                continue
        covered += 1
        confidence_sum += conf

    return {
        "covered": covered, "gap": gap, "stale": stale, "unresolved": unresolved,
        "primary_count": len(primary_meta),
        "uncovered_total": gap + stale + unresolved,
        "mean_confidence": round(confidence_sum / covered, 4) if covered else None,
        "freshness": "measured" if source_fresh_known else "unmeasured",
    }


def cross_tool_gap_deep(primary, sources_meta, *, rules=None, now_iso,
                        min_confidence=DEFAULT_MIN_CONFIDENCE,
                        ttl_seconds=DEFAULT_TTL_SECONDS, tolerance=0):
    """Resolved cross-tool coverage from an authoritative `primary` to every other source.

    sources_meta: {name: {raw_id: last_seen_iso_or_None}}; a value of None for the whole
    source (not a dict) means it could not be read.

    status: unmeasured if the primary is unreadable or fewer than two sources are readable;
    fail if any source's uncovered_total (gap + stale + unresolved) exceeds `tolerance`;
    pass only when every source resolves fully within tolerance. A source whose freshness
    is unmeasured can still pass on confidence, but the per-source `freshness:"unmeasured"`
    flag travels with the result so the caller never reads it as a clean, fresh green.
    """
    rules = rules or default_rules()
    readable = {n: m for n, m in sources_meta.items() if isinstance(m, dict)}
    if primary not in readable or len(readable) < 2:
        return {
            "primary": primary, "status": "unmeasured", "tolerance": tolerance,
            "min_confidence": min_confidence, "per_source": [],
            "note": "deep resolution needs a readable primary + >=1 other readable source",
            "unreadable": [n for n, m in sources_meta.items() if not isinstance(m, dict)],
        }

    primary_meta = readable[primary]
    per_source = []
    for name, meta in readable.items():
        if name == primary:
            continue
        r = resolve_against(primary_meta, meta, rules=rules, now_iso=now_iso,
                            min_confidence=min_confidence, ttl_seconds=ttl_seconds)
        r["to"] = name
        r["over_tolerance"] = r["uncovered_total"] > tolerance
        per_source.append(r)

    any_unmeasured_freshness = any(s["freshness"] == "unmeasured" for s in per_source)
    status = "fail" if any(s["over_tolerance"] for s in per_source) else "pass"
    return {
        "primary": primary, "status": status, "tolerance": tolerance,
        "min_confidence": min_confidence, "per_source": per_source,
        "freshness_caveat": any_unmeasured_freshness,
        "note": "deterministic declared-rule resolution; ambiguous + stale matches counted as gaps, never merged",
        "unreadable": [n for n, m in sources_meta.items() if not isinstance(m, dict)],
    }


def extract_ids_with_freshness(table, id_column, ts_column=None) -> dict | None:
    """Scan an identity column (and optionally a last-seen timestamp column) to
    {raw_id: latest_iso_or_None}. Returns None if the id column is absent or the scan
    fails (the caller then reports unmeasured, never a pass). Only these one or two
    columns are read, and only membership/freshness counts are ever surfaced — raw values
    are not rendered.
    """
    try:
        names = [f.name for f in table.schema().fields]
        if id_column not in names:
            return None
        cols = (id_column,) + ((ts_column,) if ts_column and ts_column in names else ())
        arrow = table.scan(selected_fields=cols).to_arrow()
        ids = arrow.column(id_column).to_pylist()
        if ts_column and ts_column in names:
            tss = arrow.column(ts_column).to_pylist()
        else:
            tss = [None] * len(ids)
        out: dict = {}
        for rid, ts in zip(ids, tss):
            if rid is None:
                continue
            iso = ts.isoformat() if hasattr(ts, "isoformat") else (str(ts) if ts is not None else None)
            prev = out.get(rid)
            if prev is None or (iso is not None and iso > prev):
                out[rid] = iso
        return out
    except Exception:  # noqa: BLE001
        return None
