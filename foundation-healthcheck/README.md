# Foundation data-health validation — a runnable demonstrator

A teaching demonstrator for the **Foundation · Data health** gate: the four layers, in order, that turn "trust
the data platform" from an assertion into a measured property. It runs end-to-end on a synthetic OCSF-shaped
corpus with faults injected into every layer, and lands a foundation-readiness scorecard.

- `foundation_healthcheck_demo.py` — percent-format source (the canonical copy; run it directly)
- `foundation_healthcheck_demo.ipynb` — the Jupyter notebook (generated from the `.py`)

```bash
pip install numpy pandas duckdb
python foundation_healthcheck_demo.py        # or open the .ipynb in Jupyter
```

## The four layers (measured upstream → downstream)

| layer | what it measures | the fault this demo injects |
|---|---|---|
| **1 · source health** | producer health upstream of the data — volume vs. baseline, drop rate, time-sync drift | a zeek capture dip + a +90 s clock drift |
| **2 · flow health** | the SRE golden signals per pipeline stage — latency, traffic, errors, saturation | a DLQ rate + a tail-latency burst |
| **3 · data quality** | the six dimensions + retention — timeliness, accuracy, completeness, consistency, validity (OCSF mapping), uniqueness | duplicates, NULL identities, stale records, an identity-format flip |
| **4 · cross-tool gaps** | do the sources *in combination* cover what we claim — named coverage holes across CMDB/EDR/scanner | three tools, three asset counts, none obviously right |

A **verify-the-verifier** coda guards the report itself against the silent-failure modes the SDW Lab found in
query engines (a health metric is just a query): the `NOT IN (…, NULL)` allowlist trap, naive-timestamp tz
drift, and cross-engine non-equivalence.

## What this is, and isn't

This is the **shape** of the method, on illustrative data with illustrative thresholds — enough to see how the
gate works and why the order matters. It is **not** the engagement. The engagement replaces the synthetic
generator with your sources, the illustrative thresholds with each source's documented baselines and your
SLAs, and adds the cross-tool reconciliation judgment (Layer 4's authoritative-source scoring is deliberately
left as `[ENGAGEMENT]` here) and the remediation interpretation. That — on your real, multi-vendor environment
— is the deliverable; this shows you its shape.

## Read alongside (securitydataworks.com)

- the offering this demonstrates — [Foundation · Data health](https://securitydataworks.com/thesis/foundation)
- why a fast answer can be silently wrong — [The query engine returned the wrong answer](https://securitydataworks.com/writing/detection/silent-wrong-answer)
- the measurement discipline behind the thresholds — [How to run a benchmark that doesn't lie](https://securitydataworks.com/writing/economics/how-to-run-a-benchmark-that-doesnt-lie)
- the downstream projects this gate protects — [MOAR](https://securitydataworks.com/thesis/moar) · [DetectFlow](https://securitydataworks.com/thesis/detectflow) · [MLOps-hunting](https://securitydataworks.com/thesis/mlops-hunting)
- the evidence behind the verify-the-verifier coda — the [SDW Lab](https://securitydataworks.com/lab) (`github.com/flying-coyote/sdw-lab-benchmarks`)
