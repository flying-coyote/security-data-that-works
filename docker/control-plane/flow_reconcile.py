"""Flow reconciliation — count events hop-to-hop per OCSF class.

Cluster-5 / "flow-layer silent failures are the binding constraint" (BOOK-ALIGNMENT
diagnosis): Layer 2 observes the stack is reachable but never checks that events actually
make it from source to landed table without silent loss. This reconciles per-OCSF-class
counts across the pipeline hops (emitted -> ingested -> landed) and names any drop, so a
pipeline that quietly loses 0.2% of one class surfaces instead of hiding.

Pure logic over already-collected counts; the live collection (Vector metrics + per-class
table scans) is the caller's job, wired in control_plane like the other audits. Status
vocabulary matches CONTRACT.md: pass / fail / unmeasured.
"""
from __future__ import annotations

HOPS = ("emitted", "ingested", "landed")


def reconcile_class(ocsf_class, counts, *, tolerance_frac=0.0) -> dict:
    """counts: {hop: int|None} for one OCSF class. None at any hop = that hop unmeasured.
    Returns {class, status, hops, drop, drop_frac, note}. status: unmeasured if any hop is
    None or nothing was emitted; fail if landed falls below emitted by more than
    tolerance_frac of emitted; pass otherwise."""
    e, i, l = counts.get("emitted"), counts.get("ingested"), counts.get("landed")
    if e is None or i is None or l is None:
        return {"class": ocsf_class, "status": "unmeasured", "hops": counts,
                "drop": None, "drop_frac": None, "note": "a hop count is missing"}
    if e < 0 or i < 0 or l < 0:
        return {"class": ocsf_class, "status": "unmeasured", "hops": counts,
                "drop": None, "drop_frac": None, "note": "a hop count is negative - invalid input"}
    if e <= 0:
        return {"class": ocsf_class, "status": "unmeasured", "hops": counts,
                "drop": None, "drop_frac": None, "note": "nothing emitted — no baseline to reconcile"}
    drop = e - l
    drop_frac = drop / e
    status = "fail" if drop > e * tolerance_frac else "pass"
    return {"class": ocsf_class, "status": status, "hops": counts, "drop": drop,
            "drop_frac": round(drop_frac, 4),
            "note": (f"{e} emitted, {i} ingested, {l} landed — dropped {drop} ({drop_frac:.1%})"
                     if drop else f"{e} emitted, fully reconciled")}


def reconcile(by_class, *, tolerance_frac=0.0) -> dict:
    """by_class: {ocsf_class: {hop: int|None}}. Aggregate flow status across classes:
    fail if any measured class fails; pass if >=1 class measured and all pass; else
    unmeasured. Mirrors the Layer-1/3 aggregation rule."""
    rows = [reconcile_class(c, n, tolerance_frac=tolerance_frac) for c, n in (by_class or {}).items()]
    measured = [r for r in rows if r["status"] in ("pass", "fail")]
    if any(r["status"] == "fail" for r in measured):
        status = "fail"
    elif measured:
        status = "pass"
    else:
        status = "unmeasured"
    return {"status": status, "classes": rows,
            "worst_drop": max((r["drop_frac"] for r in rows if r["drop_frac"] is not None), default=None)}
