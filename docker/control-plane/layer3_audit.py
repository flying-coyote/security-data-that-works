"""Layer 3 data-quality audit for the MOAr console — real measured checks.

This is the module that turns the gate's Layer-3 row from a hardcoded
`unmeasured` into a measured pass/fail. It runs against a deployed Iceberg table
(a loaded PyIceberg `Table`) and, for the orphan check, a listing of the object
store under that table's data prefix.

The honesty floor from the design governs every check here: a check either does
real work and returns a number, or it returns status `"unwired"` and is never
counted as a pass. Two checks have no machinery yet and say so — Parquet CRC
bit-flip verification (no per-file CRC recompute path) and the DuckLake tombstone
resurrection check (#1215, which is a DuckLake-on-Postgres failure mode that
doesn't even apply to the Iceberg/Polaris stack the console deploys). They stay
`unwired` rather than fake a green.

The four measured checks:
  - freshness         — age of the current snapshot vs a max-lag threshold
  - small_files       — count of data files under the compaction threshold (128MB)
  - orphans           — data-file basenames in the store not referenced by the
                        current snapshot's manifests (failed-write / leaked files)
  - schema_conformance- expected (required) columns present + no NULLs in any
                        Iceberg-required field

The module is deliberately catalog- and store-agnostic: it takes a PyIceberg
`Table` and a set of parquet basenames observed in the store, so the identical
code serves the live Polaris + SeaweedFS path (basenames via boto3) and a local
SqlCatalog proof harness (basenames via a filesystem walk). Comparing by basename
sidesteps `s3://` vs `file://` path differences — Iceberg data filenames are
UUID-unique, so a basename set is a sound identity for "is this file referenced."

Tier-B, single-host semantics: the required-NULL check reads the manifest
`null_value_counts` rather than scanning rows, so it never pulls telemetry into
memory; the small-file threshold is a compaction-pressure heuristic, not a tuned
production policy.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

# Iceberg's small-file / compaction-pressure threshold. Files under this are
# candidates for compaction; too many of them is the "small-file problem."
DEFAULT_MIN_FILE_BYTES = 128 * 1024 * 1024  # 128 MB
# How many sub-threshold files we tolerate before flagging compaction pressure.
DEFAULT_MAX_SMALL_FILES = 8
# How stale the current snapshot may be before freshness fails (seconds).
DEFAULT_MAX_FRESHNESS_SECONDS = 3600


@dataclass(frozen=True)
class CheckResult:
    """One Layer-3 check outcome. `status` is pass | fail | unwired | unmeasured.

    `unwired`   = no machinery exists for this check (never a pass).
    `unmeasured`= machinery exists but couldn't run (no table, store unlistable).
    """

    name: str
    status: str
    detail: str
    measured: dict = field(default_factory=dict)


def _basename(path: str) -> str:
    return os.path.basename(path.rstrip("/"))


# --------------------------------------------------------------------------- #
# Object-store listers (one per store; each returns parquet basenames or None).
# None means "could not list" — the orphan check then reports unmeasured, never
# a fabricated pass.
# --------------------------------------------------------------------------- #
def list_local_parquet_basenames(warehouse_dir: str) -> set[str] | None:
    """Walk a local FileIO warehouse for *.parquet basenames (proof harness /
    any filesystem-backed catalog)."""
    try:
        out: set[str] = set()
        for root, _dirs, files in os.walk(warehouse_dir):
            for f in files:
                if f.endswith(".parquet"):
                    out.add(f)
        return out
    except OSError:
        return None


def list_s3_parquet_basenames(endpoint, bucket, prefix, access_key, secret_key) -> set[str] | None:
    """List parquet basenames under an S3/SeaweedFS prefix via boto3 (live
    console path). Returns None on any failure so the orphan check degrades to
    unmeasured rather than bluffing."""
    try:
        import boto3
        from botocore.config import Config

        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name="us-east-1",
            config=Config(s3={"addressing_style": "path"}, connect_timeout=2, read_timeout=5, retries={"max_attempts": 1}),
        )
        out: set[str] = set()
        token = None
        while True:
            kw = {"Bucket": bucket, "Prefix": prefix}
            if token:
                kw["ContinuationToken"] = token
            resp = s3.list_objects_v2(**kw)
            for obj in resp.get("Contents", []):
                if obj["Key"].endswith(".parquet"):
                    out.add(_basename(obj["Key"]))
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")
        return out
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# The four measured checks. Each takes already-extracted inputs so it is unit-
# testable without a live stack.
# --------------------------------------------------------------------------- #
def check_freshness(snapshot_ms, now_ms, max_seconds=DEFAULT_MAX_FRESHNESS_SECONDS) -> CheckResult:
    if snapshot_ms is None:
        return CheckResult("freshness", "unmeasured", "No snapshot yet — table has never been written.")
    lag = max(0.0, (now_ms - snapshot_ms) / 1000.0)
    ok = lag <= max_seconds
    return CheckResult(
        "freshness",
        "pass" if ok else "fail",
        f"current snapshot is {lag:.0f}s old (threshold {max_seconds}s)",
        {"lag_seconds": round(lag, 1), "max_seconds": max_seconds},
    )


def check_small_files(file_sizes, min_bytes=DEFAULT_MIN_FILE_BYTES, max_small=DEFAULT_MAX_SMALL_FILES) -> CheckResult:
    total = len(file_sizes)
    if total == 0:
        return CheckResult("small_files", "unmeasured", "No data files to assess.")
    small = sum(1 for s in file_sizes if s is not None and s < min_bytes)
    ok = small <= max_small
    return CheckResult(
        "small_files",
        "pass" if ok else "fail",
        f"{small}/{total} files under {min_bytes // (1024 * 1024)}MB "
        f"(compaction-pressure threshold {max_small})",
        {"small_files": small, "total_files": total, "max_small": max_small},
    )


def check_orphans(referenced_basenames, store_basenames) -> CheckResult:
    if store_basenames is None:
        return CheckResult("orphans", "unmeasured", "Could not list the object store under the table prefix.")
    orphans = store_basenames - referenced_basenames
    ok = not orphans
    sample = ", ".join(sorted(orphans)[:3])
    return CheckResult(
        "orphans",
        "pass" if ok else "fail",
        f"{len(orphans)} parquet file(s) in the store not referenced by the current snapshot"
        + (f" (e.g. {sample})" if orphans else ""),
        {"orphan_count": len(orphans), "store_files": len(store_basenames), "referenced": len(referenced_basenames)},
    )


def check_schema_conformance(schema_field_names, required_field_names, required_null_violations,
                             expected_columns=None) -> CheckResult:
    """expected_columns: optional set the table must contain (e.g. an OCSF core
    set). required_field_names + required_null_violations: Iceberg-required fields
    and any of them carrying NULLs per the manifest counts."""
    present = set(schema_field_names)
    missing = set(expected_columns or set()) - present
    null_viol = sorted(required_null_violations)
    problems = []
    if missing:
        problems.append(f"missing expected column(s): {', '.join(sorted(missing))}")
    if null_viol:
        problems.append(f"NULLs in required field(s): {', '.join(null_viol)}")
    ok = not problems
    return CheckResult(
        "schema_conformance",
        "pass" if ok else "fail",
        ("schema conforms — "
         f"{len(present)} columns, {len(required_field_names)} required")
        if ok else "; ".join(problems),
        {"columns": len(present), "required": len(required_field_names),
         "missing": sorted(missing), "null_violations": null_viol},
    )


# --------------------------------------------------------------------------- #
# Extraction from a live PyIceberg table + the top-level audit.
# --------------------------------------------------------------------------- #
def _aggregate_required_null_violations(files_arrow, schema) -> list[str]:
    """Aggregate manifest null_value_counts across files and return the names of
    any Iceberg-required field that carries at least one NULL. Reads manifest
    stats, not rows, so no telemetry is loaded."""
    id_to_name = {f.field_id: f.name for f in schema.fields}
    required_ids = {f.field_id for f in schema.fields if f.required}
    if not required_ids or "null_value_counts" not in files_arrow.column_names:
        return []
    agg: dict[int, int] = {}
    for entry in files_arrow.column("null_value_counts").to_pylist():
        if entry is None:
            continue
        items = entry.items() if isinstance(entry, dict) else entry
        for fid, cnt in items:
            if fid in required_ids and cnt:
                agg[fid] = agg.get(fid, 0) + int(cnt)
    return [id_to_name.get(fid, str(fid)) for fid, cnt in agg.items() if cnt > 0]


def audit_table(table, *, store_basenames=None, now_ms=None, enabled=None,
                expected_columns=None, min_file_bytes=DEFAULT_MIN_FILE_BYTES,
                max_small_files=DEFAULT_MAX_SMALL_FILES,
                max_freshness_seconds=DEFAULT_MAX_FRESHNESS_SECONDS) -> dict:
    """Run the Layer-3 audit against a loaded PyIceberg table.

    `enabled` is a set of check names to run (the console's toggles); freshness
    always runs. `store_basenames` is the parquet-basename listing for the orphan
    check (None -> orphan unmeasured). `now_ms` defaults to wall-clock; the proof
    passes a fixed value for determinism.

    Returns {checks: [CheckResult...], status: pass|fail|unmeasured, ...}.
    """
    if now_ms is None:
        import datetime as _dt
        now_ms = int(_dt.datetime.now(_dt.timezone.utc).timestamp() * 1000)
    enabled = enabled if enabled is not None else {
        "freshness", "small_files", "orphans", "schema_conformance"}

    schema = table.schema()
    files_arrow = table.inspect.files()
    file_paths = files_arrow.column("file_path").to_pylist() if files_arrow.num_rows else []
    file_sizes = files_arrow.column("file_size_in_bytes").to_pylist() if files_arrow.num_rows else []
    referenced = {_basename(p) for p in file_paths}
    snap = table.current_snapshot()
    snap_ms = snap.timestamp_ms if snap else None

    results: list[CheckResult] = []

    # freshness — always on; it is the core data-health signal.
    results.append(check_freshness(snap_ms, now_ms, max_freshness_seconds))

    if "small_files" in enabled:
        results.append(check_small_files(file_sizes, min_file_bytes, max_small_files))
    if "orphans" in enabled:
        results.append(check_orphans(referenced, store_basenames))
    if "schema_conformance" in enabled:
        null_viol = _aggregate_required_null_violations(files_arrow, schema)
        results.append(check_schema_conformance(
            [f.name for f in schema.fields],
            [f.name for f in schema.fields if f.required],
            null_viol, expected_columns))

    # The two checks with no machinery — reported, never counted as a pass.
    if "crc" in enabled:
        results.append(CheckResult("crc", "unwired",
                                   "Parquet CRC bit-flip verification has no per-file recompute path yet."))
    if "tombstone" in enabled:
        results.append(CheckResult("tombstone", "unwired",
                                   "DuckLake tombstone resurrection (#1215) does not apply to the Iceberg/Polaris stack."))

    return {"checks": results, "status": layer3_status(results),
            "table": f"{'.'.join(table.name())}" if hasattr(table, "name") else "table",
            "now_ms": now_ms}


def layer3_status(results) -> str:
    """fail if any measured check fails; pass if at least one measured check ran
    and all measured checks pass; unmeasured if nothing measurable ran. `unwired`
    and `unmeasured` checks never make the layer pass and never fail it."""
    measured = [r for r in results if r.status in ("pass", "fail")]
    if any(r.status == "fail" for r in measured):
        return "fail"
    if measured:
        return "pass"
    return "unmeasured"
