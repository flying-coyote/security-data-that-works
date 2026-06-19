"""Last-validated decay — a measured verdict rots toward 'unproven' if nobody re-runs it.

The gate must not show a months-old GREEN as if it were current. Every measured layer
carries the UTC time it was last validated; past a TTL a `pass` decays to `stale`,
which the gate treats as not-green — but not a failure. `stale` means "re-run me," not
"broken." marimo is a reactive notebook, not a daemon, so this is the honest substitute
for a built-in cron: the verdict ages and a manual re-run refreshes it; an external
scheduler is documented, not faked.

Fail-closed contract: a `pass` is only kept green when it carries a parseable timestamp
that is neither older than the TTL nor implausibly in the future. A pass we cannot date,
or one stamped ahead of now beyond clock-skew tolerance, is downgraded to `stale` — an
undatable pass is not a trustworthy-fresh pass.
"""
from __future__ import annotations

import datetime as _dt

DEFAULT_TTL_SECONDS = 86400  # one day — a clean foundation unre-checked for a day reads stale
FUTURE_SKEW_TOLERANCE_SECONDS = 300  # tolerate small clock skew; beyond this a future stamp is suspect


def _parse(iso):
    if not iso:
        return None
    try:
        d = _dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None
    # Coerce a naive stamp to UTC so an aware/naive subtraction can never raise.
    if d.tzinfo is None:
        d = d.replace(tzinfo=_dt.timezone.utc)
    return d


def _raw_delta_seconds(validated_at_iso, now_iso):
    a, b = _parse(validated_at_iso), _parse(now_iso)
    if a is None or b is None:
        return None
    return (b - a).total_seconds()


def age_seconds(validated_at_iso, now_iso):
    """Non-negative age in seconds, or None if either timestamp is missing/unparseable.
    A future stamp clamps to 0 for arithmetic; effective_status handles the skew signal."""
    d = _raw_delta_seconds(validated_at_iso, now_iso)
    return None if d is None else max(0.0, d)


def is_stale(validated_at_iso, now_iso, ttl_seconds=DEFAULT_TTL_SECONDS):
    age = age_seconds(validated_at_iso, now_iso)
    # Boundary: age exactly == ttl is still fresh (strict >). Harmless at second resolution.
    return age is not None and age > ttl_seconds


def effective_status(status, validated_at_iso, now_iso, ttl_seconds=DEFAULT_TTL_SECONDS):
    """A `pass` decays to `stale` when it is older than ttl_seconds, when it cannot be
    dated (None/garbage stamp), or when it is stamped implausibly in the future (clock
    skew / integrity problem). Everything else is unchanged — only a pass can go stale;
    a fail stays a fail and unmeasured stays unmeasured (there is nothing proven to rot)."""
    if status != "pass":
        return status
    raw = _raw_delta_seconds(validated_at_iso, now_iso)
    if raw is None or raw < -FUTURE_SKEW_TOLERANCE_SECONDS:
        return "stale"  # undatable, or stamped in the future — not a trustworthy-fresh pass
    return "stale" if max(0.0, raw) > ttl_seconds else "pass"
