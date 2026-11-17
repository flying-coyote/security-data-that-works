#!/usr/bin/env bash
# The whole demo in one command: watch a correct mapping pass, a wrong mapping pass
# SILENTLY without the disjointness layer, and the same wrong mapping FAIL once the layer
# is in. The third run is the one that matters.
#
# Default runs in Docker, so you don't install Java or ROBOT. To run against a local
# ROBOT jar instead (faster if you already have one), set LOCAL=1 and, optionally,
# ROBOT_JAR=/path/to/robot.jar (defaults to /tmp/robot.jar).
#
# The validator exits 0 (consistent), 1 (type-crossing found) or 2 (the reasoner itself
# failed). Each scenario branches on the exact code, so a broken reasoner stops the demo
# instead of reading as a pass or as a catch. This script exits 0 only when all three
# scenarios behave as described.
set -uo pipefail
cd "$(dirname "$0")"

run() {
  if [ "${LOCAL:-0}" = "1" ]; then
    python3 validate_ocsf_mapping.py "$@"
  else
    docker run --rm -e ROBOT_JAR=/opt/robot.jar -v "$PWD:/work" -w /work sdtw-gate \
      python3 validate_ocsf_mapping.py "$@"
  fi
}

tool_failed() {
  echo "    => exit $1: the reasoner did not run cleanly, so this scenario proves nothing; see the error above"
  exit 2
}

if [ "${LOCAL:-0}" != "1" ]; then
  echo "==> building the reasoner image (Java + ROBOT, one time)…"
  docker build -q -t sdtw-gate ../docker >/dev/null || { echo "docker build failed"; exit 2; }
fi

echo
echo "### Scenario 1: a CORRECT mapping, with the disjointness layer"
echo "    Expect: PASS. Every mapping is type-consistent."
run mappings/correct.csv; rc=$?
case $rc in
  0) echo "    => exit 0  PASS" ;;
  1) echo "    => exit 1  unexpected FAIL on the correct mapping"; exit 1 ;;
  *) tool_failed "$rc" ;;
esac

echo
echo "### Scenario 2: a WRONG mapping, WITHOUT the disjointness layer"
echo "    This models D3FEND off the shelf: in release 1.6.0 none of its disjointness axioms"
echo "    separates any two of these artifacts, so the reasoner has no basis to object."
echo "    Expect: PASS, silently. That silence is the bug."
run --no-layer mappings/wrong.csv; rc=$?
case $rc in
  0) echo "    => exit 0  PASS (silently: the wrong mapping slips through)" ;;
  1) echo "    => exit 1  flagged (unexpected without the layer)"; exit 1 ;;
  *) tool_failed "$rc" ;;
esac

echo
echo "### Scenario 3: the SAME WRONG mapping, WITH the disjointness layer"
echo "    Expect: FAIL. Each type-crossing becomes an unsatisfiable class and the build breaks."
run mappings/wrong.csv; rc=$?
case $rc in
  1) echo "    => exit 1  FAIL, caught, as it should be" ;;
  0) echo "    => exit 0  (unexpected: nothing caught)"; exit 1 ;;
  *) tool_failed "$rc" ;;
esac

echo
echo "The same mapping that passed silently in Scenario 2 fails the build in Scenario 3,"
echo "because the disjointness layer gives the reasoner something to object to, and that is"
echo "the difference between a detection that quietly never fires and one you can trust."
