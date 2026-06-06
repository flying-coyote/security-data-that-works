# The MOAR "lab" — embedded query engine (DuckDB) + the pyiceberg write/read tooling over the lakehouse.
# Self-contained so `--profile core` alone gives a queryable open security-data lake.
FROM python:3.12-slim

# pyiceberg extras resolve compatible pyarrow/duckdb/s3fs; boto3 is omitted (its botocore pin clashes with
# s3fs's aiobotocore). s3fs gives S3 access; duckdb is the embedded engine; polars for dataframe work.
RUN pip install --no-cache-dir \
    "pyiceberg[pyarrow,s3fs,duckdb]==0.11.1" \
    polars

WORKDIR /lab
