"""One chat-completions client for every provider: OpenAI-compatible HTTP via requests (no vendor SDKs), plus the
optional Anthropic SDK imported lazily. Raises LLMError with a short, loggable kind; never logs prompts, outputs or keys.
"""
import re
import threading
from datetime import datetime, timedelta, timezone

import requests

from .providers import DAILY_RESET_UTC_OFFSET_H

# Providers that answered 400 to response_format=json_object: from then on they get plain JSON instructions only.
_NO_JSON_MODE: set[str] = set()
_lock = threading.Lock()


class LLMError(Exception):
    """kind: timeout | rate_limited | quota_exhausted | server_error | http_error | connection_error |
    invalid_output | not_installed. quota_exhausted carries reset_at (aware UTC datetime)."""

    def __init__(self, kind: str, status: int | None = None, reset_at: datetime | None = None):
        super().__init__(kind)
        self.kind, self.status, self.reset_at = kind, status, reset_at


def chat(p: dict, messages: list[dict], timeout: float) -> dict:
    """→ {content, prompt_tokens, completion_tokens}."""
    if p["kind"] == "anthropic":
        return _anthropic(p, messages, timeout)
    return _openai_compatible(p, messages, timeout)


def _openai_compatible(p: dict, messages: list[dict], timeout: float) -> dict:
    url = p["base_url"].rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if p["api_key"]:
        headers["Authorization"] = f"Bearer {p['api_key']}"
    payload = {"model": p["model"], "messages": messages, "temperature": 0, "max_tokens": 1200}
    if p["reasoning_effort"]:
        payload["reasoning_effort"] = p["reasoning_effort"]
    json_mode = p["name"] not in _NO_JSON_MODE
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    try:
        r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    except requests.Timeout:
        raise LLMError("timeout")
    except requests.RequestException:
        raise LLMError("connection_error")
    if r.status_code == 400 and json_mode and "response_format" in r.text:
        with _lock:
            _NO_JSON_MODE.add(p["name"])
        return _openai_compatible(p, messages, timeout)
    if r.status_code == 429:
        raise _rate_limit_error(p, r.headers, r.text)
    if r.status_code >= 500:
        raise LLMError("server_error", r.status_code)
    if not r.ok:
        raise LLMError("http_error", r.status_code)
    try:
        body = r.json()
        content = body["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError):
        raise LLMError("invalid_output", r.status_code)
    if not isinstance(content, str):
        raise LLMError("invalid_output", r.status_code)
    usage = body.get("usage") or {}
    return {"content": content, "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens")}


def _anthropic(p: dict, messages: list[dict], timeout: float) -> dict:
    try:
        import anthropic
    except ImportError:
        raise LLMError("not_installed")
    client = anthropic.Anthropic(api_key=p["api_key"], timeout=timeout, max_retries=0,
                                 **({"base_url": p["base_url"]} if p["base_url"] else {}))
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    try:
        resp = client.messages.create(model=p["model"], max_tokens=1200, system=system,
                                      messages=[m for m in messages if m["role"] != "system"])
    except anthropic.APITimeoutError:
        raise LLMError("timeout")
    except anthropic.APIConnectionError:
        raise LLMError("connection_error")
    except anthropic.RateLimitError as e:
        raise _rate_limit_error(p, e.response.headers, e.response.text)
    except anthropic.APIStatusError as e:
        raise LLMError("server_error" if e.status_code >= 500 else "http_error", e.status_code)
    text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), None)
    if text is None:
        raise LLMError("invalid_output")
    return {"content": text, "prompt_tokens": resp.usage.input_tokens, "completion_tokens": resp.usage.output_tokens}


# ---------------------------------------------------------------- 429 handling

_DAILY = re.compile(r"per[ _-]?day|daily|\bRPD\b|\bTPD\b|PerDay", re.I)
_QUOTA = re.compile(r"quota|RESOURCE_EXHAUSTED", re.I)
_RETRY_IN = re.compile(r"(?:try again|retry) in\s+((?:\d+h)?(?:\d+m)?(?:\d+(?:\.\d+)?s)?)", re.I)
_DURATION = re.compile(r"^(?:(\d+)h)?(?:(\d+)m(?!s))?(?:(\d+(?:\.\d+)?)s)?$")


def parse_duration(s: str | None) -> float | None:
    """'1m26.4s' / '7.66s' / '2h3m' / '30' → seconds."""
    if not s:
        return None
    s = s.strip()
    try:
        return float(s)
    except ValueError:
        pass
    m = _DURATION.match(s)
    if not m or not any(m.groups()):
        return None
    h, mi, sec = m.groups()
    return int(h or 0) * 3600 + int(mi or 0) * 60 + float(sec or 0)


def next_daily_reset(name: str, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    off = timedelta(hours=DAILY_RESET_UTC_OFFSET_H.get(name, 0))
    local = now + off
    midnight = (local + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight - off


def _rate_limit_error(p: dict, headers, text: str) -> LLMError:
    """A 429 that mentions a daily limit or a quota marks the provider exhausted until its reset; any other 429 is a
    plain rate limit (move on to the next provider)."""
    text = text or ""
    daily = bool(_DAILY.search(text)) or headers.get("x-ratelimit-remaining-requests") == "0"  # Groq: requests = RPD
    if not (daily or _QUOTA.search(text)):
        return LLMError("rate_limited", 429)
    now = datetime.now(timezone.utc)
    m = _RETRY_IN.search(text)
    wait = parse_duration(headers.get("x-ratelimit-reset-requests") if daily else None) \
        or parse_duration(headers.get("retry-after")) or (parse_duration(m.group(1)) if m else None)
    if wait:
        reset = now + timedelta(seconds=wait)
    elif daily:
        reset = next_daily_reset(p["name"], now)
    else:
        reset = now + timedelta(seconds=60)
    return LLMError("quota_exhausted", 429, reset)
