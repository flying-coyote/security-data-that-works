# AI tier (extension) — practitioner-owned, air-gappable agentic hunt over the lakehouse.
# Builds on the lab image (pyiceberg + duckdb); adds the HTTP client for a LOCAL model (Ollama). No cloud.
FROM moar/lab:latest
RUN pip install --no-cache-dir requests
WORKDIR /ai
