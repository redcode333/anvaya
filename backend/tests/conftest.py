import pytest

from anvaya import create_app, ingest
from anvaya.db import connect


@pytest.fixture(scope="session")
def app(tmp_path_factory):
    db_path = str(tmp_path_factory.mktemp("db") / "test.db")
    app = create_app({"DB_PATH": db_path, "TESTING": True, "CODE_LOOKUP_LIMIT_PER_MIN": 1000})
    conn = connect(db_path)
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
