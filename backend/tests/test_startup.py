"""Boot-time config validation and the /ready integration report."""
import logging

from conftest import db_config

from anvaya import create_app, ingest
from anvaya.db import connect
from anvaya.llm.providers import load_providers

SECRET = "sk-test-value-never-logged"


def boot(tmp_path, caplog, **cfg):
    with caplog.at_level(logging.INFO, logger="anvaya.startup"):
        app = create_app({**db_config(tmp_path / "boot.db"), "TESTING": True, "LANGFUSE_PUBLIC_KEY": "",
                          "LANGFUSE_SECRET_KEY": "", "LANGFUSE_BASE_URL": "", **cfg})
    return app, [r.getMessage() for r in caplog.records if r.name == "anvaya.startup"]


def test_one_line_per_integration_and_never_a_value(tmp_path, caplog):
    providers = load_providers({"LLM_PROVIDERS": "groq,gemini", "GROQ_API_KEY": SECRET, "GROQ_MODEL": "m"})
    app, lines = boot(tmp_path, caplog, VERBX_BASE_URL="https://verbx.test", VERBX_API_KEY=SECRET,
                      LLM_PROVIDERS=providers, METRICS_TOKEN="", LANGFUSE_PUBLIC_KEY="", LANGFUSE_SECRET_KEY="",
                      LANGFUSE_BASE_URL="")
    integ = [ln for ln in lines if ln.startswith("integration")]
    assert len(integ) == 8  # verbx, llm.groq, llm.gemini, langfuse, supabase_auth, metrics, turnstile, digilocker
    assert "integration verbx        configured" in integ[0]
    assert "llm.groq" in integ[1] and "configured" in integ[1]
    assert "llm.gemini" in integ[2] and "missing (missing GEMINI_MODEL, GEMINI_API_KEY)" in integ[2]
    assert "langfuse" in integ[3] and "missing (missing LANGFUSE_PUBLIC_KEY" in integ[3]
    assert "supabase_auth" in integ[4]
    assert "metrics" in integ[5] and "missing" in integ[5]
    assert not any(SECRET in ln or "verbx.test" in ln for ln in lines)


def test_missing_optional_keys_do_not_stop_the_app_and_ready_reports_them(tmp_path, caplog):
    app, _ = boot(tmp_path, caplog, VERBX_BASE_URL="", VERBX_API_KEY="", LLM_PROVIDERS=[], METRICS_TOKEN="")
    conn = connect(app.config)
    ingest.bootstrap(conn, app.config["DATASET_CSV"], app.config["GOLDEN_RULES"], app.config["RULE_BUNDLE_VERSION"])
    conn.close()
    r = app.test_client().get("/api/v1/ready")
    assert r.status_code == 200 and r.json["ready"] is True
    assert r.json["integrations"]["verbx"] == {"status": "missing", "missing": ["VERBX_BASE_URL", "VERBX_API_KEY"]}
    assert r.json["integrations"]["llm"]["status"] == "missing"
    assert r.json["integrations"]["metrics"]["status"] == "missing"
    assert r.json["tts_cache"] == {"entries": 0, "prerendered": 0}
    s = app.test_client().post("/api/v1/sessions", json={"language": "te"}).json["session_id"]
    speak = app.test_client().post(f"/api/v1/sessions/{s}/voice/speak", json={"text": "నమస్తే"})
    assert speak.status_code == 503 and speak.json["error"]["details"] == {"reason": "not_configured"}


def test_bad_numbers_fall_back_to_defaults_with_a_warning():
    warnings = []
    p = load_providers({"LLM_PROVIDERS": "groq", "GROQ_DAILY_REQUESTS": "lots"}, warnings)
    assert p[0]["daily_requests"] == 0 and warnings == ["GROQ_DAILY_REQUESTS is not a valid number; using 0 (no daily cap)"]


def test_no_demo_passwords_anywhere(client):
    """Staff sign in through Supabase Auth: the old local login and the demo-password hint are gone."""
    assert client.get("/api/v1/auth/demo-accounts").status_code == 404
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"}).status_code in (404, 405)
