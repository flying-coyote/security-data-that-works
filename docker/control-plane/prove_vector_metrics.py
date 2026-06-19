"""Proof for the Vector throughput parser (Layer-2 honest counters).

Fixture-based (no container needed) so it runs in CI; the live end-to-end scrape is
exercised separately against a running Vector. Exit 0 = every assertion held.
"""
from __future__ import annotations

import sys

import vector_metrics as vm

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


# Realistic exposition: real data components + Vector's own plumbing (internal_metrics
# source, prometheus_exporter sink) + the optional per-sample timestamp Vector emits.
FIXTURE = """# HELP vector_component_received_events_total Total received.
# TYPE vector_component_received_events_total counter
vector_component_received_events_total{component_id="raw",component_kind="source",component_type="file",host="h"} 8 1781847618332
vector_component_received_events_total{component_id="ocsf",component_kind="transform",component_type="remap",host="h"} 8 1781847618332
vector_component_received_events_total{component_id="internal_metrics",component_kind="source",component_type="internal_metrics",host="h"} 999 1781847618332
vector_component_sent_events_total{component_id="console",component_kind="sink",component_type="console",host="h"} 8 1781847618332
vector_component_sent_events_total{component_id="metrics",component_kind="sink",component_type="prometheus_exporter",host="h"} 777 1781847618332
vector_component_errors_total{component_id="ocsf",component_kind="transform",component_type="remap",host="h"} 2 1781847618332
"""


def main():
    print("parser honesty")
    r = vm.parse_counts(FIXTURE)
    check("parses to (in, out, errors)", r == (8, 8, 2))
    ein, eout, errs = r
    check("internal_metrics SOURCE (999) excluded from events-in", ein == 8)
    check("prometheus_exporter SINK (777) excluded from events-out", eout == 8)
    check("transform-kind received not counted as ingest", ein == 8)  # ocsf transform 8 not added
    check("errors summed", errs == 2)

    print("value parsing")
    no_ts = 'vector_component_sent_events_total{component_id="s",component_kind="sink",component_type="console"} 42\n'
    check("value parses with no trailing timestamp", vm.parse_counts(no_ts) == (0, 42, 0))
    sci = 'vector_component_received_events_total{component_id="x",component_kind="source",component_type="file"} 1.5e1 123\n'
    check("scientific-notation value tolerated", vm.parse_counts(sci) == (15, 0, 0))

    print("unmeasured, never faked")
    check("empty text -> None", vm.parse_counts("") is None)
    check("comments only -> None", vm.parse_counts("# HELP foo\n# TYPE foo counter\n") is None)
    check("non-vector metrics -> None", vm.parse_counts('go_goroutines{x="1"} 5\n') is None)
    check("failed scrape (bad url) -> None", vm.scrape_counts("http://127.0.0.1:1/metrics", timeout=0.2) is None)

    print()
    if _failures:
        print(f"\033[91m{len(_failures)} FAILED:\033[0m " + "; ".join(_failures))
        sys.exit(1)
    print("\033[92mall vector-metrics parser assertions held\033[0m")


if __name__ == "__main__":
    main()
