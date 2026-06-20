"""Proof for the intent-driven migration cockpit.

Run:  python3 prove_migrate.py     (exit 0 = every assertion held)
Pure stdlib (imports providers.py, which is stdlib-only).

What it locks down:
  - every registered INTENT yields guidance with non-empty steps + a verify step + a
    swap_cost + a reversibility back-out path;
  - the engine-swap intent's verify references cross-engine answer-equality;
  - guidance specializes to the selected components (a ClickHouse selection names it);
  - the swap-cost is derived from the selected component's real swap_cost (a high-cost
    schema-style swap and a low-cost engine swap come out differently);
  - an unknown intent_id degrades cleanly (returns guidance, never raises).
"""
from __future__ import annotations

import sys

import migrate as m

PASS, FAIL = "\033[92mPASS\033[0m", "\033[91mFAIL\033[0m"
_failures = []


def check(label, cond):
    print(f"  [{PASS if cond else FAIL}] {label}")
    if not cond:
        _failures.append(label)


# A conventional open selection, single ClickHouse engine so specialization is testable.
SEL = {"storage": "seaweedfs", "catalog": "polaris", "ingest": ["vector"],
       "query": ["clickhouse"], "schema": "ocsf"}


def main():
    print("\n=== every intent yields complete guidance ===\n")
    for intent in m.INTENTS:
        g = m.guidance_for(intent["id"], SEL)
        iid = intent["id"]
        check(f"{iid}: non-empty steps", isinstance(g["steps"], list) and len(g["steps"]) >= 1)
        check(f"{iid}: every step is a non-empty string",
              all(isinstance(s, str) and s.strip() for s in g["steps"]))
        check(f"{iid}: has a verify step", isinstance(g["verify"], str) and g["verify"].strip() != "")
        check(f"{iid}: has a swap_cost", isinstance(g["swap_cost"], str) and g["swap_cost"].strip() != "")
        check(f"{iid}: has a reversibility back-out", isinstance(g["reversibility"], str)
              and g["reversibility"].strip() != "")
        check(f"{iid}: intent label echoed", isinstance(g["intent"], str) and g["intent"].strip() != "")
        check(f"{iid}: risks is a list of (level,title,body) triples",
              isinstance(g["risks"], list)
              and all(isinstance(r, tuple) and len(r) == 3 for r in g["risks"]))

    print("\n=== engine-swap verify references cross-engine answer-equality ===\n")
    eng = m.guidance_for("swap_query_engine", SEL)
    vtext = eng["verify"].lower()
    check("swap_query_engine verify mentions cross-engine answer-equality",
          "answer" in vtext and "equality" in vtext and "engine" in vtext)
    check("swap_query_engine verify names the ./moar verify verb", "moar verify" in vtext)
    cut = m.guidance_for("replace_siem_read_path", SEL)
    check("read-path cutover also verifies via cross-engine answer-equality",
          "answer" in cut["verify"].lower() and "equality" in cut["verify"].lower())

    print("\n=== verify verb matches the intent's reversibility tier ===\n")
    cat = m.guidance_for("change_catalog", SEL)
    check("catalog change verify references swap-catalog", "swap-catalog" in cat["verify"])
    sto = m.guidance_for("change_storage", SEL)
    check("storage change verify references swap-store", "swap-store" in sto["verify"])
    rtr = m.guidance_for("swap_router", SEL)
    check("router swap verify references swap-router", "swap-router" in rtr["verify"])

    print("\n=== guidance specializes to the selected components ===\n")
    ch = m.guidance_for("swap_query_engine", SEL)
    blob = (ch["summary"] + " " + " ".join(ch["steps"]) + " " + ch["swap_cost"]).lower()
    check("ClickHouse selection names ClickHouse in the engine-swap guidance", "clickhouse" in blob)
    # A different engine selection names that engine instead — proves it's not hard-coded.
    sel_trino = dict(SEL, query=["trino"])
    tr = m.guidance_for("swap_query_engine", sel_trino)
    trblob = (tr["summary"] + " " + tr["swap_cost"]).lower()
    check("Trino selection names Trino, not ClickHouse",
          "trino" in trblob and "clickhouse" not in tr["summary"].lower())
    # Catalog specialization.
    cat_lake = m.guidance_for("change_catalog", dict(SEL, catalog="lakekeeper"))
    check("Lakekeeper catalog selection names Lakekeeper",
          "lakekeeper" in (cat_lake["summary"] + cat_lake["swap_cost"]).lower())

    print("\n=== swap_cost is derived from the component's real swap_cost field ===\n")
    # Engine swap (DataFusion) is low-cost; catalog swap (Nessie, branch history) is higher.
    df = m.guidance_for("swap_query_engine", dict(SEL, query=["datafusion"]))
    check("DataFusion engine swap reads as low cost", df["swap_cost"].lower().startswith("low"))
    nessie = m.guidance_for("change_catalog", dict(SEL, catalog="nessie"))
    check("Nessie catalog swap carries a higher (medium/high) cost from its swap_cost field",
          "medium" in nessie["swap_cost"].lower() or "high" in nessie["swap_cost"].lower())
    check("Nessie swap_cost surfaces the branch/tag history caveat from providers.py",
          "branch" in nessie["swap_cost"].lower() or "tag" in nessie["swap_cost"].lower())

    print("\n=== augment intent is the cheap, fully-reversible first move ===\n")
    aug = m.guidance_for("augment_alongside_siem", SEL)
    check("augment swap_cost reads as low", aug["swap_cost"].lower().startswith("low"))
    check("augment reversibility says the SIEM is never touched",
          "siem" in aug["reversibility"].lower())

    print("\n=== unknown intent_id degrades cleanly (no crash) ===\n")
    try:
        bad = m.guidance_for("does_not_exist", SEL)
        check("unknown intent returns a dict, does not raise", isinstance(bad, dict))
        check("unknown intent has empty steps but a usable summary",
              bad["steps"] == [] and isinstance(bad["summary"], str) and bad["summary"].strip() != "")
        check("unknown intent verify/swap_cost are present (empty strings, not missing keys)",
              "verify" in bad and "swap_cost" in bad and "reversibility" in bad)
    except Exception as e:  # noqa: BLE001
        check(f"unknown intent did not raise (raised {type(e).__name__})", False)

    # None and empty-string also degrade, not just an unrecognized word.
    for weird in (None, "", "  "):
        try:
            g = m.guidance_for(weird, SEL)
            check(f"intent_id={weird!r} degrades to a dict without raising", isinstance(g, dict))
        except Exception as e:  # noqa: BLE001
            check(f"intent_id={weird!r} did not raise (raised {type(e).__name__})", False)

    print("\n=== guidance survives a missing / partial selection ===\n")
    try:
        for intent in m.INTENTS:
            g = m.guidance_for(intent["id"], {})
            assert g["steps"] and g["verify"], intent["id"]
        check("every intent still yields steps + verify on an empty selection", True)
    except Exception as e:  # noqa: BLE001
        check(f"empty-selection guidance did not raise (raised {type(e).__name__}: {e})", False)

    if _failures:
        print(f"\n\033[91m{len(_failures)} assertion(s) FAILED\033[0m")
        return 1
    print("\n\033[92mAll migration-cockpit assertions held.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
