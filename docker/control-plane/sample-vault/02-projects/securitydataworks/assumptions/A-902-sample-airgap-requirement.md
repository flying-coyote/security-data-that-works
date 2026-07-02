---
type: Assumption
id: A-902
title: Sample — the analysis enclave stays air-gapped
claim: "SAMPLE (fictional): Meridian Metals' analysis enclave must run with no outbound network path, so every component has to be self-hostable and mirror-able."
confidence: high
last_reviewed: 2026-06-01
synthetic: true
tags: [sample, deployment]
---

**Synthetic sample record — fictional organization, shipped for demonstration only.**

A standing deployment constraint of the fictional organization: anything that requires a
cloud control plane is disqualified before evaluation starts. This is the assumption the
constraint filter's air-gap toggle represents, and it narrows the candidate set referenced
by [[MDR-9001-sample-open-table-format]].
