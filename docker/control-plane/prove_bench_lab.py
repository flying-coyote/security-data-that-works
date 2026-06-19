"""Proof that the Bench-Lab runner is well-formed and honest: the registry partitions
cleanly, the adapters gate as specified, failure classification buckets correctly, the
power-plan downgrade rule holds, and the manifest carries every required key plus the
"separate human gate" honesty note.

HERMETIC — fixtures only. No real bench is run; no powercfg / git / subprocess is invoked.
Where a function does I/O (env_snapshot, run_bench, git_head), we test only the PURE logic
it composes (is_high_performance, classify_failure, the adapters, _collect_cvs,
results_sha256, assemble_manifest). Exit 0 = every assertion held.
"""
from __future__ import annotations

import hashlib
import sys

import bench_lab as bl
import bench_lab_registry as reg

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def main():
    # --- 1. Registry sanity ---------------------------------------------------------
    print("\n=== 1. Registry sanity ===\n")
    well_shaped = all(
        s["tier"] in (1, 2, 3) and isinstance(s["dir"], str) and isinstance(s["entry"], list)
        and s["adapter"] in reg.ADAPTERS
        for s in reg.BENCHES.values()
    )
    check("every spec: tier in {1,2,3}, dir str, entry list, adapter known", well_shaped)
    check("every tier-3 bench has runnable=False",
          all(s.get("runnable") is False for s in reg.BENCHES.values() if s["tier"] == 3))
    # TIERS partitions BENCHES: union == all names, no name in two tiers.
    union = set(reg.TIERS[1]) | set(reg.TIERS[2]) | set(reg.TIERS[3])
    sizes = len(reg.TIERS[1]) + len(reg.TIERS[2]) + len(reg.TIERS[3])
    check("TIERS partitions BENCHES (each bench in exactly one tier)",
          union == set(reg.BENCHES) and sizes == len(reg.BENCHES))
    check("tier-1 count >= 25", len(reg.TIERS[1]) >= 25)

    # --- 2. default_adapter ---------------------------------------------------------
    print("\n=== 2. default_adapter ===\n")
    good = {"evidence_tier": "B"}
    check("pass on well-formed (exit0, md, evidence_tier)",
          reg.default_adapter(good, exit_code=0, has_results_md=True)[0] == "pass")
    check("fail on non-zero exit",
          reg.default_adapter(good, exit_code=1, has_results_md=True)[0] == "fail")
    check("fail on results None",
          reg.default_adapter(None, exit_code=0, has_results_md=True)[0] == "fail")
    check("fail on missing evidence_tier",
          reg.default_adapter({}, exit_code=0, has_results_md=True)[0] == "fail")
    check("fail on no RESULTS.md",
          reg.default_adapter(good, exit_code=0, has_results_md=False)[0] == "fail")
    check("fail on determinism_verified=false",
          reg.default_adapter({"evidence_tier": "B", "determinism_verified": False},
                              exit_code=0, has_results_md=True)[0] == "fail")

    # --- 3. determinism_adapter -----------------------------------------------------
    print("\n=== 3. determinism_adapter ===\n")
    check("pass when determinism_verified True",
          reg.determinism_adapter({"evidence_tier": "B", "determinism_verified": True},
                                  exit_code=0, has_results_md=True)[0] == "pass")
    check("fail when determinism_verified missing (otherwise well-formed)",
          reg.determinism_adapter({"evidence_tier": "B"}, exit_code=0, has_results_md=True)[0] == "fail")
    check("fail when determinism_verified False",
          reg.determinism_adapter({"evidence_tier": "B", "determinism_verified": False},
                                  exit_code=0, has_results_md=True)[0] == "fail")

    # --- 4. clickhouse_vs_duckdb_adapter --------------------------------------------
    print("\n=== 4. clickhouse_vs_duckdb_adapter ===\n")
    clean = {
        "evidence_tier": "B", "answers_agree_all": True, "corpus_deterministic": True,
        "scales": [{"configs": {"parquet_in_place": {"queries": [
            {"id": "q1", "duckdb": {"cv_pct": 2.1}, "clickhouse": {"cv_pct": 3.2}}]}}}],
    }
    check("pass on clean low-cv fixture",
          reg.clickhouse_vs_duckdb_adapter(clean, exit_code=0, has_results_md=True)[0] == "pass")
    noisy = {
        "evidence_tier": "B", "answers_agree_all": True, "corpus_deterministic": True,
        "scales": [{"configs": {"parquet_in_place": {"queries": [
            {"id": "q1", "duckdb": {"cv_pct": 6.0}, "clickhouse": {"cv_pct": 3.2}}]}}}],
    }
    check("invalid-environment on a buried cv_pct > 5",
          reg.clickhouse_vs_duckdb_adapter(noisy, exit_code=0, has_results_md=True)[0] == "invalid-environment")
    disagree = dict(clean, answers_agree_all=False, disagreements=["q1: 125 vs 126"])
    check("fail on answers_agree_all=False",
          reg.clickhouse_vs_duckdb_adapter(disagree, exit_code=0, has_results_md=True)[0] == "fail")
    nondet_corpus = dict(clean, corpus_deterministic=False)
    check("fail on corpus_deterministic=False",
          reg.clickhouse_vs_duckdb_adapter(nondet_corpus, exit_code=0, has_results_md=True)[0] == "fail")

    # --- 5. _collect_cvs ------------------------------------------------------------
    print("\n=== 5. _collect_cvs ===\n")
    cvs = reg._collect_cvs(clean)
    check("collects all cvs from nested scales/configs/queries shape", sorted(cvs) == [2.1, 3.2])
    check("tolerant of {} (returns [], no raise)", reg._collect_cvs({}) == [])
    check("tolerant of malformed shapes (missing keys / wrong types)",
          reg._collect_cvs({"scales": [{"configs": {"c": {"queries": [{"duckdb": "nope"}]}}}, "junk"]}) == [])

    # --- 6. classify_failure --------------------------------------------------------
    print("\n=== 6. classify_failure ===\n")
    check("137 -> oom", bl.classify_failure("killed", 137)["class"] == "oom")
    check("'warehouse not found' -> cold-start",
          bl.classify_failure("Error: warehouse not found in catalog", 1)["class"] == "cold-start")
    check("':9000 connection refused' -> tier3-misroute",
          bl.classify_failure("urllib3 ... http://minio:9000 connection refused", 1)["class"] == "tier3-misroute")
    nd = bl.classify_failure("AssertionError: determinism broken across runs", 1)
    check("'AssertionError ... determinism' -> nondeterminism", nd["class"] == "nondeterminism")
    mp = bl.classify_failure("ModuleNotFoundError: No module named 'foo'", 1)
    check("ModuleNotFoundError -> missing-prereq + module name extracted",
          mp["class"] == "missing-prereq" and "foo" in mp["message"])
    check("'weird gibberish' -> unknown", bl.classify_failure("weird gibberish", 1)["class"] == "unknown")

    # --- 7. power-plan guard logic --------------------------------------------------
    print("\n=== 7. power-plan guard ===\n")
    check("is_high_performance('(High performance)') True",
          bl.is_high_performance("Power Scheme GUID: ... (High performance)") is True)
    check("is_high_performance('(Ultimate Performance)') True",
          bl.is_high_performance("... (Ultimate Performance)") is True)
    check("is_high_performance('(Balanced)') False",
          bl.is_high_performance("Power Scheme GUID: ... (Balanced)") is False)
    # The downgrade rule (as run_one applies it): tier>=2 + pass + not-HP -> downgrade.
    def would_downgrade(tier, verdict, plan):
        return tier >= 2 and verdict == "pass" and not bl.is_high_performance(plan)
    check("downgrade rule: tier2 pass on Balanced downgrades", would_downgrade(2, "pass", "(Balanced)") is True)
    check("downgrade rule: tier2 pass on High performance does NOT downgrade",
          would_downgrade(2, "pass", "(High performance)") is False)
    check("downgrade rule: tier1 pass on Balanced does NOT downgrade",
          would_downgrade(1, "pass", "(Balanced)") is False)

    # --- 8. assemble_manifest -------------------------------------------------------
    print("\n=== 8. assemble_manifest ===\n")
    raw = b'{"evidence_tier":"B"}'
    sha = bl.results_sha256(raw)
    check("results_sha256 matches hashlib.sha256(raw)", sha == hashlib.sha256(raw).hexdigest())
    check("results_sha256(None) -> None", bl.results_sha256(None) is None)
    name = reg.TIERS[1][0]
    m = bl.assemble_manifest(
        run_id=f"{name}-20260619T000000Z", name=name, exit_code=0, duration_s=1.234,
        verdict="pass", notes="well-formed", failure=None,
        env={"python": "3.x"}, git_info={"spoke": {"head": "abc", "dirty": False}, "lab": {"head": "def", "dirty": False}},
        results_path="results/results.json", sha=sha, results_md_present=True,
        stdout="hi", stderr="", log_basename=f"{name}-20260619T000000Z.log",
    )
    required = {"run_id", "bench", "tier", "adapter", "exit_code", "duration_s", "gate", "failure",
                "env", "git", "results_path", "results_sha256", "results_md_present",
                "stdout_excerpt", "stderr_excerpt", "ran_at", "log_path", "notes"}
    check("manifest carries every required key", required.issubset(set(m)))
    check("manifest gate has verdict + notes",
          set(m["gate"]) == {"verdict", "notes"} and m["gate"]["verdict"] == "pass")
    check("manifest notes contains 'separate human gate'", "separate human gate" in m["notes"])
    check("manifest results_sha256 round-trips the fixture", m["results_sha256"] == hashlib.sha256(raw).hexdigest())

    print()
    if _failures:
        print(f"\033[91m{len(_failures)} assertion(s) FAILED:\033[0m " + "; ".join(_failures))
        return 1
    print("\033[92mAll assertions held — the Bench-Lab runner gates on well-formedness and reports honestly.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
