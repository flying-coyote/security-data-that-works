---
type: MDR
id: MDR-9001
title: Sample — adopt an open table format for the demo lakehouse
status: accepted
date: 2026-01-15
synthetic: true
tags: [sample, lakehouse]
---

**Synthetic sample record — fictional organization, shipped for demonstration only.**

Meridian Metals (fictional) standardizes its demo security-data lakehouse on an open table
format with an open REST catalog, so any conformant engine can read the same tables and the
answer can be cross-checked rather than trusted. The alternative — an engine-native
proprietary store — was declined because it couples the data's lifetime to one vendor's
reader.

Consequences: every engine added later must pass the answer-equality gate described in
[[MDR-9002-sample-answer-equality-gate]] before its results are trusted, and the ingest
assumption in [[A-901-sample-ingest-growth]] sets when the single-node tier is outgrown.
