"""Flow-layer "count at every hop" gate — the single highest-value data-health measurement the book (ch03)
says almost nobody runs, and the runnable form of Appendix-B #12 ("Mapping Wrong by Construction") and
Appendix-F F.2 (the bytes_in/out / class mis-map). The existing observe/healthcheck gate checks the QUALITY
layer (NULLs, timestamps, cross-engine count); this checks the FLOW layer: count what each source emitted and
count what landed in the model, per OCSF class, and fail LOUD when a hop silently drops or mis-routes a class.

Self-contained demonstrator: a clean pipeline passes; a pipeline with one mis-mapped class (a vendor mapping
that sends an entire activity category to the wrong data model, the silent failure the chapter describes)
reads NOT READY and names the exact gap. No engine needed — this is the counting discipline itself.
"""
import sys

# what each source EMITTED at the tap, by OCSF class_uid (the count nobody captures)
SOURCE_EMITTED = {4001: 10000, 3002: 4000, 1001: 2500, 4002: 800}


def run_pipeline(faulted: bool):
    """Returns per-class counts as they LAND in the OCSF model after parse + map."""
    landed = {}
    for cls, n in SOURCE_EMITTED.items():
        parsed = n  # assume parse succeeds for every event in this demo
        # the mapping step. A mis-map sends an entire class to the WRONG model, so 0 of it lands in the target.
        if faulted and cls == 3002:      # e.g. Authentication mis-mapped to a model the detection never reads
            landed[cls] = 0
        else:
            landed[cls] = parsed
    return landed


def gate(landed):
    print("  flow-layer count-at-every-hop gate (source tap -> OCSF model), per class_uid:")
    ok = True
    for cls, emitted in SOURCE_EMITTED.items():
        got = landed.get(cls, 0)
        status = "ok" if got == emitted else "DROP"
        if got != emitted:
            ok = False
        bar = "" if got == emitted else f"   <-- {emitted - got} events vanished between source and model"
        print(f"    class {cls}: emitted {emitted:>6}  landed {got:>6}  [{status}]{bar}")
    print(f"  {'READY — every source count reconciles at the model boundary' if ok else 'NOT READY — a class is dropping silently; a detection keyed on it would return zero on a loud network'}")
    return ok


print("=== clean pipeline ===")
clean_ok = gate(run_pipeline(faulted=False))
print("\n=== faulted pipeline (class 3002 mis-mapped to the wrong model) ===")
faulted_ok = gate(run_pipeline(faulted=True))

# the gate's job: pass clean, FAIL faulted (loudly, naming the gap). A timing/quality check would not see this.
demonstrated = clean_ok and (not faulted_ok)
print(f"\nDEMONSTRATED: the flow gate passes clean and catches the silent class-3002 drop the quality gate "
      f"cannot see: {demonstrated}")
sys.exit(0 if demonstrated else 1)
