"""Layer 4 cross-tool gap analysis — exact-match coverage deltas across tool inventories.

THESIS Layer 4 / OFFERING Service 4: "the cross-tool view is where assurance lives."
Given a set of tool inventory tables sharing an identity column (hostname / asset_id),
compute set-membership coverage gaps from a chosen authoritative source — assets the
primary tool knows about that another tool does not (e.g. CMDB-known hosts the EDR
isn't watching, or that the scanner never scanned). That delta is the named coverage
hole a SOC can act on.

HONEST SCOPE — exact-match only. This is set membership on an exact identity key, NOT
entity resolution: `web-01` in CMDB and `web-01.corp` in the EDR read as a gap here.
Authoritative-source-per-attribute with confidence and freshness scoring — the part
Service 4 actually sells — is real entity resolution and is deferred, not dressed up
as done. The result carries counts only; identities are never rendered (the telemetry-
injection rule applies — an asset id set is still data pulled from the lake).
"""
from __future__ import annotations


def extract_ids(table, id_column) -> set | None:
    """Scan a single identity column to a set of values. Returns None if the column is
    absent or the scan fails (the gap check then reports unmeasured, never a pass).
    Only the one column is read, and only its cardinality/membership is ever surfaced —
    the values themselves are not rendered."""
    try:
        if id_column not in [f.name for f in table.schema().fields]:
            return None
        arrow = table.scan(selected_fields=(id_column,)).to_arrow()
        return {v for v in arrow.column(id_column).to_pylist() if v is not None}
    except Exception:  # noqa: BLE001
        return None


def cross_tool_gap(primary, sources, *, tolerance=0) -> dict:
    """primary: name of the authoritative source. sources: {name: set_of_ids} (a value
    of None means that source could not be read). Returns coverage gaps from the primary
    to every other source.

    status: unmeasured if the primary is unreadable or fewer than two sources are
    readable; fail if any gap exceeds `tolerance`; pass otherwise.

    `tolerance`: the maximum number of primary ids allowed to be missing from any one
    other source before that gap counts as a fail (integer, default 0).
    """
    readable = {n: s for n, s in sources.items() if isinstance(s, set)}
    if primary not in readable or len(readable) < 2:
        return {"primary": primary, "status": "unmeasured", "tolerance": tolerance,
                "gaps": [], "note": "exact-match only; needs a readable primary + >=1 other source",
                "unreadable": [n for n, s in sources.items() if not isinstance(s, set)]}

    primary_ids = readable[primary]
    gaps = []
    for name, ids in readable.items():
        if name == primary:
            continue
        missing = primary_ids - ids
        gaps.append({"to": name, "gap_count": len(missing),
                     "primary_count": len(primary_ids), "to_count": len(ids),
                     "over_tolerance": len(missing) > tolerance})

    status = "fail" if any(g["over_tolerance"] for g in gaps) else "pass"
    return {"primary": primary, "status": status, "tolerance": tolerance, "gaps": gaps,
            "note": "exact-match set membership, not entity resolution (deferred)",
            "unreadable": [n for n, s in sources.items() if not isinstance(s, set)]}
