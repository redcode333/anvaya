import re
import uuid

import pytest

from conftest import start

BIHAR = "I am 62 years old, BPL household, I do not get any pension. I live in Bihar."
BIHAR_IGNOAPS = "66d19d5a9c9ff8daef6cd697"


def key():
    return {"Idempotency-Key": uuid.uuid4().hex}


def drafted(client, sid, scheme=BIHAR_IGNOAPS):
    assert client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate").status_code == 200
    r = client.post(f"/api/v1/sessions/{sid}/drafts", json={"scheme_id": scheme}, headers=key())
    assert r.status_code == 201, r.json
    return r.json


def test_health_and_ready(client):
    assert client.get("/api/v1/health").json["status"] == "ok"
    assert client.get("/api/v1/ready").json["schemes"] == 3534


def test_evaluation_blocked_until_high_impact_confirmed(client):
    sid = start(client, BIHAR, confirm=False)
    r = client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate")
    assert r.status_code == 409 and r.json["error"]["code"] == "PROFILE_NEEDS_CONFIRMATION"


def test_correction_supersedes_and_reports_changes(client):
    sid = start(client, BIHAR.replace("62", "26"))
    client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate")
    age = next(f for f in client.get(f"/api/v1/sessions/{sid}").json["facts"] if f["attribute"] == "age")
    r = client.patch(f"/api/v1/sessions/{sid}/profile/facts/{age['fact_id']}", json={"value": 62})
    assert r.json["previous"]["value"] == 26 and r.json["fact"]["confirmed"]
    ev = client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate").json
    assert any(c["scheme_id"] == BIHAR_IGNOAPS and c["after"] == "PROVISIONAL" for c in ev["changes_since_last"])
    assert r.json["fact"]["fact_id"] in ev["input_fact_ids"]
    again = client.patch(f"/api/v1/sessions/{sid}/profile/facts/{age['fact_id']}", json={"value": 63})
    assert again.status_code == 409 and again.json["error"]["code"] == "FACT_SUPERSEDED"


def test_language_switch_keeps_facts(client):
    sid = start(client, BIHAR)
    before = client.get(f"/api/v1/sessions/{sid}").json["facts"]
    client.patch(f"/api/v1/sessions/{sid}", json={"language": "te"})
    after = client.get(f"/api/v1/sessions/{sid}").json
    strip = lambda facts: [{k: v for k, v in f.items() if k != "readback"} for f in facts]  # noqa: E731
    assert after["session"]["language"] == "te" and strip(after["facts"]) == strip(before)
    assert next(f["readback"] for f in after["facts"] if f["attribute"] == "age") == "వయస్సు: 62 సంవత్సరాలు"
    ev = client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate").json
    assert ev["results"][0]["outcome_label"] in ("తాత్కాలిక సరిపోలిక", "మరింత సమాచారం కావాలి", "సరిపోలలేదు", "మానవ సమీక్ష అవసరం")


def test_no_repeated_question_for_known_fact(client):
    sid = start(client, "I live in Bihar", confirm=False)
    r = client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": "hello"})
    assert r.json["next_question"]["attribute"] == "age"


def test_draft_requires_idempotency_key_and_replays(client):
    sid = start(client, BIHAR)
    client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate")
    assert client.post(f"/api/v1/sessions/{sid}/drafts", json={"scheme_id": BIHAR_IGNOAPS}).status_code == 428
    k = key()
    a = client.post(f"/api/v1/sessions/{sid}/drafts", json={"scheme_id": BIHAR_IGNOAPS}, headers=k).json
    b = client.post(f"/api/v1/sessions/{sid}/drafts", json={"scheme_id": BIHAR_IGNOAPS}, headers=k).json
    assert a["draft_id"] == b["draft_id"] and b["idempotent_replay"] and a["version"] == b["version"]
    c = client.post(f"/api/v1/sessions/{sid}/drafts", json={"scheme_id": BIHAR_IGNOAPS}, headers=key()).json
    assert c["draft_id"] == a["draft_id"] and c["version"] == a["version"] + 1


def test_draft_field_provenance(client):
    sid = start(client, BIHAR)
    d = drafted(client, sid)
    prov = {f["key"]: f["provenance"] for f in d["fields"]}
    assert prov["age"] == "confirmed" and prov["applicant_name"] == "missing"


def test_mismatch_scheme_gets_no_draft(client):
    sid = start(client, BIHAR.replace("62", "40"))
    client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate")
    r = client.post(f"/api/v1/sessions/{sid}/drafts", json={"scheme_id": BIHAR_IGNOAPS}, headers=key())
    assert r.status_code == 409 and r.json["error"]["code"] == "SCHEME_MISMATCH"


def test_draft_edit_version_conflict(client):
    sid = start(client, BIHAR)
    d = drafted(client, sid)
    h = {"X-Session-Id": sid}
    ok = client.patch(f"/api/v1/drafts/{d['draft_id']}", json={"version": d["version"], "fields": {"applicant_name": "Sita Devi"}}, headers=h)
    assert ok.status_code == 200 and ok.json["version"] == d["version"] + 1
    assert next(f for f in ok.json["fields"] if f["key"] == "applicant_name")["provenance"] == "citizen_entered"
    stale = client.patch(f"/api/v1/drafts/{d['draft_id']}", json={"version": d["version"], "fields": {"applicant_name": "X"}}, headers=h)
    assert stale.status_code == 409 and stale.json["error"]["code"] == "CONFLICT"
    other = client.get(f"/api/v1/drafts/{d['draft_id']}", headers={"X-Session-Id": "SES_other"})
    assert other.status_code == 403


def test_handoff_needs_consent_and_is_idempotent(client):
    sid = start(client, BIHAR)
    d = drafted(client, sid)
    h = {"X-Session-Id": sid}
    no = client.post(f"/api/v1/drafts/{d['draft_id']}/handoff", json={"consent": {}}, headers={**h, **key()})
    assert no.status_code == 422 and no.json["error"]["code"] == "CONSENT_REQUIRED"
    k = key()
    a = client.post(f"/api/v1/drafts/{d['draft_id']}/handoff", json={"consent": {"share_with_reviewer": True}}, headers={**h, **k}).json
    b = client.post(f"/api/v1/drafts/{d['draft_id']}/handoff", json={"consent": {"share_with_reviewer": True}}, headers={**h, **k}).json
    assert a["case_id"] == b["case_id"] and a["code"] == b["code"] and a["status"] == "PENDING_REVIEW"
    s = client.post("/api/v1/cases/status", json={"code": a["code"].lower()}).json
    assert s["status"] == "PENDING_REVIEW" and "facts" not in s


def test_reviewer_requires_role_and_flow(client, reviewer, operator):
    assert client.get("/api/v1/reviewer/cases").status_code == 401
    assert client.get("/api/v1/reviewer/cases", headers=operator).status_code == 403
    sid = start(client, BIHAR)
    d = drafted(client, sid)
    h = client.post(f"/api/v1/drafts/{d['draft_id']}/handoff", json={"consent": {"share_with_reviewer": True}},
                    headers={"X-Session-Id": sid, **key()}).json
    found = client.post("/api/v1/reviewer/cases/lookup", json={"code": h["code"]}, headers=reviewer).json
    assert found["case_id"] == h["case_id"]
    case = client.get(f"/api/v1/reviewer/cases/{h['case_id']}", headers=reviewer).json
    assert case["evaluation"]["outcome"] == "PROVISIONAL" and case["facts"]
    r = client.post(f"/api/v1/reviewer/cases/{h['case_id']}/decision", json={"action": "request_correction"}, headers=reviewer)
    assert r.status_code == 422
    r = client.post(f"/api/v1/reviewer/cases/{h['case_id']}/decision",
                    json={"action": "request_correction", "note": "Upload age proof"}, headers=reviewer)
    assert r.json["status"] == "CORRECTION_REQUESTED"
    assert client.post("/api/v1/cases/status", json={"code": h["code"]}).json["correction_note"] == "Upload age proof"
    # Citizen resubmits; reviewer verifies documents and records an outcome.
    h2 = client.post(f"/api/v1/drafts/{d['draft_id']}/handoff", json={"consent": {"share_with_reviewer": True}},
                     headers={"X-Session-Id": sid, **key()}).json
    assert h2["case_id"] == h["case_id"] and h2["status"] == "PENDING_REVIEW"
    r = client.post(f"/api/v1/reviewer/cases/{h['case_id']}/decision",
                    json={"action": "record_review", "outcome": "appears_eligible", "verified_documents": ["age_proof"]},
                    headers=reviewer)
    assert r.json["status"] == "REVIEWED"
    audit = client.get(f"/api/v1/cases/{h['case_id']}/audit", headers=reviewer).json["events"]
    actions = [e["action"] for e in audit]
    assert {"case.created", "review.request_correction", "case.resubmitted", "review.record_review"} <= set(actions)
    # Whole-number match only: random hex IDs (DRF_1d11563628d8) may contain the digits "62".
    assert not any(re.search(r"\b62\b", str(e["details"])) for e in audit), "audit must not hold raw profile values"


def test_citizen_cannot_set_verified(client):
    sid = start(client, BIHAR)
    r = client.put(f"/api/v1/sessions/{sid}/documents/bpl_card", json={"status": "verified"})
    assert r.status_code == 422


def test_code_lookup_rate_limited(app, client):
    from anvaya import cases
    cases._lookup_hits.clear()
    app.config["CODE_LOOKUP_LIMIT_PER_MIN"] = 3
    try:
        codes = [client.post("/api/v1/cases/status", json={"code": "ANV-ZZZZ-ZZZZ"}).status_code for _ in range(5)]
    finally:
        app.config["CODE_LOOKUP_LIMIT_PER_MIN"] = 1000
    assert codes[:3] == [404, 404, 404] and 429 in codes[3:]


def test_kiosk_requires_operator_and_exit_clears_unconsented_data(client, operator):
    assert client.post("/api/v1/sessions", json={"mode": "kiosk"}).status_code == 401
    sid = client.post("/api/v1/sessions", json={"mode": "kiosk", "language": "te"}, headers=operator).json["session_id"]
    client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": BIHAR}, headers=operator)
    client.post(f"/api/v1/sessions/{sid}/end", headers=operator)
    assert client.get(f"/api/v1/sessions/{sid}", headers=operator).json["facts"] == []
    assert client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": "x"}, headers=operator).status_code == 410


def offline_event(**over):
    ev = {"event_id": uuid.uuid4().hex, "idempotency_key": uuid.uuid4().hex, "type": "offline_draft",
          "schema_version": 1, "created_at": "2026-10-21T10:00:00+00:00", "bundle_version": "rules-2026.10.1",
          "payload": {"language": "hi", "scheme_id": BIHAR_IGNOAPS,
                      "facts": {"state": "Bihar", "age": 64, "bpl": True, "receives_other_pension": False},
                      "documents": {"bpl_card": "available"}, "local_result": {"outcome": "PROVISIONAL"},
                      "consent": {"share_with_reviewer": True}}}
    ev.update(over)
    return ev


def test_sync_dedupes_and_reviewer_gets_one_case(client, reviewer):
    ev = offline_event()
    first = client.post("/api/v1/sync/events", json={"device_id": "KIOSK-1", "events": [ev]}).json["results"][0]
    assert first["status"] == "accepted" and first["case_id"] and not first["result_changed"]
    retry = client.post("/api/v1/sync/events", json={"device_id": "KIOSK-1", "events": [ev, ev]}).json["results"]
    assert [r["status"] for r in retry] == ["duplicate", "duplicate"]
    assert retry[0]["original"]["case_id"] == first["case_id"]
    queue = client.get("/api/v1/reviewer/cases", headers=reviewer).json["cases"]
    assert sum(1 for c in queue if c["case_id"] == first["case_id"]) == 1
    assert next(c for c in queue if c["case_id"] == first["case_id"])["origin"] == "offline_sync"


def test_sync_flags_outdated_bundle_and_changed_result(client):
    ev = offline_event(bundle_version="rules-2026.09.0")
    ev["payload"]["local_result"] = {"outcome": "MATCH"}
    r = client.post("/api/v1/sync/events", json={"device_id": "KIOSK-2", "events": [ev]}).json["results"][0]
    assert r["bundle_outdated"] and r["result_changed"] and r["server_outcome"] == "PROVISIONAL"


def test_sync_draft_edit_conflict(client):
    sid = start(client, BIHAR)
    d = drafted(client, sid)
    ev = {"event_id": uuid.uuid4().hex, "idempotency_key": uuid.uuid4().hex, "type": "draft_edit", "schema_version": 1,
          "payload": {"draft_id": d["draft_id"], "base_version": d["version"] - 1, "fields": {"applicant_name": "A"}}}
    r = client.post("/api/v1/sync/events", json={"device_id": "K", "events": [ev]}).json["results"][0]
    assert r["status"] == "conflict" and r["server_version"] == d["version"]


def test_bundle_has_checksum(client):
    r = client.get("/api/v1/sync/bundle")
    assert r.headers["ETag"] == r.json["checksum"] and len(r.json["rules"]) == 17


def test_catalogue_search_scoped(client):
    r = client.get("/api/v1/schemes?q=old+age+pension&state=Bihar&limit=100").json
    states = {i["state"] for i in r["items"]}
    assert states <= {"Bihar", None} and any(i["scheme_id"] == BIHAR_IGNOAPS for i in r["items"])
    assert all("freshness" in i and i["source_url"] for i in r["items"])


def test_scheme_detail_graph(client):
    s = client.get(f"/api/v1/schemes/{BIHAR_IGNOAPS}").json
    assert s["graph"]["APPLIES_IN"][0]["label"] == "Bihar" and s["graph"]["HAS_CRITERION"]


def test_admin_verify_rule(client, admin, reviewer):
    assert client.post("/api/v1/admin/rules/R_PMJJBY/verify", json={"checked_source_url": "x"}, headers=reviewer).status_code == 403
    assert client.post("/api/v1/admin/rules/R_PMJJBY/verify", json={}, headers=admin).status_code == 422
    r = client.post("/api/v1/admin/rules/R_PMJJBY/verify",
                    json={"checked_source_url": "https://jansuraksha.gov.in/Files/PMJJBY/English/Rules.pdf"}, headers=admin)
    assert r.json["source_verified_by"] == "admin@anvaya.test"
    f = client.get("/api/v1/admin/schemes/freshness", headers=admin).json
    assert next(x for x in f["rules"] if x["rule_id"] == "R_PMJJBY")["source_verified_at"]


def test_voice_unavailable_falls_back_cleanly(client):
    sid = start(client, BIHAR)
    r = client.post(f"/api/v1/sessions/{sid}/voice/speak", json={"text": "hi"})
    assert r.status_code == 503 and r.json["error"]["code"] == "VOICE_UNAVAILABLE"


@pytest.mark.parametrize("tc", ["TC1", "TC2", "TC3", "TC4"])
def test_official_scenarios(client, admin, tc):
    r = client.post(f"/api/v1/test-runs/{tc}", headers=admin).json
    assert r["passed"], [c for c in r["checks"] if not c["passed"]]


@pytest.mark.parametrize("path", ["/api/v1/test-runs/TC1", "/api/v1/test-runs/reset"])
def test_test_runs_need_admin(client, reviewer, operator, path):
    assert client.post(path).json["error"]["code"] == "UNAUTHENTICATED"
    assert client.post(path, headers=reviewer).status_code == 403
    assert client.post(path, headers=operator).status_code == 403
    r = client.get("/api/v1/test-runs")
    assert r.status_code == 200 and r.json["demo_mode"] is False


def test_test_runs_open_in_demo_mode(app, client):
    app.config["DEMO_TEST_RUNS"] = True
    try:
        assert client.get("/api/v1/test-runs").json["demo_mode"] is True
        assert client.post("/api/v1/test-runs/TC2").json["passed"]
        assert client.post("/api/v1/test-runs/reset").status_code == 200
    finally:
        app.config["DEMO_TEST_RUNS"] = False


def test_prometheus_metrics(client):
    sid = start(client, BIHAR)
    client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate")
    r = client.get("/metrics")
    assert r.status_code == 200 and r.headers["Content-Type"].startswith("text/plain")
    text = r.get_data(as_text=True)
    assert 'anvaya_eligibility_outcomes_total{outcome="PROVISIONAL",rule_id="R_IGNOAPS_BIHAR"}' in text
    assert 'anvaya_http_requests_total{method="POST",route="/api/v1/sessions/<sid>/eligibility/evaluate",status="200"}' in text
    assert 'anvaya_catalogue_records{kind="schemes"} 3534.0' in text
    assert "SES_" not in text and "Bihar" not in text, "metrics must not carry session IDs or profile values"


def test_metrics_token_enforced_when_configured(app, client):
    app.config["METRICS_TOKEN"] = "s3cret"
    try:
        assert client.get("/metrics").status_code == 401
        assert client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert client.get("/metrics", headers={"Authorization": "Bearer s3cret"}).status_code == 200
    finally:
        app.config["METRICS_TOKEN"] = ""


def turn(client, utterance, lang="en"):
    sid = client.post("/api/v1/sessions", json={"mode": "personal", "language": lang}).json["session_id"]
    r = client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": utterance})
    assert r.status_code == 200, r.json
    return sid, r.json


@pytest.mark.parametrize("lang,utterance,note", [
    ("hi", "मेरी माँ 67 साल की हैं, मेरी उम्र 35 है", "मैंने आपके माँ की उम्र (67) सुनी; इसे आपकी अपनी उम्र नहीं माना।"),
    ("te", "మా అమ్మ వయస్సు 67 సంవత్సరాలు, నా వయస్సు 35 సంవత్సరాలు",
     "మీ అమ్మ వయస్సు (67) విన్నాను; దాన్ని మీ స్వంత వయస్సుగా తీసుకోలేదు."),
    ("en", "My mother is 67 years old and I am 35", "I heard an age for your mother (67); I did not use it as your own age."),
])
def test_relative_age_not_stored_and_reply_says_so(client, lang, utterance, note):
    sid, r = turn(client, utterance, lang)
    assert [f["value"] for f in r["extracted"] if f["attribute"] == "age"] == [35]
    assert note in r["reply"] and r["other_people"][0]["value"] == 67
    facts = client.get(f"/api/v1/sessions/{sid}").json["facts"]
    assert [f["value"] for f in facts if f["attribute"] == "age"] == [35]


# LLM facts and the relative-age rule: tests/test_llm.py::test_relative_age_rule_applies_to_llm_facts


def test_confirm_all_only_confirms_low_impact_facts(client):
    sid, _ = turn(client, BIHAR)
    r = client.post(f"/api/v1/sessions/{sid}/profile/confirm-all").json
    facts = {f["attribute"]: f for f in r["facts"]}
    assert {a for a, f in facts.items() if not f["confirmed"]} == {"age", "state"}
    assert set(r["needs_confirmation"]) == {facts["age"]["fact_id"], facts["state"]["fact_id"]}
    assert set(r["needs_individual_confirmation"]) == set(r["needs_confirmation"])
    assert facts["age"]["readback"] == "Age: 62 years" and facts["state"]["readback"] == "State: Bihar"
    assert client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate").json["error"]["code"] == "PROFILE_NEEDS_CONFIRMATION"
    client.patch(f"/api/v1/sessions/{sid}/profile/facts/{facts['age']['fact_id']}", json={"confirmed": True})
    assert client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate").status_code == 409
    client.patch(f"/api/v1/sessions/{sid}/profile/facts/{facts['state']['fact_id']}", json={"confirmed": True})
    assert client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate").status_code == 200


def test_income_and_area_read_back_with_digits(client):
    sid, _ = turn(client, "मैं बिहार के गाँव में रहता हूँ। साल भर में डेढ़ लाख की कमाई है", "hi")
    facts = {f["attribute"]: f for f in client.post(f"/api/v1/sessions/{sid}/profile/confirm-all").json["facts"]}
    assert facts["annual_income"]["readback"] == "सालाना पारिवारिक आय (₹): ₹1,50,000"
    assert facts["area"]["confirm_individually"] and not facts["area"]["confirmed"]
    assert facts["area"]["readback"].endswith("ग्रामीण")


@pytest.mark.parametrize("lang,utterance,heard,alt", [
    ("hi", "मेरी उम्र साठ साल है", "साठ", "सत्तर"),
    ("en", "I am sixty years old", "sixty", "sixteen"),
    ("te", "నా వయస్సు అరవై సంవత్సరాలు", "అరవై", "డెబ్బై"),
])
def test_confusable_spoken_number_needs_confirmation(client, lang, utterance, heard, alt):
    sid, r = turn(client, utterance, lang)
    age = next(f for f in r["extracted"] if f["attribute"] == "age")
    assert age["value"] == 60 and age["confusable"] and not age["confirmed"]
    assert age["fact_id"] in r["needs_confirmation"]
    assert f"“{heard}”" in r["reply"] and alt in r["reply"]
    after = client.post(f"/api/v1/sessions/{sid}/profile/confirm-all").json
    assert age["fact_id"] in after["needs_confirmation"]


def test_schema_migration_adds_confusable_column(tmp_path):
    """A SQLite database from before schema_migrations existed (old facts table) is brought up to date."""
    import sqlite3

    from anvaya.db import connect
    from anvaya.migrations import migrate
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.execute("CREATE TABLE facts (fact_id TEXT PRIMARY KEY, session_id TEXT NOT NULL, attribute TEXT NOT NULL)")
    old.execute("INSERT INTO facts VALUES ('F-1', 'S-1', 'age')")
    old.commit()
    old.close()
    db = connect(str(path))
    assert migrate(db) == [1, 2, 3, 4, 5, 6]
    assert migrate(db) == []  # idempotent
    assert db.execute("SELECT confusable FROM facts WHERE fact_id='F-1'").fetchone()[0] == 0
    db.close()


def test_no_user_facing_string_promises_eligibility_or_approval():
    """Server-generated citizen text (en/hi/te) uses potential-match / provisional wording, never a promise."""
    from anvaya import i18n
    promise = re.compile(r"\beligible\b|\bapproved\b|\bguaranteed?\b|पात्र|मंजूर|मंज़ूर|అర్హులు", re.I)
    tables = [i18n.OUTCOMES, i18n.MESSAGES, i18n.QUESTIONS, i18n.REVIEW_OUTCOMES, i18n.CASE_STATUS, i18n.DOC_STATUS]
    texts = [s for table in tables for entry in table.values() for s in entry.values()]
    texts += [s for entry in i18n.DOCUMENTS.values() for pair in entry.values() for s in pair]
    assert texts and [s for s in texts if promise.search(s)] == []
