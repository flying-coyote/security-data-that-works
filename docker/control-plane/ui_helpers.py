"""Shared marimo UI helpers for the MOAR control plane.

Collapses the card/panel `.style({...})` dicts that were copy-pasted across a
dozen cells into two constants and three helpers, and gives section headers one
consistent size (the selection pane previously mixed markdown heading levels,
which is why the fonts looked inconsistent).
"""
from __future__ import annotations

CARD_STYLE = {
    "border": "1px solid var(--color-border-subtle)",
    "padding": "1.25rem",
    "background-color": "var(--color-bg-subtle)",
    "flex": "1",
    "min-width": "200px",
    "border-radius": "8px",
}

PANEL_STYLE = {
    "border": "1px solid var(--color-border-subtle)",
    "padding": "1.5rem",
    "background-color": "var(--color-bg-primary)",
    "margin-bottom": "1.5rem",
}


def card(mo, *children, **overrides):
    """A selection card with the shared style (override any key via kwargs)."""
    return mo.vstack(list(children)).style({**CARD_STYLE, **overrides})


def panel(mo, *children, **overrides):
    """A section panel with the shared style."""
    return mo.vstack(list(children)).style({**PANEL_STYLE, **overrides})


def header(mo, text):
    """A fixed-size section header — avoids mixing markdown heading levels."""
    return mo.Html(f"<div class='sdw-card-h'>{text}</div>")


def note(mo, level, title, body):
    """Render one compatibility/operational note.

    level == "warn" -> red accent; level == "info" -> muted accent.
    """
    color = "#c14a4a" if level == "warn" else "var(--color-text-muted)"
    return mo.md(f"**{title}**<br/>{body}").style({
        "padding": "0.6rem 0.9rem",
        "border-left": f"4px solid {color}",
        "background-color": "var(--color-bg-subtle)",
        "margin-bottom": "0.5rem",
    })


# ---------------------------------------------------------------------------
# PG-7 / CF-ART — the DISAGREEMENT panel.
#
# The Wall (PG-4 design-time prediction) shows where defenses are MAPPED; the lab's
# ocsf-attack-coverage bench (C5) shows where detections actually FIRE. This panel
# is the REAL MAP — the disagreement between the two, surfaced rather than papered
# over. It renders ONLY the reconciled aggregate records from attack_coverage.
# reconcile(): technique id, design-time status, measured state, the reconciliation
# bucket, precision, and the carried-through weakest trust tier. Every label is
# routed through _safe_key (the telemetry-injection boundary); the panel reads NO
# raw events and emits NO fabricated score (mirrors navigator_layer's no-score rule).
# ---------------------------------------------------------------------------

# The design-time prediction emoji (matches attack_coverage._STATUS_EMOJI).
_DESIGN_EMOJI = {"fired": "🔴", "covered": "🟢", "dark_spot": "🟡", "blind": "⚪"}
# The measured C5 firing emoji.
_MEASURED_EMOJI = {"DETECTED": "🟢", "MISSED": "🔴", "NOISY": "🟠", "not_measured": "⚪"}
# The reconciliation bucket emoji — RED is the exposed gap, the whole point.
_RECON_EMOJI = {
    "confirmed_fired": "🟢",
    "predicted_covered_but_missed": "🔴",
    "fired_but_noisy": "🟠",
    "not_measured": "⚪",
    "measured_only": "🟡",
}
_RECON_LABEL = {
    "confirmed_fired": "confirmed fired",
    "predicted_covered_but_missed": "predicted covered, MISSED",
    "fired_but_noisy": "fired but noisy",
    "not_measured": "not measured — re-run the bench",
    "measured_only": "measured only (no design-time hunt)",
}


def disagreement_panel(mo, ui, reconciled, meta=None, *, source_note=""):
    """The measured-firing overlay — design-time prediction vs measured C5 firing.

    One row per reconciled record: the design-time prediction (Wall / PG-4), the
    measured firing (C5 bench), the reconciliation verdict, precision, and the
    carried-through weakest trust tier. The reconciliation is colour/emoji-coded:
    confirmed_fired green, predicted_covered_but_missed RED (the exposed gap),
    fired_but_noisy amber, not_measured grey (honest-degrade).

    The headline number traces to C5 via the vendored _meta (detected/techniques_total),
    NEVER computed here. Every surfaced label routes through the imported _safe_key.
    """
    # Import the boundary lazily so this low-level helper has no import-time dependency
    # on the analyze stack when it isn't used.
    from analyze import _safe_key

    header = ui.header(mo, "ATT&CK coverage — the REAL MAP (measured firing vs design-time)")
    intro = mo.md(
        "The Wall shows where defenses are **MAPPED**; the bench shows where detections "
        "**FIRE**. This panel is the **REAL MAP** — the *disagreement* between the two. "
        "A 🟢 **confirmed fired** means the prediction held (the lab measured DETECTED). "
        "A 🔴 **predicted-covered-but-MISSED** is the exposed gap — design-time said a hunt "
        "watches it, the bench measured nothing fired. 🟠 **fired but noisy** fired with "
        "false positives (precision shown). ⚪ **not measured** is the honest-degrade — no "
        "measured verdict exists, *re-run the bench* (it is never a green and never a pass)."
    )

    # Staleness banner: if the import decayed, every verdict reads not_measured.
    stale_note = None
    if reconciled and reconciled[0].get("import_stale"):
        stale_note = ui.note(
            mo, "warn", "Stale bench import — measured overlay decayed",
            "The vendored coverage.json is older than its TTL (or undatable), so every "
            "technique honest-degrades to not_measured. Re-run the bench and regenerate "
            "the vendored verdicts — an old firing is never served as current.")

    if not reconciled:
        return ui.panel(
            mo, header, intro,
            ui.note(mo, "info", "No techniques to reconcile",
                    "The design-time coverage set is empty — nothing to overlay."),
            mo.md(source_note),
        )

    # Tally each reconciliation bucket for the summary line.
    buckets = {}
    for r in reconciled:
        buckets[r["reconciliation"]] = buckets.get(r["reconciliation"], 0) + 1
    tally = " · ".join(
        f"{_RECON_EMOJI.get(k, '')} {buckets[k]} {_RECON_LABEL.get(k, k)}"
        for k in ("confirmed_fired", "predicted_covered_but_missed", "fired_but_noisy",
                  "not_measured", "measured_only")
        if buckets.get(k)
    )

    # The headline number traces to C5's vendored _meta — NEVER computed here.
    m = meta or {}
    detected = m.get("detected")
    total = m.get("techniques_total")
    thr = m.get("precision_threshold_T")
    if detected is not None and total is not None:
        headline = (
            f"**measured detected {detected}/{total}** "
            f"(source: coverage.json detected/techniques_total), threshold_T={thr}"
        )
    else:
        headline = "*measured headline unavailable — vendored _meta missing detected/total*"
    summary_line = mo.md(f"{headline} &nbsp;·&nbsp; {tally}")

    rows = []
    for r in reconciled:
        design = r.get("design_status", "—")
        measured = r.get("measured_state", "not_measured")
        recon = r.get("reconciliation", "not_measured")
        design_cell = f"{_DESIGN_EMOJI.get(design, '')} {_safe_key(design)}"
        measured_cell = f"{_MEASURED_EMOJI.get(measured, '')} {_safe_key(measured)}"
        recon_cell = f"{_RECON_EMOJI.get(recon, '')} {_RECON_LABEL.get(recon, _safe_key(recon))}"
        prec = r.get("precision")
        prec_cell = f"{prec}" if prec is not None else "—"
        rule = r.get("rule") or "—"
        rule_cell = f"`{_safe_key(rule)}`" if rule != "—" else "—"
        trust = r.get("weakest_trust_tier")
        trust_cell = f"{trust}" if trust is not None else "—"
        rows.append(
            f"| `{_safe_key(r.get('technique', ''))}` | {_safe_key(r.get('tactic', '—'))} "
            f"| {design_cell} | {measured_cell} | {recon_cell} | {rule_cell} "
            f"| {prec_cell} | {trust_cell} |"
        )
    table = mo.md(
        "| Technique | Tactic | Design-time (Wall/PG-4) | Measured firing (C5 bench) "
        "| Reconciliation | Sigma rule | precision | weakest trust |\n"
        "|---|---|---|---|---|---|---|---|\n"
        + "\n".join(rows)
    )

    children = [header, intro]
    if stale_note is not None:
        children.append(stale_note)
    children += [summary_line, table]
    children.append(ui.note(
        mo, "info", "Aggregate verdicts only — no raw events",
        "This overlay reads ONLY the vendored C5 aggregate verdicts (technique id + "
        "DETECTED/MISSED/NOISY + counts + precision + the public Sigma filename). The "
        "console computes no coverage number of its own and holds no raw event. The "
        "weakest-trust column is the design-time D3FEND tier carried through unchanged — "
        "the measured join never upgrades an intent-blind 0.25 edge."))
    children.append(mo.md(source_note))
    return ui.panel(mo, *children)
