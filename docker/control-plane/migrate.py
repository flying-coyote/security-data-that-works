"""Migrate — the intent-driven migration cockpit.

The open-architecture thesis is that reversibility makes a wrong move cheap: every
component sits behind a stable contract (the Iceberg table, the REST catalog, OCSF on
the wire), so a migration is a *swap* with a stated cost and a verification step, not a
bet you can't unwind. This module turns that thesis into operator direction. The operator
picks one migration INTENT and the panel expands to focused guidance for it (progressive
disclosure) rather than dumping every migration path at once.

Two things keep the guidance honest rather than hand-wavy:
  - The swap cost and the back-out path are read off the *selected* components' real
    `swap_cost` field in providers.py (the per-component reversibility cliff), not invented
    per intent. A catalog swap reads what swapping THIS catalog actually costs; an engine
    swap reads THIS engine's.
  - The verify step is a concrete data-health check — the same `./moar` verb the evidence
    runner shells out to — that proves the move didn't silently break anything: cross-engine
    answer-equality for an engine swap, swap-store / swap-catalog / swap-router for those,
    flow reconciliation for a route change. A migration you can't verify is a migration you
    can't safely reverse, so the verify step is part of the intent, not an afterthought.

guidance_for() is a pure function over (intent_id, selection); the panel builder only
renders it. An unknown intent_id degrades to a clean "unknown intent" guidance rather
than raising, so a stale dropdown value can't crash the cell.
"""
from __future__ import annotations

import providers as P

# --- Migration intents --------------------------------------------------------
# Each intent: id, label, the component `category` it primarily touches (a providers.py
# category, or None for the augment intent which adds a whole stack alongside the SIEM),
# the `./moar` verify verb that proves the move, and a one-line description for the
# no-selection list view. `tier` names the reversibility tier the design uses
# (L-tier storage, I-tier catalog, R-tier router/engine) where there is one.
INTENTS = [
    {
        "id": "augment_alongside_siem",
        "label": "Stand up the lakehouse alongside the SIEM (augment, don't replace)",
        "category": None,
        "verify": "verify",
        "tier": None,
        "desc": "Land a copy of telemetry in the open lakehouse next to the existing SIEM, "
                "so you can compare answers before moving any read path.",
    },
    {
        "id": "swap_query_engine",
        "label": "Swap one query engine for another",
        "category": "query",
        "verify": "verify",
        "tier": "R-tier (query)",
        "desc": "Repoint analysts from one engine to another over the same Iceberg tables — "
                "the lowest-cost swap in the stack.",
    },
    {
        "id": "change_catalog",
        "label": "Add or change the catalog (I-tier)",
        "category": "catalog",
        "verify": "swap-catalog",
        "tier": "I-tier (catalog)",
        "desc": "Re-register Iceberg tables against a different REST catalog without "
                "rewriting any data files.",
    },
    {
        "id": "change_storage",
        "label": "Change the object store / storage tier (L-tier)",
        "category": "storage",
        "verify": "swap-store",
        "tier": "L-tier (storage)",
        "desc": "Move the bytes to a different S3-compatible store — a copy, not a re-land.",
    },
    {
        "id": "swap_router",
        "label": "Swap the ingest router / pipeline (R-tier)",
        "category": "ingest",
        "verify": "swap-router",
        "tier": "R-tier (router)",
        "desc": "Replace the pipeline that normalizes and routes data — re-authors transforms, "
                "leaves landed data untouched.",
    },
    {
        "id": "replace_siem_read_path",
        "label": "Replace the SIEM read path (cutover)",
        "category": "query",
        "verify": "verify",
        "tier": "R-tier (query)",
        "desc": "Cut detections and hunts over from the SIEM to the lakehouse read path — the "
                "irreversible-feeling step the augment intent de-risks first.",
    },
]

INTENT_INDEX = {i["id"]: i for i in INTENTS}

# How each verify verb reads in operator language — the data-health check that proves the
# move didn't silently break anything. Mirrors evidence_runner.VERBS / the `./moar` verbs.
_VERIFY_TEXT = {
    "verify": "`./moar verify` — cross-engine answer-equality: every running engine must "
              "return the identical answer over the same Iceberg table. A new or swapped engine "
              "that returns a filtered count short of the others over byte-identical data is a "
              "silent-wrong-answer, and this catches it before you trust the read path.",
    "swap-store": "`./moar swap-store` — run the same query against the old and new object "
                  "store and assert an identical answer. Proves the bytes moved without changing "
                  "what the lakehouse returns (L-tier reversibility).",
    "swap-catalog": "`./moar swap-catalog` — query the same tables via the old and new REST "
                    "catalog and assert an identical answer. Proves the tables re-registered "
                    "cleanly with no data rewrite (I-tier reversibility).",
    "swap-router": "`./moar swap-router` — feed the same raw events through the old and new "
                   "router and assert identical OCSF out. Proves the re-authored transforms "
                   "preserve the contract (R-tier reversibility).",
    "flow-reconcile": "Flow reconciliation — count events emitted → ingested → landed per OCSF "
                      "class across the new route and assert nothing is silently dropped. A route "
                      "change that quietly loses one class is a coverage hole a reachable stack "
                      "can't see.",
}


def _touched_codes(intent, selection) -> list:
    """The selected component codes the intent acts on (always a list of codes)."""
    cat = intent["category"]
    if not cat:
        return []
    val = (selection or {}).get(cat)
    if val is None:
        return []
    return list(val) if isinstance(val, list) else [val]


def _label(category, code) -> str:
    group = P.CATEGORIES.get(category)
    return P.label_for(group, code) if group else str(code)


def _swap_cost_for(category, codes) -> tuple[str, str]:
    """Derive (cost_level, why) from the touched components' real swap_cost field.
    cost_level is the highest tier any touched component carries (low < medium < high);
    why concatenates the per-component reversibility text from providers.py."""
    group = P.CATEGORIES.get(category)
    if not group or not codes:
        return "", ""
    rank = {"low": 1, "medium": 2, "high": 3}
    worst, parts = 0, []
    for code in codes:
        prov = P.find(group, code)
        text = (prov.swap_cost if prov else "") or ""
        if not text:
            continue
        # The swap_cost field opens with the level word ("Low — ...", "Medium-high — ...").
        head = text.split("—", 1)[0].strip().lower()
        level = "high" if "high" in head else "medium" if "medium" in head else "low" if "low" in head else ""
        worst = max(worst, rank.get(level, 0))
        parts.append(f"{prov.label}: {text}")
    level_word = {1: "low", 2: "medium", 3: "high"}.get(worst, "")
    return level_word, "  ".join(parts)


def guidance_for(intent_id, selection: dict) -> dict:
    """Pure function: focused migration direction for one intent over the current selection.

    Returns {intent, summary, steps, swap_cost, verify, reversibility, risks}. swap_cost and
    reversibility are derived from the touched components' real `swap_cost` field; verify is the
    concrete data-health check (`./moar` verb) that proves the move. Specializes to the selected
    components by name where it can. An unknown intent_id degrades cleanly (never raises)."""
    intent = INTENT_INDEX.get(intent_id)
    if intent is None:
        return {
            "intent": "Unknown migration intent",
            "summary": (f"No guidance for intent `{intent_id}`. Pick one of: "
                        + ", ".join(i["id"] for i in INTENTS) + "."),
            "steps": [],
            "swap_cost": "",
            "verify": "",
            "reversibility": "",
            "risks": [],
        }

    cat = intent["category"]
    codes = _touched_codes(intent, selection)
    named = ", ".join(_label(cat, c) for c in codes) if codes else ""
    verify = _VERIFY_TEXT.get(intent["verify"], "")
    level, why = _swap_cost_for(cat, codes) if cat else ("", "")

    # --- per-intent guidance --------------------------------------------------
    if intent_id == "augment_alongside_siem":
        store = _label("storage", (selection or {}).get("storage"))
        cat_lbl = _label("catalog", (selection or {}).get("catalog"))
        q = (selection or {}).get("query") or []
        q_lbl = ", ".join(_label("query", c) for c in q) if q else "your selected engine"
        summary = (
            "Run the open lakehouse next to the SIEM and prove parity before you move any read "
            "path. Nothing is cut over, so this is the cheapest possible first move — the SIEM "
            "stays authoritative while you build confidence that the same questions get the same "
            "answers from the lake."
        )
        steps = [
            "Tee ingest: fan one copy of telemetry into the SIEM (unchanged) and one into "
            f"the lakehouse via your selected pipeline, landing as OCSF on {store}.",
            f"Register the landed tables in {cat_lbl} and point {q_lbl} at them.",
            "Pick a handful of existing SIEM detections/searches and re-express them against "
            "the lake; run both daily over the same window.",
            "Compare answers side by side until they agree — only then consider moving a read "
            "path (the 'replace the SIEM read path' intent).",
        ]
        swap_cost = ("low — you are adding a stack, not removing one. Backing out is deleting "
                     "the lake copy; the SIEM is never touched, so there is nothing to undo on "
                     "the authoritative side.")
        reversibility = ("Fully reversible: tear down the lakehouse copy and you are back to "
                         "SIEM-only. The SIEM read path is never altered in this intent.")
        risks = [
            ("info", "Double ingest cost while parallel",
             "You pay to land telemetry twice during the parallel-run window. That is the price "
             "of de-risking the cutover; scope it to a subset of sources if the volume bill is a "
             "concern, and route-by-value to drop low-value events from the lake copy."),
            ("warn", "Parity is the gate, not the calendar",
             "Don't set a cutover date before answers agree. Use `./moar verify` to prove "
             "cross-engine answer-equality on the lake first; a date-driven cutover is how a "
             "silent mapping gap reaches production."),
        ]

    elif intent_id == "swap_query_engine":
        summary = (
            f"Repoint analysts from one query engine to another ({named or 'your selected engines'}) "
            "over the same Iceberg tables through the catalog. The data does not move and nothing "
            "is rewritten, so this is the lowest-cost swap in the stack — the engine is the most "
            "replaceable layer precisely because every engine reads the same shared tables."
        )
        steps = [
            "Stand up the new engine pointed at the existing REST catalog — no data copy, it "
            "reads the same Iceberg tables.",
            "Port the saved queries/detections; most are portable SQL, but engine-specific "
            "accelerations (ClickHouse MergeTree/projections, StarRocks materialized views, "
            "Dremio Reflections) rebuild from scratch on the new engine.",
            "Run `./moar verify` so the new engine is in the cross-engine answer-equality set and "
            "agrees with the others before any analyst depends on it.",
            "Cut analysts over once it agrees; leave the old engine running until you're "
            "confident, since both read the same tables and cost only compute.",
        ]
        swap_cost = (f"{level or 'low'} — {why}" if why else
                     "low — engines read the shared Iceberg tables through the catalog, so a "
                     "swap repoints clients with no data rewrite.")
        reversibility = ("Repoint clients back to the prior engine — both read the same tables, "
                         "so reverting is a connection-string change. The only loss is any "
                         "engine-specific acceleration you built, which has to be rebuilt either way.")
        risks = [
            ("warn", "Engine-specific acceleration doesn't port",
             "Base Iceberg tables port for free, but MergeTree tables/projections, async "
             "materialized views, or Reflections are engine-specific and rebuild from scratch. "
             "Budget that, and don't count it as data loss — the source tables are intact."),
            ("info", "Prove equality before trust",
             "An engine that silently returns a short count over identical data is the failure "
             "mode here. The answer-equality verb is the whole point of the open-stack design — "
             "use it, don't assume agreement."),
        ]

    elif intent_id == "change_catalog":
        summary = (
            f"Re-register the Iceberg tables against a different REST catalog "
            f"({named or 'your selected catalog'}) without rewriting any data files. The table data "
            "is portable by design; what's catalog-specific is the governance around it (RBAC/OPA "
            "policy, branch/tag history, lineage), and that is what the move re-authors."
        )
        steps = [
            "Stand up the new catalog with its relational backend (most REST catalogs need "
            "Postgres for persistence).",
            "Register the existing Iceberg tables into it — point it at the same warehouse "
            "path; the Parquet/metadata files stay exactly where they are.",
            "Re-author the governance layer: RBAC/OPA/OpenFGA policy doesn't migrate, and "
            "Nessie-style branch/tag history or Unity lineage is catalog-specific and doesn't port.",
            "Run `./moar swap-catalog` to prove a query returns the identical answer through the "
            "old and the new catalog before repointing engines.",
        ]
        swap_cost = (f"{level or 'medium'} — {why}" if why else
                     "medium — Iceberg tables re-register against another REST catalog without "
                     "rewriting data files; the policy/history layer has to be re-authored.")
        reversibility = ("Re-register the tables back against the prior catalog — the data files "
                         "never moved, so reverting is metadata-only. Catalog-specific governance "
                         "(branch/tag history, lineage) is the part that doesn't survive a round trip.")
        risks = [
            ("warn", "Governance and history are catalog-specific",
             "Data files port; the RBAC/OPA policy, Nessie branch/tag history, and Unity lineage "
             "do not. Treat re-authoring policy as the real work of this migration, not the "
             "re-registration."),
            ("info", "Watch the storage-credential path",
             "REST catalogs on SeaweedFS need static S3 keys + path-style (STS AssumeRole isn't "
             "served); a catalog swap is a good moment to re-check that wiring."),
        ]

    elif intent_id == "change_storage":
        summary = (
            f"Move the bytes to a different S3-compatible object store "
            f"({named or 'your selected store'}). Because every store in the stack speaks the same "
            "S3 API, this is a copy plus a config change, not a re-land — the table format and the "
            "catalog don't care which store holds the files as long as the paths resolve."
        )
        steps = [
            "Stand up the new store and copy the warehouse prefix across (an S3 copy, not a "
            "re-ingest — the Iceberg files are bytes that move as-is).",
            "Update the catalog's warehouse location / S3 endpoint to the new store and "
            "redeploy; no table metadata rewrite is needed.",
            "Run `./moar swap-store` to prove the same query returns the identical answer on the "
            "new store before retiring the old one.",
            "Decommission the old store once verified — keep it read-only for a window as the "
            "back-out path.",
        ]
        swap_cost = (f"{level or 'low'} — {why}" if why else
                     "low — S3-compatible stores swap by config + redeploy; moving the data is an "
                     "S3 copy, not a re-land. Cloud egress is the real bill, not a rewrite.")
        reversibility = ("Point the catalog back at the old store (kept read-only during the "
                         "window) — a config revert. The data is identical bytes in both places "
                         "until you decommission, so back-out is immediate.")
        risks = [
            ("warn", "Egress, not rewrite, is the cost moving OUT of cloud S3",
             "The API is portable, but moving data out of a cloud store incurs egress and data-"
             "gravity cost. That's the bill to size, and it's why the swap_cost on S3 flags "
             "data-out rather than a table rewrite."),
            ("info", "Keep the old store read-only during cutover",
             "Don't decommission until `./moar swap-store` agrees. A read-only old store is a "
             "zero-cost back-out path for the verification window."),
        ]

    elif intent_id == "swap_router":
        summary = (
            f"Replace the ingest router / pipeline ({named or 'your selected pipeline'}) that "
            "normalizes and routes telemetry into the lake. Landed data is untouched; what the "
            "swap re-authors is the transform logic, which is pipeline-specific (Vector's VRL, "
            "Fluent Bit parsers, NiFi flows, Cribl packs all differ)."
        )
        steps = [
            "Stand up the new router alongside the current one and re-author the transforms — "
            "VRL, parser configs, flows, or packs don't port between engines.",
            "Feed both routers the same source for a window and land into a staging table so "
            "you can compare OCSF output without touching production tables.",
            "Run `./moar swap-router` to prove the old and new routers emit identical OCSF over "
            "the same raw events.",
            "Add a flow reconciliation pass (emitted → ingested → landed per OCSF class) so a "
            "class the new pipeline silently drops surfaces before cutover.",
        ]
        swap_cost = (f"{level or 'medium'} — {why}" if why else
                     "medium — pipeline transforms are engine-specific and a swap re-authors them; "
                     "the landed tables are unaffected, so there is no data rewrite.")
        reversibility = ("Route back through the prior pipeline — landed data was never changed, "
                         "so reverting is repointing the source. The re-authored transforms are "
                         "the sunk cost, not the data.")
        risks = [
            ("warn", "Transforms re-author, and a dropped class hides",
             "Every router has its own transform language, so the logic rebuilds by hand. The "
             "subtler risk is a silently dropped OCSF class — pair the swap-router check with flow "
             "reconciliation so coverage holes surface."),
            ("info", "Config-as-code routers revert cleaner",
             "Vector/Fluent Bit configs live in git and revert as a commit; NiFi flows live in a "
             "registry and Cribl in a SaaS, so their back-out is heavier. Factor that into which "
             "way you're swapping."),
        ]

    elif intent_id == "replace_siem_read_path":
        q = (selection or {}).get("query") or []
        q_lbl = ", ".join(_label("query", c) for c in q) if q else "your selected engine"
        summary = (
            f"Cut detections and hunts over from the SIEM to the lakehouse read path ({q_lbl}). "
            "This is the step that feels irreversible, which is exactly why the augment intent "
            "exists to de-risk it first: you only cut over read paths whose answers you've already "
            "proven equal to the SIEM's, so the move is a switch you've rehearsed, not a leap."
        )
        steps = [
            "Confirm the augment phase reached parity — the lake already answers these detections "
            "the same as the SIEM over the same window.",
            "Move detections in tiers, lowest-stakes first; keep the SIEM running the same "
            "detection in parallel as a shadow for each tier.",
            "Run `./moar verify` on the lake read path so the serving engine agrees cross-engine "
            "before it becomes authoritative.",
            "Promote a tier to authoritative only after a clean shadow window; keep the SIEM "
            "ingest on until every tier is migrated, so the back-out path stays open.",
        ]
        swap_cost = (f"{level or 'medium'} — {why}" if why else
                     "medium — the read path repoints to the shared tables, but cutting the SIEM "
                     "out of the loop is the consequential change; stage it behind a shadow window.")
        reversibility = ("Re-promote the SIEM detection for any tier while its ingest is still on "
                         "— that's why you keep SIEM ingest running until the last tier migrates. "
                         "Reversibility here is procedural (shadow + staged cutover), not just "
                         "a config revert.")
        risks = [
            ("warn", "Cutover is reversible only while SIEM ingest stays on",
             "The moment you turn off SIEM ingest you lose the back-out path. Keep it running "
             "through the staged cutover; the cost of double ingest buys you a real undo."),
            ("warn", "Don't cut a tier you haven't proven at parity",
             "A read-path cutover before answers agree is the one genuinely expensive mistake in "
             "this set. The augment intent and `./moar verify` exist to make sure you never do it."),
        ]

    else:  # registered intent with no bespoke body — generic but still grounded
        summary = (f"{intent['label']}. " + (f"Touches: {named}. " if named else "")
                   + "Framed as a reversible swap behind the open contract.")
        steps = [
            "Stand up the replacement alongside the current component.",
            "Re-author only the component-specific layer; the shared contract (Iceberg table / "
            "catalog / OCSF) carries across.",
            f"Run the verify step ({intent['verify']}) to prove the move didn't change answers.",
        ]
        swap_cost = (f"{level or 'medium'} — {why}" if why
                     else "see the per-component reversibility cost.")
        reversibility = "Revert behind the same contract you migrated across."
        risks = []

    return {
        "intent": intent["label"],
        "summary": summary,
        "steps": steps,
        "swap_cost": swap_cost,
        "verify": verify,
        "reversibility": reversibility,
        "risks": risks,
    }


# --- Panel builder ------------------------------------------------------------

def migrate_panel(mo, ui, intent_id, selection):
    """Render the migration cockpit panel for one intent.

    The intent dropdown is built in control_plane; this renders the guidance for the given
    intent_id. If intent_id is None, returns a panel listing the available intents with
    one-line descriptions (the landing view before an intent is picked).
    """
    if intent_id is None:
        rows = [ui.note(mo, "info", i["label"], i["desc"]) for i in INTENTS]
        return ui.panel(
            mo,
            ui.header(mo, "Migrate — pick an intent"),
            mo.md("Every migration here is a *swap behind a stable contract*: the Iceberg table, "
                  "the REST catalog, and OCSF on the wire don't change, so a wrong move is cheap "
                  "to back out. Pick an intent and this expands to focused, verifiable direction."),
            *rows,
        )

    g = guidance_for(intent_id, selection)
    steps = g["steps"]
    step_notes = [ui.note(mo, "info", f"Step {n}", body) for n, body in enumerate(steps, 1)]

    # The structured swap-cost / reversibility / verify block.
    block = mo.md(
        f"**Swap cost** {g['swap_cost']}\n\n"
        f"**Reversibility** {g['reversibility']}\n\n"
        f"**Verify the move** {g['verify']}"
    ).style({
        "padding": "0.75rem 1rem",
        "border-left": "4px solid var(--color-teal-500)",
        "background-color": "var(--color-bg-subtle)",
        "margin": "0.75rem 0",
        "border-radius": "6px",
    })

    risk_notes = [ui.note(mo, lvl, title, body) for lvl, title, body in g["risks"]]

    children = [
        ui.header(mo, f"Migrate — {g['intent']}"),
        mo.md(g["summary"]),
    ]
    if step_notes:
        children.append(ui.header(mo, "Direction"))
        children.extend(step_notes)
    children.append(block)
    if risk_notes:
        children.append(ui.header(mo, "Risks to watch"))
        children.extend(risk_notes)

    return ui.panel(mo, *children)
