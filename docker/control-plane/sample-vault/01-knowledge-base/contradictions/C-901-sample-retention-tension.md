---
type: Contradiction
id: C-901
title: Sample — seven-year retention vs. the small-files budget
status: open
date: 2026-05-05
synthetic: true
tags: [sample, retention]
---

**Synthetic sample record — fictional organization, shipped for demonstration only.**

Two standing positions of the fictional organization pull against each other: compliance
wants seven-year retention of normalized events, while the operations budget assumes the
table's metadata footprint stays small enough for a single-node planner. Frequent small
commits at [[A-901-sample-ingest-growth]]'s volumes grow metadata fast, so one of the two
positions must give (compaction cadence, a tiered store, or a shorter hot window). Recorded
as an open contradiction the way a real vault would hold it — unresolved, visible, and
linked to the assumptions it strains.
