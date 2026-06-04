# Contributing

This repo is a front door to the open projects it stands on, not a fork of them. The most useful
thing you can do is take a fix upstream, where everyone benefits, rather than keep it in a private
patch. Here's where each kind of fix goes.

## You found a type-crossing the gate should catch but doesn't, or a pair that should be disjoint

That belongs in **D3FEND**. The disjointness layer in this repo is a proposed extension of
[d3fend/d3fend-ontology #423](https://github.com/d3fend/d3fend-ontology/issues/423) ("Assert that
some d3fend core classes are disjoint"), which asserted top-level disjointness and explicitly asked
to "carefully extend this down the hierarchy in the future." The eight-artifact layer here is one
step of that extension. If you find an artifact pair that's genuinely disjoint and isn't covered,
open an issue or PR there referencing #423, and state the scope honestly: disjointness authoring
gets harder as the set widens, because genuinely-overlapping pairs start to appear (a credential can
be stored in a file), so each addition needs the same identity-not-relation adjudication.

## You found an OCSF field whose meaning is ambiguous or whose path the gate grounds wrong

That belongs in **OCSF** ([ocsf/ocsf-schema](https://github.com/ocsf/ocsf-schema)). If a field's
intended meaning is genuinely unclear from the spec, that ambiguity is itself the bug, and clarifying
it upstream helps every consumer, not just this check.

## You want this check in a real detection pipeline

The natural home is **[SigmaHQ/pySigma-pipeline-ocsf](https://github.com/SigmaHQ/pySigma-pipeline-ocsf)**,
as a CI lint step over the pipeline's source→OCSF mappings. The validator here is written to be
dropped in as exactly that: a two-column CSV in, a non-zero exit on any type-crossing out.

## You want to improve the demo itself

PRs to this repo are welcome for the demo and the validator: clearer examples, better packaging, a
tighter container, more honest framing. Keep the validator model-independent (no LLM in the
checking loop, that's the point) and keep the scope claims accurate (it answers "is this mapping
type-consistent?", per row; it does not score vendors).

## A note on what's not here

The weighted fidelity scoring, the coverage and shipped-vs-claim deltas, and any per-vendor scored
verdict are deliberately not in this repo. This is the open check; the scoring is separate work. If
that distinction matters for what you're building, open an issue and let's talk about it.
