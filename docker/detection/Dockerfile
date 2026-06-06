# Detection tier — detection-as-code over the lakehouse: SigmaHQ rules compiled to SQL + marimo hunting.
# Builds on the lab image (already has pyiceberg + duckdb), adds pySigma + a SQL backend + marimo + sigma-cli.
FROM moar/lab:latest

RUN pip install --no-cache-dir \
    pysigma \
    pysigma-backend-sqlite \
    sigma-cli \
    marimo

WORKDIR /detection
