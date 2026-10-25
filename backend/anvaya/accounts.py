"""Citizen accounts and saved Scheme Passports.

A citizen is a Supabase Auth user (anonymous at first; citizen_id = "CIT_" + auth user id) and/or the holder of a
Passport code + PIN. Nothing is kept beyond the session until the citizen consents (text version + time recorded) and
the passport is tied to something they can come back with: a verified email / Google identity, or a code + PIN.

- Every screening of a citizen's session is stored as a passport version: rule versions, fact ids (with the values
  compared, so "what changed" can name the fact), document marks and outcomes.
- A new session of a saved citizen starts from the saved profile; age / income confirmed more than 90 days ago come
  back unconfirmed and block screening until confirmed again.
- Passport codes are PSP-XXXX-XXXX (8 Crockford base32 characters = 40 random bits), stored as sha256(pepper + code);
  PINs are 4 digits, argon2-hashed, weak PINs refused. Failed attempts are limited per code and per IP, and a code is
  locked for an hour after 10 failures; a wrong code and a wrong PIN get the same answer.
- Deleting an account removes facts, passport versions and sessions (and the Supabase Auth user); only cases the
  citizen consented to hand to a reviewer are kept. Audit events record counts, never values.
"""
import json
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from flask import current_app, request

from . import auth, i18n, metrics, profile
from .common import ApiError, audit, sha256
from .db import dumps, get_db, iso, new_id, now, parse_iso

CODE_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"  # Crockford base32: no I, L, O, U; 32 symbols = 5 bits each
DEV_PEPPER = "anvaya-dev-pepper-not-secret"
ATTEMPT_WINDOW = timedelta(minutes=15)
MAX_FAILURES_PER_WINDOW = 5
LOCK_AFTER_FAILURES = 10
LOCK_FOR = timedelta(hours=1)
STALE_ATTRIBUTES = ("age", "annual_income")
WRONG = ("PASSPORT_CODE_OR_PIN_WRONG", "The Passport code or PIN is not correct.", 401)
TOO_MANY = ("TOO_MANY_ATTEMPTS", "Too many attempts. Please wait and try again later.", 429)

_ph = PasswordHasher()
_DUMMY_HASH = _ph.hash("0000-dummy")

CITIZEN_SQL = "SELECT * FROM citizens WHERE citizen_id=?"
# The saved profile: current facts of the citizen's most recent other session that has any.
PROFILE_SQL = """SELECT * FROM facts WHERE superseded_by IS NULL AND session_id = (
    SELECT s.session_id FROM sessions s WHERE s.citizen_id=? AND s.session_id<>?
      AND EXISTS (SELECT 1 FROM facts f WHERE f.session_id = s.session_id)
    ORDER BY s.created_at DESC, s.session_id DESC LIMIT 1) ORDER BY captured_at, rowid"""
VERSIONS_SQL = "SELECT * FROM passport_versions WHERE citizen_id=? ORDER BY created_at, rowid"


def citizen_id_for(auth_user_id: str) -> str:
    return f"CIT_{auth_user_id}"


def pepper() -> str:
    return current_app.config["PASSPORT_PEPPER"] or DEV_PEPPER


# ---------------------------------------------------------------- codes and PINs

def new_passport_code() -> str:
    raw = "".join(secrets.choice(CODE_ALPHABET) for _ in range(8))
    return f"PSP-{raw[:4]}-{raw[4:]}"


def normalize_code(code: str) -> str:
    c = "".join(ch for ch in (code or "").upper() if ch.isalnum())
    if c.startswith("PSP"):
        c = c[3:]
    c = c.translate(str.maketrans({"O": "0", "I": "1", "L": "1"}))  # Crockford: read-alikes
    return f"PSP-{c[:4]}-{c[4:8]}" if len(c) == 8 else ""


def code_hash(code: str) -> str:
    return sha256(pepper() + normalize_code(code))


def spoken_code(code: str, lang: str) -> str:
    """The code read aloud character by character, in two groups."""
    _, a, b = code.split("-")
    return f"{i18n.t(i18n.MESSAGES, 'passport_code_is', lang)} {' '.join(a)} — {' '.join(b)}."


def pin_problem(pin) -> str | None:
    """None for an acceptable PIN, otherwise why it is refused."""
    if not isinstance(pin, str) or len(pin) != 4 or not pin.isdigit():
        return "PIN must be exactly 4 digits."
    d = [int(c) for c in pin]
    steps = {d[i + 1] - d[i] for i in range(3)}
    weak = (len(set(d)) == 1 or steps in ({1}, {-1})          # 1111, 1234, 4321
            or (d[0] == d[2] and d[1] == d[3])                 # 1212
            or (d[0] == d[1] and d[2] == d[3])                 # 1122
            or pin in {"1004", "2580", "0852", "6969", "1010", "0007", "1230"}
            or 1900 <= int(pin) <= 2029)                       # years
    return "This PIN is too easy to guess. Choose another." if weak else None


# ---------------------------------------------------------------- citizens

def queue_citizen(claims: dict, is_test: bool = False) -> str:
    """Make sure the auth user has a citizen row (queued: no extra round trip) and mark it active."""
    cid, ts = citizen_id_for(claims["sub"]), iso()
    db = get_db()
    db.execute("INSERT INTO citizens(citizen_id, auth_user_id, is_anonymous, is_test, created_at, last_active_at)"
               " VALUES (?,?,?,?,?,?) ON CONFLICT DO NOTHING",
               (cid, claims["sub"], int(bool(claims.get("is_anonymous"))), int(is_test), ts, ts))
    db.execute("UPDATE citizens SET is_anonymous=?, last_active_at=? WHERE citizen_id=?",
               (int(bool(claims.get("is_anonymous"))), ts, cid))
    return cid


def _stale(row) -> bool:
    days = current_app.config["STALE_FACT_DAYS"]
    at = parse_iso(row["confirmed_at"]) if row["confirmed_at"] else None
    return row["attribute"] in STALE_ATTRIBUTES and bool(at) and at < now() - timedelta(days=days)


def apply_saved_profile(session: dict, citizen_id: str) -> dict:
    """Start a new session from the citizen's saved profile (only when they consented to saving). Facts keep their
    original confirmation time; saved age / income older than STALE_FACT_DAYS come back unconfirmed."""
    db = get_db()
    sid = session["session_id"]
    cit, rows = db.query_many([(CITIZEN_SQL, (citizen_id,)), (PROFILE_SQL, (citizen_id, sid))])
    cit = cit.fetchone()
    if not cit or not cit["saved"]:
        return {"saved": False, "restored": [], "reconfirm": []}
    facts = profile.Facts(sid, [])
    restored, reconfirm = [], []
    for r in rows:
        stale = _stale(r)
        row = {c: r[c] for c in profile.Facts.COLUMNS}
        row.update(fact_id=f"F-{sid[-6:]}-{len(facts.rows) + 1:03d}", session_id=sid, source="saved_profile")
        if stale:
            row.update(confirmed=0, confirmed_at=None,
                       note=f"Saved more than {current_app.config['STALE_FACT_DAYS']} days ago — confirm it again.")
            reconfirm.append(row["fact_id"])
        facts.insert(row)
        restored.append(row["fact_id"])
    profile.refresh_workflow_state(sid, session, facts)
    audit("account.profile_restored", session_id=sid, details={"facts": restored, "reconfirm": reconfirm})
    return {"saved": True, "restored": restored, "reconfirm": reconfirm}


def record_version(session: dict, eval_id: str, bundle_version: str, facts: dict, marks: dict, results: list) -> None:
    """Queued with the evaluation's own writes: no extra round trip."""
    outcomes = [{"scheme_id": r["scheme_id"], "scheme_name": r["scheme_name"], "rule_id": r["rule_id"],
                 "rule_version": r["rule_version"], "outcome": r["outcome"],
                 "facts": sorted({c["fact"] for c in r["criteria"]}),
                 "documents": sorted(e["doc_key"] for e in r["evidence"])} for r in results]
    snapshot = {"facts": {a: {"fact_id": f["fact_id"], "value": f["value"], "confirmed": f["confirmed"]}
                          for a, f in facts.items()}, "documents": marks}
    db = get_db()
    db.execute("INSERT INTO passport_versions(version_id, citizen_id, session_id, eval_id, bundle_version, created_at,"
               " facts_json, outcomes_json) VALUES (?,?,?,?,?,?,?,?)",
               # microseconds: two screenings in the same second still order correctly for "what changed"
               (new_id("PSV"), session["citizen_id"], session["session_id"], eval_id, bundle_version,
                now().isoformat(timespec="microseconds"),
                dumps(snapshot), dumps(outcomes)))
    db.execute("UPDATE citizens SET last_active_at=? WHERE citizen_id=?", (iso(), session["citizen_id"]))


def _record_latest(session: dict, citizen_id: str, facts: "profile.Facts") -> None:
    """A session saved after it was screened: its latest screening becomes the first passport version."""
    ev = session.get("latest_eval")
    if not ev:
        return
    by_id = {r["fact_id"]: r for r in facts.rows}
    used = {by_id[f]["attribute"]: {"fact_id": f, "value": json.loads(by_id[f]["value_json"]),
                                    "confirmed": bool(by_id[f]["confirmed"])}
            for f in json.loads(ev["fact_ids_json"]) if f in by_id}
    marks = {r["doc_key"]: r["status"] for r in get_db().execute(
        "SELECT doc_key, status FROM doc_marks WHERE session_id=?", (session["session_id"],))}
    record_version({**session, "citizen_id": citizen_id}, ev["eval_id"], ev["bundle_version"], used, marks,
                   json.loads(ev["results_json"]))


# ---------------------------------------------------------------- consent and Passport codes

def _consent(body: dict, channel: str) -> dict:
    version = current_app.config["CONSENT_VERSION"]
    c = body.get("consent") if isinstance(body.get("consent"), dict) else body
    if c.get("accepted") is not True or c.get("version") != version:
        raise ApiError("CONSENT_REQUIRED", "Agree to the current saving terms before anything is kept.", 422,
                       {"consent_version": version})
    lang = c.get("language") if c.get("language") in i18n.SUPPORTED_LANGUAGES else "en"
    return {"version": version, "accepted": True, "language": lang, "channel": channel, "consented_at": iso()}


def require_account(allow_anonymous: bool = False) -> dict:
    claims = auth.citizen_claims()
    if not claims:
        raise ApiError("ACCOUNT_REQUIRED", "Sign in as a citizen (staff accounts and kiosks cannot save passports).", 401)
    if claims.get("is_anonymous") and not allow_anonymous:
        raise ApiError("LINK_REQUIRED", "Verify your email first, then save your passports.", 409)
    return claims


def give_consent(body: dict) -> dict:
    claims = require_account()
    cid = queue_citizen(claims)
    consent = _consent(body, "account")
    get_db().execute("UPDATE citizens SET saved=1, consent_json=? WHERE citizen_id=?", (dumps(consent), cid))
    audit("account.consent", details={"citizen_id": cid, "version": consent["version"]})
    get_db().commit()
    return {"citizen_id": cid, "saved": True, "consent": consent}


def create_passport_code(session_id: str, body: dict) -> dict:
    """Save a session's passport behind a Passport code + PIN (the only way to save from a kiosk)."""
    session, facts, (ev_row,) = profile.load(session_id, extra=[(
        "SELECT * FROM evaluations WHERE session_id=? ORDER BY created_at DESC, rowid DESC LIMIT 1", (session_id,))])
    session["latest_eval"] = ev_row.fetchone()
    problem = pin_problem(body.get("pin"))
    if problem:
        raise ApiError("WEAK_PIN" if "guess" in problem else "INVALID_PIN", problem, 422)
    consent = _consent(body, "passport_code")
    db = get_db()
    cid = session.get("citizen_id")
    if cid:
        row = db.execute("SELECT code_hash FROM citizens WHERE citizen_id=?", (cid,)).fetchone()
        if row and row["code_hash"]:
            raise ApiError("PASSPORT_CODE_EXISTS", "This passport already has a Passport code.", 409)
    else:
        cid = new_id("CIT")
    code, ts = new_passport_code(), iso()
    db.execute("""INSERT INTO citizens(citizen_id, code_hash, pin_hash, saved, consent_json, is_test, created_at,
                  last_active_at) VALUES (?,?,?,1,?,?,?,?)
                  ON CONFLICT (citizen_id) DO UPDATE SET code_hash=excluded.code_hash, pin_hash=excluded.pin_hash,
                  saved=1, consent_json=excluded.consent_json, last_active_at=excluded.last_active_at""",
               (cid, code_hash(code), _ph.hash(body["pin"]), dumps(consent), session["is_test"], ts, ts))
    db.execute("UPDATE sessions SET citizen_id=? WHERE session_id=?", (cid, session_id))
    if not session.get("citizen_id"):
        _record_latest(session, cid, facts)
    metrics.AUTH.labels("passport_code_created").inc()
    audit("passport.code_created", session_id=session_id, details={"citizen_id": cid, "version": consent["version"]})
    db.commit()
    lang = session["language"]
    return {"code": code, "spoken": spoken_code(code, lang), "citizen_id": cid,
            "retention_days": current_app.config["PASSPORT_RETENTION_DAYS"],
            "notice": i18n.t(i18n.MESSAGES, "passport_code_notice", lang)}


def _check_code(code: str, pin) -> dict:
    """The citizen row for a code + PIN, or the same error for a wrong code or a wrong PIN. Limits: at most
    MAX_FAILURES_PER_WINDOW failed attempts per code and per IP in ATTEMPT_WINDOW; LOCK_AFTER_FAILURES failures lock the
    code for LOCK_FOR."""
    db = get_db()
    h = code_hash(code)
    ip = sha256(pepper() + (request.remote_addr or "unknown"))
    since = iso(now() - ATTEMPT_WINDOW)
    by_code, by_ip, row = db.query_many([
        ("SELECT COUNT(*) FROM passport_attempts WHERE code_hash=? AND ok=0 AND ts>?", (h, since)),
        ("SELECT COUNT(*) FROM passport_attempts WHERE ip_hash=? AND ok=0 AND ts>?", (ip, since)),
        ("SELECT * FROM citizens WHERE code_hash=?", (h,))])
    row = row.fetchone()
    locked = row and row["locked_until"] and parse_iso(row["locked_until"]) > now()
    if by_code.fetchone()[0] >= MAX_FAILURES_PER_WINDOW or by_ip.fetchone()[0] >= MAX_FAILURES_PER_WINDOW or locked:
        metrics.RATE_LIMITED.labels("passport_code").inc()
        audit("passport.rate_limited", details={"locked": bool(locked)}, actor_id="anonymous", actor_role="anonymous")
        db.commit()
        raise ApiError(*TOO_MANY)
    ok = False
    try:
        ok = _ph.verify(row["pin_hash"] if row and row["pin_hash"] else _DUMMY_HASH, str(pin or "")) and bool(row)
    except (VerificationError, InvalidHashError):
        ok = False
    db.execute("INSERT INTO passport_attempts(code_hash, ip_hash, ok, ts) VALUES (?,?,?,?)", (h, ip, int(ok), iso()))
    if not ok:
        if row:
            failures = row["failed_attempts"] + 1
            lock = iso(now() + LOCK_FOR) if failures >= LOCK_AFTER_FAILURES else None
            db.execute("UPDATE citizens SET failed_attempts=?, locked_until=? WHERE citizen_id=?",
                       (0 if lock else failures, lock, row["citizen_id"]))
        metrics.AUTH.labels("passport_code_failed").inc()
        audit("passport.resume_failed", actor_id="anonymous", actor_role="anonymous")
        db.commit()
        raise ApiError(*WRONG)
    db.execute("UPDATE citizens SET failed_attempts=0, locked_until=NULL, last_active_at=? WHERE citizen_id=?",
               (iso(), row["citizen_id"]))
    return dict(row)


def resume(body: dict, operator_id: str | None) -> dict:
    """Code + PIN → a new session starting from the saved profile."""
    citizen = _check_code(body.get("code", ""), body.get("pin"))
    mode = "kiosk" if operator_id else "personal"
    s = profile.create_session(mode, body.get("language", "en"), operator_id=operator_id, citizen_id=citizen["citizen_id"],
                               is_test=bool(citizen["is_test"]), commit=False)
    restored = apply_saved_profile(s, citizen["citizen_id"])
    last = get_db().execute("SELECT MAX(created_at) FROM passport_versions WHERE citizen_id=?",
                            (citizen["citizen_id"],)).fetchone()[0]
    metrics.AUTH.labels("passport_code_resumed").inc()
    audit("passport.resumed", session_id=s["session_id"], details={"citizen_id": citizen["citizen_id"]})
    get_db().commit()
    return {"session_id": s["session_id"], "mode": mode, "language": s["language"], "expires_at": s["expires_at"],
            "workflow_state": s["workflow_state"], "restored": restored, "last_passport_at": last}


def attach_passport(body: dict) -> dict:
    """A code holder who later creates an account moves the code's passports into it (the code keeps working)."""
    claims = require_account()
    target = citizen_id_for(claims["sub"])
    source = _check_code(body.get("code", ""), body.get("pin"))
    db = get_db()
    if source["citizen_id"] == target:
        db.commit()
        return {"citizen_id": target, "attached": False, "already": True}
    if source["auth_user_id"]:
        db.commit()
        raise ApiError("PASSPORT_ALREADY_ATTACHED", "This passport already belongs to an account.", 409)
    queue_citizen(claims)
    db.execute("UPDATE sessions SET citizen_id=? WHERE citizen_id=?", (target, source["citizen_id"]))
    db.execute("UPDATE passport_versions SET citizen_id=? WHERE citizen_id=?", (target, source["citizen_id"]))
    db.execute("DELETE FROM citizens WHERE citizen_id=?", (source["citizen_id"],))
    db.execute("UPDATE citizens SET code_hash=?, pin_hash=?, saved=1, consent_json=COALESCE(consent_json, ?)"
               " WHERE citizen_id=?", (source["code_hash"], source["pin_hash"], source["consent_json"], target))
    audit("passport.attached", details={"citizen_id": target, "from": source["citizen_id"]})
    db.commit()
    return {"citizen_id": target, "attached": True}


# ---------------------------------------------------------------- history and what changed

def _require_saved(citizen) -> dict:
    if not citizen:
        raise ApiError("NO_SAVED_PASSPORTS", "No saved passports yet.", 404)
    if not citizen["saved"]:
        raise ApiError("CONSENT_REQUIRED", "Passports are kept only after you agree to save them.", 403,
                       {"consent_version": current_app.config["CONSENT_VERSION"]})
    return dict(citizen)


def _version_public(v) -> dict:
    outcomes = json.loads(v["outcomes_json"])
    snap = json.loads(v["facts_json"])
    counts: dict[str, int] = {}
    for o in outcomes:
        counts[o["outcome"]] = counts.get(o["outcome"], 0) + 1
    return {"version_id": v["version_id"], "created_at": v["created_at"], "session_id": v["session_id"],
            "eval_id": v["eval_id"], "bundle_version": v["bundle_version"],
            "rule_versions": {o["rule_id"]: o["rule_version"] for o in outcomes},
            "fact_ids": sorted(f["fact_id"] for f in snap["facts"].values()),
            "counts": counts, "outcomes": [{k: o[k] for k in ("scheme_id", "scheme_name", "rule_id", "rule_version",
                                                              "outcome")} for o in outcomes]}


def account_view(claims: dict) -> dict:
    cid = citizen_id_for(claims["sub"])
    queue_citizen(claims)
    db = get_db()
    cit, rows, count = db.query_many([(CITIZEN_SQL, (cid,)), (PROFILE_SQL, (cid, "")),
                                      ("SELECT COUNT(*) FROM passport_versions WHERE citizen_id=?", (cid,))])
    cit = cit.fetchone()
    db.commit()
    saved = bool(cit and cit["saved"])
    consent = json.loads(cit["consent_json"]) if cit and cit["consent_json"] else None
    return {"citizen_id": cid, "is_anonymous": bool(claims.get("is_anonymous")), "email": claims.get("email") or None,
            "saved": saved, "consent": consent, "has_passport_code": bool(cit and cit["code_hash"]),
            "passport_count": count.fetchone()[0] if saved else 0,
            "profile": [{"fact_id": r["fact_id"], "attribute": r["attribute"], "value": json.loads(r["value_json"]),
                         "confirmed_at": r["confirmed_at"], "needs_reconfirmation": _stale(r)}
                        for r in rows] if saved else [],
            "retention": retention_policy()}


def history(citizen_id: str) -> dict:
    cit, versions = get_db().query_many([(CITIZEN_SQL, (citizen_id,)), (VERSIONS_SQL, (citizen_id,))])
    _require_saved(cit.fetchone())
    return {"citizen_id": citizen_id, "versions": [_version_public(v) for v in reversed(versions.fetchall())]}


def what_changed(citizen_id: str, since: str | None) -> dict:
    """Outcome before → after for every scheme whose outcome differs between the passport as it was at `since` (the
    last version at or before it; the first version if none) and the latest one, each with its reason: a fact the rule
    reads changed, the rule's version changed, or a document mark changed."""
    cit, versions = get_db().query_many([(CITIZEN_SQL, (citizen_id,)), (VERSIONS_SQL, (citizen_id,))])
    _require_saved(cit.fetchone())
    versions = versions.fetchall()
    if not versions:
        return {"since": since, "before": None, "after": None, "changes": []}
    if since and "T" in since:
        since = since.strip().replace(" ", "+")  # an unencoded "+" in a query string arrives as a space
    try:
        cutoff = parse_iso(since) if since else None
    except ValueError:
        raise ApiError("INVALID_DATE", "since must be an ISO date, e.g. 2026-10-01.", 422)
    if cutoff and cutoff.tzinfo is None:
        cutoff = cutoff.replace(tzinfo=now().tzinfo)
    earlier = [v for v in versions if cutoff and parse_iso(v["created_at"]) <= cutoff]
    before, after = (earlier[-1] if earlier else versions[0]), versions[-1]
    b_out = {o["scheme_id"]: o for o in json.loads(before["outcomes_json"])}
    a_out = {o["scheme_id"]: o for o in json.loads(after["outcomes_json"])}
    b_snap, a_snap = json.loads(before["facts_json"]), json.loads(after["facts_json"])
    changes = []
    for sid in sorted(set(b_out) | set(a_out)):
        o, n = b_out.get(sid), a_out.get(sid)
        if (o and o["outcome"]) == (n and n["outcome"]):
            continue
        reasons = []
        if o and n and o["rule_version"] != n["rule_version"]:
            reasons.append({"kind": "rule_changed", "rule_id": n["rule_id"], "before": o["rule_version"],
                            "after": n["rule_version"]})
        for attr in sorted(set((o or {}).get("facts", [])) | set((n or {}).get("facts", [])) | {"state"}):
            bf, af = b_snap["facts"].get(attr), a_snap["facts"].get(attr)
            if (bf and (bf["value"], bf["confirmed"])) != (af and (af["value"], af["confirmed"])):
                reasons.append({"kind": "fact_changed", "attribute": attr,
                                "before": bf and bf["value"], "after": af and af["value"],
                                "fact_before": bf and bf["fact_id"], "fact_after": af and af["fact_id"]})
        for doc in sorted(set((o or {}).get("documents", [])) | set((n or {}).get("documents", []))):
            if b_snap["documents"].get(doc) != a_snap["documents"].get(doc):
                reasons.append({"kind": "document_changed", "doc_key": doc, "before": b_snap["documents"].get(doc),
                                "after": a_snap["documents"].get(doc)})
        changes.append({"scheme_id": sid, "scheme_name": (n or o)["scheme_name"], "rule_id": (n or o)["rule_id"],
                        "before": o and o["outcome"], "after": n and n["outcome"], "reasons": reasons})
    return {"since": since, "before": {"version_id": before["version_id"], "created_at": before["created_at"]},
            "after": {"version_id": after["version_id"], "created_at": after["created_at"]}, "changes": changes}


def session_citizen(session_id: str) -> str:
    """The citizen a session belongs to (code holders reach their history through a resumed session)."""
    session = profile.get_session(session_id, allow_ended=True)
    if not session.get("citizen_id"):
        raise ApiError("NO_SAVED_PASSPORTS", "This session is not saved.", 404)
    return session["citizen_id"]


# ---------------------------------------------------------------- deletion and retention

def _purge_sessions(db, sids_without_case: list[str], sids_with_case: list[str]) -> None:
    """Rows only: callers delete the sessions' stored files first (documents.delete_uploads)."""
    for table in ("facts", "turns", "doc_marks", "evaluations", "drafts", "passport_versions", "document_uploads"):
        db.executemany(f"DELETE FROM {table} WHERE session_id=?", [(s,) for s in sids_without_case])
    db.executemany("DELETE FROM sessions WHERE session_id=?", [(s,) for s in sids_without_case])
    # Consented hand-off cases stay with the reviewer; the session is no longer tied to the person.
    db.executemany("DELETE FROM turns WHERE session_id=?", [(s,) for s in sids_with_case])
    db.executemany("DELETE FROM document_uploads WHERE session_id=?", [(s,) for s in sids_with_case])
    db.executemany("UPDATE doc_marks SET status='missing' WHERE session_id=? AND status='uploaded'",
                   [(s,) for s in sids_with_case])
    db.executemany("UPDATE sessions SET citizen_id=NULL, auth_user_id=NULL WHERE session_id=?",
                   [(s,) for s in sids_with_case])


def _delete_citizen_rows(db, citizen_ids: list[str]) -> dict:
    if not citizen_ids:
        return {"sessions_deleted": 0, "cases_kept": 0, "passport_versions": 0}
    marks = ",".join("?" * len(citizen_ids))
    sessions, versions, codes = db.query_many([
        (f"SELECT s.session_id, EXISTS (SELECT 1 FROM cases c WHERE c.session_id = s.session_id) AS has_case"
         f" FROM sessions s WHERE s.citizen_id IN ({marks})", citizen_ids),
        (f"SELECT COUNT(*) FROM passport_versions WHERE citizen_id IN ({marks})", citizen_ids),
        (f"SELECT code_hash FROM citizens WHERE citizen_id IN ({marks}) AND code_hash IS NOT NULL", citizen_ids)])
    rows = sessions.fetchall()
    keep = [r["session_id"] for r in rows if r["has_case"]]
    drop = [r["session_id"] for r in rows if not r["has_case"]]
    _purge_sessions(db, drop, keep)
    db.execute(f"DELETE FROM passport_versions WHERE citizen_id IN ({marks})", citizen_ids)
    db.executemany("DELETE FROM passport_attempts WHERE code_hash=?", [(r[0],) for r in codes])
    db.execute(f"DELETE FROM citizens WHERE citizen_id IN ({marks})", citizen_ids)
    return {"sessions_deleted": len(drop), "cases_kept": len(keep), "passport_versions": versions.fetchone()[0]}


def delete_account(claims: dict) -> dict:
    """Delete the signed-in citizen's data and their Supabase Auth user. The Auth user goes first: if that fails,
    nothing is deleted and the citizen can retry; then all data goes in one transaction."""
    from . import documents
    cid = citizen_id_for(claims["sub"])
    db = get_db()
    # Uploaded files go first (a Storage failure stops here with nothing deleted), then the Auth user, then the rows.
    uploads = documents.paths_for_sessions(db, [r[0] for r in db.execute(
        "SELECT session_id FROM sessions WHERE citizen_id=?", (cid,))])
    storage_paths = [p for _, p in uploads]
    from . import storage
    storage.delete(storage_paths)
    if not auth.delete_auth_user(claims["sub"]):
        raise ApiError("ACCOUNT_DELETE_FAILED", "Could not delete the account right now; nothing was deleted. Try again.", 502)
    with db.transaction():
        counts = {**_delete_citizen_rows(db, [cid]), "uploads_deleted": len(uploads)}
        audit("account.deleted", details={**counts, "auth_user_deleted": True}, actor_id=cid, actor_role="citizen")
    metrics.AUTH.labels("account_deleted").inc()
    return {"deleted": True, **counts}


def retention_policy() -> dict:
    cfg = current_app.config
    return {"unsaved_hours": cfg["UNSAVED_RETENTION_HOURS"], "passport_days": cfg["PASSPORT_RETENTION_DAYS"],
            "stale_fact_days": cfg["STALE_FACT_DAYS"], "consent_version": cfg["CONSENT_VERSION"]}


def purge_expired(db, cfg) -> dict:
    """Retention (run by `manage cleanup`): unsaved data older than UNSAVED_RETENTION_HOURS (no consent, no hand-off
    case) and saved passports inactive for PASSPORT_RETENTION_DAYS are deleted; anonymous Auth users of deleted
    citizens and accounts deleted for inactivity are removed from Supabase Auth too (best effort)."""
    unsaved_cutoff = iso(now() - timedelta(hours=cfg["UNSAVED_RETENTION_HOURS"]))
    saved_cutoff = iso(now() - timedelta(days=cfg["PASSPORT_RETENTION_DAYS"]))
    sessions, unsaved, inactive = db.query_many([
        ("""SELECT s.session_id FROM sessions s LEFT JOIN citizens c ON c.citizen_id = s.citizen_id
            WHERE s.is_test=0 AND s.created_at < ? AND COALESCE(c.saved, 0) = 0
              AND NOT EXISTS (SELECT 1 FROM cases k WHERE k.session_id = s.session_id)""", (unsaved_cutoff,)),
        ("SELECT citizen_id, auth_user_id, is_anonymous FROM citizens WHERE saved=0 AND is_test=0 AND last_active_at < ?",
         (unsaved_cutoff,)),
        ("SELECT citizen_id, auth_user_id FROM citizens WHERE saved=1 AND is_test=0 AND last_active_at < ?",
         (saved_cutoff,))])
    from . import documents
    drop = [r[0] for r in sessions]
    unsaved, inactive = unsaved.fetchall(), inactive.fetchall()
    gone_citizens = [r["citizen_id"] for r in unsaved + inactive]
    if gone_citizens:
        drop_more = [r[0] for r in db.execute(f"SELECT session_id FROM sessions WHERE citizen_id IN"
                                               f" ({','.join('?' * len(gone_citizens))})", gone_citizens)]
    else:
        drop_more = []
    uploads = documents.paths_for_sessions(db, sorted(set(drop) | set(drop_more)))
    uploads += [u for u in documents.expired_uploads(db, cfg) if u not in uploads]
    # Files first: if Storage cannot be reached this raises, nothing is deleted and the next run retries.
    storage_removed = documents.delete_uploads(db, uploads)
    with db.transaction():
        _purge_sessions(db, drop, [])
        removed = _delete_citizen_rows(db, [r["citizen_id"] for r in unsaved + inactive])
        db.execute("DELETE FROM passport_attempts WHERE ts < ?", (iso(now() - timedelta(days=1)),))
        if drop or unsaved or inactive or storage_removed:
            db.execute("INSERT INTO audit_events(event_id, actor_id, actor_role, action, ts, details_json)"
                       " VALUES (?,?,?,?,?,?)",
                       (new_id("AUD"), "system", "system", "retention.purge", iso(),
                        dumps({"unsaved_sessions": len(drop), "unsaved_citizens": len(unsaved),
                               "inactive_passports": len(inactive), "uploads_deleted": storage_removed, **removed})))
    auth_ids = [r["auth_user_id"] for r in unsaved if r["auth_user_id"] and r["is_anonymous"]] + \
               [r["auth_user_id"] for r in inactive if r["auth_user_id"]]
    deleted_auth = sum(auth.delete_auth_user(a, cfg) for a in auth_ids) if cfg["SUPABASE_SECRET_KEY"] else 0
    return {"unsaved_sessions": len(drop), "unsaved_citizens": len(unsaved), "inactive_passports": len(inactive),
            "uploads_deleted": storage_removed, "auth_users_deleted": deleted_auth}
