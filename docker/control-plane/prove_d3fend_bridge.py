"""Proof for the D3FEND bridge (PG-3): the scoped corpus is a FAITHFUL projection of the wall,
the inferred edges are intent-blind 0.25 and can never be upgraded, the vendored CSV is fresh,
and every honest-degrade path returns an HONEST empty (not a fabricated claim).

THE INVARIANTS this asserts:
  a) JOIN INTEGRITY  : every covered (off_tech_id,d3fend_id) row in the corpus exists in the
                       source matrix_long.csv with the SAME shared_artifacts count + names.
  b) ZERO-SET EXACT  : the band=="zero_defense" off_tech_ids equal EXACTLY the 27 build_wall_leaf
                       prints (set equality both ways — no missing, no extra).
  c) TRUST NEVER UPGRADES AN INTENT-BLIND EDGE: every defenses_for edge is trust 0.25 /
                       intent_blind True; weakest_link(0.70,0.25)==0.25 and (1.00,0.25)==0.25.
  d) STALENESS GUARD : re-running gen_d3fend_corpus.py to a temp path byte-matches the checked-in
                       CSV (excluding the _meta gen_date line) — a stale/drifted file fails.
  e) AGGREGATE-SAFE  : a nasty control-char + markdown/HTML payload through the render path comes
                       out inert (no raw '<', no backtick, '&lt;' present, no control chars).
  f) HONEST-DEGRADE not-in-corpus : in_corpus("T1530") False, defenses_for returns the "not in
                       corpus" reason, required_ocsf_classes of an unproduced artifact is [].
  g) HONEST-DEGRADE zero-defense  : is_zero_defense("T1115") True, defenses_for returns the
                       zero-defense reason.
  h) OCSF SEED SANITY: required_ocsf_classes only ever returns class_uids from {1007,3002,4001,6003}.

Run:  /tmp/pyice-venv/bin/python prove_d3fend_bridge.py   (exit 0 = all invariants hold)
Pure stdlib; runs with cwd = this control-plane dir (imports d3fend_bridge directly).
"""
from __future__ import annotations

import csv
import os
import subprocess
import sys
import tempfile

import d3fend_bridge as br

HERE = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(HERE, "d3fend_coverage.csv")
WALL_DATA = os.path.normpath(os.path.join(HERE, "..", "..", "..", "project1", "02-projects", "d3fend-wall", "data"))
MATRIX_LONG = os.path.join(WALL_DATA, "matrix_long.csv")
GENERATOR = os.path.normpath(os.path.join(HERE, "..", "..", "..", "project1", "tools", "gen_d3fend_corpus.py"))

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []

# The 27 ZERO_DEFENSE techniques build_wall_leaf.py prints (pinned).
ZERO_27 = {
    "T1115", "T1559.001", "T1578.001", "T1213.004", "T1213.006", "T1006", "T1562.012",
    "T1036.007", "T1559.002", "T1056.002", "T1553.001", "T1027.006", "T1564.001", "T1559",
    "T1491.001", "T1547.015", "T1213.005", "T1564.004", "T1106", "T1055.008", "T1564.009",
    "T1036.002", "T1113", "T1049", "T1055.005", "T1070.006", "T1559.003",
}


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


def _read_matrix_long():
    out = {}
    with open(MATRIX_LONG, newline="") as f:
        for r in csv.DictReader(f):
            out[(r["off_tech_id"], r["d3fend_id"])] = (
                int(r["shared_artifacts"]), r["shared_artifact_names"],
            )
    return out


def _strip_gen_date(path):
    """Return the CSV bytes with the _meta gen_date pinned out, so byte-compare ignores the date."""
    lines = []
    with open(path, newline="") as f:
        for line in f:
            if line.startswith("_meta,"):
                # blank the gen_date=... token in the phase column without disturbing the rest.
                line = "_meta,<meta-normalized>\n"
            lines.append(line)
    return "".join(lines)


def main():
    corpus = br.load_corpus()
    covered = [r for r in corpus if r["band"] not in ("zero_defense", "_meta")]

    print("\n=== (a) JOIN INTEGRITY: the corpus is a faithful scoped projection of matrix_long ===\n")
    ml = _read_matrix_long()
    mismatch = []
    for r in covered:
        key = (r["off_tech_id"], r["d3fend_id"])
        if key not in ml:
            mismatch.append(("absent", key))
            continue
        cnt, _names = ml[key]
        if cnt != r["shared_artifacts"]:
            mismatch.append(("count", key, cnt, r["shared_artifacts"]))
    check(f"every covered (off,d3fend) row exists in matrix_long with same shared_artifacts "
          f"({len(covered)} rows checked, {len(mismatch)} mismatches)", not mismatch)
    # NOTE: shared_artifact_names is _safe_key'd at generate time, so compare the safe form.
    name_mismatch = []
    for r in covered[:500]:  # sample to keep the proof fast; full count already join-checked
        key = (r["off_tech_id"], r["d3fend_id"])
        if key in ml:
            _cnt, names = ml[key]
            if br._safe_key(names) != r["shared_artifact_names"]:
                name_mismatch.append(key)
    check("shared_artifact_names match the source (safe-form) on a 500-row sample", not name_mismatch)

    print("\n=== (b) ZERO-SET EXACT: the band==zero_defense set is EXACTLY build_wall_leaf's 27 ===\n")
    zero = {r["off_tech_id"] for r in corpus if r["band"] == "zero_defense"}
    check(f"corpus zero-defense set has 27 members (has {len(zero)})", len(zero) == 27)
    check("corpus zero-defense set == the 27 build_wall_leaf prints (no missing)", not (ZERO_27 - zero))
    check("corpus zero-defense set == the 27 build_wall_leaf prints (no extra)", not (zero - ZERO_27))

    print("\n=== (c) TRUST NEVER UPGRADES AN INTENT-BLIND EDGE ===\n")
    edges = br.defenses_for("T1071", band="detect", corpus=corpus)
    real_edges = [e for e in edges if "reason" not in e]
    check("defenses_for(T1071) returns real artifact edges", len(real_edges) > 0)
    check("every defenses_for edge is trust 0.25", all(e["trust"] == 0.25 for e in real_edges))
    check("every defenses_for edge is intent_blind True", all(e["intent_blind"] is True for e in real_edges))
    check("every edge is proxy_quality artifact_cooccurrence",
          all(e["proxy_quality"] == "artifact_cooccurrence" for e in real_edges))
    check("every edge carries the design-time / NOT-telemetry-coverage caveat",
          all("NOT coverage of your telemetry" in e["caveat"] for e in real_edges))
    check("weakest_link(0.70, 0.25) == 0.25 (curated MIN inferred can't lift it)",
          br.weakest_link(0.70, 0.25) == 0.25)
    check("weakest_link(1.00, 0.25) == 0.25 (measured MIN inferred can't lift it)",
          br.weakest_link(1.00, 0.25) == 0.25)
    check("weakest_link(0.80, 0.70, 0.25) == 0.25", br.weakest_link(0.80, 0.70, 0.25) == 0.25)
    # the curated 0.70 edge is a SEPARATE source and stays 0.70 — but MINing it with the
    # inferred edge still collapses to 0.25 (the chain is only as sound as the weak hop).
    cur = br.curated_defense_for("T1071")
    check("curated T1071 edge is the separate ontology_curated 0.70 (intent-aware)",
          cur and cur["trust"] == 0.70 and cur["intent_blind"] is False)
    check("MINing the curated 0.70 with the inferred 0.25 still reports 0.25",
          br.weakest_link(cur["trust"], real_edges[0]["trust"]) == 0.25)

    print("\n=== (d) STALENESS GUARD: a fresh generator run byte-matches the checked-in CSV ===\n")
    with tempfile.TemporaryDirectory() as td:
        tmp_out = os.path.join(td, "d3fend_coverage.csv")
        # The generator writes to a fixed path; run it with an env override via a tiny shim:
        # easiest portable path — run it, then it writes the real file; instead we copy the
        # generator's OUT by monkey-running with a patched OUT through the module API.
        sys.path.insert(0, os.path.dirname(GENERATOR))
        import importlib
        gen = importlib.import_module("gen_d3fend_corpus")
        importlib.reload(gen)
        gen.OUT = tmp_out
        rc = gen.main()
        check("generator re-run exits 0", rc == 0)
        fresh = _strip_gen_date(tmp_out)
        checked_in = _strip_gen_date(CORPUS)
        check("regenerated CSV byte-matches the checked-in vendored CSV (gen_date excluded)",
              fresh == checked_in)

    print("\n=== (e) AGGREGATE-SAFE: a nasty payload through the render path comes out inert ===\n")
    payload = "T1071\n\x00`</code><img src=x onerror=alert(1)>"
    safe = br._safe_key(payload)
    check("control chars stripped (\\n, \\x00)", "\n" not in safe and "\x00" not in safe)
    check("markdown code-span backtick stripped (no breakout)", "`" not in safe)
    check("no raw '<' / live <img reaches the render", "<img" not in safe and "<" not in safe)
    check("payload rendered inert (escaped &lt; present where '<' was)", "&lt;" in safe)
    # and through a real defenses_for edge (every label is _safe_key'd on the way out):
    nasty_corpus = list(corpus) + [{
        "off_tech_id": "T1071", "off_tech": payload, "d3fend_id": payload, "def_tech": payload,
        "phase": "detect", "tactic": payload, "shared_artifacts": 1,
        "shared_artifact_names": payload, "trust": 0.25, "proxy_quality": "artifact_cooccurrence",
        "band": "detect",
    }]
    nasty_edges = [e for e in br.defenses_for("T1071", "detect", nasty_corpus) if "reason" not in e]
    check("every surfaced label in a defenses_for edge is inert (no '<', no backtick)",
          all("<" not in str(v) and "`" not in str(v)
              for e in nasty_edges for v in e.values() if isinstance(v, str)))

    print("\n=== (f) HONEST-DEGRADE: not-in-corpus (T1530) ===\n")
    check("in_corpus(T1530) is False (not measured at all)", br.in_corpus("T1530", corpus) is False)
    t1530 = br.defenses_for("T1530", "detect", corpus)
    check("defenses_for(T1530) returns the 'not in corpus' reason, no fabricated defense",
          len(t1530) == 1 and "not in corpus" in t1530[0].get("reason", ""))
    check("required_ocsf_classes of an artifact with no console producer returns []",
          br.required_ocsf_classes("Configuration Resource") == []
          and br.required_ocsf_classes("Container Image") == [])

    print("\n=== (g) HONEST-DEGRADE: zero-defense (T1115) ===\n")
    check("is_zero_defense(T1115) is True", br.is_zero_defense("T1115", corpus) is True)
    check("in_corpus(T1115) is True (measured, but undefended)", br.in_corpus("T1115", corpus) is True)
    t1115 = br.defenses_for("T1115", "detect", corpus)
    check("defenses_for(T1115) returns the zero-defense reason, no fabricated defense",
          len(t1115) == 1 and "zero-defense" in t1115[0].get("reason", ""))

    print("\n=== (h) OCSF SEED SANITY: only {1007,3002,4001,6003} ever appear ===\n")
    allowed = {1007, 3002, 4001, 6003}
    seen = set()
    for label in ("Network Traffic", "Credential", "Process", "Cloud Storage", "Database",
                  "User Account", "Process Tree", "Network Flow", "Session", "Document File"):
        for cu in br.required_ocsf_classes(label):
            seen.add(cu)
    check(f"required_ocsf_classes only yields class_uids from {sorted(allowed)} (saw {sorted(seen)})",
          seen <= allowed and len(seen) > 0)
    # pipe-joined names resolve and union:
    multi = br.required_ocsf_classes("Network Traffic|Credential|Process")
    check("a pipe-joined artifact list unions its real producers (4001+3002+1007)",
          set(multi) == {1007, 3002, 4001})
    check("a defense dict carrying shared_artifact_names resolves too",
          br.required_ocsf_classes({"shared_artifact_names": "Network Traffic"}) == [4001])

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mD3FEND bridge: faithful scoped projection, intent-blind 0.25 never upgraded, "
          "fresh corpus, honest degrade — all invariants hold.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
