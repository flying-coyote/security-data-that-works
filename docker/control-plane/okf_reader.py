"""Minimal Google Open Knowledge Format (OKF) v0.1 bundle reader.

OKF v0.1 (Google Cloud, published 2026-06-12) represents knowledge as a directory
of markdown files with YAML frontmatter. One field is required, `type`; the rest
(`title`, `description`, `resource`, `tags`, `timestamp`) are recommended, and
relationships between notes are plain markdown links. Spec:
https://github.com/GoogleCloudPlatform/knowledge-catalog/blob/main/okf/SPEC.md

The project1 vault is already an OKF bundle: every note carries `type:` frontmatter
drawn from a 27-type registry (`01-knowledge-base/_type-registry.md`), and notes
reference each other with `[[wikilinks]]`. This module reads that bundle directly —
read-only, headless, no MCP dependency — so the control plane can surface the
standing decisions/assumptions that explain *why* a given stack was chosen.

It deliberately does NOT call the Tolaria MCP server: that server is a read-only
stdio JSON-RPC endpoint meant for an agent host, not for an in-process Python app.
Reading the same files as an OKF bundle gets the same vault content without the
protocol mismatch. Point `VAULT_PATH` at the vault (the Tolaria convention).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

# [[name]] / [[name|alias]] / [[name#section]] -> capture the bare basename
_WIKILINK = re.compile(r"\[\[([^\]|#]+)")
# [text](some/path.md) -> capture the target path
_MDLINK = re.compile(r"\]\(([^)]+\.md)(?:#[^)]*)?\)")

# Vault areas that hold historical/non-OKF content; skipped by default.
_SKIP_PARTS = frozenset(
    {".archive", "05-archives", "automation", "exports", ".venv", "node_modules", ".git"}
)


@dataclass(frozen=True)
class OKFNote:
    """One OKF concept document: its path, type, frontmatter, and body."""

    path: Path
    type: str
    frontmatter: dict
    body: str

    @property
    def id(self) -> str:
        return str(self.frontmatter.get("id") or self.path.stem)

    @property
    def title(self) -> str:
        return str(self.frontmatter.get("title", ""))

    @property
    def links(self) -> set[str]:
        """Basenames this note references (the OKF relationship graph edges)."""
        names = set(_WIKILINK.findall(self.body))
        names |= {Path(p).stem for p in _MDLINK.findall(self.body)}
        return {n.strip() for n in names if n.strip()}


def _split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return {}, parts[2]
    return (fm if isinstance(fm, dict) else {}), parts[2]


def load_bundle(root, *, subdirs=None, skip=_SKIP_PARTS) -> list[OKFNote]:
    """Load all OKF notes (files with a `type:` field) under `root`.

    `subdirs` restricts the scan to those relative paths; otherwise the whole
    bundle is read. Files without a `type` are not OKF concepts and are skipped.
    """
    root = Path(root)
    bases = [root / s for s in subdirs] if subdirs else [root]
    notes: list[OKFNote] = []
    for base in bases:
        if not base.exists():
            continue
        for path in base.rglob("*.md"):
            if skip.intersection(path.parts):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            fm, body = _split_frontmatter(text)
            note_type = fm.get("type")
            if not note_type:  # OKF requires `type`; non-OKF file
                continue
            notes.append(OKFNote(path, str(note_type), fm, body))
    return notes


def by_type(notes) -> dict[str, list[OKFNote]]:
    grouped: dict[str, list[OKFNote]] = {}
    for note in notes:
        grouped.setdefault(note.type, []).append(note)
    return grouped


def index_by_id(notes) -> dict[str, OKFNote]:
    """Map each note's id -> note, so a provenance ref (A-03, H-xxx) resolves to its
    title/confidence/last-reviewed. Last note wins on a duplicate id."""
    return {n.id: n for n in notes}


def search(notes, query: str) -> list[OKFNote]:
    """Substring match over id, title, the `claim` field, and the body."""
    q = query.strip().lower()
    if not q:
        return list(notes)
    out = []
    for note in notes:
        haystack = " ".join(
            [note.id, note.title, str(note.frontmatter.get("claim", "")), note.body[:800]]
        ).lower()
        if q in haystack:
            out.append(note)
    return out
