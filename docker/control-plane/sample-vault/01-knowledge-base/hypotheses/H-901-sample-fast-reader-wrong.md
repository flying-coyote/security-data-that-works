---
type: Hypothesis
id: H-901
title: Sample — a fast reader can be silently wrong
claim: "SAMPLE (fictional): a query engine can return a plausible, wrong answer with no error, so speed comparisons are meaningless until the answer itself is verified."
status: supported
confidence: high
last_reviewed: 2026-04-11
synthetic: true
tags: [sample, verification]
---

**Synthetic sample record — fictional organization, shipped for demonstration only.**

The working hypothesis behind the fictional organization's verification posture: correctness
failures in the read path are silent by nature, so the gate has to compare answers across
independent implementations rather than trust any single one. Ratified into practice by
[[MDR-9002-sample-answer-equality-gate]].
