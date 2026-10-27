"""A phone-call style conversation: short answers, one spoken "yes" for the read-back, no confirmation for plain
yes/no answers. The Hindi exchange follows a real demo transcript."""
from anvaya import i18n


def _say(client, sid, text, channel="voice"):
    r = client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": text, "channel": channel})
    assert r.status_code == 200, r.json
    return r.json


def _facts(client, sid):
    return {f["attribute"]: f for f in client.get(f"/api/v1/sessions/{sid}").json["facts"]}


def _msg(key, lang="hi", **kw):
    return i18n.t(i18n.MESSAGES, key, lang, **kw)


def _session(client, lang="hi"):
    return client.post("/api/v1/sessions", json={"mode": "personal", "language": lang}).json["session_id"]


INTRO = ("हेलो मेरा नाम अमन अग्रवाल मैं सुंदरनगर में रहता हूँ जमशेदपुर झारखंड भारत मेरी उम्र चौबीस साल है "
         "मुझे सारी योजनाओं के बारे में बताइए जिसके लिए मैं एलिजिबल हूँ")


def test_the_whole_call_needs_one_yes_per_group_of_important_facts(client):
    sid = _session(client)
    r = _say(client, sid, INTRO)
    f = _facts(client, sid)
    assert (f["age"]["value"], f["state"]["value"], f["gender"]["value"]) == (24, "Jharkhand", "male")
    # Read back with one spoken question; the next question waits until it is answered.
    assert r["reply_segments"][-1] == _msg("confirm_question")
    assert not r["next_question"] or r["reply_segments"][-1] != r["next_question"]["text"]
    assert not f["age"]["confirmed"]

    r = _say(client, sid, "हाँ")
    f = _facts(client, sid)
    assert f["age"]["confirmed"] and f["state"]["confirmed"] and f["gender"]["confirmed"]
    assert r["reply_segments"][0] == _msg("okay")
    assert r["next_question"]["attribute"] == "annual_income"

    r = _say(client, sid, "साढ़े चार लाख")
    assert _facts(client, sid)["annual_income"]["value"] == 450000
    assert r["reply_segments"][-1] == _msg("confirm_question")
    r = _say(client, sid, "जी हाँ")
    assert _facts(client, sid)["annual_income"]["confirmed"] and r["next_question"]["attribute"] == "household_size"

    _say(client, sid, "चार")
    assert _facts(client, sid)["household_size"]["value"] == 4
    r = _say(client, sid, "हाँ सही है")
    assert r["next_question"]["attribute"] == "bpl"

    # A plain yes/no to a direct question is taken as heard: no read-back, straight to the next question.
    r = _say(client, sid, "नहीं")
    f = _facts(client, sid)
    assert f["bpl"]["value"] is False and f["bpl"]["confirmed"]
    assert _msg("confirm_question") not in r["reply_segments"]
    assert r["next_question"]["attribute"] == "marital_status"  # area and gender were already heard in the intro
    assert client.get(f"/api/v1/sessions/{sid}").json["needs_confirmation"] == []


def test_saying_no_to_the_read_back_asks_for_the_right_value(client):
    sid = _session(client)
    _say(client, sid, "मेरी उम्र चौबीस साल है")
    r = _say(client, sid, "नहीं")
    assert _msg("correct_it", label=i18n.t(i18n.ATTRIBUTE_LABELS, "age", "hi")) in r["reply_segments"]
    assert not _facts(client, sid)["age"]["confirmed"]
    # The corrected age is read back again, and a bare number now means the age.
    r = _say(client, sid, "पच्चीस")
    assert _facts(client, sid)["age"]["value"] == 25
    assert r["reply_segments"][-1] == _msg("confirm_question")


def test_stating_the_value_again_confirms_it(client):
    sid = _session(client)
    _say(client, sid, "मेरी उम्र चौबीस साल है")
    _say(client, sid, "हाँ उम्र चौबीस साल है")
    assert _facts(client, sid)["age"]["confirmed"]


def test_a_changed_value_instead_of_a_yes_is_not_confirmed(client):
    sid = _session(client)
    _say(client, sid, "मेरी उम्र चौबीस साल है")
    _say(client, sid, "नहीं पच्चीस साल है")
    f = _facts(client, sid)["age"]
    assert f["value"] == 25 and not f["confirmed"]


def test_a_bare_yes_with_nothing_to_confirm_changes_nothing(client):
    sid = _session(client)
    r = _say(client, sid, "हाँ")
    assert _facts(client, sid) == {}
    assert r["reply_segments"]


def test_the_bot_hints_at_yes_or_no_after_a_misheard_answer(client):
    sid = _session(client)
    _say(client, sid, "मेरी उम्र चौबीस साल है और मैं झारखंड में रहता हूँ")
    _say(client, sid, "हाँ")
    _say(client, sid, "साढ़े चार लाख")
    _say(client, sid, "हाँ")
    _say(client, sid, "चार")
    _say(client, sid, "हाँ")  # now asking about BPL
    r = _say(client, sid, "कानर डाल लो फिर")
    assert _msg("answer_yes_no") in r["reply_segments"]


def test_typed_chat_is_unchanged_and_still_uses_the_card(client):
    sid = _session(client, "en")
    r = _say(client, sid, "I am 62 years old. I live in Bihar.", channel="text")
    assert i18n.t(i18n.MESSAGES, "please_confirm", "en") in r["reply_segments"]
    assert not _facts(client, sid)["age"]["confirmed"]
