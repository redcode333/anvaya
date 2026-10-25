import hashlib
import json
import secrets
from functools import wraps

from flask import g, request
from werkzeug.security import check_password_hash

from . import metrics
from .db import dumps, get_db, iso, iso_in, new_id, now, parse_iso


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

def login(username: str, password: str) -> dict:
    db = get_db()
    user = db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
    if not user or not check_password_hash(user["password_hash"], password):
        metrics.AUTH.labels("login_failed").inc()
        audit("auth.login_failed", details={"username": username}, actor_id="anonymous", actor_role="anonymous")
        db.commit()
        raise ApiError("INVALID_CREDENTIALS", "Username or password is incorrect.", 401)
    from flask import current_app
    token = secrets.token_urlsafe(32)
    expires = iso_in(current_app.config["AUTH_TOKEN_TTL_HOURS"])
    db.execute("INSERT INTO auth_tokens(token_hash, user_id, expires_at) VALUES (?,?,?)",
               (sha256(token), user["user_id"], expires))
    metrics.AUTH.labels("login_ok").inc()
    audit("auth.login", actor_id=user["user_id"], actor_role=user["role"])
    db.commit()
    return {"token": token, "expires_at": expires,
            "user": {"user_id": user["user_id"], "username": user["username"], "role": user["role"],
                     "display_name": user["display_name"]}}


def current_user() -> dict | None:
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    row = get_db().execute(
        """SELECT u.user_id, u.username, u.role, u.display_name, t.expires_at FROM auth_tokens t
           JOIN users u ON u.user_id = t.user_id WHERE t.token_hash=?""",
        (sha256(header[7:]),),
    ).fetchone()
    if not row or parse_iso(row["expires_at"]) < now():
        return None
    return dict(row)


def require_role(*roles):
    def deco(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            user = current_user()
            if user is None:
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
