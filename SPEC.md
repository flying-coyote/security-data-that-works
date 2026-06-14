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

The transform that gets the least scrutiny is OCSF normalization at the pipeline, because "maps to OCSF" reads
like a finished property when it is really two separate questions. The first is *availability* — whether the
tool ships a usable mapping for your source at all — and in the normalization-fidelity bench that turned out
to be the binding constraint, not per-field accuracy: of the two open routing tools tested, one ships a
JSON-consumable OCSF mapping for one of four common security sources and the other ships none, so for most
sources the honest answer is that there is nothing to evaluate yet. The second question only matters where a
mapping does exist, and there *coverage is not fidelity*: a shipped mapping can land the right OCSF class and
most of the values and still get the part that drives detection wrong, because it never derives the activity
classification from the source's own state field, so a hunt that filters on the activity bucket sees a record
that validates and is still mis-classified. The principle is that a pipeline's OCSF mapping is scored on
availability first and then on the fidelity of the fields detection actually keys on — not on whether the
schema validates — and the gap is version-bound to the shipped mapping, so it is re-checked when the tool's
library moves (Tier B, single host; per-vendor scores are paid and stay out of this spec).

## 4. Storage — formats, compression, and the answer you get back

The campaign findings seed this category directly:

- Table formats are **read-neutral on byte-identical data** — the Parquet *encoder/writer* is the read
  lever, not the table format. Pick the format on the write path and the catalog properties you need.
- Compression is **regime-aware** — a trained dictionary pays in the per-event streaming hot path; the
  columnar lake gets its compression from the format. The codec name is not the compression.
- Parquet is **not byte-reproducible** by default (parallel row order), so integrity workflows must hash
  logical content, not file bytes.
- The lakehouse's **point-lookup weakness is a layout choice, not a fundamental limit**. On a random
  high-cardinality needle the inverted index does beat an *unsorted* open-format table by a wide margin
  (~41× on the worst case in the needle arm), but it ties a *sorted* columnar store that clusters on the
  looked-up columns — both serve the lookup in a few milliseconds, and the only thing that loses is the
  unsorted full scan. So the binding choice is whether the table is sorted/clustered on the fields the
  workload looks up, and the same sort/Z-order that pays on the scan path closes the point-lookup gap;
  pick the regime your queries live in rather than treating "the lake can't do needles" as a property of
  the format (Tier B, single host; the BM25 full-text half of the index's home turf is not yet measured).
- The **query engine can return a silently wrong answer**, so a cross-engine answer-equality check is a
  required control, not ceremony, and it belongs in CI because the failure is *version-bound and moving*.
  Two Parquet readers were caught returning a fast, confident, wrong answer under the high-cardinality,
  small-row-group structure security telemetry actually has (the conditions that build per-row-group bloom
  filters and a large string dictionary); on a tiny clean test corpus neither fires, which is why the
  check has to run against realistic data. One of the two (chDB's bloom-pushdown undercount) was *fixed by
  a point release* — wrong on 4.1.8, correct on 4.1.9 — while the other (fastparquet mis-decoding
  DuckDB's `PLAIN_DICTIONARY` strings) is still wrong on the latest version. A bug that a point release
  fixes is a bug a future point release can reintroduce, so the principle is that answer-equality is a
  standing CI gate pinned to the library versions under test, not a one-time bake-off you trust forever.

## 5. Data architecture — the open substrate, tiered, under one contract

The deconstructed-database / open-format substrate, temperature-tiered (virtual hot, catalog warm,
materialized cold) under one read contract. The principle is that the substrate stays open and verifiable,
with the honest caveat that "the engine is indifferent to the backend" holds for most query shapes but not
unconditionally — the read path can still leak through on the heaviest scans, and at the other extreme on the
random high-cardinality point lookup, where the answer depends on whether the table is sorted/clustered on the
looked-up columns (the Category 4 layout-choice caveat). The tiering decision and the sort/cluster decision
are how you keep that caveat from biting: tier by temperature and lay each tier out for the regime its queries
live in, rather than assuming the open format reads the same under every query shape.

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
