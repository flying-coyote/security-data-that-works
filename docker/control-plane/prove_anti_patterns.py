"""Proof for the design anti-pattern guards (Appendix B).

Run:  python3 prove_anti_patterns.py     (exit 0 = every assertion held)
Pure stdlib.
"""
from __future__ import annotations

import sys

import anti_patterns as ap

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def titles(sel):
    return {t for _s, t, _b in ap.detect(sel)}


def warns(sel):
    return {t for s, t, _b in ap.detect(sel) if s == "warn"}


def main():
    # A clean, conventional open stack: SeaweedFS + Polaris + Vector + one engine + OCSF.
    clean = {"storage": "seaweedfs", "catalog": "polaris", "schema": "ocsf",
             "ingest": ["vector"], "query": ["datafusion"]}
    print("\n=== a conventional single-engine OCSF stack ===\n")
    _t = titles(clean)
    check("no sprawl / lock-in / lossy warnings on the clean stack", warns(clean) == set())
    check("but the Iceberg-maintenance advisory always fires", "Iceberg maintenance has no owner" in _t)

    print("\n=== multi-engine sprawl ===\n")
    sprawl = dict(clean, query=["datafusion", "trino", "clickhouse", "starrocks"])
    check("4 engines → sprawl warning", "Multi-engine sprawl" in warns(sprawl))
    three = dict(clean, query=["datafusion", "trino", "clickhouse"])
    check("3 engines → no sprawl warning (threshold is 4)", "Multi-engine sprawl" not in warns(three))

    print("\n=== schema lock-in / lossiness ===\n")
    check("Splunk CIM → vendor-tied lock-in warning",
          "Vendor-tied schema lock-in" in warns(dict(clean, schema="splunk_cim")))
    check("ASIM → vendor-tied lock-in warning",
          "Vendor-tied schema lock-in" in warns(dict(clean, schema="asim")))
    check("CEF → lossy-schema warning", "Lossy schema (CEF)" in warns(dict(clean, schema="cef")))
    check("Raw → parsing-deferred advisory (info, not warn)",
          "Parsing deferred to query time (Raw)" in titles(dict(clean, schema="raw"))
          and "Parsing deferred to query time (Raw)" not in warns(dict(clean, schema="raw")))
    check("OCSF → no schema warning", not any("schema" in t.lower() and "OCSF" not in t
                                              for t in warns(clean)))

    print("\n=== cloud lock-in without an exit ===\n")
    awsbound = dict(clean, storage="aws_s3", catalog="aws_glue")
    check("AWS S3 + AWS Glue → AWS-bound-metadata warning",
          "AWS-bound metadata (no preserved exit)" in warns(awsbound))
    check("AWS S3 + Polaris → no AWS-bound warning (exit preserved)",
          "AWS-bound metadata (no preserved exit)" not in warns(dict(clean, storage="aws_s3")))

    print("\n=== incomplete pipeline ===\n")
    check("no ingest selected → warning", "No ingest pipeline selected" in warns(dict(clean, ingest=[])))

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mAll anti-pattern assertions held.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
