"""LLM provider configuration, read from the environment only.

LLM_PROVIDERS=groq,gemini lists providers in fallback order. For each NAME: NAME_BASE_URL, NAME_API_KEY, NAME_MODEL,
NAME_DAILY_REQUESTS (soft cap per UTC day, 0 = none) and optional NAME_REASONING_EFFORT. Every provider except
"anthropic" is called through the OpenAI-compatible POST {base_url}/chat/completions; "anthropic" uses the optional
anthropic package, imported only when that provider is actually called.
"""

# Base URLs taken from each provider's OpenAI-compatibility documentation (checked 2026-10-23):
#   groq   https://console.groq.com/docs/openai
#   gemini https://ai.google.dev/gemini-api/docs/openai
#   ollama https://docs.ollama.com/api/openai-compatibility  (local server; the key is ignored)
DEFAULT_BASE_URLS = {
    "groq": "https://api.groq.com/openai/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai/",
    "ollama": "http://localhost:11434/v1",
}
KEYLESS = {"ollama"}

# Gemini's daily quotas reset at midnight Pacific time; others are counted per UTC day.
DAILY_RESET_UTC_OFFSET_H = {"gemini": -8}


def _daily(env, key: str, warnings: list | None) -> int:
    try:
        return int(env.get(key, "0") or 0)
    except ValueError:
        if warnings is not None:
            warnings.append(f"{key} is not a valid number; using 0 (no daily cap)")
        return 0


def load_providers(env, warnings: list | None = None) -> list[dict]:
    names = [n.strip().lower() for n in env.get("LLM_PROVIDERS", "").split(",") if n.strip()]
    out = []
    for name in dict.fromkeys(names):
        up = name.upper()
        kind = "anthropic" if name == "anthropic" else "openai"
        model = env.get(f"{up}_MODEL", "")
        if name == "anthropic" and not model:
            model = env.get("ANVAYA_LLM_MODEL", "")  # name used before the provider package existed
        out.append({
            "name": name,
            "kind": kind,
            "base_url": env.get(f"{up}_BASE_URL", DEFAULT_BASE_URLS.get(name, "")),
            "api_key": env.get(f"{up}_API_KEY", ""),
            "model": model,
            "daily_requests": _daily(env, f"{up}_DAILY_REQUESTS", warnings),
            "reasoning_effort": env.get(f"{up}_REASONING_EFFORT", ""),
        })
    return out


def is_configured(p: dict) -> bool:
    if not p["model"]:
        return False
    if p["kind"] == "anthropic":
        return bool(p["api_key"])
    return bool(p["base_url"] and (p["api_key"] or p["name"] in KEYLESS))


def missing(p: dict) -> list[str]:
    """Names (never values) of the environment variables this provider still needs."""
    up = p["name"].upper()
    need = [] if p["model"] else [f"{up}_MODEL"]
    if p["kind"] == "anthropic" or p["name"] not in KEYLESS:
        need += [] if p["api_key"] else [f"{up}_API_KEY"]
    if p["kind"] != "anthropic" and not p["base_url"]:
        need.append(f"{up}_BASE_URL")
    return need


def public(p: dict) -> dict:
    """Provider description safe for /ready and logs: never the key."""
    return {"name": p["name"], "model": p["model"], "kind": p["kind"], "configured": is_configured(p),
            "daily_requests": p["daily_requests"] or None}
