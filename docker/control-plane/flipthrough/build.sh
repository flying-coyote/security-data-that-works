#!/usr/bin/env bash
# Build the MOAR console flip-through PDF: export the live app -> screenshot each view ->
# annotate -> PDF. Regenerate after a console change (and before pushing a new version).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
CP="$(dirname "$HERE")"                                   # docker/control-plane
VENV="${MARIMO_VENV:-$HOME/sdw-lab-benchmarks/.venv}"     # a venv with marimo + pandas + pyiceberg

# 1. pulumi stub so the deploy module imports cleanly (the deploy feature is not exercised
#    for screenshots, only imported).
STUB="$(mktemp -d)"; mkdir -p "$STUB/pulumi"
printf 'def export(*a,**k):\n pass\nclass ResourceOptions:\n def __init__(self,*a,**k): pass\n' > "$STUB/pulumi/__init__.py"
printf "def create_or_select_stack(*a,**k):\n raise RuntimeError('pulumi stub - deploy disabled in screenshot mode')\n" > "$STUB/pulumi/automation.py"
printf '# stub for screenshot mode\n' > "$STUB/pulumi_docker.py"

# 2. export the app to a static HTML with baked outputs (hydrating JS, so tabs still work).
EXPORT_LOG="$(mktemp)"
( cd "$CP" && PYTHONPATH="$STUB" VAULT_PATH="${VAULT_PATH:-$HOME/project1}" \
    "$VENV/bin/marimo" export html --no-include-code control_plane.py -o /tmp/cp_app.html ) >"$EXPORT_LOG" 2>&1 || true
rm -rf "$STUB"
[ -s /tmp/cp_app.html ] || { echo "marimo export failed — no /tmp/cp_app.html"; cat "$EXPORT_LOG"; rm -f "$EXPORT_LOG"; exit 1; }
# Fail-fast on cell-execution errors. A baked app with a failed cell screenshots BLANK panels
# (the failed cell + its descendants render nothing), which would ship a misleading flip-through —
# the exact opposite of "real screenshots of the live UI". The honest result is to FAIL here, not
# to capture blanks. (export html executes the cells; `marimo export script` only checks the graph,
# so this is the one gate that catches a runtime cell error.)
if grep -qE "failed to execute|MarimoExceptionRaisedError" "$EXPORT_LOG"; then
  echo "ERROR: the marimo app has cell-execution failures — refusing to build a blank flip-through:"
  grep -E "failed to execute|MarimoExceptionRaisedError|^Error:" "$EXPORT_LOG" | head -20
  rm -f "$EXPORT_LOG"; exit 1
fi
rm -f "$EXPORT_LOG"

# 3. screenshot each view (Playwright/Chromium) + assemble the annotated HTML.
( cd "$CP" && python3 "$HERE/capture.py" )

# 4. render the annotated pages to PDF (headless Chrome). DBus/UPower warnings are harmless.
google-chrome --headless=new --no-sandbox --disable-gpu --no-pdf-header-footer \
  --print-to-pdf="$HERE/MOAR-console-flipthrough.pdf" "$HERE/flipthrough.html"
echo "built $HERE/MOAR-console-flipthrough.pdf"
