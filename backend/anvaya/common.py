import hashlib
import json
import threading
import time
from collections import defaultdict, deque
from functools import wraps

from flask import current_app, g, request

from . import metrics
from .db import dumps, get_db, iso, new_id

_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()


class ApiError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details: dict | None = None):
        super().__init__(message)
        self.code, self.message, self.status, self.details = code, message, status, details or {}


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()


# ---------------------------------------------------------------- audit

def audit(action: str, *, case_id=None, session_id=None, object_version=None, details=None,
          actor_id=None, actor_role=None) -> None:
    """Append a data-minimized audit event. Never pass raw profile values in details."""
    user = getattr(g, "user", None)
    get_db().execute(
        """INSERT INTO audit_events(event_id, actor_id, actor_role, case_id, session_id, action, ts,
           request_id, object_version, details_json) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            new_id("AUD"),
            actor_id or (user["user_id"] if user else "citizen"),
            actor_role or (user["role"] if user else "citizen"),
            case_id, session_id, action, iso(), getattr(g, "request_id", None), object_version,
            dumps(details or {}),
        ),
    )


# ---------------------------------------------------------------- auth

def current_user(require_mfa: bool = True) -> dict | None:
    """The signed-in staff member (Supabase account whose app_metadata.role is operator / reviewer / admin), from the
    access token verified for this request (auth.authenticate_request); None otherwise. Every staff API call needs an
    aal2 token (TOTP verified in this sign-in): a staff token at aal1 is refused with 403 MFA_REQUIRED unless
    require_mfa=False (only /auth/me, so the browser knows to ask for the code)."""
    from . import auth
    claims = g.get("auth")
    role = auth.staff_role(claims)
    if not role:
        return None
    email = claims.get("email") or ""
    user = {"user_id": claims["sub"], "username": email, "role": role, "display_name": email or role,
            "aal": auth.aal(claims)}
    if require_mfa and user["aal"] != "aal2" and current_app.config["STAFF_MFA_REQUIRED"]:
        metrics.AUTH.labels("mfa_required").inc()
        auth.record("mfa_required", user["user_id"], role, {"endpoint": request.endpoint})
        get_db().commit()
        raise ApiError("MFA_REQUIRED", "Staff accounts must verify a code from the authenticator app first.", 403,
                       {"aal": user["aal"]})
    return user


def rate_limit(bucket: str, limit: int, message: str = "Too many requests. Wait a minute and try again.") -> None:
    """At most `limit` requests per minute per client IP in `bucket` (in memory, per process)."""
    key = f"{id(current_app._get_current_object())}:{bucket}:{request.remote_addr}"
    with _hits_lock:
        q, t = _hits[key], time.monotonic()
        while q and t - q[0] > 60:
            q.popleft()
        if len(q) >= limit:
            metrics.RATE_LIMITED.labels(bucket).inc()
            raise ApiError("RATE_LIMITED", message, 429)
        q.append(t)


def require_role(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            user = current_user()
            if user is None:
                metrics.AUTH.labels("unauthenticated").inc()
                raise ApiError("UNAUTHENTICATED", "Sign in with a staff account.", 401)
            if user["role"] not in roles:
                g.user = user
                metrics.AUTH.labels("forbidden").inc()
                audit("auth.forbidden", details={"endpoint": request.endpoint, "required": list(roles)})
                get_db().commit()
                raise ApiError("FORBIDDEN", "Your role cannot access this resource.", 403)
            g.user = user
            return fn(*a, **kw)
        return wrapper
    return deco


# ---------------------------------------------------------------- idempotency

def idempotency_key(required: bool = True) -> str | None:
    key = request.headers.get("Idempotency-Key")
    if required and not key:
        raise ApiError("IDEMPOTENCY_KEY_REQUIRED", "This write requires an Idempotency-Key header.", 428)
    return key


def idempotent(scope: str, key: str, fn) -> tuple[dict, int]:
    """Run fn() -> (body, status) at most once per (scope, key), also when identical requests arrive together. The key
    is claimed with INSERT ... ON CONFLICT DO NOTHING in the same transaction as fn's writes: a concurrent request with
    the same key waits on that row until the first commits, then replays the stored response. If fn raises, the
    transaction (claim included) rolls back and nothing is stored, so a retry runs again."""
    db = get_db()
    with db.transaction():
        claimed = db.execute(
            "INSERT INTO idempotency(scope, idem_key, response_json, status_code, created_at) VALUES (?,?,?,?,?)"
            " ON CONFLICT DO NOTHING RETURNING status_code", (scope, key, "{}", 0, iso())).fetchone()
        if not claimed:
            row = db.execute("SELECT response_json, status_code FROM idempotency WHERE scope=? AND idem_key=?",
                             (scope, key)).fetchone()
            replay = json.loads(row["response_json"])
            replay["idempotent_replay"] = True
            metrics.IDEMPOTENT_REPLAYS.labels(scope.split(":")[0]).inc()
            return replay, row["status_code"]
        body, status = fn()
        db.execute("UPDATE idempotency SET response_json=?, status_code=? WHERE scope=? AND idem_key=?",
                   (dumps(body), status, scope, key))
    return body, status
