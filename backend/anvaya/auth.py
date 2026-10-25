"""Supabase Auth: access-token verification and the Auth admin API.

Every request that carries "Authorization: Bearer <access token>" is verified here before any handler runs: the
signature against the project's signing keys (GET <SUPABASE_URL>/auth/v1/.well-known/jwks.json, asymmetric ES256 /
RS256 only), the issuer (<SUPABASE_URL>/auth/v1), the audience ("authenticated"), and expiry. A token that fails is
rejected with 401; there is no fallback to unverified claims. The verified claims are kept on `g.auth`.

Keys are cached in memory for SUPABASE_JWKS_CACHE_S (default 600 s, as long as Supabase's own edge caches them) and
re-read at once when a token names an unknown key id (key rotation), at most every 30 s.

SUPABASE_SECRET_KEY is used only for the admin API (delete an account, seed staff accounts), sent in the `apikey`
header as Supabase documents for secret keys. It is never logged, never returned and never sent to the browser.
"""
import json
import logging
import threading
import time

import jwt
import requests
from flask import current_app, g, request

from .common import ApiError

log = logging.getLogger(__name__)

ALGORITHMS = ["ES256", "RS256"]
STAFF_ROLES = ("operator", "reviewer", "admin")
_REFRESH_MIN_S = 30


class _Jwks:
    def __init__(self):
        self.lock = threading.Lock()
        self.keys: dict[str, tuple[str, object]] = {}  # kid -> (alg, public key)
        self.fetched_at = float("-inf")
        self.url = ""


_jwks = _Jwks()


def fetch_jwks(url: str) -> dict:
    """The project's public signing keys. Tests replace this function with a mock JWKS."""
    r = requests.get(url, timeout=5, headers={"User-Agent": "anvaya-backend"})
    r.raise_for_status()
    return r.json()


def _load_keys(url: str) -> None:
    data = fetch_jwks(url)
    keys = {}
    for k in data.get("keys", []):
        alg = k.get("alg")
        if alg not in ALGORITHMS or not k.get("kid"):
            continue  # symmetric (HS256) or unknown keys are never used for verification
        keys[k["kid"]] = (alg, jwt.PyJWK.from_dict(k, algorithm=alg).key)
    _jwks.keys, _jwks.fetched_at, _jwks.url = keys, time.monotonic(), url


def _key_for(kid: str, url: str, cache_s: int):
    with _jwks.lock:
        age = time.monotonic() - _jwks.fetched_at
        if _jwks.url != url or age >= cache_s or (kid not in _jwks.keys and age >= _REFRESH_MIN_S):
            try:
                _load_keys(url)
            except Exception as e:  # noqa: BLE001 - keep the last good keys; report the class only
                log.warning("auth: could not fetch signing keys (%s)", type(e).__name__)
                if _jwks.url != url:
                    raise ApiError("AUTH_UNAVAILABLE", "Sign-in cannot be checked right now; try again.", 503)
        return _jwks.keys.get(kid)


def reset_jwks_cache() -> None:
    with _jwks.lock:
        _jwks.keys, _jwks.fetched_at, _jwks.url = {}, float("-inf"), ""


def issuer(cfg) -> str:
    return f"{cfg['SUPABASE_URL']}/auth/v1"


def verify_token(token: str, cfg=None) -> dict:
    """Verified claims of a Supabase access token, or ApiError 401."""
    cfg = cfg or current_app.config
    if not cfg["SUPABASE_URL"]:
        raise ApiError("AUTH_NOT_CONFIGURED", "Accounts are not configured on this server.", 401)
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        raise ApiError("INVALID_TOKEN", "The sign-in token is not valid. Sign in again.", 401)
    if header.get("alg") not in ALGORITHMS:
        raise ApiError("INVALID_TOKEN", "The sign-in token is not valid. Sign in again.", 401)
    found = _key_for(header.get("kid") or "", f"{issuer(cfg)}/.well-known/jwks.json", cfg["SUPABASE_JWKS_CACHE_S"])
    if not found or found[0] != header["alg"]:
        raise ApiError("INVALID_TOKEN", "The sign-in token is not valid. Sign in again.", 401)
    try:
        claims = jwt.decode(token, found[1], algorithms=[found[0]], audience=cfg["SUPABASE_JWT_AUDIENCE"],
                            issuer=issuer(cfg), leeway=10, options={"require": ["exp", "iat", "sub", "aud", "iss"]})
    except jwt.ExpiredSignatureError:
        raise ApiError("TOKEN_EXPIRED", "Your sign-in has expired. Sign in again.", 401)
    except jwt.PyJWTError:
        raise ApiError("INVALID_TOKEN", "The sign-in token is not valid. Sign in again.", 401)
    return claims


def authenticate_request() -> None:
    """before_request: verify the bearer token, if any, and keep its claims on g.auth (None without a token). A token
    whose sign-in started before the user's last "sign out of all devices" is refused even if it has not expired."""
    g.auth = None
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer ") and request.path.startswith("/api/"):
        g.auth_token = header[7:].strip()
        claims = verify_token(g.auth_token)
        if is_revoked(claims):
            raise ApiError("SESSION_REVOKED", "You were signed out on all devices. Sign in again.", 401)
        g.auth = claims


def signed_in_at(claims: dict) -> int:
    """When this sign-in session began: the earliest authentication method time (amr timestamps survive token
    refreshes, unlike iat); iat if the token has no amr."""
    stamps = [a.get("timestamp") for a in claims.get("amr") or [] if isinstance(a, dict)]
    stamps = [s for s in stamps if isinstance(s, (int, float))]
    return int(min(stamps)) if stamps else int(claims.get("iat", 0))


def _revocations() -> dict[str, int]:
    from .db import cached, get_db, parse_iso

    def load():
        return {r["user_id"]: int(parse_iso(r["revoked_before"]).timestamp())
                for r in get_db().execute("SELECT user_id, revoked_before FROM auth_revocations")}
    return cached(get_db(), "auth", "revocations", load)


def is_revoked(claims: dict) -> bool:
    before = _revocations().get(claims.get("sub"))
    return bool(before) and signed_in_at(claims) < before


def revoke_sessions(user_id: str, reason: str) -> None:
    """Refuse every token of `user_id` whose sign-in began before now (queued with the caller's transaction)."""
    from .db import bump, get_db, iso
    db = get_db()
    db.execute("INSERT INTO auth_revocations(user_id, revoked_before, reason) VALUES (?,?,?) ON CONFLICT (user_id)"
               " DO UPDATE SET revoked_before=excluded.revoked_before, reason=excluded.reason",
               (user_id, iso(), reason))
    bump(db, "auth")


def aal(claims: dict | None) -> str:
    return (claims or {}).get("aal") or "aal1"


def ip_prefix(addr: str | None) -> str | None:
    """The network part only: IPv4 /24, IPv6 /48. Never the full address."""
    import ipaddress
    try:
        ip = ipaddress.ip_address((addr or "").strip())
    except ValueError:
        return None
    net = ipaddress.ip_network(f"{ip}/{24 if ip.version == 4 else 48}", strict=False)
    return str(net)


AUTH_EVENTS = {
    # reported by the browser after a Supabase call (sign-in happens between the browser and Supabase)
    "sign_in_success", "sign_in_failure", "otp_requested", "mfa_enrolled", "mfa_verified", "mfa_failed",
    # recorded by the server itself
    "mfa_required", "mfa_reset", "role_changed", "password_changed", "global_sign_out", "data_export",
    "account_deleted", "kiosk_sign_out", "digilocker_linked", "digilocker_unlinked", "digilocker_failed",
}


def record(event: str, actor_id: str | None = None, actor_role: str | None = None, details: dict | None = None,
           db=None) -> None:
    """Append an auth event: actor id, event, time and IP prefix. `details` holds enums and counts only — never an
    email, phone number, code, token or profile value. Queued with the caller's transaction."""
    from .db import dumps, get_db, iso, new_id
    assert event in AUTH_EVENTS, event
    try:
        prefix = ip_prefix(request.remote_addr)
    except RuntimeError:  # outside a request (CLI)
        prefix = None
    (db or get_db()).execute(
        "INSERT INTO auth_events(event_id, ts, event, actor_id, actor_role, ip_prefix, details_json)"
        " VALUES (?,?,?,?,?,?,?)",
        (new_id("AEV"), iso(), event, actor_id or "anonymous", actor_role or "anonymous", prefix, dumps(details or {})))


def recent_events(limit: int = 500) -> list[dict]:
    import json as _json
    from .db import get_db
    rows = get_db().execute("SELECT ts, event, actor_id, actor_role, ip_prefix, details_json FROM auth_events"
                            " ORDER BY ts DESC, event_id DESC LIMIT ?", (limit,)).fetchall()
    return [{"ts": r["ts"], "event": r["event"], "actor_id": r["actor_id"], "actor_role": r["actor_role"],
             "ip_prefix": r["ip_prefix"], "details": _json.loads(r["details_json"])} for r in rows]


def staff_role(claims: dict | None) -> str | None:
    """A staff role is only ever read from app_metadata, which only the server (service role) can set."""
    if not claims or claims.get("is_anonymous"):
        return None
    role = (claims.get("app_metadata") or {}).get("role")
    return role if role in STAFF_ROLES else None


def citizen_claims() -> dict | None:
    """Claims of a signed-in citizen (anonymous or with email); None for no token or a staff token."""
    claims = g.get("auth")
    return claims if claims and not staff_role(claims) else None


# ---------------------------------------------------------------- admin API (server-side only)

def _admin(method: str, path: str, cfg=None, **kw):
    cfg = cfg or current_app.config
    if not (cfg["SUPABASE_URL"] and cfg["SUPABASE_SECRET_KEY"]):
        raise ApiError("AUTH_ADMIN_NOT_CONFIGURED", "SUPABASE_URL / SUPABASE_SECRET_KEY are not set.", 503)
    headers = {"apikey": cfg["SUPABASE_SECRET_KEY"], "User-Agent": "anvaya-backend", "Content-Type": "application/json"}
    return requests.request(method, f"{cfg['SUPABASE_URL']}/auth/v1/admin{path}", headers=headers, timeout=10, **kw)


def delete_auth_user(auth_user_id: str, cfg=None) -> bool:
    """Hard-delete a Supabase Auth user. True when deleted (or already gone)."""
    try:
        r = _admin("DELETE", f"/users/{auth_user_id}", cfg, data=json.dumps({"should_soft_delete": False}))
    except (requests.RequestException, ApiError) as e:
        log.warning("auth: delete user failed (%s)", type(e).__name__)
        return False
    if r.status_code not in (200, 204, 404):
        log.warning("auth: delete user failed (HTTP %s)", r.status_code)
    return r.status_code in (200, 204, 404)


def sign_out_everywhere(access_token: str, cfg=None) -> bool:
    """Supabase global sign-out for the token's user: every refresh token of every session is revoked
    (POST /auth/v1/logout?scope=global with the user's own access token). Access tokens stay valid until they expire,
    which is why revoke_sessions() is also recorded."""
    cfg = cfg or current_app.config
    key = cfg["SUPABASE_SECRET_KEY"]
    if not (cfg["SUPABASE_URL"] and key):
        return False
    try:
        r = requests.post(f"{cfg['SUPABASE_URL']}/auth/v1/logout?scope=global", timeout=10,
                          headers={"apikey": key, "Authorization": f"Bearer {access_token}", "User-Agent": "anvaya-backend"})
    except requests.RequestException as e:
        log.warning("auth: global sign-out failed (%s)", type(e).__name__)
        return False
    if r.status_code not in (200, 204, 401, 403, 404):  # 401/404: the session is already gone
        log.warning("auth: global sign-out failed (HTTP %s)", r.status_code)
        return False
    return True


def list_factors(user_id: str, cfg=None) -> list[dict]:
    r = _admin("GET", f"/users/{user_id}/factors", cfg)
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, list) else data.get("factors", [])


def delete_factors(user_id: str, cfg=None) -> int:
    """Remove every MFA factor of a user (admin reset). Returns how many were removed."""
    removed = 0
    for f in list_factors(user_id, cfg):
        r = _admin("DELETE", f"/users/{user_id}/factors/{f['id']}", cfg)
        if r.status_code not in (200, 204, 404):
            r.raise_for_status()
        removed += 1
    return removed


def get_user(user_id: str, cfg=None) -> dict | None:
    r = _admin("GET", f"/users/{user_id}", cfg)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json()


def staff_accounts(cfg=None) -> list[dict]:
    """Staff users with their role and MFA state (no emails beyond what the admin page shows)."""
    out = []
    for u in list_users(cfg or current_app.config):
        role = (u.get("app_metadata") or {}).get("role")
        if role in STAFF_ROLES:
            factors = [f for f in u.get("factors") or [] if f.get("factor_type") == "totp"]
            out.append({"user_id": u["id"], "email": u.get("email"), "role": role,
                        "mfa_enrolled": any(f.get("status") == "verified" for f in factors),
                        "last_sign_in_at": u.get("last_sign_in_at")})
    return sorted(out, key=lambda s: (s["role"], s["email"] or ""))


def list_users(cfg) -> list[dict]:
    users, page = [], 1
    while True:
        r = _admin("GET", f"/users?page={page}&per_page=1000", cfg)
        r.raise_for_status()
        batch = r.json().get("users", [])
        users += batch
        if len(batch) < 1000:
            return users
        page += 1


def upsert_staff(cfg, email: str, password: str, role: str) -> dict:
    """Create or update a staff account; the role goes into app_metadata. Returns {action: 'created' | 'updated',
    user_id, previous_role}. The caller records the role change and, for an update (the password is set again),
    revokes the account's existing sessions."""
    existing = next((u for u in list_users(cfg) if (u.get("email") or "").lower() == email.lower()), None)
    if existing:
        previous = (existing.get("app_metadata") or {}).get("role")
        meta = {**(existing.get("app_metadata") or {}), "role": role}
        r = _admin("PUT", f"/users/{existing['id']}", cfg, data=json.dumps({"password": password, "app_metadata": meta}))
        r.raise_for_status()
        return {"action": "updated", "user_id": existing["id"], "previous_role": previous}
    r = _admin("POST", "/users", cfg, data=json.dumps({"email": email, "password": password, "email_confirm": True,
                                                       "app_metadata": {"role": role}}))
    r.raise_for_status()
    try:
        created = r.json().get("id")
    except (AttributeError, ValueError):
        created = None
    return {"action": "created", "user_id": created, "previous_role": None}
