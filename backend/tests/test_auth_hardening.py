"""Production auth hardening: staff MFA (aal2) enforced by the backend, admin MFA reset, sign out of all devices
(revocation of still-valid access tokens), kiosk temporary sessions (128-bit ids kept out of URLs and logs, bound to
device + operator, 30-minute limit, operator sign-out ends them), "Download my data", the auth audit log, rate limits,
the Content-Security-Policy, and the DigiLocker OIDC adapter tested end to end against a local mock provider."""
import base64
import hashlib
import json
import logging
import re
import secrets
import threading
import time
import uuid
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import jwt
import pytest
from conftest import KIOSK_DEVICE, SUPABASE_URL, bearer, kiosk, staff, staff_id, token
from cryptography.hazmat.primitives.asymmetric import rsa

from anvaya import auth, digilocker
from anvaya.db import connect, iso, now

TC1 = ("I am 67 years old, a farmer in a village in Guntur, Andhra Pradesh. Family of 4, yearly income 60,000 rupees. "
       "We have a BPL card, I do not get any pension, I own 2 acres of land and have a bank account.")


def rows(app, sql, params=()):
    db = connect(app.config)
    try:
        return db.execute(sql, params).fetchall()
    finally:
        db.close()


def write(app, sql, params=()):
    db = connect(app.config)
    try:
        db.execute(sql, params)
        db.commit()
    finally:
        db.close()


def citizen_headers(uid=None, **kw):
    return bearer(token(uid or str(uuid.uuid4()), **kw))


def personal_session(client, headers, utterance=TC1):
    r = client.post("/api/v1/sessions", json={"mode": "personal", "language": "en"}, headers=headers)
    assert r.status_code == 201, r.json
    sid = r.json["session_id"]
    assert client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": utterance}, headers=headers).status_code == 200
    return sid


# ---------------------------------------------------------------- 1. staff MFA

@pytest.mark.parametrize("path", ["/api/v1/reviewer/cases", "/api/v1/admin/schemes/freshness"])
def test_staff_token_at_aal1_is_refused_with_mfa_required(app, client, path):
    r = client.get(path, headers=staff("reviewer", aal="aal1"))
    assert r.status_code == 403 and r.json["error"]["code"] == "MFA_REQUIRED"
    assert client.get(path, headers=staff("reviewer", aal="aal2")).status_code == 200
    ev = rows(app, "SELECT actor_id, details_json FROM auth_events WHERE event='mfa_required' ORDER BY ts DESC LIMIT 1")
    assert ev[0][0] == staff_id("reviewer") and "endpoint" in json.loads(ev[0][1])


def test_every_staff_path_needs_aal2_not_only_role_decorated_ones(client):
    aal1 = {**staff("operator", aal="aal1"), "X-Kiosk-Device": KIOSK_DEVICE}
    r = client.post("/api/v1/sessions", json={"mode": "kiosk", "language": "en"}, headers=aal1)
    assert r.status_code == 403 and r.json["error"]["code"] == "MFA_REQUIRED"
    r = client.post("/api/v1/passport/resume", json={"code": "PSP-0000-0000", "pin": "4826"}, headers=aal1)
    assert r.json["error"]["code"] == "MFA_REQUIRED"
    assert client.post("/api/v1/sessions", json={"mode": "kiosk", "language": "en"}, headers=kiosk()).status_code == 201


def test_auth_me_tells_the_browser_to_ask_for_the_code(client):
    me = client.get("/api/v1/auth/me", headers=staff("admin", aal="aal1")).json
    assert me["mfa_required"] is True and me["user"]["aal"] == "aal1" and me["user"]["role"] == "admin"
    assert client.get("/api/v1/auth/me", headers=staff("admin")).json["mfa_required"] is False


def test_citizens_never_need_mfa(client):
    h = citizen_headers(anonymous=True)
    assert client.post("/api/v1/sessions", json={"mode": "personal"}, headers=h).status_code == 201


def test_admin_resets_staff_mfa_audited_and_signed_out(app, client, monkeypatch):
    target = staff_id("operator")
    old = kiosk()  # the operator's current (aal2) sign-in
    assert client.get("/api/v1/auth/me", headers=old).status_code == 200
    monkeypatch.setattr(auth, "get_user", lambda uid, cfg=None: {"id": uid, "app_metadata": {"role": "operator"}})
    removed = []
    monkeypatch.setattr(auth, "delete_factors", lambda uid, cfg=None: removed.append(uid) or 1)
    assert client.post(f"/api/v1/admin/staff/{target}/reset-mfa", headers=staff("reviewer")).status_code == 403
    r = client.post(f"/api/v1/admin/staff/{target}/reset-mfa", headers=staff("admin"))
    assert r.status_code == 200 and r.json["factors_removed"] == 1 and removed == [target]
    # existing tokens of that sign-in are refused at once; a new sign-in (later amr time) works again
    r = client.get("/api/v1/auth/me", headers=old)
    assert r.status_code == 401 and r.json["error"]["code"] == "SESSION_REVOKED"
    assert client.get("/api/v1/auth/me", headers=kiosk(signed_in_at=time.time() + 2)).status_code == 200
    ev = json.loads(rows(app, "SELECT details_json FROM auth_events WHERE event='mfa_reset' ORDER BY ts DESC LIMIT 1")[0][0])
    assert ev == {"user_id": target, "role": "operator", "factors_removed": 1}
    write(app, "DELETE FROM auth_revocations WHERE user_id=?", (target,))
    from anvaya.db import reset_caches
    reset_caches(connect(app.config))


def test_admin_reset_refuses_non_staff(client, monkeypatch):
    monkeypatch.setattr(auth, "get_user", lambda uid, cfg=None: {"id": uid, "app_metadata": {}})
    r = client.post(f"/api/v1/admin/staff/{uuid.uuid4()}/reset-mfa", headers=staff("admin"))
    assert r.status_code == 404


def test_staff_list_shows_mfa_state(client, monkeypatch):
    users = [{"id": "a", "email": "a@x", "app_metadata": {"role": "admin"},
              "factors": [{"factor_type": "totp", "status": "verified"}]},
             {"id": "b", "email": "b@x", "app_metadata": {"role": "operator"}, "factors": []},
             {"id": "c", "email": "citizen@x", "app_metadata": {}}]
    monkeypatch.setattr(auth, "list_users", lambda cfg: users)
    staff_rows = client.get("/api/v1/admin/staff", headers=staff("admin")).json["staff"]
    assert [(s["user_id"], s["mfa_enrolled"]) for s in staff_rows] == [("a", True), ("b", False)]


# ---------------------------------------------------------------- 5. sign out of all devices

@pytest.fixture()
def supabase_logout(monkeypatch):
    calls = []
    monkeypatch.setattr(auth, "sign_out_everywhere", lambda tok, cfg=None: calls.append(tok) or True)
    return calls


def test_sign_out_of_all_devices_refuses_old_tokens_even_after_refresh(app, client, supabase_logout):
    uid = str(uuid.uuid4())
    signed_in = time.time() - 600
    phone, laptop = citizen_headers(uid, email="c@example.org", signed_in_at=signed_in), \
        citizen_headers(uid, email="c@example.org", signed_in_at=signed_in - 100)
    assert client.get("/api/v1/auth/me", headers=laptop).status_code == 200
    r = client.post("/api/v1/auth/sign-out-all", json={}, headers=phone)
    assert r.status_code == 200 and len(supabase_logout) == 1
    for h in (phone, laptop, citizen_headers(uid, email="c@example.org", signed_in_at=signed_in)):  # a refreshed token keeps amr
        r = client.get("/api/v1/auth/me", headers=h)
        assert r.status_code == 401 and r.json["error"]["code"] == "SESSION_REVOKED"
    assert client.get("/api/v1/auth/me", headers=citizen_headers(uid, email="c@example.org",
                                                                 signed_in_at=time.time() + 2)).status_code == 200
    ev = json.loads(rows(app, "SELECT details_json FROM auth_events WHERE event='global_sign_out' AND actor_id=?", (uid,))[0][0])
    assert ev == {"reason": "user", "supabase": True}


def test_staff_password_change_forces_global_sign_out(app, client, supabase_logout):
    uid = str(uuid.uuid4())
    h = bearer(token(uid, role="reviewer", email="r2@anvaya.test", aal="aal2"))
    assert client.post("/api/v1/auth/sign-out-all", json={"reason": "password_changed"}, headers=h).status_code == 200
    assert client.get("/api/v1/reviewer/cases", headers=h).json["error"]["code"] == "SESSION_REVOKED"
    events = [r[0] for r in rows(app, "SELECT event FROM auth_events WHERE actor_id=?", (uid,))]
    assert "password_changed" in events and "global_sign_out" in events


def test_seed_staff_password_update_revokes_sessions_and_logs_role_change(app, monkeypatch, capsys):
    from anvaya import manage
    monkeypatch.setattr(manage, "_record_staff_change", manage._record_staff_change)
    uid = str(uuid.uuid4())
    manage._record_staff_change(app, {"action": "updated", "user_id": uid, "previous_role": "operator"}, "reviewer")
    events = {r[0]: json.loads(r[1]) for r in rows(app, "SELECT event, details_json FROM auth_events WHERE details_json LIKE ?",
                                                     (f"%{uid}%",))}
    assert events["role_changed"] == {"user_id": uid, "from": "operator", "to": "reviewer"}
    assert events["password_changed"]["global_sign_out"] is True
    assert rows(app, "SELECT reason FROM auth_revocations WHERE user_id=?", (uid,))[0][0] == "password_changed"


# ---------------------------------------------------------------- 6. auth audit

def test_browser_reported_events_store_prefix_only_and_no_secrets(app, client):
    uid = str(uuid.uuid4())
    h = {**citizen_headers(uid, email="secret.person@example.org")}
    r = client.post("/api/v1/auth/events", json={"event": "sign_in_success", "method": "email_otp",
                                                 "email": "secret.person@example.org", "code": "123456"},
                    headers=h, environ_base={"REMOTE_ADDR": "203.0.113.77"})
    assert r.status_code == 201
    row = rows(app, "SELECT * FROM auth_events WHERE actor_id=?", (uid,))[0]
    assert row["ip_prefix"] == "203.0.113.0/24" and row["actor_role"] == "citizen"
    assert json.loads(row["details_json"]) == {"method": "email_otp"}
    flat = json.dumps([dict(r) for r in rows(app, "SELECT * FROM auth_events")])
    assert "secret.person" not in flat and "123456" not in flat and "203.0.113.77" not in flat
    assert client.post("/api/v1/auth/events", json={"event": "role_changed"}).status_code == 422  # server-only
    r = client.post("/api/v1/auth/events", json={"event": "sign_in_failure", "method": "password"})
    assert r.status_code == 201  # failures have no token: recorded as anonymous


def test_ip_prefix():
    assert auth.ip_prefix("198.51.100.9") == "198.51.100.0/24"
    assert auth.ip_prefix("2001:db8:abcd:12::1") == "2001:db8:abcd::/48"
    assert auth.ip_prefix("not-an-ip") is None


def test_admin_sees_the_last_500_auth_events(app, client):
    db = connect(app.config)
    try:
        with app.test_request_context():
            for _ in range(510):
                auth.record("otp_requested", "x", "citizen", {"method": "email_otp"}, db=db)
        db.commit()
    finally:
        db.close()
    assert client.get("/api/v1/admin/auth-events", headers=staff("reviewer")).status_code == 403
    events = client.get("/api/v1/admin/auth-events", headers=staff("admin")).json["events"]
    assert len(events) == 500 and set(events[0]) == {"ts", "event", "actor_id", "actor_role", "ip_prefix", "details"}


# ---------------------------------------------------------------- 2. rate limits on session-creating endpoints

def test_session_creation_is_rate_limited_per_ip(client, config):
    config(SESSION_CREATE_LIMIT_PER_MIN=3)
    ip = {"REMOTE_ADDR": "192.0.2.50"}
    codes = [client.post("/api/v1/sessions", json={"mode": "personal"}, environ_base=ip).status_code for _ in range(5)]
    assert codes[:3] == [201, 201, 201] and codes[3:] == [429, 429]
    other = client.post("/api/v1/sessions", json={"mode": "personal"}, environ_base={"REMOTE_ADDR": "192.0.2.51"})
    assert other.status_code == 201
    r = [client.post("/api/v1/passport/resume", json={"code": "PSP-AAAA-AAAA", "pin": "4826"},
                     environ_base={"REMOTE_ADDR": "192.0.2.52"}).status_code for _ in range(4)]
    assert r[-1] == 429


def test_auth_config_reports_turnstile_free_flags(client):
    cfg = client.get("/api/v1/auth/config").json
    assert cfg["kiosk_max_session_minutes"] == 30 and cfg["staff_mfa_required"] is True
    assert cfg["digilocker_enabled"] is False and cfg["phone_otp_enabled"] is False


# ---------------------------------------------------------------- 3. kiosk temporary sessions

def kiosk_session(client, headers=None):
    r = client.post("/api/v1/sessions", json={"mode": "kiosk", "language": "en"}, headers=headers or kiosk())
    assert r.status_code == 201, r.json
    return r.json


def test_session_ids_are_128_bit_random(client):
    ids = {kiosk_session(client)["session_id"] for _ in range(5)} | {
        client.post("/api/v1/sessions", json={"mode": "personal"}).json["session_id"] for _ in range(5)}
    assert len(ids) == 10 and all(re.fullmatch(r"SES_[0-9a-f]{32}", i) for i in ids)


def test_session_id_travels_in_a_header_and_never_in_logs(client, caplog):
    caplog.set_level(logging.INFO)
    sid = kiosk_session(client)["session_id"]
    h = {**kiosk(), "X-Session-Id": sid}
    assert client.post("/api/v1/sessions/current/turns", json={"utterance": TC1}, headers=h).status_code == 200
    assert client.get("/api/v1/sessions/current", headers=h).json["session"]["session_id"] == sid
    assert client.get("/api/v1/sessions/current", headers=kiosk()).json["error"]["code"] == "SESSION_REQUIRED"
    assert client.post("/api/v1/sessions/current/end", json={}, headers=h).json["ended"]
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "/sessions/<sid>" in logged and sid not in logged and "Bearer" not in logged


def test_kiosk_session_is_bound_to_device_and_operator(client):
    sid = kiosk_session(client)["session_id"]
    assert client.get(f"/api/v1/sessions/{sid}", headers=kiosk()).status_code == 200
    for h in ({}, staff("operator"), kiosk(device="KD-another-kiosk-9"), kiosk("admin"),
              citizen_headers(anonymous=True)):
        r = client.get(f"/api/v1/sessions/{sid}", headers=h)
        assert r.status_code in (403, 401) and r.json["error"]["code"] in ("SESSION_FORBIDDEN", "UNAUTHENTICATED"), h
    r = client.post("/api/v1/sessions", json={"mode": "kiosk"}, headers=staff("operator"))  # no device id
    assert r.status_code == 422 and r.json["error"]["code"] == "KIOSK_DEVICE_REQUIRED"


def test_kiosk_session_ends_after_the_absolute_limit(app, client):
    s = kiosk_session(client)
    created = rows(app, "SELECT created_at, expires_at FROM sessions WHERE session_id=?", (s["session_id"],))[0]
    from anvaya.db import parse_iso
    assert parse_iso(created[1]) - parse_iso(created[0]) == timedelta(minutes=30)
    client.post(f"/api/v1/sessions/{s['session_id']}/turns", json={"utterance": TC1}, headers=kiosk())
    write(app, "UPDATE sessions SET expires_at=? WHERE session_id=?", (iso(now() - timedelta(seconds=1)), s["session_id"]))
    r = client.post(f"/api/v1/sessions/{s['session_id']}/turns", json={"utterance": "hello"}, headers=kiosk())
    assert r.status_code == 410 and r.json["error"]["code"] == "SESSION_EXPIRED"


def test_kiosk_limit_is_configurable(app, client, config):
    config(KIOSK_MAX_SESSION_MINUTES=5)
    s = kiosk_session(client)
    from anvaya.db import parse_iso
    created, expires = rows(app, "SELECT created_at, expires_at FROM sessions WHERE session_id=?", (s["session_id"],))[0]
    assert parse_iso(expires) - parse_iso(created) == timedelta(minutes=5)


def test_operator_sign_out_ends_every_citizen_session_on_the_device(app, client):
    device = f"KD-{uuid.uuid4().hex[:16]}"
    mine = [kiosk_session(client, kiosk(device=device))["session_id"] for _ in range(2)]
    by_admin = kiosk_session(client, kiosk("admin", device=device))["session_id"]  # earlier shift, same device
    elsewhere = kiosk_session(client, kiosk(device=f"KD-{uuid.uuid4().hex[:16]}"))["session_id"]
    for sid in mine:
        client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": TC1}, headers=kiosk(device=device))
    assert client.post("/api/v1/kiosk/sign-out", json={}, headers=citizen_headers()).status_code == 401
    r = client.post("/api/v1/kiosk/sign-out", json={}, headers=kiosk(device=device))
    assert r.status_code == 200 and r.json["sessions_ended"] == 3
    ended = {r[0]: r[1] for r in rows(app, "SELECT session_id, ended_at FROM sessions WHERE session_id IN (?,?,?,?)",
                                          (*mine, by_admin, elsewhere))}
    assert all(ended[s] for s in (*mine, by_admin)) and ended[elsewhere] is None
    assert rows(app, "SELECT COUNT(*) FROM facts WHERE session_id IN (?,?)", tuple(mine))[0][0] == 0


def test_after_end_session_nothing_can_be_restored(app, client):
    """A browser refresh after End session: the kiosk keeps the id only in memory, and even a copied id is useless."""
    sid = kiosk_session(client)["session_id"]
    client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": TC1}, headers=kiosk())
    client.post(f"/api/v1/sessions/{sid}/end", json={"reason": "user"}, headers=kiosk())
    for method, path in (("get", f"/api/v1/sessions/{sid}/eligibility/latest"),
                         ("post", f"/api/v1/sessions/{sid}/turns"), ("post", f"/api/v1/sessions/{sid}/eligibility/evaluate")):
        r = getattr(client, method)(path, json={"utterance": "x"} if method == "post" else None, headers=kiosk())
        assert r.status_code in (404, 410), (path, r.json)
    assert client.get(f"/api/v1/sessions/{sid}", headers=kiosk()).json["facts"] == []
    assert rows(app, "SELECT COUNT(*) FROM turns WHERE session_id=?", (sid,))[0][0] == 0


# ---------------------------------------------------------------- 4. download my data

def test_download_my_data_has_only_the_citizens_own_data(app, client):
    uid, other = str(uuid.uuid4()), str(uuid.uuid4())
    h, ho = citizen_headers(uid, email="me@example.org"), citizen_headers(other, email="other@example.org")
    consent = {"consent": {"version": app.config["CONSENT_VERSION"], "accepted": True, "language": "hi"}}
    assert client.post("/api/v1/account/consent", json=consent, headers=h).status_code == 200
    sid = personal_session(client, h)
    for fid in client.post(f"/api/v1/sessions/{sid}/profile/confirm-all", headers=h).json["needs_confirmation"]:
        client.patch(f"/api/v1/sessions/{sid}/profile/facts/{fid}", json={"confirmed": True}, headers=h)
    assert client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate", headers=h).status_code == 200
    osid = personal_session(client, ho, "I am 31 years old and live in Kerala. Family of 7.")
    r = client.get("/api/v1/account/export", headers=h)
    assert r.status_code == 200 and "attachment" in r.headers["Content-Disposition"]
    assert r.headers["Cache-Control"] == "no-store"
    data = r.json
    assert data["format"] == "anvaya-my-data/1" and data["citizen"]["citizen_id"] == f"CIT_{uid}"
    assert {f["attribute"]: f["value"] for f in data["facts"]}["age"] == 67
    assert all(f["session_id"] == sid for f in data["facts"]) and all("raw_text" not in f for f in data["facts"])
    assert len(data["passport_versions"]) >= 1 and data["passport_versions"][0]["facts"]["age"] == 67
    assert data["consents"][0]["purpose"] == "save_passports" and data["consents"][0]["version"] == app.config["CONSENT_VERSION"]
    assert set(data) >= {"documents", "document_marks", "cases", "linked_identities", "retention", "sessions"}
    flat = json.dumps(data)
    assert osid not in flat and "Kerala" not in flat and other not in flat and "farmer in a village" not in flat
    ev = json.loads(rows(app, "SELECT details_json FROM auth_events WHERE event='data_export' AND actor_id=?", (uid,))[0][0])
    assert ev["facts"] == len(data["facts"]) and "67" not in json.dumps(ev)
    assert client.get("/api/v1/account/export").status_code == 401


def test_unsaved_session_can_export_its_own_data(client):
    sid = client.post("/api/v1/sessions", json={"mode": "personal"}).json["session_id"]
    client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": TC1})
    data = client.get("/api/v1/sessions/current/export", headers={"X-Session-Id": sid}).json
    assert data["citizen"] is None and {f["attribute"] for f in data["facts"]} >= {"age", "state"}


def test_delete_is_audited_without_values(app, client, monkeypatch):
    monkeypatch.setattr(auth, "delete_auth_user", lambda uid, cfg=None: True)
    uid = str(uuid.uuid4())
    h = citizen_headers(uid, email="del@example.org")
    personal_session(client, h)
    assert client.delete("/api/v1/account", headers=h).json["deleted"]
    ev = json.loads(rows(app, "SELECT details_json FROM auth_events WHERE event='account_deleted' AND actor_id=?", (uid,))[0][0])
    assert set(ev) == {"sessions_deleted", "cases_kept"}


# ---------------------------------------------------------------- 9. Content-Security-Policy

def test_strict_csp_on_every_response(client):
    for path in ("/api/v1/health", "/", "/citizen"):
        csp = client.get(path).headers["Content-Security-Policy"]
        assert "default-src 'self'" in csp and "script-src 'self' https://challenges.cloudflare.com" in csp
        assert f"connect-src 'self' {SUPABASE_URL}" in csp and "frame-src 'self' https://challenges.cloudflare.com" in csp
        assert "'unsafe-inline'" not in csp and "'unsafe-eval'" not in csp and "object-src 'none'" in csp


# ---------------------------------------------------------------- 7. DigiLocker / Meri Pehchaan against a mock OIDC provider

class MockOIDC:
    """A local OpenID provider: issues codes bound to a PKCE challenge, exchanges them once, signs ID tokens (RS256)."""

    def __init__(self):
        self.key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.codes: dict[str, dict] = {}
        self.sign_with_other_key = False
        self.wrong_nonce = False
        self.token_requests: list[dict] = []
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, status, body):
                raw = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):
                if self.path == "/jwks":
                    jwk = jwt.algorithms.RSAAlgorithm.to_jwk(mock.key.public_key(), as_dict=True)
                    return self._send(200, {"keys": [{**jwk, "kid": "dl-1", "alg": "RS256", "use": "sig"}]})
                self._send(404, {})

            def do_POST(self):
                form = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode()).items()}
                mock.token_requests.append(form)
                c = mock.codes.pop(form.get("code", ""), None)
                if not c or c["expires"] < time.time():
                    return self._send(400, {"error": "invalid_grant"})
                if form.get("client_secret") != "dl-secret" or form.get("client_id") != c["client_id"]:
                    return self._send(401, {"error": "invalid_client"})
                if form.get("redirect_uri") != c["redirect_uri"]:
                    return self._send(400, {"error": "invalid_grant"})
                verifier = form.get("code_verifier", "")
                if base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode() != c["challenge"]:
                    return self._send(400, {"error": "invalid_grant", "error_description": "PKCE"})
                t = int(time.time())
                claims = {"iss": mock.base, "aud": c["client_id"], "sub": c["sub"], "iat": t, "exp": t + 300,
                          "nonce": "not-the-nonce" if mock.wrong_nonce else c["nonce"], "name": "Lakshmi Devi",
                          "birthdate": "1958-03-14", "gender": "F",
                          "aadhaar": "999911112222", "masked_aadhaar": "XXXX-XXXX-2222"}
                key = mock.other_key if mock.sign_with_other_key else mock.key
                idt = jwt.encode(claims, key, algorithm="RS256", headers={"kid": "dl-1"})
                self._send(200, {"access_token": secrets.token_hex(8), "token_type": "Bearer", "id_token": idt})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def authorize(self, url: str, sub="dl-subject-1", expires_in=60) -> tuple[str, str]:
        """The citizen signs in at the provider and consents: a code bound to the PKCE challenge."""
        q = {k: v[0] for k, v in parse_qs(urlparse(url).query).items()}
        assert q["response_type"] == "code" and q["code_challenge_method"] == "S256" and len(q["code_challenge"]) == 43
        code = secrets.token_urlsafe(16)
        self.codes[code] = {"challenge": q["code_challenge"], "nonce": q["nonce"], "client_id": q["client_id"],
                            "redirect_uri": q["redirect_uri"], "sub": sub, "expires": time.time() + expires_in,
                            "scope": q["scope"]}
        return code, q["state"]


@pytest.fixture(scope="module")
def oidc():
    m = MockOIDC()
    yield m
    m.server.shutdown()


@pytest.fixture()
def dl(app, config, oidc, monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    oidc.sign_with_other_key = oidc.wrong_nonce = False
    config(DIGILOCKER_ENABLED=True, DIGILOCKER_CLIENT_ID="anvaya-test", DIGILOCKER_CLIENT_SECRET="dl-secret",
           DIGILOCKER_AUTH_URL=f"{oidc.base}/authorize", DIGILOCKER_TOKEN_URL=f"{oidc.base}/token",
           DIGILOCKER_JWKS_URL=f"{oidc.base}/jwks", DIGILOCKER_REDIRECT_URI="https://anvaya.test/auth/digilocker/callback",
           DIGILOCKER_SCOPES="openid profile aadhaar_number", DIGILOCKER_ISSUER=oidc.base)
    return oidc


def dl_start(client, h, sid):
    r = client.post("/api/v1/auth/digilocker/start", json={}, headers={**h, "X-Session-Id": sid})
    assert r.status_code == 200, r.json
    return r.json["authorization_url"]


def test_digilocker_is_off_and_hidden_by_default(client):
    assert client.get("/api/v1/auth/config").json["digilocker_enabled"] is False
    h = citizen_headers(anonymous=True)
    sid = personal_session(client, h)
    r = client.post("/api/v1/auth/digilocker/start", json={}, headers={**h, "X-Session-Id": sid})
    assert r.status_code == 404 and r.json["error"]["code"] == "DIGILOCKER_DISABLED"


def test_digilocker_full_flow_links_identity_and_stores_verified_facts(app, client, dl):
    uid = str(uuid.uuid4())
    h = citizen_headers(uid, anonymous=True)
    sid = personal_session(client, h)
    assert client.get("/api/v1/auth/config").json["digilocker_enabled"] is True
    url = dl_start(client, h, sid)
    assert url.startswith(f"{dl.base}/authorize?")
    q = parse_qs(urlparse(url).query)
    assert q["scope"] == ["openid profile"]  # the Aadhaar scope is never requested
    code, state = dl.authorize(url)
    r = client.post("/api/v1/auth/digilocker/callback", json={"code": code, "state": state}, headers=h)
    assert r.status_code == 200, r.json
    assert {f["attribute"] for f in r.json["facts"]} == {"applicant_name", "date_of_birth", "gender"}
    assert dl.token_requests[-1]["code_verifier"] and dl.token_requests[-1]["grant_type"] == "authorization_code"
    facts = {f["attribute"]: f for f in client.get(f"/api/v1/sessions/{sid}", headers=h).json["facts"]}
    for attr, value in (("date_of_birth", "1958-03-14"), ("gender", "female")):
        assert facts[attr]["value"] == value and facts[attr]["source"] == "digilocker"
        assert facts[attr]["confirmed"] and facts[attr]["verified"]
    link = rows(app, "SELECT * FROM linked_identities WHERE citizen_id=?", (f"CIT_{uid}",))[0]
    assert link["provider"] == "digilocker" and "dl-subject-1" not in link["subject_hash"]
    every = json.dumps([[dict(r) for r in rows(app, f"SELECT * FROM {t}")]
                        for t in ("facts", "auth_events", "audit_events", "linked_identities", "oidc_states")])
    assert "999911112222" not in every and "XXXX-XXXX-2222" not in every
    assert rows(app, "SELECT COUNT(*) FROM oidc_states WHERE auth_user_id=?", (uid,))[0][0] == 0  # single use


def test_digilocker_rejects_invalid_or_replayed_state(client, dl):
    h = citizen_headers(anonymous=True)
    sid = personal_session(client, h)
    code, state = dl.authorize(dl_start(client, h, sid))
    r = client.post("/api/v1/auth/digilocker/callback", json={"code": code, "state": "forged"}, headers=h)
    assert r.status_code == 400 and r.json["error"]["code"] == "INVALID_STATE"
    other = citizen_headers(anonymous=True)  # another user cannot use this state
    r = client.post("/api/v1/auth/digilocker/callback", json={"code": code, "state": state}, headers=other)
    assert r.json["error"]["code"] == "INVALID_STATE"
    r = client.post("/api/v1/auth/digilocker/callback", json={"code": code, "state": state}, headers=h)
    assert r.json["error"]["code"] == "INVALID_STATE"  # consumed by the attempt above: single use


def test_digilocker_rejects_an_expired_code(client, dl):
    h = citizen_headers(anonymous=True)
    sid = personal_session(client, h)
    code, state = dl.authorize(dl_start(client, h, sid), expires_in=-1)
    r = client.post("/api/v1/auth/digilocker/callback", json={"code": code, "state": state}, headers=h)
    assert r.status_code == 400 and r.json["error"]["code"] == "DIGILOCKER_CODE_REJECTED"


def test_digilocker_state_expires(app, client, dl):
    uid = str(uuid.uuid4())
    h = citizen_headers(uid, anonymous=True)
    code, state = dl.authorize(dl_start(client, h, personal_session(client, h)))
    write(app, "UPDATE oidc_states SET expires_at=? WHERE auth_user_id=?", (iso(now() - timedelta(seconds=1)), uid))
    r = client.post("/api/v1/auth/digilocker/callback", json={"code": code, "state": state}, headers=h)
    assert r.json["error"]["code"] == "STATE_EXPIRED"


def test_digilocker_pkce_verifier_must_match(app, client, dl):
    uid = str(uuid.uuid4())
    h = citizen_headers(uid, anonymous=True)
    code, state = dl.authorize(dl_start(client, h, personal_session(client, h)))
    write(app, "UPDATE oidc_states SET code_verifier=? WHERE auth_user_id=?", (secrets.token_urlsafe(64), uid))
    r = client.post("/api/v1/auth/digilocker/callback", json={"code": code, "state": state}, headers=h)
    assert r.json["error"]["code"] == "DIGILOCKER_CODE_REJECTED"


def test_digilocker_rejects_a_bad_signature_and_a_wrong_nonce(app, client, dl):
    uid = str(uuid.uuid4())
    h = citizen_headers(uid, anonymous=True)
    sid = personal_session(client, h)
    dl.sign_with_other_key = True
    code, state = dl.authorize(dl_start(client, h, sid))
    r = client.post("/api/v1/auth/digilocker/callback", json={"code": code, "state": state}, headers=h)
    assert r.status_code == 400 and r.json["error"]["code"] == "DIGILOCKER_BAD_TOKEN"
    dl.sign_with_other_key, dl.wrong_nonce = False, True
    code, state = dl.authorize(dl_start(client, h, sid))
    r = client.post("/api/v1/auth/digilocker/callback", json={"code": code, "state": state}, headers=h)
    assert r.json["error"]["code"] == "DIGILOCKER_BAD_TOKEN"
    assert not [f for f in client.get(f"/api/v1/sessions/{sid}", headers=h).json["facts"] if f["source"] == "digilocker"]
    reasons = [json.loads(r[0])["reason"] for r in rows(app, "SELECT details_json FROM auth_events WHERE"
                                                             " event='digilocker_failed' AND actor_id=?", (uid,))]
    assert reasons == ["bad_signature", "bad_nonce"]


def test_digilocker_only_from_your_own_personal_session(client, dl):
    h = citizen_headers(anonymous=True)
    sid = personal_session(client, citizen_headers(anonymous=True))
    r = client.post("/api/v1/auth/digilocker/start", json={}, headers={**h, "X-Session-Id": sid})
    assert r.status_code == 403


def test_digilocker_scopes_never_include_aadhaar():
    assert digilocker.scopes({"DIGILOCKER_SCOPES": "profile aadhaar uid openid Aadhar_Number"}) == "openid profile"
    v = secrets.token_urlsafe(64)
    assert digilocker.pkce_challenge(v) == base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b"=").decode()
