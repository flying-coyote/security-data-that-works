"""Proof that the cost advisor reproduces the cost-to-serve-retention lab numbers.

The published essay's cost table (1 TB/day, AWS us-east-1 list) is the oracle:
30d index $1,200 vs warm $81 (~14.8x); 7y ~$95k/mo gap; cold ~96.7x. This asserts the
advisor lands on those within rounding.

Run:  python3 prove_cost_advisor.py     (exit 0 = every assertion held)
Pure stdlib.
"""
from __future__ import annotations

import os
import sys

import cost_advisor as ca

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def near(a, b, tol=0.03):
    return abs(a - b) <= tol * max(abs(b), 1.0)


def main():
    print("\n=== 1 TB/day, 30 days (essay reference row) ===\n")
    e30 = ca.estimate(1, 30)
    check(f"hot index ~ $1,200/mo (got ${e30['index_hot_monthly']:,.0f})", near(e30["index_hot_monthly"], 1200, 0.02))
    check(f"warm lakehouse ~ $81/mo (got ${e30['warm_lakehouse_monthly']:,.0f})", near(e30["warm_lakehouse_monthly"], 81, 0.03))
    check(f"warm multiple ~ 14.8x (got {e30['warm_multiple']:.2f})", near(e30["warm_multiple"], 14.8, 0.02))
    check(f"cold multiple ~ 96.7x (got {e30['cold_multiple']:.1f})", near(e30["cold_multiple"], 96.7, 0.02))

    print("\n=== 1 TB/day, 7 years (the existential gap) ===\n")
    e7y = ca.estimate(1, 2555)
    check(f"7y monthly gap ~ $95k (got ${e7y['monthly_gap']:,.0f})", near(e7y["monthly_gap"], 95000, 0.03))
    check("the multiple is retention-invariant (linear in days)",
          near(e7y["warm_multiple"], e30["warm_multiple"], 0.001))

    print("\n=== scaling + edge cases ===\n")
    e10 = ca.estimate(10, 30)
    check("10x volume scales monthly cost 10x", near(e10["warm_lakehouse_monthly"], 10 * e30["warm_lakehouse_monthly"], 0.001))
    z = ca.estimate(0, 30)
    check("zero volume → zero cost, no divide-by-zero", z["warm_lakehouse_monthly"] == 0 and z["warm_multiple"] == 0)
    check("summary_md handles the zero case", "Set a non-zero" in ca.summary_md(z))
    check("summary_md renders the reference read", "14.8x" in ca.summary_md(e30) or "14.8" in ca.summary_md(e30))

    print("\n=== CF-COST: per-source event weight + retention presets + named-SIEM list anchor ===\n")
    import config_preview as _cpv
    import json as _json
    _zpath = os.path.join(_cpv._DEFAULT_SAMPLES, "zeek_conn.sample.tsv")
    _zeek_n = len(_cpv._read_zeek_tsv(_zpath))
    zbe = ca.sample_bytes_per_event("zeek")
    check("zeek raw bytes/event == file_size / n_events (measured, not guessed)",
          near(zbe["raw_bytes_per_event"], os.path.getsize(_zpath) / _zeek_n, 1e-9))
    check("zeek OCSF bytes/event is populated and positive", zbe["ocsf_bytes_per_event"] > 0)
    check("unknown source degrades to {error}, no raise", "error" in ca.sample_bytes_per_event("nope"))
    check("FINRA_7yr preset == 2555 days", ca.RETENTION_PRESETS["FINRA_7yr"] == 2555)
    check("estimate_per_source annotates the per-source event weight",
          ca.estimate_per_source("zeek", 1, 365)["per_source"]["raw_bytes_per_event"] > 0)

    p = ca.NAMED_SIEM_LIST_PRICE
    check("Splunk price is dated 2024-04-23", p["published"] == "2024-04-23")
    check("Splunk price sources G-Cloud 14", "G-Cloud 14" in p["source"])
    check("Splunk price vendor is Splunk", p["vendor"] == "Splunk")
    check("Splunk price is labeled a list price (never a score)", "list price" in p["basis"])
    cmp = ca.named_siem_compare(ca.estimate(2, 365))
    check("named_siem_compare carries provenance + basis='list price'",
          cmp["basis"] == "list price" and cmp["provenance"]["published"] == "2024-04-23")
    check("Splunk list scales with ingest volume (2 TB/day = 2000 GB/day)",
          near(cmp["ingest_gb_day"], 2000.0, 1e-9))

    _e = ca.estimate(1, 30)
    check("estimate carries NO compute/license/egress/labor key (storage floor only)",
          not ({"compute_monthly", "license_monthly", "egress_monthly", "labor_monthly"} & set(_e.keys())))
    _sps = ca.summary_md_per_source(ca.estimate_per_source("zeek", 1, 30))
    check("summary_md_per_source keeps the storage-floor-not-TCO disclaimer",
          "Storage floor" in _sps and "not a TCO" in _sps)
    # Firewall: the price surface must carry list prices only — never a 0-5 Matrix-style
    # score. Every numeric provenance value is a $/GB-day list price (hundreds), so none
    # falls in the 0-5 band a paid per-vendor score would occupy.
    _price_nums = [v for v in p.values() if isinstance(v, (int, float))]
    check("price provenance carries list prices only, no 0-5 Matrix-style score",
          bool(_price_nums) and all(v > 5 for v in _price_nums))

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mAll cost-advisor assertions held — reproduces the lab numbers.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
