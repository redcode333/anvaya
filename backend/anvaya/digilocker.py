"""DigiLocker / Meri Pehchaan-ready sign-in: a generic OAuth 2.0 / OpenID Connect authorization-code flow with PKCE.

Disabled unless DIGILOCKER_ENABLED=true and every endpoint is configured from the environment (DIGILOCKER_CLIENT_ID,
DIGILOCKER_CLIENT_SECRET, DIGILOCKER_AUTH_URL, DIGILOCKER_TOKEN_URL, DIGILOCKER_JWKS_URL, DIGILOCKER_REDIRECT_URI,
DIGILOCKER_SCOPES; optional DIGILOCKER_ISSUER). No real endpoint is written here: partner onboarding provides them.

1. start: the signed-in citizen (anonymous is fine) asks for an authorization URL for their current personal session.
   We keep sha256(state), the nonce and the PKCE code_verifier for DIGILOCKER_STATE_TTL_S, and send the browser to
   the provider with state, nonce and code_challenge (S256).
2. finish: the browser hands back code + state. The state is single use, must not be expired and must belong to the
   same user. The code is exchanged (client secret + code_verifier) at the token endpoint; the ID token's signature is
   checked against the provider's JWKS (asymmetric algorithms only), with audience = client id, issuer (if
   configured), expiry and nonce.
3. The provider subject is linked to the citizen (provider + sha256(pepper + subject); no raw id, no tokens kept) and
   name, date of birth and gender become facts with source="digilocker", confirmed and verified.

The Aadhaar number is never requested (scopes naming it are dropped) and never read from the response: only the three
claims above are used. Tokens, codes and claims are never logged.
"""
import base64
import hashlib
import json
import logging
import secrets
from datetime import date, datetime, timedelta
from urllib.parse import urlencode

import jwt
import requests
from flask import current_app

from . import auth, profile
from .accounts import citizen_id_for, pepper
from .common import ApiError, audit, sha256
from .db import get_db, iso, now, parse_iso

log = logging.getLogger(__name__)

PROVIDER = "digilocker"
ALGORITHMS = ["RS256", "RS384", "RS512", "PS256", "ES256", "ES384"]
REQUIRED = ("DIGILOCKER_CLIENT_ID", "DIGILOCKER_CLIENT_SECRET", "DIGILOCKER_AUTH_URL", "DIGILOCKER_TOKEN_URL",
            "DIGILOCKER_JWKS_URL", "DIGILOCKER_REDIRECT_URI")
GENDERS = {"m": "male", "male": "male", "f": "female", "female": "female", "t": "other", "o": "other",
           "other": "other", "transgender": "other"}


def missing(cfg) -> list[str]:
    return [k for k in REQUIRED if not cfg.get(k)]


def enabled(cfg) -> bool:
    return bool(cfg.get("DIGILOCKER_ENABLED")) and not missing(cfg)


def scopes(cfg) -> str:
    """The configured scopes without anything that names Aadhaar; always includes openid."""
    out = [s for s in (cfg.get("DIGILOCKER_SCOPES") or "openid").split()
           if "aadhaar" not in s.lower() and "aadhar" not in s.lower() and s.lower() != "uid"]
    return " ".join(["openid"] + [s for s in out if s != "openid"])


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def pkce_challenge(verifier: str) -> str:
    return _b64url(hashlib.sha256(verifier.encode()).digest())


def _require_enabled():
    cfg = current_app.config
    if not enabled(cfg):
        raise ApiError("DIGILOCKER_DISABLED", "DigiLocker sign-in is not enabled on this server.", 404)
    return cfg


def start(claims: dict, session_id: str | None) -> dict:
    cfg = _require_enabled()
    if not session_id:
        raise ApiError("SESSION_REQUIRED", "Start DigiLocker from your current session.", 400)
    session = profile.get_session(session_id)  # owned by this citizen, not ended
    if session["mode"] != "personal" or session.get("auth_user_id") != claims["sub"]:
        raise ApiError("SESSION_FORBIDDEN", "DigiLocker can only be linked from your own personal session.", 403)
    state, nonce = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)  # 86 characters (RFC 7636: 43-128)
    db = get_db()
    db.execute("DELETE FROM oidc_states WHERE expires_at < ?", (iso(),))
    db.execute("INSERT INTO oidc_states(state_hash, provider, auth_user_id, session_id, nonce, code_verifier,"
               " created_at, expires_at) VALUES (?,?,?,?,?,?,?,?)",
               (sha256(state), PROVIDER, claims["sub"], session_id, nonce, verifier, iso(),
                iso(now() + timedelta(seconds=cfg["DIGILOCKER_STATE_TTL_S"]))))
    db.commit()
    query = urlencode({"response_type": "code", "client_id": cfg["DIGILOCKER_CLIENT_ID"],
                       "redirect_uri": cfg["DIGILOCKER_REDIRECT_URI"], "scope": scopes(cfg), "state": state,
                       "nonce": nonce, "code_challenge": pkce_challenge(verifier), "code_challenge_method": "S256"})
    sep = "&" if "?" in cfg["DIGILOCKER_AUTH_URL"] else "?"
    return {"authorization_url": f"{cfg['DIGILOCKER_AUTH_URL']}{sep}{query}"}


def _fail(code: str, message: str, status: int = 400, reason: str | None = None, actor: str | None = None):
    auth.record("digilocker_failed", actor, "citizen", {"reason": reason or code})
    get_db().commit()
    raise ApiError(code, message, status)


def _signing_key(token: str, cfg):
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        return None, None
    if header.get("alg") not in ALGORITHMS:
        return None, None  # never "none" or a symmetric algorithm
    r = requests.get(cfg["DIGILOCKER_JWKS_URL"], timeout=10, headers={"User-Agent": "anvaya-backend"})
    r.raise_for_status()
    for k in r.json().get("keys", []):
        if k.get("kid") == header.get("kid") or (not header.get("kid") and len(r.json()["keys"]) == 1):
            return jwt.PyJWK.from_dict(k, algorithm=header["alg"]).key, header["alg"]
    return None, None


def _birthdate(raw) -> str | None:
    s = str(raw or "").strip()
    for fmt in ("%Y-%m-%d", "%d%m%Y", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def finish(claims: dict, code: str, state: str) -> dict:
    cfg = _require_enabled()
    actor = claims["sub"]
    db = get_db()
    row = db.execute("SELECT * FROM oidc_states WHERE state_hash=? AND provider=?", (sha256(state or ""), PROVIDER)).fetchone()
    if row:
        db.execute("DELETE FROM oidc_states WHERE state_hash=?", (row["state_hash"],))  # single use
        db.commit()
    if not row or row["auth_user_id"] != actor:
        _fail("INVALID_STATE", "This DigiLocker sign-in is not valid. Start again.", reason="invalid_state", actor=actor)
    if parse_iso(row["expires_at"]) < now():
        _fail("STATE_EXPIRED", "This DigiLocker sign-in took too long. Start again.", reason="state_expired", actor=actor)
    if not code:
        _fail("CODE_REQUIRED", "DigiLocker did not return a code. Start again.", reason="no_code", actor=actor)
    try:
        r = requests.post(cfg["DIGILOCKER_TOKEN_URL"], timeout=15, headers={"Accept": "application/json"},
                          data={"grant_type": "authorization_code", "code": code,
                                "redirect_uri": cfg["DIGILOCKER_REDIRECT_URI"], "client_id": cfg["DIGILOCKER_CLIENT_ID"],
                                "client_secret": cfg["DIGILOCKER_CLIENT_SECRET"], "code_verifier": row["code_verifier"]})
    except requests.RequestException as e:
        log.warning("digilocker: token endpoint unreachable (%s)", type(e).__name__)
        _fail("DIGILOCKER_UNAVAILABLE", "DigiLocker cannot be reached right now. Try again.", 502,
              reason="token_unreachable", actor=actor)
    if r.status_code != 200:
        log.warning("digilocker: code exchange refused (HTTP %s)", r.status_code)
        _fail("DIGILOCKER_CODE_REJECTED", "DigiLocker did not accept this sign-in (it may have expired). Start again.",
              reason="code_rejected", actor=actor)
    id_token = (r.json() or {}).get("id_token")
    if not id_token:
        _fail("DIGILOCKER_NO_ID_TOKEN", "DigiLocker did not return an ID token.", 502, reason="no_id_token", actor=actor)
    try:
        key, alg = _signing_key(id_token, cfg)
    except (requests.RequestException, ValueError, jwt.PyJWTError) as e:
        log.warning("digilocker: signing keys unavailable (%s)", type(e).__name__)
        key, alg = None, None
    if key is None:
        _fail("DIGILOCKER_BAD_TOKEN", "The DigiLocker answer could not be verified.", reason="bad_signature", actor=actor)
    issuer = cfg.get("DIGILOCKER_ISSUER") or None
    try:
        idc = jwt.decode(id_token, key, algorithms=[alg], audience=cfg["DIGILOCKER_CLIENT_ID"], issuer=issuer,
                         leeway=30, options={"require": ["exp", "iat", "sub", "aud"], "verify_iss": bool(issuer)})
    except jwt.PyJWTError:
        _fail("DIGILOCKER_BAD_TOKEN", "The DigiLocker answer could not be verified.", reason="bad_signature", actor=actor)
    if not secrets.compare_digest(str(idc.get("nonce") or ""), row["nonce"]):
        _fail("DIGILOCKER_BAD_TOKEN", "The DigiLocker answer could not be verified.", reason="bad_nonce", actor=actor)
    return _link(claims, row["session_id"], idc)


def _link(claims: dict, session_id: str, idc: dict) -> dict:
    """Link the provider subject to the citizen and store the three verified facts. Nothing else from the ID token is
    read (in particular no Aadhaar number, masked or not)."""
    db = get_db()
    cid = citizen_id_for(claims["sub"])
    subject = sha256(pepper() + f"{PROVIDER}:{idc['sub']}")
    other = db.execute("SELECT citizen_id FROM linked_identities WHERE provider=? AND subject_hash=?",
                       (PROVIDER, subject)).fetchone()
    if other and other["citizen_id"] != cid:
        _fail("IDENTITY_LINKED_ELSEWHERE", "This DigiLocker account is already linked to another Anvaya account.", 409,
              reason="linked_elsewhere", actor=claims["sub"])
    values = {"applicant_name": (str(idc.get("name") or "").strip()[:80] or None),
              "date_of_birth": _birthdate(idc.get("birthdate") or idc.get("dob")),
              "gender": GENDERS.get(str(idc.get("gender") or "").strip().lower())}
    session, facts, _ = profile.load(session_id)
    from .accounts import queue_citizen
    queue_citizen(claims)
    if not other:
        db.execute("INSERT INTO linked_identities(provider, subject_hash, citizen_id, linked_at) VALUES (?,?,?,?)",
                   (PROVIDER, subject, cid, iso()))
    stored = []
    for attr, value in values.items():
        if value is None:
            continue
        if attr == "date_of_birth" and date.fromisoformat(value) > date.today():
            continue
        res = profile.upsert_fact(session_id, attr, value, source="digilocker", raw_text=None, confidence=1.0,
                                  confirmed=True, verified=True, facts=facts)
        stored.append({"attribute": attr, "fact_id": res["fact"]["fact_id"]})
    profile.refresh_workflow_state(session_id, session, facts)
    audit("account.identity_linked", session_id=session_id,
          details={"provider": PROVIDER, "facts": [s["fact_id"] for s in stored]})
    auth.record("digilocker_linked", claims["sub"], "citizen", {"facts": [s["attribute"] for s in stored]})
    db.commit()
    return {"linked": True, "provider": PROVIDER, "facts": stored}


_ME_KEYS = {"applicant_name": "name", "date_of_birth": "dob", "gender": "gender"}


def me(claims: dict) -> dict:
    """Is this citizen linked to DigiLocker, and which verified facts did it give (name, date of birth, gender)?"""
    db = get_db()
    cid = citizen_id_for(claims["sub"])
    if not db.execute("SELECT 1 FROM linked_identities WHERE provider=? AND citizen_id=?", (PROVIDER, cid)).fetchone():
        return {"linked": False, "facts": {}}
    rows = db.execute("SELECT f.attribute, f.value_json FROM facts f JOIN sessions s ON s.session_id = f.session_id"
                      " WHERE s.citizen_id=? AND f.source='digilocker' AND f.superseded_by IS NULL", (cid,)).fetchall()
    return {"linked": True, "facts": {_ME_KEYS[r["attribute"]]: json.loads(r["value_json"])
                                      for r in rows if r["attribute"] in _ME_KEYS}}


def unlink(claims: dict) -> dict:
    """Remove the link. The facts stay but are no longer marked verified, so the citizen can change them."""
    db = get_db()
    cid = citizen_id_for(claims["sub"])
    with db.transaction():
        db.execute("DELETE FROM linked_identities WHERE provider=? AND citizen_id=?", (PROVIDER, cid))
        db.execute("UPDATE facts SET verified=0 WHERE source='digilocker' AND session_id IN"
                   " (SELECT session_id FROM sessions WHERE citizen_id=?)", (cid,))
        audit("account.identity_unlinked", details={"provider": PROVIDER})
        auth.record("digilocker_unlinked", claims["sub"], "citizen", {})
    return {"linked": False}


def describe(cfg) -> dict:
    """For the startup report: on/off and which variable names are missing (never values)."""
    return {"enabled": enabled(cfg), "missing": missing(cfg) if cfg.get("DIGILOCKER_ENABLED") else []}
