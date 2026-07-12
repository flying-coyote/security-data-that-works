# CLAUDE.md — session guidance for this repo (public)

This is the PUBLIC repo of Security Data Works. Everything committed here ships to anyone
who clones it, so the rules below gate every commit.

## Naming

- The kit's public name is the **MOAR Reference Stack** ("MOAR Stack" informally). "Console"
  names the marimo UI component inside it, not the product — keep "console" for the marimo
  app itself.

## Client references

- Atlassian / Project Banyan nameable ONLY with facts from the published public sources
  (Databricks customer story + 2026 Transformation Award + Schmerber's public OCSF deck);
  NDA-derived details — sourcetype counts, precise daily volumes — stay anonymized. No
  sourcetype count, no "2 PB", never mix the deck's 45% storage figure with Databricks' 20%
  file-size figure.
- NEVER publish Dremio benchmark results (DeWitt clause). Dremio as a deployable component
  option, and functional integration findings stated without performance figures, are fine.

## Paid/public firewall

- Per-vendor Capability Matrix scores, weights, weighted totals, and claim-vs-shipped deltas
  are paid SDW IP and never live in this repo. The firewall is `docker/control-plane/
  paid_scoring.py` (`MOAR_PAID_MODE` + the `PaidScoreLeak` guard); its proofs are the
  `prove_*.py` battery. Builds may widen the public half, but no score crosses the line.

Portfolio-review program (2026-07): see `.claude/review-protocol.md` before any review-program session.
