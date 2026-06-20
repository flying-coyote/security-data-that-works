"""OCSF round-trip semantic validation — does the transform mean what it should?

Cluster-5 / "field-mapping correctness is not schema correctness" (context-collapse and
silent-wrong-answer findings): a mapping can satisfy the OCSF schema and still carry the
wrong meaning. Schema-shape conformance (layer3) is necessary but not sufficient. This is
the value-level check on top: a small set of known-good test events runs through the
(caller-run) transform, and each produced OCSF record must contain the expected fields
with the expected values.

Pure logic over {expected, produced} pairs; running events through the deployed VRL
transform is the caller's job. Status vocabulary matches CONTRACT.md.
"""
from __future__ import annotations

_MISSING = object()


def _get(record, path):
    """Resolve a dotted OCSF path (e.g. 'src_endpoint.ip') against a nested dict."""
    cur = record
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return _MISSING
        cur = cur[part]
    return cur


def check_event(expected, produced) -> dict:
    """expected: {ocsf_path: value} the transform must yield. produced: the OCSF record it
    actually emitted (nested dict). Returns {status, mismatches:[{path, expected, got, why}]}.
    status: pass only if every expected path is present with the expected value."""
    mismatches = []
    for path, want in (expected or {}).items():
        got = _get(produced or {}, path)
        if got is _MISSING:
            mismatches.append({"path": path, "expected": want, "got": None, "why": "missing"})
        elif got != want or (isinstance(got, bool) is not isinstance(want, bool)):
            # The bool clause defeats Python's 0==False / 1==True trap: a produced 0 must
            # not satisfy an expected False (nor 1 an expected True): a different OCSF meaning.
            mismatches.append({"path": path, "expected": want, "got": got, "why": "wrong-value"})
    return {"status": "pass" if not mismatches else "fail", "mismatches": mismatches}


def validate(pairs) -> dict:
    """pairs: [{expected, produced}] for a source's test events. Aggregate:
    unmeasured if there are no test events; fail if any event fails; pass otherwise."""
    if not pairs:
        return {"status": "unmeasured", "events": [], "note": "no test events supplied"}
    events = [check_event(p.get("expected"), p.get("produced")) for p in pairs]
    status = "fail" if any(e["status"] == "fail" for e in events) else "pass"
    return {"status": status, "events": events,
            "fail_count": sum(1 for e in events if e["status"] == "fail")}
