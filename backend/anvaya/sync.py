"""Kiosk bundle distribution and offline outbox ingestion (dedup, re-evaluation, conflicts)."""
import hashlib
import json

from flask import current_app

from . import catalogue, cases, i18n, metrics, profile
from .common import ApiError, audit
from .db import dumps, get_db, iso, new_id

SCHEMA_VERSION = 1


def build_bundle() -> dict:
    rules = []
    for item in catalogue.active_rules():
        rules.append({"rule": item["rule"], "meta": item["meta"]})
    body = {
        "bundle_version": current_app.config["RULE_BUNDLE_VERSION"],
        "schema_version": SCHEMA_VERSION,
        "rules": rules,
        "documents": i18n.DOCUMENTS,
        "scope_note": "Offline pre-screening covers only these curated rules. Results are preliminary and are re-checked online before handoff.",
    }
    checksum = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return {**body, "generated_at": iso(), "checksum": checksum}


def _ingest_offline_draft(device_id: str, ev: dict) -> dict:
    p = ev["payload"]
    lang = p.get("language", "en")
    sess = profile.create_session("kiosk", lang, device_id=device_id)
    sid = sess["session_id"]
    for attr, value in (p.get("facts") or {}).items():
        if value is None or value == "":
            continue
        profile.upsert_fact(sid, attr, value, source="kiosk_offline_form", confidence=1.0, confirmed=True,
                            raw_text="entered offline on kiosk form")
    for doc, status in (p.get("documents") or {}).items():
        if status in ("available", "missing", "expired", "unknown"):
            catalogue.set_doc_mark(sid, doc, status, commit=False)
    evaluation = catalogue.evaluate_session(sid, origin="offline_sync")
    server_result = next((r for r in evaluation["results"] if r["scheme_id"] == p["scheme_id"]), None)
    local_outcome = (p.get("local_result") or {}).get("outcome")
    out = {
        "status": "accepted",
        "session_id": sid,
        "local_outcome": local_outcome,
        "server_outcome": server_result["outcome"] if server_result else None,
        "result_changed": (server_result["outcome"] if server_result else None) != local_outcome,
        "bundle_outdated": ev.get("bundle_version") != current_app.config["RULE_BUNDLE_VERSION"],
    }
    if not server_result or server_result["outcome"] == "MISMATCH":
        out["status"] = "accepted_no_draft"
        out["message"] = "Online re-check no longer supports a draft for this scheme."
        return out
    draft = cases.save_draft(sid, p["scheme_id"], origin="offline_sync")
    out["draft_id"] = draft["draft_id"]
    if (p.get("consent") or {}).get("share_with_reviewer"):
        h = cases.handoff(draft["draft_id"], sid, p["consent"])
        out.update({"case_id": h["case_id"], "code": h["code"], "case_status": h["status"]})
    return out


def _ingest_draft_edit(ev: dict) -> dict:
    p = ev["payload"]
    row = get_db().execute("SELECT * FROM drafts WHERE draft_id=?", (p["draft_id"],)).fetchone()
    if not row:
        return {"status": "rejected", "reason": "DRAFT_NOT_FOUND"}
    if row["version"] != p.get("base_version"):
        return {"status": "conflict", "reason": "VERSION_MISMATCH", "server_version": row["version"],
                "message": "The draft changed on the server while this kiosk was offline. Reconcile before re-sending."}
    try:
        d = cases.patch_draft(p["draft_id"], row["session_id"], p["base_version"], p.get("fields") or {})
    except ApiError as e:
        return {"status": "rejected", "reason": e.code}
    return {"status": "accepted", "draft_id": d["draft_id"], "version": d["version"]}


def _process(device_id: str, ev: dict) -> dict:
    if ev.get("schema_version") != SCHEMA_VERSION:
        return {"status": "rejected", "reason": "UNSUPPORTED_SCHEMA_VERSION"}
    if ev.get("type") == "offline_draft":
        return _ingest_offline_draft(device_id, ev)
    if ev.get("type") == "draft_edit":
        return _ingest_draft_edit(ev)
    return {"status": "rejected", "reason": "UNKNOWN_EVENT_TYPE"}


def ingest(device_id: str, events: list[dict]) -> dict:
    """Apply each outbox event exactly once. The event is claimed first (INSERT ... ON CONFLICT DO NOTHING on its
    event_id and idempotency_key) in the same transaction as its effects, so the same event sent twice at once is
    applied once; the second sender waits for the first commit and gets "duplicate"."""
    if not device_id:
        raise ApiError("DEVICE_ID_REQUIRED", "device_id is required.", 422)
    db = get_db()
    results = []
    for ev in events[:50]:
        key = ev.get("idempotency_key")
        if not key or not ev.get("event_id"):
            results.append({"event_id": ev.get("event_id"), "status": "rejected", "reason": "MISSING_KEYS"})
            continue
        with db.transaction():
            claimed = db.execute(
                """INSERT INTO sync_events(event_id, device_id, idempotency_key, session_id, event_type,
                   local_created_at, bundle_version, rule_version, schema_version, payload_json, server_result_json,
                   received_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT DO NOTHING RETURNING event_id""",
                (ev["event_id"], device_id, key, None, ev.get("type", "?"), ev.get("created_at"),
                 ev.get("bundle_version"), ev.get("rule_version"), ev.get("schema_version") or 0,
                 dumps({k: v for k, v in (ev.get("payload") or {}).items() if k != "facts"}), "{}", iso()),
            ).fetchone()
            if not claimed:
                prior = db.execute("SELECT server_result_json FROM sync_events WHERE idempotency_key=? OR event_id=?",
                                   (key, ev["event_id"])).fetchone()
                metrics.SYNC_EVENTS.labels("duplicate").inc()
                results.append({"event_id": ev["event_id"], "status": "duplicate",
                                "original": json.loads(prior["server_result_json"])})
                continue
            try:
                with db.savepoint():  # a rejected event keeps its claim and result, not its partial effects
                    res = _process(device_id, ev)
            except ApiError as e:
                res = {"status": "rejected", "reason": e.code, "message": e.message}
            db.execute("UPDATE sync_events SET session_id=?, server_result_json=? WHERE event_id=?",
                       (res.get("session_id"), dumps(res), ev["event_id"]))
            metrics.SYNC_EVENTS.labels(res["status"]).inc()
            if res.get("result_changed"):
                metrics.SYNC_RESULT_CHANGED.inc()
            audit("sync.event", case_id=res.get("case_id"), session_id=res.get("session_id"),
                  details={"event_id": ev["event_id"], "device_id": device_id, "status": res["status"]})
        results.append({"event_id": ev["event_id"], **res})
    return {"device_id": device_id, "server_bundle_version": current_app.config["RULE_BUNDLE_VERSION"],
            "results": results}
