"""Official scenarios TC1–TC4: seeded inputs run through the real pipeline with recorded evidence."""
import json

from . import cases, catalogue, metrics, profile, rules_engine, voice
from .common import ApiError
from .db import dumps, get_db, iso, new_id

TC_DEFS = {
    "TC1": {
        "title": "Eligible household",
        "expected": "Candidate scheme list with relevant rules quoted, source citations and a reproducible criterion trace.",
        "language": "en",
        "utterance": ("I am 67 years old, a farmer in a village in Guntur, Andhra Pradesh. Family of 4, yearly income "
                      "60,000 rupees. We have a BPL card, I do not get any pension, I own 2 acres of land and have a bank account."),
    },
    "TC2": {
        "title": "Same scheme name in two states",
        "expected": "Identical query in Bihar vs Maharashtra uses each state's own IGNOAPS record and rule (60+ vs 65+); the central NSAP scheme is considered in both.",
        "language": "en",
        "utterance": "I am 62 years old, BPL household, I do not get any pension. I live in {state}.",
        "states": ["Bihar", "Maharashtra"],
        "query": "old age pension",
    },
    "TC3": {
        "title": "Age misheard",
        "expected": "Misheard age (26) is held for confirmation, read back in digits and blocks screening even after confirm-all; correction to 62 creates a new fact, re-evaluates and changes results.",
        "language": "hi",
        "utterance": "मेरी उम्र 26 साल है। मैं बिहार में रहता हूँ। बीपीएल कार्ड है, कोई पेंशन नहीं मिलती। सालाना आय 40000 रुपये।",
        "corrected_age": 62,
    },
    "TC4": {
        "title": "Provisional eligibility",
        "expected": "Criteria pass but proof is missing → PROVISIONAL (never MATCH), document gap listed, draft saved idempotently; unknown facts give INSUFFICIENT_INFORMATION.",
        "language": "en",
        "utterance": "I am 70 years old and live in Punjab. We have a BPL card. I do not get any pension.",
        "documents": {"bpl_card": "missing", "age_proof": "unknown", "residence_proof": "available"},
    },
}


def _check(name, passed, detail=None):
    return {"name": name, "passed": bool(passed), "detail": detail}


def _by_rule(ev):
    return {r["rule_id"]: r for r in ev["results"]}


def _brief(r):
    return {"rule_id": r["rule_id"], "scheme": r["scheme_name"], "outcome": r["outcome"],
            "criteria": [{k: c[k] for k in ("criterion_id", "fact", "operator", "expected", "observed", "outcome", "fact_id", "quote")}
                         for c in r["criteria"]],
            "source_url": r["source"]["source_url"], "rule_version": r["rule_version"],
            "document_gaps": r["document_gaps"], "decision_reason": r["decision_reason"]}


def _session(lang):
    return profile.create_session("personal", lang, is_test=True)["session_id"]


def _confirm(sid):
    """The citizen confirms: low-impact facts in bulk, then each high-impact fact after its digit read-back."""
    pending = profile.confirm_all(sid)["needs_individual_confirmation"]
    for fid in pending:
        profile.patch_fact(sid, fid, {"confirmed": True})
    return pending


def run_tc1(d):
    sid = _session(d["language"])
    turn = profile.handle_turn(sid, d["utterance"], channel="text")
    _confirm(sid)
    ev1 = catalogue.evaluate_session(sid)
    ev2 = catalogue.evaluate_session(sid)
    rules = _by_rule(ev1)
    candidates = [r for r in ev1["results"] if r["outcome"] in (rules_engine.MATCH, rules_engine.PROVISIONAL)]
    checks = [
        _check("Facts extracted with stable IDs", len(turn["extracted"]) >= 8, [f["fact_id"] for f in turn["extracted"]]),
        _check("At least 3 candidate schemes", len(candidates) >= 3, [r["scheme_name"] for r in candidates]),
        _check("AP INDIRAMMA Old Age Pension (Rural) is a candidate",
               rules.get("R_AP_INDIRAMMA_OAP_RURAL", {}).get("outcome") == rules_engine.PROVISIONAL),
        _check("Every candidate quotes rule text and cites a source",
               all(any(c["quote"] for c in r["criteria"]) and r["source"]["source_url"] for r in candidates)),
        _check("Out-of-state schemes excluded (no Bihar/Telangana rules)",
               not {"R_IGNOAPS_BIHAR", "R_TG_RYTHU_BIMA"} & set(rules)),
        _check("Deterministic: same facts + rule version ⇒ same outcomes",
               {r["rule_id"]: r["outcome"] for r in ev1["results"]} == {r["rule_id"]: r["outcome"] for r in ev2["results"]}),
    ]
    return {"input": {"utterance": d["utterance"], "language": d["language"]},
            "actual": {"eval_id": ev1["eval_id"], "candidates": [_brief(r) for r in candidates],
                       "all_outcomes": {r["rule_id"]: r["outcome"] for r in ev1["results"]}},
            "checks": checks, "session_ids": [sid]}


def run_tc2(d):
    actual, sids, per_state = {}, [], {}
    for st in d["states"]:
        sid = _session(d["language"])
        sids.append(sid)
        profile.handle_turn(sid, d["utterance"].format(state=st), channel="text")
        _confirm(sid)
        ev = catalogue.evaluate_session(sid)
        found = catalogue.search(d["query"], state=st, limit=50)
        per_state[st] = {"rules": _by_rule(ev), "search_ids": {i["scheme_id"] for i in found["items"]},
                         "search_states": sorted({i["state"] or "Central" for i in found["items"]})}
        actual[st] = {"outcomes": {r["rule_id"]: r["outcome"] for r in ev["results"]},
                      "pension_results": [_brief(r) for r in ev["results"] if "IGNOAPS" in r["rule_id"]],
                      "catalogue_search": {"query": d["query"], "total": found["total"],
                                           "states_in_results": per_state[st]["search_states"]}}
    b, m = per_state["Bihar"], per_state["Maharashtra"]
    checks = [
        _check("Bihar uses Bihar IGNOAPS rule (60+) → PROVISIONAL",
               b["rules"].get("R_IGNOAPS_BIHAR", {}).get("outcome") == rules_engine.PROVISIONAL),
        _check("Maharashtra uses Maharashtra IGNOAPS rule (65+) → MISMATCH for age 62",
               m["rules"].get("R_IGNOAPS_MAHARASHTRA", {}).get("outcome") == rules_engine.MISMATCH),
        _check("No cross-state rule leakage",
               "R_IGNOAPS_MAHARASHTRA" not in b["rules"] and "R_IGNOAPS_BIHAR" not in m["rules"]),
        _check("Central NSAP IGNOAPS considered in both states",
               "R_NSAP_IGNOAPS" in b["rules"] and "R_NSAP_IGNOAPS" in m["rules"]),
        _check("Different source URLs for the two state records",
               b["rules"]["R_IGNOAPS_BIHAR"]["source"]["source_url"] != m["rules"]["R_IGNOAPS_MAHARASHTRA"]["source"]["source_url"]),
        _check("Catalogue search is jurisdiction-scoped",
               "66d19d5a9c9ff8daef6cd697" in b["search_ids"] and "66d19d5a9c9ff8daef6cd697" not in m["search_ids"]
               and "671a21dd80ec82b742b8fee4" in m["search_ids"] and "671a21dd80ec82b742b8fee4" not in b["search_ids"]),
    ]
    return {"input": {"utterance_template": d["utterance"], "states": d["states"], "query": d["query"]},
            "actual": actual, "checks": checks, "session_ids": sids}


def run_tc3(d):
    sid = _session(d["language"])
    turn = profile.handle_turn(sid, d["utterance"], channel="voice")
    age_fact = next((f for f in turn["extracted"] if f["attribute"] == "age"), None)
    blocked = None
    try:
        catalogue.evaluate_session(sid)
    except ApiError as e:
        blocked = {"code": e.code, "facts": e.details.get("facts")}

    # What the misheard value would have produced (dry run, not persisted) for the comparison.
    facts = catalogue.engine_facts(sid)
    dry = {a: {**f, "confirmed": True} for a, f in facts.items()}
    misheard = {c["rule"]["rule_id"]: rules_engine.evaluate(c["rule"], dry, {}, c["meta"])["outcome"]
                for c in catalogue.candidate_rules("Bihar")}

    bulk = profile.confirm_all(sid)
    after_bulk = None
    try:
        catalogue.evaluate_session(sid)
    except ApiError as e:
        after_bulk = e.code
    readback = next(f["readback"] for f in profile.profile_view(sid)["facts"] if f["attribute"] == "age")

    corrected = profile.patch_fact(sid, age_fact["fact_id"], {"value": d["corrected_age"], "raw_text": "citizen correction"})
    _confirm(sid)
    ev = catalogue.evaluate_session(sid)
    after = {r["rule_id"]: r["outcome"] for r in ev["results"]}
    changed = {k: {"with_misheard_age": misheard.get(k), "after_correction": after.get(k)}
               for k in after if misheard.get(k) != after.get(k)}
    history = [f for f in profile.fact_history(sid) if f["attribute"] == "age"]
    checks = [
        _check("Transcript age 26 extracted and held unconfirmed", age_fact and age_fact["value"] == 26 and not age_fact["confirmed"],
               age_fact and {"fact_id": age_fact["fact_id"], "raw_text": age_fact["raw_text"]}),
        _check("Screening blocked before confirmation", blocked and blocked["code"] == "PROFILE_NEEDS_CONFIRMATION", blocked),
        _check("Confirm-all leaves high-impact facts pending and screening blocked",
               age_fact["fact_id"] in bulk["needs_individual_confirmation"] and after_bulk == "PROFILE_NEEDS_CONFIRMATION",
               bulk),
        _check("Age read back with digits for individual confirmation", "26" in readback, readback),
        _check("Correction creates new confirmed fact superseding the old one",
               len(history) == 2 and history[0]["superseded_by"] == history[1]["fact_id"] and history[1]["confirmed"],
               [{"fact_id": h["fact_id"], "value": h["value"], "superseded_by": h["superseded_by"]} for h in history]),
        _check("Re-evaluation uses the corrected fact ID",
               corrected["fact"]["fact_id"] in ev["input_fact_ids"]),
        _check("Results changed: Bihar IGNOAPS MISMATCH → PROVISIONAL",
               changed.get("R_IGNOAPS_BIHAR") == {"with_misheard_age": "MISMATCH", "after_correction": "PROVISIONAL"}, changed),
    ]
    return {"input": {"utterance": d["utterance"], "channel": "voice (simulated transcript)", "language": d["language"],
                      "correction": {"age": d["corrected_age"]}},
            "actual": {"reply": turn["reply"], "blocked": blocked, "confirm_all": bulk, "age_readback": readback,
                       "age_history": history, "changed": changed},
            "checks": checks, "session_ids": [sid]}


def run_tc4(d):
    sid = _session(d["language"])
    profile.handle_turn(sid, d["utterance"], channel="text")
    _confirm(sid)
    for doc, st in d["documents"].items():
        catalogue.set_doc_mark(sid, doc, st)
    ev = catalogue.evaluate_session(sid)
    rules = _by_rule(ev)
    pj = rules.get("R_IGNOAPS_PUNJAB")
    draft1 = cases.save_draft(sid, "680a02cb41f9fb65ecb3453f")
    draft2 = cases.save_draft(sid, "680a02cb41f9fb65ecb3453f")
    summary = voice.summarize(ev, "en", catalogue.doc_marks(sid))
    insufficient = [r["rule_id"] for r in ev["results"] if r["outcome"] == rules_engine.INSUFFICIENT]
    checks = [
        _check("Punjab IGNOAPS is PROVISIONAL (not MATCH)", pj and pj["outcome"] == rules_engine.PROVISIONAL,
               pj and [x["code"] for x in pj["decision_reason"]]),
        _check("No result is MATCH while proof is unverified", all(r["outcome"] != rules_engine.MATCH for r in ev["results"])),
        _check("Document gap lists the missing BPL card", pj and "bpl_card" in pj["document_gaps"], pj and pj["document_gaps"]),
        _check("Unknown facts produce INSUFFICIENT_INFORMATION (e.g. PM-KISAN land ownership)",
               "R_PM_KISAN" in insufficient, insufficient),
        _check("Draft saved with status DRAFT_SAVED", draft1["status"] == "DRAFT_SAVED"),
        _check("Repeat save returns the same draft (no duplicate)", draft1["draft_id"] == draft2["draft_id"],
               {"first": draft1["draft_id"], "second": draft2["draft_id"], "version": draft2["version"]}),
        _check("Summary makes no approval/benefit promise",
               not any(w in summary.lower() for w in ("approved", "granted", "guaranteed", "submitted")), summary),
    ]
    return {"input": {"utterance": d["utterance"], "documents": d["documents"]},
            "actual": {"punjab_result": pj and _brief(pj), "draft_id": draft1["draft_id"], "summary": summary,
                       "insufficient": insufficient},
            "checks": checks, "session_ids": [sid]}


RUNNERS = {"TC1": run_tc1, "TC2": run_tc2, "TC3": run_tc3, "TC4": run_tc4}


def run(tc_id: str) -> dict:
    if tc_id not in RUNNERS:
        raise ApiError("UNKNOWN_TEST_CASE", "Use TC1, TC2, TC3 or TC4.", 404)
    d = TC_DEFS[tc_id]
    out = RUNNERS[tc_id](d)
    passed = all(c["passed"] for c in out["checks"])
    metrics.TEST_RUNS.labels(tc_id, "pass" if passed else "fail").inc()
    record = {"tc_id": tc_id, "title": d["title"], "expected": d["expected"], "passed": passed, "ran_at": iso(), **out}
    db = get_db()
    run_id = new_id("RUN")
    db.execute("INSERT INTO test_runs(run_id, tc_id, ran_at, passed, evidence_json) VALUES (?,?,?,?,?)",
               (run_id, tc_id, record["ran_at"], int(passed), dumps(record)))
    db.commit()
    return {"run_id": run_id, **record}


def latest_runs() -> dict:
    out = {}
    for tc in TC_DEFS:
        row = get_db().execute("SELECT * FROM test_runs WHERE tc_id=? ORDER BY ran_at DESC, rowid DESC LIMIT 1", (tc,)).fetchone()
        out[tc] = json.loads(row["evidence_json"]) | {"run_id": row["run_id"]} if row else None
    return {"definitions": {k: {"title": v["title"], "expected": v["expected"]} for k, v in TC_DEFS.items()}, "latest": out}


def reset() -> dict:
    db = get_db()
    sids = [r[0] for r in db.execute("SELECT session_id FROM sessions WHERE is_test=1")]
    for table in ("facts", "turns", "doc_marks", "evaluations", "drafts", "cases", "audit_events"):
        db.executemany(f"DELETE FROM {table} WHERE session_id=?", [(s,) for s in sids])
    db.execute("DELETE FROM sessions WHERE is_test=1")
    db.execute("DELETE FROM test_runs")
    db.commit()
    return {"removed_sessions": len(sids)}
