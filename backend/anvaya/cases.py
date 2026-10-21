"""Draft preparation, consent + handoff, case-code status lookup and reviewer decisions."""
import json
import secrets
import time
from collections import defaultdict, deque

from flask import current_app, request

from . import catalogue, i18n, metrics, profile, rules_engine
from .common import ApiError, audit, sha256
from .db import dumps, get_db, iso, iso_in, new_id, now, parse_iso

BASE_FIELDS = ["applicant_name", "state", "district", "age", "gender"]
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L

CASE_STATES = {"PENDING_REVIEW", "CORRECTION_REQUESTED", "REVIEWED"}
REVIEW_OUTCOMES = {"appears_eligible", "not_eligible", "needs_more_documents"}

_lookup_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(bucket: str) -> None:
    limit = current_app.config["CODE_LOOKUP_LIMIT_PER_MIN"]
    key = f"{bucket}:{request.remote_addr}"
    q, t = _lookup_hits[key], time.monotonic()
    while q and t - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        metrics.RATE_LIMITED.labels(bucket).inc()
        audit("case.lookup_rate_limited", details={"bucket": bucket})
        get_db().commit()
        raise ApiError("RATE_LIMITED", "Too many code lookups. Wait a minute and try again.", 429)
    q.append(t)


def new_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"ANV-{raw[:4]}-{raw[4:]}"


def normalize_code(code: str) -> str:
    c = "".join(ch for ch in (code or "").upper() if ch.isalnum())
    if c.startswith("ANV"):
        c = c[3:]
    return f"ANV-{c[:4]}-{c[4:8]}"


# ---------------------------------------------------------------- drafts

def _build_fields(session_id: str, rule_facts: list[str]) -> list[dict]:
    facts = profile.current_facts(session_id)
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


def _draft_public(row, lang="en") -> dict:
    fields = json.loads(row["fields_json"])
    for f in fields.get("fields", []):
        f["label"] = i18n.t(i18n.ATTRIBUTE_LABELS, f["key"], lang)
    case = get_db().execute("SELECT case_id, status, review_outcome, updated_at FROM cases WHERE draft_id=?",
                            (row["draft_id"],)).fetchone()
    return {
        "draft_id": row["draft_id"], "session_id": row["session_id"], "scheme_id": row["scheme_id"],
        "eval_id": row["eval_id"], "version": row["version"], "status": row["status"], "origin": row["origin"],
        "bundle_version": row["bundle_version"], "created_at": row["created_at"], "updated_at": row["updated_at"],
        **fields,
        "case": dict(case) if case else None,
        "notice": "This is a draft for review. It has not been submitted to any government portal.",
    }


def save_draft(session_id: str, scheme_id: str, origin: str = "online") -> dict:
    session = profile.get_session(session_id)
    ev = catalogue.latest_evaluation(session_id)
    if not ev:
        raise ApiError("NO_EVALUATION", "Check schemes before preparing a draft.", 409)
    result = next((r for r in ev["results"] if r["scheme_id"] == scheme_id), None)
    if not result:
        raise ApiError("SCHEME_NOT_EVALUATED", "This scheme was not part of the latest screening.", 409)
    if result["outcome"] == rules_engine.MISMATCH:
        raise ApiError("SCHEME_MISMATCH", "A confirmed detail does not meet this scheme's criteria; no draft prepared.", 409)
    rule_facts = [c["fact"] for c in result["criteria"]]
    marks = catalogue.doc_marks(session_id)
    body = {
        "scheme_name": result["scheme_name"],
        "fields": _build_fields(session_id, rule_facts),
        "documents": [{"doc_key": e["doc_key"], "status": marks.get(e["doc_key"], "unknown")} for e in result["evidence"]],
        "eligibility_snapshot": {"outcome": result["outcome"], "rule_id": result["rule_id"],
                                 "rule_version": result["rule_version"], "bundle_version": ev["bundle_version"],
                                 "eval_id": ev["eval_id"], "decision_reason": result["decision_reason"]},
    }
    db = get_db()
    existing = db.execute("SELECT * FROM drafts WHERE session_id=? AND scheme_id=?", (session_id, scheme_id)).fetchone()
    if existing:
        case = db.execute("SELECT status FROM cases WHERE draft_id=?", (existing["draft_id"],)).fetchone()
        if case and case["status"] in ("PENDING_REVIEW", "REVIEWED"):
            raise ApiError("DRAFT_LOCKED", "This draft is with the reviewer and cannot be changed now.", 409)
        db.execute("UPDATE drafts SET fields_json=?, eval_id=?, version=version+1, updated_at=?, bundle_version=? WHERE draft_id=?",
                   (dumps(body), ev["eval_id"], iso(), ev["bundle_version"], existing["draft_id"]))
        draft_id = existing["draft_id"]
        action = "draft.updated"
    else:
        draft_id = new_id("DRF")
        db.execute(
            """INSERT INTO drafts(draft_id, session_id, scheme_id, eval_id, version, fields_json, status, origin,
               bundle_version, created_at, updated_at) VALUES (?,?,?,?,1,?,?,?,?,?,?)""",
            (draft_id, session_id, scheme_id, ev["eval_id"], dumps(body), "DRAFT_SAVED", origin, ev["bundle_version"], iso(), iso()),
        )
        action = "draft.created"
    profile.set_workflow_state(session_id, "DRAFT_SAVED")
    row = db.execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
    metrics.DRAFTS.labels(action.split(".")[1]).inc()
    audit(action, session_id=session_id, object_version=row["version"], details={"draft_id": draft_id, "scheme_id": scheme_id})
    db.commit()
    return _draft_public(row, session["language"])


def get_draft(draft_id: str, session_id: str | None, staff: bool = False) -> dict:
    row = get_db().execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
    if not row:
        raise ApiError("DRAFT_NOT_FOUND", "Draft not found.", 404)
    if not staff and row["session_id"] != session_id:
        raise ApiError("FORBIDDEN", "This draft belongs to another session.", 403)
    lang = get_db().execute("SELECT language FROM sessions WHERE session_id=?", (row["session_id"],)).fetchone()[0]
    return _draft_public(row, lang)


def patch_draft(draft_id: str, session_id: str, version: int, edits: dict) -> dict:
    """Citizen edits with optimistic concurrency. Each edit becomes a confirmed citizen-entered fact."""
    db = get_db()
    row = db.execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
    if not row:
        raise ApiError("DRAFT_NOT_FOUND", "Draft not found.", 404)
    if row["session_id"] != session_id:
        raise ApiError("FORBIDDEN", "This draft belongs to another session.", 403)
    if row["version"] != version:
        audit("draft.conflict", session_id=session_id, object_version=row["version"], details={"draft_id": draft_id, "sent_version": version})
        db.commit()
        raise ApiError("CONFLICT", "The draft changed since you opened it. Reload and re-apply your edits.", 409,
                       {"current_version": row["version"]})
    case = db.execute("SELECT status FROM cases WHERE draft_id=?", (draft_id,)).fetchone()
    if case and case["status"] in ("PENDING_REVIEW", "REVIEWED"):
        raise ApiError("DRAFT_LOCKED", "This draft is with the reviewer and cannot be changed now.", 409)
    for key, value in edits.items():
        profile.upsert_fact(session_id, key, value, source="draft_edit", confidence=1.0, confirmed=True)
    db.commit()
    # Re-run rules so the draft snapshot reflects the edited facts, then rebuild the draft.
    catalogue.evaluate_session(session_id, require_confirmed=False)
    return save_draft(session_id, row["scheme_id"], origin=row["origin"])


def handoff(draft_id: str, session_id: str, consent: dict, staff: bool = False) -> dict:
    db = get_db()
    row = db.execute("SELECT * FROM drafts WHERE draft_id=?", (draft_id,)).fetchone()
    if not row:
        raise ApiError("DRAFT_NOT_FOUND", "Draft not found.", 404)
    if not staff and row["session_id"] != session_id:
        raise ApiError("FORBIDDEN", "This draft belongs to another session.", 403)
    if not (consent.get("share_with_reviewer") is True):
        raise ApiError("CONSENT_REQUIRED", "The citizen must consent to share this draft with a reviewer.", 422)
    session = profile.get_session(row["session_id"], allow_ended=True)

    # Re-check under the current rule bundle before handoff and tell the citizen if anything changed.
    snapshot = json.loads(row["fields_json"])["eligibility_snapshot"]
    current = None
    for c in catalogue.candidate_rules(catalogue.engine_facts(row["session_id"]).get("state", {}).get("value")):
        if c["rule"]["scheme_id"] == row["scheme_id"]:
            current = rules_engine.evaluate(c["rule"], catalogue.engine_facts(row["session_id"]),
                                            catalogue.doc_marks(row["session_id"]), c["meta"])
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
    case = db.execute("SELECT * FROM cases WHERE draft_id=?", (draft_id,)).fetchone()
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
             session["language"], row["origin"], dumps(recheck), iso(), iso()),
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
    row = get_db().execute("SELECT * FROM cases WHERE code_hash=?", (sha256(normalize_code(code)),)).fetchone()
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
    scheme = get_db().execute("SELECT d.scheme_id, s.name FROM drafts d JOIN schemes s ON s.scheme_id=d.scheme_id WHERE d.draft_id=?",
                              (row["draft_id"],)).fetchone()
    status_label = i18n.t(i18n.CASE_STATUS, row["status"], lang)
    return {
        "status": row["status"], "status_label": status_label, "updated_at": row["updated_at"],
        "review_outcome": row["review_outcome"], "scheme_name": scheme["name"], "language": lang,
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
                    d.scheme_id, s.name AS scheme_name, d.fields_json, se.is_test
             FROM cases c JOIN drafts d ON d.draft_id=c.draft_id JOIN schemes s ON s.scheme_id=d.scheme_id
             JOIN sessions se ON se.session_id=c.session_id
             WHERE json_extract(c.consent_json, '$.share_with_reviewer') = 1"""
    args = []
    if status:
        sql += " AND c.status=?"
        args.append(status)
    sql += " ORDER BY c.updated_at DESC"
    out = []
    for r in db.execute(sql, args):
        snap = json.loads(r["fields_json"])["eligibility_snapshot"]
        out.append({k: r[k] for k in ("case_id", "status", "review_outcome", "origin", "created_at", "updated_at",
                                      "language", "scheme_id", "scheme_name")}
                   | {"screening_outcome": snap["outcome"], "is_test": bool(r["is_test"])})
    return out


def get_case(case_id: str) -> dict:
    db = get_db()
    row = db.execute("SELECT * FROM cases WHERE case_id=?", (case_id,)).fetchone()
    if not row:
        raise ApiError("CASE_NOT_FOUND", "Case not found.", 404)
    consent = json.loads(row["consent_json"])
    if not consent.get("share_with_reviewer"):
        raise ApiError("FORBIDDEN", "The citizen has not consented to share this case.", 403)
    draft = get_draft(row["draft_id"], None, staff=True)
    ev = catalogue.latest_evaluation(row["session_id"])
    scheme_result = next((r for r in (ev["results"] if ev else []) if r["scheme_id"] == draft["scheme_id"]), None)
    audit("case.read", case_id=case_id)
    db.commit()
    return {
        "case_id": case_id, "status": row["status"], "review_outcome": row["review_outcome"],
        "reviewer_note": row["reviewer_note"], "origin": row["origin"], "language": row["language"],
        "created_at": row["created_at"], "updated_at": row["updated_at"],
        "consent": consent, "recheck": json.loads(row["recheck_json"]) if row["recheck_json"] else None,
        "facts": profile.fact_history(row["session_id"]),
        "documents": catalogue.doc_marks(row["session_id"]),
        "draft": draft,
        "evaluation": catalogue.localize_result(scheme_result, "en") if scheme_result else None,
        "scheme": catalogue.scheme_card(db.execute("SELECT * FROM schemes WHERE scheme_id=?", (draft["scheme_id"],)).fetchone()),
        "audit": case_audit(case_id),
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
        catalogue.set_doc_mark(row["session_id"], doc, "verified", by="reviewer")
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


def case_audit(case_id: str) -> list[dict]:
    db = get_db()
    session_id = db.execute("SELECT session_id FROM cases WHERE case_id=?", (case_id,)).fetchone()
    rows = db.execute(
        "SELECT * FROM audit_events WHERE case_id=? OR (session_id=? AND case_id IS NULL) ORDER BY ts, rowid",
        (case_id, session_id[0] if session_id else None),
    ).fetchall()
    return [{"event_id": r["event_id"], "actor_id": r["actor_id"], "actor_role": r["actor_role"], "action": r["action"],
             "ts": r["ts"], "request_id": r["request_id"], "object_version": r["object_version"],
             "details": json.loads(r["details_json"])} for r in rows]
