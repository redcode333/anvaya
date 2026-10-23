"""Live LLM checks (pytest -m live): each free provider on its own, with three kiosk demo phrases (hi, te, en).
Reads LLM settings from the environment or the repo-root .env; never prints keys. Demo data only."""
import json
import os
import time
from pathlib import Path

import pytest

from anvaya import create_app, llm
from anvaya.llm.providers import load_providers

pytestmark = pytest.mark.live

DEMO = json.loads((Path(llm.__file__).resolve().parent.parent / "data" / "demo_phrases.json").read_text(encoding="utf-8"))
SENTENCES = [  # (language, demo phrase, facts that must come back)
    ("hi", DEMO["hi"][1]["text"], {"age": 52, "state": "Bihar", "marital_status": "widowed"}),
    ("te", DEMO["te"][0]["text"], {"age": 67, "state": "Andhra Pradesh", "household_size": 4}),
    ("en", DEMO["en"][0]["text"], {"age": 67, "state": "Andhra Pradesh", "annual_income": 60000}),
]


def _env() -> dict:
    env = dict(os.environ)
    dotenv = Path(__file__).resolve().parents[2] / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


@pytest.fixture(scope="module", params=["groq", "gemini"])
def provider_app(request, tmp_path_factory):
    env = _env()
    env["LLM_PROVIDERS"] = request.param
    providers = load_providers(env)
    if not providers[0]["api_key"] or not providers[0]["model"]:
        pytest.skip(f"{request.param.upper()}_API_KEY / _MODEL not set")
    app = create_app({"DB_PATH": str(tmp_path_factory.mktemp(f"live-{request.param}") / "live.db"), "TESTING": True,
                      "LLM_EXTRACTION": True, "LLM_PROVIDERS": providers})
    with app.app_context():
        yield app, request.param


@pytest.mark.parametrize("lang,utterance,expected", SENTENCES, ids=[s[0] for s in SENTENCES])
def test_live_extraction(provider_app, lang, utterance, expected):
    app, name = provider_app
    t0 = time.perf_counter()
    res = llm.extract(utterance, None, time.monotonic() + app.config["LLM_TURN_BUDGET_S"])
    ms = round((time.perf_counter() - t0) * 1000)
    got = {f["attribute"]: f["value"] for f in res["facts"]}
    print(f"\n{name} {lang}: result={res['result']} {ms}ms cached={res['cached']} attributes={sorted(got)} "
          f"dropped={[d['reason'] for d in res['dropped']]}")
    assert res["result"] == "ok", res["result"]
    assert res["provider"] == name and ms < app.config["LLM_TURN_BUDGET_S"] * 1000
    for attr, value in expected.items():
        assert got.get(attr) == value, (attr, got.get(attr))
    again = llm.extract(utterance, None, time.monotonic() + 7)
    assert again["cached"] and again["facts"] == res["facts"]
