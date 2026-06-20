"""Analyze — log analysis over a loaded OCSF table (AGGREGATE OUTPUT ONLY).

This is the "Analyze" pane's logic. The console already loads a PyIceberg table
into a PyArrow Table for the Iceberg Metadata Inspector (`scan().to_arrow()`),
and that inspector deliberately renders FIELD POPULATION counts only — it never
returns or renders raw telemetry rows, because real security telemetry is a
prompt-injection and control-char surface (an attacker who controls a log line
controls a string that would otherwise land verbatim in the model's context).

This module keeps that same rule, made explicit: `analyze_table` computes counts
and aggregates over the Arrow table and returns ONLY:
  - integer counts (row_count, non_null / null tallies),
  - the grouping-KEY VALUES for low-cardinality categorical fields it knows are
    safe to surface (class_uid, activity_id — small enumerated OCSF integers),
  - top-N (value, count) pairs for a high-cardinality field (e.g. src_ip), which
    is an aggregate of N capped entries, not the row contents, and
  - a min/max time bound (two scalar timestamps) when a time field exists.

It NEVER returns a full record, a row object, or a free-text field's contents.
There is no code path here that copies an arbitrary cell value into the output
except (a) the low-cardinality categorical grouping keys named above and (b) the
capped top-N keys for the one configured high-cardinality field. Everything else
is a count.

Honesty floor (matches layer3_audit / ocsf_roundtrip): if a requested grouping
field is absent from the table, the corresponding view is skipped — the result is
partial and says nothing it didn't measure, rather than crashing or fabricating.

duckdb-over-arrow idiom (from lab/promote.py): register the Arrow table as a view
and GROUP BY in SQL. duckdb reads the Arrow table zero-copy; the GROUP BY only
ever emits the grouping key and its count, never the underlying rows.
"""
from __future__ import annotations

# Low-cardinality categorical OCSF fields whose grouping-key VALUES are safe to
# surface (small enumerated integers — class_uid, activity_id, status_id, etc.).
# These are codepoints from the OCSF schema, not attacker-controlled free text.
LOW_CARD_CATEGORICAL = ("class_uid", "activity_id")

# High-cardinality fields we will summarise as top-N (value, count) AGGREGATES
# only — never as full rows. src_ip is attacker-influenced, so it is bounded to
# the top-N most frequent values with their counts (an aggregate), and the
# values themselves are coerced to plain strings and length-bounded so a crafted
# address-shaped string can't smuggle control characters or a long payload.
HIGH_CARD_SOURCE_FIELDS = ("src_ip", "src_endpoint_ip", "src")

# Candidate time/timestamp fields, in preference order, for the min/max bound.
TIME_FIELDS = ("time", "timestamp", "event_time", "@timestamp", "time_dt")

# How many top sources to surface. A cap is what makes top-N an aggregate rather
# than a row dump.
TOP_N_SOURCES = 10

# Defensive bound on a surfaced grouping-key string (sources): drop anything
# absurdly long and strip control characters, so even a low-card/top-N value can
# never carry a control-char or oversized injection payload into the UI.
_MAX_KEY_LEN = 64


def _safe_key(value):
    """Coerce a surfaced grouping key to a short, control-char-free string.

    Used for the high-cardinality top-N source values only — the one place a
    field's own value reaches the output. Low-card categorical keys (class_uid,
    activity_id) are integers and pass through untouched.
    """
    if value is None:
        return None
    s = str(value)
    # Strip control chars (keep printable + space); telemetry-injection rule.
    s = "".join(ch for ch in s if ord(ch) >= 32)
    if len(s) > _MAX_KEY_LEN:
        s = s[:_MAX_KEY_LEN] + "…"
    return s


def _column_names(arrow_table):
    try:
        return set(arrow_table.column_names)
    except Exception:  # noqa: BLE001 - be honest about a non-Arrow input
        return set()


def _first_present(names, present):
    for n in names:
        if n in present:
            return n
    return None


def _group_counts(con, field):
    """COUNT(*) grouped by a single categorical field, as a {value: count} dict.

    Only the grouping key and its count leave SQL — never a row. NULLs are
    folded into a "<null>" bucket so the tally is complete.
    """
    rows = con.execute(
        f'SELECT "{field}" AS k, COUNT(*) AS n FROM t GROUP BY "{field}" ORDER BY n DESC'
    ).fetchall()
    out = {}
    for k, n in rows:
        out["<null>" if k is None else k] = int(n)
    return out


def _top_sources(con, field, top_n=TOP_N_SOURCES):
    """Top-N (value, count) for a high-cardinality source field — an aggregate.

    Capped at top_n; values are sanitised + length-bounded via _safe_key. NULLs
    are skipped (a NULL source isn't a useful top entry, and folding it in would
    just be noise here).
    """
    rows = con.execute(
        f'SELECT "{field}" AS k, COUNT(*) AS n FROM t '
        f'WHERE "{field}" IS NOT NULL GROUP BY "{field}" ORDER BY n DESC, k LIMIT {int(top_n)}'
    ).fetchall()
    return [(_safe_key(k), int(n)) for k, n in rows]


def _field_population(arrow_table, present):
    """Per-column non-null / null counts — the same field-population view the
    Iceberg Metadata Inspector renders. Counts only; no values."""
    out = []
    total = arrow_table.num_rows
    for name in arrow_table.column_names:
        try:
            nulls = arrow_table.column(name).null_count
        except Exception:  # noqa: BLE001
            continue
        out.append({"field": name, "non_null": total - nulls, "null": nulls})
    return out


def _time_span(con, field):
    """min/max of a time field — two scalar bounds, not rows."""
    lo, hi = con.execute(
        f'SELECT MIN("{field}") AS lo, MAX("{field}") AS hi FROM t'
    ).fetchone()
    return {"field": field, "min": lo, "max": hi}


def analyze_table(arrow_table) -> dict:
    """Aggregate-only analysis of a loaded OCSF PyArrow table.

    Returns a dict of counts and low-cardinality / capped-top-N aggregates:
      {
        "row_count": int,
        "field_population": [{"field", "non_null", "null"}, ...],
        "by_class":    {class_uid_value: count, ...},     # if class_uid present
        "by_activity": {activity_id_value: count, ...},   # if activity_id present
        "top_sources": [(src_value, count), ...]          # if a source field present, capped
        "top_sources_field": "src_ip",                    # which field that was
        "time_span": {"field", "min", "max"},             # if a time field present
        "skipped": [field, ...],                          # requested-but-absent views
      }

    Every value emitted is a count, a low-card categorical key, a capped top-N
    (value,count) pair, or a min/max time scalar. No full rows, record objects,
    or free-text field contents are ever returned. A missing field is recorded
    in "skipped" and its view omitted — partial and honest, never a crash.
    """
    present = _column_names(arrow_table)
    result: dict = {
        "row_count": int(getattr(arrow_table, "num_rows", 0) or 0),
        "field_population": _field_population(arrow_table, present),
        "skipped": [],
    }

    # Field population needs no SQL; the GROUP BY views do. Register the Arrow
    # table as a duckdb view (zero-copy) and aggregate in SQL (promote.py idiom).
    import duckdb

    con = duckdb.connect()
    try:
        con.register("t", arrow_table)

        # by_class — low-cardinality categorical, key values safe to surface.
        if "class_uid" in present:
            result["by_class"] = _group_counts(con, "class_uid")
        else:
            result["skipped"].append("class_uid")

        # by_activity — low-cardinality categorical, key values safe to surface.
        if "activity_id" in present:
            result["by_activity"] = _group_counts(con, "activity_id")
        else:
            result["skipped"].append("activity_id")

        # top_sources — high-cardinality, summarised as capped top-N aggregates only.
        src_field = _first_present(HIGH_CARD_SOURCE_FIELDS, present)
        if src_field:
            result["top_sources"] = _top_sources(con, src_field)
            result["top_sources_field"] = src_field
        else:
            result["skipped"].append("top_sources")

        # time_span — two scalar bounds from the first present time field.
        time_field = _first_present(TIME_FIELDS, present)
        if time_field:
            result["time_span"] = _time_span(con, time_field)
        else:
            result["skipped"].append("time_span")
    finally:
        con.close()

    return result


# --------------------------------------------------------------------------- #
# Panel builder — Analyze pane. Renders the aggregates as small tables / notes.
# `arrow_or_none` is the console's loaded PyArrow table (or None if the user
# hasn't loaded one in the Inspector yet).
# --------------------------------------------------------------------------- #
def analyze_panel(mo, ui, arrow_or_none):
    """Build the Analyze pane as a ui.panel.

    None -> a note telling the user to load a table in the Inspector first.
    Else -> small tables/notes for row count, by-class, by-activity, top sources,
    field population, with a caption stating counts-only / raw rows never shown.
    """
    header = ui.header(mo, "Analyze — log analysis")

    if arrow_or_none is None:
        return ui.panel(
            mo,
            header,
            ui.note(mo, "info", "No table loaded",
                    "Load an OCSF table in the Iceberg Metadata Inspector first, then this "
                    "pane will report aggregate counts over it."),
        )

    try:
        agg = analyze_table(arrow_or_none)
    except Exception as e:  # noqa: BLE001 - surface honestly, never bluff
        return ui.panel(
            mo, header,
            ui.note(mo, "warn", "Analysis failed",
                    f"Could not aggregate the loaded table: `{str(e)[:200]}`"),
        )

    import pandas as pd

    blocks = [
        header,
        mo.md(f"**{agg['row_count']:,} rows** analyzed — counts and aggregates only."),
    ]

    # by_class (low-card categorical keys + counts).
    if agg.get("by_class"):
        blocks.append(mo.md("##### Records by OCSF class (`class_uid`)"))
        blocks.append(mo.as_html(pd.DataFrame(
            [{"class_uid": k, "count": v} for k, v in agg["by_class"].items()])))

    # by_activity (low-card categorical keys + counts).
    if agg.get("by_activity"):
        blocks.append(mo.md("##### Records by activity (`activity_id`)"))
        blocks.append(mo.as_html(pd.DataFrame(
            [{"activity_id": k, "count": v} for k, v in agg["by_activity"].items()])))

    # top_sources (capped top-N (value, count) aggregates).
    if agg.get("top_sources"):
        _f = agg.get("top_sources_field", "source")
        blocks.append(mo.md(f"##### Top sources (`{_f}`, top {TOP_N_SOURCES} by volume)"))
        blocks.append(mo.as_html(pd.DataFrame(
            [{_f: v, "count": c} for v, c in agg["top_sources"]])))

    # time_span (two scalar bounds).
    if agg.get("time_span"):
        ts = agg["time_span"]
        blocks.append(mo.md(
            f"##### Time span (`{ts['field']}`)\n\n"
            f"`{ts['min']}` → `{ts['max']}`"))

    # field_population — the inspector's counts-only view.
    if agg.get("field_population"):
        blocks.append(mo.md("##### Field population — counts only"))
        blocks.append(mo.as_html(pd.DataFrame(agg["field_population"])))

    # Honest note about any requested-but-absent view.
    if agg.get("skipped"):
        blocks.append(ui.note(mo, "info", "Some views skipped (field absent)",
                              "Not present in this table: " + ", ".join(f"`{s}`" for s in agg["skipped"])))

    blocks.append(mo.md(
        "*Aggregate output only — individual records, raw rows, and free-text field "
        "values are never rendered. Real security telemetry is a prompt-injection and "
        "control-char surface, so this pane reports counts, low-cardinality grouping "
        "keys, and capped top-N (value, count) aggregates — nothing else.*"))

    return ui.panel(mo, *blocks)
