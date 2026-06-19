"""Layer 1 source-health audit — per-source completeness, freshness, conformance.

THESIS Layer 1, the trustworthy pillar: "failures surface before analysts notice them,"
and continuously, not at procurement time. This audits each source table (one per OCSF
class) in the deployed catalog and reports three signals per source:
  - freshness     — age of the source's latest snapshot vs a threshold
  - conformance   — schema readable + no NULLs in Iceberg-required fields
  - completeness  — current row count vs a captured baseline; PENDING until a baseline
                    sidecar exists (you cannot measure "dropped 30%" with nothing to
                    compare against)

Honest scope rides every result: this is a LAKE-SIDE RECEIPT, not sensor-side capture.
A source that never sent an event and a source whose events were dropped on the wire
upstream look identical downstream, because we only see what landed. Completeness-vs-
baseline catches a source that *fell off* relative to its own history; it cannot see a
source that was never wired. Freshness and conformance read from manifests (no row scan).
"""
from __future__ import annotations

import json
import math

import layer3_audit as l3

LAKE_SIDE_LABEL = "lake-side receipt, not sensor-side capture"

# A source whose row count drops below this fraction of its baseline fails completeness.
DEFAULT_COMPLETENESS_FLOOR = 0.9


def _live_rows(table):
    """Live row count for the current snapshot. Iceberg nets deletes into the snapshot
    summary's `total-records`, so this is correct on merge-on-read / copy-on-write tables
    where summing per-file `record_count` (pre-delete counts, plus delete files) would
    overstate the live rows and hide a real completeness drop."""
    snap = table.current_snapshot()
    if snap is None:
        return 0
    total = (snap.summary or {}).get("total-records")
    if total is not None:
        try:
            return int(total)
        except (TypeError, ValueError):
            pass
    # Fallback if the summary lacks total-records: sum record_count over DATA files only.
    files = table.inspect.files()
    if not files.num_rows or "record_count" not in files.column_names:
        return 0
    counts = files.column("record_count").to_pylist()
    contents = files.column("content").to_pylist() if "content" in files.column_names else None
    return int(sum(c for i, c in enumerate(counts)
                   if c and (contents is None or contents[i] == 0)))


def audit_source(name, table, *, now_ms, max_freshness_seconds=l3.DEFAULT_MAX_FRESHNESS_SECONDS,
                 baseline=None, expected_columns=None, completeness_floor=DEFAULT_COMPLETENESS_FLOOR) -> dict:
    """Health for one source table. Returns {name, status, rows, checks:[CheckResult],
    completeness:{status,...}}. status is pass | fail | unmeasured."""
    try:
        schema = table.schema()
        files_arrow = table.inspect.files()
        snap = table.current_snapshot()
    except Exception as e:  # noqa: BLE001 - an unreadable source is unmeasured, never a pass
        return {"name": name, "status": "unmeasured", "rows": None,
                "checks": [l3.CheckResult("source", "unmeasured", f"unreadable: {e}")], "completeness": None}

    rows = _live_rows(table)
    fresh = l3.check_freshness(snap.timestamp_ms if snap else None, now_ms, max_freshness_seconds)
    null_viol = l3._aggregate_required_null_violations(files_arrow, schema)
    conf = l3.check_schema_conformance(
        [f.name for f in schema.fields], [f.name for f in schema.fields if f.required],
        null_viol, expected_columns)

    # Completeness vs the captured baseline — PENDING until a nonzero baseline exists
    # (you cannot measure a drop from a source that was empty when baselined).
    if baseline is not None and baseline.get(name, 0) > 0:
        base = baseline[name]
        floor = math.ceil(base * completeness_floor)
        ok = rows >= floor
        comp = {"status": "pass" if ok else "fail", "rows": rows, "baseline": base,
                "floor": floor, "detail": f"{rows} rows vs baseline {base} (floor {floor})"}
    elif baseline is not None and name in baseline:  # baseline == 0
        comp = {"status": "pending", "rows": rows, "baseline": 0,
                "detail": f"{rows} rows; baseline was 0 (no nonzero history to compare)"}
    else:
        comp = {"status": "pending", "rows": rows, "baseline": None,
                "detail": f"{rows} rows; no baseline captured (completeness pending)"}

    # Aggregation is freshness-gated: a source is healthy only if it has a fresh live
    # snapshot AND nothing fails. A never-written source (freshness unmeasured, no
    # snapshot) is UNMEASURED, never a pass — the gate must not bluff a green on a
    # source with no data. unmeasured/unwired checks never create a pass on their own.
    measured = [fresh, conf]
    if any(c.status == "fail" for c in measured) or comp["status"] == "fail":
        status = "fail"
    elif fresh.status == "pass":
        status = "pass"
    else:
        status = "unmeasured"
    return {"name": name, "status": status, "rows": rows,
            "checks": measured, "completeness": comp}


def audit_sources(tables, *, now_ms, max_freshness_seconds=l3.DEFAULT_MAX_FRESHNESS_SECONDS,
                  baseline=None, expected_columns=None) -> dict:
    """Audit a set of source tables ({name: PyIceberg Table}). Aggregate Layer-1 status:
    fail if any source fails; pass if >=1 source measured and all pass; unmeasured if
    none are measurable."""
    results = [audit_source(n, t, now_ms=now_ms, max_freshness_seconds=max_freshness_seconds,
                            baseline=baseline, expected_columns=expected_columns)
               for n, t in tables.items()]
    measured = [r for r in results if r["status"] in ("pass", "fail")]
    if any(r["status"] == "fail" for r in measured):
        status = "fail"
    elif measured:
        status = "pass"
    else:
        status = "unmeasured"
    return {"sources": results, "status": status, "label": LAKE_SIDE_LABEL,
            "now_ms": now_ms, "pending_baseline": baseline is None}


def source_row_counts(tables) -> dict:
    """Live row counts per source — what a baseline capture persists (same measure the
    completeness check compares against)."""
    out = {}
    for name, table in tables.items():
        try:
            out[name] = _live_rows(table)
        except Exception:  # noqa: BLE001
            continue
    return out


def load_baseline(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def save_baseline(path, counts) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(counts, f, sort_keys=True, indent=2)
