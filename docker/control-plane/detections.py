"""Detections over landed OCSF — the SOC "found something" moment, aggregate-safe.

Each detection is a DECLARATIVE spec (predicate + group + measures + having + rank) so the same
definition runs two ways: `scan()` executes it in pure Python over landed records (for the proof and
the Analyze preview, no stack), and `to_sql()` emits the GROUP BY/HAVING SQL the live run_detections.py
runs over the Iceberg table at scale. The spec carries the *aggregation* Sigma can't express; a Sigma
rule alongside carries only the predicate.

THE INVARIANT (telemetry-injection rule): a finding is an AGGREGATE — the grouping key (src_ip/dst_ip,
which are attacker-influenced, so bounded + control-char-stripped via analyze._safe_key) plus numeric
measures (counts/sums). A raw record, a free-text field value, or an unbounded high-cardinality value
NEVER appears in the output. `scan()` cannot emit a record: it only ever returns (safe_key, {measure:
number}).
"""
from __future__ import annotations

import operator

from analyze import _safe_key

_OPS = {"=": operator.eq, "!=": operator.ne, ">": operator.gt, ">=": operator.ge,
        "<": operator.lt, "<=": operator.le}

# Declarative detection specs. where/having: lists of (field|measure, op, value). group: fields to
# aggregate by. measures: name -> (agg, field) with agg in {count, sum, avg}. rank: the measure to sort by.
DETECTIONS = [
    {
        "id": "c2_beacon",
        "title": "C2 beacon — low-byte repeated outbound to a rare destination",
        "technique": "T1071", "table": "network_activity",
        "where": [("class_uid", "=", 4001)],
        "group": ("src_ip", "dst_ip"),
        "measures": {"connections": ("count", None), "avg_bytes_out": ("avg", "bytes_out")},
        "having": [("connections", ">=", 3), ("avg_bytes_out", "<", 256)],
        "rank": "connections",
        "why": "Many small, regular outbound connections to one destination — the shape of a beaconing implant "
               "checking in. Small bytes_out is the corrected egress direction (orig_bytes).",
    },
    {
        "id": "exfil_egress",
        "title": "Data exfiltration — high outbound volume by source",
        "technique": "T1048", "table": "network_activity",
        "where": [("class_uid", "=", 4001)],
        "group": ("src_ip",),
        "measures": {"total_bytes_out": ("sum", "bytes_out"), "flows": ("count", None)},
        "having": [("total_bytes_out", ">=", 10000)],
        "rank": "total_bytes_out",
        "why": "A source sending an unusually large total volume outbound (bytes_out = what src_endpoint sent).",
    },
]


def _match(r, where):
    return all(op in _OPS and _OPS[op](r.get(f), v) for f, op, v in where)


def _measure(agg, field, group_rows):
    if agg == "count":
        return len(group_rows)
    vals = [g.get(field) for g in group_rows if isinstance(g.get(field), (int, float))]
    if agg == "sum":
        return sum(vals)
    if agg == "avg":
        return round(sum(vals) / len(vals), 1) if vals else 0
    return 0


def scan(records, detections=None, *, top_n=10):
    """Run every detection over `records` (a list of landed OCSF dicts) and return aggregate-safe
    findings: [{id, title, technique, table, match_count, top: [(safe_key, {measure: number})]}].
    The grouping key is bounded via analyze._safe_key; the only other output is numeric measures."""
    out = []
    for d in (detections or DETECTIONS):
        hits = [r for r in records if isinstance(r, dict) and _match(r, d["where"])]
        groups = {}
        for r in hits:
            groups.setdefault(tuple(r.get(g) for g in d["group"]), []).append(r)
        findings = []
        for key, grp in groups.items():
            m = {name: _measure(agg, field, grp) for name, (agg, field) in d["measures"].items()}
            if all(op in _OPS and _OPS[op](m.get(meas), v) for meas, op, v in d["having"]):
                safe_key = " → ".join(_safe_key(k) for k in key)   # bounded; never a raw value
                findings.append((safe_key, m))
        findings.sort(key=lambda f: -(f[1].get(d["rank"], 0) or 0))
        out.append({"id": d["id"], "title": d["title"], "technique": d["technique"], "table": d["table"],
                    "match_count": len(findings),
                    "top": [(k, {mk: m[mk] for mk in d["measures"]}) for k, m in findings[:top_n]]})
    return out


_AGG_SQL = {"count": "count(*)", "sum": "sum({field})", "avg": "avg({field})"}


def to_sql(detection, table):
    """Emit the GROUP BY/HAVING SQL for the live path (run_detections.py over the Iceberg table).
    Same spec as scan(), so the live query and the pure preview can't drift."""
    d = detection
    where = " AND ".join(f"{f} {op} {v!r}" if isinstance(v, str) else f"{f} {op} {v}"
                         for f, op, v in d["where"])
    group = ", ".join(d["group"])
    meas = ", ".join(f"{_AGG_SQL[agg].format(field=field)} AS {name}"
                     for name, (agg, field) in d["measures"].items())
    having = " AND ".join(f"{meas} {op} {v}" for meas, op, v in d["having"])
    return (f"SELECT {group}, {meas} FROM {table} WHERE {where} "
            f"GROUP BY {group} HAVING {having} ORDER BY {d['rank']} DESC LIMIT 20")


def demo_records(samples_dir=None):
    """Landed-OCSF records for the Analyze detection preview: the Zeek 4001 gold sample + a planted
    high-egress source, so the worked detections fire over a known distribution. The live version runs
    run_detections.py over the real landed ocsf.network_activity table."""
    import json
    import os
    sd = samples_dir or os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                      "..", "config", "samples"))
    try:
        recs = [json.loads(line) for line in open(os.path.join(sd, "zeek_conn.ocsf.expected.ndjson"))
                if line.strip()]
    except Exception:  # noqa: BLE001 - the preview degrades to the planted rows only
        recs = []
    recs += [{"class_uid": 4001, "activity_id": 6, "src_ip": "10.0.1.200", "dst_ip": "198.51.100.9",
              "dst_port": 443, "bytes_in": 100, "bytes_out": 5000} for _ in range(3)]
    return recs


def detections_panel(mo, ui, findings, *, source_note=""):
    """Render the detection findings as an aggregate-safe scorecard (counts + bounded keys only)."""
    blocks = []
    for f in findings:
        fired = f["match_count"] > 0
        head = f"{'🔴' if fired else '🟢'} **{f['title']}** &nbsp;·&nbsp; `{f['technique']}` &nbsp;·&nbsp; {f['match_count']} finding(s)"
        rows = []
        for key, m in f["top"]:
            meas = " · ".join(f"{mk.replace('_', ' ')} {mv}" for mk, mv in m.items())
            rows.append(f"&nbsp;&nbsp;`{key}` — {meas}")
        blocks.append(ui.note(mo, "warn" if fired else "info", "",
                              head + ("<br/>" + "<br/>".join(rows) if rows else "")))
    return ui.panel(mo,
        ui.header(mo, "Detections — hunts over the landed OCSF (aggregate-safe)"),
        mo.md("Worked detections run over the landed OCSF table. Each result is an **aggregate** — a "
              "bounded grouping key plus counts — never a raw event row (real telemetry is a "
              "prompt-injection surface). " + source_note),
        *blocks,
    )
