-- R-tier swap (Fluent Bit): one raw Okta-style auth event -> one OCSF Authentication (3002) record.
-- Field-for-field the same contract the Vector/VRL and Tenzir routers emit, so `./moar swap-router` can
-- assert all three agree. Container runs with TZ=UTC (see compose); the offset correction below makes the
-- epoch-ms right regardless, so there is no hidden timezone dependence.

-- "2026-01-01T00:00:01Z" -> unix epoch MILLISECONDS (integer). os.time() reads the broken-down table as
-- local time, so compute the local<->UTC offset and add it back to land on a true UTC epoch.
local function iso8601_to_epoch_ms(ts)
  local Y, Mo, D, h, m, s = ts:match("(%d+)-(%d+)-(%d+)T(%d+):(%d+):(%d+)Z")
  if Y == nil then return nil end
  local local_epoch = os.time({
    year = tonumber(Y), month = tonumber(Mo), day = tonumber(D),
    hour = tonumber(h), min = tonumber(m), sec = tonumber(s), isdst = false,
  })
  local utc_offset = os.difftime(os.time(os.date("*t", local_epoch)),
                                 os.time(os.date("!*t", local_epoch)))
  return math.floor(local_epoch + utc_offset) * 1000
end

function to_ocsf(tag, timestamp, record)
  local actor   = record["actor"]   or {}
  local client  = record["client"]  or {}
  local outcome = record["outcome"] or {}
  local result  = outcome["result"]

  -- Canonical per OCSF 1.8.0 + ocsf/examples (CON-AUTH-1): activity_id = the operation (1 Logon, from the
  -- event type); the success/failure outcome lives in status_id (1 Success / 2 Failure), NOT activity_id.
  -- Field-for-field the same contract the Vector/VRL and Tenzir transforms emit.
  local ocsf = {
    class_uid    = 3002,
    class_name   = "Authentication",
    category_uid = 3,
    time         = iso8601_to_epoch_ms(record["published"]),
    activity_id  = 1,
    status_id    = (result == "SUCCESS") and 1 or 2,
    user         = actor["alternateId"],
    src_ip       = client["ipAddress"],
    status       = result,
  }
  -- return code 2 = keep original timestamp, replace the record with the flat OCSF object
  return 2, timestamp, ocsf
end
