"""Land — pipeline topology — the selected stack drawn as a data path.

The component panel answers "what did I pick"; it doesn't answer "where does an
event go." This renders the selection as a sources -> route -> land -> query ->
present node-edge graph so the operator reads the actual path the data takes
through the stack, not just an unordered component list. The tiers match how the
book talks about the pipeline:

  Source(s)  — where telemetry originates (a fixed entry node; the console does
               not yet model named sources, so this is a single passthrough).
  Route      — the ingest engine(s), R-tier; OCSF-normalizes via the schema pick.
  Lakehouse  — storage + open table format, L-tier; brokered by the Catalog.
  Catalog    — the Iceberg REST catalog, I-tier; the broker that makes the land
               readable and the engines interchangeable.
  Engine(s)  — the query engine(s), E-tier, reading the shared catalog.
  Present    — Graph / UX, a passthrough sink so the path terminates somewhere.

Honesty rule, matching the data-health gate and flow_reconcile's vocabulary: a
node or edge with no live telemetry is "unmeasured" ("—"), never a fabricated
"up" or a made-up throughput. Throughput strings only appear when a real
`live_status` carries them. `build_topology` is pure (no marimo); the panel
builder receives `mo` and `ui` from the calling cell, like the other modules.
"""
from __future__ import annotations

import providers as P

# Live-status vocabulary. "selected" is the design-time default (the node is in
# the chosen stack but carries no live signal yet); the live overrides mirror the
# pass/fail/unmeasured spirit of CONTRACT.md, mapped onto a node's reachability.
STATUS_SELECTED = "selected"
STATUS_UP = "up"
STATUS_DOWN = "down"
STATUS_UNMEASURED = "unmeasured"
_LIVE_STATUSES = (STATUS_UP, STATUS_DOWN, STATUS_UNMEASURED)

# Glyphs for the legend / per-node badge. A node with no live signal reads as the
# em-dash, never a faked green.
_STATUS_GLYPH = {
    STATUS_SELECTED: "•",
    STATUS_UP: "✓",
    STATUS_DOWN: "✗",
    STATUS_UNMEASURED: "—",
}

# Fixed passthrough endpoints. These are not user-selected components; they bound
# the path so it always has a start and an end even on a partial selection.
_SOURCE_ID = "source"
_PRESENT_ID = "present"


def _mermaid_label(text) -> str:
    """Sanitize a label for a mermaid node body.

    Mermaid node text inside [] chokes on quotes/brackets/newlines, so collapse
    them. Labels here come from providers.label_for (a closed catalog), so this is
    defensive rather than load-bearing, but a stray catalog edit shouldn't produce
    an unparseable graph."""
    s = str(text)
    # Strip every bracket/brace/paren and the pipe: mermaid treats them as syntax, and an
    # unquoted edge label like `Iceberg read (via catalog)` or a node `Polaris (catalog)`
    # breaks the parser. Labels come from a closed catalog, so dropping them reads fine.
    for bad, repl in (("\n", " "), ('"', "'"), ("|", "/"),
                      ("[", ""), ("]", ""), ("{", ""), ("}", ""), ("(", ""), (")", "")):
        s = s.replace(bad, repl)
    return s.strip() or "?"


def _status_for(node_id, live_status) -> str:
    """Resolve a node's status: a live override if present and valid, else the
    design-time default. A node the live map doesn't mention is "selected" (it's in
    the stack), and an out-of-vocabulary live value degrades to "unmeasured" rather
    than being trusted — we never invent an "up"."""
    if not live_status:
        return STATUS_SELECTED
    raw = live_status.get(node_id)
    if raw is None:
        return STATUS_SELECTED
    return raw if raw in _LIVE_STATUSES else STATUS_UNMEASURED


def _throughput_for(node_id, live_status):
    """A real throughput string for a node, only if a live signal carries one.

    Accepts either {node_id: "up"} (no throughput) or
    {node_id: {"status": "up", "throughput": "12k ev/s"}} (carries one). Never
    fabricates a number — absence returns None and the node shows no rate."""
    if not live_status:
        return None
    raw = live_status.get(node_id)
    if isinstance(raw, dict):
        tp = raw.get("throughput")
        return str(tp) if tp not in (None, "") else None
    return None


def _norm_status(raw):
    """Normalize a live entry (string or {"status": ...} dict) to a status string."""
    if isinstance(raw, dict):
        raw = raw.get("status")
    return raw if raw in _LIVE_STATUSES else STATUS_UNMEASURED


def build_topology(selection, live_status=None) -> dict:
    """Build the source -> route -> land -> query -> present graph for `selection`.

    selection: {"storage": code, "catalog": code, "ingest": [codes],
                "query": [codes], "schema": code} — the same shape control_plane
                uses (a missing/empty key just drops that tier's nodes).
    live_status: optional {node_id: "up"|"down"|"unmeasured"} OR
                 {node_id: {"status": ..., "throughput": ...}} to override the
                 design-time "selected" default. A node absent from the map stays
                 "selected"; an unknown value degrades to "unmeasured".

    Returns {"nodes": [...], "edges": [...], "mermaid": str}. Each node is
    {id, label, tier, status}; each edge is {from, to, label}. An empty selection
    still yields the source/present endpoints (degrades cleanly, never raises)."""
    selection = selection or {}
    storage = selection.get("storage")
    catalog = selection.get("catalog")
    schema = selection.get("schema")
    ingest = [c for c in (selection.get("ingest") or []) if c]
    query = [c for c in (selection.get("query") or []) if c]

    # Resolve the live map up front so the same entry drives status + throughput.
    live = live_status or {}

    def _live(node_id):
        return _norm_status(live[node_id]) if node_id in live else STATUS_SELECTED

    nodes: list[dict] = []
    edges: list[dict] = []

    def add_node(node_id, label, tier):
        nodes.append({
            "id": node_id,
            "label": label,
            "tier": tier,
            "status": _live(node_id),
        })

    # --- Source: a fixed entry node (no named-source model yet). ----------------
    add_node(_SOURCE_ID, "Source(s)", "source")

    # --- Route: the ingest engine(s), R-tier; OCSF-normalize via the schema. ----
    schema_label = P.label_for(P.SCHEMA, schema) if schema else None
    route_ids: list[str] = []
    for code in ingest:
        nid = f"route_{code}"
        route_ids.append(nid)
        label = P.label_for(P.INGEST, code)
        if schema_label:
            label = f"{label} → {schema_label}"
        add_node(nid, label, "route")
        edges.append({"from": _SOURCE_ID, "to": nid, "label": "raw events"})

    # --- Lakehouse: storage + format, L-tier; the land the route writes into. ---
    land_id = None
    if storage:
        land_id = f"land_{storage}"
        add_node(land_id, f"{P.label_for(P.STORAGE, storage)} + Iceberg", "land")
        # Route -> land. If there's no route, the source still hands off to the
        # land so the path isn't broken (the anti-pattern guard separately flags a
        # missing ingest pipeline).
        upstreams = route_ids or [_SOURCE_ID]
        for up in upstreams:
            edges.append({"from": up, "to": land_id, "label": "normalized OCSF"})

    # --- Catalog: I-tier broker that makes the land readable + engines swappable.
    catalog_id = None
    if catalog:
        catalog_id = f"catalog_{catalog}"
        add_node(catalog_id, f"{P.label_for(P.CATALOG, catalog)} (catalog)", "catalog")
        if land_id:
            edges.append({"from": land_id, "to": catalog_id, "label": "registers tables"})

    # --- Engine(s): the query engine(s), E-tier, reading the shared catalog. -----
    # Engines read THROUGH the catalog when one is selected (the broker is the
    # whole point); without a catalog they read the land directly.
    engine_source = catalog_id or land_id or _SOURCE_ID
    edge_label = "Iceberg read (via catalog)" if catalog_id else "table read"
    engine_ids: list[str] = []
    for code in query:
        nid = f"engine_{code}"
        engine_ids.append(nid)
        add_node(nid, P.label_for(P.QUERY, code), "query")
        edges.append({"from": engine_source, "to": nid, "label": edge_label})

    # --- Present: a fixed sink so the path always terminates. -------------------
    add_node(_PRESENT_ID, "Graph / UX", "present")
    present_upstreams = engine_ids or ([engine_source] if engine_source != _SOURCE_ID else [])
    for up in present_upstreams:
        edges.append({"from": up, "to": _PRESENT_ID, "label": "results"})

    mermaid = _build_mermaid(nodes, edges, live)
    return {"nodes": nodes, "edges": edges, "mermaid": mermaid}


# Per-tier mermaid class styling (fill follows the tier; the status badge carries
# liveness so the colour doesn't double as a fake "up").
_TIER_CLASS = {
    "source": "fill:#e8eef5,stroke:#6b7a8f",
    "route": "fill:#eaf3ea,stroke:#5a7a5a",
    "land": "fill:#fdf3e3,stroke:#b08642",
    "catalog": "fill:#f0eaf6,stroke:#7a5a9a",
    "query": "fill:#eaf0f6,stroke:#3f6098",
    "present": "fill:#f2f2f2,stroke:#888888",
}


def _build_mermaid(nodes, edges, live) -> str:
    """Render the nodes/edges as a `graph TD` mermaid string.

    The status glyph is baked into each node label so the diagram alone shows
    liveness (— for a node with no live signal), and a real throughput from
    `live` is appended only when present."""
    lines = ["graph TD"]
    for n in nodes:
        glyph = _STATUS_GLYPH.get(n["status"], _STATUS_GLYPH[STATUS_UNMEASURED])
        tp = _throughput_for(n["id"], live)
        body = _mermaid_label(n["label"])
        suffix = f"<br/>{glyph}"
        if tp:
            suffix += f" {_mermaid_label(tp)}"
        lines.append(f'    {n["id"]}["{body}{suffix}"]')
    for e in edges:
        lbl = _mermaid_label(e.get("label") or "")
        if lbl:
            lines.append(f'    {e["from"]} -->|{lbl}| {e["to"]}')
        else:
            lines.append(f'    {e["from"]} --> {e["to"]}')
    # Tier styling via classDef + class, grouped so the diagram reads by tier.
    for tier, style in _TIER_CLASS.items():
        ids = [n["id"] for n in nodes if n["tier"] == tier]
        if ids:
            lines.append(f"    classDef {tier} {style};")
            lines.append(f"    class {','.join(ids)} {tier};")
    return "\n".join(lines)


def _legend_md(nodes, live_status) -> str:
    """A one-line legend + status summary under the diagram.

    Names the glyph meanings and reports how many nodes carry a live signal vs.
    how many are design-time-only ("selected"), so the honesty is stated, not just
    drawn: a node with no telemetry is unmeasured, never assumed up."""
    live_count = sum(1 for n in nodes if n["status"] in _LIVE_STATUSES)
    selected_only = sum(1 for n in nodes if n["status"] == STATUS_SELECTED)
    up = sum(1 for n in nodes if n["status"] == STATUS_UP)
    down = sum(1 for n in nodes if n["status"] == STATUS_DOWN)
    legend = ("**Legend** &nbsp; • selected &nbsp; ✓ up &nbsp; ✗ down &nbsp; "
              "— unmeasured")
    if live_status:
        summary = (f"{live_count} node(s) report live status "
                   f"({up} up, {down} down); {selected_only} are design-time only "
                   "(no telemetry — shown unmeasured, never assumed up).")
    else:
        summary = (f"No live telemetry attached — all {selected_only} nodes are "
                   "design-time (selected), not measured. Deploy and wire live "
                   "status to light the path up.")
    return f"{legend}<br/>{summary}"


def topology_panel(mo, ui, selection, live_status=None):
    """Build the topology panel: header, the mermaid graph, and a legend/status line.

    `mo`/`ui` are passed in by the calling cell (same convention as the other
    panel builders). An empty selection returns a panel inviting the user to pick
    components first, rather than a near-empty graph."""
    selection = selection or {}
    has_picks = any([
        selection.get("storage"),
        selection.get("catalog"),
        selection.get("schema"),
        [c for c in (selection.get("ingest") or []) if c],
        [c for c in (selection.get("query") or []) if c],
    ])
    if not has_picks:
        return ui.panel(
            mo,
            ui.header(mo, "Land — pipeline topology"),
            mo.md("*Pick components above to draw the data path. The topology view "
                  "renders your stack as a sources → route → land → query → present "
                  "graph, so you see where an event goes, not just which boxes are "
                  "checked.*"),
        )

    topo = build_topology(selection, live_status)
    return ui.panel(
        mo,
        ui.header(mo, "Land — pipeline topology"),
        mo.md("How an event travels through the selected stack — Source(s) → Route "
              "(ingest, OCSF-normalize) → Lakehouse (storage + Iceberg) brokered by "
              "the Catalog → Engine(s) → Present."),
        mo.mermaid(topo["mermaid"]),
        mo.md(_legend_md(topo["nodes"], live_status)),
    )
