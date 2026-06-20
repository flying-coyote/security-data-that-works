"""Capture each MOAR console view as a real screenshot and assemble an annotated
flip-through HTML (rendered to PDF by build.sh).

This drives the EXPORTED static app (marimo export html, baked outputs + hydrating JS)
with Playwright/Chromium: it navigates the real tab tree and screenshots each view, then
writes flipthrough.html — one page per view, the screenshot plus an "Intent" annotation
underneath. These are real screenshots of the live UI (stack down, so the data-driven
panels show their honest pre-audit states); the annotations explain what each view is for.

Run via build.sh (which exports the app first and renders the PDF after). Needs:
  - /tmp/cp_app.html  (the exported app — build.sh produces it)
  - playwright + a chromium browser (system python3 has both here)
"""
from __future__ import annotations

import os
import subprocess

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "img")
APP = "file:///tmp/cp_app.html"

# (key, breadcrumb, [tab names to click in order], annotation-html)
VIEWS = [
    ("pick", "Startup › Strategy › Pick components", ["Startup", "Strategy", "Pick components"],
     "The constraint-first decision flow. You declare the binding constraints first "
     "(deployment, team size, vendor posture, workload, compliance, cost), and the funnel "
     "narrows the full component catalog to a fit-justified shortlist &mdash; disqualify / "
     "caution / favor per candidate, with a reachable-N/M count and a best-fit pick. This is "
     "the public half of the Capability Matrix's method (constraint-conditional weighting) "
     "shown live and free; the scored ranking &mdash; which specific tool wins for your "
     "workload archetype and by how much &mdash; is the paid Matrix at /matrix."),
    ("vault", "Startup › Strategy › Vault &amp; Matrix", ["Startup", "Strategy", "Vault & Matrix"],
     "Two consultant-mode surfaces plus the evidence runner. The Strategy Vault (OKF) and the "
     "Capability Matrix scorecard are paid/consultant IP &mdash; in the public default mode the "
     "scorecard shows no scores and points to /matrix; with PAID_MODE on, the consultant sees "
     "the per-criterion scored view loaded from the private vault (never the repo). The "
     "thesis-evidence verbs re-prove the program's claims live against the stack."),
    ("config", "Startup › Configuration", ["Startup", "Configuration"],
     "Configure the stack spec, validate the OCSF transform (VRL) before provisioning, and "
     "deploy / tear-down the MOAr stack locally via Pulumi. The deploy is authorized by the "
     "data-health gate (shown here as a compact verdict chip; the full breakdown lives in "
     "Flow &rsaquo; Health) &mdash; you can't deploy onto an incoherent selection without "
     "logging an override."),
    ("land", "Flow › Land", ["Flow", "Land"],
     "The pipeline topology &mdash; your selected stack drawn as the path an event actually "
     "travels: Source &rarr; Route (ingest, OCSF-normalize) &rarr; Lakehouse (storage + "
     "Iceberg) brokered by the Catalog &rarr; Engine(s) &rarr; Present. A node with no live "
     "telemetry shows '&mdash;', never a fabricated 'up'; throughput appears only when a real "
     "signal carries it."),
    ("health", "Flow › Health", ["Flow", "Health"],
     "The data-health gate &mdash; the console's center of gravity. It refuses to certify the "
     "foundation GREEN until each measurable layer actually passes: source health (L1), data "
     "quality (L3), cross-tool coverage (L4), plus the cluster-5 deepenings &mdash; cross-engine "
     "answer-equality, OCSF round-trip mapping fidelity, and flow reconciliation. Unproven "
     "layers are labeled, never shown as a pass; a proven layer decays to 'stale' if it isn't "
     "re-run. A GREEN gate is the deploy authorization, not a slide."),
    ("migrate", "Flow › Migrate", ["Flow", "Migrate"],
     "The intent-driven migration cockpit. Pick one of six migration intents and the panel "
     "expands to focused, verifiable direction: the steps, the real swap-cost and how to back "
     "out (read off each component's reversibility), and the live data-health check that proves "
     "the move didn't change the answer &mdash; cross-engine answer-equality for an engine swap, "
     "the swap-store/catalog/router checks for those tiers, flow reconciliation for a route "
     "change. The open architecture makes being wrong cheap; this makes that concrete."),
    ("analyze", "Analyze", ["Analyze"],
     "Aggregate-only analysis over the loaded OCSF table &mdash; row and per-class/activity "
     "counts, top-N sources, field population, time span &mdash; plus the Iceberg metadata "
     "inspector. It never renders a raw telemetry row: real security data is a prompt-injection "
     "and control-char surface, so only counts and low-cardinality keys leave the query, and "
     "source values are control-char-stripped and length-bounded."),
]


def _sha():
    try:
        return subprocess.run(["git", "-C", HERE, "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def capture():
    os.makedirs(IMG, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
        ctx = b.new_context(locale="en-US", timezone_id="America/New_York",
                            viewport={"width": 1500, "height": 1150}, device_scale_factor=2)
        pg = ctx.new_page()
        pg.goto(APP, wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(6000)  # let the app hydrate
        for key, _bc, clicks, _ann in VIEWS:
            for name in clicks:
                try:
                    pg.get_by_role("tab", name=name, exact=True).first.click(timeout=15000)
                    pg.wait_for_timeout(900)
                except Exception as e:  # noqa: BLE001 - keep going; a missing tab is visible in the shot
                    print(f"  [{key}] click '{name}' note: {str(e)[:80]}")
            pg.wait_for_timeout(1200)
            pg.screenshot(path=os.path.join(IMG, f"{key}.png"), full_page=True)
            print(f"  captured {key}: {os.path.getsize(os.path.join(IMG, key + '.png'))} bytes")
        ctx.close()
        b.close()


def build_html():
    sha = _sha()
    css = """
    @page { size: 360mm 290mm; margin: 0 }
    * { box-sizing: border-box }
    body { margin: 0; font-family: -apple-system, Segoe UI, Roboto, sans-serif; color: #1f2937 }
    .page { width: 360mm; height: 290mm; padding: 14mm 16mm; page-break-after: always;
            display: flex; flex-direction: column }
    .crumb { font: 600 13pt ui-monospace, monospace; color: #0f766e; letter-spacing: .04em;
             text-transform: uppercase; margin: 0 0 6mm }
    .shot { flex: 1 1 auto; min-height: 0; border: 1px solid #e5e7eb; border-radius: 8px;
            overflow: hidden; background: #fff }
    .shot img { width: 100%; height: auto; display: block }
    .intent { margin: 6mm 0 0; padding: 6mm 7mm; background: #f0fdfa; border-left: 4px solid #0f766e;
              border-radius: 4px; font-size: 12.5pt; line-height: 1.5 }
    .intent b { color: #0f766e }
    /* cover */
    .cover { justify-content: center; align-items: flex-start; background: #0b1f1d; color: #e7f5f2 }
    .cover h1 { font-size: 40pt; margin: 0 0 4mm }
    .cover .sub { font-size: 15pt; color: #93c5bd; max-width: 230mm; line-height: 1.5 }
    .cover .tree { font: 12pt ui-monospace, monospace; color: #6ee7d4; margin-top: 10mm; line-height: 1.8 }
    .cover .note { font-size: 11pt; color: #7f9b96; margin-top: 12mm; max-width: 230mm; line-height: 1.5 }
    """
    pages = []
    pages.append(f"""<div class="page cover">
      <h1>MOAR Console &mdash; visual walkthrough</h1>
      <div class="sub">A flip-through of each console view, captured live from the marimo app, with the
      intent of each view annotated underneath. Generated from console <b>@{sha}</b>.</div>
      <div class="tree">Startup &rsaquo; { '{' } Strategy &rsaquo; [ Pick components, Vault &amp; Matrix ], Configuration { '}' }<br>
      Flow &rsaquo; [ Land, Health, Migrate ]<br>Analyze</div>
      <div class="note">These are real screenshots of the live UI. The data-driven panels (Health, Analyze)
      show their honest pre-audit / no-data states because the demo stack is not running &mdash; the gate
      never bluffs a pass, so an un-run audit reads as unmeasured, not green. Regenerate this PDF with
      <b>bash flipthrough/build.sh</b> after a console change.</div>
    </div>""")
    for key, bc, _clicks, ann in VIEWS:
        pages.append(f"""<div class="page">
          <div class="crumb">{bc}</div>
          <div class="shot"><img src="img/{key}.png"></div>
          <div class="intent"><b>Intent.</b> {ann}</div>
        </div>""")
    html = f"<!doctype html><html><head><meta charset='utf-8'><style>{css}</style></head><body>{''.join(pages)}</body></html>"
    with open(os.path.join(HERE, "flipthrough.html"), "w") as f:
        f.write(html)
    print(f"  wrote flipthrough.html ({len(html)} bytes), {len(VIEWS)} views + cover")


if __name__ == "__main__":
    capture()
    build_html()
