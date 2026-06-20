"""Proof that the constraint-first filter encodes the book's hard rules.

constraint_filter.py translates Ch3's "constraints override technical merit" into a
pure function over the open-stack component catalog. This harness asserts the hard
disqualifications, the favor/caution signals, and the disqualify > caution > favor
precedence — the part of the funnel that does the Tier-1 elimination.

Run:  python3 prove_constraint_filter.py     (exit 0 = every assertion held)
Pure stdlib; no catalog, no stack.
"""
from __future__ import annotations

import sys

import constraint_filter as cf

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def v(code, selection):
    return cf.verdict_for(code, selection)["verdict"]


def main():
    print("\n=== neutral selection — nothing ruled out ===\n")
    neutral = {"deployment": "cloud_ok", "team": "t_3_5", "vendor": "open_first",
               "workload": "balanced", "compliance": [], "cost": "balanced"}
    rep0 = cf.evaluate(neutral, {"storage": ["aws_s3"], "query": ["clickhouse", "duckdb"]})
    check("no constraint declared → no picked verdicts", rep0["picked_verdicts"] == [])
    check("no constraint declared → catalog disqualifies nothing", rep0["catalog_disqualified"] == [])
    check("inert defaults are dropped (no active constraints)", rep0["active_constraints"] == [])

    print("\n=== deployment: on-prem / air-gap (C3 hard disqualification) ===\n")
    airgap = {"deployment": "on_prem_airgap"}
    check("air-gap disqualifies AWS S3", v("aws_s3", airgap) == "disqualify")
    check("air-gap disqualifies AWS Glue", v("aws_glue", airgap) == "disqualify")
    check("air-gap disqualifies Wasabi", v("wasabi", airgap) == "disqualify")
    check("air-gap favors Dell ECS", v("dell_ecs", airgap) == "favor")
    check("air-gap favors SeaweedFS", v("seaweedfs", airgap) == "favor")
    check("air-gap leaves Polaris neutral (no rule)", v("polaris", airgap) == "neutral")
    rep1 = cf.evaluate(airgap, {"storage": ["aws_s3"], "catalog": ["polaris"]})
    check("catalog-wide disqualified set is exactly {aws_glue, aws_s3, wasabi}",
          rep1["catalog_disqualified"] == ["aws_glue", "aws_s3", "wasabi"])
    check("picking AWS S3 under air-gap flags it disqualified", rep1["picked_disqualified"] == ["aws_s3"])
    check("summary warns about the disqualified pick", "picked a disqualified component" in rep1["summary_md"])

    print("\n=== workload mandates (Workload 1/2/5) ===\n")
    rt = {"workload": "real_time_detection"}
    check("real-time favors ClickHouse", v("clickhouse", rt) == "favor")
    check("real-time cautions DuckDB", v("duckdb", rt) == "caution")
    check("real-time cautions DataFusion (no streaming engine here)", v("datafusion", rt) == "caution")
    th = {"workload": "threat_hunting"}
    check("threat-hunting favors Trino", v("trino", th) == "favor")
    check("threat-hunting favors StarRocks", v("starrocks", th) == "favor")
    check("threat-hunting cautions DuckDB (10-analyst ceiling)", v("duckdb", th) == "caution")
    pr = {"workload": "pipeline_routing"}
    check("pipeline-routing favors Cribl", v("cribl", pr) == "favor")
    check("pipeline-routing favors Tenzir", v("tenzir", pr) == "favor")
    check("pipeline-routing cautions Fluent Bit", v("fluentbit", pr) == "caution")

    print("\n=== compliance (Workload 4) ===\n")
    imm = {"compliance": ["immutable_audit"]}
    check("immutable-audit cautions ClickHouse (DELETE/MergeTree)", v("clickhouse", imm) == "caution")
    check("immutable-audit favors OCSF (structured, lossless)", v("ocsf", imm) == "favor")
    check("immutable-audit cautions CEF (flat/lossy)", v("cef", imm) == "caution")
    multi = {"compliance": ["immutable_audit", "long_retention_queryable"]}
    check("multi-select compliance handled (long-retention favors DataFusion)", v("datafusion", multi) == "favor")

    print("\n=== vendor posture (C4) ===\n")
    low = {"vendor": "low_oss_tolerance"}
    check("low-OSS-tolerance cautions Trino", v("trino", low) == "caution")
    check("low-OSS-tolerance favors Cribl (commercial)", v("cribl", low) == "favor")
    aws = {"vendor": "aws_committed"}
    check("AWS-committed favors AWS Glue", v("aws_glue", aws) == "favor")

    print("\n=== precedence: disqualify > caution > favor ===\n")
    # AWS S3 is disqualified by air-gap AND favored by AWS-committed -> disqualify wins.
    conflict_d = {"deployment": "on_prem_airgap", "vendor": "aws_committed"}
    check("disqualify beats favor on the same component", v("aws_s3", conflict_d) == "disqualify")
    # ClickHouse is favored by threat-hunting AND cautioned by immutable-audit -> caution wins.
    conflict_c = {"workload": "threat_hunting", "compliance": ["immutable_audit"]}
    check("caution beats favor on the same component", v("clickhouse", conflict_c) == "caution")
    # The favored verdict still carries a reason (non-empty).
    check("a favored verdict carries a book-cited reason",
          bool(cf.verdict_for("trino", th)["reasons"]))

    print("\n=== UI label<->code helpers ===\n")
    check("option_labels returns the deployment labels",
          "On-prem / air-gapped" in cf.option_labels("deployment"))
    check("code_for_label round-trips", cf.code_for_label("deployment", "On-prem / air-gapped") == "on_prem_airgap")
    check("default_label resolves for a single-select", cf.default_label("deployment") == "Cloud is fine")

    print("\n=== funnel (Ch3 reduction over the catalog) ===\n")
    _cats = {"storage": ["seaweedfs", "minio", "aws_s3", "wasabi", "dell_ecs"],
             "query": ["datafusion", "clickhouse", "starrocks", "dremio", "duckdb", "trino"]}
    f_air = cf.funnel({"deployment": "on_prem_airgap"}, _cats)
    check("air-gap narrows storage from 5 to 3 reachable (drops aws_s3, wasabi)",
          f_air["storage"]["total"] == 5 and f_air["storage"]["reachable"] == 3)
    check("disqualified storage is gone from the reachable order",
          all(code not in {"aws_s3", "wasabi"} for code, _v in f_air["storage"]["order"]))
    f_th = cf.funnel({"workload": "threat_hunting"}, _cats)
    check("threat-hunting disqualifies no engine (6 of 6 reachable)", f_th["query"]["reachable"] == 6)
    check("favored sorts ahead of cautioned in the query order",
          f_th["query"]["order"][0][1] == "favor" and f_th["query"]["order"][-1][1] == "caution")

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mAll constraint-filter assertions held — the book's Tier-1 rules are encoded.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
