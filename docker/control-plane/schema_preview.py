"""Setup schema preview (Phase E, PE-3): for the chosen standard, show the classes the stack normalizes
data INTO and their key fields — "your data lands in these OCSF classes, with these fields". Grounded in
the console's own crosswalk (the classes its routers actually produce — see config_preview.CROSSWALK) and
the OCSF 1.8.0 / CON-AUTH-1 canonical field set verified this session. Pure (no IO); the panel renders it."""
from __future__ import annotations

# The OCSF classes the MOAR routers normalize into (the console's real target shape), with the key fields
# its pipeline populates. CON-AUTH-1 canonical: activity_id = the operation; success/failure lives in
# status_id, NOT activity_id. CloudTrail non-login API -> API Activity 6003 (category 6, not 3005).
OCSF_CLASSES = {
    3002: {"name": "Authentication", "category_uid": 3,
           "key_fields": ["class_uid=3002", "category_uid=3", "activity_id (1 Logon — the operation)",
                          "status_id (1 Success / 2 Failure — the outcome)", "user", "src_ip", "time"]},
    4001: {"name": "Network Activity", "category_uid": 4,
           "key_fields": ["class_uid=4001", "category_uid=4", "activity_id", "src_ip", "dst_ip",
                          "dst_port", "bytes_in", "bytes_out", "time"]},
    1007: {"name": "Process Activity", "category_uid": 1,
           "key_fields": ["class_uid=1007", "category_uid=1", "activity_id (1 Launch)", "process.name",
                          "process.cmd_line", "actor.process", "actor.user", "device.hostname", "time"]},
    6003: {"name": "API Activity", "category_uid": 6,
           "key_fields": ["class_uid=6003", "category_uid=6", "activity_id (CRUD verb)", "api.operation",
                          "actor.user", "src_ip", "time"]},
}

# Source -> the class(es) that source's router produces, mirroring config_preview.CROSSWALK / SOURCES.
SOURCE_CLASSES = {"okta": [3002], "zeek": [4001], "sysmon": [1007], "cloudtrail": [3002, 6003]}


def classes_for(standard, sources=None):
    """Pure: the OCSF classes to preview for `standard`. OCSF -> the classes the routers produce (scoped to
    `sources` when given, else all known); a non-OCSF standard -> [] (the console normalizes to OCSF only)."""
    if (standard or "").lower() != "ocsf":
        return []
    if sources:
        uids = sorted({u for s in sources for u in SOURCE_CLASSES.get(str(s).lower(), [])})
    else:
        uids = sorted(OCSF_CLASSES)
    return [{"class_uid": u, **OCSF_CLASSES[u]} for u in uids if u in OCSF_CLASSES]


def schema_preview_panel(mo, ui, standard, sources=None):
    """Render the landed-schema preview for the chosen standard. OCSF-only; honest note otherwise."""
    classes = classes_for(standard, sources)
    if not classes:
        body = (f"*The console normalizes to **OCSF**; no schema preview for standard `{standard}`.*"
                if standard and str(standard).lower() != "ocsf"
                else "*Pick **OCSF** as the schema standard to preview the classes your data lands in.*")
        return ui.panel(mo, ui.header(mo, "Schema preview"), mo.md(body))
    rows = "\n".join(
        f"- **{c['name']}** (`class_uid {c['class_uid']}`, category {c['category_uid']}) — "
        + ", ".join(f"`{f}`" for f in c["key_fields"])
        for c in classes)
    head = (f"**OCSF 1.8.0** — your data lands in {len(classes)} class(es). Every record carries "
            "`class_uid` + `category_uid`; the key fields per class:")
    return ui.panel(mo, ui.header(mo, "Schema preview"), mo.md(head + "\n\n" + rows))
