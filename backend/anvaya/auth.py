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
    """before_request: verify the bearer token, if any, and keep its claims on g.auth (None without a token)."""
    g.auth = None
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer ") and request.path.startswith("/api/"):
        g.auth = verify_token(header[7:].strip())


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


def upsert_staff(cfg, email: str, password: str, role: str) -> str:
    """Create or update a staff account; the role goes into app_metadata. Returns 'created' or 'updated'."""
    existing = next((u for u in list_users(cfg) if (u.get("email") or "").lower() == email.lower()), None)
    if existing:
        meta = {**(existing.get("app_metadata") or {}), "role": role}
        r = _admin("PUT", f"/users/{existing['id']}", cfg, data=json.dumps({"password": password, "app_metadata": meta}))
        r.raise_for_status()
        return "updated"
    r = _admin("POST", "/users", cfg, data=json.dumps({"email": email, "password": password, "email_confirm": True,
                                                       "app_metadata": {"role": role}}))
    r.raise_for_status()
    return "created"
