---
type: MDR
id: MDR-9002
title: Sample — answer-equality is a standing gate, not a one-off check
status: accepted
date: 2026-02-03
synthetic: true
tags: [sample, verification]
---

**Synthetic sample record — fictional organization, shipped for demonstration only.**

Meridian Metals (fictional) treats cross-engine answer-equality as a standing control: every
query engine reading the shared lakehouse must return the same answer over the same table
before and after any component swap. The trigger was a (fictional) incident in which a
faster reader returned a silently low count and the dashboard stayed green.

This decision operationalizes [[H-901-sample-fast-reader-wrong]] and is re-run on every
version bump, because a defect a point release fixes is one a later release can reintroduce.
See also the retention tension recorded in [[C-901-sample-retention-tension]].
