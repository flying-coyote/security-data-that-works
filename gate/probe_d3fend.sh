#!/usr/bin/env bash
# Re-derives the off-the-shelf claim behind Scenario 2: that D3FEND's own disjointness axioms
# separate none of the eight artifacts the gate grounds to. It fetches the D3FEND source
# ontology and its catalog extension at a release tag, adds one probe class under each of the
# 28 pairs of those artifacts plus two positive controls under pairs D3FEND does declare
# disjoint, and reasons over the lot with ELK. The expected result is that only the two
# control probes come back unsatisfiable.
#
# With --layer it runs a second check instead: it merges the validator's own disjointness
# layer (the owl:AllDisjointClasses axiom over DISJOINT_SET, read from
# validate_ocsf_mapping.py) into the same two D3FEND files and expects ROBOT to report the
# merged ontology consistent with no unsatisfiable class. This is the check to run after
# editing DISJOINT_SET, because --selfcheck only knows the one subclass axiom its stub
# encodes (NetworkSession under Session), while D3FEND carries many more (ExecutableFile
# under File, for one), and a set member that sits in another member's subclass chain makes
# the layer inconsistent.
#
# Usage: ./probe_d3fend.sh [--layer] [tag]        (default tag 1.6.0)
# Runs in the sdtw-gate Docker image like run.sh; LOCAL=1 uses a local Java and $ROBOT_JAR.
# Needs network access to raw.githubusercontent.com. Exit 0 when the result is as expected,
# 1 when the reasoner ran and the result is not (with --layer, a clash with D3FEND), and 2 when
# a download, the DISJOINT_SET read or (with --layer) the reasoner itself failed, so a missing
# jar or Java never reads as a clash.
set -uo pipefail
cd "$(dirname "$0")"
MODE=pairs
if [ "${1:-}" = "--layer" ]; then MODE=layer; shift; fi
TAG="${1:-1.6.0}"
BASE="https://raw.githubusercontent.com/d3fend/d3fend-ontology/${TAG}/src/ontology"
TMP="$(mktemp -d "$PWD/.tmp-XXXX")"   # under the gate dir so a Docker bind mount sees it
trap 'rm -rf "$TMP"' EXIT

curl -fsSL -o "$TMP/d3fend-protege.ttl" "$BASE/d3fend-protege.ttl" || { echo "download failed"; exit 2; }
curl -fsSL -o "$TMP/d3fend-catalog.ttl" "$BASE/extensions/d3fend-catalog.ttl" || { echo "download failed"; exit 2; }

echo "D3FEND $TAG disjointness axioms (source ontology / catalog extension):"
for f in d3fend-protege.ttl d3fend-catalog.ttl; do
  printf '  %-20s owl:disjointWith %s, owl:AllDisjointClasses %s\n' "$f" \
    "$(grep -c 'owl:disjointWith' "$TMP/$f")" "$(grep -c 'owl:AllDisjointClasses' "$TMP/$f")"
done

if [ "$MODE" = "layer" ]; then
  python3 -B - "$TMP/probe.ttl" <<'EOF' || { echo "could not read DISJOINT_SET from the validator"; exit 2; }
import sys
sys.path.insert(0, ".")
from validate_ocsf_mapping import D3F, DISJOINT_SET
ttl = ["@prefix owl: <http://www.w3.org/2002/07/owl#> .",
       f"@prefix d3f: <{D3F}> .",
       "<https://example.org/probe> a owl:Ontology .",
       "[] a owl:AllDisjointClasses ; owl:members ( "
       + " ".join(f"d3f:{c}" for c in DISJOINT_SET) + " ) ."]
open(sys.argv[1], "w").write("\n".join(ttl) + "\n")
print(f"  layer: owl:AllDisjointClasses over {len(DISJOINT_SET)} classes: {' '.join(DISJOINT_SET)}")
EOF
else
python3 - "$TMP/probe.ttl" <<'EOF'
import itertools, sys
arts = ["UserAccount", "UserGroup", "Process", "File",
        "NetworkNode", "NetworkSession", "URL", "ServiceApplication"]
ttl = ["@prefix owl: <http://www.w3.org/2002/07/owl#> .",
       "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .",
       "@prefix d3f: <http://d3fend.mitre.org/ontologies/d3fend.owl#> .",
       "@prefix p: <https://example.org/probe#> .",
       "<https://example.org/probe> a owl:Ontology ."]
pairs = list(itertools.combinations(arts, 2)) + [("Agent", "Artifact"),
                                                 ("FastSymbolicLink", "SlowSymbolicLink")]
for a, b in pairs:
    ttl.append(f"p:{a}__{b} a owl:Class ; rdfs:subClassOf d3f:{a} ; rdfs:subClassOf d3f:{b} .")
open(sys.argv[1], "w").write("\n".join(ttl) + "\n")
print(f"  {len(pairs) - 2} artifact-pair probes + 2 positive controls")
EOF
fi

reason() {
  local args=(merge --input d3fend-protege.ttl --input d3fend-catalog.ttl --input probe.ttl
              reason --reasoner ELK --dump-unsatisfiable unsat.owl --output reasoned.owl)
  if [ "${LOCAL:-0}" = "1" ]; then
    (cd "$TMP" && java -jar "${ROBOT_JAR:-/tmp/robot.jar}" "${args[@]}")
  else
    docker run --rm -v "$TMP:/probe" -w /probe sdtw-gate java -jar /opt/robot.jar "${args[@]}"
  fi
}
reason >"$TMP/robot.log" 2>&1
rc=$?
if [ "$MODE" = "layer" ]; then
  # ROBOT exits non-zero on an inconsistent ontology or an unsatisfiable class, and writes
  # the dump only for the latter; either one means the layer clashes with D3FEND. Any other
  # non-zero exit (a missing or corrupt jar, no Java, a Docker failure) means the reasoner did
  # not run, which is exit 2 and never a clash.
  nunsat=0
  [ -s "$TMP/unsat.owl" ] && nunsat="$(grep -c 'owl:Class' "$TMP/unsat.owl")"
  echo "ROBOT exit $rc; unsatisfiable-class dump entries: $nunsat"
  if [ "$rc" = "0" ] && [ "$nunsat" = "0" ]; then
    echo "as expected: the layer is consistent with D3FEND $TAG and makes no class unsatisfiable"
    exit 0
  fi
  if [ "$nunsat" != "0" ] || grep -q 'The ontology is inconsistent' "$TMP/robot.log"; then
    echo "the layer clashes with D3FEND $TAG; see the ROBOT log:"; tail -5 "$TMP/robot.log"; exit 1
  fi
  echo "reasoner did not run; see the ROBOT log:"; tail -5 "$TMP/robot.log"; exit 2
fi
unsat="$(grep -o 'probe#[A-Za-z_]*' "$TMP/unsat.owl" 2>/dev/null | sed 's/probe#//' | sort -u)"
echo "ROBOT exit $rc; unsatisfiable probes:"
echo "${unsat:-  (none)}" | sed 's/^/  /'
expected=$'Agent__Artifact\nFastSymbolicLink__SlowSymbolicLink'
if [ "$unsat" = "$expected" ]; then
  echo "as expected: no D3FEND $TAG axiom separates any two of the eight artifacts; both controls fire"
  exit 0
fi
echo "unexpected result; see the ROBOT log:"; tail -5 "$TMP/robot.log"; exit 1
