# What good looks like — the security-data-that-works spec

This repo states *what good looks like* for security data, in public, as a method rather than a product.
It sits above two other things: the **SDW Lab** (the *evidence* — reproducible benchmarks you can clone and
run) and the **Capability Matrix** (the *scoring instrument* — per-vendor scores, which stay paid). The spec
here is the public method; the per-vendor scores are not.

The flagship runnable example of the spec is the deductive OCSF→D3FEND mapping gate in [`gate/`](gate/) (see
the [README](README.md)) — a clone-and-run check that catches the wrong field mapping that silently kills a
detection. It is the data-health-validation category made executable; the other categories are stated here
and will grow the same way, evidence first.

The spec is organized into five categories. Each states the principle, points to the evidence that backs it,
and is the thing the Capability Matrix scores a vendor against.

## 1. Data-health validation — does the data mean what the schema says?

Shape-validation (types) is necessary and not sufficient. A field can fit OCSF exactly and still mean the
wrong thing, and a mapping wrong by construction fails silently: the schema validates, the table fills, and
the records you needed simply are not there. The principle is that meaning has to be *verified*, not trusted
because someone shipped it.

- **Runnable evidence**: the deductive OCSF→D3FEND mapping gate ([`gate/`](gate/)) — a reasoner flags a
  type-crossing mapping as a class that cannot logically exist, no ML in the loop, the same verdict whoever
  produced the mapping.
- **Lab evidence**: the cross-engine answer-equality finding (one query engine silently undercounting a
  Parquet equality filter — a fast wrong answer that a timing-only benchmark would have published as a win)
  and the context-collapse finding (coarse normalization doesn't tax detection uniformly; it makes some rules
  go blind while others cry wolf).

## 2. Sources — is the telemetry actually arriving, and complete?

Sensor instrumentation, coverage, and the gap between "ingested" and "complete." A source that silently
under-collects (a sampled sensor, a firewall logging only blocks, a category switched off) is invisible until
an incident needs the data that was never landing. The principle is that source health is measured at the
point of arrival, not assumed from a connector's success status.

## 3. Flows — is the pipeline correct and fresh?

Pipeline correctness and freshness, the Google SRE golden signals applied to telemetry. Where data is
transformed it can be transformed wrong, and where it is buffered it can fall behind. The principle is that
the pipeline is instrumented for correctness and latency, not only for throughput.

## 4. Storage — formats, compression, and the answer you get back

The campaign findings seed this category directly:

- Table formats are **read-neutral on byte-identical data** — the Parquet *encoder/writer* is the read
  lever, not the table format. Pick the format on the write path and the catalog properties you need.
- Compression is **regime-aware** — a trained dictionary pays in the per-event streaming hot path; the
  columnar lake gets its compression from the format. The codec name is not the compression.
- Parquet is **not byte-reproducible** by default (parallel row order), so integrity workflows must hash
  logical content, not file bytes.
- The **query engine can return a silently wrong answer**, so a cross-engine answer-equality check is a
  required control, not ceremony.

## 5. Data architecture — the open substrate, tiered, under one contract

The deconstructed-database / open-format substrate, temperature-tiered (virtual hot, catalog warm,
materialized cold) under one read contract. The principle is that the substrate stays open and verifiable,
with the honest caveat that "the engine is indifferent to the backend" holds for most query shapes but not
unconditionally — the read path can still leak through on the heaviest scans.

## Build your own MCP, don't adopt a black box

The companion to the spec is [`build-your-own-mcp/`](build-your-own-mcp/) — the case, and the curated
references, for building an MCP server against a vendor's product *yourself, in your own environment*, rather
than adopting a vendor's potentially-vulnerable, phone-home MCP. The first-party cautionary example is real:
an MCP code executor that ran user code with in-process `exec()` and enforced neither memory nor timeout
limits, a denial-of-service waiting to happen that you would never see without reading the internals.

## What this is and isn't

The spec is the public method; the **per-vendor scores** that apply the method live in the Capability Matrix
and are paid. This repo is a front door to the open projects it stands on (D3FEND, OCSF, Sigma, the
ROBOT/ELK reasoner toolchain), not a fork of them, and the fixes it surfaces belong upstream where everyone
benefits.
