"""Boot-time configuration check: one log line per integration (configured / missing) and a list of warnings.

Only variable *names* are ever logged or returned — never their values. Every integration is optional: a missing
key turns that feature off (see each line's "effect"), it never stops the app. The result is kept on the app and
shown by GET /api/v1/ready.
"""
import logging

from .config import CONFIG_WARNINGS, STAFF_ACCOUNTS
from .llm.providers import is_configured, missing

log = logging.getLogger("anvaya.startup")


def check(cfg, demo_password_users: list[str]) -> dict:
    integrations = {}

    need = [k for k in ("VERBX_BASE_URL", "VERBX_API_KEY") if not cfg[k]]
    integrations["verbx"] = {
        "status": "missing" if need else "configured", "missing": need,
        "effect": "speech falls back to browser voice / text; scheme names stay in English" if need
        else "STT, TTS (cached) and translation via VerbX"}

    for p in cfg["LLM_PROVIDERS"]:
        need = missing(p)
        on = is_configured(p)
        integrations[f"llm.{p['name']}"] = {
            "status": "configured" if on else "missing", "missing": need,
            "effect": ("used for candidate facts" if cfg["LLM_EXTRACTION"] else "configured but ANVAYA_LLM_EXTRACTION=off")
            if on else "skipped; deterministic extraction only"}
    if not cfg["LLM_PROVIDERS"]:
        integrations["llm"] = {"status": "missing", "missing": ["LLM_PROVIDERS"],
                               "effect": "deterministic extraction only"}

    integrations["metrics"] = {
        "status": "configured" if cfg["METRICS_TOKEN"] else "missing",
        "missing": [] if cfg["METRICS_TOKEN"] else ["ANVAYA_METRICS_TOKEN"],
        "effect": "/metrics requires a bearer token" if cfg["METRICS_TOKEN"]
        else "/metrics is open (fine for a local demo; set a token behind a public ingress)"}

    warnings = list(CONFIG_WARNINGS)
    for user in demo_password_users:
        warnings.append(f"{STAFF_ACCOUNTS[user][0]} is not set: account '{user}' uses the public demo password")

    for name, i in integrations.items():
        extra = f" (missing {', '.join(i['missing'])})" if i["missing"] else ""
        log.info("integration %-12s %s%s: %s", name, i["status"], extra, i["effect"])
    for w in warnings:
        log.warning("config: %s", w)
    return {"integrations": integrations, "warnings": warnings, "demo_password_users": demo_password_users}
