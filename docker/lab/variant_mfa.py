"""Variant / nested absence-vs-NULL: the CloudTrail MFA silent-miss, made falsifiable (H-OCSF-CONTEXT-COLLAPSE-01).

The failure mode the flattening essays describe: a detection for "logins NOT protected by MFA" has to count
two populations — events where MFA was explicitly false, AND events where the MFA field is ABSENT (a legacy or
mis-instrumented path that never asserted MFA at all, the risky ones). Flattening nested JSON to a column
collapses "field absent" into the same NULL as "field present but null", so a naive flattened detection
written as `mfa = 'false'` silently MISSES the absent-MFA logins. Querying the nested structure keeps absence
distinguishable, so it catches them.

Self-contained DuckDB probe (the lab image carries duckdb): builds raw CloudTrail-shaped JSON events with three
MFA states, then runs the detection both ways and shows the flattened path under-counts the unprotected logins.
"""
import duckdb

con = duckdb.connect()
# raw events: present-true (protected), present-false (explicitly no MFA), ABSENT (field never emitted)
con.execute("""
CREATE TABLE raw AS
  SELECT '{"eventName":"ConsoleLogin","userIdentity":{"sessionContext":{"attributes":{"mfaAuthenticated":"true"}}}}' AS body, 'mfa_true' tag FROM range(500)
  UNION ALL
  SELECT '{"eventName":"ConsoleLogin","userIdentity":{"sessionContext":{"attributes":{"mfaAuthenticated":"false"}}}}', 'mfa_false' FROM range(120)
  UNION ALL
  SELECT '{"eventName":"ConsoleLogin","userIdentity":{"sessionContext":{"attributes":{}}}}', 'mfa_absent' FROM range(200)
""")
total = con.sql("SELECT count(*) FROM raw").fetchone()[0]
truth_true = con.sql("SELECT count(*) FROM raw WHERE tag='mfa_true'").fetchone()[0]
truth_false = con.sql("SELECT count(*) FROM raw WHERE tag='mfa_false'").fetchone()[0]
truth_absent = con.sql("SELECT count(*) FROM raw WHERE tag='mfa_absent'").fetchone()[0]
unprotected_truth = truth_false + truth_absent  # the security-correct answer

# FLATTENED path: extract to a column; an absent key extracts to SQL NULL, indistinguishable from present-null.
con.execute("""
CREATE TABLE flat AS
  SELECT json_extract_string(body, '$.userIdentity.sessionContext.attributes.mfaAuthenticated') AS mfa FROM raw
""")
flat_naive = con.sql("SELECT count(*) FROM flat WHERE mfa = 'false'").fetchone()[0]          # the bug
flat_aware = con.sql("SELECT count(*) FROM flat WHERE mfa IS DISTINCT FROM 'true'").fetchone()[0]

# NESTED/Variant-aware path: ask the structure whether MFA was affirmatively asserted true; everything else
# (false OR absent) is unprotected — absence stays visible because we test the structure, not a flattened cell.
nested = con.sql("""
  SELECT count(*) FROM raw
  WHERE coalesce(json_extract_string(body,'$.userIdentity.sessionContext.attributes.mfaAuthenticated'),'') != 'true'
""").fetchone()[0]

print(f"corpus: {total} ConsoleLogin events — mfa=true {truth_true}, mfa=false {truth_false}, mfa ABSENT {truth_absent}")
print(f"security-correct 'unprotected logins' (false + absent) = {unprotected_truth}")
print(f"  flattened naive  (mfa = 'false')          = {flat_naive}   {'MISS' if flat_naive < unprotected_truth else 'ok'}: silently drops the {truth_absent} absent-MFA logins")
print(f"  flattened absence-aware (mfa IS DISTINCT FROM 'true') = {flat_aware}   (only correct if you KNOW absent->NULL and no explicit nulls collapse with it)")
print(f"  nested/structure-aware (test the path)     = {nested}   {'OK — catches false + absent' if nested == unprotected_truth else 'MISS'}")
ok = (flat_naive < unprotected_truth) and (nested == unprotected_truth)
print(f"DEMONSTRATED: flattening hides absence -> the naive detection under-counts unprotected logins by "
      f"{unprotected_truth - flat_naive} ({truth_absent} absent-MFA events): {ok}")
