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

## Review rules (folded from the retired `.claude/review-protocol.md`, 2026-11-08)

- **apply_now** (edit without staging for Jeremy) requires ALL of: mechanically derivable from a named source; reversible in one commit; no narrative, voice or framing change; no price, tier or taxonomy choice; not touching a settled decision in the hub's DO-NOT-REFLAG list. Anything else is staged for the owner in the hub.
- **Numbers**: every quantitative claim in agent-drafted, publication-bound prose is re-derived by a different agent from the named source before commit; unverifiable means stage it, never ship it.

## Owner rulings recorded 2026-11-08 (grill bank items 3 and 4)

- **The repo name echoes the venture name on purpose.** "security-data-that-works" next to Security Data Works is a deliberate echo, not drift; do not propose a rename.
- **The MOAR Reference Stack supersedes `~/zeek-iceberg-demo`.** That repo is formally retired as a working demo, but it stays archived rather than deleted, because book ch02 cites it as provenance (ch02:203). Its archive (git bundle plus a tar of dirty files to the off-disk store) is a hub action recorded in the hub's REPOSITORY-MAPPING.md.

## Cloud sessions and Claude Code Projects (2026-11-15)

A Claude Code Projects thread loads this file and `.claude/rules/` only, not this repo's skills, commands, hooks or permission rules from `.claude/settings.json`, or `.mcp.json`. An ordinary single-repo cloud session or cloud routine does read the committed `.claude/settings.json` ([cloud sessions doc](https://code.claude.com/docs/en/claude-code-on-the-web), corrected 2026-11-15), but no cloud session gets git hooks, because a fresh clone has none, so these local gates do not run there: the pre-commit secret scan (`secret-scan.sh`) ([Projects docs](https://code.claude.com/docs/en/claude-projects), "What threads pick up from your repositories"). From a cloud thread, work on a branch and open a draft pull request, never push to `master` and never merge, and say in the pull request which of these local gates still need a local run before merge.
