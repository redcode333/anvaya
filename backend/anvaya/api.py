from functools import wraps

from flask import Blueprint, Response, current_app, g, jsonify, request

from . import (accounts, auth, cases, catalogue, digilocker, documents, formhelper, i18n, llm, migrations, profile, sync,
               testrunner, translation, voice)
from .common import ApiError, audit, current_user, idempotency_key, idempotent, rate_limit, require_role
from .db import bump, get_db, iso

bp = Blueprint("api", __name__, url_prefix="/api/v1")


@bp.url_value_preprocessor
def _session_from_header(endpoint, values):
    """/sessions/current/... takes the session id from the X-Session-Id header, so the id never appears in a URL (and
    so never in a proxy or server access log). The browser always uses this form."""
    if values and values.get("sid") == "current":
        sid = request.headers.get("X-Session-Id", "").strip()
        if not sid:
            raise ApiError("SESSION_REQUIRED", "Send the session id in the X-Session-Id header.", 400)
        values["sid"] = sid


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
    schemes = rules = 0
    database = {"backend": db.dialect, "status": "ok"}
    try:
        checks = [("SELECT COUNT(*) FROM schemes", ()), ("SELECT COUNT(*) FROM rules WHERE active=1", ())]
        if db.dialect == "postgres":
            checks.append((migrations.TABLES_WITHOUT_RLS, ()))
        res = db.query_many(checks)
        schemes, rules = res[0].fetchone()[0], res[1].fetchone()[0]
        if db.dialect == "postgres":
            # Every table must have Row Level Security on (no policies), so Supabase's REST API cannot reach it.
            database["rls"] = "ok" if res[2].fetchone()[0] == 0 else "error"
    except Exception as e:  # noqa: BLE001 - report, never raise; the error class only (no URL, no SQL)
        current_app.logger.warning("ready: database check failed (%s)", type(e).__name__)
        database["status"] = "error"
    ok = schemes > 0 and rules > 0 and database["status"] == "ok" and database.get("rls", "ok") == "ok"
    boot = current_app.extensions["anvaya.startup"]
    # Readiness depends on the database and catalogue only: every integration is optional and reported, never required.
    return jsonify({"ready": ok, "db": database, "schemes": schemes, "rules": rules,
                    "bundle_version": current_app.config["RULE_BUNDLE_VERSION"],
                    "integrations": {k: {"status": v["status"], "missing": v["missing"]}
                                     for k, v in boot["integrations"].items()},
                    "warnings": boot["warnings"],
                    "tts_cache": voice.cache_stats() if database["status"] == "ok" else None,
                    "voice": voice.status(),
                    "llm_extraction": llm.status() if database["status"] == "ok" else None}), (200 if ok else 503)


@bp.get("/auth/config")
def auth_config():
    """Public settings the browser needs for sign-in and the privacy notice (no secrets: the browser gets the
    publishable key from its own build environment)."""
    cfg = current_app.config
    return {"supabase_configured": bool(cfg["SUPABASE_URL"]), "google_enabled": cfg["GOOGLE_AUTH_ENABLED"],
            "kiosk_idle_seconds": cfg["KIOSK_IDLE_SECONDS"], "kiosk_warning_seconds": 30,
            "kiosk_max_session_minutes": cfg["KIOSK_MAX_SESSION_MINUTES"],
            "staff_mfa_required": cfg["STAFF_MFA_REQUIRED"], "phone_otp_enabled": cfg["PHONE_OTP_ENABLED"],
            "digilocker_enabled": digilocker.enabled(cfg),
            "retention": accounts.retention_policy()}


# ---------------------------------------------------------------- auth

@bp.get("/auth/me")
def auth_me():
    """Who the token belongs to. Staff at aal1 get mfa_required: true (and nothing else works until they verify)."""
    u = current_user(require_mfa=False)
    if u:
        need = u["aal"] != "aal2" and current_app.config["STAFF_MFA_REQUIRED"]
        return {"user": {k: u[k] for k in ("user_id", "username", "role", "display_name", "aal")}, "mfa_required": need}
    claims = auth.citizen_claims()
    if not claims:
        raise ApiError("UNAUTHENTICATED", "Not signed in.", 401)
    return {"citizen": {"user_id": claims["sub"], "is_anonymous": bool(claims.get("is_anonymous")),
                        "email": claims.get("email") or None, "phone": claims.get("phone") or None}}


# Events the browser reports after its own Supabase call (sign-in runs between the browser and Supabase, so the
# server cannot see it). With a token the actor is the verified user; without one (a failed sign-in) it is anonymous.
BROWSER_EVENTS = {"sign_in_success", "sign_in_failure", "otp_requested", "mfa_enrolled", "mfa_verified", "mfa_failed"}
EVENT_METHODS = {"anonymous", "email_otp", "password", "google", "phone_otp", "totp"}


@bp.post("/auth/events")
def auth_event():
    rate_limit("auth_events", current_app.config["AUTH_EVENT_LIMIT_PER_MIN"])
    b = body()
    event, method = b.get("event"), b.get("method")
    if event not in BROWSER_EVENTS or (method is not None and method not in EVENT_METHODS):
        raise ApiError("INVALID_EVENT", "Unknown auth event.", 422)
    claims = g.get("auth")
    role = auth.staff_role(claims) or ("citizen" if claims else "anonymous")
    auth.record(event, claims["sub"] if claims else None, role, {"method": method} if method else {})
    get_db().commit()
    return {"recorded": True}, 201


@bp.post("/auth/sign-out-all")
def sign_out_all():
    """Sign out of every device: Supabase revokes all refresh tokens, and this server refuses every token of a sign-in
    that started before now. reason=password_changed after a staff password change."""
    claims = g.get("auth")
    if not claims:
        raise ApiError("UNAUTHENTICATED", "Not signed in.", 401)
    reason = "password_changed" if body().get("reason") == "password_changed" else "user"
    role = auth.staff_role(claims) or "citizen"
    supabase_ok = auth.sign_out_everywhere(g.auth_token)
    auth.revoke_sessions(claims["sub"], reason)
    if reason == "password_changed":
        auth.record("password_changed", claims["sub"], role, {"global_sign_out": True})
    auth.record("global_sign_out", claims["sub"], role, {"reason": reason, "supabase": supabase_ok})
    get_db().commit()
    return {"signed_out": True, "supabase": supabase_ok}


@bp.post("/kiosk/sign-out")
def kiosk_sign_out():
    """The operator signs out at a kiosk: every citizen session on this device ends first."""
    u = current_user()
    if not u or u["role"] not in ("operator", "admin"):
        raise ApiError("OPERATOR_REQUIRED", "Only the kiosk operator can sign out the kiosk.", 401)
    g.user = u
    ended = profile.end_device_sessions(profile.kiosk_device() or "", u["user_id"])
    auth.record("kiosk_sign_out", u["user_id"], u["role"], {"sessions_ended": ended})
    get_db().commit()
    return {"sessions_ended": ended}


# ---------------------------------------------------------------- DigiLocker / Meri Pehchaan (off by default)

@bp.post("/auth/digilocker/start")
def digilocker_start():
    claims = accounts.require_account(allow_anonymous=True)
    return digilocker.start(claims, session_header())


@bp.post("/auth/digilocker/callback")
def digilocker_callback():
    claims = accounts.require_account(allow_anonymous=True)
    b = body()
    return digilocker.finish(claims, b.get("code") or "", b.get("state") or "")


# ---------------------------------------------------------------- citizen accounts

@bp.get("/account")
def account():
    return accounts.account_view(accounts.require_account(allow_anonymous=True))


@bp.post("/account/consent")
def account_consent():
    return accounts.give_consent(body())


@bp.get("/account/passports")
def account_passports():
    claims = accounts.require_account(allow_anonymous=True)
    return accounts.history(accounts.citizen_id_for(claims["sub"]))


@bp.get("/account/passports/changes")
def account_changes():
    claims = accounts.require_account(allow_anonymous=True)
    return accounts.what_changed(accounts.citizen_id_for(claims["sub"]), request.args.get("since"))


@bp.post("/account/attach-passport")
def account_attach():
    return accounts.attach_passport(body())


@bp.delete("/account")
def account_delete():
    """Delete = withdraw consent (DPDP Act 2023): the data goes, only consented hand-off cases stay with the reviewer."""
    claims = accounts.require_account(allow_anonymous=True)
    res = accounts.delete_account(claims, acknowledge_pending_case=body().get("acknowledge_pending_case") is True)
    auth.record("account_deleted", claims["sub"], "citizen", {k: res[k] for k in ("sessions_deleted", "cases_kept")})
    get_db().commit()
    return res


@bp.get("/account/export")
def account_export():
    """"Download my data": the signed-in citizen's own data as JSON."""
    claims = accounts.require_account(allow_anonymous=True)
    return _export(accounts.citizen_id_for(claims["sub"]), claims["sub"])


@bp.get("/sessions/<sid>/export")
def session_export(sid):
    """The same for a Passport-code holder (through the session they resumed) or an unsaved session's own data."""
    session = profile.get_session(sid, allow_ended=False)
    if session.get("citizen_id"):
        return _export(session["citizen_id"], session.get("auth_user_id"))
    return _export(None, None, session_id=sid)


def _export(citizen_id, actor_id, session_id=None):
    data = accounts.export_data(citizen_id, session_id=session_id)
    counts = {k: len(v) for k, v in data.items() if isinstance(v, list)}
    auth.record("data_export", actor_id or citizen_id or "citizen", "citizen", counts)
    get_db().commit()
    resp = jsonify(data)
    resp.headers["Content-Disposition"] = 'attachment; filename="anvaya-my-data.json"'
    resp.headers["Cache-Control"] = "no-store"
    return resp


@bp.post("/sessions/<sid>/passport-code")
def passport_code(sid):
    return accounts.create_passport_code(sid, body()), 201


@bp.post("/passport/resume")
def passport_resume():
    """Passport code + PIN → a new session from the saved profile. At a kiosk the operator's token makes it a kiosk
    session; a personal device needs no account."""
    rate_limit("passport_resume", current_app.config["SESSION_CREATE_LIMIT_PER_MIN"])
    u = current_user()
    operator_id = None
    if u and u["role"] in ("operator", "admin"):
        g.user, operator_id = u, u["user_id"]
    return accounts.resume(body(), operator_id, device_id=profile.kiosk_device()), 201


@bp.get("/sessions/<sid>/passports")
def session_passports(sid):
    return accounts.history(accounts.session_citizen(sid))


@bp.get("/sessions/<sid>/passports/changes")
def session_changes(sid):
    return accounts.what_changed(accounts.session_citizen(sid), request.args.get("since"))


# ---------------------------------------------------------------- sessions & conversation

@bp.post("/sessions")
def create_session():
    rate_limit("session_create", current_app.config["SESSION_CREATE_LIMIT_PER_MIN"])
    b = body()
    mode = b.get("mode", "personal")
    operator_id = None
    device_id = b.get("device_id")
    if mode == "kiosk":
        u = current_user()
        if not u or u["role"] not in ("operator", "admin"):
            raise ApiError("OPERATOR_REQUIRED", "Kiosk sessions are started by a signed-in kiosk operator.", 401)
        g.user = u
        operator_id = u["user_id"]
        device_id = profile.kiosk_device()  # the session is bound to the device that sends this header
    # "demo": true marks demo data, which (unlike real citizen data) may be sent to free-tier LLM providers.
    # A signed-in citizen (anonymous or linked) owns a personal session; kiosks never keep anything (no account).
    s = profile.create_session(mode, b.get("language", "en"), device_id=device_id, operator_id=operator_id,
                               is_demo=b.get("demo") is True, claims=auth.citizen_claims() if mode == "personal" else None)
    return {**{k: s[k] for k in ("session_id", "mode", "language", "workflow_state", "expires_at")},
            "demo": bool(s["is_demo"]), "account": s.get("account"),
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
    reason = body().get("reason")
    profile.end_session(sid, reason if reason in ("user", "idle") else "user")
    return {"ended": True}


@bp.post("/sessions/<sid>/turns")
def turn(sid):
    b = body()
    utterance = (b.get("utterance") or "").strip()
    channel = b.get("channel", "text")
    if channel not in ("text", "voice"):
        raise ApiError("INVALID_CHANNEL", "channel must be text or voice.", 422)
    return profile.handle_turn(sid, utterance, channel=channel, language=b.get("language"))


@bp.patch("/sessions/<sid>/profile/facts/<fact_id>")
def patch_fact(sid, fact_id):
    loaded = []
    res = profile.patch_fact(sid, fact_id, body(), loaded)
    return {**res, "profile": profile.profile_view(sid, loaded)}


@bp.post("/sessions/<sid>/profile/facts")
def add_fact(sid):
    """Typed entry from the profile card (citizen or operator); confirmed by the act of entering it."""
    b = body()
    session, facts, _ = profile.load(sid)
    res = profile.upsert_fact(sid, b.get("attribute"), b.get("value"), source=b.get("source", "text_form"),
                              raw_text="entered on profile card", confirmed=True, facts=facts)
    audit("profile.fact_entered", session_id=sid, details={"fact_id": res["fact"]["fact_id"], "attribute": b.get("attribute")})
    profile.refresh_workflow_state(sid, session, facts)
    get_db().commit()
    return {**res, "profile": profile.profile_view(sid, [session, facts])}, 201


@bp.post("/sessions/<sid>/profile/confirm-all")
def confirm_all(sid):
    loaded = []
    res = profile.confirm_all(sid, loaded)
    return {**profile.profile_view(sid, loaded), **res}


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


@bp.post("/sessions/<sid>/translate")
def translate(sid):
    """Machine translation (VerbX, cached) — always labelled machine_translated; never used for eligibility."""
    s = profile.get_session(sid)
    b = body()
    return translation.translate_text(b.get("text") or "", b.get("source_lang", "en"), b.get("target_lang", s["language"]))


def with_summary(ev: dict, sid: str, lang: str, marks: dict | None = None) -> dict:
    names = translation.localize_scheme_names(ev, lang)
    marks = catalogue.doc_marks(sid) if marks is None else marks
    ev["voice_summary_segments"] = voice.summary_parts(ev, lang, marks, names)
    ev["voice_summary"] = " ".join(ev["voice_summary_segments"])
    ev["voice_summary_machine_translated"] = any(
        r["scheme_name_machine_translated"] for r in ev["results"] if r["outcome"] in ("MATCH", "PROVISIONAL"))
    return ev


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
    loaded = {}
    ev = catalogue.evaluate_session(sid, loaded=loaded)
    return with_summary(ev, sid, loaded["session"]["language"], loaded["marks"])


@bp.get("/sessions/<sid>/eligibility/latest")
def latest(sid):
    s = profile.get_session(sid)
    ev = catalogue.latest_evaluation(sid)
    if not ev:
        raise ApiError("NO_EVALUATION", "No screening has been run yet.", 404)
    ev["results"] = [catalogue.localize_result(r, s["language"]) for r in ev["results"]]
    return with_summary(ev, sid, s["language"])


@bp.get("/sessions/<sid>/documents")
def session_documents(sid):
    return catalogue.document_guide(sid)


@bp.put("/sessions/<sid>/documents/<doc_key>")
def mark_document(sid, doc_key):
    profile.get_session(sid)
    catalogue.set_doc_mark(sid, doc_key, body().get("status", ""))
    return catalogue.document_guide(sid)


@bp.post("/sessions/<sid>/documents/<doc_key>/upload-url")
def document_upload_url(sid, doc_key):
    return documents.create_upload_url(sid, doc_key, body()), 201


@bp.put("/uploads/<token>")
def document_upload(token):
    """The signed upload URL: the file body goes through this backend (type + size checked) into private Storage."""
    return documents.receive_upload(token, request.stream)


@bp.get("/sessions/<sid>/documents/<doc_key>/view-url")
def document_view_url(sid, doc_key):
    return documents.create_view_url(sid, doc_key)


@bp.get("/uploads/view/<token>")
def document_view(token):
    return documents.serve_view(token)


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
    scheme_id = body().get("scheme_id", "")
    return idempotent(f"draft:{sid}", idempotency_key(), lambda: (cases.save_draft(sid, scheme_id), 201))


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


def _helper_for(draft_id):
    row, staff = formhelper.load(draft_id, session_header())
    lang = request.args.get("language") or row["session_language"]
    code = formhelper._case_code(row, request.headers.get("X-Case-Code"))
    return row, staff, formhelper.helper(row, lang, code)


@bp.get("/drafts/<draft_id>/helper")
def draft_helper(draft_id):
    """Form Helper: copy-ready fields, application steps, official link + QR. Nothing is submitted anywhere."""
    return _helper_for(draft_id)[2]


@bp.get("/drafts/<draft_id>/pdf")
def draft_pdf(draft_id):
    """The draft as a PDF (en / hi / te) with a 'not submitted' watermark. Owner, or a reviewer / admin with a case."""
    row, staff, h = _helper_for(draft_id)
    data = formhelper.render_pdf(h)
    formhelper.record_download(row, h["language"], staff)
    return Response(data, mimetype="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="anvaya-draft-{row["draft_id"]}-{h["language"]}.pdf"',
        "Cache-Control": "no-store"})


@bp.get("/schemes/<scheme_id>/portal-qr.svg")
def portal_qr(scheme_id):
    return Response(formhelper.portal_qr_svg(scheme_id), mimetype="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=86400"})


@bp.post("/drafts/<draft_id>/handoff")
def handoff(draft_id):
    consent = body().get("consent") or {}
    return idempotent(f"handoff:{draft_id}", idempotency_key(),
                      lambda: (cases.handoff(draft_id, session_header(), consent), 201))


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


@bp.post("/reviewer/cases/<case_id>/documents/<doc_key>")
@require_role("reviewer", "admin")
def reviewer_document(case_id, doc_key):
    return documents.review_document(case_id, doc_key, body().get("action", ""))


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
    bump(db, "catalogue")
    audit("admin.rule_verified", details={"rule_id": rule_id, "checked_source_url": b["checked_source_url"],
                                          "note": (b.get("note") or "")[:500]})
    db.commit()
    return {"rule_id": rule_id, "source_verified_at": iso(), "source_verified_by": g.user["username"]}


@bp.get("/admin/staff")
@require_role("admin")
def admin_staff():
    return {"staff": auth.staff_accounts()}


@bp.post("/admin/staff/<user_id>/reset-mfa")
@require_role("admin")
def admin_reset_mfa(user_id):
    """Remove a staff member's authenticator (lost phone): they enrol a new one at their next sign-in. Their current
    sessions are signed out. Audited (who, whom, how many factors) without any secret."""
    target = auth.get_user(user_id)
    role = auth.staff_role({"app_metadata": (target or {}).get("app_metadata")})
    if not target or not role:
        raise ApiError("STAFF_NOT_FOUND", "No staff account with this id.", 404)
    removed = auth.delete_factors(user_id)
    auth.revoke_sessions(user_id, "mfa_reset")
    auth.record("mfa_reset", g.user["user_id"], "admin", {"user_id": user_id, "role": role, "factors_removed": removed})
    audit("admin.mfa_reset", details={"user_id": user_id, "factors_removed": removed})
    get_db().commit()
    return {"user_id": user_id, "factors_removed": removed}


@bp.get("/admin/auth-events")
@require_role("admin")
def admin_auth_events():
    return {"events": auth.recent_events(500)}


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

def admin_unless_demo(fn):
    """Scenario runs write test sessions and reset wipes them: admin only, unless ANVAYA_DEMO_TEST_RUNS=on."""
    guarded = require_role("admin")(fn)

    @wraps(fn)
    def wrapper(*a, **kw):
        return fn(*a, **kw) if current_app.config["DEMO_TEST_RUNS"] else guarded(*a, **kw)
    return wrapper


@bp.get("/test-runs")
def test_runs():
    return {**testrunner.latest_runs(), "demo_mode": current_app.config["DEMO_TEST_RUNS"]}


@bp.post("/test-runs/<tc_id>")
@admin_unless_demo
def run_test(tc_id):
    return testrunner.run(tc_id.upper())


@bp.post("/test-runs/reset")
@admin_unless_demo
def reset_tests():
    return testrunner.reset()
