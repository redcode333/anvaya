"""Optional Langfuse tracing of LLM extraction (Langfuse Python SDK v5, OpenTelemetry based).

Enabled only when LANGFUSE_PUBLIC_KEY, LANGFUSE_SECRET_KEY and LANGFUSE_BASE_URL (or the deprecated LANGFUSE_HOST) are
all set. Otherwise every call here is a no-op: the SDK is never imported and nothing leaves the process.

One trace per conversation turn that used the LLM, trace id = the request's correlation id (X-Request-Id):

    extract-facts (chain)                    root; trace input/output = utterance / merged candidate facts
    ├─ translate-utterance (tool)            VerbX translation hi/te → en, when the utterance needed it
    ├─ extract-candidate-facts (generation)  one per provider call or retry: model, tokens, latency, result
    └─ merge-facts (span)                    agree / llm_only / disagree / dropped_* per attribute

Privacy: input/output are recorded only for demo/test data (the same test as the LLM privacy gate: TC-runner and
"demo" sessions, the kiosk demo phrases). Any other turn is traced as metadata only, enforced twice: the code never
sets input/output for it, and the export-stage `mask_otel_spans` hook strips everything outside an allowlist from its
spans. A span the hook cannot classify raises, which makes the SDK drop the whole export batch (fail closed).

Failure isolation: spans are exported by the SDK's background BatchSpanProcessor with a short HTTP timeout
(LANGFUSE_TIMEOUT_S, default 2 s); a slow or unreachable Langfuse never blocks or breaks a turn, and every tracing
call here swallows its own errors.
"""
import json
import logging
import re
import threading
import time
from contextlib import ExitStack, contextmanager

from flask import current_app, g, has_request_context

log = logging.getLogger(__name__)

DATA_CLASS_KEY = "langfuse.trace.metadata.data_class"
# Attributes kept on metadata-only ("real") spans: structure, model, usage, levels and our own non-personal metadata.
_ALLOWED_PREFIXES = (
    "langfuse.observation.type", "langfuse.observation.level", "langfuse.observation.status_message",
    "langfuse.observation.model.", "langfuse.observation.usage_details", "langfuse.observation.cost_details",
    "langfuse.observation.metadata.", "langfuse.observation.prompt.", "langfuse.trace.metadata.",
    "langfuse.trace.tags", "langfuse.trace.name", "langfuse.environment", "langfuse.release", "langfuse.version",
    "langfuse.internal.", "session.id",
)
_HEX32 = re.compile(r"^[0-9a-f]{32}$")

_client = None
_client_key = None
_lock = threading.Lock()


class MaskingError(Exception):
    """Raised inside the mask hook for a span it cannot classify: the SDK then drops the export batch."""


def settings(cfg) -> dict | None:
    base_url = cfg.get("LANGFUSE_BASE_URL") or cfg.get("LANGFUSE_HOST")
    if not (cfg.get("LANGFUSE_PUBLIC_KEY") and cfg.get("LANGFUSE_SECRET_KEY") and base_url):
        return None
    return {"public_key": cfg["LANGFUSE_PUBLIC_KEY"], "secret_key": cfg["LANGFUSE_SECRET_KEY"], "base_url": base_url,
            "timeout": cfg.get("LANGFUSE_TIMEOUT_S", 2)}


def enabled() -> bool:
    return settings(current_app.config) is not None


def mask_spans(*, params):
    """Export-stage masking (`mask_otel_spans`): demo spans pass unchanged; metadata-only spans keep allowlisted
    attributes; anything unclassifiable fails the batch."""
    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    patches = {}
    for ident, span in params.spans.items():
        attrs = span.attributes
        if any(k.startswith("langfuse.experiment.") for k in attrs):
            continue  # eval experiment spans: demo fixtures, only sent with LANGFUSE_TRACE_EVAL=1
        raw = attrs.get(DATA_CLASS_KEY)
        if raw is None:
            raise MaskingError(f"span {span.name!r} has no data_class")
        data_class = json.loads(raw)
        if data_class == "demo":
            continue
        if data_class != "real":
            raise MaskingError(f"unknown data_class {data_class!r}")
        drop = tuple(k for k in attrs if not k.startswith(_ALLOWED_PREFIXES))
        patches[ident] = OtelSpanPatch(delete_attributes=drop,
                                       set_attributes={"langfuse.observation.metadata.redacted": json.dumps(True)})
    return MaskOtelSpansResult(span_patches=patches)


def client():
    """The process-wide Langfuse client for the current config (created on first use, imported only then)."""
    global _client, _client_key
    cfg = current_app.config
    s = settings(cfg)
    if s is None:
        return None
    key = (s["public_key"], s["base_url"], id(cfg.get("LANGFUSE_SPAN_EXPORTER")))
    with _lock:
        if _client is None or _client_key != key:
            from langfuse import Langfuse
            from opentelemetry.sdk.trace import TracerProvider

            # Own TracerProvider: Langfuse spans stay out of any other OpenTelemetry setup and vice versa.
            _client = Langfuse(public_key=s["public_key"], secret_key=s["secret_key"], base_url=s["base_url"],
                               timeout=int(max(1, s["timeout"])), tracer_provider=TracerProvider(),
                               mask_otel_spans=mask_spans, span_exporter=cfg.get("LANGFUSE_SPAN_EXPORTER"))
            _client_key = key
        return _client


def flush() -> None:
    try:
        if _client is not None:
            _client.flush()
    except Exception:  # noqa: BLE001 - tracing must never break the caller
        log.debug("langfuse flush failed", exc_info=True)


def correlation_trace_id(correlation_id: str | None) -> str | None:
    if not correlation_id:
        return None
    if _HEX32.match(correlation_id):
        return correlation_id
    from langfuse import Langfuse
    return Langfuse.create_trace_id(seed=correlation_id)


# ---------------------------------------------------------------- per-turn tracing

class _Noop:
    """Stands in for TurnTrace / _Call when tracing is off: every method returns itself, `with` yields a scratch dict."""

    def __bool__(self):
        return False

    def __getattr__(self, name):
        return lambda *a, **kw: _NOOP

    def __enter__(self):
        return {}

    def __exit__(self, *exc):
        return False


_NOOP = _Noop()


class _Call:
    """One provider call (generation). end() is idempotent and never raises."""

    def __init__(self, turn, obs):
        self.turn, self.obs, self.t0, self.ended = turn, obs, time.monotonic(), False

    def end(self, result: str, status: int | None = None, usage: dict | None = None, content: str | None = None):
        if self.ended:
            return
        self.ended = True
        try:
            usage = usage or {}
            ok = result in ("ok", "cache_hit")
            update = {"metadata": {"result": result, "status": status,
                                   "latency_ms": int((time.monotonic() - self.t0) * 1000)},
                      "level": "DEFAULT" if ok else ("WARNING" if result == "invalid_output" else "ERROR")}
            if not ok:
                update["status_message"] = result
            if usage.get("prompt_tokens") is not None or usage.get("completion_tokens") is not None:
                update["usage_details"] = {"input": usage.get("prompt_tokens") or 0,
                                           "output": usage.get("completion_tokens") or 0}
            if self.turn.full and content is not None:
                update["output"] = content
            self.obs.update(**update)
            self.obs.end()
        except Exception:  # noqa: BLE001
            log.debug("langfuse generation end failed", exc_info=True)


class TurnTrace:
    def __init__(self, root, full: bool):
        self.root, self.full = root, full

    def _child(self, **kw):
        try:
            return self.root.start_observation(**kw)
        except Exception:  # noqa: BLE001
            log.debug("langfuse child observation failed", exc_info=True)
            return None

    @contextmanager
    def translate(self, source_lang: str, text: str):
        obs = self._child(name="translate-utterance", as_type="tool",
                          input={"text": text, "source_lang": source_lang, "target_lang": "en"} if self.full else None,
                          metadata={"provider": "verbx", "source_lang": source_lang})
        box, t0 = {}, time.monotonic()
        try:
            yield box
        finally:
            if obs is not None:
                try:
                    out = box.get("text")
                    obs.update(output=({"text": out} if self.full and out else None),
                               metadata={"ok": bool(out), "latency_ms": int((time.monotonic() - t0) * 1000)},
                               level="DEFAULT" if out else "WARNING")
                    obs.end()
                except Exception:  # noqa: BLE001
                    log.debug("langfuse translate span failed", exc_info=True)

    def llm_call(self, p: dict, attempt: int, messages: list[dict], cached: bool = False):
        obs = self._child(name="extract-candidate-facts", as_type="generation", model=p["model"],
                          input=messages if self.full else None,
                          model_parameters={"temperature": 0, "max_tokens": 1200,
                                            **({"reasoning_effort": p["reasoning_effort"]}
                                               if p.get("reasoning_effort") else {})},
                          metadata={"provider": p["name"], "attempt": attempt, "retry": attempt > 1,
                                    "cached": cached})
        return _Call(self, obs) if obs is not None else _NOOP

    def merge(self, outcomes: dict, dropped: list[dict], candidates: list[dict]):
        counts: dict[str, int] = {}
        for o in list(outcomes.values()) + [("dropped_evidence" if d["reason"] == "evidence" else "dropped_invalid")
                                            for d in dropped]:
            counts[o] = counts.get(o, 0) + 1
        obs = self._child(name="merge-facts", as_type="span",
                          metadata={"outcomes": outcomes, "counts": counts})
        if obs is None:
            return
        try:
            if self.full:
                obs.update(output=_facts_view(candidates))
            obs.end()
        except Exception:  # noqa: BLE001
            log.debug("langfuse merge span failed", exc_info=True)

    def finish(self, run: dict, candidates: list[dict] | None):
        try:
            self.root.update(
                output={"facts": _facts_view(candidates or [])} if self.full else None,
                metadata={"result": run["result"], "provider": run["provider"], "model": run["model"],
                          "cached": run["cached"], "latency_ms": run["latency_ms"], "translated": run["translated"]},
                level="DEFAULT" if run["result"] == "ok" else "WARNING")
        except Exception:  # noqa: BLE001
            log.debug("langfuse root update failed", exc_info=True)


def _facts_view(facts: list[dict]) -> list[dict]:
    return [{"attribute": f["attribute"], "value": f["value"], "source": f.get("source", "deterministic"),
             **({"alternatives": f["alternatives"]} if f.get("alternatives") else {})} for f in facts]


@contextmanager
def turn(session_id: str, demo_data: bool, utterance: str, prompt_version: str, environment: str | None = None):
    """Trace one LLM turn. Yields a TurnTrace, or a falsy no-op when tracing is off or could not start.
    `environment` overrides the client's Langfuse environment for this trace (TC-runner turns use "tc-runner")."""
    stack = ExitStack()
    tr = _NOOP
    try:
        lf = client()
        if lf is not None:
            correlation_id = g.get("request_id") if has_request_context() else None
            # One trace per turn: a request that runs several turns (the TC runner) keeps the correlation id for its
            # first turn and derives the others from it; every trace carries correlation_id in its metadata.
            n = g.get("langfuse_turns", 0) if has_request_context() else 0
            if has_request_context():
                g.langfuse_turns = n + 1
            trace_id = correlation_trace_id(correlation_id if n == 0 or not correlation_id else f"{correlation_id}#{n}")
            full = bool(demo_data)
            root = stack.enter_context(lf.start_as_current_observation(
                as_type="chain", name="extract-facts",
                trace_context={"trace_id": trace_id} if trace_id else None,
                input={"utterance": utterance} if full else None))
            stack.enter_context(_propagate(session_id, full, correlation_id, prompt_version, environment))
            tr = TurnTrace(root, full)
    except Exception:  # noqa: BLE001
        log.debug("langfuse trace start failed", exc_info=True)
        _close(stack)
        stack, tr = ExitStack(), _NOOP
    try:
        yield tr
    finally:
        _close(stack)


def _propagate(session_id, full, correlation_id, prompt_version, environment):
    from langfuse import propagate_attributes
    return propagate_attributes(
        session_id=session_id, trace_name="extract-facts", environment=environment,
        tags=["llm-extraction", f"prompt:{prompt_version}"],
        metadata={"data_class": "demo" if full else "real", "correlation_id": correlation_id,
                  "prompt_version": prompt_version})


def _close(stack: ExitStack) -> None:
    try:
        stack.close()
    except Exception:  # noqa: BLE001
        log.debug("langfuse trace end failed", exc_info=True)
