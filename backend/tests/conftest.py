import os
import uuid

import pytest

# Tests never use the app's DATABASE_URL (in a shell that loaded .env it points at the hosted database). They run on
# SQLite, or on Postgres when TEST_DATABASE_URL is set (a local postgres:16 container / the CI service), each test app
# in its own fresh schema.
_HOSTED_URL = os.environ.pop("DATABASE_URL", "")
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
if TEST_DATABASE_URL and (TEST_DATABASE_URL == _HOSTED_URL or "supabase" in TEST_DATABASE_URL):
    raise RuntimeError("TEST_DATABASE_URL must point at a disposable local Postgres, never the hosted database")

from anvaya import create_app, ingest  # noqa: E402  (after DATABASE_URL is removed from the environment)
from anvaya.db import connect, dispose  # noqa: E402

_schemas: list[str] = []


def db_config(path) -> dict:
    """Database settings for a new test app: a SQLite file at `path`, or a new Postgres schema."""
    if TEST_DATABASE_URL:
        schema = f"t_{uuid.uuid4().hex[:12]}"
        _schemas.append(schema)
        return {"DATABASE_URL": TEST_DATABASE_URL, "DB_SCHEMA": schema, "DB_PATH": str(path)}
    return {"DATABASE_URL": "", "DB_PATH": str(path)}


def on_postgres() -> bool:
    return bool(TEST_DATABASE_URL)


@pytest.fixture(scope="session", autouse=True)
def _drop_test_schemas():
    yield
    if TEST_DATABASE_URL and _schemas:
        import psycopg
        with psycopg.connect(TEST_DATABASE_URL, autocommit=True) as conn:
            for schema in _schemas:
                dispose({"DATABASE_URL": TEST_DATABASE_URL, "DB_SCHEMA": schema})
                conn.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    db = db_config(tmp_path_factory.mktemp("db") / "test.db")
    # LLM extraction is off unless a test turns it on with mocked providers (tests/test_llm.py).
    app = create_app({**db, "TESTING": True, "CODE_LOOKUP_LIMIT_PER_MIN": 1000,
                      "LLM_EXTRACTION": False, "LLM_PROVIDERS": [], "LLM_ALLOW_REAL_DATA": False,
                      # never trace to a real Langfuse from tests (tests/test_tracing.py uses a fake exporter)
                      "LANGFUSE_PUBLIC_KEY": "", "LANGFUSE_SECRET_KEY": "", "LANGFUSE_BASE_URL": ""})
    conn = connect(app.config)
    ingest.bootstrap(conn, app.config["DATASET_CSV"], app.config["GOLDEN_RULES"], app.config["RULE_BUNDLE_VERSION"])
    conn.close()
    return app


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, username, password):
    r = client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.json
    return {"Authorization": f"Bearer {r.json['token']}"}


@pytest.fixture()
def reviewer(client):
    return login(client, "reviewer", "reviewer123")


@pytest.fixture()
def admin(client):
    return login(client, "admin", "admin123")


@pytest.fixture()
def operator(client):
    return login(client, "operator", "operator123")


def start(client, utterance, lang="en", confirm=True):
    sid = client.post("/api/v1/sessions", json={"mode": "personal", "language": lang}).json["session_id"]
    r = client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": utterance})
    assert r.status_code == 200, r.json
    if confirm:
        # Confirm-all covers low-impact facts; each high-impact fact is confirmed on its own after its read-back.
        pending = client.post(f"/api/v1/sessions/{sid}/profile/confirm-all").json["needs_confirmation"]
        for fid in pending:
            client.patch(f"/api/v1/sessions/{sid}/profile/facts/{fid}", json={"confirmed": True})
    return sid
