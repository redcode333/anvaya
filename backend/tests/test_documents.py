"""Document uploads through the backend into private Storage (mocked here; tests/test_storage_live.py uses the real
bucket): ownership, consent, link expiry, type / size checks, reviewer access, audit, and deletion."""
import json
import uuid
from datetime import timedelta

import pytest
from conftest import bearer, staff, start, token

from anvaya import accounts, auth, documents, storage
from anvaya.common import ApiError
from anvaya.db import connect, iso, now

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 60
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 60
PDF = b"%PDF-1.7\n" + b"\x00" * 60
PUNJAB = "I am 70 years old and live in Punjab. We have a BPL card. I do not get any pension."
PUNJAB_IGNOAPS = "680a02cb41f9fb65ecb3453f"


class FakeStorage:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.fail = False
        self.corrupt = False

    def upload(self, path, data, content_type, cfg=None):
        if self.fail:
            raise ApiError("STORAGE_UNAVAILABLE", "down", 502)
        assert path not in self.objects  # never overwrites
        self.objects[path] = data + (b"x" if self.corrupt else b"")

    def probe(self, path, cfg=None):
        data = self.objects.get(path)
        return None if data is None else (len(data), data[:8])

    def download(self, path, cfg=None):
        if path not in self.objects:
            raise ApiError("DOCUMENT_NOT_FOUND", "gone", 404)
        return self.objects[path]

    def delete(self, paths, cfg=None):
        if self.fail and paths:
            raise ApiError("STORAGE_UNAVAILABLE", "down", 502)
        for p in paths:
            self.objects.pop(p, None)


@pytest.fixture()
def store(monkeypatch):
    fake = FakeStorage()
    for name in ("upload", "probe", "download", "delete"):
        monkeypatch.setattr(storage, name, getattr(fake, name))
    return fake


@pytest.fixture()
def clock(monkeypatch):
    t = {"now": 1_800_000_000.0}
    monkeypatch.setattr(documents, "clock", lambda: t["now"])
    return t


def consent(app):
    return {"version": app.config["UPLOAD_CONSENT_VERSION"], "accepted": True}


def url_for(client, app, sid, doc="bpl_card", ctype="image/png", size=len(PNG), headers=None):
    return client.post(f"/api/v1/sessions/{sid}/documents/{doc}/upload-url", headers=headers or {},
                       json={"content_type": ctype, "size": size, "consent": consent(app)})


def upload(client, app, sid, data=PNG, ctype="image/png", doc="bpl_card", headers=None):
    r = url_for(client, app, sid, doc, ctype, len(data), headers)
    assert r.status_code == 201, r.json
    return client.put(r.json["upload_url"], data=data, headers={"Content-Type": ctype}), r.json


def rows(app, sql, params=()):
    db = connect(app.config)
    try:
        return db.execute(sql, params).fetchall()
    finally:
        db.close()


def handed_off(client, sid, headers=None):
    h = headers or {}
    ev = client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate", headers=h).json
    scheme = next(r["scheme_id"] for r in ev["results"] if r["outcome"] != "MISMATCH")
    d = client.post(f"/api/v1/sessions/{sid}/drafts", json={"scheme_id": scheme},
                    headers={**h, "Idempotency-Key": uuid.uuid4().hex}).json
    return client.post(f"/api/v1/drafts/{d['draft_id']}/handoff", json={"consent": {"share_with_reviewer": True}},
                       headers={**h, "Idempotency-Key": uuid.uuid4().hex, "X-Session-Id": sid}).json["case_id"]


# ---------------------------------------------------------------- upload

def test_upload_marks_document_uploaded_and_outcome_stays_provisional(app, client, store):
    sid = start(client, PUNJAB)
    r, issued = upload(client, app, sid)
    assert r.status_code == 200 and r.json == {"upload_id": issued["upload_id"], "doc_key": "bpl_card",
                                               "status": "uploaded", "verified": False, "size_bytes": len(PNG),
                                               "content_type": "image/png"}
    path = rows(app, "SELECT storage_path FROM document_uploads WHERE upload_id=?", (issued["upload_id"],))[0][0]
    assert path.startswith(f"{sid}/{sid}/bpl_card/") and store.objects[path] == PNG
    ev = client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate").json
    guide = client.get(f"/api/v1/sessions/{sid}/documents").json
    bpl = next(d for d in guide["documents"] if d["doc_key"] == "bpl_card")
    assert bpl["status"] == "uploaded" and bpl["status_label"] == "Uploaded — not verified yet"
    assert bpl["upload"]["status"] == "uploaded" and guide["upload"]["allowed"] is True
    pj = next(x for x in ev["results"] if x["scheme_id"] == PUNJAB_IGNOAPS)
    assert pj["outcome"] == "PROVISIONAL" and "bpl_card" not in pj["document_gaps"]  # the citizen has it ...
    assert any(d["code"] == "EVIDENCE_NOT_VERIFIED" and "bpl_card" in d["docs"] for d in pj["decision_reason"])  # unverified
    # Citizens can never set these states themselves
    for st in ("uploaded", "verified", "reupload_requested"):
        assert client.put(f"/api/v1/sessions/{sid}/documents/bpl_card", json={"status": st}).status_code == 422


def test_upload_url_lives_five_minutes_and_works_once(app, client, store, clock):
    sid = start(client, PUNJAB)
    r = url_for(client, app, sid)
    url = r.json["upload_url"]
    assert url.startswith("/api/v1/uploads/") and r.json["expires_at"]
    clock["now"] += 301
    late = client.put(url, data=PNG)
    assert late.status_code == 410 and late.json["error"]["code"] == "LINK_EXPIRED"
    url = url_for(client, app, sid).json["upload_url"]
    assert client.put(url, data=PNG).status_code == 200
    assert client.put(url, data=PNG).json["error"]["code"] == "LINK_USED"
    assert client.put(url[:-3] + "abc", data=PNG).json["error"]["code"] == "INVALID_LINK"


@pytest.mark.parametrize("ctype, size, code, status", [
    ("image/gif", 10, "UNSUPPORTED_TYPE", 415),
    ("application/msword", 10, "UNSUPPORTED_TYPE", 415),
    ("image/png", 5 * 1024 * 1024 + 1, "FILE_TOO_LARGE", 413),
    ("image/png", 0, "INVALID_SIZE", 422),
])
def test_upload_url_refuses_bad_type_or_size(app, client, store, ctype, size, code, status):
    sid = start(client, PUNJAB)
    r = url_for(client, app, sid, ctype=ctype, size=size)
    assert r.status_code == status and r.json["error"]["code"] == code


def test_body_is_checked_by_magic_bytes_and_size(app, client, store):
    sid = start(client, PUNJAB)
    for data, declared, code, status in ((PDF, "image/png", "INVALID_FILE_TYPE", 415),
                                         (b"GIF89a" + b"\x00" * 20, "image/png", "INVALID_FILE_TYPE", 415),
                                         (b"<html>evil</html>", "application/pdf", "INVALID_FILE_TYPE", 415),
                                         (b"", "image/png", "EMPTY_FILE", 422),
                                         (PNG + b"\x00" * (5 * 1024 * 1024), "image/png", "FILE_TOO_LARGE", 413)):
        r = url_for(client, app, sid, ctype=declared, size=10)
        put = client.put(r.json["upload_url"], data=data)
        assert put.status_code == status and put.json["error"]["code"] == code
        assert rows(app, "SELECT status FROM document_uploads WHERE upload_id=?", (r.json["upload_id"],))[0][0] == "rejected"
    assert store.objects == {}  # nothing invalid was ever stored
    for data, ctype in ((JPEG, "image/jpeg"), (PDF, "application/pdf")):
        assert upload(client, app, sid, data, ctype, doc="age_proof")[0].status_code == 200
    assert len(store.objects) == 1  # the second upload of a document replaces the first


def test_stored_object_is_rechecked_and_deleted_when_it_differs(app, client, store):
    sid = start(client, PUNJAB)
    store.corrupt = True
    r, issued = upload(client, app, sid)
    assert r.status_code == 422 and r.json["error"]["code"] == "STORED_FILE_INVALID"
    assert store.objects == {}
    assert rows(app, "SELECT status FROM document_uploads WHERE upload_id=?", (issued["upload_id"],))[0][0] == "rejected"


def test_consent_and_ownership_are_required(app, client, store):
    owner = bearer(token(anonymous=True))
    sid = client.post("/api/v1/sessions", json={"mode": "personal", "language": "en"}, headers=owner).json["session_id"]
    no = client.post(f"/api/v1/sessions/{sid}/documents/bpl_card/upload-url", headers=owner,
                     json={"content_type": "image/png", "size": 10})
    assert no.status_code == 422 and no.json["error"]["code"] == "CONSENT_REQUIRED"
    for other in ({}, bearer(token()), staff("operator")):
        r = url_for(client, app, sid, headers=other)
        assert r.status_code == 403 and r.json["error"]["code"] == "SESSION_FORBIDDEN"
    assert upload(client, app, sid, headers=owner)[0].status_code == 200
    assert client.get(f"/api/v1/sessions/{sid}/documents/bpl_card/view-url", headers=bearer(token())).status_code == 403
    assert client.get(f"/api/v1/sessions/{sid}/documents/bpl_card/view-url", headers=owner).status_code == 200


def test_kiosk_uploads_only_into_a_consented_case(app, client, store, operator):
    sid = client.post("/api/v1/sessions", json={"mode": "kiosk", "language": "en"}, headers=operator).json["session_id"]
    client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": PUNJAB}, headers=operator)
    for fid in client.post(f"/api/v1/sessions/{sid}/profile/confirm-all", headers=operator).json["needs_confirmation"]:
        client.patch(f"/api/v1/sessions/{sid}/profile/facts/{fid}", json={"confirmed": True}, headers=operator)
    r = url_for(client, app, sid, headers=operator)
    assert r.status_code == 409 and r.json["error"]["code"] == "CASE_REQUIRED"
    client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate", headers=operator)
    assert client.get(f"/api/v1/sessions/{sid}/documents", headers=operator).json["upload"] | {"consent_version": None,
                                                                                               "max_bytes": 0, "types": []}         == {"allowed": False, "reason": "CASE_REQUIRED", "consent_version": None, "max_bytes": 0, "types": []}
    case_id = handed_off(client, sid, operator)
    r, issued = upload(client, app, sid, headers=operator)
    assert r.status_code == 200
    path = rows(app, "SELECT storage_path FROM document_uploads WHERE upload_id=?", (issued["upload_id"],))[0][0]
    assert path.split("/")[1] == case_id  # filed under the case
    # Ending the kiosk session keeps the case's upload (it is with the reviewer), nothing else
    client.post(f"/api/v1/sessions/{sid}/end", json={"reason": "idle"}, headers=operator)
    assert path in store.objects


# ---------------------------------------------------------------- viewing and review

def test_view_links_audit_and_reviewer_access(app, client, store, clock, reviewer):
    sid = start(client, PUNJAB)
    _, issued = upload(client, app, sid)
    # No consented case yet: a reviewer cannot open it
    r = client.get(f"/api/v1/sessions/{sid}/documents/bpl_card/view-url", headers=reviewer)
    assert r.status_code == 403
    case_id = handed_off(client, sid)
    v = client.get(f"/api/v1/sessions/{sid}/documents/bpl_card/view-url", headers=reviewer)
    assert v.status_code == 200 and v.json["view_url"].startswith("/api/v1/uploads/view/")
    got = client.get(v.json["view_url"])
    assert got.status_code == 200 and got.data == PNG and got.mimetype == "image/png"
    assert "no-store" in got.headers["Cache-Control"] and got.headers["X-Content-Type-Options"] == "nosniff"
    clock["now"] += 121
    assert client.get(v.json["view_url"]).json["error"]["code"] == "LINK_EXPIRED"
    # The owner may view too
    own = client.get(f"/api/v1/sessions/{sid}/documents/bpl_card/view-url").json["view_url"]
    assert client.get(own).status_code == 200
    viewed = [json.loads(r[0]) | {"actor": r[1], "role": r[2]} for r in rows(
        app, "SELECT details_json, actor_id, actor_role FROM audit_events WHERE action='document.viewed' AND session_id=?",
        (sid,))]
    assert [(v["role"], v["doc_key"]) for v in viewed] == [("reviewer", "bpl_card"), ("citizen", "bpl_card")]
    assert all(set(v) == {"upload_id", "doc_key", "actor", "role"} for v in viewed)  # never content
    assert viewed[0]["actor"] == reviewer_id(reviewer)
    # The case view lists the upload; Verify makes the document verified
    case = client.get(f"/api/v1/reviewer/cases/{case_id}", headers=reviewer).json
    assert case["uploads"]["bpl_card"]["status"] == "uploaded" and case["documents"]["bpl_card"] == "uploaded"
    r = client.post(f"/api/v1/reviewer/cases/{case_id}/documents/bpl_card", json={"action": "verify"}, headers=reviewer)
    assert r.json["status"] == "verified"
    assert client.get(f"/api/v1/reviewer/cases/{case_id}", headers=reviewer).json["uploads"]["bpl_card"]["status"] == "verified"
    # Only reviewers decide
    assert client.post(f"/api/v1/reviewer/cases/{case_id}/documents/bpl_card", json={"action": "verify"},
                       headers=staff("operator")).status_code == 403


def reviewer_id(headers):
    import jwt
    return jwt.decode(headers["Authorization"][7:], options={"verify_signature": False})["sub"]


def test_request_reupload_deletes_the_file(app, client, store, reviewer):
    sid = start(client, PUNJAB)
    upload(client, app, sid)
    case_id = handed_off(client, sid)
    r = client.post(f"/api/v1/reviewer/cases/{case_id}/documents/bpl_card", json={"action": "request_reupload"},
                    headers=reviewer)
    assert r.json["status"] == "reupload_requested" and store.objects == {}
    guide = client.get(f"/api/v1/sessions/{sid}/documents").json
    assert next(d for d in guide["documents"] if d["doc_key"] == "bpl_card")["status"] == "reupload_requested"
    assert upload(client, app, sid)[0].status_code == 200  # the citizen can upload again into the open case


# ---------------------------------------------------------------- deletion

def test_end_of_unsaved_session_deletes_uploads(app, client, store):
    sid = start(client, PUNJAB)
    upload(client, app, sid)
    client.post(f"/api/v1/sessions/{sid}/end", json={})
    assert store.objects == {} and not rows(app, "SELECT 1 FROM document_uploads WHERE session_id=?", (sid,))


def test_account_deletion_deletes_uploads(app, client, store, monkeypatch):
    monkeypatch.setattr(auth, "delete_auth_user", lambda uid, cfg=None: True)
    user = bearer(token(email="u@example.org"))
    client.post("/api/v1/account/consent", json={"consent": {"version": app.config["CONSENT_VERSION"], "accepted": True}},
                headers=user)
    sid = client.post("/api/v1/sessions", json={"mode": "personal", "language": "en"}, headers=user).json["session_id"]
    client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": PUNJAB}, headers=user)
    upload(client, app, sid, headers=user)
    upload(client, app, sid, JPEG, "image/jpeg", doc="age_proof", headers=user)
    assert len(store.objects) == 2
    store.fail = True
    r = client.delete("/api/v1/account", headers=user)
    assert r.status_code == 502 and len(store.objects) == 2  # nothing deleted, account intact
    assert rows(app, "SELECT COUNT(*) FROM document_uploads WHERE session_id=?", (sid,))[0][0] == 2
    store.fail = False
    r = client.delete("/api/v1/account", headers=user)
    assert r.status_code == 200 and r.json["uploads_deleted"] == 2 and store.objects == {}
    assert not rows(app, "SELECT 1 FROM document_uploads WHERE session_id=?", (sid,))


def _age(app, sql, params):
    db = connect(app.config)
    db.execute(sql, params)
    db.commit()
    db.close()


def test_retention_deletes_anonymous_and_reviewed_uploads(app, client, store, reviewer):
    anon = bearer(token(anonymous=True))
    old = client.post("/api/v1/sessions", json={"mode": "personal", "language": "en"}, headers=anon).json["session_id"]
    upload(client, app, old, headers=anon)
    reviewed = start(client, PUNJAB)
    upload(client, app, reviewed, doc="age_proof")
    case_id = handed_off(client, reviewed)
    client.post(f"/api/v1/reviewer/cases/{case_id}/decision", json={"action": "record_review", "outcome": "appears_eligible"},
                headers=reviewer)
    keep = start(client, PUNJAB)
    upload(client, app, keep, doc="residence_proof")
    handed_off(client, keep)  # open case: kept
    assert len(store.objects) == 3
    _age(app, "UPDATE sessions SET created_at=? WHERE session_id=?", (iso(now() - timedelta(hours=25)), old))
    _age(app, "UPDATE cases SET updated_at=? WHERE case_id=?", (iso(now() - timedelta(days=31)), case_id))
    db = connect(app.config)
    try:
        with app.app_context():
            r = accounts.purge_expired(db, app.config)
    finally:
        db.close()
    assert r["uploads_deleted"] >= 2
    left = {p.split("/")[2] for p in store.objects}
    assert left == {"residence_proof"}
    assert not rows(app, "SELECT 1 FROM document_uploads WHERE session_id IN (?, ?)", (old, reviewed))


def test_retention_keeps_rows_when_storage_is_down(app, client, store):
    sid = start(client, PUNJAB)
    upload(client, app, sid)
    _age(app, "UPDATE sessions SET created_at=? WHERE session_id=?", (iso(now() - timedelta(hours=25)), sid))
    store.fail = True
    db = connect(app.config)
    try:
        with app.app_context(), pytest.raises(ApiError):
            accounts.purge_expired(db, app.config)
    finally:
        db.close()
    assert rows(app, "SELECT COUNT(*) FROM document_uploads WHERE session_id=?", (sid,))[0][0] == 1  # retried next run


def test_documents_module_never_touches_llm_or_ocr():
    import inspect
    src = inspect.getsource(documents)
    assert "llm" not in src.split('"""', 2)[2] and "ocr" not in src.lower().split('"""', 2)[2]
