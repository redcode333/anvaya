"""Rate limits kept in the database: fixed-window counters with an expiry (table rate_limits), so a restart or a
sleeping server never resets them and several app instances share one limit. The retention job deletes expired rows.

A counter is keyed by (bucket, window_start); every client key is hashed with the pepper, so no raw IP address is stored.
`hit` counts a request and says whether it is over the limit; `exceeded` only reads (used where only *failed* attempts
count: check first, then `fail` after a wrong answer)."""
import time

from flask import request

from . import metrics
from .common import ApiError, sha256
from .db import get_db


def client_key() -> str:
    """The caller's IP address, peppered and hashed (never stored raw)."""
    from .accounts import pepper
    return sha256(pepper() + (request.remote_addr or "unknown"))[:32]


def _window(window_s: int) -> tuple[int, int]:
    t = int(time.time())
    return t - t % window_s, t


def hit(bucket: str, key: str, limit: int, window_s: int = 60) -> bool:
    """Count one request in the current window of (bucket, key). True when it is within `limit`."""
    start, _ = _window(window_s)
    row = get_db().execute(
        "INSERT INTO rate_limits(bucket, window_start, hits, expires_at) VALUES (?,?,1,?)"
        " ON CONFLICT (bucket, window_start) DO UPDATE SET hits = rate_limits.hits + 1 RETURNING hits",
        (f"{bucket}:{key}", start, start + window_s)).fetchone()
    return row[0] <= limit


def exceeded(bucket: str, key: str, limit: int, window_s: int) -> bool:
    start, _ = _window(window_s)
    row = get_db().execute("SELECT hits FROM rate_limits WHERE bucket=? AND window_start=?",
                           (f"{bucket}:{key}", start)).fetchone()
    return bool(row) and row[0] >= limit


def fail(bucket: str, key: str, window_s: int) -> None:
    """Record one failed attempt (counts without checking a limit)."""
    hit(bucket, key, 0, window_s)


def forget(bucket: str, key: str) -> None:
    get_db().execute("DELETE FROM rate_limits WHERE bucket=?", (f"{bucket}:{key}",))


def limit_per_minute(bucket: str, limit: int, message: str = "Too many requests. Wait a minute and try again.",
                     *, on_limited=None) -> None:
    """At most `limit` requests per minute per client IP in `bucket`; raises 429 RATE_LIMITED otherwise."""
    if not hit(bucket, client_key(), limit, 60):
        metrics.RATE_LIMITED.labels(bucket).inc()
        if on_limited:
            on_limited()
        raise ApiError("RATE_LIMITED", message, 429)


def purge_expired(db) -> int:
    return db.execute("DELETE FROM rate_limits WHERE expires_at < ?", (int(time.time()),)).rowcount
