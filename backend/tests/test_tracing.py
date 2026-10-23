"""Langfuse tracing of LLM extraction: real Langfuse SDK + masking hook, spans captured by a fake (in-memory)
OpenTelemetry exporter instead of OTLP/HTTP. No test here talks to a real Langfuse."""
import json
import statistics
import subprocess
import sys
import time
import uuid

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from anvaya.llm import tracing
from test_llm import BIHAR, Resp, completion, facts, fake, new_session  # noqa: F401  (fake is a fixture)

DEMO_EN = "I am 62 years old, BPL household, I do not get any pension. I live in Maharashtra, in a city. " \
          "Family of 2, income 90000 per year."  # a kiosk demo phrase (backend/anvaya/data/demo_phrases.json)
LF_KEYS = ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL", "LANGFUSE_SPAN_EXPORTER",
           "LANGFUSE_TIMEOUT_S")


@pytest.fixture()
def exported(app):
    """Tracing on, with a fresh client whose spans go to an in-memory exporter; yields a function that flushes and
    returns the exported spans."""
    saved = {k: app.config[k] for k in LF_KEYS}
    exp = InMemorySpanExporter()
    app.config.update(LANGFUSE_PUBLIC_KEY=f"pk-lf-test-{uuid.uuid4().hex[:8]}", LANGFUSE_SECRET_KEY="sk-lf-test",
                      LANGFUSE_BASE_URL="http://127.0.0.1:9", LANGFUSE_SPAN_EXPORTER=exp)

    def spans():
        with app.app_context():
            tracing.client().flush()
        return exp.get_finished_spans()

    yield spans
    app.config.update(saved)


def turn(client, sid, utterance, channel="text", request_id=None):
    headers = {"X-Request-Id": request_id} if request_id else {}
    r = client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": utterance, "channel": channel}, headers=headers)
    assert r.status_code == 200, r.json
    return r


def by_name(spans):
    out = {}
    for s in spans:
        out.setdefault(s.name, []).append(s)
    return out


def meta(span, key, level="observation"):
    raw = span.attributes.get(f"langfuse.{level}.metadata.{key}")
    return None if raw is None else json.loads(raw)


def trace_hex(span):
    return format(span.context.trace_id, "032x")


# ---------------------------------------------------------------- off by default

def test_without_langfuse_keys_the_sdk_is_never_imported():
    code = """
import sys, os
for k in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL", "LANGFUSE_HOST"):
    os.environ.pop(k, None)
import tempfile
from anvaya import create_app
from anvaya.llm import tracing
app = create_app({"DB_PATH": tempfile.mkdtemp() + "/t.db", "TESTING": True})
with app.test_request_context():
    with tracing.turn("SES_x", True, "hello", "extract-v1.1") as tr:
        assert not tr and tr.llm_call({"name": "groq", "model": "m"}, 1, []).end("ok") is not None
    assert tracing.client() is None
print("langfuse" in sys.modules, "opentelemetry" in sys.modules)
"""
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.split() == ["False", "False"]


def test_ready_reports_langfuse_integration(app, client, exported):
    from anvaya import startup
    rep = startup.check(app.config, [])
    assert rep["integrations"]["langfuse"] == {"status": "configured", "missing": [], "effect": rep["integrations"]
                                               ["langfuse"]["effect"]}
    assert client.get("/api/v1/ready").json["integrations"]["langfuse"]["status"] == "missing"  # boot-time report


# ---------------------------------------------------------------- one trace per LLM turn

def test_demo_turn_is_one_trace_with_full_input_output(client, fake, exported):
    fake.default["groq"] = facts(("age", 62, "62 years old"), ("state", "Maharashtra", "Maharashtra"))
    sid = new_session(client, demo=True)
    rid = uuid.uuid4().hex
    r = turn(client, sid, DEMO_EN, request_id=rid)
    assert r.headers["X-Request-Id"] == rid
    spans = exported()
    names = by_name(spans)
    assert set(names) == {"extract-facts", "extract-candidate-facts", "merge-facts"}
    assert {trace_hex(s) for s in spans} == {rid}  # trace id = the request's correlation id

    root = names["extract-facts"][0]
    a = root.attributes
    assert a["langfuse.observation.type"] == "chain" and a["session.id"] == sid
    assert set(a["langfuse.trace.tags"]) == {"llm-extraction", "prompt:extract-v1.1"}
    assert meta(root, "data_class", "trace") == "demo" and meta(root, "correlation_id", "trace") == rid
    assert meta(root, "prompt_version", "trace") == "extract-v1.1"
    assert json.loads(a["langfuse.observation.input"]) == {"utterance": DEMO_EN}
    out = json.loads(a["langfuse.observation.output"])["facts"]
    assert {f["attribute"] for f in out} >= {"age", "state", "bpl"}
    assert meta(root, "result") == "ok" and meta(root, "provider") == "groq"

    gen = names["extract-candidate-facts"][0].attributes
    assert gen["langfuse.observation.type"] == "generation"
    assert gen["langfuse.observation.model.name"] == "groq-model"
    assert json.loads(gen["langfuse.observation.usage_details"]) == {"input": 321, "output": 45}
    assert json.loads(gen["langfuse.observation.metadata.provider"]) == "groq"
    assert json.loads(gen["langfuse.observation.metadata.attempt"]) == 1
    assert json.loads(gen["langfuse.observation.metadata.retry"]) is False
    assert json.loads(gen["langfuse.observation.metadata.result"]) == "ok"
    assert isinstance(json.loads(gen["langfuse.observation.metadata.latency_ms"]), int)
    assert DEMO_EN in gen["langfuse.observation.input"] and "facts" in gen["langfuse.observation.output"]

    merge = names["merge-facts"][0]
    assert meta(merge, "outcomes") == {"age": "agree", "state": "agree"}
    assert meta(merge, "counts") == {"agree": 2}


def test_non_hex_correlation_id_maps_to_a_deterministic_trace_id(client, fake, exported):
    from langfuse import Langfuse
    fake.default["groq"] = facts()
    sid = new_session(client, demo=True)
    turn(client, sid, DEMO_EN, request_id="kiosk-7/req-42")
    assert {trace_hex(s) for s in exported()} == {Langfuse.create_trace_id(seed="kiosk-7/req-42")}


def test_turns_without_the_llm_are_not_traced(client, exported):
    sid = new_session(client, demo=True)  # LLM extraction is off in the default test app
    turn(client, sid, DEMO_EN)
    assert exported() == ()


def test_retry_and_fallback_each_get_a_generation(client, fake, exported):
    fake.queues["groq"] = [completion("not json"), Resp(500, {"error": "boom"})]
    fake.default["gemini"] = facts(("age", 62, "62 years old"))
    sid = new_session(client, demo=True)
    turn(client, sid, DEMO_EN)
    gens = sorted(by_name(exported())["extract-candidate-facts"], key=lambda s: s.start_time)
    seen = [(meta(g, "provider"), meta(g, "attempt"), meta(g, "retry"), meta(g, "result"),
             g.attributes["langfuse.observation.level"]) for g in gens]
    assert seen == [("groq", 1, False, "invalid_output", "WARNING"),
                    ("groq", 2, True, "server_error", "ERROR"),
                    ("gemini", 1, False, "ok", "DEFAULT")]
    assert gens[1].attributes["langfuse.observation.status_message"] == "server_error"


def test_hindi_turn_has_a_translate_span(app, client, fake, exported):
    app.config.update(VERBX_BASE_URL="https://verbx.test", VERBX_API_KEY="vx_key")
    fake.queues["verbx"] = [Resp(200, {"text": "My age is 26 years.", "degraded": False, "diagnostics": {}})]
    fake.default["groq"] = facts(("age", 26, "26"))
    sid = new_session(client, "hi", demo=True)
    turn(client, sid, "मेरी उम्र 26 साल है। मैं बिहार के गाँव में रहता हूँ।")
    names = by_name(exported())
    tspan = names["translate-utterance"][0]
    assert tspan.attributes["langfuse.observation.type"] == "tool"
    assert json.loads(tspan.attributes["langfuse.observation.output"]) == {"text": "My age is 26 years."}
    assert meta(tspan, "source_lang") == "hi" and meta(tspan, "ok") is True
    assert meta(names["extract-facts"][0], "translated") is True


# ---------------------------------------------------------------- privacy

def test_real_session_is_metadata_only(client, fake, exported):
    """LLM_ALLOW_REAL_DATA=true (as in the `fake` fixture) lets a real citizen turn reach the LLM; its trace still
    carries no utterance, prompt, output or fact values — only structure, model, tokens, timings and outcomes."""
    fake.default["groq"] = facts(("age", 62, "62 years old"), ("state", "Bihar", "Bihar"))
    sid = new_session(client)  # not a demo session, and BIHAR is not a demo phrase
    turn(client, sid, BIHAR)
    spans = exported()
    assert {s.name for s in spans} == {"extract-facts", "extract-candidate-facts", "merge-facts"}
    for s in spans:
        assert meta(s, "data_class", "trace") == "real"
        assert not any(k.endswith((".input", ".output")) for k in s.attributes), s.name
        assert meta(s, "redacted") is True
        values = " ".join(str(v) for v in s.attributes.values())
        assert "62 years" not in values and "Bihar" not in values and "pension" not in values
    gen = by_name(spans)["extract-candidate-facts"][0]
    assert json.loads(gen.attributes["langfuse.observation.usage_details"]) == {"input": 321, "output": 45}
    assert gen.attributes["langfuse.observation.model.name"] == "groq-model"


class _Snap:
    def __init__(self, name, attrs):
        self.name, self.attributes = name, attrs


class _Params:
    def __init__(self, spans):
        self.spans = spans


def test_mask_hook_strips_leaked_content_and_fails_closed():
    leaked = {"langfuse.trace.metadata.data_class": '"real"', "langfuse.observation.input": '{"utterance": "x"}',
              "langfuse.observation.output": "y", "gen_ai.prompt.0.content": "z",
              "langfuse.observation.model.name": "m", "langfuse.observation.metadata.provider": '"groq"'}
    res = tracing.mask_spans(params=_Params({"a": _Snap("extract-facts", leaked)}))
    patch = res.span_patches["a"]
    assert set(patch.delete_attributes) == {"langfuse.observation.input", "langfuse.observation.output",
                                            "gen_ai.prompt.0.content"}
    demo = dict(leaked, **{"langfuse.trace.metadata.data_class": '"demo"'})
    assert tracing.mask_spans(params=_Params({"b": _Snap("extract-facts", demo)})).span_patches == {}
    for attrs in ({"langfuse.observation.input": "x"}, {"langfuse.trace.metadata.data_class": '"other"'}):
        with pytest.raises(tracing.MaskingError):
            tracing.mask_spans(params=_Params({"c": _Snap("unclassified", attrs)}))


def test_unclassifiable_span_drops_the_whole_batch(app, exported):
    with app.app_context():
        lf = tracing.client()
        with lf.start_as_current_observation(as_type="span", name="no-data-class", input={"secret": "x"}):
            pass
    assert exported() == ()


# ---------------------------------------------------------------- failure isolation

def _timed_turn(client, sid):
    t0 = time.perf_counter()
    turn(client, sid, DEMO_EN)
    return (time.perf_counter() - t0) * 1000


@pytest.mark.parametrize("host", ["http://127.0.0.1:9", "http://10.255.255.1:81"])  # refused / black-holed
def test_unreachable_langfuse_adds_under_50ms_and_raises_nothing(app, client, fake, host):
    """Traced and untraced turns alternate, so machine load affects both equally; the median paired difference is
    the cost tracing adds to a turn while every export fails in the background."""
    fake.default["groq"] = facts(("age", 62, "62 years old"))
    saved = {k: app.config[k] for k in LF_KEYS}
    on = dict(LANGFUSE_PUBLIC_KEY=f"pk-lf-unreachable-{uuid.uuid4().hex[:8]}", LANGFUSE_SECRET_KEY="sk-lf-test",
              LANGFUSE_BASE_URL=host, LANGFUSE_SPAN_EXPORTER=None, LANGFUSE_TIMEOUT_S=1)
    off = dict(LANGFUSE_PUBLIC_KEY="", LANGFUSE_SECRET_KEY="", LANGFUSE_BASE_URL="")
    sid = new_session(client, demo=True)
    try:
        app.config.update(on)
        with app.app_context():
            tracing.client()  # created at boot in production (create_app), not inside a turn
        for _ in range(3):
            _timed_turn(client, sid)  # warm the LLM cache and rules
        diffs = []
        for _ in range(15):
            app.config.update(off)
            untraced = _timed_turn(client, sid)
            app.config.update(on)
            diffs.append(_timed_turn(client, sid) - untraced)
    finally:
        app.config.update(saved)
    added = statistics.median(diffs)
    print(f"\n{host}: tracing adds {added:+.1f} ms per turn (median of 15 paired turns)")
    assert added < 50


# ---------------------------------------------------------------- eval → Langfuse dataset + experiments

class FakeEvalLangfuse:
    """Stands in for the Langfuse client's dataset / experiment API (those are REST calls, not OTel spans)."""

    def __init__(self):
        self.items, self.runs = {}, []

    def create_dataset(self, **kw):
        self.dataset = kw

    def create_dataset_item(self, *, dataset_name, id, input, expected_output, metadata):
        self.items[id] = {"input": input, "expected_output": expected_output}

    def get_dataset(self, name):
        fake = self

        class Item:
            def __init__(self, d):
                self.input, self.expected_output = d["input"], d["expected_output"]

        class Dataset:
            def run_experiment(self, *, name, run_name, task, evaluators, run_evaluators, **kw):
                results = []
                for d in fake.items.values():
                    item = Item(d)
                    out = task(item=item)
                    evals = [e for ev in evaluators for e in ev(input=item.input, output=out,
                                                                 expected_output=item.expected_output, metadata={})]
                    results.append(type("R", (), {"evaluations": evals})())
                runs = [e for rv in run_evaluators for e in rv(item_results=results)]
                fake.runs.append(run_name)
                return type("Result", (), {"item_results": results, "run_evaluations": runs,
                                           "experiment_url": "https://langfuse.test/x"})()
        return Dataset()

    def flush(self):
        pass


def test_eval_pushes_dataset_and_one_experiment_per_config(app, monkeypatch):
    from anvaya.llm import evaluate
    fake_lf = FakeEvalLangfuse()
    monkeypatch.setattr(tracing, "client", lambda: fake_lf)
    with app.app_context():
        rows = evaluate.push_to_langfuse(use_llm=False)
    fixture = json.loads(evaluate.FIXTURE.read_text(encoding="utf-8"))["items"]
    assert set(fake_lf.items) == {f"anvaya-eval-{it['id']}" for it in fixture}  # stable ids: re-runs upsert
    assert len(rows) == 1 and rows[0]["run"] == "rules-only" and rows[0]["items"] == len(fixture)
    assert rows[0]["wrong_facts_reaching_confirmation"] == 0 and rows[0]["wrong_high_impact_facts"] == 0
    assert 0.9 < rows[0]["mean_recall"] <= 1.0
    assert fake_lf.runs[0].startswith("rules-only · extract-v1.1 · ")


def test_several_turns_in_one_request_get_one_trace_each(app, fake, exported):
    from langfuse import Langfuse
    from anvaya import profile
    fake.default["groq"] = facts(("age", 62, "62 years old"))
    rid = uuid.uuid4().hex
    with app.test_request_context(headers={"X-Request-Id": rid}):
        app.preprocess_request()
        sid = profile.create_session("personal", "en", is_demo=True)["session_id"]
        profile.handle_turn(sid, DEMO_EN)
        profile.handle_turn(sid, "Family of 3.")
    roots = by_name(exported())["extract-facts"]
    assert sorted(trace_hex(r) for r in roots) == sorted([rid, Langfuse.create_trace_id(seed=f"{rid}#1")])
    assert {meta(r, "correlation_id", "trace") for r in roots} == {rid}


def test_tc_runner_turns_go_to_their_own_environment(app, client, fake, exported, admin):
    fake.default["groq"] = facts()
    assert client.post("/api/v1/test-runs/TC1", headers=admin).json["passed"]
    envs = {s.attributes.get("langfuse.environment") for s in exported()}
    assert envs == {"tc-runner"}
    sid = new_session(client, demo=True)
    turn(client, sid, DEMO_EN)
    assert "langfuse.environment" not in by_name(exported())["extract-facts"][-1].attributes  # client default
