"""CIDR-membership: native IPv4 type vs String column (ClickHouse), the most-cited security-specific
number ("native IP types 50-100x faster CIDR hunting"). Measures it first-party on one host so the essays
can carry a measured ratio instead of a vendor-doc figure.

Run from inside the clickhouse container (the workload is ClickHouse-internal MergeTree, not the lakehouse):
  docker compose exec -T clickhouse clickhouse client -mn < /dev/stdin   # or just run ./moar cidr (if wired)

Measured 2026-06-07, single host (Ryzen 5800H/WSL2), 20,000,000 rows, warm:
  string parse (isIPAddressInRange on String) : ~0.166 s
  ipv4 native (integer range BETWEEN toIPv4)  : ~0.010 s   -> ~13-17x faster
  storage: String 188.1 MiB vs IPv4 65.4 MiB  -> ~2.9x smaller
  same answer both ways (78,211 IPs in 10.5.0.0/16).
Honest read: ~13-17x on a single host at 20M rows lands BELOW the borrowed 50-100x headline (which is at
larger scale / different query shapes); the measured direction and storage ratio are the durable findings.

This file documents the exact queries so the result is reproducible. N is parameterizable.
"""
SQL = r"""
-- setup
CREATE OR REPLACE TABLE ip_str (src_ip String) ENGINE=MergeTree ORDER BY tuple();
INSERT INTO ip_str
  SELECT '10.'||toString(rand()%256)||'.'||toString(rand(1)%256)||'.'||toString(rand(2)%256)
  FROM numbers({N});
CREATE OR REPLACE TABLE ip_v4 (src_ip IPv4) ENGINE=MergeTree ORDER BY src_ip;
INSERT INTO ip_v4 SELECT toIPv4(src_ip) FROM ip_str;

-- string parse per row (catalog of the slow path)
SELECT count() FROM ip_str WHERE isIPAddressInRange(src_ip, '10.5.0.0/16');
-- native integer range on the IPv4 type (the fast path)
SELECT count() FROM ip_v4 WHERE src_ip BETWEEN toIPv4('10.5.0.0') AND toIPv4('10.5.255.255');

-- storage footprint per representation
SELECT table, formatReadableSize(sum(bytes_on_disk)) sz, sum(rows) rows
FROM system.parts WHERE table IN ('ip_str','ip_v4') AND active GROUP BY table ORDER BY table;
"""

if __name__ == "__main__":
    import os
    print(SQL.replace("{N}", os.environ.get("CIDR_N", "20000000")))
