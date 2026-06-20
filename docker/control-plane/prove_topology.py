"""Proof for the Land — pipeline topology builder.

Run:  python3 prove_topology.py     (exit 0 = every assertion held)
Pure stdlib (imports only `topology`, which imports `providers`; no marimo).
"""
from __future__ import annotations

import sys

import topology as T

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def ids(topo):
    return {n["id"] for n in topo["nodes"]}


def status_of(topo, node_id):
    return next((n["status"] for n in topo["nodes"] if n["id"] == node_id), None)


def has_edge(topo, frm, to):
    return any(e["from"] == frm and e["to"] == to for e in topo["edges"])


def main():
    # A representative single-engine open stack.
    sel = {"storage": "seaweedfs", "catalog": "polaris", "schema": "ocsf",
           "ingest": ["vector"], "query": ["datafusion"]}

    print("\n=== representative selection: full source→route→catalog→storage→engine→present chain ===\n")
    topo = T.build_topology(sel)
    nids = ids(topo)
    check("source node present", "source" in nids)
    check("route node present (vector)", "route_vector" in nids)
    check("land node present (seaweedfs)", "land_seaweedfs" in nids)
    check("catalog node present (polaris)", "catalog_polaris" in nids)
    check("engine node present (datafusion)", "engine_datafusion" in nids)
    check("present (sink) node present", "present" in nids)

    # The data path is wired end-to-end in the right order.
    check("edge source → route", has_edge(topo, "source", "route_vector"))
    check("edge route → land", has_edge(topo, "route_vector", "land_seaweedfs"))
    check("edge land → catalog", has_edge(topo, "land_seaweedfs", "catalog_polaris"))
    check("engine reads THROUGH the catalog (catalog → engine)",
          has_edge(topo, "catalog_polaris", "engine_datafusion"))
    check("engine does NOT read the land directly when a catalog exists",
          not has_edge(topo, "land_seaweedfs", "engine_datafusion"))
    check("edge engine → present", has_edge(topo, "engine_datafusion", "present"))

    # Human labels come from providers.label_for, and the schema is folded into the route label.
    route_label = next(n["label"] for n in topo["nodes"] if n["id"] == "route_vector")
    check("route label uses the human ingest label (Vector)", "Vector" in route_label)
    check("route label folds in the OCSF schema normalization", "OCSF" in route_label)
    land_label = next(n["label"] for n in topo["nodes"] if n["id"] == "land_seaweedfs")
    check("land label uses the human storage label (SeaweedFS)", "SeaweedFS" in land_label)

    # Tiers are tagged per node.
    tiers = {n["id"]: n["tier"] for n in topo["nodes"]}
    check("tiers tagged: source/route/land/catalog/query/present",
          tiers.get("source") == "source" and tiers.get("route_vector") == "route"
          and tiers.get("land_seaweedfs") == "land" and tiers.get("catalog_polaris") == "catalog"
          and tiers.get("engine_datafusion") == "query" and tiers.get("present") == "present")

    print("\n=== default node status is 'selected', never a faked 'up' ===\n")
    check("with no live_status, every node is 'selected'",
          all(n["status"] == "selected" for n in topo["nodes"]))
    check("no node is 'up' without telemetry",
          not any(n["status"] == "up" for n in topo["nodes"]))

    print("\n=== live_status overrides node status ===\n")
    live = {"route_vector": "up", "engine_datafusion": "down"}
    topo_live = T.build_topology(sel, live_status=live)
    check("live 'up' overrides the route node", status_of(topo_live, "route_vector") == "up")
    check("live 'down' overrides the engine node", status_of(topo_live, "engine_datafusion") == "down")
    check("a node absent from the live map stays 'selected' (not faked up)",
          status_of(topo_live, "land_seaweedfs") == "selected"
          and status_of(topo_live, "land_seaweedfs") != "up")

    print("\n=== an out-of-vocabulary live value degrades to 'unmeasured', never trusted as up ===\n")
    bad_live = {"route_vector": "green", "engine_datafusion": "100% healthy"}
    topo_bad = T.build_topology(sel, live_status=bad_live)
    check("unknown live value → 'unmeasured', not 'up'",
          status_of(topo_bad, "route_vector") == "unmeasured")
    check("no fabricated 'up' from a bogus live value",
          not any(n["status"] == "up" for n in topo_bad["nodes"]))

    print("\n=== throughput only appears with a real live signal carrying one ===\n")
    # No throughput in the live map → the mermaid must not invent a rate.
    check("no throughput string fabricated when live carries none",
          "ev/s" not in topo_live["mermaid"] and "ev/s" not in topo["mermaid"])
    live_tp = {"route_vector": {"status": "up", "throughput": "12k ev/s"}}
    topo_tp = T.build_topology(sel, live_status=live_tp)
    check("a real throughput is carried into the mermaid", "12k ev/s" in topo_tp["mermaid"])
    check("dict-form live status still resolves the node status",
          status_of(topo_tp, "route_vector") == "up")

    print("\n=== empty selection degrades cleanly ===\n")
    empty = T.build_topology({})
    check("empty selection does not raise and returns endpoints only",
          ids(empty) == {"source", "present"})
    check("empty selection has no faked 'up' nodes",
          not any(n["status"] == "up" for n in empty["nodes"]))
    check("None selection degrades the same way (no raise)",
          ids(T.build_topology(None)) == {"source", "present"})
    # Partial selections drop only the missing tiers, without breaking the path.
    no_cat = T.build_topology(dict(sel, catalog=None))
    check("no catalog → engine reads the land directly",
          has_edge(no_cat, "land_seaweedfs", "engine_datafusion")
          and "catalog_polaris" not in ids(no_cat))

    print("\n=== multi-engine fan-out ===\n")
    multi = T.build_topology(dict(sel, query=["datafusion", "trino"]))
    check("two engines → two engine nodes", {"engine_datafusion", "engine_trino"} <= ids(multi))
    check("both engines read the catalog and feed present",
          has_edge(multi, "catalog_polaris", "engine_trino")
          and has_edge(multi, "engine_trino", "present"))

    print("\n=== mermaid string is well-formed ===\n")
    m = topo["mermaid"]
    check("mermaid starts with 'graph' or 'flowchart'",
          m.lstrip().startswith("graph") or m.lstrip().startswith("flowchart"))
    check("mermaid references every node id",
          all(n["id"] in m for n in topo["nodes"]))
    check("mermaid contains edge arrows (-->)", "-->" in m)
    check("mermaid for an empty selection is still well-formed",
          empty["mermaid"].lstrip().startswith("graph")
          and "source" in empty["mermaid"] and "present" in empty["mermaid"])

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mAll topology assertions held.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
