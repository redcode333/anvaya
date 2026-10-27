"""Fill a draft by speaking: the plan of open fields, parsing answers (name, district, gender, several at once), the guardrails,
access rules, and the document-by-voice answers."""
import pytest

from anvaya import draftvoice
from test_formhelper import make_draft
from test_formhelper import owner as session_headers


NO_DISTRICT = ("I am 67 years old, a farmer in a village in Andhra Pradesh. Family of 4, yearly income 60,000 rupees. "
               "We have a BPL card, I do not get any pension, I own 2 acres of land and have a bank account.")


@pytest.fixture()
def open_draft(client):
    """A draft with the applicant name, district and gender still open (the story names no district)."""
    import uuid
    sid = client.post("/api/v1/sessions", json={"mode": "personal", "language": "en"}).json["session_id"]
    client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": NO_DISTRICT})
    for fid in client.post(f"/api/v1/sessions/{sid}/profile/confirm-all").json["needs_confirmation"]:
        client.patch(f"/api/v1/sessions/{sid}/profile/facts/{fid}", json={"confirmed": True})
    ev = client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate").json
    scheme = next(r["scheme_id"] for r in ev["results"] if r["outcome"] != "MISMATCH" and r["jurisdiction"]["level"] == "State")
    d = client.post(f"/api/v1/sessions/{sid}/drafts", json={"scheme_id": scheme}, headers={"Idempotency-Key": uuid.uuid4().hex}).json
    return sid, d["draft_id"]


def plan(client, sid, draft_id, lang="en"):
    r = client.get(f"/api/v1/drafts/{draft_id}/voice-fill/plan?language={lang}", headers=session_headers(sid))
    assert r.status_code == 200, r.json
    return r.json


def say(client, sid, draft_id, text, asked=None, lang="en"):
    r = client.post(f"/api/v1/drafts/{draft_id}/voice-fill", json={"utterance": text, "asked": asked, "language": lang}, headers=session_headers(sid))
    assert r.status_code == 200, r.json
    return r.json


def test_the_plan_lists_the_open_fields_in_form_order_with_a_question_each(client, open_draft):
    sid, did = open_draft
    steps = plan(client, sid, did)["steps"]
    keys = [s["key"] for s in steps]
    assert keys[0] == "applicant_name" and "gender" in keys and "district" in keys
    assert steps[0]["question"] == "What is your full name?" and steps[0]["label"]
    hi = plan(client, sid, did, "hi")["steps"][0]
    assert hi["question"] == "आपका पूरा नाम क्या है?"
    te = plan(client, sid, did, "te")["steps"][0]
    assert te["question"] == "మీ పూర్తి పేరు ఏమిటి?"


@pytest.mark.parametrize("text,name", [
    ("My name is Lakshmi Devi", "Lakshmi Devi"), ("lakshmi devi", "Lakshmi Devi"), ("I am Ravi Kumar", "Ravi Kumar"),
    ("My name is Ravi and I live in Guntur", "Ravi"), ("मेरा नाम लक्ष्मी देवी है", "लक्ष्मी देवी"), ("mera naam Sita hai", "Sita"),
    ("నా పేరు లక్ష్మి", "లక్ష్మి"),
])
def test_names_in_any_phrasing(client, open_draft, text, name):
    sid, did = open_draft
    r = say(client, sid, did, text, asked="applicant_name")
    assert r["understood"] and r["fields"]["applicant_name"] == name and r["labels"]["applicant_name"]


def test_district_and_gender_answers(client, open_draft):
    sid, did = open_draft
    assert say(client, sid, did, "Guntur", asked="district")["fields"]["district"] == "Guntur"
    assert say(client, sid, did, "I live in Krishna district", asked="district")["fields"]["district"] == "Krishna"
    assert say(client, sid, did, "Rampur", asked="district")["fields"]["district"] == "Rampur"  # not in the built-in list: taken as said
    assert say(client, sid, did, "I am a woman", asked="gender")["fields"]["gender"] == "female"
    assert say(client, sid, did, "मैं पुरुष हूँ", asked="gender")["fields"]["gender"] == "male"


def test_several_answers_in_one_sentence_fill_several_fields(client, open_draft):
    sid, did = open_draft
    r = say(client, sid, did, "My name is Ravi Kumar and I live in Guntur")
    assert r["fields"].get("district") == "Guntur" and r["fields"].get("applicant_name") == "Ravi Kumar"


def test_a_field_that_is_not_open_is_not_filled(client, open_draft):
    sid, did = open_draft
    r = say(client, sid, did, "I am 30 years old and I live in Bihar")  # age and state are already in the draft
    assert "age" not in r["fields"] and "state" not in r["fields"]


def test_a_district_already_in_the_draft_is_not_asked_again(client):
    sid, d = make_draft(client, {}, name=None)  # this story names Guntur
    keys = [s["key"] for s in client.get(f"/api/v1/drafts/{d['draft_id']}/voice-fill/plan", headers=session_headers(sid)).json["steps"]]
    assert "applicant_name" in keys and "district" not in keys


def test_nothing_understood_and_skip(client, open_draft):
    sid, did = open_draft
    r = say(client, sid, did, "blah blah blah blah", asked="gender")
    assert not r["understood"] and r["fields"] == {} and "could not pick out" in r["message"]
    r = say(client, sid, did, "skip", asked="gender")
    assert r["skipped"] and not r["understood"]


def test_sensitive_or_abusive_answers_are_refused_and_not_echoed(client, open_draft):
    sid, did = open_draft
    r = say(client, sid, did, "my aadhaar number is 1234 5678 9012", asked="applicant_name")
    assert r["guardrail"] == "sensitive" and r["fields"] == {} and r["heard"] is None and "1234" not in str(r)
    assert say(client, sid, did, "you are a fucking idiot", asked="applicant_name")["guardrail"] == "abuse"


def test_a_name_is_a_name_not_a_sentence(client, open_draft):
    sid, did = open_draft
    for text in ("I have 3 children and a farm", "a" * 200, "1234"):
        r = client.post(f"/api/v1/drafts/{did}/voice-fill", json={"utterance": text, "asked": "applicant_name"}, headers=session_headers(sid))
        assert r.status_code in (200, 422)
        if r.status_code == 200:
            assert "applicant_name" not in r.json["fields"]
    assert draftvoice.clean_name("O'Brien-Smith") == "O'Brien-Smith"


def test_only_the_owner_can_use_it_and_nothing_is_saved(client, open_draft):
    sid, did = open_draft
    other = client.post("/api/v1/sessions", json={"mode": "personal", "language": "en"}).json["session_id"]
    assert client.get(f"/api/v1/drafts/{did}/voice-fill/plan", headers=session_headers(other)).status_code == 403
    say(client, sid, did, "My name is Lakshmi Devi", asked="applicant_name")
    d = client.get(f"/api/v1/drafts/{did}", headers=session_headers(sid)).json
    assert next(f for f in d["fields"] if f["key"] == "applicant_name")["value"] in (None, "")  # parsing alone never saves


def test_a_draft_with_the_reviewer_cannot_be_voice_filled(client):
    sid, d = make_draft(client, {}, name="Lakshmi Devi")
    h = session_headers(sid)
    sent = client.post(f"/api/v1/drafts/{d['draft_id']}/handoff", json={"consent": {"share_with_reviewer": True}},
                       headers={**h, "Idempotency-Key": "k" * 16})
    assert sent.status_code in (200, 201), sent.json
    assert client.get(f"/api/v1/drafts/{d['draft_id']}/voice-fill/plan", headers=h).status_code == 409


# ---------------------------------------------------------------- documents by voice

@pytest.mark.parametrize("lang,text,status", [
    ("en", "I have it", "available"), ("en", "yes", "available"), ("en", "uh-huh", "available"), ("en", "no", "missing"),
    ("en", "I don't have it", "missing"), ("en", "I lost it", "missing"), ("en", "it has expired", "expired"),
    ("en", "I'm not sure", "unknown"), ("hi", "हाँ है", "available"), ("hi", "नहीं है", "missing"), ("hi", "पता नहीं", "unknown"),
    ("hi", "यह समाप्त हो गया है", "expired"), ("te", "అవును", "available"), ("te", "లేదు", "missing"),
])
def test_document_answers(client, lang, text, status):
    sid = client.post("/api/v1/sessions", json={"mode": "personal", "language": lang}).json["session_id"]
    r = client.post(f"/api/v1/sessions/{sid}/documents/parse-answer", json={"utterance": text, "language": lang})
    assert r.status_code == 200 and r.json["status"] == status and r.json["understood"], (text, r.json)


def test_a_question_or_noise_is_not_a_document_answer(client):
    sid = client.post("/api/v1/sessions", json={"mode": "personal", "language": "en"}).json["session_id"]
    for text in ("why do you need this?", "blah blah"):
        r = client.post(f"/api/v1/sessions/{sid}/documents/parse-answer", json={"utterance": text, "language": "en"}).json
        assert r["status"] is None and not r["understood"]
    r = client.post(f"/api/v1/sessions/{sid}/documents/parse-answer", json={"utterance": "my aadhaar is 1234 5678 9012", "language": "en"}).json
    assert r["status"] is None and "Aadhaar" in r["message"]
