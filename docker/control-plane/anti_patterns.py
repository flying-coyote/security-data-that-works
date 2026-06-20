"""Design anti-pattern guards — Appendix B made into pre-pick checks.

The book's anti-patterns catalog (Appendix B) lists design mistakes that cost
$200K-$4M. Several are detectable from the component selection alone, so the console
can flag them the way the data-health gate refuses to bluff green. This complements two
existing checks rather than duplicating them:
  - providers.compat_notes catches cross-component *incompatibilities* (don't pair X+Y),
  - constraint_filter catches *constraint* violations (your air-gap rules out X),
  - this module catches selection-level *design* anti-patterns (the shape is risky).

detect(selection) returns [(severity, title, body)] where severity is "warn" (a real
anti-pattern, rendered red) or "info" (an advisory). Bodies cite Appendix B. These are
advisories, not hard deploy blockers — the book says "avoid," not "forbidden."
"""
from __future__ import annotations

# Schemas that re-create vendor lock-in (transformation logic doesn't port across vendors).
_VENDOR_TIED_SCHEMA = {"splunk_cim": "Splunk CIM", "asim": "Sentinel ASIM"}
# Iceberg REST catalogs that preserve the open escape path.
_OPEN_CATALOGS = {"polaris", "nessie", "lakekeeper"}


def detect(selection) -> list[tuple]:
    """selection: {storage, catalog, schema: code; ingest, query: [codes]}.
    Returns [(severity, title, body)] for the design anti-patterns the picks trip."""
    storage = selection.get("storage")
    catalog = selection.get("catalog")
    schema = selection.get("schema")
    ingest = list(selection.get("ingest") or [])
    query = list(selection.get("query") or [])
    out: list[tuple] = []

    # 1. Multi-engine sprawl — "who is going to run four engines?"
    if len(query) >= 4:
        out.append((
            "warn", "Multi-engine sprawl",
            f"{len(query)} query engines selected. Each one is its own tuning, upgrade, and "
            "on-call surface, and the book's scored join bench found no SOC-shaped query "
            "exceeded 1.5s on any single engine. Lead with one engine over shared Iceberg and "
            "add a second only for a workload that genuinely demands it (Appendix B; "
            "single-front-engine).",
        ))

    # 2. Vendor-tied schema lock-in.
    if schema in _VENDOR_TIED_SCHEMA:
        out.append((
            "warn", "Vendor-tied schema lock-in",
            f"{_VENDOR_TIED_SCHEMA[schema]} re-creates the lock-in an open lakehouse is meant "
            "to escape: the normalization logic is vendor-specific and doesn't port. Prefer "
            "OCSF so detections and transforms travel across engines and vendors (Appendix B; "
            "vendor lock-in).",
        ))
    if schema == "cef":
        out.append((
            "warn", "Lossy schema (CEF)",
            "CEF is flat and lossy — nested event detail is dropped at parse time and cannot "
            "be reconstructed later. A structured standard (OCSF) keeps the detail forensics "
            "and audits need (Appendix B).",
        ))
    if schema == "raw":
        out.append((
            "info", "Parsing deferred to query time (Raw)",
            "Raw preserves the source exactly but defers all parsing and normalization to "
            "query time and to the analyst. Fine for cheap retention; every downstream query "
            "and detection then pays the parsing cost you skipped (Appendix B; flattening).",
        ))

    # 3. Cloud lock-in without a preserved exit.
    if storage == "aws_s3" and catalog == "aws_glue":
        out.append((
            "warn", "AWS-bound metadata (no preserved exit)",
            "AWS S3 + AWS Glue is a fully AWS-managed data plane. The open table format is the "
            "escape hatch, but a Glue-only catalog keeps the *metadata* AWS-bound, so leaving "
            "means re-registering every table. Keep an Iceberg REST catalog (Polaris / Nessie / "
            "Lakekeeper) in the design to preserve the exit (Appendix B; vendor lock-in).",
        ))

    # 4. Iceberg table maintenance unowned (the stack is always Iceberg via the catalog).
    if catalog:
        out.append((
            "info", "Iceberg maintenance has no owner",
            "None of the selected query engines runs Iceberg table maintenance on its own. "
            "Without scheduled compaction, snapshot expiration, and orphan-file cleanup, "
            "small files accumulate and reads slow over time — budget a maintenance job "
            "(Spark or a pyiceberg cron) as part of the deploy (Appendix B; Iceberg "
            "maintenance at scale).",
        ))

    # 5. No pipeline selected — incomplete (can't land data).
    if not ingest:
        out.append((
            "warn", "No ingest pipeline selected",
            "No pipeline is selected, so nothing routes or normalizes data into the lake. Pick "
            "at least one ingest component before deploying (Appendix B; incomplete pipeline).",
        ))

    return out
