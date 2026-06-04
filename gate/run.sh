#!/usr/bin/env bash
# The whole demo in one command: watch a correct mapping pass, a wrong mapping pass
# SILENTLY without the disjointness layer, and the same wrong mapping FAIL once the layer
# is in. The third run is the point.
#
# Default runs in Docker, so you don't install Java or ROBOT. To run against a local
# ROBOT jar instead (faster if you already have one), set LOCAL=1 and, optionally,
# ROBOT_JAR=/path/to/robot.jar (defaults to /tmp/robot.jar).
set -euo pipefail
cd "$(dirname "$0")"

run() {
  if [ "${LOCAL:-0}" = "1" ]; then
    python3 validate_ocsf_mapping.py "$@"
  else
    docker run --rm -e ROBOT_JAR=/opt/robot.jar -v "$PWD:/work" -w /work sdtw-gate \
      python3 validate_ocsf_mapping.py "$@"
  fi
}

if [ "${LOCAL:-0}" != "1" ]; then
  echo "==> building the reasoner image (Java + ROBOT, one time)…"
  docker build -q -t sdtw-gate ../docker >/dev/null
fi

echo
echo "### Scenario 1 — a CORRECT mapping, with the disjointness layer"
echo "    Expect: PASS. Every mapping is type-consistent."
if run mappings/correct.csv; then echo "    => exit 0  PASS"; else echo "    => unexpected FAIL"; exit 1; fi

echo
echo "### Scenario 2 — a WRONG mapping, WITHOUT the disjointness layer"
echo "    This is D3FEND off the shelf: it ships only 3 disjointness pairs, none among"
echo "    these artifacts, so the reasoner has no basis to object."
echo "    Expect: PASS — silently. That silence is the bug."
if run --no-layer mappings/wrong.csv; then echo "    => exit 0  PASS (silently — the wrong mapping slips through)"; else echo "    => flagged (unexpected)"; fi

echo
echo "### Scenario 3 — the SAME WRONG mapping, WITH the disjointness layer"
echo "    Expect: FAIL. Each type-crossing becomes an unsatisfiable class and the build breaks."
if run mappings/wrong.csv; then echo "    => exit 0 (unexpected — nothing caught)"; else echo "    => exit 1  FAIL — caught, as it should be"; fi

echo
echo "The same mapping that passed silently in Scenario 2 fails the build in Scenario 3,"
echo "because the disjointness layer gives the reasoner something to object to. That is the"
echo "difference between a detection that quietly never fires and one you can trust."
