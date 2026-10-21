from flask import Blueprint, current_app, g, jsonify, request

from . import cases, catalogue, i18n, llm, profile, sync, testrunner, voice
from .common import (ApiError, audit, current_user, idem_lookup, idem_store, idempotency_key, login,
                     require_role)
from .db import get_db, iso

bp = Blueprint("api", __name__, url_prefix="/api/v1")


def body() -> dict:
    data = request.get_json(silent=True)
    if data is None and request.data:
        raise ApiError("INVALID_JSON", "Request body must be JSON.", 400)
    return data or {}


def session_header() -> str | None:
    return request.headers.get("X-Session-Id")


def staff_user():
    u = current_user()
    if u:
        g.user = u
    return u


# ---------------------------------------------------------------- health

@bp.get("/health")
def health():
    return {"status": "ok", "time": iso()}


@bp.get("/ready")
def ready():
    db = get_db()
    schemes = db.execute("SELECT COUNT(*) FROM schemes").fetchone()[0]
    rules = db.execute("SELECT COUNT(*) FROM rules WHERE active=1").fetchone()[0]
    ok = schemes > 0 and rules > 0
    return jsonify({"ready": ok, "schemes": schemes, "rules": rules,
                    "bundle_version": current_app.config["RULE_BUNDLE_VERSION"],
                    "voice": voice.status(), "llm_extraction": llm.enabled()}), (200 if ok else 503)


# ---------------------------------------------------------------- auth

@bp.post("/auth/login")
def auth_login():
    b = body()
    return login(b.get("username", ""), b.get("password", ""))


@bp.get("/auth/me")
def auth_me():
    u = current_user()
    if not u:
        raise ApiError("UNAUTHENTICATED", "Not signed in.", 401)
    return {"user": {k: u[k] for k in ("user_id", "username", "role", "display_name")}}


# ---------------------------------------------------------------- sessions & conversation

@bp.post("/sessions")
def create_session():
    b = body()
    mode = b.get("mode", "personal")
    operator_id = None
    if mode == "kiosk":
        u = current_user()
        if not u or u["role"] not in ("operator", "admin"):
            raise ApiError("OPERATOR_REQUIRED", "Kiosk sessions are started by a signed-in kiosk operator.", 401)
        g.user = u
        operator_id = u["user_id"]
    s = profile.create_session(mode, b.get("language", "en"), device_id=b.get("device_id"), operator_id=operator_id)
    return {**{k: s[k] for k in ("session_id", "mode", "language", "workflow_state", "expires_at")},
            "greeting": i18n.t(i18n.MESSAGES, "greeting", s["language"])}, 201


@bp.get("/sessions/<sid>")
def read_session(sid):
    return profile.profile_view(sid)


@bp.patch("/sessions/<sid>")
def patch_session(sid):
    b = body()
    if "language" in b:
        profile.set_language(sid, b["language"])
    return profile.profile_view(sid)


@bp.post("/sessions/<sid>/end")
def end_session(sid):
    profile.end_session(sid)
    return {"ended": True}


@bp.post("/sessions/<sid>/turns")
def turn(sid):
    b = body()
    utterance = (b.get("utterance") or "").strip()
    channel = b.get("channel", "text")
    if channel not in ("text", "voice"):
        raise ApiError("INVALID_CHANNEL", "channel must be text or voice.", 422)
    llm_candidates = llm.extract(utterance) if llm.enabled() else None
    return profile.handle_turn(sid, utterance, channel=channel, language=b.get("language"),
                               llm_candidates=llm_candidates)


@bp.patch("/sessions/<sid>/profile/facts/<fact_id>")
def patch_fact(sid, fact_id):
    res = profile.patch_fact(sid, fact_id, body())
    return {**res, "profile": profile.profile_view(sid)}


@bp.post("/sessions/<sid>/profile/facts")
def add_fact(sid):
    """Typed entry from the profile card (citizen or operator); confirmed by the act of entering it."""
    b = body()
    profile.get_session(sid)
    res = profile.upsert_fact(sid, b.get("attribute"), b.get("value"), source=b.get("source", "text_form"),
                              raw_text="entered on profile card", confirmed=True)
    audit("profile.fact_entered", session_id=sid, details={"fact_id": res["fact"]["fact_id"], "attribute": b.get("attribute")})
    profile.refresh_workflow_state(sid)
    get_db().commit()
    return {**res, "profile": profile.profile_view(sid)}, 201


@bp.post("/sessions/<sid>/profile/confirm-all")
def confirm_all(sid):
    profile.confirm_all(sid)
    return profile.profile_view(sid)


@bp.post("/sessions/<sid>/voice/transcribe")
def transcribe(sid):
    s = profile.get_session(sid)
    f = request.files.get("audio")
    if not f:
        raise ApiError("AUDIO_REQUIRED", "Upload audio as multipart field 'audio'.", 422)
    data = f.read()
    if len(data) > 5 * 1024 * 1024:
        raise ApiError("AUDIO_TOO_LARGE", "Audio must be under 5 MB.", 413)
    return voice.transcribe(data, f.mimetype, request.form.get("language", s["language"]))


@bp.post("/sessions/<sid>/voice/speak")
def speak(sid):
    s = profile.get_session(sid)
    b = body()
    return voice.speak((b.get("text") or "")[:2000], b.get("language", s["language"]))


@bp.get("/voice/status")
def voice_status():
    return voice.status()


# ---------------------------------------------------------------- schemes & eligibility

@bp.post("/sessions/<sid>/schemes/search")
def session_search(sid):
    b = body()
    facts = profile.current_facts(sid)
    st = facts.get("state")
    state = st["value"] if st and st["confirmed"] else b.get("state")
    return catalogue.search(b.get("q", ""), state=state, level=b.get("level"), category=b.get("category"),
                            limit=min(int(b.get("limit", 20)), 50))


@bp.post("/sessions/<sid>/eligibility/evaluate")
def evaluate(sid):
    ev = catalogue.evaluate_session(sid)
    s = profile.get_session(sid)
    ev["voice_summary"] = voice.summarize(ev, s["language"], catalogue.doc_marks(sid))
    return ev


@bp.get("/sessions/<sid>/eligibility/latest")
def latest(sid):
    s = profile.get_session(sid)
    ev = catalogue.latest_evaluation(sid)
    if not ev:
        raise ApiError("NO_EVALUATION", "No screening has been run yet.", 404)
    ev["results"] = [catalogue.localize_result(r, s["language"]) for r in ev["results"]]
    ev["voice_summary"] = voice.summarize(ev, s["language"], catalogue.doc_marks(sid))
    return ev


@bp.get("/sessions/<sid>/documents")
def session_documents(sid):
    return catalogue.document_guide(sid)


@bp.put("/sessions/<sid>/documents/<doc_key>")
def mark_document(sid, doc_key):
    profile.get_session(sid)
    catalogue.set_doc_mark(sid, doc_key, body().get("status", ""))
    return catalogue.document_guide(sid)


@bp.get("/schemes")
def list_schemes():
    a = request.args
    return catalogue.search(a.get("q", ""), state=a.get("state") or None, level=a.get("level") or None,
                            category=a.get("category") or None, beneficiary=a.get("beneficiary") or None,
                            include_central=a.get("include_central", "1") == "1",
                            limit=min(int(a.get("limit", 30)), 100), offset=int(a.get("offset", 0)),
                            has_rule=a.get("has_rule") == "1")


@bp.get("/schemes/facets")
def scheme_facets():
    return catalogue.facets()


@bp.get("/schemes/<scheme_id>")
def read_scheme(scheme_id):
    return catalogue.get_scheme(scheme_id)


@bp.get("/schemes/<scheme_id>/documents")
def scheme_documents(scheme_id):
    lang = request.args.get("language", "en")
    s = catalogue.get_scheme(scheme_id)
    rule = next((c["rule"] for c in catalogue.active_rules() if c["rule"]["scheme_id"] == scheme_id), None)
    docs = [{"doc_key": d, "label": i18n.doc_label(d, lang)[0], "purpose": i18n.doc_label(d, lang)[1]}
            for d in (rule or {}).get("evidence_requirements", [])]
    return {"scheme_id": scheme_id, "structured": docs, "evidence_note": (rule or {}).get("evidence_note"),
            "dataset_documents_text": s["documents_text"]}


# ---------------------------------------------------------------- drafts & handoff

@bp.post("/sessions/<sid>/drafts")
def create_draft(sid):
    key = idempotency_key()
    scope = f"draft:{sid}"
    replay = idem_lookup(scope, key)
    if replay:
        return replay[0], replay[1]
    d = cases.save_draft(sid, body().get("scheme_id", ""))
    idem_store(scope, key, d, 201)
    get_db().commit()
    return d, 201


@bp.get("/drafts/<draft_id>")
def read_draft(draft_id):
    return cases.get_draft(draft_id, session_header(), staff=bool(staff_user()))


@bp.patch("/drafts/<draft_id>")
def edit_draft(draft_id):
    b = body()
    if_match = request.headers.get("If-Match") or b.get("version")
    if if_match is None:
        raise ApiError("VERSION_REQUIRED", "Send the draft version (If-Match header or body.version).", 428)
    return cases.patch_draft(draft_id, session_header(), int(if_match), b.get("fields") or {})


@bp.post("/drafts/<draft_id>/handoff")
def handoff(draft_id):
    key = idempotency_key()
    scope = f"handoff:{draft_id}"
    replay = idem_lookup(scope, key)
    if replay:
        return replay[0], replay[1]
    res = cases.handoff(draft_id, session_header(), body().get("consent") or {})
    idem_store(scope, key, res, 201)
    get_db().commit()
    return res, 201


@bp.post("/cases/status")
def case_status():
    return cases.public_status(body().get("code", ""))


# ---------------------------------------------------------------- reviewer

@bp.get("/reviewer/cases")
@require_role("reviewer", "admin")
def reviewer_queue():
    return {"cases": cases.list_cases(request.args.get("status") or None)}


@bp.post("/reviewer/cases/lookup")
@require_role("reviewer", "admin")
def reviewer_lookup():
    return cases.reviewer_lookup(body().get("code", ""))


@bp.get("/reviewer/cases/<case_id>")
@require_role("reviewer", "admin")
def reviewer_case(case_id):
    return cases.get_case(case_id)


@bp.post("/reviewer/cases/<case_id>/decision")
@require_role("reviewer", "admin")
def reviewer_decision(case_id):
    return cases.decide(case_id, body())


@bp.get("/cases/<case_id>/audit")
@require_role("reviewer", "admin")
def read_audit(case_id):
    return {"case_id": case_id, "events": cases.case_audit(case_id)}


# ---------------------------------------------------------------- sync

@bp.get("/sync/bundle")
def bundle():
    b = sync.build_bundle()
    resp = jsonify(b)
    resp.headers["ETag"] = b["checksum"]
    return resp


@bp.post("/sync/events")
def sync_events():
    b = body()
    return sync.ingest(b.get("device_id", ""), b.get("events") or [])


# ---------------------------------------------------------------- admin

@bp.get("/admin/schemes/freshness")
@require_role("admin", "reviewer")
def freshness():
    db = get_db()
    import json as _json
    artifacts = [dict(r) | {"report": _json.loads(r["report_json"])} for r in
                 db.execute("SELECT artifact_id, filename, sha256, row_count, imported_at, report_json FROM source_artifacts")]
    for a in artifacts:
        a.pop("report_json")
    rules = []
    for item in catalogue.active_rules():
        r, m = item["rule"], item["meta"]
        rules.append({"rule_id": r["rule_id"], "scheme_id": r["scheme_id"], "scheme_name": m["scheme_name"],
                      "version": r["version"], "jurisdiction": r["jurisdiction"], "review_status": m["review_status"],
                      "review_note": r.get("review_note"), "reviewed_at": m["reviewed_at"],
                      "source_verified_at": m["source_verified_at"], "source_verified_by": m["source_verified_by"],
                      "freshness_days": r.get("freshness_days"), "source_url": m["source_url"],
                      "criteria": len(r["all"]), "manual_checks": len(r.get("manual_checks", []))})
    return {"artifacts": artifacts, "rules": rules, "graph": catalogue.graph_summary(),
            "bundle_version": current_app.config["RULE_BUNDLE_VERSION"]}


@bp.post("/admin/rules/<rule_id>/verify")
@require_role("admin")
def verify_rule(rule_id):
    b = body()
    if not b.get("checked_source_url"):
        raise ApiError("SOURCE_REQUIRED", "Record which official source URL you checked.", 422)
    db = get_db()
    if not db.execute("SELECT 1 FROM rules WHERE rule_id=?", (rule_id,)).fetchone():
        raise ApiError("RULE_NOT_FOUND", "Rule not found.", 404)
    db.execute("UPDATE rules SET source_verified_at=?, source_verified_by=? WHERE rule_id=?",
               (iso(), g.user["username"], rule_id))
    audit("admin.rule_verified", details={"rule_id": rule_id, "checked_source_url": b["checked_source_url"],
                                          "note": (b.get("note") or "")[:500]})
    db.commit()
    return {"rule_id": rule_id, "source_verified_at": iso(), "source_verified_by": g.user["username"]}


@bp.post("/admin/schemes/import")
@require_role("admin")
def reimport():
    from . import ingest
    db = get_db()
    res = ingest.bootstrap(db, current_app.config["DATASET_CSV"], current_app.config["GOLDEN_RULES"],
                           current_app.config["RULE_BUNDLE_VERSION"])
    audit("admin.import", details={"artifact_id": res["catalogue"]["artifact_id"], "skipped": res["catalogue"]["skipped"]})
    db.commit()
    return res


# ---------------------------------------------------------------- test runner

@bp.get("/test-runs")
def test_runs():
    return testrunner.latest_runs()


@bp.post("/test-runs/<tc_id>")
def run_test(tc_id):
    return testrunner.run(tc_id.upper())


@bp.post("/test-runs/reset")
def reset_tests():
    return testrunner.reset()
