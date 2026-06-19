"""Proof for Layer 1 (source health), Layer 4 (cross-tool gap), last-validated decay,
and — the headline — that the gate now reaches a true GREEN with all four layers
measured against real Iceberg tables.

No mocks: real tables on a local SqlCatalog with a filesystem warehouse, the same
PyIceberg paths the live console uses. Exit 0 = every assertion held.
"""
from __future__ import annotations

import shutil
import sys
import tempfile

import pyarrow as pa
from pyiceberg.catalog.sql import SqlCatalog

import decay
import gate_logic as gl
import layer1_audit as l1
import layer3_audit as l3
import layer4_audit as l4

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def main():
    wh = tempfile.mkdtemp(prefix="moar_layers_proof_")
    try:
        cat = SqlCatalog("proof", **{"uri": f"sqlite:///{wh}/cat.db", "warehouse": f"file://{wh}"})
        cat.create_namespace("ocsf")
        cat.create_namespace("inv")

        # OCSF source tables for Layer 1.
        src_schema = pa.schema([("time", pa.int64()), ("user", pa.string()), ("action", pa.string())])
        auth = cat.create_table("ocsf.authentication", schema=src_schema)
        auth.append(pa.table({"time": [1, 2, 3], "user": ["a", "b", "c"], "action": ["login"] * 3}, schema=src_schema))
        dns = cat.create_table("ocsf.dns", schema=src_schema)
        dns.append(pa.table({"time": [1, 2], "user": ["a", "b"], "action": ["query"] * 2}, schema=src_schema))
        sources = {"authentication": auth, "dns": dns}
        snap_ms = auth.current_snapshot().timestamp_ms

        print("\n=== Layer 1 — source health ===\n")
        # Healthy + no baseline → pass, completeness pending.
        h = l1.audit_sources(sources, now_ms=snap_ms + 10_000)
        check("healthy sources → Layer 1 pass", h["status"] == "pass")
        check("completeness PENDING with no baseline",
              all(s["completeness"]["status"] == "pending" for s in h["sources"]))
        check("carries the lake-side-receipt label", h["label"] == l1.LAKE_SIDE_LABEL)

        # Capture a baseline → completeness becomes measured pass.
        base = l1.source_row_counts(sources)
        l1.save_baseline(f"{wh}/baseline.json", base)
        base2 = l1.load_baseline(f"{wh}/baseline.json")
        check("baseline round-trips to a sidecar", base2 == base and base2["authentication"] == 3)
        hb = l1.audit_sources(sources, now_ms=snap_ms + 10_000, baseline=base2)
        check("with baseline → completeness measured pass",
              all(s["completeness"]["status"] == "pass" for s in hb["sources"]) and hb["status"] == "pass")

        # A source that fell off vs its baseline → completeness fail → Layer 1 fail.
        dropped = dict(base2, authentication=base2["authentication"] * 3)  # baseline was 3x current
        fc = l1.audit_sources(sources, now_ms=snap_ms + 10_000, baseline=dropped)
        check("row count below baseline floor → Layer 1 fail", fc["status"] == "fail")

        # Stale snapshot → freshness fail → Layer 1 fail.
        sf = l1.audit_sources(sources, now_ms=snap_ms + 7_200_000)
        check("stale source snapshot → Layer 1 fail", sf["status"] == "fail")

        # Missing expected column → conformance fail.
        mc = l1.audit_sources(sources, now_ms=snap_ms + 10_000, expected_columns={"time", "user", "src_endpoint"})
        check("missing expected column → Layer 1 fail", mc["status"] == "fail")

        # Regression for the critical false-green: a readable-but-never-written source
        # (no snapshot → freshness unmeasured) must be UNMEASURED, never a 'pass'.
        empty = cat.create_table("ocsf.empty", schema=src_schema)  # created, never appended
        ec = l1.audit_sources({"empty": empty}, now_ms=snap_ms + 10_000)
        check("never-written source itself unmeasured (no false pass)", ec["sources"][0]["status"] == "unmeasured")
        check("never-written-only namespace → Layer 1 unmeasured", ec["status"] == "unmeasured")

        print("\n=== last-validated decay ===\n")
        t0 = "2026-06-18T00:00:00Z"
        check("fresh pass stays pass", decay.effective_status("pass", t0, "2026-06-18T00:00:10Z", 3600) == "pass")
        check("pass past TTL → stale", decay.effective_status("pass", t0, "2026-06-18T03:00:00Z", 3600) == "stale")
        check("fail never decays", decay.effective_status("fail", t0, "2026-06-19T00:00:00Z", 3600) == "fail")
        check("unmeasured never decays", decay.effective_status("unmeasured", t0, "2026-06-19T00:00:00Z", 3600) == "unmeasured")
        # Fail-closed + crash-safety edge cases (the review's decay findings).
        check("age == TTL boundary stays pass", decay.effective_status("pass", t0, "2026-06-18T01:00:00Z", 3600) == "pass")
        check("pass with None timestamp → stale (fail closed)", decay.effective_status("pass", None, "2026-06-18T00:00:10Z", 3600) == "stale")
        check("pass with garbage timestamp → stale", decay.effective_status("pass", "not-a-date", "2026-06-18T00:00:10Z", 3600) == "stale")
        check("naive validated_at vs aware now does not crash", decay.effective_status("pass", "2026-06-18T00:00:00", "2026-06-18T00:00:10Z", 3600) == "pass")
        check("future-stamped pass → stale (clock skew)", decay.effective_status("pass", "2026-06-18T02:00:00Z", "2026-06-18T00:00:00Z", 3600) == "stale")

        print("\n=== Layer 4 — cross-tool gap (exact-match) ===\n")
        inv_schema = pa.schema([("asset_id", pa.string()), ("owner", pa.string())])

        def inv(name, ids):
            t = cat.create_table(f"inv.{name}", schema=inv_schema)
            t.append(pa.table({"asset_id": ids, "owner": ["x"] * len(ids)}, schema=inv_schema))
            return t

        cmdb = inv("cmdb", [f"host-{i}" for i in range(1, 51)])           # 50 assets
        edr = inv("edr", [f"host-{i}" for i in range(1, 48)])             # 47 — missing 48,49,50
        scanner = inv("scanner", [f"host-{i}" for i in range(1, 53)])     # 52 — superset

        ids_cmdb = l4.extract_ids(cmdb, "asset_id")
        ids_edr = l4.extract_ids(edr, "asset_id")
        ids_scan = l4.extract_ids(scanner, "asset_id")
        check("extract_ids reads the identity column", ids_cmdb is not None and len(ids_cmdb) == 50)
        check("extract_ids returns None for a missing column", l4.extract_ids(cmdb, "no_such_col") is None)

        gap = l4.cross_tool_gap("cmdb", {"cmdb": ids_cmdb, "edr": ids_edr, "scanner": ids_scan}, tolerance=0)
        _edr_gap = next(g for g in gap["gaps"] if g["to"] == "edr")
        _scan_gap = next(g for g in gap["gaps"] if g["to"] == "scanner")
        check("CMDB→EDR coverage gap = 3 (unmonitored)", _edr_gap["gap_count"] == 3)
        check("CMDB→scanner coverage gap = 0", _scan_gap["gap_count"] == 0)
        check("any over-tolerance gap → Layer 4 fail", gap["status"] == "fail")

        # Remediate: enroll the 3 missing hosts in the EDR.
        edr.append(pa.table({"asset_id": ["host-48", "host-49", "host-50"], "owner": ["x"] * 3}, schema=inv_schema))
        ids_edr2 = l4.extract_ids(edr, "asset_id")
        gap2 = l4.cross_tool_gap("cmdb", {"cmdb": ids_cmdb, "edr": ids_edr2, "scanner": ids_scan}, tolerance=0)
        check("after enrollment → Layer 4 pass", gap2["status"] == "pass")
        # Unmeasured guards, disambiguated: an unreadable primary WITH two other readable
        # sources can only be explained by the primary-unreadable condition (not the <2 guard).
        gap3 = l4.cross_tool_gap("cmdb", {"cmdb": None, "edr": ids_edr2, "scanner": ids_scan}, tolerance=0)
        check("unreadable primary (2 others readable) → unmeasured", gap3["status"] == "unmeasured")
        gap4 = l4.cross_tool_gap("cmdb", {"cmdb": ids_cmdb}, tolerance=0)
        check("readable primary but <2 readable sources → unmeasured", gap4["status"] == "unmeasured")

        print("\n=== Integrated arc — a TRUE GREEN with all four layers MEASURED ===\n")
        infra = dict(warns=[], spec_saved=True, docker_up=True, catalog_live=True)
        l1_ok = l1.audit_sources(sources, now_ms=snap_ms + 10_000, baseline=base2)["status"]
        l4_ok = gap2["status"]
        # Layer 3 measured for real against the auth table (not a literal 'pass').
        _auth_dir = auth.location().replace("file://", "")
        l3_ok = l3.audit_table(
            auth, store_basenames=l3.list_local_parquet_basenames(_auth_dir),
            now_ms=snap_ms + 10_000, enabled={"small_files", "orphans", "schema_conformance"},
            expected_columns={"time", "user"})["status"]
        check("Layer 1 audited real → pass", l1_ok == "pass")
        check("Layer 3 audited real (auth table) → pass", l3_ok == "pass")
        check("Layer 4 audited real (post-remediation) → pass", l4_ok == "pass")

        g_green = gl.compute_gate(layer1_status=l1_ok, layer3_status=l3_ok, layer4_status=l4_ok, **infra)
        print("  all healthy →", gl.verdict_line(g_green)[0])
        check("all four layers (each real-measured) pass → gate GREEN", g_green["all_green"] is True)

        l1_bad = l1.audit_sources(sources, now_ms=snap_ms + 7_200_000)["status"]  # freshness fail
        g_l1 = gl.compute_gate(layer1_status=l1_bad, layer3_status=l3_ok, layer4_status=l4_ok, **infra)
        print("  Layer 1 fails →", gl.verdict_line(g_l1)[0])
        check("Layer 1 fail → NOT green", g_l1["all_green"] is False)
        check("Layer 1 fail → verdict RED", gl.verdict_line(g_l1)[1] == "#c14a4a")

        # Layer 4 fail threaded from the REAL pre-remediation computed gap (status fail).
        g_l4 = gl.compute_gate(layer1_status=l1_ok, layer3_status=l3_ok, layer4_status=gap["status"], **infra)
        print("  Layer 4 fails →", gl.verdict_line(g_l4)[0])
        check("Layer 4 fail (computed) → NOT green", g_l4["all_green"] is False)

        # Decay applied to a passing layer flips GREEN → amber (stale), not RED.
        l3_stale = decay.effective_status("pass", "2026-06-17T00:00:00Z", "2026-06-18T12:00:00Z", decay.DEFAULT_TTL_SECONDS)
        g_stale = gl.compute_gate(layer1_status=l1_ok, layer3_status=l3_stale, layer4_status=l4_ok, **infra)
        print("  Layer 3 stale →", gl.verdict_line(g_stale)[0])
        check("stale layer → NOT green", g_stale["all_green"] is False)
        check("stale layer → amber not red", gl.verdict_line(g_stale)[1] != "#c14a4a")
        check("stale layer listed in gate['stale']", "Layer 3 — data-quality audit" in g_stale["stale"])

        print()
        if _failures:
            print(f"\033[91m{len(_failures)} assertion(s) FAILED:\033[0m " + "; ".join(_failures))
            return 1
        print("\033[92mAll assertions held — Layers 1, 3 & 4 measure real health against real Iceberg "
              "tables, decay rots a stale/undatable pass, and the gate reaches a true GREEN only when all "
              "four layers pass.\033[0m")
        return 0
    finally:
        shutil.rmtree(wh, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
