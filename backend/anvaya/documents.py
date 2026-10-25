"""Document uploads (JPEG, PNG or PDF, at most 5 MB) into the private Storage bucket, mediated by this backend.

1. POST .../documents/<doc_key>/upload-url: the backend checks session ownership and the citizen's upload consent (a
   kiosk also needs a consented hand-off case) and returns its own signed, single-use upload URL, valid 5 minutes.
2. PUT /api/v1/uploads/<token>: the file comes to the backend, which checks size and type by its magic bytes (not by
   the declared type alone), stores it, reads the stored object back (size + magic bytes) and deletes it if anything
   differs. The document state becomes "uploaded": declared by the citizen, not verified, so outcomes stay
   PROVISIONAL until a reviewer marks it "verified".
3. GET .../documents/<doc_key>/view-url: for the session's owner or a reviewer when the session has a consented case;
   the link is valid 2 minutes and every view is audited (who, when, which document; never the content).

Uploads are never read for content: no OCR, no ID-number extraction, never sent to an LLM. They are deleted with the
account, with unsaved sessions (24 h), REVIEWED_UPLOAD_RETENTION_DAYS after the case is reviewed, and right away when
a reviewer asks for a re-upload.
"""
import hashlib
import hmac
import json
import time
import uuid

from flask import Response, current_app, g
from itsdangerous import BadSignature, URLSafeSerializer

from . import catalogue, i18n, metrics, profile, storage
from .common import ApiError, audit, current_user
from .db import get_db, iso, new_id, now

MAGIC = {"image/jpeg": b"\xff\xd8\xff", "image/png": b"\x89PNG\r\n\x1a\n", "application/pdf": b"%PDF-"}
UPLOAD_TTL_MAX_S, VIEW_TTL_MAX_S = 300, 120
LIVE = ("uploaded", "verified")

CASES_SQL = "SELECT case_id, consent_json, status FROM cases WHERE session_id=?"
LATEST_SQL = ("SELECT * FROM document_uploads WHERE session_id=? AND doc_key=? AND status IN ('uploaded', 'verified')"
              " ORDER BY uploaded_at DESC LIMIT 1")
SESSION_UPLOADS_SQL = ("SELECT doc_key, upload_id, status, content_type, size_bytes, uploaded_at FROM document_uploads"
                       " WHERE session_id=? AND status IN ('uploaded', 'verified')")


def clock() -> float:
    return time.time()  # tests move time forward to check expiry


def sniff(head: bytes) -> str | None:
    return next((t for t, m in MAGIC.items() if head.startswith(m)), None)


def _serializer(purpose: str) -> URLSafeSerializer:
    cfg = current_app.config
    root = (cfg["SUPABASE_SECRET_KEY"] or cfg["PASSPORT_PEPPER"] or "anvaya-dev-links").encode()
    return URLSafeSerializer(hmac.new(root, b"anvaya-document-links", hashlib.sha256).hexdigest(), salt=purpose)


def _sign(purpose: str, ttl: int, **claims) -> tuple[str, str]:
    exp = int(clock()) + ttl
    return _serializer(purpose).dumps({**claims, "exp": exp}), iso(now().fromtimestamp(exp, now().tzinfo))


def _verify(purpose: str, token: str) -> dict:
    try:
        claims = _serializer(purpose).loads(token)
    except BadSignature:
        raise ApiError("INVALID_LINK", "This link is not valid.", 403)
    if clock() > claims["exp"]:
        raise ApiError("LINK_EXPIRED", "This link has expired. Ask for a new one.", 410)
    return claims


def consented_case(rows) -> bool:
    return any(json.loads(r["consent_json"]).get("share_with_reviewer") is True for r in rows)


def upload_policy(session: dict, case_rows) -> dict:
    """Whether this session may upload now, and why not (shown before the upload button)."""
    if session["mode"] == "kiosk" and not consented_case(case_rows):
        return {"allowed": False, "reason": "CASE_REQUIRED"}
    if case_rows and all(r["status"] == "REVIEWED" for r in case_rows):
        return {"allowed": False, "reason": "CASE_CLOSED"}
    return {"allowed": True, "reason": None}


def policy_public(session: dict, case_rows) -> dict:
    cfg = current_app.config
    return {**upload_policy(session, case_rows), "consent_version": cfg["UPLOAD_CONSENT_VERSION"],
            "max_bytes": cfg["MAX_UPLOAD_BYTES"], "types": list(MAGIC)}


# ---------------------------------------------------------------- upload

def create_upload_url(session_id: str, doc_key: str, body: dict) -> dict:
    cfg = current_app.config
    if doc_key not in i18n.DOCUMENTS:
        raise ApiError("UNKNOWN_DOCUMENT", "Unknown document type.", 422)
    ctype, size = body.get("content_type"), body.get("size")
    if ctype not in MAGIC:
        raise ApiError("UNSUPPORTED_TYPE", "Upload a JPEG, PNG or PDF file.", 415)
    if not isinstance(size, int) or isinstance(size, bool) or size <= 0:
        raise ApiError("INVALID_SIZE", "Send the file size in bytes.", 422)
    if size > cfg["MAX_UPLOAD_BYTES"]:
        raise ApiError("FILE_TOO_LARGE", "Files must be 5 MB or smaller.", 413)
    consent = body.get("consent") or {}
    if consent.get("accepted") is not True or consent.get("version") != cfg["UPLOAD_CONSENT_VERSION"]:
        raise ApiError("CONSENT_REQUIRED", "Agree to the upload terms first.", 422,
                       {"consent_version": cfg["UPLOAD_CONSENT_VERSION"]})
    session, _, (cases,) = profile.load(session_id, extra=[(CASES_SQL, (session_id,))])  # ownership + not ended
    cases = cases.fetchall()
    policy = upload_policy(session, cases)
    if not policy["allowed"]:
        msg = {"CASE_REQUIRED": "At a kiosk, documents can be uploaded only into a case the citizen agreed to send to a reviewer.",
               "CASE_CLOSED": "This case has already been reviewed."}[policy["reason"]]
        raise ApiError(policy["reason"], msg, 409)
    case = next((r for r in cases if json.loads(r["consent_json"]).get("share_with_reviewer") is True), None)
    owner = session.get("auth_user_id") or session_id
    path = f"{owner}/{case['case_id'] if case else session_id}/{doc_key}/{uuid.uuid4().hex}"
    upload_id = new_id("UPL")
    ttl = min(int(cfg["UPLOAD_URL_TTL_S"]), UPLOAD_TTL_MAX_S)
    token, expires = _sign("upload", ttl, u=upload_id)
    db = get_db()
    db.execute("""INSERT INTO document_uploads(upload_id, session_id, citizen_id, case_id, doc_key, storage_path,
                  content_type, status, consent_json, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
               (upload_id, session_id, session.get("citizen_id"), case["case_id"] if case else None, doc_key, path,
                ctype, "pending", json.dumps({"version": consent["version"], "accepted": True, "consented_at": iso()}),
                iso(), expires))
    audit("document.upload_url_issued", session_id=session_id, details={"upload_id": upload_id, "doc_key": doc_key})
    db.commit()
    return {"upload_id": upload_id, "upload_url": f"/api/v1/uploads/{token}", "method": "PUT", "expires_at": expires,
            "max_bytes": cfg["MAX_UPLOAD_BYTES"], "content_type": ctype}


def receive_upload(token: str, stream) -> dict:
    claims = _verify("upload", token)
    cfg = current_app.config
    db = get_db()
    row, old = db.query_many([
        ("SELECT u.*, s.ended_at AS session_ended FROM document_uploads u JOIN sessions s ON s.session_id = u.session_id"
         " WHERE u.upload_id=?", (claims["u"],)),
        ("SELECT o.upload_id, o.storage_path FROM document_uploads o JOIN document_uploads u"
         " ON u.session_id = o.session_id AND u.doc_key = o.doc_key"
         " WHERE u.upload_id=? AND o.upload_id <> u.upload_id AND o.status IN ('uploaded', 'verified')", (claims["u"],))])
    row = row.fetchone()
    if not row:
        raise ApiError("UPLOAD_NOT_FOUND", "This upload no longer exists.", 404)
    if row["status"] != "pending":
        raise ApiError("LINK_USED", "This upload link was already used. Ask for a new one.", 409)
    data = stream.read(cfg["MAX_UPLOAD_BYTES"] + 1)

    def reject(code: str, message: str, status: int):
        db.execute("UPDATE document_uploads SET status='rejected' WHERE upload_id=?", (row["upload_id"],))
        metrics.UPLOADS.labels("rejected").inc()
        audit("document.upload_rejected", session_id=row["session_id"],
              details={"upload_id": row["upload_id"], "doc_key": row["doc_key"], "reason": code})
        db.commit()
        raise ApiError(code, message, status)

    if row["session_ended"] and not row["case_id"]:
        reject("SESSION_EXPIRED", "This session has ended.", 410)
    if len(data) > cfg["MAX_UPLOAD_BYTES"]:
        reject("FILE_TOO_LARGE", "Files must be 5 MB or smaller.", 413)
    if not data:
        reject("EMPTY_FILE", "The file is empty.", 422)
    kind = sniff(data[:8])
    if kind is None or kind != row["content_type"]:
        reject("INVALID_FILE_TYPE", "The file is not the JPEG, PNG or PDF it claims to be.", 415)
    storage.upload(row["storage_path"], data, kind)
    stored = storage.probe(row["storage_path"])
    if not stored or stored[0] != len(data) or stored[0] > cfg["MAX_UPLOAD_BYTES"] or sniff(stored[1]) != kind:
        storage.delete([row["storage_path"]])
        reject("STORED_FILE_INVALID", "The stored file did not match what was sent; it was deleted. Try again.", 422)
    replaced = old.fetchall()
    if replaced:  # the newest upload of a document replaces the older ones
        storage.delete([r["storage_path"] for r in replaced])
        db.executemany("DELETE FROM document_uploads WHERE upload_id=?", [(r["upload_id"],) for r in replaced])
    db.execute("UPDATE document_uploads SET status='uploaded', size_bytes=?, uploaded_at=? WHERE upload_id=?",
               (len(data), iso(), row["upload_id"]))
    catalogue.set_doc_mark(row["session_id"], row["doc_key"], "uploaded", by="upload", commit=False)
    metrics.UPLOADS.labels("uploaded").inc()
    audit("document.uploaded", session_id=row["session_id"],
          details={"upload_id": row["upload_id"], "doc_key": row["doc_key"], "content_type": kind,
                   "size_bytes": len(data), "replaced": [r["upload_id"] for r in replaced]})
    db.commit()
    return {"upload_id": row["upload_id"], "doc_key": row["doc_key"], "status": "uploaded", "verified": False,
            "size_bytes": len(data), "content_type": kind}


# ---------------------------------------------------------------- viewing

def create_view_url(session_id: str, doc_key: str) -> dict:
    """For the session's owner, or a reviewer / admin when the session has a case the citizen consented to share."""
    db = get_db()
    staff = current_user()
    if staff and staff["role"] in ("reviewer", "admin"):
        g.user = staff
        s, cases, latest = db.query_many([(profile.SESSION_SQL, (session_id,)), (CASES_SQL, (session_id,)),
                                          (LATEST_SQL, (session_id, doc_key))])
        if not s.fetchone():
            raise ApiError("SESSION_NOT_FOUND", "Session not found.", 404)
        if not consented_case(cases.fetchall()):
            raise ApiError("FORBIDDEN", "Reviewers can open documents only of cases shared with them.", 403)
        actor, role = staff["user_id"], staff["role"]
    else:
        session, _, (latest,) = profile.load(session_id, allow_ended=True, extra=[(LATEST_SQL, (session_id, doc_key))])
        claims = g.get("auth")
        actor, role = (claims["sub"] if claims else "citizen"), (staff["role"] if staff else "citizen")
    row = latest.fetchone()
    if not row:
        raise ApiError("NO_UPLOAD", "No uploaded file for this document.", 404)
    ttl = min(int(current_app.config["VIEW_URL_TTL_S"]), VIEW_TTL_MAX_S)
    token, expires = _sign("view", ttl, u=row["upload_id"], by=actor, r=role)
    return {"view_url": f"/api/v1/uploads/view/{token}", "expires_at": expires, "content_type": row["content_type"],
            "status": row["status"], "uploaded_at": row["uploaded_at"]}


def serve_view(token: str) -> Response:
    claims = _verify("view", token)
    db = get_db()
    row = db.execute("SELECT * FROM document_uploads WHERE upload_id=? AND status IN ('uploaded', 'verified')",
                     (claims["u"],)).fetchone()
    if not row:
        raise ApiError("DOCUMENT_NOT_FOUND", "This document is no longer stored.", 404)
    data = storage.download(row["storage_path"])
    audit("document.viewed", session_id=row["session_id"], actor_id=claims["by"], actor_role=claims["r"],
          details={"upload_id": row["upload_id"], "doc_key": row["doc_key"]})
    db.commit()
    # Images are fully sandboxed; PDFs keep the browser's own (sandboxed) viewer, which a CSP sandbox would disable.
    csp = ("default-src 'none'; img-src 'self'; style-src 'unsafe-inline'; sandbox; frame-ancestors 'self'"
           if row["content_type"].startswith("image/") else "frame-ancestors 'self'")
    return Response(data, mimetype=row["content_type"], headers={
        "Cache-Control": "no-store, private, max-age=0", "Pragma": "no-cache", "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Content-Security-Policy": csp})


# ---------------------------------------------------------------- reviewer

def review_document(case_id: str, doc_key: str, action: str) -> dict:
    db = get_db()
    case, latest = db.query_many([
        ("SELECT * FROM cases WHERE case_id=?", (case_id,)),
        ("SELECT u.* FROM document_uploads u JOIN cases c ON c.session_id = u.session_id WHERE c.case_id=?"
         " AND u.doc_key=? AND u.status IN ('uploaded', 'verified') ORDER BY u.uploaded_at DESC LIMIT 1", (case_id, doc_key))])
    case, row = case.fetchone(), latest.fetchone()
    if not case:
        raise ApiError("CASE_NOT_FOUND", "Case not found.", 404)
    if json.loads(case["consent_json"]).get("share_with_reviewer") is not True:
        raise ApiError("FORBIDDEN", "The citizen has not consented to share this case.", 403)
    if case["status"] == "REVIEWED":
        raise ApiError("CASE_CLOSED", "This case already has a recorded review.", 409)
    if not row:
        raise ApiError("NO_UPLOAD", "No uploaded file for this document.", 404)
    if action == "verify":
        catalogue.set_doc_mark(case["session_id"], doc_key, "verified", by="reviewer", commit=False)
        status = "verified"
    elif action == "request_reupload":
        storage.delete([row["storage_path"]])  # the rejected file is not kept
        db.execute("DELETE FROM document_uploads WHERE upload_id=?", (row["upload_id"],))
        catalogue.set_doc_mark(case["session_id"], doc_key, "reupload_requested", by="reviewer", commit=False)
        status = "reupload_requested"
    else:
        raise ApiError("INVALID_ACTION", "action must be verify or request_reupload.", 422)
    audit(f"review.document_{action}", case_id=case_id, details={"doc_key": doc_key, "upload_id": row["upload_id"]})
    db.commit()
    return {"case_id": case_id, "doc_key": doc_key, "status": status}


# ---------------------------------------------------------------- deletion

def paths_for_sessions(db, session_ids: list[str]) -> list[tuple[str, str]]:
    """(upload_id, storage_path) of every upload of these sessions, pending ones included."""
    if not session_ids:
        return []
    marks = ",".join("?" * len(session_ids))
    return [(r[0], r[1]) for r in db.execute(
        f"SELECT upload_id, storage_path FROM document_uploads WHERE session_id IN ({marks})", session_ids)]


def delete_uploads(db, uploads: list[tuple[str, str]]) -> int:
    """Delete the objects first, then their rows (queued in the caller's transaction). Raises if Storage fails, so the
    rows stay and the next retention run tries again."""
    if not uploads:
        return 0
    storage.delete([p for _, p in uploads])
    db.executemany("DELETE FROM document_uploads WHERE upload_id=?", [(u,) for u, _ in uploads])
    return len(uploads)


def expired_uploads(db, cfg) -> list[tuple[str, str]]:
    """Uploads of cases reviewed more than REVIEWED_UPLOAD_RETENTION_DAYS ago (no open case on the session), and
    pending / rejected rows older than an hour."""
    from datetime import timedelta
    reviewed_cutoff = iso(now() - timedelta(days=cfg["REVIEWED_UPLOAD_RETENTION_DAYS"]))
    stale = iso(now() - timedelta(hours=1))
    rows = db.execute(
        """SELECT u.upload_id, u.storage_path FROM document_uploads u
           WHERE (u.status IN ('pending', 'rejected') AND u.created_at < ?)
              OR (EXISTS (SELECT 1 FROM cases c WHERE c.session_id = u.session_id)
                  AND NOT EXISTS (SELECT 1 FROM cases c WHERE c.session_id = u.session_id
                                  AND (c.status <> 'REVIEWED' OR c.updated_at >= ?)))""", (stale, reviewed_cutoff))
    return [(r[0], r[1]) for r in rows]
