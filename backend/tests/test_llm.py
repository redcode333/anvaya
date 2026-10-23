"""LLM extraction with mocked HTTP: provider fallback, budgets, quota/circuit state, validation, merge safety rules,
privacy gate, cache and logging. No real provider is ever called here (live checks: tests/test_llm_live.py)."""
import json
import logging
import time

import pytest
import requests

from anvaya import metrics, testrunner
from anvaya.db import get_db
from anvaya.llm import client as llm_client
from anvaya.llm import merge, state
from anvaya.llm import validate

GROQ_KEY, GEMINI_KEY = "gsk_test_key_never_logged", "AIza_test_key_never_logged"
GROQ = {"name": "groq", "kind": "openai", "base_url": "https://groq.test/openai/v1", "api_key": GROQ_KEY,
        "model": "groq-model", "daily_requests": 0, "reasoning_effort": "low"}
GEMINI = {"name": "gemini", "kind": "openai", "base_url": "https://gemini.test/v1beta/openai/", "api_key": GEMINI_KEY,
          "model": "gemini-model", "daily_requests": 0, "reasoning_effort": ""}
CONFIG_KEYS = ("LLM_EXTRACTION", "LLM_PROVIDERS", "LLM_ALLOW_REAL_DATA", "LLM_TURN_BUDGET_S", "LLM_CALL_TIMEOUT_S",
               "VERBX_BASE_URL", "VERBX_API_KEY")
BIHAR = "I am 62 years old, BPL household, I do not get any pension. I live in Bihar."


class Resp:
    def __init__(self, status=200, body=None, text=None, headers=None):
        self.status_code, self.ok = status, status < 400
        self._body = body
        self.text = text if text is not None else json.dumps(body)
        self.headers = {"Content-Type": "application/json", **(headers or {})}

    def json(self):
        if self._body is None:
            raise ValueError("not json")
        return self._body


def completion(content: str) -> Resp:
    return Resp(200, {"choices": [{"message": {"role": "assistant", "content": content}}],
                      "usage": {"prompt_tokens": 321, "completion_tokens": 45}})


def facts(*items) -> Resp:
    return completion(json.dumps({"facts": [{"attribute": a, "value": v, "evidence": e} for a, v, e in items]},
                                 ensure_ascii=False))


class FakeHTTP:
    """Routes requests.post by host: groq.test / gemini.test / verbx.test, each answering from its own queue
    (then its default). Items may be Resp, an exception, or a zero-argument callable returning either."""

    def __init__(self):
        self.calls, self.queues, self.default = [], {"groq": [], "gemini": [], "verbx": []}, {}

    def __call__(self, url, headers=None, json=None, timeout=None):
        name = next(n for n in self.queues if f"{n}.test" in url)
        self.calls.append({"provider": name, "url": url, "headers": headers, "json": json, "timeout": timeout})
        item = self.queues[name].pop(0) if self.queues[name] else self.default.get(name)
        if callable(item):
            item = item()
        if item is None:
            raise AssertionError(f"unexpected call to {name}")
        if isinstance(item, Exception):
            raise item
        return item

    def n(self, name):
        return sum(c["provider"] == name for c in self.calls)


def metric(counter, **labels) -> float:
    return counter.labels(**labels)._value.get()


@pytest.fixture()
def fake(app, monkeypatch):
    saved = {k: app.config[k] for k in CONFIG_KEYS}
    app.config.update(LLM_EXTRACTION=True, LLM_PROVIDERS=[dict(GROQ), dict(GEMINI)], LLM_ALLOW_REAL_DATA=True,
                      LLM_TURN_BUDGET_S=7.0, LLM_CALL_TIMEOUT_S=6.0, VERBX_BASE_URL="", VERBX_API_KEY="")
    http = FakeHTTP()
    monkeypatch.setattr(llm_client.requests, "post", http)
    with app.app_context():
        db = get_db()
        for table in ("llm_cache", "llm_provider_state", "translations"):
            db.execute(f"DELETE FROM {table}")
        db.commit()
    state.reset_memory()
    llm_client._NO_JSON_MODE.clear()
    yield http
    app.config.update(saved)
    state.reset_memory()


def new_session(client, lang="en", **extra):
    return client.post("/api/v1/sessions", json={"mode": "personal", "language": lang, **extra}).json["session_id"]


def say(client, sid, utterance, channel="text"):
    r = client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": utterance, "channel": channel})
    assert r.status_code == 200, r.json
    return r.json


def by_attr(r):
    return {f["attribute"]: f for f in r["extracted"]}


# ---------------------------------------------------------------- fallback

@pytest.mark.parametrize("failure,kind", [
    (Resp(429, {"error": {"message": "Rate limit reached for model on tokens per minute (TPM). Please try again in 2s."}},
          headers={"retry-after": "2"}), "rate_limited"),
    (Resp(503, {"error": {"message": "over capacity"}}), "server_error"),
    (requests.Timeout("read timed out"), "timeout"),
])
def test_fallback_groq_to_gemini(client, fake, failure, kind):
    fake.queues["groq"] = [failure]
    fake.queues["gemini"] = [facts(("age", "62", "I am 62 years old"))]
    before = metric(metrics.LLM_FALLBACKS, **{"from": "groq", "to": "gemini"})
    r = say(client, new_session(client), BIHAR)
    assert r["llm"]["result"] == "ok" and r["llm"]["provider"] == "gemini"
    assert r["llm"]["merge"] == {"age": "agree"}
    assert (fake.n("groq"), fake.n("gemini")) == (1, 1)
    assert metric(metrics.LLM_FALLBACKS, **{"from": "groq", "to": "gemini"}) == before + 1
    assert metric(metrics.LLM_CALLS, provider="groq", result=kind) >= 1


def test_invalid_json_retried_once_with_error_then_falls_back(client, fake):
    fake.queues["groq"] = [completion("Sure! Here are the facts: age 62"), completion('{"facts": "age 62"}')]
    fake.queues["gemini"] = [facts(("age", "62", "I am 62 years old"))]
    r = say(client, new_session(client), BIHAR)
    assert r["llm"]["provider"] == "gemini" and fake.n("groq") == 2
    retry = [c for c in fake.calls if c["provider"] == "groq"][1]["json"]["messages"]
    assert retry[-2]["role"] == "assistant" and "That reply was invalid: not valid JSON" in retry[-1]["content"]


def test_invalid_json_then_valid_on_retry_stays_on_first_provider(client, fake):
    fake.queues["groq"] = [completion("not json"), facts(("age", "62", "I am 62 years old"))]
    r = say(client, new_session(client), BIHAR)
    assert r["llm"]["provider"] == "groq" and fake.n("groq") == 2 and fake.n("gemini") == 0


def test_json_mode_rejected_falls_back_to_plain_instructions(client, fake):
    fake.queues["groq"] = [Resp(400, {"error": {"message": "response_format is not supported"}}),
                           facts(("age", "62", "I am 62 years old"))]
    r = say(client, new_session(client), BIHAR)
    first, second = [c["json"] for c in fake.calls if c["provider"] == "groq"]
    assert "response_format" in first and "response_format" not in second
    assert r["llm"]["provider"] == "groq" and "groq" in llm_client._NO_JSON_MODE


def test_request_shape_and_auth(client, fake):
    fake.queues["groq"] = [facts()]
    say(client, new_session(client), BIHAR)
    call = fake.calls[0]
    assert call["url"] == "https://groq.test/openai/v1/chat/completions"
    assert call["headers"]["Authorization"] == f"Bearer {GROQ_KEY}"
    body = call["json"]
    assert body["model"] == "groq-model" and body["response_format"] == {"type": "json_object"}
    assert body["reasoning_effort"] == "low" and body["temperature"] == 0
    assert body["messages"][0]["role"] == "system" and "evidence" in body["messages"][0]["content"]
    assert json.loads(body["messages"][1]["content"]) == {"original_message": BIHAR}
    assert call["timeout"] <= 6.0


# ---------------------------------------------------------------- all down / budget

def _tc_outcomes(app):
    with app.app_context():
        out = {}
        for tc in ("TC1", "TC2", "TC3", "TC4"):
            run = testrunner.run(tc)
            assert run["passed"], [c for c in run["checks"] if not c["passed"]]
            out[tc] = [c["passed"] for c in run["checks"]]
        return out


def test_all_providers_down_gives_deterministic_results_and_same_tc_outcomes(app, client, fake):
    app.config["LLM_EXTRACTION"] = False
    baseline_turn = say(client, new_session(client), BIHAR)
    baseline_tc = _tc_outcomes(app)

    app.config["LLM_EXTRACTION"] = True
    fake.default = {"groq": requests.ConnectionError("down"), "gemini": Resp(500, {"error": {}})}
    r = say(client, new_session(client), BIHAR)
    assert r["llm"]["result"] == "all_failed" and not r["llm"]["used"]
    strip = lambda t: {f["attribute"]: (f["value"], f["confirmed"], f["source"]) for f in t["extracted"]}
    assert strip(r) == strip(baseline_turn)
    assert r["reply"] == baseline_turn["reply"]
    assert _tc_outcomes(app) == baseline_tc
    assert fake.n("groq") > 0 and fake.n("gemini") > 0  # the TC runner's test sessions did try the LLM


def test_turn_budget_exceeded_returns_deterministic_only(app, client, fake):
    app.config.update(LLM_TURN_BUDGET_S=1.0)

    def slow_timeout():
        time.sleep(0.6)
        return requests.Timeout("slow")

    fake.queues["groq"] = [slow_timeout]  # leaves < 0.5 s, so gemini is never started
    r = say(client, new_session(client), BIHAR)
    assert r["llm"]["result"] == "budget_exceeded" and fake.n("gemini") == 0
    assert by_attr(r)["age"]["source"] == "text"


def test_answer_arriving_after_budget_is_discarded(app, client, fake):
    app.config.update(LLM_TURN_BUDGET_S=0.8)

    def slow_answer():
        time.sleep(0.9)
        return facts(("household_size", "5", "I am 62 years old"))

    fake.queues["groq"] = [slow_answer]
    r = say(client, new_session(client), BIHAR)
    assert r["llm"]["result"] == "budget_exceeded"
    assert "household_size" not in by_attr(r)


def test_each_call_timeout_is_capped_by_remaining_budget(app, client, fake):
    app.config.update(LLM_TURN_BUDGET_S=2.0)
    fake.queues["groq"] = [facts()]
    say(client, new_session(client), BIHAR)
    assert fake.calls[0]["timeout"] <= 2.0


# ---------------------------------------------------------------- quota & circuit breaker

def test_daily_quota_429_marks_provider_exhausted_in_db(app, client, fake):
    fake.queues["groq"] = [Resp(429, {"error": {"message": "Rate limit reached for model `x` on requests per day (RPD): "
                                                           "Limit 1000, Used 1000, Requested 1."}},
                                headers={"x-ratelimit-remaining-requests": "0", "x-ratelimit-reset-requests": "2h"})]
    fake.default["gemini"] = facts()
    say(client, new_session(client), BIHAR)
    say(client, new_session(client), "I am 40 years old and live in Punjab")
    assert fake.n("groq") == 1 and fake.n("gemini") == 2
    with app.app_context():
        row = get_db().execute("SELECT exhausted_until FROM llm_provider_state WHERE provider='groq'").fetchone()
    assert row and row[0]
    ready = {p["name"]: p for p in client.get("/api/v1/ready").json["llm_extraction"]["providers"]}
    assert ready["groq"]["status"] == "exhausted" and ready["groq"]["exhausted_until"]
    assert ready["gemini"]["status"] == "ok"


def test_gemini_quota_without_hint_resets_at_pacific_midnight():
    err = llm_client._rate_limit_error(GEMINI, {}, '[{"error": {"code": 429, "message": "You exceeded your current '
                                                   'quota ... GenerateRequestsPerDayPerProjectPerModel-FreeTier", '
                                                   '"status": "RESOURCE_EXHAUSTED"}}]')
    assert err.kind == "quota_exhausted" and err.reset_at.hour == 8 and err.reset_at.minute == 0


def test_plain_429_is_not_quota():
    assert llm_client._rate_limit_error(GROQ, {"retry-after": "3"}, "Rate limit reached on tokens per minute").kind \
        == "rate_limited"


def test_soft_daily_cap_marks_exhausted(app, client, fake):
    app.config["LLM_PROVIDERS"][0]["daily_requests"] = 1
    fake.default = {"groq": facts(), "gemini": facts()}
    say(client, new_session(client), BIHAR)
    say(client, new_session(client), "I am 41 years old and live in Punjab")
    assert fake.n("groq") == 1 and fake.n("gemini") == 1


def test_circuit_opens_after_five_consecutive_failures(app, client, fake):
    fake.default = {"groq": Resp(502, {}), "gemini": facts()}
    for i in range(5):
        say(client, new_session(client), f"I am {30 + i} years old and live in Bihar")
    assert fake.n("groq") == 5
    say(client, new_session(client), "I am 50 years old and live in Bihar")
    assert fake.n("groq") == 5  # skipped while open
    ready = {p["name"]: p["status"] for p in client.get("/api/v1/ready").json["llm_extraction"]["providers"]}
    assert ready["groq"] == "open-circuit"
    app.config["LLM_CIRCUIT_OPEN_S"], saved = 0.0, app.config["LLM_CIRCUIT_OPEN_S"]
    try:
        state.reset_memory()
        fake.default["groq"] = facts()
        say(client, new_session(client), "I am 51 years old and live in Bihar")
        assert fake.n("groq") == 6
    finally:
        app.config["LLM_CIRCUIT_OPEN_S"] = saved


def test_ready_never_shows_keys(client, fake):
    body = client.get("/api/v1/ready").json["llm_extraction"]
    text = json.dumps(body)
    assert GROQ_KEY not in text and GEMINI_KEY not in text and "api_key" not in text
    assert [p["status"] for p in body["providers"]] == ["configured", "configured"]
    assert body["prompt_version"].startswith("extract-v1")


# ---------------------------------------------------------------- validation & merge

def test_evidence_not_in_utterance_is_dropped(client, fake):
    before = metric(metrics.LLM_MERGE, outcome="dropped_evidence")
    fake.queues["groq"] = [facts(("household_size", "5", "we are five people"), ("area", "rural", "I live in Bihar"),
                                 ("occupation", "farmer", "BPL household"))]
    r = say(client, new_session(client), BIHAR)
    got = by_attr(r)
    assert "household_size" not in got  # evidence never said
    assert got["area"]["source"] == "llm"  # evidence is a real span (the model's inference is still unconfirmed)
    assert r["llm"]["dropped"] == ["evidence"]
    assert metric(metrics.LLM_MERGE, outcome="dropped_evidence") == before + 1


def test_invalid_values_and_unknown_attributes_are_dropped(client, fake):
    fake.queues["groq"] = [facts(("age", "two hundred", "I am 62 years old"), ("applicant_name", "Ravi", "I am"),
                                 ("gender", "robot", "I am 62"))]
    r = say(client, new_session(client), BIHAR)
    assert r["llm"]["dropped"] == ["invalid", "invalid", "invalid"]
    assert by_attr(r)["age"]["source"] == "text"


def test_llm_only_fact_is_unconfirmed_candidate_and_agreement_is_noted(client, fake):
    fake.queues["groq"] = [facts(("age", "62", "I am 62 years old"), ("gender", "male", "I am 62 years old"),
                                 ("area", "rural", "BPL household"))]
    r = say(client, new_session(client), BIHAR)
    got = by_attr(r)
    assert "Confirmed by both" in got["age"]["note"] and got["age"]["source"] == "text"
    for a in ("gender", "area"):
        assert got[a]["source"] == "llm" and got[a]["inferred"] and not got[a]["confirmed"]
    assert r["llm"]["merge"] == {"age": "agree", "gender": "llm_only", "area": "llm_only"}
    assert got["area"]["confirm_individually"]  # area is high-impact


def test_llm_only_fact_never_replaces_a_held_fact(client, fake):
    sid = new_session(client)
    fake.queues["groq"] = [facts()]
    say(client, sid, BIHAR)
    fake.queues["groq"] = [facts(("bpl", "false", "no card"))]
    r = say(client, sid, "we have no card")
    profile = {f["attribute"]: f for f in client.get(f"/api/v1/sessions/{sid}").json["facts"]}
    assert profile["bpl"]["value"] is True and profile["bpl"]["source"] == "text"
    assert "bpl" not in by_attr(r)


def test_disagreement_on_high_impact_holds_both_values_in_session_language(client, fake):
    sid = new_session(client, "hi")
    fake.queues["groq"] = [facts(("age", "70", "मेरी उम्र साठ साल है"), ("state", "Bihar", "बिहार"))]
    r = say(client, sid, "मेरी उम्र साठ साल है। मैं बिहार में रहता हूँ।", channel="voice")
    age = by_attr(r)["age"]
    assert age["disputed"] and age["alternatives"] == [60, 70] and not age["confirmed"]
    assert "उम्र: 60 वर्ष या 70 वर्ष? कृपया सही चुनें।" in r["reply"]
    assert r["llm"]["merge"] == {"age": "disagree", "state": "agree"} and r["llm"]["disputed"] == ["age"]

    bulk = client.post(f"/api/v1/sessions/{sid}/profile/confirm-all").json
    assert age["fact_id"] in bulk["needs_individual_confirmation"]
    blocked = client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate")
    assert blocked.status_code == 409 and blocked.json["error"]["code"] == "PROFILE_NEEDS_CONFIRMATION"
    plain = client.patch(f"/api/v1/sessions/{sid}/profile/facts/{age['fact_id']}", json={"confirmed": True})
    assert plain.status_code == 409 and plain.json["error"]["code"] == "VALUE_DISPUTED"
    assert plain.json["error"]["details"]["alternatives"] == [60, 70]

    chosen = client.patch(f"/api/v1/sessions/{sid}/profile/facts/{age['fact_id']}", json={"value": 70}).json
    assert chosen["fact"]["value"] == 70 and chosen["fact"]["confirmed"]
    for fid in chosen["profile"]["needs_confirmation"]:
        client.patch(f"/api/v1/sessions/{sid}/profile/facts/{fid}", json={"confirmed": True})
    assert client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate").status_code == 200


def test_choosing_the_stored_value_confirms_in_place(client, fake):
    sid = new_session(client, "en")
    fake.queues["groq"] = [facts(("household_size", "5", "Family of 4"))]
    r = say(client, sid, "Family of 4, I live in Bihar")
    hh = by_attr(r)["household_size"]
    assert hh["alternatives"] == [4, 5]
    assert "Household members: 4 or 5? Please choose the right one." in r["reply"]
    res = client.patch(f"/api/v1/sessions/{sid}/profile/facts/{hh['fact_id']}", json={"value": 4}).json
    assert res["fact"]["fact_id"] == hh["fact_id"] and res["fact"]["confirmed"] and not res["fact"]["disputed"]


def test_disagreement_on_low_impact_keeps_deterministic_but_not_auto_confirmed(client, fake):
    fake.queues["groq"] = [facts(("occupation", "labourer", "a farmer"))]
    r = say(client, new_session(client), "I am a farmer in Bihar")
    occ = by_attr(r)["occupation"]
    assert occ["value"] == "farmer" and not occ["confirmed"] and not occ["disputed"] and "labourer" in occ["note"]


def test_relative_age_rule_applies_to_llm_facts(client, fake):
    fake.queues["groq"] = [facts(("age", "70", "My father is 70 years old"))]
    r = say(client, new_session(client), "My father is 70 years old")
    assert "age" not in by_attr(r) and r["llm"]["merge"] == {"age": "dropped_relative"}
    # The deterministic extractor found no age here, but the LLM's own evidence names the relative.
    fake.queues["groq"] = [facts(("age", "45", "my wife, she is 45"))]
    r = say(client, new_session(client), "I live with my wife, she is 45")
    assert "age" not in by_attr(r) and r["llm"]["merge"] == {"age": "dropped_relative"}


def test_confusable_spoken_number_rule_applies_to_llm_facts(client, fake):
    fake.queues["groq"] = [facts(("age", "60", "मैं साठ का हूँ"))]
    r = say(client, new_session(client, "hi"), "मैं साठ का हूँ")
    age = by_attr(r)["age"]
    assert age["source"] == "llm" and age["confusable"] and age["confirm_individually"]
    assert "सत्तर" in r["reply"]  # read back with the number it can be confused with


def test_merge_is_pure_and_keeps_deterministic_primary():
    det = [{"attribute": "age", "value": 60, "note": None, "high_impact": True},
           {"attribute": "state", "value": "Bihar", "note": None, "high_impact": True}]
    out, info = merge.merge(det, [{"attribute": "age", "value": 70, "evidence": "साठ"},
                                  {"attribute": "state", "value": "Bihar", "evidence": "बिहार"}], [])
    assert det[0].get("alternatives") is None  # inputs untouched
    assert out[0]["value"] == 60 and out[0]["alternatives"] == [60, 70] and info["disputed"] == ["age"]


@pytest.mark.parametrize("utterance,evidence", [
    ("Tell me about the widow pension. I am 67 years old and live in Bihar.", "widow pension"),
    ("Tell me about the widow pension. I am 67 years old and live in Bihar.", "widow"),
    ("विधवा पेंशन के बारे में बताइए। मेरी उम्र 64 साल है।", "विधवा पेंशन"),
    ("వితంతు పింఛను గురించి చెప్పండి. నా వయస్సు 61 సంవత్సరాలు.", "వితంతు పింఛను"),
])
def test_merge_drops_widowed_read_from_a_scheme_name(utterance, evidence):
    from anvaya import extraction
    det = extraction.extract(utterance)
    out, info = merge.merge(det["facts"], [{"attribute": "marital_status", "value": "widowed", "evidence": evidence},
                                           {"attribute": "gender", "value": "female", "evidence": evidence}],
                            det["other_people"], utterance)
    attrs = {f["attribute"] for f in out}
    assert "marital_status" not in attrs and "gender" not in attrs
    assert info["outcomes"] == {"marital_status": "dropped_scheme_name", "gender": "dropped_scheme_name"}


@pytest.mark.parametrize("utterance,evidence", [
    ("मैं विधवा हूँ, विधवा पेंशन चाहिए।", "मैं विधवा हूँ"),
    ("My husband passed away. Tell me about the widow pension.", "husband passed away"),
    ("నేను వితంతువును, వితంతు పింఛను కావాలి.", "నేను వితంతువును"),
])
def test_merge_keeps_widowed_when_the_speaker_says_so(utterance, evidence):
    out, info = merge.merge([], [{"attribute": "marital_status", "value": "widowed", "evidence": evidence}], [], utterance)
    assert out[0]["value"] == "widowed" and info["outcomes"] == {"marital_status": "llm_only"}


def test_parse_accepts_fenced_json_and_rejects_bad_shapes():
    assert validate.parse('```json\n{"facts": []}\n```') == []
    for bad in ("[]", '{"facts": {}}', '{"facts": [{"attribute": "age"}]}', "nope"):
        with pytest.raises(validate.InvalidOutput):
            validate.parse(bad)


# ---------------------------------------------------------------- translation input

def test_hindi_utterance_sent_with_verbx_translation_and_evidence_may_come_from_it(app, client, fake):
    app.config.update(VERBX_BASE_URL="https://verbx.test", VERBX_API_KEY="vx_key")
    fake.queues["verbx"] = [Resp(200, {"text": "I am sixty two years old.", "degraded": False,
                                       "diagnostics": {"model": "verbx-langshift"}})]
    fake.queues["groq"] = [facts(("household_size", "3", "sixty two years old"))]
    r = say(client, new_session(client, "hi"), "मेरी उम्र बासठ साल है")
    sent = json.loads([c for c in fake.calls if c["provider"] == "groq"][0]["json"]["messages"][1]["content"])
    assert sent == {"original_message": "मेरी उम्र बासठ साल है", "english_translation": "I am sixty two years old."}
    assert r["llm"]["translated"] and "household_size" in by_attr(r)
    verbx_call = next(c for c in fake.calls if c["provider"] == "verbx")
    assert verbx_call["json"] == {"text": "मेरी उम्र बासठ साल है", "source_lang": "hi", "target_lang": "en"}


def test_translation_failure_sends_original_only(app, client, fake):
    app.config.update(VERBX_BASE_URL="https://verbx.test", VERBX_API_KEY="vx_key")
    fake.queues["verbx"] = [Resp(503, {})]
    fake.queues["groq"] = [facts()]
    r = say(client, new_session(client, "te"), "నా వయస్సు 67 సంవత్సరాలు")
    sent = json.loads([c for c in fake.calls if c["provider"] == "groq"][0]["json"]["messages"][1]["content"])
    assert sent == {"original_message": "నా వయస్సు 67 సంవత్సరాలు"} and r["llm"]["result"] == "ok"
    assert fake.n("verbx") == 1  # one attempt only inside the turn budget


# ---------------------------------------------------------------- privacy gate

def test_real_data_never_sent_unless_allowed(app, client, fake):
    app.config["LLM_ALLOW_REAL_DATA"] = False
    fake.default = {"groq": facts()}
    r = say(client, new_session(client), BIHAR)
    assert r["llm"] == {"used": False, "result": "real_data_not_allowed"} and fake.n("groq") == 0

    r = say(client, new_session(client, demo=True), BIHAR)  # session created with "demo": true
    assert r["llm"]["result"] == "ok" and fake.n("groq") == 1

    demo = json.load(open(app.root_path + "/data/demo_phrases.json", encoding="utf-8"))["en"][1]["text"]
    r = say(client, new_session(client), demo)  # kiosk demo phrase in an ordinary session
    assert r["llm"]["result"] == "ok" and fake.n("groq") == 2

    with app.app_context():
        testrunner.run("TC4")  # TC-runner sessions are test data
    assert fake.n("groq") == 3


def test_demo_flag_is_returned_on_session_create(client, fake):
    r = client.post("/api/v1/sessions", json={"mode": "personal", "language": "en", "demo": True}).json
    assert r["demo"] is True
    r = client.post("/api/v1/sessions", json={"mode": "personal", "language": "en", "demo": "yes"}).json
    assert r["demo"] is False


# ---------------------------------------------------------------- cache & logs

def test_cache_hit_avoids_second_call(client, fake):
    fake.queues["groq"] = [facts(("age", "62", "I am 62 years old"))]
    before = metric(metrics.LLM_CALLS, provider="groq", result="cache_hit")
    first = say(client, new_session(client), BIHAR)
    second = say(client, new_session(client), BIHAR)
    assert fake.n("groq") == 1 and not first["llm"]["cached"] and second["llm"]["cached"]
    assert second["llm"]["merge"] == first["llm"]["merge"]
    assert metric(metrics.LLM_CALLS, provider="groq", result="cache_hit") == before + 1


def test_cache_from_a_fallback_provider_is_used_first(client, fake):
    fake.queues["groq"] = [Resp(500, {})]
    fake.queues["gemini"] = [facts(("age", "62", "I am 62 years old"))]
    say(client, new_session(client), BIHAR)
    r = say(client, new_session(client), BIHAR)
    assert r["llm"]["cached"] and r["llm"]["provider"] == "gemini" and fake.n("groq") == 1


def test_logs_never_contain_utterance_prompt_output_or_keys(app, client, fake, caplog):
    caplog.set_level(logging.DEBUG)
    app.config.update(VERBX_BASE_URL="https://verbx.test", VERBX_API_KEY="vx_secret_key")
    secret_utterance = "मेरी उम्र साठ साल है और मेरा नाम गुप्तनाम है"
    fake.queues["verbx"] = [Resp(200, {"text": "SECRET-TRANSLATION sixty", "diagnostics": {}})]
    fake.queues["groq"] = [completion("SECRET-BAD-OUTPUT"), completion("SECRET-BAD-OUTPUT-2")]
    fake.queues["gemini"] = [facts(("age", "60", "मेरी उम्र साठ साल है"))]
    say(client, new_session(client, "hi"), secret_utterance)
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "provider=groq model=groq-model result=invalid_output" in logged
    assert "provider=gemini model=gemini-model result=ok status=200" in logged and "prompt_tokens=321" in logged
    for secret in (secret_utterance, "साठ", "गुप्तनाम", "SECRET-TRANSLATION", "SECRET-BAD-OUTPUT", GROQ_KEY, GEMINI_KEY,
                   "vx_secret_key", "evidence"):
        assert secret not in logged


def test_anthropic_is_optional_and_lazily_imported(app, client, fake, monkeypatch):
    import builtins

    real_import = builtins.__import__

    def no_anthropic(name, *a, **kw):
        if name == "anthropic":
            raise ImportError("not installed")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", no_anthropic)
    app.config["LLM_PROVIDERS"] = [{"name": "anthropic", "kind": "anthropic", "base_url": "", "api_key": "sk-ant-x",
                                    "model": "claude-x", "daily_requests": 0, "reasoning_effort": ""}, dict(GEMINI)]
    fake.queues["gemini"] = [facts()]
    r = say(client, new_session(client), BIHAR)
    assert r["llm"]["provider"] == "gemini"
    assert metric(metrics.LLM_CALLS, provider="anthropic", result="not_installed") >= 1
