# MOAR evidence-run — five verbs, 2026-06-15

Live `./moar` validation pass on the MOAR docker stack (Ryzen 5800H / WSL2, single host;
moar-* compose project; ClickHouse + StarRocks + Trino + DuckDB-in-lab + MinIO + Iceberg-REST).
Each verb validates a hypothesis live; the durable record is the Evidence Update attached to the
project1 hypothesis tracker. Raw outputs captured here because the stack is regenerated on teardown.
Tier B, single host, synthetic/structured data only.

## 1. `flow-gate` — flow-layer count-at-every-hop (OCSF mis-map the quality gate can't see)

```
=== clean pipeline ===
  class 4001: emitted 10000  landed 10000  [ok]
  class 3002: emitted  4000  landed  4000  [ok]
  class 1001: emitted  2500  landed  2500  [ok]
  class 4002: emitted   800  landed   800  [ok]
  READY — every source count reconciles at the model boundary
=== faulted pipeline (class 3002 mis-mapped) ===
  class 3002: emitted  4000  landed     0  [DROP]  <-- 4000 events vanished source->model
  NOT READY — a class drops silently; a detection keyed on it returns zero on a "healthy" network
DEMONSTRATED: flow gate passes clean and catches the silent class-3002 drop the quality gate cannot see: True
```

Demonstrator (deterministic, synthetic). The point: a per-`class_uid` count reconciliation at the
source→model boundary catches a whole-class silent drop/mis-route that the NULL/timestamp/cross-engine
*quality* gate is blind to (the rows are valid; they just never arrived in that class). Maps to the
flow-layer counting discipline (book ch03 / Appendix-B #12 / Appendix-F F.2) under H-SPEC-INTEGRITY-01.

## 2. `variant-mfa` — absence-vs-NULL (flattening hides absent-MFA logins)

```
corpus: 820 ConsoleLogin — mfa=true 500, mfa=false 120, mfa ABSENT 200
security-correct 'unprotected logins' (false + absent) = 320
  flattened naive  (mfa = 'false')                      = 120   MISS 200 absent-MFA logins
  flattened absence-aware (mfa IS DISTINCT FROM 'true') = 320   (only correct if you KNOW absent->NULL)
  nested/structure-aware (test the path)                = 320   OK — catches false + absent
DEMONSTRATED: flattening hides absence -> naive detection under-counts by 200: True
```

Demonstrator. The naive flattened detection catches 120 of 320 unprotected logins (misses 200/320 =
62.5%); structure-aware catches all 320. Maps to H-OCSF-CONTEXT-COLLAPSE-01 (the CloudTrail MFA silent
miss — "field absent" collapses into the same NULL as "present-null" once flattened).

## 3. `commit-tax` — Iceberg per-commit floor vs DuckLake catalog metadata (100k rows)

```
config                       commits ingest_s data_files meta_files meta/cat_KB plan_ms
iceberg  batch                     1    1.86          1          4         8.8     9.9
iceberg  stream                  100   15.32        100        301      4577.1   142.5
ducklake stream (inline off)     100    2.51        100(catDB)    -      3596.0     7.2
ducklake stream (inline on)      100    4.73          0(catDB)    -      3596.0     5.6
```

Re-derived deltas (Iceberg batch → 100-commit stream): data files 1→100, metadata files 4→301 (75×),
metadata size 8.8→4577.1 KB (520×), planning 9.9→142.5 ms (14.4×), ingest 1.86→15.32 s (8.2×).
DuckLake holds commit metadata in the catalog DB, so streaming planning stays 5.6–7.2 ms (~20–25×
faster than Iceberg's streamed 142.5 ms) and inlining-on writes 0 Parquet files for the small commits.
The shape of the tax — not the absolute ms — is the finding. Maps to H-DUCKLAKE-02 (write-pattern is
architectural: tiny-frequent-commit security telemetry is the cadence Iceberg's file-per-commit floor
punishes).

## 4. `cidr` — native IPv4 vs String CIDR hunting in ClickHouse (20M rows, warm)

Answer-equality: 78,222 IPs in 10.5.0.0/16 both ways. Storage: ip_str 188.10 MiB vs ip_v4 69.21 MiB
= **2.72×** smaller. Latency (6 warm trials, `--time`, `FORMAT Null`):

```
STRING (isIPAddressInRange): 0.127 0.119 0.121 0.153 0.116 0.116  -> median ~0.120 s
IPv4   (BETWEEN toIPv4):     0.008 0.007 0.008 0.007 0.007 0.007  -> median ~0.007 s
```

Re-derived ratio: 0.120 / 0.007 = **~17×** (conservative bound 0.116 / 0.008 = 14.5×). Confirms the
published ~13–17× on matrix/private/vendors.astro — this warm re-run lands at the top of that range.
Honest read unchanged: ~15–17× at 20M on one host sits below the borrowed 50–100× headline; the measured
direction + the ~2.7× storage ratio are the durable findings.

## 5. `concurrency-sweep` — embedded vs server scheduling (1M rows, scan-agg group by dst_port)

```
engine      C1 q/s   C16 q/s  C16/C1   C1 p95   C16 p95
duckdb       75.4     114.4    1.52x    40.7ms   343.3ms   (embedded: saturates soonest, p95 +8.4x)
clickhouse   56.7     210.4    3.71x    20.0ms    94.0ms   (server scheduler scales throughput)
trino         6.2      24.8    4.00x   230.9ms   764.7ms   (scales but low absolute; JVM/coordinator)
starrocks    14.2      75.9    5.35x    99.9ms   261.7ms   (best throughput scaling, tightest tail)
```

Embedded DuckDB (one in-process engine per client, sharing the host's cores) flattens at 1.52× and its
p95 climbs hardest; the server engines with their own schedulers grow throughput as C rises (ClickHouse
3.71×, Trino 4.00×, StarRocks 5.35×). Maps to H-ARCH-02 (engine specialization shows in the concurrency
*model* too). NOTE the reconciliation with the sdw-lab `concurrency-multiuser` bench (which found ~no
headroom, ClickHouse 1.10×): that bench used a host-saturating HEAVY query (10.3M-row top-talkers); this
sweep uses a LIGHTER 1M-row group-by with spare per-query headroom. Concurrency headroom is
query-weight-dependent — heavy queries leave none even on server engines, lighter queries leave headroom
that server schedulers exploit and embedded DuckDB largely can't.

## Caveats (all five)

Single host (engine *model*, not cluster behavior); synthetic/structured corpora; demonstrators (#1,#2)
are deterministic n=1 illustrations of a mechanism, not measured magnitudes; measured legs (#3,#4,#5) are
Tier B first-party, warm, single-host. ClickHouse/StarRocks/Trino at the versions in the moar compose.
