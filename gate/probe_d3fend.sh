#!/usr/bin/env bash
# Re-derives the off-the-shelf claim behind Scenario 2: that D3FEND's own disjointness axioms
# separate none of the eight artifacts the gate grounds to. It fetches the D3FEND source
# ontology and its catalog extension at a release tag, adds one probe class under each of the
# 28 pairs of those artifacts plus two positive controls under pairs D3FEND does declare
# disjoint, and reasons over the lot with ELK. The expected result is that only the two
# control probes come back unsatisfiable.
#
# Usage: ./probe_d3fend.sh [tag]        (default tag 1.6.0)
# Runs in the sdtw-gate Docker image like run.sh; LOCAL=1 uses a local Java and $ROBOT_JAR.
# Needs network access to raw.githubusercontent.com. Exit 0 when the result is as expected.
set -uo pipefail
cd "$(dirname "$0")"
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
unsat="$(grep -o 'probe#[A-Za-z_]*' "$TMP/unsat.owl" 2>/dev/null | sed 's/probe#//' | sort -u)"
echo "ROBOT exit $rc; unsatisfiable probes:"
echo "${unsat:-  (none)}" | sed 's/^/  /'
expected=$'Agent__Artifact\nFastSymbolicLink__SlowSymbolicLink'
if [ "$unsat" = "$expected" ]; then
  echo "as expected: no D3FEND $TAG axiom separates any two of the eight artifacts; both controls fire"
  exit 0
fi
echo "unexpected result; see the ROBOT log:"; tail -5 "$TMP/robot.log"; exit 1
