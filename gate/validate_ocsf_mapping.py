#!/usr/bin/env python3
"""
ocsf-mapping-lint — a model-independent CI check for OCSF field mappings.

It flags TYPE-CROSSING field mappings: a source field whose meaning is an *actor*
(a user, a process) mapped onto an OCSF path whose meaning is an *object* (a file, a
host), or the reverse. Those are the silent, dangerous mapping errors — the field looks
populated, it passes schema validation, but it holds the wrong kind of thing, so the
detection downstream quietly matches nothing.

The check is a logic gate: an OWL reasoner (ELK, via ROBOT) over a hand-authored
disjointness layer. No machine-learning model is in the loop, so the verdict is the same
whether a frontier model, a small local model, or a tired engineer produced the mapping —
which is what makes it usable in regulated / air-gapped / safety-critical pipelines that
need deterministic verifiability before automated countermeasures fire.

What this answers: "is this mapping type-consistent?" — yes/no, per row. It does NOT rank a
vendor or score fidelity; that is a separate, non-donated layer.

Usage:
    python3 validate_ocsf_mapping.py mappings.csv      # CSV: source_field,ocsf_path
    python3 validate_ocsf_mapping.py --no-layer m.csv  # same, WITHOUT the disjointness
                                                       # layer — shows what the reasoner
                                                       # can't object to off the shelf
    python3 validate_ocsf_mapping.py --selfcheck       # check the layer against the
                                                       # validator's small D3FEND stub
    python3 validate_ocsf_mapping.py --allow-untestable m.csv  # accept a file in which
                                                       # no row is type-testable

Exit codes (CI-friendly): 0 = every type-testable mapping is consistent; 1 = at least one
mapping is type-crossing (or --selfcheck found the layer inconsistent); 2 = the reasoner
itself failed (Java missing, corrupt jar, parse error, timeout), the layer was inconsistent
at the start of a mapping run, or the mapping CSV is missing, unreadable, parses to zero
rows or has no type-testable row (swapped columns or unrecognised field names, unless
--allow-untestable is given). A tool or input failure never reports a pass.
Requires ROBOT (https://robot.obolibrary.org) on $ROBOT_JAR or /tmp/robot.jar, plus Java.

Honest scope (Tier B): the disjointness layer is adjudicated over 8 artifacts. On a
925-row six-schema corpus, 231 of 231 injected crossings were flagged, which is true by
construction of the injection (each sound mapping was corrupted to a disjoint artifact), so
it shows the check runs end to end rather than measuring a catch rate; the measured result
there is 15 firings on the 231 presumed-correct mapping classes (6.5%), none traced to a
bad disjointness axiom: about 7 came from the approximate field-typer and about 8 were
coarse mappings worth a human look, plausible rather than confirmed wrong. On a separate 83-field mapping it had never seen, 22 of the 83
fields were type-testable; the 22 injected crossings were again flagged by construction, and the
measured result is 0 false positives on the 22 sound mappings. Nothing here is measured on a
held-out set of confirmed human errors. The false-positive risk rises as the artifact set
widens, so treat this as a strong first-pass check rather than a certification, and the
layer as a starting set to extend rather than a finished ontology.
"""
import csv
import os
import re
import subprocess
import sys
import tempfile

ROBOT = os.environ.get("ROBOT_JAR", "/tmp/robot.jar")
D3F = "http://d3fend.mitre.org/ontologies/d3fend.owl#"
NS = "https://schema.ocsf.io/align#"

# --- the donated disjointness layer (D3FEND issue #423 invited this) ----------------
# Eight D3FEND digital artifacts asserted pairwise-disjoint at the ENTITY/IDENTITY level.
# The judgement: an individual that IS a process is not also the file it was executed
# from; a credential is stored in a file but is not the file; a URL locates a file but is
# not the file. "executed-from" / "stored-in" / "locates" are relations, not identity, so
# the disjointness is sound and the "but they overlap" objection is a category error.
# Session is DELIBERATELY EXCLUDED: D3FEND has NetworkSession ⊑ Session, so asserting
# Session ⊥ NetworkSession would make NetworkSession unsatisfiable. --selfcheck catches
# that one trap only, because the validator's stub encodes no other D3FEND subclass
# axiom; after any edit to this set, also run `./probe_d3fend.sh --layer`, which reasons
# the set against the real D3FEND release.
DISJOINT_SET = ["UserAccount", "UserGroup", "Process", "File",
                "NetworkNode", "NetworkSession", "URL", "ServiceApplication"]

# OCSF path-segment → D3FEND artifact (resolve a dot-path by its deepest entity segment).
SEG_ARTIFACT = {
    "user": "UserAccount", "group": "UserGroup", "owner": "UserAccount",
    "process": "Process", "file": "File",
    "src_endpoint": "NetworkNode", "dst_endpoint": "NetworkNode",
    "endpoint": "NetworkNode", "device": "NetworkNode",
    "connection_info": "NetworkSession", "session": "Session",
    "url": "URL", "service": "ServiceApplication", "app_name": "ServiceApplication",
}
# Source-field typer (independent grounding): type by the DEEPEST matching token.
SEG_RULES = [
    ("File",        r"^(executable|image|file|filename|filepath|filehash|md5|sha\d+|dll|binary|exe)$"),
    ("UserAccount", r"^(user|username|userid|owner|principal|account|sam|upn|real_user|effective_user|target_user|src_user)$"),
    ("UserGroup",   r"^(group|groupname|usergroup)$"),
    ("Process",     r"^(process|cmdline|commandline|command_line|pid|proc|parent)$"),
    ("URL",         r"^(url|uri|referer|referrer)$"),
    ("ServiceApplication", r"^(application|service|appname|app)$"),
    ("NetworkSession", r"^(connection|conn|session|sessionid|flow|socket|netflow|communityid|community_id)$"),
    ("NetworkNode", r"^(ip|ipv4|ipv6|host|hostname|src|dst|dest|destination|source|address|addr|endpoint|device|machine|node|port)$"),
]


def source_type(field):
    f = re.sub(r"[`*~]", "", field).strip().lower()
    if not f or f in ("—", "-", "const"):
        return None
    art = None
    for s in re.split(r"[._ ]", f):
        for a, pat in SEG_RULES:
            if re.match(pat, s):
                art = a
    return art


def ground_path(path):
    art = None
    for s in [p.replace("[]", "") for p in path.split(".")]:
        if s in SEG_ARTIFACT:
            art = SEG_ARTIFACT[s]
        elif (s + "_endpoint") in SEG_ARTIFACT:
            art = SEG_ARTIFACT[s + "_endpoint"]
    return art


def _prefix(with_layer=True):
    arts = sorted(set(SEG_ARTIFACT.values()) | set(DISJOINT_SET) | {"Session"})
    ttl = ("@prefix owl: <http://www.w3.org/2002/07/owl#> .\n"
           "@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
           f"@prefix d3f: <{D3F}> .\n@prefix ocsf: <{NS}> .\n"
           f"<{NS.rstrip('#')}> a owl:Ontology .\n"
           + "".join(f"d3f:{a} a owl:Class .\n" for a in arts)
           + "d3f:NetworkSession rdfs:subClassOf d3f:Session .\n")
    if with_layer:
        ttl += ("[] a owl:AllDisjointClasses ; owl:members ( "
                + " ".join(f"d3f:{c}" for c in DISJOINT_SET) + " ) .\n")
    return ttl


EXIT_TOOL_ERROR = 2  # the reasoner itself failed; distinct from exit 1 (crossing found)


def _tool_error(msg, proc=None):
    """Fail closed. A broken reasoner must never read as 'nothing flagged'."""
    detail = ""
    if proc is not None:
        lines = [l for l in (proc.stderr + proc.stdout).splitlines()
                 if l.strip() and not l.startswith("WARNING")]
        detail = "\n  " + "\n  ".join(lines[-5:]) if lines else ""
    print(f"ERROR: {msg}{detail}", file=sys.stderr)
    sys.exit(EXIT_TOOL_ERROR)


def reason(ttl):
    """Return the set of unsatisfiable ocsf-namespace classes, or exit 2 on tool failure.

    ROBOT `reason` exits 0 and writes --output when every class is satisfiable, and exits
    non-zero and writes --dump-unsatisfiable when some class is not. Anything else (Java
    missing, a corrupt jar, a parse error, an inconsistent ontology, a timeout) is a tool
    failure and stops the run with exit 2 rather than reporting a clean pass.
    """
    if not os.path.exists(ROBOT):
        _tool_error(f"ROBOT not found at {ROBOT}; set $ROBOT_JAR (https://robot.obolibrary.org)")
    with tempfile.TemporaryDirectory() as td:
        inp, dump, out = (os.path.join(td, x) for x in ("in.ttl", "u.owl", "o.owl"))
        with open(inp, "w") as fh:
            fh.write(ttl)
        try:
            proc = subprocess.run(["java", "-jar", ROBOT, "reason", "--reasoner", "ELK",
                                   "--input", inp, "--dump-unsatisfiable", dump, "--output", out],
                                  capture_output=True, text=True, timeout=300)
        except FileNotFoundError:
            _tool_error("java not found on PATH; the reasoner did not run")
        except subprocess.TimeoutExpired:
            _tool_error("ROBOT reason timed out after 300s; the reasoner did not finish")
        if proc.returncode == 0:
            if not os.path.exists(out):
                _tool_error("ROBOT exited 0 but wrote no reasoned output", proc)
            return set()
        if os.path.exists(dump):
            with open(dump) as fh:
                unsat = set(re.findall(r"align#([A-Za-z0-9_]+)", fh.read()))
            if unsat:
                return unsat
            _tool_error("ROBOT reported unsatisfiable classes, none in the mapping namespace", proc)
        _tool_error(f"ROBOT reason failed (exit {proc.returncode}) without an unsatisfiable-class dump", proc)


def selfcheck():
    ttl = _prefix(with_layer=True)
    for art in sorted(set(SEG_ARTIFACT.values())):
        ttl += f"ocsf:probe_{art} a owl:Class ; rdfs:subClassOf d3f:{art} .\n"
    unsat = reason(ttl)
    ok = not unsat
    print(f"[selfcheck] disjointness layer consistent? {'YES' if ok else 'NO: ' + str(sorted(unsat))}")
    return ok


def validate(rows, with_layer=True, allow_untestable=False):
    ttl, classes = _prefix(with_layer=with_layer), {}
    for i, (src, ocsf) in enumerate(rows):
        tart, sart = ground_path(ocsf), source_type(src)
        if tart and sart:
            c = f"M{i}_" + re.sub(r"[^A-Za-z0-9]", "_", f"{src}__{ocsf}")
            ttl += f"ocsf:{c} a owl:Class ; rdfs:subClassOf d3f:{tart} ; rdfs:subClassOf d3f:{sart} .\n"
            classes[c] = (src, ocsf, sart, tart)
    # Zero type-testable rows would otherwise be a vacuous pass: nothing reasoned, nothing
    # flagged, exit 0. Treat it as an input failure unless the caller opts out.
    if not classes and not allow_untestable:
        _tool_error(f"none of the {len(rows)} mappings is type-testable, so a pass would be vacuous; "
                    "likely causes are swapped columns (expected source_field,ocsf_path) or field "
                    "names the typer does not recognise. Pass --allow-untestable to accept this.")
    unsat = reason(ttl)
    crossings = [(s, o, sa, ta) for c, (s, o, sa, ta) in classes.items() if c in unsat]
    layer = "with disjointness layer" if with_layer else "WITHOUT disjointness layer"
    print(f"checked {len(rows)} mappings · {len(classes)} type-testable · "
          f"{len(crossings)} type-crossing flagged ({layer})")
    for s, o, sa, ta in crossings:
        print(f"  ✗ {s}  →  {o}   (source is {sa}, target is {ta} — disjoint)")
    if not crossings and not with_layer:
        print("  (nothing flagged — off the shelf, the reasoner has no basis to object;"
              " the wrong mapping passes silently)")
    return crossings


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    if "--selfcheck" in flags:
        sys.exit(0 if selfcheck() else 1)
    if not args:
        sys.exit(__doc__)
    with_layer = "--no-layer" not in flags
    if with_layer and not selfcheck():
        # exit 2, not 1: a broken layer is a tool failure, never a caught crossing
        _tool_error("disjointness layer is inconsistent; fix before validating")
    # An unreadable or empty mapping file is a tool failure (exit 2), never a pass and never
    # a "type-crossing found" (exit 1).
    try:
        with open(args[0], newline="") as fh:
            # Skip a header only on the first line, so a data row whose source field is
            # literally "source" is still checked.
            rows = [(r[0].strip(), r[1].strip()) for n, r in enumerate(csv.reader(fh))
                    if len(r) >= 2
                    and not (n == 0 and r[0].strip().lower() in ("source_field", "source"))]
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        _tool_error(f"could not read mapping CSV {args[0]}: {e}")
    if not rows:
        _tool_error(f"no mappings parsed from {args[0]}; expected comma-separated "
                    "source_field,ocsf_path rows (wrong delimiter, missing columns or empty file?)")
    sys.exit(1 if validate(rows, with_layer=with_layer,
                           allow_untestable="--allow-untestable" in flags) else 0)
