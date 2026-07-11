"""Guided walkthrough (Phase F, PF-1): the golden path — the demo spine — threaded as a narrative
across the console's tabs, with progressive disclosure and a live per-step status. The operator sees
the whole operator workflow at a glance (declare constraints -> wire a source -> land per class ->
the gate certifies + engines agree -> a hunt fires -> any component is reversible) and where each
step lives, and each step shows whether its value moment has actually been demonstrated yet.

Grounded in the demo-spine spec (project1) and the site's named value moments (trust+verify, the SOC
hunt, reversibility). Pure: the step text is static; step_status maps a plain `signals` dict (the
console's already-computed reactive state) to a per-step status, and never invents a 'live' without a
real signal — an undemonstrated step reads 'waiting', not green. The panel renders it."""
from __future__ import annotations

# status vocabulary — LIVE is the only one that claims a value moment was actually demonstrated.
LIVE, READY, WAITING, STALE, NA = "live", "ready", "waiting", "stale", "n/a"
_CHIP = {LIVE: "✓ live", READY: "• ready", WAITING: "○ waiting", STALE: "◑ stale", NA: "· —"}

# The golden path (the demo spine). Each step: the operator action, the tab it lives in, the value
# moment it delivers, and what you'll see there. Order IS the narrative.
STEPS = [
    {"n": 1, "key": "setup", "title": "Declare your constraints, get a fitting open stack",
     "tab": "Startup › Strategy › Pick components",
     "value": "the constraint-first decision — the public half of the Capability Matrix, free",
     "see": "the funnel narrows the full component catalog to a fit-justified shortlist with a best-fit pick"},
    {"n": 2, "key": "config", "title": "Wire a source and watch the OCSF mapping applied",
     "tab": "Startup › Configuration",
     "value": "raw → transform → OCSF record, field by field — the schema, not the field name, decides the answer",
     "see": "the deployed router transform run on a sample event, with the semantic-trap fields flagged"},
    {"n": 3, "key": "land", "title": "Deploy and watch data land per OCSF class",
     "tab": "Flow › Land",
     "value": "the pipeline topology lights up with real per-class landed counts into Iceberg",
     "see": "Source → Route → Lakehouse → Engine, each node live or an honest '—' when no signal carries it"},
    {"n": 4, "key": "gate", "title": "The data-health gate certifies it — and every engine agrees",
     "tab": "Flow › Health",
     "value": "the trust+verify pair the site sells most: a GREEN gate is the deploy authorization, not a slide",
     "see": "each measurable layer passes (or is labeled unproven); cross-engine answer-equality holds"},
    {"n": 5, "key": "analyze", "title": "Run a real hunt over the landed OCSF and get a finding",
     "tab": "Analyze",
     "value": "the SOC value moment — a detection fires over really-landed OCSF",
     "see": "N rules ran, M triggered, aggregate-safe (counts + the grouping key, never a raw row)"},
    {"n": 6, "key": "migrate", "title": "Swap any component — being wrong is cheap",
     "tab": "Migrate",
     "value": "reversibility: the open architecture makes a wrong pick cheap to undo",
     "see": "the swap-cost, the back-out, and the live check that proves the swap didn't change the answer"},
]


def step_status(key, signals):
    """Pure: (status, note) for a step from the console's live signals. Absent signal -> WAITING
    (the value moment is not yet demonstrated), never a fabricated LIVE."""
    s = signals or {}
    if key == "setup":
        return (READY, "spec saved — the fitting stack is locked in") if s.get("spec_saved") \
            else (READY, "a stack is selected; save the spec to lock it in")
    if key == "config":
        sch = s.get("schema")
        return (READY, f"previewing the raw → OCSF mapping for `{sch}`") if sch \
            else (READY, "a raw → OCSF transform preview is available")
    if key == "land":
        landed = s.get("landed")
        if landed:
            return LIVE, "landed " + " · ".join(f"{c}:{n}" for c, n in landed.items())
        return WAITING, "deploy and run the pipeline to watch data land per class"
    if key == "gate":
        if s.get("gate_green"):
            ae = s.get("answer_equality")
            return LIVE, "gate GREEN" + (" · engines agree on the count" if ae == "pass" else "")
        if s.get("gate_unmeasured"):
            return WAITING, "gate amber — unproven layers remain; run them in Flow › Health"
        return WAITING, "the gate has not certified the foundation yet"
    if key == "analyze":
        d = s.get("detections")
        if d == "pass":
            return LIVE, "a hunt fired over landed OCSF (recorded, dated in the gate)"
        if d == "stale":
            return STALE, "a hunt fired before, but the measurement has decayed — re-run it"
        return WAITING, "run a hunt over the landed table to surface a finding"
    if key == "migrate":
        ae = s.get("answer_equality")
        if ae == "pass":
            return LIVE, "a swap was proven not to change the answer (cross-engine equality)"
        if ae == "stale":
            return STALE, "a swap was proven before; the equality check has decayed"
        return READY, "reversibility is a property of each component — read the swap-cost + back-out"
    return NA, ""


def assemble(signals):
    """The steps annotated with their live status + note (pure)."""
    out = []
    for st in STEPS:
        status, note = step_status(st["key"], signals)
        out.append({**st, "status": status, "note": note, "chip": _CHIP.get(status, _CHIP[NA])})
    return out


def progress(steps):
    """(demonstrated_live, total). Only LIVE counts as a demonstrated value moment — the honest count."""
    return sum(1 for st in steps if st["status"] == LIVE), len(steps)


def walkthrough_panel(mo, ui, steps):
    """Render the golden path as a progressive-disclosure stepper: a one-line spine + a per-step
    accordion (collapsed), each step showing its tab, its value moment, and a live status chip."""
    done, total = progress(steps)
    spine = " → ".join(f"{st['n']}·{st['key'].title()}" for st in steps)
    head = (f"**The golden path — the operator workflow, end to end.**  \n`{spine}`\n\n"
            f"**{done} of {total}** value moments demonstrated live in this session; the rest light up as "
            "you walk the tabs. A step is `live` only when a real signal backs it — an undemonstrated step "
            "reads `waiting`, never a bluffed green.")
    items = {}
    for st in steps:
        label = f"{st['n']}. {st['title']}   —   {st['chip']}  ·  {st['note']}"
        body = mo.md(
            f"**Where:** {st['tab']}\n\n"
            f"**Why it matters:** {st['value']}\n\n"
            f"**What you'll see:** {st['see']}")
        items[label] = body
    return ui.panel(mo, ui.header(mo, "Guided walkthrough"), mo.md(head), mo.accordion(items))
