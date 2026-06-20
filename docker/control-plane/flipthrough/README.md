# Console flip-through (visual walkthrough)

`MOAR-console-flipthrough.pdf` is a flip-through of each console view — a real screenshot of
each view captured from the live marimo app, with the intent annotated underneath. Regenerate
it after a console change (and before pushing a new console version):

```bash
bash flipthrough/build.sh
```

It exports the app to static HTML (a small pulumi stub stands in so the deploy module imports;
the deploy feature isn't needed for screenshots), screenshots each view with Playwright/Chromium,
and renders the annotated pages to PDF with headless Chrome. With the demo stack down, the
data-driven panels (Health, Analyze) show their honest pre-audit / no-data states — the gate
never bluffs a pass, so an un-run audit reads as unmeasured, not green.

Requirements: a venv with `marimo` + `pandas` + `pyiceberg` (override with `MARIMO_VENV`),
`playwright` with a chromium browser (system python3 here), and `google-chrome`.
