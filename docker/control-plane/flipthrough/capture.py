"""Capture each MOAR console view as a real screenshot and assemble an annotated
flip-through HTML (rendered to PDF by build.sh).

This drives the EXPORTED static app (marimo export html, baked outputs + hydrating JS)
with Playwright/Chromium: it navigates the real tab tree and screenshots each view, then
writes flipthrough.html — one page per view, the screenshot plus an "Intent" annotation
underneath. These are real screenshots of the live UI (stack down, so the data-driven
panels show their honest pre-audit states); the annotations explain what each view is for.

marimo's exported app renders inside a fixed-height shell: #App is pinned to the viewport
height with overflow:auto, so a naive full_page screenshot captures only each view's TOP
FOLD and silently drops the below-fold panels (e.g. the Phase E Setup diagnostics). Before
each shot we RELEASE that shell (height:auto / overflow:visible on #App + its pinning
ancestors), measure the view's true content height, and size the flip-through page to it —
so every view is shown whole. Per-view dimensions are recorded in img/manifest.json.

Run via build.sh (which exports the app first and renders the PDF after). Needs:
  - /tmp/cp_app.html  (the exported app — build.sh produces it)
  - playwright + a chromium browser (system python3 has both here)
"""
from __future__ import annotations

import json
import os
import struct
import subprocess

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "img")
APP = "file:///tmp/cp_app.html"

# Release marimo's fixed-height inner scroll shell so the document grows to its true content
# height. Without this, #App is pinned to the viewport (overflow:auto) and full_page captures
# only the top fold. Sets height:auto / overflow:visible on #App and neutralizes every ancestor
# that pins a pixel height, clips overflow, or positions absolutely. Returns the content height (px).
RELEASE_JS = """() => {
  const imp = (el, props) => { if (el) for (const k in props) el.style.setProperty(k, props[k], 'important'); };
  imp(document.documentElement, {height: 'auto', overflow: 'visible'});
  imp(document.body, {height: 'auto', overflow: 'visible'});
  const app = document.getElementById('App');
  imp(app, {height: 'auto', 'max-height': 'none', overflow: 'visible'});
  let n = app;
  while (n && n !== document.documentElement) {
    const cs = getComputedStyle(n);
    if (cs.position === 'absolute' || cs.position === 'fixed') imp(n, {position: 'static'});
    if (['auto','scroll','hidden'].includes(cs.overflowY) || ['auto','scroll','hidden'].includes(cs.overflowX))
      imp(n, {overflow: 'visible'});
    if (cs.height.endsWith('px')) imp(n, {height: 'auto', 'max-height': 'none'});
    n = n.parentElement;
  }
  return Math.max(document.documentElement.scrollHeight, document.body.scrollHeight, app ? app.scrollHeight : 0);
}"""

# (key, breadcrumb, [tab names to click in order], annotation-html)
VIEWS = [
    ("walkthrough", "Walkthrough", ["Walkthrough"],
     "The guided walkthrough &mdash; the golden path (the operator workflow end to end) threaded "
     "across the tabs as a progressive-disclosure stepper: declare constraints &rarr; wire a source "
     "and watch the OCSF mapping &rarr; land data per OCSF class &rarr; the data-health gate certifies "
     "it and every engine agrees &rarr; a hunt fires over the landed OCSF &rarr; any component is "
     "reversible. Each step names where it lives and shows a live status &mdash; 'live' only when a "
     "real signal backs it, 'waiting' until the value moment is actually demonstrated, never a bluffed "
     "green. It is the product's narrative spine; the flip-through you're reading is the standing "
     "visual record of it."),
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
     "logging an override. Before deploy, the pre-flight checks (Docker, ports, object store), "
     "the deploy-progress checklist, and the schema preview show what will come up."),
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
     "inspector, and the ATT&amp;CK&rarr;D3FEND coverage read built on the lab's measured bench: "
     "per-technique fired / covered / dark-spot / blind status with an ATT&amp;CK-Navigator export, "
     "the dark-spot recommendations (which OCSF classes to land), the 27 zero-defense holes and the "
     "fired&rarr;D3FEND-defense mapping, and the measured-firing overlay where the design-time "
     "structure and the measured firing disagree. Every D3FEND edge carries its trust tier and the "
     "intent-blind co-occurrence leads (0.25) are never laundered into coverage; this is design-time "
     "defensive structure, never a claim about your telemetry. It never renders a raw telemetry row: "
     "real security data is a prompt-injection and control-char surface, so only counts and "
     "low-cardinality keys leave the query, and source values are control-char-stripped and "
     "length-bounded."),
]

MAX_H = 12000  # safety cap on a runaway content-height measurement


def _png_size(path):
    """(width, height) in px from a PNG's IHDR — no PIL dependency."""
    with open(path, "rb") as fh:
        head = fh.read(24)
    return struct.unpack(">II", head[16:24])


def _sha():
    try:
        return subprocess.run(["git", "-C", HERE, "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, timeout=10).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001
        return "unknown"


def capture():
    os.makedirs(IMG, exist_ok=True)
    manifest = {}
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-gpu"])
        ctx = b.new_context(locale="en-US", timezone_id="America/New_York",
                            viewport={"width": 1500, "height": 1150}, device_scale_factor=2)
        pg = ctx.new_page()
        pg.goto(APP, wait_until="networkidle", timeout=60000)
        pg.wait_for_timeout(6000)  # let the app hydrate
        for key, _bc, clicks, _ann in VIEWS:
            pg.set_viewport_size({"width": 1500, "height": 1150})  # normal layout for tab nav
            for name in clicks:
                try:
                    pg.get_by_role("tab", name=name, exact=True).first.click(timeout=15000)
                    pg.wait_for_timeout(900)
                except Exception as e:  # noqa: BLE001 - keep going; a missing tab is visible in the shot
                    print(f"  [{key}] click '{name}' note: {str(e)[:80]}")
            pg.wait_for_timeout(1200)
            # release the pinned shell, measure true content height, grow the viewport to it,
            # re-release (a resize can re-render and drop the inline styles), then full-page shot.
            content_h = min(MAX_H, max(1150, int(pg.evaluate(RELEASE_JS) or 1150)))
            pg.set_viewport_size({"width": 1500, "height": content_h})
            pg.wait_for_timeout(500)  # reflow
            content_h = min(MAX_H, max(content_h, int(pg.evaluate(RELEASE_JS) or content_h)))
            pg.set_viewport_size({"width": 1500, "height": content_h})
            pg.wait_for_timeout(400)
            path = os.path.join(IMG, f"{key}.png")
            pg.screenshot(path=path, full_page=True)
            w, h = _png_size(path)
            manifest[key] = [w, h]
            print(f"  captured {key}: {os.path.getsize(path)} bytes, {w}x{h}px (content_h={content_h})")
        ctx.close()
        b.close()
    with open(os.path.join(IMG, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


# flip-through page geometry (mm)
PAGE_W = 360
SIDE = 16
CONTENT_W = PAGE_W - 2 * SIDE                  # 328mm — the rendered image width
OVERHEAD = 14 + 12 + 6 + 58 + 14               # pad_top + crumb + gap + annotation reserve + pad_bot


def _page_h_mm(manifest, key):
    """Physical page height (mm) for a view: the rendered image height + fixed chrome overhead.
    The image renders at CONTENT_W mm wide, so its height scales by the screenshot's aspect ratio."""
    wh = manifest.get(key)
    if not wh:
        return 290
    w, h = wh
    img_h_mm = CONTENT_W * (h / w)
    return max(290, round(OVERHEAD + img_h_mm))


def build_html():
    sha = _sha()
    try:
        with open(os.path.join(IMG, "manifest.json")) as f:
            manifest = json.load(f)
    except Exception:  # noqa: BLE001
        manifest = {}

    # Per-view named @page rules so each physical PDF page is sized to its view's full height
    # (verified: headless Chrome --print-to-pdf honors distinct named @page sizes in one PDF).
    page_rules = ["@page cover { size: 360mm 290mm; margin: 0 }"]
    page_assign = []
    for key, _bc, _clicks, _ann in VIEWS:
        page_rules.append(f"@page p_{key} {{ size: 360mm {_page_h_mm(manifest, key)}mm; margin: 0 }}")
        page_assign.append(f".page-{key} {{ page: p_{key} }}")

    css = "\n".join(page_rules) + "\n" + "\n".join(page_assign) + """
    * { box-sizing: border-box }
    body { margin: 0; font-family: -apple-system, Segoe UI, Roboto, sans-serif; color: #1f2937 }
    .page { width: 360mm; padding: 14mm 16mm; page-break-after: always;
            display: flex; flex-direction: column }
    .crumb { font: 600 13pt ui-monospace, monospace; color: #0f766e; letter-spacing: .04em;
             text-transform: uppercase; margin: 0 0 6mm }
    .shot { border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden; background: #fff }
    .shot img { width: 100%; height: auto; display: block }
    .intent { margin: 6mm 0 0; padding: 6mm 7mm; background: #f0fdfa; border-left: 4px solid #0f766e;
              border-radius: 4px; font-size: 12.5pt; line-height: 1.5 }
    .intent b { color: #0f766e }
    /* cover */
    .cover { page: cover; height: 290mm; justify-content: center; align-items: flex-start;
             background: #0b1f1d; color: #e7f5f2 }
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
      <div class="tree">Walkthrough<br>Startup &rsaquo; { '{' } Strategy &rsaquo; [ Pick components, Vault &amp; Matrix ], Configuration { '}' }<br>
      Flow &rsaquo; [ Land, Health, Migrate ]<br>Analyze</div>
      <div class="note">These are real screenshots of the live UI, each shown in full &mdash; the marimo
      scroll shell is released at capture time so below-fold panels are not cropped. The data-driven panels
      (Health, Analyze) show their honest pre-audit / no-data states because the demo stack is not running:
      the gate never bluffs a pass, so an un-run audit reads as unmeasured, not green. Regenerate this PDF
      with <b>bash flipthrough/build.sh</b> after a console change.</div>
    </div>""")
    for key, bc, _clicks, ann in VIEWS:
        pages.append(f"""<div class="page page-{key}">
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
