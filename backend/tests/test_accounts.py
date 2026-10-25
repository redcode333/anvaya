"""Supabase Auth token verification, citizen accounts, saved passports, Passport code + PIN, staff roles, kiosk endings
and retention. Tokens are minted with a test key whose public half is served by a mock JWKS (conftest)."""
import json
import logging
import time
import uuid
from datetime import timedelta
from urllib.parse import quote

import jwt
import pytest
from conftest import ISSUER, JWKS_FETCHES, OTHER_KEY, SIGNING_KEY, bearer, staff, start, token

from anvaya import accounts, auth
from anvaya.db import connect, iso, now

TC1 = ("I am 67 years old, a farmer in a village in Guntur, Andhra Pradesh. Family of 4, yearly income 60,000 rupees. "
       "We have a BPL card, I do not get any pension, I own 2 acres of land and have a bank account.")
INDIRAMMA = "R_AP_INDIRAMMA_OAP_RURAL"


@pytest.fixture()
def consent(app):
    return {"version": app.config["CONSENT_VERSION"], "accepted": True, "language": "en"}


@pytest.fixture()
def deleted_auth_users(monkeypatch):
    calls = []

    def fake(uid, cfg=None):
        calls.append(uid)
        return True
    monkeypatch.setattr(auth, "delete_auth_user", fake)
    return calls


def session_for(client, headers, utterance=TC1, confirm=True):
    r = client.post("/api/v1/sessions", json={"mode": "personal", "language": "en"}, headers=headers)
    assert r.status_code == 201, r.json
    sid = r.json["session_id"]
    assert client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": utterance}, headers=headers).status_code == 200
    if confirm:
        pending = client.post(f"/api/v1/sessions/{sid}/profile/confirm-all", headers=headers).json["needs_confirmation"]
        for fid in pending:
            client.patch(f"/api/v1/sessions/{sid}/profile/facts/{fid}", json={"confirmed": True}, headers=headers)
    return sid


def evaluate(client, sid, headers=None):
    r = client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate", headers=headers or {})
    assert r.status_code == 200, r.json
    return r.json


def age_fact(client, sid, headers=None):
    return next(f for f in client.get(f"/api/v1/sessions/{sid}", headers=headers or {}).json["facts"]
                if f["attribute"] == "age")


def rows(app, sql, params=()):
    db = connect(app.config)
    try:
        return db.execute(sql, params).fetchall()
    finally:
        db.close()


# ---------------------------------------------------------------- token verification

def test_valid_token_is_accepted(client):
    r = client.get("/api/v1/auth/me", headers=bearer(token("11111111-1111-4111-8111-111111111111", anonymous=True)))
    assert r.status_code == 200 and r.json["citizen"] == {
        "user_id": "11111111-1111-4111-8111-111111111111", "is_anonymous": True, "email": None}


@pytest.mark.parametrize("bad, code", [
    (lambda: token(expires_in=-120), "TOKEN_EXPIRED"),
    (lambda: token(iss="https://evil-project.supabase.co/auth/v1"), "INVALID_TOKEN"),
    (lambda: token(aud="anon"), "INVALID_TOKEN"),
    (lambda: token(key=OTHER_KEY), "INVALID_TOKEN"),                       # signed by a key not in the JWKS
    (lambda: token(kid="unknown-kid"), "INVALID_TOKEN"),
    (lambda: jwt.encode({"sub": "x", "iss": ISSUER, "aud": "authenticated", "exp": int(time.time()) + 60,
                         "iat": int(time.time())}, "shared-secret-of-32-bytes-or-more!!", algorithm="HS256",
                        headers={"kid": "test-key-1"}), "INVALID_TOKEN"),  # symmetric tokens are never trusted
    (lambda: "not-a-jwt", "INVALID_TOKEN"),
])
def test_bad_tokens_are_rejected_on_every_endpoint(client, bad, code):
    for method, path in (("get", "/api/v1/auth/me"), ("post", "/api/v1/sessions"), ("get", "/api/v1/schemes")):
        r = getattr(client, method)(path, headers=bearer(bad()), json={} if method == "post" else None)
        assert r.status_code == 401 and r.json["error"]["code"] == code, (path, r.json)


def test_token_missing_required_claims_is_rejected(client):
    t = int(time.time())
    tok = jwt.encode({"iss": ISSUER, "aud": "authenticated", "exp": t + 60, "iat": t}, SIGNING_KEY, algorithm="ES256",
                     headers={"kid": "test-key-1"})  # no sub
    assert client.get("/api/v1/auth/me", headers=bearer(tok)).json["error"]["code"] == "INVALID_TOKEN"


def test_jwks_is_cached_and_refetched_only_for_new_keys(client, monkeypatch):
    auth.reset_jwks_cache()
    JWKS_FETCHES.clear()
    for _ in range(5):
        assert client.get("/api/v1/auth/me", headers=bearer(token())).status_code == 200
    assert len(JWKS_FETCHES) == 1
    # An unknown key id refetches at most every 30 s (key rotation), never on every request.
    for _ in range(3):
        client.get("/api/v1/auth/me", headers=bearer(token(kid="rotated")))
    assert len(JWKS_FETCHES) == 1
    monkeypatch.setattr(auth._jwks, "fetched_at", auth._jwks.fetched_at - 31)
    client.get("/api/v1/auth/me", headers=bearer(token(kid="rotated")))
    assert len(JWKS_FETCHES) == 2


def test_secret_key_is_never_returned_or_logged(app, client, caplog):
    with caplog.at_level(logging.DEBUG):
        cfg = client.get("/api/v1/auth/config").json
        client.get("/api/v1/ready")
        client.get("/api/v1/auth/me", headers=bearer(token(expires_in=-100)))
    secret = app.config["SUPABASE_SECRET_KEY"]
    assert secret not in json.dumps(cfg) and secret not in caplog.text
    assert cfg["retention"]["passport_days"] == 365 and cfg["kiosk_idle_seconds"] == 180


# ---------------------------------------------------------------- staff roles

def test_roles_come_only_from_app_metadata_and_are_enforced(client):
    citizen = bearer(token())
    # user_metadata is writable by the user, so a role there means nothing; anonymous users never get a role
    assert client.get("/api/v1/reviewer/cases", headers=citizen).status_code == 401
    assert client.get("/api/v1/reviewer/cases", headers=bearer(token(role="reviewer", anonymous=True))).status_code == 401
    assert client.get("/api/v1/reviewer/cases", headers=staff("operator")).status_code == 403
    assert client.get("/api/v1/reviewer/cases", headers=staff("reviewer")).status_code == 200
    assert client.post("/api/v1/admin/rules/R_PMJJBY/verify", json={"checked_source_url": "x"},
                       headers=staff("reviewer")).status_code == 403
    kiosk = {"mode": "kiosk", "language": "en"}
    assert client.post("/api/v1/sessions", json=kiosk, headers=staff("reviewer")).status_code == 401
    assert client.post("/api/v1/sessions", json=kiosk, headers=citizen).status_code == 401
    assert client.post("/api/v1/sessions", json=kiosk, headers=staff("operator")).status_code == 201
    me = client.get("/api/v1/auth/me", headers=staff("admin")).json["user"]
    assert me["role"] == "admin" and me["username"] == "admin@anvaya.test"


def test_seed_staff_sets_roles_in_app_metadata(app, monkeypatch, capsys):
    from anvaya import manage
    calls = []
    monkeypatch.setattr(auth, "list_users", lambda cfg: [{"id": "u-rev", "email": "Rev@x.org", "app_metadata": {}}])

    class Resp:
        status_code = 200

        def raise_for_status(self):
            pass

    def fake_admin(method, path, cfg=None, **kw):
        calls.append((method, path, json.loads(kw.get("data") or "{}")))
        return Resp()
    monkeypatch.setattr(auth, "_admin", fake_admin)
    env = {"ANVAYA_ADMIN_EMAIL": "admin@x.org", "ANVAYA_ADMIN_PASSWORD": "a-long-password",
           "ANVAYA_REVIEWER_EMAIL": "rev@x.org", "ANVAYA_REVIEWER_PASSWORD": "another-password"}
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("ANVAYA_OPERATOR_EMAIL", raising=False)
    monkeypatch.setattr(manage, "create_app", lambda: app)
    monkeypatch.setattr(manage, "dispose", lambda cfg: None)
    assert manage.main(["seed-staff"]) == 1  # operator not configured
    out = capsys.readouterr().out
    assert "admin     created" in out and "reviewer  updated" in out and "operator  skipped" in out
    assert "a-long-password" not in out and "admin@x.org" not in out
    assert ("POST", "/users", {"email": "admin@x.org", "password": "a-long-password", "email_confirm": True,
                               "app_metadata": {"role": "admin"}}) in calls
    assert ("PUT", "/users/u-rev", {"password": "another-password", "app_metadata": {"role": "reviewer"}}) in calls


# ---------------------------------------------------------------- citizen accounts

def test_session_belongs_to_its_account(client):
    owner = bearer(token())
    sid = session_for(client, owner, confirm=False)
    assert client.get(f"/api/v1/sessions/{sid}", headers=owner).status_code == 200
    for other in ({}, bearer(token()), staff("reviewer")):
        r = client.get(f"/api/v1/sessions/{sid}", headers=other)
        assert r.status_code == 403 and r.json["error"]["code"] == "SESSION_FORBIDDEN"


def test_anonymous_to_linked_account_keeps_data(app, client, consent):
    uid = str(uuid.uuid4())
    anon = bearer(token(uid, anonymous=True))
    sid = session_for(client, anon)
    evaluate(client, sid, anon)
    # Saving needs a linked identity first
    r = client.post("/api/v1/account/consent", json={"consent": consent}, headers=anon)
    assert r.status_code == 409 and r.json["error"]["code"] == "LINK_REQUIRED"
    # The email OTP links the identity: Supabase keeps the same user id and issues tokens with is_anonymous=false.
    linked = bearer(token(uid, email="asha@example.org"))
    assert client.get(f"/api/v1/sessions/{sid}", headers=linked).status_code == 200
    assert client.post("/api/v1/account/consent", json={"consent": consent}, headers=linked).json["saved"] is True
    acct = client.get("/api/v1/account", headers=linked).json
    assert acct["saved"] and not acct["is_anonymous"] and acct["passport_count"] == 1
    assert {f["attribute"] for f in acct["profile"]} >= {"age", "state", "annual_income"}
    row = rows(app, "SELECT consent_json FROM citizens WHERE citizen_id=?", (accounts.citizen_id_for(uid),))[0]
    stored = json.loads(row[0])
    assert stored["version"] == consent["version"] and stored["consented_at"]
    # A new session of the saved citizen starts from the saved profile
    r = client.post("/api/v1/sessions", json={"mode": "personal", "language": "en"}, headers=linked)
    assert r.json["account"]["saved"] and len(r.json["account"]["restored"]) >= 8
    assert evaluate(client, r.json["session_id"], linked)["results"]


def test_consent_is_required_before_anything_is_kept(app, client):
    anon = bearer(token(anonymous=True))
    sid = session_for(client, anon)
    evaluate(client, sid, anon)
    r = client.get("/api/v1/account/passports", headers=anon)
    assert r.status_code == 403 and r.json["error"]["code"] == "CONSENT_REQUIRED"
    linked = bearer(token(email="x@example.org"))
    bad = client.post("/api/v1/account/consent", json={"consent": {"version": "old", "accepted": True}}, headers=linked)
    assert bad.status_code == 422 and bad.json["error"]["code"] == "CONSENT_REQUIRED"
    # Ending an unsaved session deletes everything, passport versions included
    client.post(f"/api/v1/sessions/{sid}/end", json={}, headers=anon)
    assert rows(app, "SELECT COUNT(*) FROM passport_versions WHERE session_id=?", (sid,))[0][0] == 0
    assert rows(app, "SELECT COUNT(*) FROM facts WHERE session_id=?", (sid,))[0][0] == 0


def test_kiosk_and_staff_cannot_save_to_an_account(client, consent):
    r = client.post("/api/v1/account/consent", json={"consent": consent}, headers=staff("operator"))
    assert r.status_code == 401 and r.json["error"]["code"] == "ACCOUNT_REQUIRED"
    kiosk = client.post("/api/v1/sessions", json={"mode": "kiosk", "language": "en"}, headers=staff("operator")).json
    assert kiosk["account"] is None


def test_passport_history_and_what_changed(client, consent):
    user = bearer(token(email="r@example.org"))
    client.post("/api/v1/account/consent", json={"consent": consent}, headers=user)
    sid = session_for(client, user)
    evaluate(client, sid, user)
    first = client.get("/api/v1/account/passports", headers=user).json["versions"][0]
    assert first["rule_versions"][INDIRAMMA] >= 1 and first["fact_ids"]
    assert any(o["rule_id"] == INDIRAMMA and o["outcome"] == "PROVISIONAL" for o in first["outcomes"])
    age = age_fact(client, sid, user)
    client.patch(f"/api/v1/sessions/{sid}/profile/facts/{age['fact_id']}", json={"value": 52}, headers=user)
    evaluate(client, sid, user)
    hist = client.get("/api/v1/account/passports", headers=user).json["versions"]
    assert len(hist) == 2 and hist[0]["created_at"] > hist[1]["created_at"]
    ch = client.get(f"/api/v1/account/passports/changes?since={quote(first['created_at'])}", headers=user).json
    c = next(x for x in ch["changes"] if x["rule_id"] == INDIRAMMA)
    assert (c["before"], c["after"]) == ("PROVISIONAL", "MISMATCH")
    assert {"kind": "fact_changed", "attribute": "age", "before": 67, "after": 52} == \
        {k: v for k, v in c["reasons"][0].items() if k in ("kind", "attribute", "before", "after")}


def test_what_changed_names_a_rule_version_change(app, client, consent):
    user = bearer(token(email="v@example.org"))
    client.post("/api/v1/account/consent", json={"consent": consent}, headers=user)
    sid = session_for(client, user)
    evaluate(client, sid, user)
    cid = accounts.citizen_id_for(jwt.decode(user["Authorization"][7:], options={"verify_signature": False})["sub"])
    # A newer rule version produced a different outcome (simulated in the stored passport)
    db = connect(app.config)
    try:
        v = db.execute("SELECT * FROM passport_versions WHERE citizen_id=?", (cid,)).fetchone()
        outs = json.loads(v["outcomes_json"])
        for o in outs:
            if o["rule_id"] == INDIRAMMA:
                o["rule_version"], o["outcome"] = o["rule_version"] + 1, "MISMATCH"
        db.execute("INSERT INTO passport_versions(version_id, citizen_id, session_id, eval_id, bundle_version,"
                   " created_at, facts_json, outcomes_json) VALUES (?,?,?,?,?,?,?,?)",
                   ("PSV_rule", cid, sid, "EVAL_x", "rules-next", now().isoformat(timespec="microseconds"),
                    v["facts_json"], json.dumps(outs)))
        db.commit()
    finally:
        db.close()
    ch = client.get(f"/api/v1/account/passports/changes?since={quote(v['created_at'])}", headers=user).json
    c = next(x for x in ch["changes"] if x["rule_id"] == INDIRAMMA)
    assert c["reasons"] == [{"kind": "rule_changed", "rule_id": INDIRAMMA, "before": c["reasons"][0]["before"],
                             "after": c["reasons"][0]["before"] + 1}]


def test_saved_age_older_than_90_days_must_be_reconfirmed(app, client, consent):
    user = bearer(token(email="old@example.org"))
    client.post("/api/v1/account/consent", json={"consent": consent}, headers=user)
    sid = session_for(client, user)
    db = connect(app.config)
    try:
        db.execute("UPDATE facts SET confirmed_at=? WHERE session_id=? AND attribute IN ('age', 'annual_income')",
                   (iso(now() - timedelta(days=91)), sid))
        db.commit()
    finally:
        db.close()
    assert {f["attribute"] for f in client.get("/api/v1/account", headers=user).json["profile"]
            if f["needs_reconfirmation"]} == {"age", "annual_income"}
    new = client.post("/api/v1/sessions", json={"mode": "personal", "language": "en"}, headers=user).json
    assert len(new["account"]["reconfirm"]) == 2 and new["workflow_state"] == "PROFILE_NEEDS_CONFIRMATION"
    r = client.post(f"/api/v1/sessions/{new['session_id']}/eligibility/evaluate", headers=user)
    assert r.status_code == 409 and {f["attribute"] for f in r.json["error"]["details"]["facts"]} == {"age", "annual_income"}


def test_delete_account_removes_data_and_auth_user_but_keeps_consented_cases(app, client, consent, deleted_auth_users):
    uid = str(uuid.uuid4())
    user = bearer(token(uid, email="d@example.org"))
    client.post("/api/v1/account/consent", json={"consent": consent}, headers=user)
    kept_sid = session_for(client, user)
    ev = evaluate(client, kept_sid, user)
    scheme = next(r["scheme_id"] for r in ev["results"] if r["outcome"] != "MISMATCH")
    draft = client.post(f"/api/v1/sessions/{kept_sid}/drafts", json={"scheme_id": scheme},
                        headers={**user, "Idempotency-Key": uuid.uuid4().hex}).json
    case = client.post(f"/api/v1/drafts/{draft['draft_id']}/handoff", json={"consent": {"share_with_reviewer": True}},
                       headers={**user, "Idempotency-Key": uuid.uuid4().hex, "X-Session-Id": kept_sid}).json
    gone_sid = session_for(client, user)
    evaluate(client, gone_sid, user)
    r = client.delete("/api/v1/account", headers=user)
    assert r.status_code == 200 and r.json["sessions_deleted"] == 1 and r.json["cases_kept"] == 1
    assert r.json["passport_versions"] == 2 and deleted_auth_users == [uid]
    cid = accounts.citizen_id_for(uid)
    assert rows(app, "SELECT COUNT(*) FROM citizens WHERE citizen_id=?", (cid,))[0][0] == 0
    assert rows(app, "SELECT COUNT(*) FROM passport_versions WHERE citizen_id=?", (cid,))[0][0] == 0
    assert rows(app, "SELECT COUNT(*) FROM facts WHERE session_id=?", (gone_sid,))[0][0] == 0
    assert rows(app, "SELECT COUNT(*) FROM sessions WHERE citizen_id=?", (cid,))[0][0] == 0
    # The consented hand-off case stays with the reviewer
    assert client.get(f"/api/v1/reviewer/cases/{case['case_id']}", headers=staff("reviewer")).status_code == 200
    ev_row = rows(app, "SELECT details_json FROM audit_events WHERE action='account.deleted' AND actor_id=?", (cid,))
    details = json.loads(ev_row[0][0])
    assert details == {"sessions_deleted": 1, "cases_kept": 1, "passport_versions": 2, "auth_user_deleted": True}


def test_delete_account_deletes_nothing_when_auth_delete_fails(app, client, consent, monkeypatch):
    monkeypatch.setattr(auth, "delete_auth_user", lambda uid, cfg=None: False)
    uid = str(uuid.uuid4())
    user = bearer(token(uid, email="f@example.org"))
    client.post("/api/v1/account/consent", json={"consent": consent}, headers=user)
    r = client.delete("/api/v1/account", headers=user)
    assert r.status_code == 502 and r.json["error"]["code"] == "ACCOUNT_DELETE_FAILED"
    assert rows(app, "SELECT saved FROM citizens WHERE citizen_id=?", (accounts.citizen_id_for(uid),))[0][0] == 1


# ---------------------------------------------------------------- Passport code + PIN

def test_pin_rules():
    for weak in ("1111", "1234", "4321", "1212", "1122", "1990", "2025", "2580"):
        assert accounts.pin_problem(weak), weak
    for bad in ("123", "12345", "abcd", 1234, None):
        assert accounts.pin_problem(bad) == "PIN must be exactly 4 digits."
    assert accounts.pin_problem("4826") is None and accounts.pin_problem("7391") is None


def test_code_format_entropy_and_normalisation():
    codes = {accounts.new_passport_code() for _ in range(200)}
    assert len(codes) == 200 and all(len(c) == 13 and c.startswith("PSP-") for c in codes)
    assert len(accounts.CODE_ALPHABET) == 32 and set("ILOU").isdisjoint(accounts.CODE_ALPHABET)
    assert accounts.normalize_code("psp 0ab1 - 2cd3") == accounts.normalize_code("PSP-OAB1-2CD3") == "PSP-0AB1-2CD3"
    assert accounts.normalize_code("PSP-ABC") == ""


def test_code_and_pin_save_and_resume(app, client, consent):
    sid = start(client, TC1)
    evaluate(client, sid)
    assert client.post(f"/api/v1/sessions/{sid}/passport-code", json={"pin": "1234", "consent": consent}).json[
        "error"]["code"] == "WEAK_PIN"
    assert client.post(f"/api/v1/sessions/{sid}/passport-code", json={"pin": "4826"}).json[
        "error"]["code"] == "CONSENT_REQUIRED"
    r = client.post(f"/api/v1/sessions/{sid}/passport-code", json={"pin": "4826", "consent": consent})
    assert r.status_code == 201 and r.json["spoken"].startswith("Your Passport code is")
    code = r.json["code"]
    stored = rows(app, "SELECT code_hash, pin_hash FROM citizens WHERE citizen_id=?", (r.json["citizen_id"],))[0]
    with app.app_context():
        assert stored[0] == accounts.code_hash(code) and len(stored[0]) == 64 and stored[1].startswith("$argon2")
    assert not rows(app, "SELECT 1 FROM citizens WHERE code_hash=? OR pin_hash=?", (code, "4826"))
    client.post(f"/api/v1/sessions/{sid}/end", json={})
    assert rows(app, "SELECT COUNT(*) FROM facts WHERE session_id=?", (sid,))[0][0] > 0  # saved: kept
    res = client.post("/api/v1/passport/resume", json={"code": code.lower().replace("-", " "), "pin": "4826"},
                      environ_base={"REMOTE_ADDR": "10.1.0.1"})
    assert res.status_code == 201 and res.json["restored"]["saved"] and res.json["last_passport_at"]
    new = res.json["session_id"]
    assert age_fact(client, new)["value"] == 67
    assert len(client.get(f"/api/v1/sessions/{new}/passports").json["versions"]) == 1


def _coded(client, consent, pin="4826"):
    sid = start(client, TC1)
    return client.post(f"/api/v1/sessions/{sid}/passport-code", json={"pin": pin, "consent": consent}).json["code"]


def test_wrong_code_and_wrong_pin_get_the_same_answer(client, consent):
    code = _coded(client, consent)
    ip = {"REMOTE_ADDR": "10.2.0.1"}
    a = client.post("/api/v1/passport/resume", json={"code": code, "pin": "4827"}, environ_base=ip)
    b = client.post("/api/v1/passport/resume", json={"code": accounts.new_passport_code(), "pin": "4826"},
                    environ_base={"REMOTE_ADDR": "10.2.0.2"})
    strip = lambda r: {k: v for k, v in r.json["error"].items() if k != "request_id"}  # noqa: E731
    assert a.status_code == b.status_code == 401 and strip(a) == strip(b)


def test_five_failures_per_code_and_per_ip_in_15_minutes(client, consent):
    code = _coded(client, consent)
    for i in range(5):
        r = client.post("/api/v1/passport/resume", json={"code": code, "pin": "0000"},
                        environ_base={"REMOTE_ADDR": f"10.3.0.{i}"})
        assert r.status_code == 401
    # per code: even the right PIN from a new address waits
    r = client.post("/api/v1/passport/resume", json={"code": code, "pin": "4826"}, environ_base={"REMOTE_ADDR": "10.3.1.1"})
    assert r.status_code == 429 and r.json["error"]["code"] == "TOO_MANY_ATTEMPTS"
    # per IP: five failures on different codes block that address
    ip = {"REMOTE_ADDR": "10.4.0.1"}
    for _ in range(5):
        assert client.post("/api/v1/passport/resume", json={"code": accounts.new_passport_code(), "pin": "0000"},
                           environ_base=ip).status_code == 401
    good = _coded(client, consent, pin="7391")
    assert client.post("/api/v1/passport/resume", json={"code": good, "pin": "7391"}, environ_base=ip).status_code == 429
    assert client.post("/api/v1/passport/resume", json={"code": good, "pin": "7391"},
                       environ_base={"REMOTE_ADDR": "10.4.0.2"}).status_code == 201


def test_code_locks_for_an_hour_after_ten_failures(app, client, consent):
    code = _coded(client, consent)
    with app.app_context():
        h = accounts.code_hash(code)
    for i in range(10):
        if i == 5:  # the 15-minute window has passed
            db = connect(app.config)
            db.execute("UPDATE passport_attempts SET ts=? WHERE code_hash=?", (iso(now() - timedelta(minutes=16)), h))
            db.commit()
            db.close()
        r = client.post("/api/v1/passport/resume", json={"code": code, "pin": "0000"},
                        environ_base={"REMOTE_ADDR": f"10.5.0.{i}"})
        assert r.status_code == 401, (i, r.json)
    db = connect(app.config)
    db.execute("DELETE FROM passport_attempts WHERE code_hash=?", (h,))  # even with a fresh window...
    db.commit()
    db.close()
    r = client.post("/api/v1/passport/resume", json={"code": code, "pin": "4826"}, environ_base={"REMOTE_ADDR": "10.5.1.1"})
    assert r.status_code == 429  # ...the code stays locked
    locked_until = rows(app, "SELECT locked_until FROM citizens WHERE code_hash=?", (h,))[0][0]
    assert timedelta(minutes=59) < (accounts.parse_iso(locked_until) - now()) <= timedelta(hours=1)


def test_code_holder_can_attach_the_passport_to_an_account(app, client, consent):
    sid = start(client, TC1)
    evaluate(client, sid)
    code = client.post(f"/api/v1/sessions/{sid}/passport-code", json={"pin": "4826", "consent": consent}).json["code"]
    anon = bearer(token(anonymous=True))
    assert client.post("/api/v1/account/attach-passport", json={"code": code, "pin": "4826"},
                       headers=anon).json["error"]["code"] == "LINK_REQUIRED"
    user = bearer(token(email="holder@example.org"))
    r = client.post("/api/v1/account/attach-passport", json={"code": code, "pin": "4826"}, headers=user,
                    environ_base={"REMOTE_ADDR": "10.6.0.1"})
    assert r.status_code == 200 and r.json["attached"]
    acct = client.get("/api/v1/account", headers=user).json
    assert acct["saved"] and acct["has_passport_code"] and acct["passport_count"] == 1
    # The code still opens the (now account-owned) passport
    assert client.post("/api/v1/passport/resume", json={"code": code, "pin": "4826"},
                       environ_base={"REMOTE_ADDR": "10.6.0.2"}).status_code == 201


# ---------------------------------------------------------------- kiosk

def test_kiosk_idle_end_deletes_unconsented_data_like_end_session(app, client, operator, consent):
    def kiosk_session():
        sid = client.post("/api/v1/sessions", json={"mode": "kiosk", "language": "en"}, headers=operator).json["session_id"]
        client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": TC1}, headers=operator)
        return sid
    idle = kiosk_session()
    assert client.post(f"/api/v1/sessions/{idle}/end", json={"reason": "idle"}, headers=operator).json["ended"]
    for table in ("facts", "turns"):
        assert rows(app, f"SELECT COUNT(*) FROM {table} WHERE session_id=?", (idle,))[0][0] == 0
    details = json.loads(rows(app, "SELECT details_json FROM audit_events WHERE session_id=? AND action='session.end'",
                              (idle,))[0][0])
    assert details == {"retained_case": False, "saved_passport": False, "reason": "idle"}
    saved = kiosk_session()  # saved with a Passport code: kept, but its utterances are not
    assert client.post(f"/api/v1/sessions/{saved}/passport-code", json={"pin": "4826", "consent": consent},
                       headers=operator).status_code == 201
    client.post(f"/api/v1/sessions/{saved}/end", json={"reason": "idle"}, headers=operator)
    assert rows(app, "SELECT COUNT(*) FROM facts WHERE session_id=?", (saved,))[0][0] > 0
    assert rows(app, "SELECT COUNT(*) FROM turns WHERE session_id=?", (saved,))[0][0] == 0


# ---------------------------------------------------------------- retention

def test_retention_purges_unsaved_after_24h_and_inactive_saved_passports(app, client, consent, deleted_auth_users):
    anon_uid, saved_uid, fresh_uid = (str(uuid.uuid4()) for _ in range(3))
    old_anon = session_for(client, bearer(token(anon_uid, anonymous=True)), confirm=False)
    fresh = session_for(client, bearer(token(fresh_uid, anonymous=True)), confirm=False)
    saved_user = bearer(token(saved_uid, email="s@example.org"))
    client.post("/api/v1/account/consent", json={"consent": consent}, headers=saved_user)
    saved_sid = session_for(client, saved_user)
    db = connect(app.config)
    try:
        db.execute("UPDATE sessions SET created_at=? WHERE session_id IN (?, ?)",
                   (iso(now() - timedelta(hours=25)), old_anon, saved_sid))
        db.execute("UPDATE citizens SET last_active_at=? WHERE citizen_id=?",
                   (iso(now() - timedelta(hours=25)), accounts.citizen_id_for(anon_uid)))
        with app.app_context():
            r = accounts.purge_expired(db, app.config)
        assert r["unsaved_sessions"] >= 1 and r["unsaved_citizens"] >= 1
        assert db.execute("SELECT COUNT(*) FROM sessions WHERE session_id=?", (old_anon,)).fetchone()[0] == 0
        assert db.execute("SELECT COUNT(*) FROM sessions WHERE session_id IN (?, ?)", (fresh, saved_sid)).fetchone()[0] == 2
        assert anon_uid in deleted_auth_users and saved_uid not in deleted_auth_users
        # A saved passport untouched for PASSPORT_RETENTION_DAYS goes too, Auth user included
        db.execute("UPDATE citizens SET last_active_at=? WHERE citizen_id=?",
                   (iso(now() - timedelta(days=366)), accounts.citizen_id_for(saved_uid)))
        db.commit()
        with app.app_context():
            r = accounts.purge_expired(db, app.config)
        assert r["inactive_passports"] == 1 and saved_uid in deleted_auth_users
        assert db.execute("SELECT COUNT(*) FROM facts WHERE session_id=?", (saved_sid,)).fetchone()[0] == 0
    finally:
        db.close()


# ---------------------------------------------------------------- query budget

def test_account_sessions_stay_within_the_query_budget(app, client, caplog, monkeypatch):
    from test_db import _counts

    from anvaya.db import backend
    monkeypatch.setattr(backend(app.config), "cache_check_s", 3600)
    client.get("/api/v1/sync/bundle")
    user = bearer(token(anonymous=True))
    r, q, rt = _counts(caplog, lambda: client.post("/api/v1/sessions", json={"mode": "personal", "language": "en"},
                                                   headers=user))
    assert r.status_code == 201 and q <= 6 and rt <= 2, (q, rt)  # + citizen upsert and the saved-profile read
    sid = r.json["session_id"]
    client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": TC1}, headers=user)
    for fid in client.post(f"/api/v1/sessions/{sid}/profile/confirm-all", headers=user).json["needs_confirmation"]:
        client.patch(f"/api/v1/sessions/{sid}/profile/facts/{fid}", json={"confirmed": True}, headers=user)
    r, q, rt = _counts(caplog, lambda: client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate", headers=user))
    assert r.status_code == 200 and q <= 9 and rt <= 2, (q, rt)  # passport version joins the evaluation's writes


def test_tc5_returning_citizen_passes(client, admin):
    r = client.post("/api/v1/test-runs/TC5", headers=admin)
    assert r.status_code == 200 and r.json["passed"], [c for c in r.json["checks"] if not c["passed"]]
