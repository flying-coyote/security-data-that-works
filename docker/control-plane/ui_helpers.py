"""Shared marimo UI helpers for the MOAr control plane.

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
