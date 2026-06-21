"""Configuration raw->OCSF preview — show the deployed mapping applied to a sample event.

The Configuration value moment: pick a source and SEE its raw event become an OCSF record,
field by field, with the semantic traps highlighted — the mappings where the OCSF *schema*,
not the field name, decides the answer (the part a name-based mapper gets wrong). Pure over the
sample library (../config/samples/): it reads a raw sample + its OCSF gold, picks a
representative row, and pairs raw fields to OCSF fields via a per-source crosswalk that names
which mappings are direction- or role-sensitive.

No stack: this renders the AUTHORED OCSF contract (labeled as such); the live-router version —
the same mapping run by the deployed Tenzir/Vector pipeline — is `ocsf_roundtrip_live`. Synthetic
samples only (telemetry-injection rule); the values are RFC-5737 / TEST-NET.
"""
from __future__ import annotations

import json
import os

_DEFAULT_SAMPLES = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                                  "..", "config", "samples"))

# Per-source crosswalk: class metadata, the demonstrative row to show, and the raw->OCSF field
# pairs. A note beginning with the warning glyph marks a SEMANTIC TRAP (direction / role); a plain
# note explains a non-trivial-but-safe mapping; "" is a straight copy.
_WARN = "⚠"
CROSSWALK = {
    "zeek": {
        "class_uid": 4001, "class_name": "Network Activity", "raw_kind": "zeek_tsv", "default_row": 0,
        "raw_file": "zeek_conn.sample.tsv", "gold_file": "zeek_conn.ocsf.expected.ndjson",
        "fields": [
            ("id.orig_h", "src_ip", ""),
            ("id.orig_p", "src_port", ""),
            ("id.resp_h", "dst_ip", ""),
            ("id.resp_p", "dst_port", ""),
            ("proto", "protocol_num", "string -> IANA number (tcp=6, udp=17, icmp=1)"),
            ("orig_bytes", "bytes_out",
             f"{_WARN} direction: traffic is from src_endpoint's view and orig_h->src_endpoint, so the "
             "originator's SENT bytes are bytes_OUT — a perspective-confused map inverts this "
             "(canonical: ocsf/examples Zeek conn_log)"),
            ("resp_bytes", "bytes_in", f"{_WARN} direction: the responder's bytes are bytes_IN (received by src)"),
            ("orig_pkts", "packets_out", ""),
            ("resp_pkts", "packets_in", ""),
            ("conn_state", "activity_id",
             "derived, not copied (canonical case table): SF/RSTO->2 Close | S0->4 Fail | REJ->5 Refuse | else->6 Traffic"),
        ],
    },
    "sysmon": {
        "class_uid": 1007, "class_name": "Process Activity", "raw_kind": "ndjson", "default_row": 2,
        "raw_file": "sysmon_process.sample.ndjson", "gold_file": "sysmon_process.ocsf.expected.ndjson",
        "fields": [
            ("Image", "process_path", "the NEW process is `process` (the target of the Launch)"),
            ("ProcessId", "process_pid", ""),
            ("CommandLine", "cmd_line", ""),
            ("ParentImage", "parent_path", "the PARENT is `actor.process` — not the new process"),
            ("ParentProcessId", "parent_pid", ""),
            ("User", "user",
             f"{_WARN} actor/target: the launching user is `actor.user` (the actor), not the target — "
             "the OCSF class structure resolves the 'which user?' the field name leaves open"),
            ("Computer", "hostname", ""),
        ],
    },
    "cloudtrail": {
        "class_uid": 3002, "class_name": "Authentication (ConsoleLogin)", "raw_kind": "ndjson", "default_row": 1,
        "raw_file": "cloudtrail.sample.ndjson", "gold_file": "cloudtrail.ocsf.expected.ndjson",
        "fields": [
            ("eventName", "class_uid",
             "ConsoleLogin -> Authentication 3002; other API events -> API Activity 6003 (category 6, NOT 3005)"),
            ("eventName", "activity_id", "ConsoleLogin -> 1 Logon (the operation, from the event type — not the outcome)"),
            ("responseElements.ConsoleLogin", "status_id",
             "Success -> 1 / Failure -> 2 — the outcome is status_id, not activity_id (CON-AUTH-1)"),
            ("userIdentity.userName", "user", ""),
            ("sourceIPAddress", "src_ip", ""),
            ("additionalEventData.MFAUsed", "is_mfa",
             f"{_WARN} MFA three-state: Yes->true, No->false, but ABSENT (no key) must STAY absent — a flatten "
             "that coerces a missing MFA field to 'false' silently misses unprotected logins (this row IS the absent case)"),
        ],
    },
}

SOURCES = {"zeek": "Zeek conn.log -> Network Activity (4001)",
           "sysmon": "Sysmon EventID-1 -> Process Activity (1007)",
           "cloudtrail": "AWS CloudTrail -> Authentication (3002) / API Activity (6003)"}


def _read_zeek_tsv(path):
    fields, rows = [], []
    with open(path) as f:
        for line in f:
            line = line.rstrip("\n")
            if line.startswith("#fields"):
                fields = line.split("\t")[1:]
            elif line.startswith("#") or not line.strip():
                continue
            else:
                rows.append(dict(zip(fields, line.split("\t"))))
    return rows


def _read_ndjson(path):
    with open(path) as f:
        return [json.loads(line) for line in f if line.strip()]


def _dig(d, path):
    """Resolve a raw-field path. Tries the LITERAL key first — Zeek's keys contain dots but are flat
    (`id.orig_h`) — then falls back to nested traversal so a genuinely nested source like CloudTrail
    (`responseElements.ConsoleLogin`) maps just as cleanly. Absent path -> None (the MFA-absent case)."""
    if not isinstance(d, dict):
        return None
    if path in d:
        return d[path]
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def build_preview(source, *, samples_dir=None, row_index=None) -> dict:
    """Build the raw->OCSF mapping preview for one source: the chosen raw row, the OCSF record it
    maps to, and the field-by-field crosswalk with the traps flagged. Pure; returns
    {error: <str>} (never raises) when the source is unknown or its samples are unreadable, so the
    panel degrades honestly."""
    cfg = CROSSWALK.get(source)
    if cfg is None:
        return {"source": source, "error": f"unknown source '{source}'", "rows": []}
    sd = samples_dir or _DEFAULT_SAMPLES
    try:
        raw_path = os.path.join(sd, cfg["raw_file"])
        gold_path = os.path.join(sd, cfg["gold_file"])
        raws = _read_zeek_tsv(raw_path) if cfg["raw_kind"] == "zeek_tsv" else _read_ndjson(raw_path)
        golds = _read_ndjson(gold_path)
    except Exception as e:  # noqa: BLE001 - surface honestly, never crash the tab
        return {"source": source, "error": f"sample unreadable: {e}", "rows": []}
    if not raws or not golds or len(raws) != len(golds):
        return {"source": source, "error": "sample/gold empty or count-mismatched", "rows": []}
    idx = cfg["default_row"] if row_index is None else row_index
    idx = max(0, min(int(idx), len(raws) - 1))
    raw, gold = raws[idx], golds[idx]
    rows = [{"raw_field": rf, "raw_value": _dig(raw, rf), "ocsf_field": of,
             "ocsf_value": gold.get(of), "trap": note.startswith(_WARN), "note": note}
            for rf, of, note in cfg["fields"]]
    return {"source": source, "class_uid": cfg["class_uid"], "class_name": cfg["class_name"],
            "activity_id": gold.get("activity_id"), "row_index": idx, "n_rows": len(raws),
            "raw": raw, "ocsf": gold, "rows": rows, "error": None}


# --- panel ------------------------------------------------------------------ #

def _short(v, n=72):
    s = json.dumps(v) if not isinstance(v, str) else v
    return (s[:n] + "…") if len(s) > n else s


def config_preview_panel(mo, ui, preview):
    """Render the raw->OCSF preview as a field-by-field mapping table with the traps flagged."""
    if preview.get("error"):
        return ui.panel(mo, ui.header(mo, "Configuration — raw -> OCSF preview"),
                        mo.md(f"*Preview unavailable: {preview['error']}.*"))
    head = f"{preview['class_name']} ({preview['class_uid']})"
    tbl = ["| | Raw field | Raw value | OCSF field | Value |", "|:-:|---|---|---|---|"]
    for r in preview["rows"]:
        flag = "⚠️" if r["trap"] else ""
        tbl.append(f"| {flag} | `{r['raw_field']}` | {_short(r['raw_value'])} | "
                   f"`{r['ocsf_field']}` | {_short(r['ocsf_value'])} |")
    notes = [r["note"] for r in preview["rows"] if r["note"]]
    return ui.panel(mo,
        ui.header(mo, f"Configuration — raw → OCSF · {head}"),
        mo.md("Pick a source and watch the deployed mapping turn one **raw event** into an **OCSF "
              "record**, field by field. The ⚠️ rows are the semantic traps a name-based mapper gets "
              "wrong — where the schema, not the field name, decides the answer."),
        mo.md(f"**Raw event** (synthetic; row {preview['row_index'] + 1} of {preview['n_rows']}):"),
        mo.md(f"```json\n{json.dumps(preview['raw'], indent=1)[:1200]}\n```"),
        mo.md("\n".join(tbl)),
        mo.md("\n".join(f"- {n}" for n in notes)),
        mo.md(f"**Produced OCSF record** (`class_uid {preview['class_uid']}`, "
              f"`activity_id {preview['activity_id']}`):"),
        mo.md(f"```json\n{json.dumps(preview['ocsf'], indent=1)[:1200]}\n```"),
        mo.md("*Renders the authored OCSF contract from the sample library; the live-router round-trip "
              "(the same mapping run by the deployed Tenzir/Vector pipeline) is in Flow › Health.*"),
    )
