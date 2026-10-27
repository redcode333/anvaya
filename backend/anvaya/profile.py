"""Sessions, profile facts (stable IDs + provenance + confirmation) and conversation turns."""
import json
import secrets
from datetime import timedelta

from flask import current_app, g, request

from . import extraction, guardrails, i18n, llm, metrics
from .llm import merge as llm_merge
from .common import ApiError, audit
from .db import dumps, get_db, iso, iso_in, new_id, now, parse_iso

ATTR_SCHEMA = {
    "state": ("enum", set(extraction.STATES)),
    "district": ("str", 60),
    "age": ("int", (0, 120)),
    "annual_income": ("int", (0, 1_000_000_000)),
    "household_size": ("int", (1, 30)),
    "gender": ("enum", {"female", "male", "other"}),
    "marital_status": ("enum", {"married", "widowed", "single", "divorced"}),
    "area": ("enum", {"rural", "urban"}),
    "occupation": ("enum", {"farmer", "construction_worker", "weaver", "labourer", "student", "self_employed", "salaried", "homemaker", "other"}),
    "bpl": ("bool", None),
    "receives_other_pension": ("bool", None),
    "owns_cultivable_land": ("bool", None),
    "has_bank_account": ("bool", None),
    "owns_pucca_house": ("bool", None),
    "applicant_name": ("str", 80),
    "date_of_birth": ("date", None),  # only from an official source (DigiLocker), YYYY-MM-DD
}

# Order in which missing attributes are asked about (FR-03).
QUESTION_ORDER = ["state", "age", "annual_income", "household_size", "bpl", "area", "gender",
                  "marital_status", "occupation", "receives_other_pension", "owns_cultivable_land",
                  "has_bank_account", "owns_pucca_house"]

SESSION_MODES = {"personal", "kiosk"}


def validate_value(attr: str, value):
    if attr not in ATTR_SCHEMA:
        raise ApiError("UNKNOWN_ATTRIBUTE", f"Unknown profile attribute '{attr}'.", 422)
    kind, spec = ATTR_SCHEMA[attr]
    if kind == "int":
        try:
            v = int(value)
        except (TypeError, ValueError):
            raise ApiError("INVALID_VALUE", f"{attr} must be a whole number.", 422)
        if not spec[0] <= v <= spec[1]:
            raise ApiError("INVALID_VALUE", f"{attr} must be between {spec[0]} and {spec[1]}.", 422)
        return v
    if kind == "bool":
        if isinstance(value, bool):
            return value
        if str(value).lower() in ("true", "yes", "1"):
            return True
        if str(value).lower() in ("false", "no", "0"):
            return False
        raise ApiError("INVALID_VALUE", f"{attr} must be yes or no.", 422)
    if kind == "date":
        from datetime import date
        try:
            d = date.fromisoformat(str(value).strip()[:10])
        except ValueError:
            raise ApiError("INVALID_VALUE", f"{attr} must be a date (YYYY-MM-DD).", 422)
        if not date(1900, 1, 1) <= d <= date.today():
            raise ApiError("INVALID_VALUE", f"{attr} is out of range.", 422)
        return d.isoformat()
    if kind == "enum":
        match = next((s for s in spec if s.lower() == str(value).strip().lower()), None)
        if match is None:
            raise ApiError("INVALID_VALUE", f"{attr} has an unsupported value.", 422)
        return match
    v = str(value).strip()
    if not v or len(v) > spec:
        raise ApiError("INVALID_VALUE", f"{attr} must be 1–{spec} characters.", 422)
    return v


# ---------------------------------------------------------------- sessions

DEVICE_ID_CHARS = set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_")


def new_session_id() -> str:
    """128 random bits: a session id is never guessable. It travels only in the X-Session-Id header and the request
    body, never in a URL or a log line."""
    return f"SES_{secrets.token_hex(16)}"


def valid_device_id(device_id) -> bool:
    return isinstance(device_id, str) and 8 <= len(device_id) <= 64 and set(device_id) <= DEVICE_ID_CHARS


def kiosk_device() -> str | None:
    """The kiosk device id this request comes from (header set by the kiosk browser)."""
    return request.headers.get("X-Kiosk-Device") or None


def create_session(mode: str, language: str, device_id=None, operator_id=None, is_test=False, is_demo=False,
                   claims: dict | None = None, citizen_id: str | None = None, commit: bool = True,
                   synced: bool = False) -> dict:
    """A new session. `claims` = a signed-in citizen (Supabase user): the session is tied to that user and, if they saved
    their passports, starts from the saved profile. `citizen_id` = a Passport code holder resuming."""
    if mode not in SESSION_MODES:
        raise ApiError("INVALID_MODE", "mode must be personal or kiosk.", 422)
    if language not in i18n.SUPPORTED_LANGUAGES:
        raise ApiError("UNSUPPORTED_LANGUAGE", "Supported languages: en, hi, te.", 422)
    db = get_db()
    auth_user_id = None
    if claims and mode == "personal":
        from .accounts import queue_citizen
        citizen_id, auth_user_id = queue_citizen(claims), claims["sub"]
    if mode == "kiosk":
        # A kiosk session belongs to one device and one operator, and ends after KIOSK_MAX_SESSION_MINUTES at most.
        # (synced=True: rebuilt from a kiosk's offline outbox, which has no live operator session to bind to)
        if not synced and (not operator_id or not valid_device_id(device_id)):
            raise ApiError("KIOSK_DEVICE_REQUIRED", "A kiosk session needs the operator and the kiosk device id.", 422)
        expires = iso(now() + timedelta(minutes=current_app.config["KIOSK_MAX_SESSION_MINUTES"]))
    else:
        expires = iso_in(current_app.config["SESSION_TTL_HOURS"])
    s = {"session_id": new_session_id(), "mode": mode, "language": language, "workflow_state": "SESSION_ACTIVE",
         "device_id": device_id, "operator_id": operator_id, "is_test": int(is_test), "is_demo": int(is_demo),
         "created_at": iso(), "expires_at": expires, "ended_at": None,
         "citizen_id": citizen_id, "auth_user_id": auth_user_id}
    cols = ("session_id", "mode", "language", "workflow_state", "device_id", "operator_id", "is_test", "is_demo",
            "created_at", "expires_at", "citizen_id", "auth_user_id")
    db.execute(f"INSERT INTO sessions({', '.join(cols)}) VALUES ({','.join('?' * len(cols))})", tuple(s[k] for k in cols))
    audit("session.start", session_id=s["session_id"], details={"mode": mode, "language": language, "demo": bool(is_demo),
                                                                "account": bool(citizen_id)})
    if auth_user_id:
        from .accounts import apply_saved_profile
        s["account"] = apply_saved_profile(s, citizen_id)
    if commit:
        db.commit()
    return s


SESSION_SQL = "SELECT * FROM sessions WHERE session_id=?"
FACTS_SQL = "SELECT * FROM facts WHERE session_id=? ORDER BY captured_at, rowid"


def check_owner(s: dict) -> None:
    """A signed-in citizen's session is reachable only with that citizen's verified token (same user id after an
    anonymous account is linked to an email); a kiosk session only from its kiosk device (X-Kiosk-Device) with the
    token of the operator who started it."""
    if s.get("auth_user_id"):
        claims = g.get("auth")
        if not claims or claims.get("sub") != s["auth_user_id"]:
            raise ApiError("SESSION_FORBIDDEN", "This session belongs to another account.", 403)
    if s.get("mode") == "kiosk" and s.get("operator_id"):
        from .common import current_user
        user = current_user()
        if not user or user["user_id"] != s["operator_id"] or kiosk_device() != s.get("device_id"):
            raise ApiError("SESSION_FORBIDDEN", "This kiosk session belongs to another kiosk or operator.", 403)
        g.user = user


def _checked_session(row, allow_ended: bool, owner: bool = True) -> dict:
    if not row:
        raise ApiError("SESSION_NOT_FOUND", "Session not found.", 404)
    s = dict(row)
    if owner:
        check_owner(s)
    if not allow_ended and (s["ended_at"] or parse_iso(s["expires_at"]) < now()):
        raise ApiError("SESSION_EXPIRED", "This session has ended or expired.", 410)
    return s


def get_session(session_id: str, allow_ended=False) -> dict:
    return _checked_session(get_db().execute(SESSION_SQL, (session_id,)).fetchone(), allow_ended)


def load(session_id: str, allow_ended=False, extra=()) -> tuple[dict, "Facts", list]:
    """The session, its facts and any `extra` (sql, params) reads, in one database round trip."""
    res = get_db().query_many([(SESSION_SQL, (session_id,)), (FACTS_SQL, (session_id,)), *extra])
    session = _checked_session(res[0].fetchone(), allow_ended)
    return session, Facts(session_id, res[1].fetchall()), res[2:]


def set_language(session_id: str, language: str, session: dict | None = None, commit: bool = True) -> dict:
    if language not in i18n.SUPPORTED_LANGUAGES:
        raise ApiError("UNSUPPORTED_LANGUAGE", "Supported languages: en, hi, te.", 422)
    session = session or get_session(session_id)
    get_db().execute("UPDATE sessions SET language=? WHERE session_id=?", (language, session_id))
    audit("session.language", session_id=session_id, details={"language": language})
    if commit:
        get_db().commit()
    return {**session, "language": language}


def end_session(session_id: str, reason: str = "user", owner_checked: bool = False) -> None:
    """End a session (kiosk End session / idle timeout, or Start over). Data nobody consented to keep is deleted:
    a saved passport keeps its facts and versions, a consented hand-off keeps its case; utterances never stay."""
    db = get_db()
    session, case, saved, uploads = db.query_many([
        (SESSION_SQL, (session_id,)), ("SELECT 1 FROM cases WHERE session_id=?", (session_id,)),
        ("SELECT c.saved FROM citizens c JOIN sessions s ON s.citizen_id = c.citizen_id WHERE s.session_id=?",
         (session_id,)),
        ("SELECT upload_id, storage_path FROM document_uploads WHERE session_id=?", (session_id,))])
    _checked_session(session.fetchone(), allow_ended=True, owner=not owner_checked)
    has_case, row = case.fetchone(), saved.fetchone()
    is_saved = bool(row and row[0])
    removed_uploads = 0
    if not has_case and not is_saved:
        for table in ("facts", "turns", "doc_marks", "evaluations", "drafts", "passport_versions"):
            db.execute(f"DELETE FROM {table} WHERE session_id=?", (session_id,))
        from . import documents
        try:
            removed_uploads = documents.delete_uploads(db, [(r[0], r[1]) for r in uploads])
        except ApiError:
            pass  # Storage unreachable: the rows stay and the hourly retention run deletes the files later
    else:
        db.execute("DELETE FROM turns WHERE session_id=?", (session_id,))
    db.execute("UPDATE sessions SET ended_at=? WHERE session_id=?", (iso(), session_id))
    audit("session.end", session_id=session_id,
          details={"retained_case": bool(has_case), "saved_passport": is_saved, "reason": reason,
                   **({"uploads_deleted": removed_uploads} if removed_uploads else {})})
    db.commit()


def end_device_sessions(device_id: str, operator_id: str, reason: str = "operator_sign_out") -> int:
    """A kiosk operator signs out at the device: every citizen session still open on that device ends, whoever started
    it (shift change), with the same deletion as End session. Returns how many ended."""
    if not valid_device_id(device_id):
        raise ApiError("KIOSK_DEVICE_REQUIRED", "Send the kiosk device id (X-Kiosk-Device).", 422)
    rows = get_db().execute("SELECT session_id FROM sessions WHERE mode='kiosk' AND device_id=? AND ended_at IS NULL",
                            (device_id,)).fetchall()
    for r in rows:
        end_session(r[0], reason, owner_checked=True)
    ended = len(rows)
    audit("kiosk.device_signed_out", details={"sessions_ended": ended}, actor_id=operator_id)
    get_db().commit()
    return ended


# ---------------------------------------------------------------- facts

def _fact_row_to_public(r) -> dict:
    alternatives = json.loads(r["alternatives_json"]) if r["alternatives_json"] else None
    disputed = bool(alternatives) and not r["confirmed"]
    return {
        "fact_id": r["fact_id"], "attribute": r["attribute"], "value": json.loads(r["value_json"]),
        "raw_text": r["raw_text"], "source": r["source"], "confidence": r["confidence"],
        "confirmed": bool(r["confirmed"]), "inferred": bool(r["inferred"]), "note": r["note"],
        "captured_at": r["captured_at"], "confirmed_at": r["confirmed_at"],
        "high_impact": r["attribute"] in extraction.HIGH_IMPACT,
        "confusable": bool(r["confusable"]),
        # Read from an official source (DigiLocker), not from what was said or typed.
        "verified": bool(r["verified"]),
        # Two extractors heard different values: the citizen picks one of these (PATCH {value}); plain confirm is refused.
        "alternatives": alternatives,
        "disputed": disputed,
        # High-impact facts, confusable spoken numbers and disputed values are read back and confirmed one by one,
        # never in bulk.
        "confirm_individually": r["attribute"] in extraction.HIGH_IMPACT or bool(r["confusable"]) or disputed,
    }


class Facts:
    """A session's fact rows (history included) held in memory for one request: upserts update these rows and queue
    their INSERT/UPDATE, so a request reads the facts once instead of after every change."""

    COLUMNS = ("fact_id", "session_id", "attribute", "value_json", "raw_text", "source", "confidence", "confirmed",
               "inferred", "note", "captured_at", "confirmed_at", "confusable", "alternatives_json", "verified")

    def __init__(self, session_id: str, rows):
        self.session_id = session_id
        self.rows = [dict(r) for r in rows]

    def by_attribute(self) -> dict[str, dict]:
        return {r["attribute"]: r for r in self.rows if r["superseded_by"] is None}

    def get(self, fact_id: str) -> dict | None:
        return next((r for r in self.rows if r["fact_id"] == fact_id), None)

    def current(self) -> dict[str, dict]:
        return {a: _fact_row_to_public(r) for a, r in self.by_attribute().items()}

    def history(self) -> list[dict]:
        return [{**_fact_row_to_public(r), "superseded_by": r["superseded_by"]} for r in self.rows]

    def unconfirmed_critical(self) -> list[dict]:
        return [f for f in self.current().values() if f["confirm_individually"] and not f["confirmed"]]

    def confirm(self, row: dict) -> None:
        row.update(confirmed=1, confirmed_at=iso())
        get_db().execute("UPDATE facts SET confirmed=1, confirmed_at=? WHERE fact_id=?",
                         (row["confirmed_at"], row["fact_id"]))

    def insert(self, row: dict) -> None:
        self.rows.append({**row, "superseded_by": None})
        get_db().execute(f"INSERT INTO facts({', '.join(self.COLUMNS)}) VALUES ({','.join('?' * len(self.COLUMNS))})",
                         tuple(row[c] for c in self.COLUMNS))


def load_facts(session_id: str) -> Facts:
    return Facts(session_id, get_db().execute(FACTS_SQL, (session_id,)).fetchall())


def current_facts(session_id: str) -> dict[str, dict]:
    return load_facts(session_id).current()


def fact_history(session_id: str) -> list[dict]:
    return load_facts(session_id).history()


def upsert_fact(session_id, attribute, value, *, source, raw_text=None, confidence=1.0, inferred=False,
                note=None, confirmed=False, confusable=False, alternatives=None, verified=False,
                facts: Facts | None = None) -> dict:
    value = validate_value(attribute, value)
    alternatives = [validate_value(attribute, a) for a in alternatives] if alternatives else None
    facts = facts or load_facts(session_id)
    db = get_db()
    existing = facts.by_attribute().get(attribute)
    if existing and json.loads(existing["value_json"]) == value and (existing["verified"] or not verified):
        if confirmed and not existing["confirmed"]:
            facts.confirm(existing)
        elif alternatives and not existing["confirmed"]:
            existing.update(alternatives_json=dumps(alternatives), note=note)
            db.execute("UPDATE facts SET alternatives_json=?, note=? WHERE fact_id=?",
                       (existing["alternatives_json"], note, existing["fact_id"]))
            return {"fact": _fact_row_to_public(existing), "changed": True, "previous": None}
        return {"fact": _fact_row_to_public(existing), "changed": False, "previous": None}
    fact_id = f"F-{session_id[-6:]}-{len(facts.rows) + 1:03d}"
    ts = iso()
    row = {"fact_id": fact_id, "session_id": session_id, "attribute": attribute, "value_json": dumps(value),
           "raw_text": raw_text, "source": source, "confidence": confidence, "confirmed": int(confirmed),
           "inferred": int(inferred), "note": note, "captured_at": ts, "confirmed_at": ts if confirmed else None,
           "confusable": int(confusable), "alternatives_json": dumps(alternatives) if alternatives else None,
           "verified": int(verified)}
    facts.insert(row)
    previous = None
    if existing:
        existing["superseded_by"] = fact_id
        db.execute("UPDATE facts SET superseded_by=? WHERE fact_id=?", (fact_id, existing["fact_id"]))
        previous = {"fact_id": existing["fact_id"], "value": json.loads(existing["value_json"])}
    return {"fact": _fact_row_to_public(facts.get(fact_id)), "changed": True, "previous": previous}


def patch_fact(session_id: str, fact_id: str, body: dict, loaded: list | None = None) -> dict:
    """Confirm a fact as-is, or correct it (creates a new confirmed fact that supersedes it). Pass a list as `loaded`
    to receive the (session, Facts) this call ended with, for the profile view."""
    session, facts, _ = load(session_id)
    db = get_db()
    row = facts.get(fact_id)
    if not row:
        raise ApiError("FACT_NOT_FOUND", "Fact not found in this session.", 404)
    if row["superseded_by"]:
        raise ApiError("FACT_SUPERSEDED", "This fact was already replaced; reload the profile.", 409,
                       {"superseded_by": row["superseded_by"]})
    if "value" in body:
        res = upsert_fact(session_id, row["attribute"], body["value"], source=body.get("source", "citizen_correction"),
                          raw_text=body.get("raw_text"), confidence=1.0, confirmed=True, facts=facts)
        if res["changed"]:
            metrics.FACT_CORRECTIONS.labels(row["attribute"]).inc()
        audit("profile.fact_corrected", session_id=session_id,
              details={"fact_id": fact_id, "new_fact_id": res["fact"]["fact_id"], "attribute": row["attribute"]})
    elif body.get("confirmed") is True:
        if row["alternatives_json"] and not row["confirmed"]:
            raise ApiError("VALUE_DISPUTED", "Two different values were heard; choose one by sending {value: ...}.", 409,
                           {"alternatives": json.loads(row["alternatives_json"])})
        facts.confirm(row)
        res = {"fact": _fact_row_to_public(row), "changed": False, "previous": None}
        audit("profile.fact_confirmed", session_id=session_id, details={"fact_id": fact_id, "attribute": row["attribute"]})
    else:
        raise ApiError("INVALID_PATCH", "Send {confirmed: true} or {value: ...}.", 422)
    refresh_workflow_state(session_id, session, facts)
    db.commit()
    if loaded is not None:
        loaded[:] = [session, facts]
    return res


def confirm_all(session_id: str, loaded: list | None = None) -> dict:
    """Bulk-confirm low-impact facts only. High-impact facts (age, income, state, area, household size) and
    confusable spoken numbers stay pending until each one is read back and confirmed on its own."""
    session, facts, _ = load(session_id)
    db = get_db()
    pending = [f for f in facts.current().values() if not f["confirmed"]]
    bulk = [f["fact_id"] for f in pending if not f["confirm_individually"]]
    ts = iso()
    for fid in bulk:
        facts.get(fid).update(confirmed=1, confirmed_at=ts)
    db.executemany("UPDATE facts SET confirmed=1, confirmed_at=? WHERE fact_id=?", [(ts, fid) for fid in bulk])
    still = [f["fact_id"] for f in pending if f["confirm_individually"]]
    audit("profile.confirm_all", session_id=session_id, details={"confirmed": bulk, "needs_individual": still})
    refresh_workflow_state(session_id, session, facts)
    db.commit()
    if loaded is not None:
        loaded[:] = [session, facts]
    return {"confirmed": bulk, "needs_individual_confirmation": still}


def unconfirmed_critical(session_id: str) -> list[dict]:
    """Facts that block screening until confirmed one by one."""
    return load_facts(session_id).unconfirmed_critical()


def refresh_workflow_state(session_id: str, session: dict | None = None, facts: Facts | None = None) -> str:
    if session is None or facts is None:
        session, facts, _ = load(session_id, allow_ended=True)
    state = session["workflow_state"]
    if facts.unconfirmed_critical():
        new = "PROFILE_NEEDS_CONFIRMATION"
    elif state == "PROFILE_NEEDS_CONFIRMATION":
        new = "SESSION_ACTIVE"
    else:
        new = state
    if new != state:
        get_db().execute("UPDATE sessions SET workflow_state=? WHERE session_id=?", (new, session_id))
        session["workflow_state"] = new
    return new


def set_workflow_state(session_id: str, state: str) -> None:
    get_db().execute("UPDATE sessions SET workflow_state=? WHERE session_id=?", (state, session_id))


# ---------------------------------------------------------------- conversation

def next_question(session_id: str, lang: str, needed: set[str] | None = None, facts: dict | None = None) -> dict | None:
    facts = current_facts(session_id) if facts is None else facts
    for attr in QUESTION_ORDER:
        if attr in facts:
            continue  # never re-ask an attribute we already hold (confirmed or pending confirmation)
        if needed is not None and attr not in needed and attr not in extraction.HIGH_IMPACT:
            continue
        return {"attribute": attr, "text": i18n.t(i18n.QUESTIONS, attr, lang)}
    return None


def _llm_turn(session: dict, utterance: str, det_facts: list[dict], other_people: list[dict]) -> tuple[list[dict], dict]:
    """Deterministic facts merged with LLM facts when the LLM is enabled and allowed for this data; otherwise the
    deterministic facts unchanged. Returns (candidates, summary without any utterance text or values)."""
    if not llm.enabled():
        return det_facts, {"used": False, "result": "disabled"}
    if not llm.allowed(session, utterance):
        return det_facts, {"used": False, "result": "real_data_not_allowed"}
    with llm.tracing.turn(session["session_id"], llm.is_demo_data(session, utterance), utterance,
                          llm.prompt.version(), environment="tc-runner" if session.get("is_test") else None) as tr:
        return _traced_llm_turn(tr, utterance, det_facts, other_people)


def _traced_llm_turn(tr, utterance: str, det_facts: list[dict], other_people: list[dict]) -> tuple[list[dict], dict]:
    run = llm.run_turn(utterance, tr)
    for d in run["dropped"]:
        metrics.LLM_MERGE.labels("dropped_evidence" if d["reason"] == "evidence" else "dropped_invalid").inc()
    summary = {"used": run["result"] == "ok", "result": run["result"], "provider": run["provider"],
               "model": run["model"], "cached": run["cached"], "latency_ms": run["latency_ms"],
               "translated": run["translated"], "prompt_version": run["prompt_version"],
               "dropped": [d["reason"] for d in run["dropped"]]}
    if run["result"] != "ok":
        tr.finish(run, None)
        return det_facts, summary
    candidates, merged = llm_merge.merge(det_facts, run["facts"], other_people, utterance)
    tr.merge(merged["outcomes"], run["dropped"], candidates)
    tr.finish(run, candidates)
    for outcome in merged["outcomes"].values():
        metrics.LLM_MERGE.labels(outcome).inc()
    return candidates, {**summary, "merge": merged["outcomes"], "disputed": merged["disputed"]}


def _valid(attribute: str, value) -> bool:
    try:
        validate_value(attribute, value)
        return True
    except ApiError:
        return False


LAST_TURN_SQL = "SELECT extracted_json FROM turns WHERE session_id=? ORDER BY created_at DESC LIMIT 1"


def _turn_state(row) -> dict:
    """{"asked": attribute the bot's last reply asked about, "awaiting": fact ids it read back for a yes}."""
    try:
        data = json.loads(row["extracted_json"]) if row else {}
    except (TypeError, ValueError):
        return {}
    return {"asked": data.get("asked"), "awaiting": data.get("awaiting") or []}


def handle_turn(session_id: str, utterance: str, channel: str = "text", language: str | None = None,
                needed: set[str] | None = None) -> dict:
    session, facts, (last_turn,) = load(session_id, extra=[(LAST_TURN_SQL, (session_id,))])
    if language and language != session["language"]:
        session = set_language(session_id, language, session, commit=False)
    lang = session["language"]
    if not utterance or len(utterance) > 2000:
        raise ApiError("INVALID_UTTERANCE", "Utterance must be 1–2000 characters.", 422)

    # What the previous turn left open: the attribute the bot asked about (so a bare "नहीं" or "चार" has a meaning) and
    # the facts it read back and is waiting to hear "yes" for.
    prior = _turn_state(last_turn.fetchone())
    asked = prior.get("asked")
    awaiting = [fid for fid in prior.get("awaiting", [])
                if facts.get(fid) and not facts.get(fid)["confirmed"] and not facts.get(fid)["superseded_by"]]
    awaiting_attrs = {facts.get(fid)["attribute"] for fid in awaiting}
    spoken = channel == "voice"

    blocked = guardrails.screen(utterance)  # before extraction and before any LLM call
    pol = None if blocked else extraction.polarity(utterance)
    if blocked:
        result = {"facts": [], "other_people": [], "intents": [], "glossary": []}
        candidates, llm_summary = [], {"used": False, "result": "blocked", "provider": None, "cached": False}
    else:
        result = extraction.extract(utterance, asked=asked)
        candidates, llm_summary = _llm_turn(session, utterance, result["facts"], result["other_people"])
    held = facts.by_attribute()
    applied = []
    for cand in candidates:
        if cand.get("source") == "llm" and cand["attribute"] in held:
            continue  # an LLM-only reading never replaces a fact the profile already holds
        # High-impact facts, confusable spoken numbers and values the two extractors disagree on always need explicit
        # confirmation (spoken: one "yes" to the read-back). Plain answers such as yes/no to a direct question are
        # taken as heard; LLM-proposed facts always wait for confirmation.
        auto_confirm = not cand.get("high_impact") and not cand.get("inferred") \
            and not cand.get("confusable") and not cand.get("hold") and cand.get("source") != "llm"
        # Saying the value again while it is being read back confirms it.
        if cand["attribute"] in awaiting_attrs and pol is not False and not cand.get("confusable") \
                and held.get(cand["attribute"]) and json.loads(held[cand["attribute"]]["value_json"]) == cand["value"]:
            auto_confirm = True
        alternatives = cand.get("alternatives")
        if channel == "voice" and not alternatives:
            # Speech recognition confuses sound-alike numbers (साठ 60 / सात 7): offer them as one-tap choices.
            alternatives = [v for v in (extraction.sound_alike_values(cand) or [])
                            if _valid(cand["attribute"], v)] or None
            if alternatives and len(alternatives) < 2:
                alternatives = None
        try:
            res = upsert_fact(session_id, cand["attribute"], cand["value"],
                              source=cand.get("source") or channel, raw_text=cand.get("raw_text"),
                              confidence=cand.get("confidence", 0.9) * (0.85 if channel == "voice" else 1.0),
                              inferred=cand.get("inferred", False), note=cand.get("note"), confirmed=auto_confirm,
                              confusable=bool(cand.get("confusable")), alternatives=alternatives,
                              facts=facts)
        except ApiError:
            continue
        if res["changed"]:
            applied.append({**res["fact"], "previous": res["previous"]})

    # A spoken "yes" to the read-back confirms everything that was read out.
    said_yes = False
    if awaiting and pol is True:
        for fid in awaiting:
            row = facts.get(fid)
            if row and not row["confirmed"] and not row["superseded_by"]:
                facts.confirm(row)
                said_yes = True
        if said_yes:
            audit("profile.confirmed_by_voice", session_id=session_id, details={"fact_ids": awaiting})
    said_no = bool(awaiting) and pol is False and not applied

    wf = refresh_workflow_state(session_id, session, facts)
    parts = []
    guard = blocked
    settled = [f for f in applied if not f["disputed"]]
    # By voice only what still needs a "yes" is read back; facts taken as heard are not repeated.
    to_read = [f for f in settled if not f["confirmed"]] if spoken else settled

    def _read(fs: list[dict]) -> str:
        heard = ", ".join(
            f"{i18n.t(i18n.ATTRIBUTE_LABELS, f['attribute'], lang)}: {display_value(f['attribute'], f['value'], lang)}"
            for f in fs
        )
        return f"{i18n.t(i18n.MESSAGES, 'heard', lang)} {heard}."

    if to_read:
        parts.append(_read(to_read))
    elif not applied and not said_yes and not said_no:
        kind = blocked or (guardrails.no_details(utterance) if not result["other_people"] else "nothing_heard")
        guard = guard or (kind if kind != "nothing_heard" else None)
        parts.append(i18n.t(i18n.MESSAGES, "nothing_heard" if kind == "nothing_heard" else f"guard_{kind}", lang))
        if kind == "nothing_heard" and asked in extraction.BOOL_ATTRS:
            parts.append(i18n.t(i18n.MESSAGES, "answer_yes_no", lang))
    for f in applied:
        if f["disputed"]:
            a, b = (display_value(f["attribute"], v, lang) for v in f["alternatives"][:2])
            parts.append(i18n.t(i18n.MESSAGES, "disputed_value", lang,
                                label=i18n.t(i18n.ATTRIBUTE_LABELS, f["attribute"], lang), a=a, b=b))
    for f in applied:
        cand = next((c for c in candidates if c["attribute"] == f["attribute"]), {})
        if f["confusable"] and cand.get("heard_as"):
            parts.append(i18n.t(i18n.MESSAGES, "confusable_number", lang, value=display_value(f["attribute"], f["value"], lang),
                                words=cand["heard_as"], alt=" / ".join(cand["confusable_with"])))
    for o in result["other_people"]:
        parts.append(i18n.t(i18n.MESSAGES, "relative_age_ignored", lang, relation=o["relation"], age=o["value"]))
    q = next_question(session_id, lang, needed, facts.current())
    next_asked, next_awaiting = None, []
    if said_no:
        # "No" to the read-back: ask for the right value instead of moving on.
        attr = facts.get(awaiting[0])["attribute"]
        parts.append(i18n.t(i18n.MESSAGES, "correct_it", lang, label=i18n.t(i18n.ATTRIBUTE_LABELS, attr, lang)))
        next_asked = attr
    elif spoken:
        # Everything still unconfirmed and important is read back with one question, answered by one "yes".
        waiting = [f for f in facts.unconfirmed_critical() if not f["disputed"] and f["fact_id"] not in {x["fact_id"] for x in to_read}]
        if waiting and not to_read:
            parts.append(_read(waiting))
        if to_read or waiting:
            parts.append(i18n.t(i18n.MESSAGES, "confirm_question", lang))
            next_awaiting = [f["fact_id"] for f in to_read] + [f["fact_id"] for f in waiting]
        else:
            if said_yes:
                parts.insert(0, i18n.t(i18n.MESSAGES, "okay", lang))
            parts.append(q["text"] if q else i18n.t(i18n.MESSAGES, "ready", lang))
            next_asked = q["attribute"] if q else None
        disputed = next((f for f in applied if f["disputed"]), None)
        if disputed:
            next_asked = disputed["attribute"]
    else:
        if wf == "PROFILE_NEEDS_CONFIRMATION":
            parts.append(i18n.t(i18n.MESSAGES, "please_confirm", lang))
        if q:
            parts.append(q["text"])
        elif wf != "PROFILE_NEEDS_CONFIRMATION":
            parts.append(i18n.t(i18n.MESSAGES, "ready", lang))
        next_asked = q["attribute"] if q else None
    reply = " ".join(parts)

    db = get_db()
    db.execute(
        "INSERT INTO turns(turn_id, session_id, language, utterance, channel, extracted_json, reply, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (new_id("TRN"), session_id, lang, guardrails.placeholder(blocked) if blocked else utterance, channel,
         dumps({**result, "llm": llm_summary, "asked": next_asked, "awaiting": next_awaiting}), reply,
         now().isoformat()),  # microseconds: the next turn finds this one as the latest even within the same second
    )
    metrics.TURNS.labels(channel, lang).inc()
    for f in applied:
        metrics.FACTS_EXTRACTED.labels(f["attribute"]).inc()
    audit("conversation.turn", session_id=session_id,
          details={"channel": channel, "facts_extracted": [f["fact_id"] for f in applied], "guardrail": guard,
                   "llm": {k: llm_summary.get(k) for k in ("used", "result", "provider", "cached")}})
    db.commit()
    return {
        "reply": reply,
        "guardrail": guard,  # abuse | injection | sensitive | smalltalk | offtopic | None
        "reply_segments": parts,  # read aloud one by one: fixed sentences come from the prerendered audio cache
        "language": lang,
        "extracted": applied,
        "intents": result["intents"],
        "glossary": result["glossary"],
        "other_people": result["other_people"],
        "next_question": q,
        "workflow_state": wf,
        "needs_confirmation": [f["fact_id"] for f in facts.unconfirmed_critical()],
        "llm": llm_summary,
    }


AGE_UNIT = {"en": "years", "hi": "वर्ष", "te": "సంవత్సరాలు"}
AREA_LABELS = {"rural": {"en": "rural", "hi": "ग्रामीण", "te": "గ్రామీణ"}, "urban": {"en": "urban", "hi": "शहरी", "te": "పట్టణ"}}


def inr(n: int) -> str:
    """Indian digit grouping: 150000 → 1,50,000."""
    s = str(abs(int(n)))
    head, tail = s[:-3], s[-3:]
    while len(head) > 2:
        tail = f"{head[-2:]},{tail}"
        head = head[:-2]
    return ("-" if n < 0 else "") + (f"{head},{tail}" if head else tail)


def display_value(attr: str, value, lang: str) -> str:
    """Read-back form: numbers always in digits, so a misheard spoken number is easy to spot."""
    if isinstance(value, bool):
        return {"en": ("yes", "no"), "hi": ("हाँ", "नहीं"), "te": ("అవును", "కాదు")}[lang][0 if value else 1]
    if attr == "annual_income":
        return f"₹{inr(value)}"
    if attr == "age":
        return f"{value} {AGE_UNIT[lang]}"
    if attr == "area" and value in AREA_LABELS:
        return AREA_LABELS[value][lang]
    return str(value)


def profile_view(session_id: str, loaded: list | None = None) -> dict:
    """The profile card. `loaded` = [session, Facts] this request already holds, so they are not read again."""
    marks_sql = ("SELECT doc_key, status FROM doc_marks WHERE session_id=?", (session_id,))
    if loaded:
        (s, fact_set), marks_rows = loaded, get_db().execute(*marks_sql)
    else:
        s, fact_set, (marks_rows,) = load(session_id, allow_ended=True, extra=[marks_sql])
    facts = fact_set.current()
    for f in facts.values():
        f["readback"] = f"{i18n.t(i18n.ATTRIBUTE_LABELS, f['attribute'], s['language'])}: " \
                        f"{display_value(f['attribute'], f['value'], s['language'])}"
    marks = {r["doc_key"]: r["status"] for r in marks_rows}
    return {
        "session": {**{k: s[k] for k in ("session_id", "mode", "language", "workflow_state", "created_at", "expires_at",
                                         "ended_at")}, "linked_to_citizen": bool(s.get("citizen_id"))},
        "facts": list(facts.values()),
        "needs_confirmation": [f["fact_id"] for f in facts.values() if f["confirm_individually"] and not f["confirmed"]],
        "documents": marks,
    }
