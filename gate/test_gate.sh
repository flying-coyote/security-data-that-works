#!/usr/bin/env bash
# Regression test for the gate. It checks six things:
#   1. the correct mapping passes, and its output matches expected/correct.out
#   2. the wrong mapping without the layer passes silently (expected/wrong-nolayer.out)
#   3. the wrong mapping with the layer fails, and its output matches expected/wrong.out
#   4. a broken reasoner (a corrupt jar, a missing jar) exits 2 and never reports a pass,
#      both from the validator and from run.sh
#   5. a bad input file (missing, empty, semicolon-delimited, or columns swapped so that no
#      row is type-testable) exits 2, and a data row whose source field is "source" is still
#      checked rather than dropped as a header
#   6. a disjointness layer made inconsistent (Session added to the set) stops a mapping run
#      with exit 2, never exit 1
#
# Default runs the reasoner in the sdtw-gate Docker image, like run.sh. With LOCAL=1 it uses
# a local Java plus $ROBOT_JAR (default /tmp/robot.jar; with that file absent every scenario
# check fails, closed). Exit 0 means every check passed, 2 means the image would not build,
# and 1 means at least one check failed.
#
# To regenerate a golden after an intended output change, run with UPDATE=1; it rewrites
# expected/<name>.out in the exact format diffed here (the validator's stdout without the
# JVM WARNING lines, plus a final "<name> exit=N" line this script appends).
set -uo pipefail
cd "$(dirname "$0")"

# The scratch dir sits under the gate dir rather than /tmp, because on Docker Desktop with WSL
# a /tmp bind mount shows up empty inside the container, and a missing broken.jar would then
# pass the corrupt-jar checks through the missing-jar path. .tmp-*/ is gitignored.
TMP="$(mktemp -d "$PWD/.tmp-XXXX")"
trap 'rm -rf "$TMP"' EXIT
fails=0

run() {  # run <robot_jar_path_or_empty> <args...>
  local jar="$1"; shift
  run_script validate_ocsf_mapping.py "$jar" "$@"
}

run_script() {  # run_script <script> <robot_jar_path_or_empty> <args...>
  local script="$1" jar="$2"; shift 2
  if [ "${LOCAL:-0}" = "1" ]; then
    ROBOT_JAR="${jar:-${ROBOT_JAR:-/tmp/robot.jar}}" python3 -B "$script" "$@"
  else
    docker run --rm -e ROBOT_JAR="${jar:-/opt/robot.jar}" -v "$PWD:/work" -v "$TMP:/scratch" \
      -w /work sdtw-gate python3 -B "$script" "$@"
  fi
}

if [ "${LOCAL:-0}" != "1" ]; then
  docker build -q -t sdtw-gate ../docker >/dev/null || { echo "docker build failed"; exit 2; }
  JAR_DIR=/scratch
else
  JAR_DIR="$TMP"
fi

check() {  # check <label> <condition-result 0|1>
  if [ "$2" = "0" ]; then echo "ok   $1"; else echo "FAIL $1"; fails=$((fails + 1)); fi
}

scenario() {  # scenario <name> <expected-file> <expected-exit> <args...>
  local name="$1" exp="$2" want="$3"; shift 3
  { run "" "$@" 2>/dev/null; echo "$name exit=$?"; } | grep -v '^WARNING' > "$TMP/$name.out"
  if [ "${UPDATE:-0}" = "1" ]; then cp "$TMP/$name.out" "$exp"; echo "updated $exp"; fi
  diff -u "$exp" "$TMP/$name.out" > "$TMP/$name.diff"
  check "$name matches $exp" $?
  grep -q "^$name exit=$want\$" "$TMP/$name.out"
  check "$name exits $want" $?
  [ -s "$TMP/$name.diff" ] && cat "$TMP/$name.diff"
}

scenario correct expected/correct.out        0 mappings/correct.csv
scenario nolayer expected/wrong-nolayer.out  0 --no-layer mappings/wrong.csv
scenario wrong   expected/wrong.out          1 mappings/wrong.csv

# A corrupt jar: before the 2026-11-17 fix this printed "selfcheck YES, 0 flagged" and exit 0.
printf 'not a jar\n' > "$TMP/broken.jar"
for args in "mappings/wrong.csv" "--selfcheck" "--no-layer mappings/wrong.csv"; do
  # shellcheck disable=SC2086
  out="$(run "$JAR_DIR/broken.jar" $args 2>&1)"; rc=$?
  [ "$rc" = "2" ]; check "broken jar ($args) exits 2 (got $rc)" $?
  ! grep -qE 'consistent\? YES|0 type-crossing flagged' <<<"$out"
  check "broken jar ($args) reports no pass" $?
  # It must fail through the corrupt-jar branch, not the missing-jar one.
  grep -qE 'corrupt jarfile|Invalid or corrupt|ROBOT reason failed' <<<"$out"
  check "broken jar ($args) fails as a corrupt jar, not a missing one" $?
done

# run.sh itself must stop on a tool failure rather than print a pass or a catch. This runs
# in LOCAL mode in both modes, because it needs a broken jar the image doesn't have; with no
# local Java the validator still exits 2 ("java not found"), which is the same contract.
out="$(LOCAL=1 ROBOT_JAR="$TMP/broken.jar" bash run.sh 2>&1)"; rc=$?
[ "$rc" = "2" ]; check "run.sh with a broken jar exits 2 (got $rc)" $?
! grep -qE '=> exit 0  PASS|caught, as it should be' <<<"$out"
check "run.sh with a broken jar reports no pass and no catch" $?

# A missing jar.
out="$(run "$JAR_DIR/does-not-exist.jar" mappings/wrong.csv 2>&1)"; rc=$?
[ "$rc" = "2" ]; check "missing jar exits 2 (got $rc)" $?
grep -q 'ROBOT not found' <<<"$out"; check "missing jar says ROBOT not found" $?

# Bad input files: a missing CSV, an empty CSV and a semicolon-delimited CSV must each exit 2,
# never 0 (a pass on zero rows) and never 1 (read as a caught crossing by run.sh).
: > "$TMP/empty.csv"
printf 'source_field;ocsf_path\nUser;actor.user.name\n' > "$TMP/semicolon.csv"
for f in does-not-exist.csv empty.csv semicolon.csv; do
  if [ "${LOCAL:-0}" = "1" ]; then p="$TMP/$f"; else p="/scratch/$f"; fi
  out="$(run "" --no-layer "$p" 2>&1)"; rc=$?
  [ "$rc" = "2" ]; check "input $f exits 2 (got $rc)" $?
done

# Columns swapped: every row parses, but none is type-testable, which used to print
# "0 type-testable · 0 type-crossing flagged" and exit 0.
printf 'ocsf_path,source_field\nprocess.name,username\nsrc_endpoint.ip,file_path\n' > "$TMP/swapped.csv"
# A data row whose source field is literally "source" (a NetworkNode) mapped to a Process
# path must be checked and flagged, not skipped as a header.
printf 'source_field,ocsf_path\nsource,process.name\n' > "$TMP/source-row.csv"
if [ "${LOCAL:-0}" = "1" ]; then d="$TMP"; else d=/scratch; fi
out="$(run "" "$d/swapped.csv" 2>&1)"; rc=$?
[ "$rc" = "2" ]; check "input swapped.csv (no type-testable row) exits 2 (got $rc)" $?
out="$(run "" "$d/source-row.csv" 2>&1)"; rc=$?
[ "$rc" = "1" ]; check "a data row with source field \"source\" is checked and flagged (got $rc)" $?

# An inconsistent layer must stop a mapping run with exit 2. The copy adds Session to the
# disjoint set, which D3FEND's NetworkSession subclass axiom makes inconsistent.
sed 's/"URL", "ServiceApplication"\]/"URL", "ServiceApplication", "Session"]/' \
  validate_ocsf_mapping.py > "$TMP/inconsistent_layer.py"
grep -q '"ServiceApplication", "Session"\]' "$TMP/inconsistent_layer.py"
check "inconsistent-layer copy was built" $?
cp -r mappings "$TMP/"
out="$(run_script "$d/inconsistent_layer.py" "" "$d/mappings/correct.csv" 2>&1)"; rc=$?
[ "$rc" = "2" ]; check "inconsistent layer stops a mapping run with exit 2 (got $rc)" $?
grep -q 'layer is inconsistent' <<<"$out"; check "inconsistent layer says so" $?

echo
if [ "$fails" = "0" ]; then echo "all gate checks passed"; exit 0; fi
echo "$fails gate check(s) failed"; exit 1
