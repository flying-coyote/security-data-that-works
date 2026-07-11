"""Entity-pivot investigation (analyst-value, Phase G flagship): given ONE entity — an IP or a user —
profile its activity across every OCSF class present, as AGGREGATES ONLY.

This is the analyst's highest-frequency daily job (the book's six daily functions list "Pivot — follow a
single entity across every source" as done dozens of times a shift), and the one the open MOAR stack
uniquely earns: the same pivot in SPL/KQL is engine-locked, but one normalized OCSF query following an
entity across Authentication (3002) + Network Activity (4001) + Process Activity (1007) is the
cross-source correlation a unified schema makes portable.

THE INVARIANT (telemetry-injection rule, same as analyze.py / detections.py): a profile is an AGGREGATE.
It returns only integer counts (total, per-class, per-activity), a min/max time bound (first_seen /
last_seen for the entity), a distinct-counterpart COUNT, and a capped top-N of (counterpart_key, count)
pairs. A raw OCSF record, a free-text field value (cmd_line / url / message), or an unbounded id set
NEVER appears. The echoed entity selector and every surfaced counterpart key pass through
analyze._safe_key (printable-ASCII, backtick-stripped, HTML-escaped, length-bounded). The PIVOTABLE
allow-list bars pivoting on a free-text field — grouping/filtering to one would make each group a single
record and leak it as a key. Absent class/field -> that sub-view is skipped + reported, honest-degrade.

Two paths, one definition (detections.py discipline): scan_entity() runs pure-Python over landed OCSF
dicts (the proof + the stack-down preview); profile_entity() runs the duckdb-over-arrow GROUP BY over a
loaded PyArrow table (analyze.py pattern) for the panel; to_sql() emits the BOUND-parameter SQL the live
run-at-scale path uses over the Iceberg table. The proof asserts scan_entity and profile_entity agree on
the same data, so the pure preview and the SQL path can't drift.
"""
from __future__ import annotations

from collections import Counter

from analyze import _safe_key

# The entity types an analyst may pivot on, and the OCSF fields that carry each. Identifier-shaped /
# bounded fields only — NEVER a free-text field (cmd_line / url / message), which would surface a
# record's raw value as the pivot key. `match`: the fields the entity can appear in (matched in ANY
# role). `peers`: (match_field, peer_field) rules — "in rows where match_field == the entity, the
# counterpart is peer_field" — so for an IP the peer is the opposite-role IP, for a user it's the
# source they authenticated from. A peer rule applies only when both fields are present in the data.
PIVOTABLE = {
    "ip": {
        "label": "IP address",
        "match": ("src_ip", "dst_ip", "src_endpoint_ip"),
        "peers": (("src_ip", "dst_ip"), ("dst_ip", "src_ip")),
    },
    "user": {
        "label": "User",
        "match": ("user", "actor_user", "user_name"),
        "peers": (("user", "src_ip"),),
    },
}

# Candidate time fields, in preference order, for the first_seen / last_seen bound.
TIME_FIELDS = ("time", "timestamp", "event_time", "@timestamp", "time_dt")

# Display names for the OCSF classes the console's routers produce (low-card schema codepoints).
CLASS_NAMES = {1007: "Process Activity", 3002: "Authentication", 4001: "Network Activity",
               6001: "File System Activity", 6003: "API Activity"}

TOP_N_COUNTERPARTS = 10


def class_label(class_uid):
    """A readable 'Name (uid)' for a class_uid, or just the uid if unknown — display only."""
    try:
        u = int(class_uid)
    except (TypeError, ValueError):
        return str(class_uid)
    return f"{CLASS_NAMES[u]} ({u})" if u in CLASS_NAMES else str(u)


def pivotable_types():
    """The entity types an analyst can pivot on (for the picker)."""
    return {k: v["label"] for k, v in PIVOTABLE.items()}


def _present_keys(records):
    keys = set()
    for r in records:
        if isinstance(r, dict):
            keys.update(r.keys())
    return keys


def scan_entity(records, entity_type, value, *, top_n=TOP_N_COUNTERPARTS):
    """Pure-Python reference profile of ONE entity over a list of landed OCSF dicts. Aggregates only —
    counts, a time bound, a distinct-counterpart count, and a capped top-N of counterparts. The
    reference implementation profile_entity() is proven to agree with this."""
    if entity_type not in PIVOTABLE:
        raise ValueError(f"unknown entity type {entity_type!r}; pivotable: {sorted(PIVOTABLE)}")
    spec = PIVOTABLE[entity_type]
    recs = [r for r in records if isinstance(r, dict)]
    present = _present_keys(recs)
    match_fields = [f for f in spec["match"] if f in present]
    skipped = []

    hits = [r for r in recs if any(r.get(f) == value for f in match_fields)]
    by_class = _count_keys(r.get("class_uid") for r in hits)
    by_activity = _count_keys(r.get("activity_id") for r in hits)

    tfield = next((f for f in TIME_FIELDS if f in present), None)
    if tfield:
        times = [r.get(tfield) for r in hits if r.get(tfield) is not None]
        time_span = {"field": tfield, "min": min(times), "max": max(times)} if times else None
    else:
        time_span = None
        skipped.append("time_span")

    peer_counts = Counter()
    peer_rules = [(mf, pf) for mf, pf in spec["peers"] if mf in present and pf in present]
    if peer_rules:
        for r in recs:
            for mf, pf in peer_rules:
                if r.get(mf) == value:
                    peer = r.get(pf)
                    if peer is not None and peer != value:
                        peer_counts[peer] += 1
    else:
        skipped.append("counterparts")

    return _assemble(entity_type, spec, value, match_fields, len(hits), by_class, by_activity,
                     time_span, peer_counts, top_n, skipped)


def profile_entity(arrow_table, entity_type, value, *, top_n=TOP_N_COUNTERPARTS):
    """Duckdb-over-arrow profile of ONE entity over a loaded OCSF PyArrow table (the panel path).
    Same aggregates as scan_entity, computed in SQL so only the grouping key + count ever leave the
    query — never a row. The entity value is passed as a BOUND parameter, not interpolated."""
    if entity_type not in PIVOTABLE:
        raise ValueError(f"unknown entity type {entity_type!r}; pivotable: {sorted(PIVOTABLE)}")
    import duckdb

    spec = PIVOTABLE[entity_type]
    try:
        present = set(arrow_table.column_names)
    except Exception:  # noqa: BLE001 - honest about a non-Arrow input
        present = set()
    match_fields = [f for f in spec["match"] if f in present]
    skipped = []

    con = duckdb.connect()
    try:
        con.register("t", arrow_table)
        if not match_fields:
            # the entity can't appear in this table — honest empty profile, nothing fabricated.
            return _assemble(entity_type, spec, value, [], 0, {}, {}, None, Counter(), top_n,
                             ["time_span", "counterparts"])

        where = " OR ".join(f'"{f}" = ?' for f in match_fields)
        wp = [value] * len(match_fields)
        total = con.execute(f"SELECT count(*) FROM t WHERE {where}", wp).fetchone()[0]
        by_class = _sql_group(con, "class_uid", where, wp, present)
        by_activity = _sql_group(con, "activity_id", where, wp, present)

        tfield = next((f for f in TIME_FIELDS if f in present), None)
        if tfield:
            lo, hi = con.execute(f'SELECT min("{tfield}"), max("{tfield}") FROM t WHERE {where}', wp).fetchone()
            time_span = {"field": tfield, "min": lo, "max": hi} if lo is not None else None
        else:
            time_span = None
            skipped.append("time_span")

        peer_rules = [(mf, pf) for mf, pf in spec["peers"] if mf in present and pf in present]
        peer_counts = Counter()
        if peer_rules:
            selects, params = [], []
            for mf, pf in peer_rules:
                selects.append(f'SELECT "{pf}" AS peer, count(*) AS n FROM t '
                               f'WHERE "{mf}" = ? AND "{pf}" IS NOT NULL AND "{pf}" <> ? GROUP BY "{pf}"')
                params += [value, value]
            union = " UNION ALL ".join(selects)
            rows = con.execute(f"SELECT peer, sum(n) AS n FROM ({union}) GROUP BY peer", params).fetchall()
            for k, n in rows:
                peer_counts[k] = int(n)
        else:
            skipped.append("counterparts")

        return _assemble(entity_type, spec, value, match_fields, int(total), by_class, by_activity,
                         time_span, peer_counts, top_n, skipped)
    finally:
        con.close()


def to_sql(entity_type, value, table, present_fields=None):
    """The live run-at-scale path: the filtered per-class aggregate SQL over the Iceberg `table`.
    Returns (sql, params). The entity value — the ONE user-supplied input in the console — is emitted
    as BOUND '?' placeholders, never interpolated into the SQL string, so it is neither a SQL-injection
    surface nor a way to smuggle a raw value into the query text. The result cells (class_uid, count)
    are low-card + numeric; the caller still routes any surfaced key through analyze._safe_key."""
    if entity_type not in PIVOTABLE:
        raise ValueError(f"unknown entity type {entity_type!r}")
    spec = PIVOTABLE[entity_type]
    fields = [f for f in spec["match"] if (present_fields is None or f in present_fields)]
    if not fields:
        fields = list(spec["match"])
    where = " OR ".join(f"{f} = ?" for f in fields)
    sql = (f"SELECT class_uid, count(*) AS n FROM {table} WHERE {where} "
           f"GROUP BY class_uid ORDER BY n DESC")
    return sql, [value] * len(fields)


# --------------------------------------------------------------------------- #
# demo data for the preview / flip-through (synthetic OCSF; the live path profiles the landed tables)
# --------------------------------------------------------------------------- #
def demo_records():
    """A synthetic OCSF sample for the pivot preview. Built so one entity (10.0.1.50 / jsmith) appears
    across BOTH Network Activity (4001) and Authentication (3002) — the cross-source story the pivot
    tells — alongside a network scanner and an auth-spray source so the picker shows distinct shapes."""
    recs = []
    # 10.0.1.50 — a workstation: network flows to a few destinations + a failed-auth burst by jsmith.
    for i, d in enumerate(["10.0.2.10", "10.0.2.10", "10.0.2.10", "203.0.113.7", "203.0.113.7",
                           "8.8.8.8", "10.0.2.99", "10.0.2.10"]):
        recs.append({"class_uid": 4001, "category_uid": 4, "activity_id": 6, "src_ip": "10.0.1.50",
                     "dst_ip": d, "dst_port": 443, "bytes_in": 1200, "bytes_out": 300,
                     "time": f"2026-06-21T12:{i:02d}:00Z"})
    for i in range(3):
        recs.append({"class_uid": 3002, "category_uid": 3, "activity_id": 1, "status_id": 2,
                     "src_ip": "10.0.1.50", "user": "jsmith@acme.example", "time": f"2026-06-21T12:3{i}:00Z"})
    # 198.51.100.23 — an external scanner hitting many internal hosts on 22.
    for i in range(6):
        recs.append({"class_uid": 4001, "category_uid": 4, "activity_id": 6, "src_ip": "198.51.100.23",
                     "dst_ip": f"10.0.3.{i}", "dst_port": 22, "bytes_in": 40, "bytes_out": 40,
                     "time": f"2026-06-21T11:0{i}:00Z"})
    # 203.0.113.99 — an auth-spray source across distinct users.
    for i in range(5):
        recs.append({"class_uid": 3002, "category_uid": 3, "activity_id": 1, "status_id": 2,
                     "src_ip": "203.0.113.99", "user": f"user{i}@acme.example", "time": f"2026-06-21T10:0{i}:00Z"})
    return recs


def demo_entities():
    """Suggested (entity_type, value, label) pivots present in demo_records() — for the picker, so the
    preview/flip-through self-demonstrates a real profile."""
    return [
        ("ip", "10.0.1.50", "IP 10.0.1.50 — workstation (network + auth)"),
        ("user", "jsmith@acme.example", "User jsmith@acme.example"),
        ("ip", "198.51.100.23", "IP 198.51.100.23 — external scanner"),
        ("ip", "203.0.113.99", "IP 203.0.113.99 — auth-spray source"),
    ]


# --------------------------------------------------------------------------- #
# internals
# --------------------------------------------------------------------------- #
def _count_keys(values):
    """Counter over non-null values — low-card categorical keys (class_uid / activity_id)."""
    c = Counter()
    for v in values:
        if v is not None:
            c[v] += 1
    return c


def _sql_group(con, field, where, params, present):
    if field not in present:
        return {}
    rows = con.execute(
        f'SELECT "{field}" AS k, count(*) AS n FROM t WHERE {where} GROUP BY "{field}" ORDER BY n DESC',
        params).fetchall()
    return {("<null>" if k is None else k): int(n) for k, n in rows}


def _assemble(entity_type, spec, value, match_fields, total, by_class, by_activity,
              time_span, peer_counts, top_n, skipped):
    counterparts = [(_safe_key(k), int(n)) for k, n in peer_counts.most_common(top_n)]
    return {
        "entity_type": entity_type,
        "label": spec["label"],
        "value": _safe_key(value),                 # echoed selector — sanitized
        "matched_fields": list(match_fields),       # provenance: which fields carried the entity
        "total_events": int(total),
        "by_class": {(k if isinstance(k, str) else int(k)): int(v) for k, v in by_class.items()},
        "by_activity": {(k if isinstance(k, str) else int(k)): int(v) for k, v in by_activity.items()},
        "time_span": time_span,                     # {field, min, max} first_seen/last_seen, or None
        "counterparts": counterparts,               # capped top-N (safe_key, count)
        "distinct_counterparts": len(peer_counts),
        "skipped": skipped,
    }


def entity_pivot_panel(mo, ui, profile, *, source_note=""):
    """Render one entity's cross-class profile as aggregate count tables — never a raw row."""
    header = ui.header(mo, "Entity pivot — investigate one indicator across every OCSF class")
    if profile is None:
        return ui.panel(mo, header, ui.note(mo, "info", "Pick an entity",
                        "Choose an entity type and value to profile its activity across all OCSF classes."))

    if not profile.get("matched_fields") or profile.get("total_events", 0) == 0:
        return ui.panel(mo, header, ui.note(mo, "info", "No activity for this entity",
                        f"`{profile.get('value', '')}` ({profile.get('label', '')}) does not appear in the "
                        "loaded data, or its field isn't present. " + source_note))

    blocks = [header,
              mo.md(f"### {profile['label']} `{profile['value']}`\n"
                    f"**{profile['total_events']:,} event(s)** across **{len(profile['by_class'])} OCSF "
                    f"class(es)** — matched in {', '.join('`' + f + '`' for f in profile['matched_fields'])}.")]

    if profile.get("time_span"):
        ts = profile["time_span"]
        blocks.append(mo.md(f"**First seen → last seen** (`{ts['field']}`): `{ts['min']}` → `{ts['max']}`"))

    if profile.get("by_class"):
        rows = "\n".join(f"| {class_label(k)} | {v} |" for k, v in sorted(profile["by_class"].items(),
                                                                          key=lambda kv: -kv[1]))
        blocks.append(mo.md("##### Activity by OCSF class\n\n| Class | Events |\n|---|---|\n" + rows))

    if profile.get("by_activity"):
        rows = "\n".join(f"| {k} | {v} |" for k, v in sorted(profile["by_activity"].items(),
                                                             key=lambda kv: -kv[1]))
        blocks.append(mo.md("##### Activity by `activity_id`\n\n| activity_id | Events |\n|---|---|\n" + rows))

    if profile.get("counterparts"):
        rows = "\n".join(f"| `{k}` | {n} |" for k, n in profile["counterparts"])
        blocks.append(mo.md(
            f"##### Top counterparts (of {profile['distinct_counterparts']} distinct, top "
            f"{len(profile['counterparts'])})\n\n| Counterpart | Shared events |\n|---|---|\n" + rows))

    if profile.get("skipped"):
        blocks.append(ui.note(mo, "info", "Some views skipped (field absent)",
                              "Not derivable from this data: " + ", ".join(f"`{s}`" for s in profile["skipped"])))

    blocks.append(mo.md(
        "*Aggregate output only — counts, low-cardinality OCSF keys, a time bound, and capped top-N "
        "counterparts. No raw record, free-text value, or unbounded id set is ever rendered. The same "
        "pivot runs unchanged over OCSF in standard SQL across ClickHouse / Trino / StarRocks — the hunt "
        "travels with the schema, not the vendor.* " + source_note))

    return ui.panel(mo, *blocks)
