"""Bench-Lab registry — the inventory of SDW Lab benchmarks plus the well-formedness
adapters that gate each run.

Pure data + pure functions, STDLIB-ONLY (this module is imported by bench_lab.py, which
runs under the HOST python3 — a python that lacks pyiceberg/duckdb/chdb). The actual
benches are shelled out to the lab venv by bench_lab.py; nothing here imports a heavy
dependency or runs a subprocess.

The gate is MECHANICAL WELL-FORMEDNESS, not scientific promotion: an adapter answers
"did this bench produce a structurally complete result that didn't contradict its own
correctness/determinism invariants?", and nothing more. Promotion of a clean run to
hypothesis evidence is a separate human gate (karen-evaluator -> hypothesis-validator ->
contradiction-detector). A tier-2/3 timing result on a non-power-planned host is
invalid-environment, not a result.
"""
from __future__ import annotations

LAB_ROOT = "/home/USER/sdw-lab-benchmarks"
LAB_VENV_PYTHON = LAB_ROOT + "/.venv/bin/python"
CV_THRESHOLD_PCT = 5.0


# name -> spec. Each spec:
#   tier     1 (pure host, no network) | 2 (timing-sensitive / live local service) | 3 (needs the compose stack)
#   dir      bench sub-directory under LAB_ROOT
#   entry    argv AFTER the python interpreter (e.g. ["run.py"] or ["timed_run.py"])
#   results  path to results.json relative to dir, or None (some benches write a top-level RESULTS.md only)
#   adapter  which well-formedness gate to apply: "default" | "determinism" | "clickhouse_vs_duckdb"
#   runnable True if bench_lab.py may shell it out unattended (tier-3 needs the docker stack -> False)
BENCHES = {
    # ----- TIER 1 — pure host, no network -----
    "flattening-fidelity":            {"tier": 1, "dir": "flattening-fidelity",            "entry": ["run.py"],                "results": "results/results.json", "adapter": "determinism", "runnable": True},
    "ocsf-mapping-fidelity":          {"tier": 1, "dir": "ocsf-mapping-fidelity",          "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "sigma-portability":              {"tier": 1, "dir": "sigma-portability",              "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-deterministic-mapper":      {"tier": 1, "dir": "ocsf-deterministic-mapper",      "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-parquet-determinism":       {"tier": 1, "dir": "ocsf-parquet-determinism",       "entry": ["determinism_probe.py"], "results": None,                   "adapter": "determinism", "runnable": True},
    "parquet-checksum-integrity":     {"tier": 1, "dir": "parquet-checksum-integrity",     "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "parquet-library-matrix":         {"tier": 1, "dir": "parquet-library-matrix",         "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "parquet-determinism-encryption": {"tier": 1, "dir": "parquet-determinism-encryption", "entry": ["run.py"],                "results": "results/results.json", "adapter": "simd_determinism", "runnable": True},
    "ocsf-pruning-correctness":       {"tier": 1, "dir": "ocsf-pruning-correctness",       "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-temporal-null-coercion":    {"tier": 1, "dir": "ocsf-temporal-null-coercion",    "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-nested-type-fidelity":      {"tier": 1, "dir": "ocsf-nested-type-fidelity",      "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-zstd-dictionary":           {"tier": 1, "dir": "ocsf-zstd-dictionary",           "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-write-contract":            {"tier": 1, "dir": "ocsf-write-contract",            "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-write-inlining":            {"tier": 1, "dir": "ocsf-write-inlining",            "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-streaming-cadence":         {"tier": 1, "dir": "ocsf-streaming-cadence",         "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-iceberg-metadata":          {"tier": 1, "dir": "ocsf-iceberg-metadata",          "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-format-planning":           {"tier": 1, "dir": "ocsf-format-planning",           "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "iceberg-compaction":             {"tier": 1, "dir": "iceberg-compaction",             "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-vortex-format":             {"tier": 1, "dir": "ocsf-vortex-format",             "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-zorder-pruning":            {"tier": 1, "dir": "ocsf-zorder-pruning",            "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-storage-endurance":         {"tier": 1, "dir": "ocsf-storage-endurance",         "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-rls-overhead":              {"tier": 1, "dir": "ocsf-rls-overhead",              "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-mv-acceleration":           {"tier": 1, "dir": "ocsf-mv-acceleration",           "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-data-health":               {"tier": 1, "dir": "ocsf-data-health",               "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "bench-a-context-collapse":       {"tier": 1, "dir": "bench-a-context-collapse",       "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-context-collapse-apt29":    {"tier": 1, "dir": "ocsf-context-collapse-apt29",    "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-fsi-compliance":            {"tier": 1, "dir": "ocsf-fsi-compliance",            "entry": ["timed_run.py"],          "results": "results/results.json", "adapter": "default",     "runnable": True},
    "spec-vs-emitted-integrity":      {"tier": 1, "dir": "spec-vs-emitted-integrity",      "entry": ["spec_vs_emitted.py"],    "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-sigma-detection":           {"tier": 1, "dir": "ocsf-sigma-detection",           "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    # scores pre-emitted files via `score.py --tool <name>`; needs per-tool args, so not auto-runnable here.
    "pipeline-normalization-fidelity": {"tier": 1, "dir": "pipeline-normalization-fidelity", "entry": ["score.py"],           "results": "results/results.json", "adapter": "default",     "runnable": False,
                                        "note": "needs per-tool args; not auto-runnable"},
    "ocsf-arrow-transport":           {"tier": 1, "dir": "ocsf-arrow-transport",           "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-marimo-hunt":               {"tier": 1, "dir": "ocsf-marimo-hunt",               "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},

    # ----- TIER 2 — timing-sensitive / live local service -----
    "clickhouse-vs-duckdb":           {"tier": 2, "dir": "clickhouse-vs-duckdb",           "entry": ["run.py"],                "results": "results/results.json", "adapter": "clickhouse_vs_duckdb", "runnable": True},
    "ocsf-read-scan":                 {"tier": 2, "dir": "ocsf-read-scan",                 "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "edr-two-regime":                 {"tier": 2, "dir": "edr-two-regime",                 "entry": ["edr_two_regime.py"],     "results": "results/results.json", "adapter": "default",     "runnable": True},
    "text-search-regex":              {"tier": 2, "dir": "text-search-regex",              "entry": ["synth_text_bench.py"],   "results": "results/results.json", "adapter": "default",     "runnable": True},
    "duckdb-edge-floor":              {"tier": 2, "dir": "duckdb-edge-floor",              "entry": ["edge_analytics_floor.py"], "results": "results/results.json", "adapter": "default",   "runnable": True},
    "cost-to-serve-retention":        {"tier": 2, "dir": "cost-to-serve-retention",        "entry": ["measure.py"],            "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-catalog-contention":        {"tier": 2, "dir": "ocsf-catalog-contention",        "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-airgap-agent":              {"tier": 2, "dir": "ocsf-airgap-agent",              "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-mapping-oracle":            {"tier": 2, "dir": "ocsf-mapping-oracle",            "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-nl2sql-silenterror":        {"tier": 2, "dir": "ocsf-nl2sql-silenterror",        "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "ocsf-semantic-query":            {"tier": 2, "dir": "ocsf-semantic-query",            "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": True},
    "polaris-catalog-dryrun":         {"tier": 2, "dir": "polaris-catalog-dryrun",         "entry": ["data_plane.py"],         "results": "results/results.json", "adapter": "default",     "runnable": True},

    # ----- TIER 3 — need the docker compose stack — NONE auto-runnable -----
    "workload-interference":          {"tier": 3, "dir": "workload-interference",          "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": False},
    "sdpp-ingest-throughput":         {"tier": 3, "dir": "sdpp-ingest-throughput",         "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": False},
    "engine-join-specialization":     {"tier": 3, "dir": "engine-join-specialization",     "entry": ["run_bench.py"],          "results": "results/results.json", "adapter": "default",     "runnable": False},
    "deterministic-routing-sim":      {"tier": 3, "dir": "deterministic-routing-sim",      "entry": ["route_sim.py"],          "results": "results/results.json", "adapter": "default",     "runnable": False},
    "concurrency-multiuser":          {"tier": 3, "dir": "concurrency-multiuser",          "entry": ["run.py"],                "results": "results/results.json", "adapter": "default",     "runnable": False},
    "soc-query-shapes":               {"tier": 3, "dir": "soc-query-shapes",               "entry": ["soc_shapes_bench.py"],   "results": "results/results.json", "adapter": "default",     "runnable": False},
    "zeek-flagship-rerun":            {"tier": 3, "dir": "zeek-flagship-rerun",            "entry": ["run_bench.py"],          "results": "results/results.json", "adapter": "default",     "runnable": False},
    "mv-rewrite-freshness":           {"tier": 3, "dir": "mv-rewrite-freshness",           "entry": ["starrocks_freshness.py"], "results": "results/results.json", "adapter": "default",    "runnable": False},
}


# TIERS partitions BENCHES — derived, never hand-maintained, so it can't drift.
TIERS = {1: [], 2: [], 3: []}
for _name, _spec in BENCHES.items():
    TIERS[_spec["tier"]].append(_name)
for _t in TIERS:
    TIERS[_t].sort()


# ---------------------------------------------------------------------------
# Well-formedness adapters. Each: (results, *, exit_code, has_results_md) -> (verdict, notes)
# verdict in {"pass", "fail", "invalid-environment"}.
# ---------------------------------------------------------------------------
def default_adapter(results, *, exit_code, has_results_md):
    if exit_code != 0:
        return ("fail", f"non-zero exit ({exit_code})")
    if results is None:
        return ("fail", "no results.json produced")
    if "evidence_tier" not in results:
        return ("fail", "results.json missing evidence_tier")
    if not has_results_md:
        return ("fail", "no RESULTS.md produced")
    if results.get("determinism_verified") is False:
        return ("fail", "determinism_verified=false")
    return ("pass", "well-formed: exit 0, results.json + RESULTS.md present, evidence_tier set")


def determinism_adapter(results, *, exit_code, has_results_md):
    # Stricter: determinism MUST be present and true (these benches exist to prove determinism).
    base = default_adapter(results, exit_code=exit_code, has_results_md=has_results_md)
    if base[0] != "pass":
        return base
    if results.get("determinism_verified") is not True:
        return ("fail", "determinism not verified (determinism_verified missing or not true)")
    return ("pass", "well-formed + determinism_verified=true")


def simd_determinism_adapter(results, *, exit_code, has_results_md):
    # parquet-determinism-encryption proves determinism via SIMD byte-identity, reported
    # nested under armA_simd_determinism.byte_identical_across_levels rather than a top-level
    # determinism_verified flag. Same strictness as determinism_adapter, different field.
    base = default_adapter(results, exit_code=exit_code, has_results_md=has_results_md)
    if base[0] != "pass":
        return base
    simd = (results or {}).get("armA_simd_determinism") or {}
    if simd.get("byte_identical_across_levels") is not True:
        return ("fail", "SIMD determinism not verified "
                        "(armA_simd_determinism.byte_identical_across_levels not true)")
    return ("pass", "well-formed + SIMD byte-identical across levels")


def clickhouse_vs_duckdb_adapter(results, *, exit_code, has_results_md):
    base = default_adapter(results, exit_code=exit_code, has_results_md=has_results_md)
    if base[0] != "pass":
        return base
    if results.get("answers_agree_all") is False:
        return ("fail", f"answers_agree_all=false (correctness bug; do not publish): {results.get('disagreements')}")
    if results.get("corpus_deterministic") is False:
        return ("fail", "corpus_deterministic=false (non-reproducible corpus)")
    cvs = _collect_cvs(results)
    if cvs and max(cvs) > CV_THRESHOLD_PCT:
        return ("invalid-environment",
                f"max cv_pct {max(cvs):.1f} > {CV_THRESHOLD_PCT} — noisy host / no High-Performance power plan; "
                "re-run, do not trust timing")
    return ("pass", f"well-formed, answers agree, max cv_pct {max(cvs):.1f}" if cvs
            else "well-formed, answers agree")


ADAPTERS = {
    "default": default_adapter,
    "determinism": determinism_adapter,
    "simd_determinism": simd_determinism_adapter,
    "clickhouse_vs_duckdb": clickhouse_vs_duckdb_adapter,
}


def _collect_cvs(results):
    """Walk the real clickhouse-vs-duckdb nested shape defensively and return every
    cv_pct float found. Real path:
        results["scales"] (list)
          -> each ["configs"] (dict config-name -> obj)
            -> each ["queries"] (list)
              -> each query ["duckdb"] / ["clickhouse"] (dict) -> ["cv_pct"]
    Tolerant of missing keys / wrong types — skips, never raises, returns [] on {}.
    """
    cvs = []
    if not isinstance(results, dict):
        return cvs
    scales = results.get("scales")
    if not isinstance(scales, list):
        return cvs
    for scale in scales:
        if not isinstance(scale, dict):
            continue
        configs = scale.get("configs")
        if not isinstance(configs, dict):
            continue
        for cfg in configs.values():
            if not isinstance(cfg, dict):
                continue
            queries = cfg.get("queries")
            if not isinstance(queries, list):
                continue
            for q in queries:
                if not isinstance(q, dict):
                    continue
                for engine in ("duckdb", "clickhouse"):
                    eng = q.get(engine)
                    if not isinstance(eng, dict):
                        continue
                    cv = eng.get("cv_pct")
                    if isinstance(cv, bool):  # bool is an int subclass; exclude
                        continue
                    if isinstance(cv, (int, float)):
                        cvs.append(float(cv))
    return cvs
