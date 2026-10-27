"""A real voice conversation that went wrong (speech-recognition spellings, a greeting treated as off-topic, "uh-huh" not taken
as yes, the same "could not pick out" reply five times) replayed turn by turn, plus the pieces it exposed."""
import pytest

from anvaya import extraction, guardrails


def say(client, sid, text, lang="en"):
    r = client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": text, "channel": "voice", "language": lang})
    assert r.status_code == 200, r.json
    return r.json


@pytest.fixture()
def sid(client):
    return client.post("/api/v1/sessions", json={"mode": "personal", "language": "en"}).json["session_id"]


def facts(client, sid):
    return {f["attribute"]: f for f in client.get(f"/api/v1/sessions/{sid}").json["facts"]}


def test_the_conversation_that_went_wrong(client, sid):
    # A greeting is answered, not refused as off-topic.
    r = say(client, sid, "Hello, how are you?")
    assert r["guardrail"] == "smalltalk" and "can't answer that" not in r["reply"]
    assert "Which state" in r["reply"]
    # The name is taken.
    assert say(client, sid, "My name is Amina")["extracted"][0]["attribute"] == "applicant_name"
    # Noise: the first miss is a short "say it another way", the second gives tips instead of repeating itself.
    first = say(client, sid, "latency is slaying")
    assert "could not pick out" in first["reply"]
    second = say(client, sid, "जॉ करना पड़ेगा तम ये प्रोफाइल प रहे तो देखो")
    assert "still not catching that" in second["reply"] and "could not pick out" not in second["reply"]
    # Words about logging in (here, mangled Hindi) are answered as the login question they most likely are.
    assert say(client, sid, "तमें उनको लॉगइन कराना फोन")["guardrail"] == "login"
    # "Where do I log in?" gets a real answer: no account is needed.
    r = say(client, sid, "What? You wrote Amina, right? Where do I log in? Why don't you log in?")
    assert r["guardrail"] == "login" and "don't need to log in" in r["reply"] and "Which state" in r["reply"]
    # The state, said the way speech recognition spelled it, is understood and read back for a yes.
    r = say(client, sid, "यस मैं झारखणंड में रहता हूँ", lang="en")
    state = next(f for f in r["extracted"] if f["attribute"] == "state")
    assert state["value"] == "Jharkhand" and not state["confirmed"]
    assert "Jharkhand" in r["reply"] and "Is that right" in r["reply"] or "right" in r["reply"].lower()
    # "Uh-huh" is a yes: everything that was read out is confirmed.
    r = say(client, sid, "Uh-huh.")
    assert "could not pick out" not in r["reply"]
    assert facts(client, sid)["state"]["confirmed"]


def test_charkhand_is_jharkhand_and_asks_for_confirmation(client, sid):
    r = say(client, sid, "I live in Charkhand.")
    state = next(f for f in r["extracted"] if f["attribute"] == "state")
    assert state["value"] == "Jharkhand" and not state["confirmed"]
    assert "Jharkhand" in r["reply"]


@pytest.mark.parametrize("text,state", [
    ("I live in Jarkhand", "Jharkhand"), ("मैं झारखणंड में रहता हूँ", "Jharkhand"), ("I am from Chattisgarh", "Chhattisgarh"),
    ("मैं छत्तीसगढ़ में रहती हूँ", "Chhattisgarh"), ("हम केरल से हैं", "Kerala"), ("mai Maharastra mein rehta hoon", "Maharashtra"),
])
def test_states_named_the_way_speech_recognition_spells_them(text, state):
    found = [f for f in extraction.extract(text)["facts"] if f["attribute"] == "state"]
    assert found and found[0]["value"] == state


@pytest.mark.parametrize("text", ["I like the goal", "my name is Amina", "we have a goat", "assamese food", "I work in a school", "latency is slaying"])
def test_ordinary_words_are_not_taken_for_states(text):
    assert not [f for f in extraction.extract(text)["facts"] if f["attribute"] == "state"]


@pytest.mark.parametrize("text,expected", [
    ("Uh-huh.", True), ("uh huh", True), ("mm-hmm", True), ("mhm", True), ("yup", True), ("Uh-uh", False), ("nah", False),
    ("not sure", None), ("hmm", None),
])
def test_spoken_yes_and_no_sounds(text, expected):
    assert extraction.polarity(text) is expected


@pytest.mark.parametrize("text,kind", [
    ("Hello, how are you?", "smalltalk"), ("how are you doing today", "smalltalk"), ("hi there", "smalltalk"), ("आप कैसे हैं", "smalltalk"),
    ("thank you so much", "smalltalk"), ("where do I log in?", "login"), ("how do I sign up", "login"), ("क्या मुझे लॉगइन करना पड़ेगा", "login"),
    ("Uh-huh.", "ack"), ("okay", "ack"), ("what is the capital of France?", "offtopic"), ("latency is slaying", "nothing_heard"),
])
def test_what_kind_of_turn_it_was(text, kind):
    assert guardrails.no_details(text) == kind


def test_a_plain_yes_with_nothing_waiting_is_acknowledged_not_refused(client, sid):
    r = say(client, sid, "uh-huh")
    assert r["guardrail"] is None and r["reply"].startswith("Okay.") and "Which state" in r["reply"]


def test_the_tips_come_back_to_the_short_message_once_something_is_understood(client, sid):
    say(client, sid, "latency is slaying")
    assert "still not catching" in say(client, sid, "blah blah")["reply"]
    assert say(client, sid, "I live in Bihar")["extracted"]
    assert "could not pick out" in say(client, sid, "latency is slaying")["reply"]  # the counter started again
