"""Optional LLM candidate-fact extraction over free OpenAI-compatible providers (off by default).

The deterministic extractor is the primary path; the LLM only adds or cross-checks facts (see merge.py) and never
decides eligibility. Every failure mode — no provider configured, all down, quota exhausted, budget exceeded,
invalid output — ends in "no LLM facts", so the app behaves exactly as with deterministic extraction alone.

Per turn: one budget (LLM_TURN_BUDGET_S, default 7 s) covers the VerbX translation and every provider call; each
call is capped at LLM_CALL_TIMEOUT_S (6 s). Providers are tried in LLM_PROVIDERS order, moving on after a timeout,
429, 5xx or invalid output; invalid JSON gets exactly one retry with the validation error appended.

Logs and metrics carry provider, model, result, status, latency and token counts only — never utterances, prompts,
model output or keys.
"""
import json
import logging
import re
import time
from functools import lru_cache
from pathlib import Path

from flask import current_app

from .. import metrics
from . import cache, client, prompt, state, validate
from .providers import is_configured, public
from .validate import ATTRIBUTES  # noqa: F401  (re-exported)

log = logging.getLogger(__name__)

DEMO_PHRASES_FILE = Path(__file__).resolve().parent.parent / "data" / "demo_phrases.json"
MIN_CALL_S = 0.5  # below this much remaining budget a call is not worth starting


def providers() -> list[dict]:
    return [p for p in current_app.config["LLM_PROVIDERS"] if is_configured(p)]


def enabled() -> bool:
    return bool(current_app.config["LLM_EXTRACTION"] and providers())


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().casefold()


@lru_cache(maxsize=1)
def demo_phrases() -> frozenset[str]:
    data = json.loads(DEMO_PHRASES_FILE.read_text(encoding="utf-8"))
    return frozenset(_norm(s["text"]) for items in data.values() for s in items)


def allowed(session: dict, utterance: str) -> bool:
    """Privacy gate: unless LLM_ALLOW_REAL_DATA, only demo/test data may reach (free-tier) providers — TC-runner
    sessions, sessions created with "demo": true, and the kiosk's built-in demo phrases."""
    if current_app.config["LLM_ALLOW_REAL_DATA"]:
        return True
    return bool(session.get("is_test") or session.get("is_demo")) or _norm(utterance) in demo_phrases()


def status() -> dict:
    out = []
    for p in current_app.config["LLM_PROVIDERS"]:
        d = public(p)
        d["status"] = state.status(p) if d["configured"] else "not_configured"
        until = state.exhausted_until(p["name"]) if d["configured"] else None
        d["exhausted_until"] = until.isoformat(timespec="seconds") if until else None
        out.append(d)
    return {"enabled": enabled(), "allow_real_data": current_app.config["LLM_ALLOW_REAL_DATA"],
            "prompt_version": prompt.version(), "turn_budget_s": current_app.config["LLM_TURN_BUDGET_S"],
            "providers": out}


# ---------------------------------------------------------------- translation input

_SCRIPT = [("hi", re.compile(r"[ऀ-ॿ]")), ("te", re.compile(r"[ఀ-౿]"))]


def source_language(utterance: str) -> str | None:
    """hi / te when the utterance is written in that script (romanised Hinglish goes to the LLM untranslated)."""
    return next((lang for lang, pat in _SCRIPT if pat.search(utterance)), None)


def english_translation(utterance: str, deadline: float) -> str | None:
    from .. import translation

    lang = source_language(utterance)
    remaining = deadline - time.monotonic() - MIN_CALL_S  # leave room for at least one LLM call
    if not lang or remaining <= 0.2:
        return None
    return translation.translate_for_extraction(utterance, lang, timeout=min(remaining, 3.5))


# ---------------------------------------------------------------- extraction

def _result(facts=(), dropped=(), result="ok", provider=None, model=None, cached=False, latency_ms=None,
            translated=False):
    return {"facts": list(facts), "dropped": list(dropped), "result": result, "provider": provider, "model": model,
            "cached": cached, "latency_ms": latency_ms, "translated": translated, "prompt_version": prompt.version()}


def _log(p, result, status=None, latency=None, usage=None):
    usage = usage or {}
    log.info("llm provider=%s model=%s result=%s status=%s latency_ms=%s prompt_tokens=%s completion_tokens=%s",
             p["name"], p["model"], result, status, None if latency is None else int(latency * 1000),
             usage.get("prompt_tokens"), usage.get("completion_tokens"))


def run_turn(utterance: str) -> dict:
    """Translation (hi/te) + extraction inside one turn budget. Validated facts only; never raises."""
    deadline = time.monotonic() + current_app.config["LLM_TURN_BUDGET_S"]
    tr = english_translation(utterance, deadline)
    res = extract(utterance, tr, deadline)
    res["translated"] = bool(tr)
    return res


def extract(utterance: str, translation: str | None, deadline: float) -> dict:
    ps = providers()
    if not ps:
        return _result(result="not_configured")
    messages = prompt.build(utterance, translation)
    version = prompt.version()

    # A cached answer from any configured provider costs nothing, so look before calling anyone.
    for p in ps:
        items = cache.get(cache.key(p, messages))
        if items is not None:
            facts, dropped = validate.check(items, utterance, translation)
            metrics.LLM_CALLS.labels(p["name"], "cache_hit").inc()
            _log(p, "cache_hit")
            return _result(facts, dropped, "ok", p["name"], p["model"], cached=True, latency_ms=0)

    failed_from = None
    for p in ps:
        name = p["name"]
        if state.exhausted_until(name):
            metrics.LLM_CALLS.labels(name, "skipped_exhausted").inc()
            continue
        if state.circuit_open(name):
            metrics.LLM_CALLS.labels(name, "skipped_circuit").inc()
            continue
        if failed_from:
            metrics.LLM_FALLBACKS.labels(failed_from, name).inc()
        msgs = messages
        for attempt in (1, 2):
            remaining = deadline - time.monotonic()
            if remaining < MIN_CALL_S:
                metrics.LLM_CALLS.labels(name, "budget_exceeded").inc()
                _log(p, "budget_exceeded")
                return _result(result="budget_exceeded")
            t0 = time.monotonic()
            try:
                resp = client.chat(p, msgs, timeout=min(current_app.config["LLM_CALL_TIMEOUT_S"], remaining))
            except client.LLMError as e:
                latency = time.monotonic() - t0
                metrics.LLM_LATENCY.labels(name).observe(latency)
                metrics.LLM_CALLS.labels(name, e.kind).inc()
                _log(p, e.kind, e.status, latency)
                if e.kind == "quota_exhausted":
                    state.mark_exhausted(name, e.reset_at)
                elif e.status:
                    state.count_request(p)  # the provider answered, so it counts toward its daily limit
                state.record(name, False)
                break
            latency = time.monotonic() - t0
            metrics.LLM_LATENCY.labels(name).observe(latency)
            state.count_request(p)
            if time.monotonic() > deadline:
                metrics.LLM_CALLS.labels(name, "budget_exceeded").inc()
                _log(p, "budget_exceeded", 200, latency, resp)
                return _result(result="budget_exceeded")
            try:
                items = validate.parse(resp["content"])
            except validate.InvalidOutput as e:
                metrics.LLM_CALLS.labels(name, "invalid_output").inc()
                _log(p, "invalid_output", 200, latency, resp)
                if attempt == 1:
                    msgs = prompt.retry(messages, resp["content"], str(e))
                    continue
                state.record(name, False)
                break
            metrics.LLM_CALLS.labels(name, "ok").inc()
            _log(p, "ok", 200, latency, resp)
            state.record(name, True)
            cache.put(cache.key(p, messages), p, version, items)
            facts, dropped = validate.check(items, utterance, translation)
            return _result(facts, dropped, "ok", name, p["model"], latency_ms=int(latency * 1000))
        failed_from = name
    if failed_from:
        metrics.LLM_FALLBACKS.labels(failed_from, "deterministic").inc()
    return _result(result="all_failed")
