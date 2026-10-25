"""Draft preparation, consent + handoff, case-code status lookup and reviewer decisions."""
import json
import secrets

from flask import current_app, request

from . import catalogue, i18n, metrics, profile, ratelimit, rules_engine
from .common import ApiError, audit, sha256
from .db import dumps, get_db, iso, iso_in, new_id, now, parse_iso

BASE_FIELDS = ["applicant_name", "state", "district", "age", "gender"]
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L

CASE_STATES = {"PENDING_REVIEW", "CORRECTION_REQUESTED", "REVIEWED"}
REVIEW_OUTCOMES = {"appears_eligible", "not_eligible", "needs_more_documents"}

def rate_limit(bucket: str) -> None:
    def audited():
        audit("case.lookup_rate_limited", details={"bucket": bucket})
        get_db().commit()
    ratelimit.limit_per_minute(bucket, current_app.config["CODE_LOOKUP_LIMIT_PER_MIN"],
                               "Too many code lookups. Wait a minute and try again.", on_limited=audited)


def new_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"ANV-{raw[:4]}-{raw[4:]}"


def normalize_code(code: str) -> str:
    c = "".join(ch for ch in (code or "").upper() if ch.isalnum())
    if c.startswith("ANV"):
        c = c[3:]
    return f"ANV-{c[:4]}-{c[4:8]}"


# ---------------------------------------------------------------- drafts

def _build_fields(facts: dict, rule_facts: list[str]) -> list[dict]:
    keys = list(dict.fromkeys(BASE_FIELDS + rule_facts))
    out = []
    for k in keys:
        f = facts.get(k)
        if f is None:
            out.append({"key": k, "value": None, "provenance": "missing", "fact_id": None})
        else:
            prov = "citizen_entered" if f["source"] == "draft_edit" else (
                "inferred" if f["inferred"] and not f["confirmed"] else ("confirmed" if f["confirmed"] else "unconfirmed"))
            out.append({"key": k, "value": f["value"], "provenance": prov, "fact_id": f["fact_id"]})
    return out


# A draft with its session's language and its case (if any), in one query.
DRAFT_SQL = """SELECT d.*, s.language AS session_language, s.mode, s.device_id, s.operator_id, s.auth_user_id,
                      c.case_id AS case_case_id, c.status AS case_status,
                      c.review_outcome AS case_review_outcome, c.updated_at AS case_updated_at
               FROM drafts d JOIN sessions s ON s.session_id = d.session_id
               LEFT JOIN cases c ON c.draft_id = d.draft_id"""
LOCKED_STATES = ("PENDING_REVIEW", "REVIEWED")


def _case_of(row) -> dict | None:
    if row["case_case_id"] is None:
        return None
    return {"case_id": row["case_case_id"], "status": row["case_status"], "review_outcome": row["case_review_outcome"],
            "updated_at": row["case_updated_at"]}


def _draft_public(row, lang="en", case: dict | None = None) -> dict:
    fields = json.loads(row["fields_json"])
    for f in fields.get("fields", []):
        f["label"] = i18n.t(i18n.ATTRIBUTE_LABELS, f["key"], lang)
    return {
        "draft_id": row["draft_id"], "session_id": row["session_id"], "scheme_id": row["scheme_id"],
        "eval_id": row["eval_id"], "version": row["version"], "status": row["status"], "origin": row["origin"],
        "bundle_version": row["bundle_version"], "created_at": row["created_at"], "updated_at": row["updated_at"],
        **fields,
        "case": case,
        "notice": "This is a draft for review. It has not been submitted to any government portal.",
    }


def save_draft(session_id: str, scheme_id: str, origin: str = "online") -> dict:
    """Create the session's draft for a scheme, or refresh it (version + 1) from the latest screening. One upsert on
    UNIQUE(session_id, scheme_id), so concurrent saves never create two drafts; a draft whose case is with the
    reviewer is never changed (checked inside the same statement)."""
    session, fact_set, (ev_row, marks_rows, existing) = profile.load(session_id, extra=[
        (catalogue.LATEST_EVAL_SQL, (session_id,)), (catalogue.DOC_MARKS_SQL, (session_id,)),
        (DRAFT_SQL + " WHERE d.session_id=? AND d.scheme_id=?", (session_id, scheme_id))])
    ev = catalogue.latest_evaluation(session_id, ev_row.fetchone())
    if not ev:
        raise ApiError("NO_EVALUATION", "Check schemes before preparing a draft.", 409)
    result = next((r for r in ev["results"] if r["scheme_id"] == scheme_id), None)
    if not result:
        raise ApiError("SCHEME_NOT_EVALUATED", "This scheme was not part of the latest screening.", 409)
    if result["outcome"] == rules_engine.MISMATCH:
        raise ApiError("SCHEME_MISMATCH", "A confirmed detail does not meet this scheme's criteria; no draft prepared.", 409)
    rule_facts = [c["fact"] for c in result["criteria"]]
    marks = {r["doc_key"]: r["status"] for r in marks_rows}
    existing = existing.fetchone()
    if existing and existing["case_status"] in LOCKED_STATES:
        raise ApiError("DRAFT_LOCKED", "This draft is with the reviewer and cannot be changed now.", 409)
    body = {
        "scheme_name": result["scheme_name"],
        "fields": _build_fields(fact_set.current(), rule_facts),
        "documents": [{"doc_key": e["doc_key"], "status": marks.get(e["doc_key"], "unknown")} for e in result["evidence"]],
        "eligibility_snapshot": {"outcome": result["outcome"], "rule_id": result["rule_id"],
                                 "rule_version": result["rule_version"], "bundle_version": ev["bundle_version"],
                                 "eval_id": ev["eval_id"], "decision_reason": result["decision_reason"]},
    }
    db = get_db()
    ts = iso()
    row = db.execute(
        """INSERT INTO drafts(draft_id, session_id, scheme_id, eval_id, version, fields_json, status, origin,
           bundle_version, created_at, updated_at) VALUES (?,?,?,?,1,?,?,?,?,?,?)
           ON CONFLICT (session_id, scheme_id) DO UPDATE SET fields_json=excluded.fields_json,
               eval_id=excluded.eval_id, version=drafts.version + 1, updated_at=excluded.updated_at,
               bundle_version=excluded.bundle_version
           WHERE NOT EXISTS (SELECT 1 FROM cases WHERE cases.draft_id = drafts.draft_id
                             AND cases.status IN ('PENDING_REVIEW', 'REVIEWED'))
           RETURNING *""",
        (new_id("DRF"), session_id, scheme_id, ev["eval_id"], dumps(body), "DRAFT_SAVED", origin, ev["bundle_version"],
         ts, ts),
    ).fetchone()
    if row is None:  # a case reached the reviewer between our read and the upsert
        raise ApiError("DRAFT_LOCKED", "This draft is with the reviewer and cannot be changed now.", 409)
    action = "draft.created" if row["version"] == 1 else "draft.updated"
    profile.set_workflow_state(session_id, "DRAFT_SAVED")
    metrics.DRAFTS.labels(action.split(".")[1]).inc()
    audit(action, session_id=session_id, object_version=row["version"],
          details={"draft_id": row["draft_id"], "scheme_id": scheme_id})
    db.commit()
    return _draft_public(row, session["language"], _case_of(existing) if existing else None)


def get_draft(draft_id: str, session_id: str | None, staff: bool = False) -> dict:
    row = get_db().execute(DRAFT_SQL + " WHERE d.draft_id=?", (draft_id,)).fetchone()
    if not row:
        raise ApiError("DRAFT_NOT_FOUND", "Draft not found.", 404)
    if not staff and row["session_id"] != session_id:
        raise ApiError("FORBIDDEN", "This draft belongs to another session.", 403)
    if not staff:
        profile.check_owner(dict(row))
    return _draft_public(row, row["session_language"], _case_of(row))


def patch_draft(draft_id: str, session_id: str, version: int, edits: dict) -> dict:
    """Citizen edits with optimistic concurrency. Each edit becomes a confirmed citizen-entered fact."""
    db = get_db()
    row = db.execute(DRAFT_SQL + " WHERE d.draft_id=?", (draft_id,)).fetchone()
    if not row:
        raise ApiError("DRAFT_NOT_FOUND", "Draft not found.", 404)
    if row["session_id"] != session_id:
        raise ApiError("FORBIDDEN", "This draft belongs to another session.", 403)
    profile.check_owner(dict(row))
    if row["version"] != version:
        audit("draft.conflict", session_id=session_id, object_version=row["version"], details={"draft_id": draft_id, "sent_version": version})
        db.commit()
        raise ApiError("CONFLICT", "The draft changed since you opened it. Reload and re-apply your edits.", 409,
                       {"current_version": row["version"]})
    if row["case_status"] in LOCKED_STATES:
        raise ApiError("DRAFT_LOCKED", "This draft is with the reviewer and cannot be changed now.", 409)
    facts = profile.load_facts(session_id)
    for key, value in edits.items():
        profile.upsert_fact(session_id, key, value, source="draft_edit", confidence=1.0, confirmed=True, facts=facts)
    db.commit()
    # Re-run rules so the draft snapshot reflects the edited facts, then rebuild the draft.
    catalogue.evaluate_session(session_id, require_confirmed=False)
    return save_draft(session_id, row["scheme_id"], origin=row["origin"])


def handoff(draft_id: str, session_id: str, consent: dict, staff: bool = False) -> dict:
    """Share a draft with a reviewer: creates its case (or re-issues the code / resubmits after a correction). The
    draft row is locked (SELECT ... FOR UPDATE on Postgres; SQLite's write lock) for the rest of the transaction, so
    concurrent hand-offs of one draft run one after another and the draft never gets two cases."""
    db = get_db()
    by_draft = "(SELECT session_id FROM drafts WHERE draft_id=?)"
    row, fact_rows, marks_rows, case = db.query_many([
        ("SELECT d.*, s.language AS session_language, s.mode, s.device_id, s.operator_id, s.auth_user_id"
         " FROM drafts d JOIN sessions s ON s.session_id = d.session_id WHERE d.draft_id=? FOR UPDATE OF d", (draft_id,)),
        (f"SELECT * FROM facts WHERE session_id={by_draft} ORDER BY captured_at, rowid", (draft_id,)),
        (f"SELECT doc_key, status FROM doc_marks WHERE session_id={by_draft}", (draft_id,)),
        ("SELECT * FROM cases WHERE draft_id=?", (draft_id,)),
    ])
    row = row.fetchone()
    if not row:
        raise ApiError("DRAFT_NOT_FOUND", "Draft not found.", 404)
    if not staff and row["session_id"] != session_id:
        raise ApiError("FORBIDDEN", "This draft belongs to another session.", 403)
    if not staff:
        profile.check_owner(dict(row))
    if not (consent.get("share_with_reviewer") is True):
        raise ApiError("CONSENT_REQUIRED", "The citizen must consent to share this draft with a reviewer.", 422)

    # Re-check under the current rule bundle before handoff and tell the citizen if anything changed.
    snapshot = json.loads(row["fields_json"])["eligibility_snapshot"]
    facts = catalogue.engine_facts(row["session_id"], profile.Facts(row["session_id"], fact_rows).current())
    marks = {r["doc_key"]: r["status"] for r in marks_rows}
    current = None
    for c in catalogue.candidate_rules(facts.get("state", {}).get("value")):
        if c["rule"]["scheme_id"] == row["scheme_id"]:
            current = rules_engine.evaluate(c["rule"], facts, marks, c["meta"])
    recheck = {
        "checked_at": iso(),
        "bundle_version": current_app.config["RULE_BUNDLE_VERSION"],
        "draft_bundle_version": row["bundle_version"],
        "outcome_at_draft": snapshot["outcome"],
        "outcome_now": current["outcome"] if current else None,
        "result_changed": (current["outcome"] if current else None) != snapshot["outcome"],
    }

    code = new_code()
    expires = iso_in(current_app.config["CASE_CODE_TTL_HOURS"])
    case = case.fetchone()
    consent_record = {**consent, "consented_at": iso(), "scope": ["profile_facts", "document_status", "eligibility_trace"]}
    if case:
        if case["status"] == "PENDING_REVIEW":
            action = "case.code_reissued"
        elif case["status"] == "CORRECTION_REQUESTED":
            action = "case.resubmitted"
        else:
            raise ApiError("CASE_CLOSED", "This case has already been reviewed.", 409)
        db.execute("""UPDATE cases SET code_hash=?, code_expires_at=?, consent_json=?, status='PENDING_REVIEW',
                      recheck_json=?, updated_at=? WHERE case_id=?""",
                   (sha256(code), expires, dumps(consent_record), dumps(recheck), iso(), case["case_id"]))
        case_id = case["case_id"]
    else:
        case_id = new_id("CASE")
        db.execute(
            """INSERT INTO cases(case_id, draft_id, session_id, code_hash, code_expires_at, consent_json, status,
               language, origin, recheck_json, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (case_id, draft_id, row["session_id"], sha256(code), expires, dumps(consent_record), "PENDING_REVIEW",
             row["session_language"], row["origin"], dumps(recheck), iso(), iso()),
        )
        action = "case.created"
    db.execute("UPDATE drafts SET status='PENDING_REVIEW' WHERE draft_id=?", (draft_id,))
    profile.set_workflow_state(row["session_id"], "PENDING_REVIEW")
    metrics.CASE_TRANSITIONS.labels(action.split(".")[1]).inc()
    audit(action, case_id=case_id, session_id=row["session_id"], object_version=row["version"],
          details={"draft_id": draft_id, "result_changed": recheck["result_changed"]})
    db.commit()
    return {"case_id": case_id, "code": code, "code_expires_at": expires, "status": "PENDING_REVIEW",
            "recheck": recheck,
            "notice": "Code is a locator for status only. It does not prove identity and does not reveal personal details."}


def _find_case_by_code(code: str):
    row = get_db().execute(
        """SELECT c.*, s.name AS scheme_name FROM cases c JOIN drafts d ON d.draft_id = c.draft_id
           JOIN schemes s ON s.scheme_id = d.scheme_id WHERE c.code_hash=?""", (sha256(normalize_code(code)),)).fetchone()
    if not row:
        return None, "NOT_FOUND"
    if parse_iso(row["code_expires_at"]) < now():
        return row, "EXPIRED"
    return row, "OK"


def public_status(code: str) -> dict:
    """Citizen resume: status only. A code alone never returns profile facts."""
    rate_limit("public_status")
    row, st = _find_case_by_code(code)
    if st == "NOT_FOUND":
        audit("case.lookup_miss")
        get_db().commit()
        raise ApiError("CODE_NOT_FOUND", "No case matches this code.", 404)
    if st == "EXPIRED":
        raise ApiError("CODE_EXPIRED", "This code has expired. Ask the kiosk operator or reviewer for help.", 410)
    lang = row["language"]
    status_label = i18n.t(i18n.CASE_STATUS, row["status"], lang)
    return {
        "status": row["status"], "status_label": status_label, "updated_at": row["updated_at"],
        "review_outcome": row["review_outcome"],
        "review_outcome_label": i18n.t(i18n.REVIEW_OUTCOMES, row["review_outcome"], lang) if row["review_outcome"] else None,
        "scheme_name": row["scheme_name"], "language": lang,
        "spoken_summary": i18n.t(i18n.MESSAGES, "status_line", lang, status=status_label, ts=row["updated_at"][:16].replace("T", " ")),
        "correction_note": row["reviewer_note"] if row["status"] == "CORRECTION_REQUESTED" else None,
        "notice": "Status of a draft review. No government submission has been made.",
    }


# ---------------------------------------------------------------- reviewer

def reviewer_lookup(code: str) -> dict:
    rate_limit("reviewer_lookup")
    row, st = _find_case_by_code(code)
    if st != "OK":
        audit("reviewer.lookup_failed", details={"reason": st})
        get_db().commit()
        raise ApiError("CODE_NOT_FOUND" if st == "NOT_FOUND" else "CODE_EXPIRED", "Code not found or expired.", 404 if st == "NOT_FOUND" else 410)
    audit("reviewer.lookup", case_id=row["case_id"])
    get_db().commit()
    return {"case_id": row["case_id"], "status": row["status"]}


def list_cases(status: str | None = None) -> list[dict]:
    db = get_db()
    sql = """SELECT c.case_id, c.status, c.review_outcome, c.origin, c.created_at, c.updated_at, c.language,
                    c.consent_json, d.scheme_id, s.name AS scheme_name, d.fields_json, se.is_test
             FROM cases c JOIN drafts d ON d.draft_id=c.draft_id JOIN schemes s ON s.scheme_id=d.scheme_id
             JOIN sessions se ON se.session_id=c.session_id"""
    args = []
    if status:
        sql += " WHERE c.status=?"
        args.append(status)
    sql += " ORDER BY c.updated_at DESC, c.case_id"
    out = []
    for r in db.execute(sql, args):
        if json.loads(r["consent_json"]).get("share_with_reviewer") is not True:
            continue  # only cases the citizen consented to share
        snap = json.loads(r["fields_json"])["eligibility_snapshot"]
        out.append({k: r[k] for k in ("case_id", "status", "review_outcome", "origin", "created_at", "updated_at",
                                      "language", "scheme_id", "scheme_name")}
                   | {"screening_outcome": snap["outcome"], "is_test": bool(r["is_test"])})
    return out


def get_case(case_id: str) -> dict:
    db = get_db()
    by_case = "(SELECT session_id FROM cases WHERE case_id=?)"
    row, draft_row, ev_row, fact_rows, marks_rows, scheme_row, audit_rows, upload_rows = db.query_many([
        ("SELECT * FROM cases WHERE case_id=?", (case_id,)),
        (DRAFT_SQL + " WHERE d.draft_id=(SELECT draft_id FROM cases WHERE case_id=?)", (case_id,)),
        (f"SELECT * FROM evaluations WHERE session_id={by_case} ORDER BY created_at DESC, rowid DESC LIMIT 1", (case_id,)),
        (f"SELECT * FROM facts WHERE session_id={by_case} ORDER BY captured_at, rowid", (case_id,)),
        (f"SELECT doc_key, status FROM doc_marks WHERE session_id={by_case}", (case_id,)),
        ("SELECT s.* FROM schemes s JOIN drafts d ON d.scheme_id = s.scheme_id JOIN cases c ON c.draft_id = d.draft_id"
         " WHERE c.case_id=?", (case_id,)),
        _audit_query(case_id),
        (f"SELECT doc_key, upload_id, status, content_type, size_bytes, uploaded_at FROM document_uploads"
         f" WHERE session_id={by_case} AND status IN ('uploaded', 'verified')", (case_id,)),
    ])
    row = row.fetchone()
    if not row:
        raise ApiError("CASE_NOT_FOUND", "Case not found.", 404)
    consent = json.loads(row["consent_json"])
    if not consent.get("share_with_reviewer"):
        raise ApiError("FORBIDDEN", "The citizen has not consented to share this case.", 403)
    draft_row = draft_row.fetchone()
    draft = _draft_public(draft_row, draft_row["session_language"], _case_of(draft_row))
    ev = catalogue.latest_evaluation(row["session_id"], ev_row.fetchone())
    scheme_result = next((r for r in (ev["results"] if ev else []) if r["scheme_id"] == draft["scheme_id"]), None)
    audit("case.read", case_id=case_id)
    db.commit()
    return {
        "case_id": case_id, "status": row["status"], "review_outcome": row["review_outcome"],
        "reviewer_note": row["reviewer_note"], "origin": row["origin"], "language": row["language"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "consent": consent, "recheck": json.loads(row["recheck_json"]) if row["recheck_json"] else None,
        "facts": profile.Facts(row["session_id"], fact_rows).history(),
        "documents": {r["doc_key"]: r["status"] for r in marks_rows},
        "uploads": {r["doc_key"]: {k: r[k] for k in ("upload_id", "status", "content_type", "size_bytes", "uploaded_at")}
                    for r in upload_rows},
        "session_id": row["session_id"],
        "draft": draft,
        "evaluation": catalogue.localize_result(scheme_result, "en") if scheme_result else None,
        "scheme": catalogue.scheme_card(scheme_row.fetchone()),
        "audit": _audit_events(audit_rows),
    }


def decide(case_id: str, body: dict) -> dict:
    db = get_db()
    row = db.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
    if not row:
        raise ApiError("CASE_NOT_FOUND", "Case not found.", 404)
    if row["status"] == "REVIEWED":
        raise ApiError("CASE_CLOSED", "This case already has a recorded review.", 409)
    action = body.get("action")
    note = (body.get("note") or "").strip()[:1000]
    for doc in body.get("verified_documents", []) or []:
        catalogue.set_doc_mark(row["session_id"], doc, "verified", by="reviewer", commit=False)
    if action == "request_correction":
        if not note:
            raise ApiError("NOTE_REQUIRED", "Explain what the citizen needs to correct.", 422)
        db.execute("UPDATE cases SET status='CORRECTION_REQUESTED', reviewer_note=?, updated_at=? WHERE case_id=?",
                   (note, iso(), case_id))
        db.execute("UPDATE drafts SET status='CORRECTION_REQUESTED' WHERE draft_id=?", (row["draft_id"],))
        new_status = "CORRECTION_REQUESTED"
    elif action == "record_review":
        outcome = body.get("outcome")
        if outcome not in REVIEW_OUTCOMES:
            raise ApiError("INVALID_OUTCOME", f"outcome must be one of {sorted(REVIEW_OUTCOMES)}.", 422)
        db.execute("UPDATE cases SET status='REVIEWED', review_outcome=?, reviewer_note=?, updated_at=? WHERE case_id=?",
                   (outcome, note, iso(), case_id))
        db.execute("UPDATE drafts SET status='REVIEWED' WHERE draft_id=?", (row["draft_id"],))
        new_status = "REVIEWED"
    elif action == "verify_documents":
        new_status = row["status"]
    else:
        raise ApiError("INVALID_ACTION", "action must be request_correction, record_review or verify_documents.", 422)
    metrics.CASE_TRANSITIONS.labels(action).inc()
    audit(f"review.{action}", case_id=case_id,
          details={"outcome": body.get("outcome"), "verified_documents": body.get("verified_documents") or []})
    db.commit()
    return {"case_id": case_id, "status": new_status}


def _audit_query(case_id: str) -> tuple:
    return ("SELECT * FROM audit_events WHERE case_id=? OR (case_id IS NULL AND"
            " session_id=(SELECT session_id FROM cases WHERE case_id=?)) ORDER BY ts, rowid", (case_id, case_id))


def case_audit(case_id: str) -> list[dict]:
    return _audit_events(get_db().execute(*_audit_query(case_id)))


def _audit_events(rows) -> list[dict]:
    return [{"event_id": r["event_id"], "actor_id": r["actor_id"], "actor_role": r["actor_role"], "action": r["action"],
             "ts": r["ts"], "request_id": r["request_id"], "object_version": r["object_version"],
             "details": json.loads(r["details_json"])} for r in rows]
