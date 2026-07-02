# Sample vault — synthetic OKF bundle (fictional, ships with the public kit)

This directory is a **synthetic** Google Open Knowledge Format (OKF v0.1) bundle: a handful of
fictional decision records, assumptions, hypotheses, and contradictions for a made-up
organization ("Meridian Metals", which does not exist). It ships with the public MOAR
Reference Stack so the console's consultant-mode Strategy surface is demonstrable from a
public clone — the panel has real typed notes to render, search, and link.

What it is NOT:

- It is **not** the private strategy vault. No real vault content ships here, ever.
- It contains **zero scored-Matrix content** — no per-vendor criterion values, no weights,
  no totals. `prove_sample_vault.py` asserts this on every run, and the `PaidScoreLeak`
  firewall in `paid_scoring.py` independently refuses to source paid Matrix data from any
  path inside this repository (including this one).

How it is used: when `VAULT_PATH` is unset and no private vault exists on disk,
`okf_reader.resolve_vault_path()` falls back here (see `control_plane.py`); the console then
banners the surface as the bundled synthetic sample. Point `VAULT_PATH` at a real OKF vault
to replace it.

Every note carries `synthetic: true` frontmatter and a "Sample —" title prefix so nothing in
here can be mistaken for a real record.
