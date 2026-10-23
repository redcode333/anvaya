"""Sessions, profile facts (stable IDs + provenance + confirmation) and conversation turns."""
import json

from flask import current_app

from . import extraction, i18n, llm, metrics
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

def create_session(mode: str, language: str, device_id=None, operator_id=None, is_test=False, is_demo=False) -> dict:
    if mode not in SESSION_MODES:
        raise ApiError("INVALID_MODE", "mode must be personal or kiosk.", 422)
    if language not in i18n.SUPPORTED_LANGUAGES:
        raise ApiError("UNSUPPORTED_LANGUAGE", "Supported languages: en, hi, te.", 422)
    sid = new_id("SES")
    db = get_db()
    db.execute(
        """INSERT INTO sessions(session_id, mode, language, workflow_state, device_id, operator_id, is_test,
           is_demo, created_at, expires_at) VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (sid, mode, language, "SESSION_ACTIVE", device_id, operator_id, int(is_test), int(is_demo), iso(),
         iso_in(current_app.config["SESSION_TTL_HOURS"])),
    )
    audit("session.start", session_id=sid, details={"mode": mode, "language": language, "demo": bool(is_demo)})
    db.commit()
    return get_session(sid)


def get_session(session_id: str, allow_ended=False) -> dict:
    row = get_db().execute("SELECT * FROM sessions WHERE session_id=?", (session_id,)).fetchone()
    if not row:
        raise ApiError("SESSION_NOT_FOUND", "Session not found.", 404)
    s = dict(row)
    if not allow_ended and (s["ended_at"] or parse_iso(s["expires_at"]) < now()):
        raise ApiError("SESSION_EXPIRED", "This session has ended or expired.", 410)
    return s


def set_language(session_id: str, language: str) -> dict:
    if language not in i18n.SUPPORTED_LANGUAGES:
        raise ApiError("UNSUPPORTED_LANGUAGE", "Supported languages: en, hi, te.", 422)
    get_session(session_id)
    get_db().execute("UPDATE sessions SET language=? WHERE session_id=?", (language, session_id))
    audit("session.language", session_id=session_id, details={"language": language})
    get_db().commit()
    return get_session(session_id)


def end_session(session_id: str) -> None:
    """Kiosk exit: unconsented facts are deleted; consented case data is retained."""
    db = get_db()
    get_session(session_id, allow_ended=True)
    has_case = db.execute("SELECT 1 FROM cases WHERE session_id=?", (session_id,)).fetchone()
    if not has_case:
        db.execute("DELETE FROM facts WHERE session_id=?", (session_id,))
        db.execute("DELETE FROM turns WHERE session_id=?", (session_id,))
        db.execute("DELETE FROM doc_marks WHERE session_id=?", (session_id,))
        db.execute("DELETE FROM evaluations WHERE session_id=?", (session_id,))
        db.execute("DELETE FROM drafts WHERE session_id=?", (session_id,))
    else:
        db.execute("DELETE FROM turns WHERE session_id=?", (session_id,))
    db.execute("UPDATE sessions SET ended_at=? WHERE session_id=?", (iso(), session_id))
    audit("session.end", session_id=session_id, details={"retained_case": bool(has_case)})
    db.commit()


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
        # Two extractors heard different values: the citizen picks one of these (PATCH {value}); plain confirm is refused.
        "alternatives": alternatives,
        "disputed": disputed,
        # High-impact facts, confusable spoken numbers and disputed values are read back and confirmed one by one,
        # never in bulk.
        "confirm_individually": r["attribute"] in extraction.HIGH_IMPACT or bool(r["confusable"]) or disputed,
    }


def current_facts(session_id: str) -> dict[str, dict]:
    rows = get_db().execute(
        "SELECT * FROM facts WHERE session_id=? AND superseded_by IS NULL ORDER BY captured_at", (session_id,)
    ).fetchall()
    return {r["attribute"]: _fact_row_to_public(r) for r in rows}


def fact_history(session_id: str) -> list[dict]:
    rows = get_db().execute("SELECT * FROM facts WHERE session_id=? ORDER BY captured_at, rowid", (session_id,)).fetchall()
    out = []
    for r in rows:
        d = _fact_row_to_public(r)
        d["superseded_by"] = r["superseded_by"]
        out.append(d)
    return out


def upsert_fact(session_id, attribute, value, *, source, raw_text=None, confidence=1.0, inferred=False,
                note=None, confirmed=False, confusable=False, alternatives=None) -> dict:
    value = validate_value(attribute, value)
    alternatives = [validate_value(attribute, a) for a in alternatives] if alternatives else None
    db = get_db()
    existing = db.execute(
        "SELECT * FROM facts WHERE session_id=? AND attribute=? AND superseded_by IS NULL", (session_id, attribute)
    ).fetchone()
    if existing and json.loads(existing["value_json"]) == value:
        if confirmed and not existing["confirmed"]:
            db.execute("UPDATE facts SET confirmed=1, confirmed_at=? WHERE fact_id=?", (iso(), existing["fact_id"]))
        elif alternatives and not existing["confirmed"]:
            db.execute("UPDATE facts SET alternatives_json=?, note=? WHERE fact_id=?",
                       (dumps(alternatives), note, existing["fact_id"]))
            return {"fact": _fact_row_to_public(db.execute("SELECT * FROM facts WHERE fact_id=?", (existing["fact_id"],)).fetchone()),
                    "changed": True, "previous": None}
        return {"fact": _fact_row_to_public(db.execute("SELECT * FROM facts WHERE fact_id=?", (existing["fact_id"],)).fetchone()),
                "changed": False, "previous": None}
    seq = db.execute("SELECT COUNT(*) FROM facts WHERE session_id=?", (session_id,)).fetchone()[0] + 1
    fact_id = f"F-{session_id[-6:]}-{seq:03d}"
    db.execute(
        """INSERT INTO facts(fact_id, session_id, attribute, value_json, raw_text, source, confidence, confirmed,
           inferred, note, captured_at, confirmed_at, confusable, alternatives_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (fact_id, session_id, attribute, dumps(value), raw_text, source, confidence, int(confirmed), int(inferred),
         note, iso(), iso() if confirmed else None, int(confusable), dumps(alternatives) if alternatives else None),
    )
    previous = None
    if existing:
        db.execute("UPDATE facts SET superseded_by=? WHERE fact_id=?", (fact_id, existing["fact_id"]))
        previous = {"fact_id": existing["fact_id"], "value": json.loads(existing["value_json"])}
    fact = _fact_row_to_public(db.execute("SELECT * FROM facts WHERE fact_id=?", (fact_id,)).fetchone())
    return {"fact": fact, "changed": True, "previous": previous}


def patch_fact(session_id: str, fact_id: str, body: dict) -> dict:
    """Confirm a fact as-is, or correct it (creates a new confirmed fact that supersedes it)."""
    get_session(session_id)
    db = get_db()
    row = db.execute("SELECT * FROM facts WHERE fact_id=? AND session_id=?", (fact_id, session_id)).fetchone()
    if not row:
        raise ApiError("FACT_NOT_FOUND", "Fact not found in this session.", 404)
    if row["superseded_by"]:
        raise ApiError("FACT_SUPERSEDED", "This fact was already replaced; reload the profile.", 409,
                       {"superseded_by": row["superseded_by"]})
    if "value" in body:
        res = upsert_fact(session_id, row["attribute"], body["value"], source=body.get("source", "citizen_correction"),
                          raw_text=body.get("raw_text"), confidence=1.0, confirmed=True)
        if res["changed"]:
            metrics.FACT_CORRECTIONS.labels(row["attribute"]).inc()
        audit("profile.fact_corrected", session_id=session_id,
              details={"fact_id": fact_id, "new_fact_id": res["fact"]["fact_id"], "attribute": row["attribute"]})
    elif body.get("confirmed") is True:
        if row["alternatives_json"] and not row["confirmed"]:
            raise ApiError("VALUE_DISPUTED", "Two different values were heard; choose one by sending {value: ...}.", 409,
                           {"alternatives": json.loads(row["alternatives_json"])})
        db.execute("UPDATE facts SET confirmed=1, confirmed_at=? WHERE fact_id=?", (iso(), fact_id))
        res = {"fact": _fact_row_to_public(db.execute("SELECT * FROM facts WHERE fact_id=?", (fact_id,)).fetchone()),
               "changed": False, "previous": None}
        audit("profile.fact_confirmed", session_id=session_id, details={"fact_id": fact_id, "attribute": row["attribute"]})
    else:
        raise ApiError("INVALID_PATCH", "Send {confirmed: true} or {value: ...}.", 422)
    refresh_workflow_state(session_id)
    db.commit()
    return res


def confirm_all(session_id: str) -> dict:
    """Bulk-confirm low-impact facts only. High-impact facts (age, income, state, area, household size) and
    confusable spoken numbers stay pending until each one is read back and confirmed on its own."""
    get_session(session_id)
    db = get_db()
    pending = [f for f in current_facts(session_id).values() if not f["confirmed"]]
    bulk = [f["fact_id"] for f in pending if not f["confirm_individually"]]
    db.executemany("UPDATE facts SET confirmed=1, confirmed_at=? WHERE fact_id=?", [(iso(), fid) for fid in bulk])
    still = [f["fact_id"] for f in pending if f["confirm_individually"]]
    audit("profile.confirm_all", session_id=session_id, details={"confirmed": bulk, "needs_individual": still})
    refresh_workflow_state(session_id)
    db.commit()
    return {"confirmed": bulk, "needs_individual_confirmation": still}


def unconfirmed_critical(session_id: str) -> list[dict]:
    """Facts that block screening until confirmed one by one."""
    return [f for f in current_facts(session_id).values() if f["confirm_individually"] and not f["confirmed"]]


def refresh_workflow_state(session_id: str) -> str:
    db = get_db()
    state = db.execute("SELECT workflow_state FROM sessions WHERE session_id=?", (session_id,)).fetchone()[0]
    if unconfirmed_critical(session_id):
        new = "PROFILE_NEEDS_CONFIRMATION"
    elif state == "PROFILE_NEEDS_CONFIRMATION":
        new = "SESSION_ACTIVE"
    else:
        new = state
    if new != state:
        db.execute("UPDATE sessions SET workflow_state=? WHERE session_id=?", (new, session_id))
    return new


def set_workflow_state(session_id: str, state: str) -> None:
    get_db().execute("UPDATE sessions SET workflow_state=? WHERE session_id=?", (state, session_id))


# ---------------------------------------------------------------- conversation

def next_question(session_id: str, lang: str, needed: set[str] | None = None) -> dict | None:
    facts = current_facts(session_id)
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
    run = llm.run_turn(utterance)
    for d in run["dropped"]:
        metrics.LLM_MERGE.labels("dropped_evidence" if d["reason"] == "evidence" else "dropped_invalid").inc()
    summary = {"used": run["result"] == "ok", "result": run["result"], "provider": run["provider"],
               "model": run["model"], "cached": run["cached"], "latency_ms": run["latency_ms"],
               "translated": run["translated"], "prompt_version": run["prompt_version"],
               "dropped": [d["reason"] for d in run["dropped"]]}
    if run["result"] != "ok":
        return det_facts, summary
    candidates, merged = llm_merge.merge(det_facts, run["facts"], other_people, utterance)
    for outcome in merged["outcomes"].values():
        metrics.LLM_MERGE.labels(outcome).inc()
    return candidates, {**summary, "merge": merged["outcomes"], "disputed": merged["disputed"]}


def handle_turn(session_id: str, utterance: str, channel: str = "text", language: str | None = None,
                needed: set[str] | None = None) -> dict:
    session = get_session(session_id)
    if language and language != session["language"]:
        session = set_language(session_id, language)
    lang = session["language"]
    if not utterance or len(utterance) > 2000:
        raise ApiError("INVALID_UTTERANCE", "Utterance must be 1–2000 characters.", 422)

    result = extraction.extract(utterance)
    candidates, llm_summary = _llm_turn(session, utterance, result["facts"], result["other_people"])
    held = current_facts(session_id)
    applied = []
    for cand in candidates:
        if cand.get("source") == "llm" and cand["attribute"] in held:
            continue  # an LLM-only reading never replaces a fact the profile already holds
        # High-impact facts, confusable spoken numbers and values the two extractors disagree on always need explicit
        # confirmation; voice-derived and LLM-proposed facts all do.
        auto_confirm = channel == "text" and not cand.get("high_impact") and not cand.get("inferred") \
            and not cand.get("confusable") and not cand.get("hold") and cand.get("source") != "llm"
        try:
            res = upsert_fact(session_id, cand["attribute"], cand["value"],
                              source=cand.get("source") or channel, raw_text=cand.get("raw_text"),
                              confidence=cand.get("confidence", 0.9) * (0.85 if channel == "voice" else 1.0),
                              inferred=cand.get("inferred", False), note=cand.get("note"), confirmed=auto_confirm,
                              confusable=bool(cand.get("confusable")), alternatives=cand.get("alternatives"))
        except ApiError:
            continue
        if res["changed"]:
            applied.append({**res["fact"], "previous": res["previous"]})

    wf = refresh_workflow_state(session_id)
    parts = []
    settled = [f for f in applied if not f["disputed"]]
    if settled:
        heard = ", ".join(
            f"{i18n.t(i18n.ATTRIBUTE_LABELS, f['attribute'], lang)}: {display_value(f['attribute'], f['value'], lang)}"
            for f in settled
        )
        parts.append(f"{i18n.t(i18n.MESSAGES, 'heard', lang)} {heard}.")
    elif not applied:
        parts.append(i18n.t(i18n.MESSAGES, "nothing_heard", lang))
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
    q = next_question(session_id, lang, needed)
    if wf == "PROFILE_NEEDS_CONFIRMATION":
        parts.append(i18n.t(i18n.MESSAGES, "please_confirm", lang))
    if q:
        parts.append(q["text"])
    elif wf != "PROFILE_NEEDS_CONFIRMATION":
        parts.append(i18n.t(i18n.MESSAGES, "ready", lang))
    reply = " ".join(parts)

    db = get_db()
    db.execute(
        "INSERT INTO turns(turn_id, session_id, language, utterance, channel, extracted_json, reply, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (new_id("TRN"), session_id, lang, utterance, channel, dumps({**result, "llm": llm_summary}), reply, iso()),
    )
    metrics.TURNS.labels(channel, lang).inc()
    for f in applied:
        metrics.FACTS_EXTRACTED.labels(f["attribute"]).inc()
    audit("conversation.turn", session_id=session_id,
          details={"channel": channel, "facts_extracted": [f["fact_id"] for f in applied],
                   "llm": {k: llm_summary.get(k) for k in ("used", "result", "provider", "cached")}})
    db.commit()
    return {
        "reply": reply,
        "reply_segments": parts,  # read aloud one by one: fixed sentences come from the prerendered audio cache
        "language": lang,
        "extracted": applied,
        "intents": result["intents"],
        "glossary": result["glossary"],
        "other_people": result["other_people"],
        "next_question": q,
        "workflow_state": wf,
        "needs_confirmation": [f["fact_id"] for f in unconfirmed_critical(session_id)],
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


def profile_view(session_id: str) -> dict:
    s = get_session(session_id, allow_ended=True)
    facts = current_facts(session_id)
    for f in facts.values():
        f["readback"] = f"{i18n.t(i18n.ATTRIBUTE_LABELS, f['attribute'], s['language'])}: " \
                        f"{display_value(f['attribute'], f['value'], s['language'])}"
    marks = {r["doc_key"]: r["status"] for r in get_db().execute(
        "SELECT doc_key, status FROM doc_marks WHERE session_id=?", (session_id,))}
    return {
        "session": {k: s[k] for k in ("session_id", "mode", "language", "workflow_state", "created_at", "expires_at", "ended_at")},
        "facts": list(facts.values()),
        "needs_confirmation": [f["fact_id"] for f in facts.values() if f["confirm_individually"] and not f["confirmed"]],
        "documents": marks,
    }
