"""Partner-mode gate for the MOAr console — the integrator-enablement third mode (KIT-4).

Three modes, three surfaces, and NO implication between the keys:

  PUBLIC  (default — what any clone gets)
      The generic land-this-source METHOD on synthetic data only. Byte-for-byte
      what the console rendered before this module existed: turning partner mode
      off is not a state a public clone can observe.
  PARTNER (MOAR_PARTNER_MODE truthy — this module)
      Unlocks the per-customer recommender WORKFLOW: the dark-spot technique
      (attack_coverage.assess) -> the detect-band D3FEND leads -> the OCSF
      classes to land -> the land-this-source route binding, run over the
      OPERATOR'S OWN landed OCSF data (the Inspector-loaded table) instead of
      the synthetic preview. It NEVER unlocks the scored Matrix: no per-vendor
      1-5 scores, weights, weighted totals, or claim-vs-shipped deltas render
      in partner mode (paid_scoring.load_scores stays {} unless MOAR_PAID_MODE
      is independently on — the paid firewall is untouched).
  PAID    (MOAR_PAID_MODE truthy — paid_scoring.py, unchanged)
      The scored Matrix, plus (as before) the per-environment recommender.

THE INDEPENDENCE RULE (KIT-4 owner decision): MOAR_PARTNER_MODE is its own key.
It is never implied by MOAR_PAID_MODE being off — a public clone (both keys
unset) behaves exactly as before — and never implied by MOAR_PAID_MODE being on
either. partner_mode() reads ONLY MOAR_PARTNER_MODE; this module deliberately
does not import paid_scoring, so no code path here can read, relax, or leak the
paid gate. Proven in prove_partner_mode.py.

TELEMETRY-INJECTION. The operator-data feed below returns ONLY the two
aggregate inputs the dark-spot technique consumes: detections.scan() findings
(match counts + _safe_key'd allow-listed group keys) and analyze.analyze_table's
by_class ({class_uid: count}). Raw rows are materialized only inside this
process to feed scan(); no raw row, record object, or free-text field value is
ever returned — the same boundary the synthetic path honors.

Env:
  MOAR_PARTNER_MODE   truthy (1/true/yes/on) to enable the partner recommender
"""
from __future__ import annotations

import os

import analyze as az
import detections as dets


def partner_mode() -> bool:
    """True iff MOAR_PARTNER_MODE is truthy. Reads ONLY its own key — never
    derived from MOAR_PAID_MODE (on or off), never from vault presence."""
    return os.environ.get("MOAR_PARTNER_MODE", "").strip().lower() in {"1", "true", "yes", "on"}


def operator_coverage_inputs(arrow_table):
    """The operator-data feed for the dark-spot technique (partner mode only).

    Given the operator's Inspector-loaded OCSF table (PyArrow), return the two
    aggregate inputs attack_coverage.assess() needs:
      scan_findings — detections.scan() over the table's rows (aggregate-safe:
                      match counts + _safe_key'd allow-listed group keys only)
      by_class      — analyze.analyze_table()'s {class_uid: count} view

    Raises ValueError if the table has no class_uid column (not an OCSF table),
    so the caller degrades honestly to the synthetic walkthrough instead of
    resolving every technique to a fake dark_spot.
    """
    agg = az.analyze_table(arrow_table)
    by_class = agg.get("by_class")
    if by_class is None:
        raise ValueError("loaded table has no class_uid column — not an OCSF table")
    findings = dets.scan(arrow_table.to_pylist())
    return findings, by_class
