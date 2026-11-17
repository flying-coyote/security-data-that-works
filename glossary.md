# Glossary

A few terms this demo uses, in plain language, since none of them is as academic as it sounds.

**Ontology** is an agreed map of what the things in your data actually are and how they connect, such as a
process, a file, a user account, a network node, and the real relationships between them, written
down in a form a machine can check. D3FEND is the one used here.

**Semantics** is what the data *means*, as opposed to what *shape* it's in. "There's a field called
`dst_ip` holding an IP address" is shape. "This is the address the connection went *to*, not the one
it came from" is semantics. Schema validation checks shape; this gate checks semantics.

**Grounding** is tying a field to a shared, checkable definition, so instead of "I called this field
`process` and I hope that's right" you've said "this `process` field is the same kind of thing
D3FEND calls a Process," and now a tool can verify it. The gate grounds each mapping two ways: by the
OCSF path it targets, and by the source field itself.

**Disjointness** is an assertion that two kinds of thing can't be the same individual, so a process is
not a user account, a file is not a network node, even when they're related to each other. This is
the assertion that gives the reasoner something to object to. D3FEND 1.6.0 carries a handful of
disjointness axioms (three pairwise assertions and seven multi-class groups across its source ontology and
catalog extension), but
none of them separates any two of the eight artifacts this gate grounds to, which is why the wrong
mapping passes silently until you add the layer.

**Reasoner** is the program that works out what logically follows from what you've told it. This demo
uses ELK, run through a tool called ROBOT. It runs in seconds on a laptop, not a cluster.

**Unsatisfiable** describes a class the reasoner has proven can't possibly have any members, an impossibility.
When a mapping is grounded as two disjoint kinds of thing at once (a process *and* a user account),
that's a logical contradiction, so the class is unsatisfiable, and the build fails instead of the
detection silently going dark.
