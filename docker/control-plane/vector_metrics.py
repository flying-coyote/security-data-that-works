"""Honest Vector throughput counters from the prometheus_exporter scrape.

Vector exposes no control/REST throughput API, so the truthful source of per-component
counts is its own `internal_metrics` source exported via a `prometheus_exporter` sink. This
parses that text exposition into data-throughput counts the Layer-2 panel shows.

Honesty contract (the gate's spine, applied here):
  - a failed/empty scrape returns None — the panel renders "—" (unmeasured), never a zero
    or a fabricated number dressed as a reading;
  - Vector's own telemetry plumbing (the internal_metrics source + the prometheus_exporter
    sink) is excluded, so the counts measure pipeline data, not the meter measuring itself;
  - the optional Prometheus per-sample timestamp is ignored (value is the first field).
"""
from __future__ import annotations

import urllib.request

_DATA_METRICS = (
    "vector_component_received_events_total",
    "vector_component_sent_events_total",
    "vector_component_errors_total",
)
_PLUMBING = ("internal_metrics", "prometheus_exporter")


def parse_counts(text):
    """Parse Prometheus text into integer counts (events_in, events_out, errors), or None if no Vector
    component metrics are present. events_in = received over sources, events_out = sent
    over sinks, errors = component_errors_total — all excluding Vector's own plumbing."""
    ein = eout = errs = 0.0
    seen = False
    for line in text.splitlines():
        if not line or line[0] == "#" or "{" not in line:
            continue
        name = line.split("{", 1)[0]
        if name not in _DATA_METRICS:
            continue
        labels = line[line.find("{") + 1:line.find("}")]
        try:
            val = float(line.split("}", 1)[1].split()[0])  # value first; ignore optional timestamp
        except (ValueError, IndexError):
            continue
        kind = ctype = ""
        for part in labels.split(","):
            if part.startswith("component_kind="):
                kind = part.split("=", 1)[1].strip('"')
            elif part.startswith("component_type="):
                ctype = part.split("=", 1)[1].strip('"')
        if ctype in _PLUMBING:
            continue  # don't count the meter measuring itself
        seen = True
        if name == "vector_component_errors_total":
            errs += val
        elif name == "vector_component_received_events_total" and kind == "source":
            ein += val
        elif name == "vector_component_sent_events_total" and kind == "sink":
            eout += val
    return (int(ein), int(eout), int(errs)) if seen else None


def scrape_counts(url, timeout=0.7):
    """Fetch and parse Vector's /metrics. None on any failure (unmeasured, never faked)."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            if r.status != 200:
                return None
            text = r.read().decode("utf-8", "replace")
    except Exception:  # noqa: BLE001
        return None
    return parse_counts(text)
