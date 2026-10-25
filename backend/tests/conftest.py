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

import time  # noqa: E402

import jwt  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402

from anvaya import auth, create_app, ingest  # noqa: E402  (after DATABASE_URL is removed from the environment)
from anvaya.db import connect, dispose  # noqa: E402

# Supabase Auth in tests: a mock project whose JWKS holds one ES256 key generated here. Tokens are minted with it.
SUPABASE_URL = "https://test-project.supabase.co"
ISSUER = f"{SUPABASE_URL}/auth/v1"
SIGNING_KEY = ec.generate_private_key(ec.SECP256R1())
OTHER_KEY = ec.generate_private_key(ec.SECP256R1())  # not in the JWKS
KID = "test-key-1"
JWKS = {"keys": [{**jwt.algorithms.ECAlgorithm.to_jwk(SIGNING_KEY.public_key(), as_dict=True),
                  "kid": KID, "alg": "ES256", "use": "sig", "key_ops": ["verify"]}]}
JWKS_FETCHES: list[str] = []


def _fake_fetch_jwks(url):
    JWKS_FETCHES.append(url)
    assert url == f"{ISSUER}/.well-known/jwks.json"
    return JWKS


auth.fetch_jwks = _fake_fetch_jwks


def token(sub=None, *, role=None, anonymous=False, email=None, expires_in=3600, iss=ISSUER, aud="authenticated",
          key=None, kid=KID, alg="ES256", aal="aal1", signed_in_at=None) -> str:
    """A Supabase-style access token (claims as documented: iss, aud, sub, exp, iat, role, is_anonymous, aal, amr,
    app_metadata). amr lists the sign-in methods with their times, most recent first; totp is added at aal2."""
    t = int(time.time())
    first = int(signed_in_at if signed_in_at is not None else t - 5)
    amr = [{"method": "anonymous" if anonymous else "password", "timestamp": first}]
    if aal == "aal2":
        amr.insert(0, {"method": "totp", "timestamp": first + 1})
    claims = {"iss": iss, "aud": aud, "sub": sub or str(uuid.uuid4()), "iat": t - 5, "exp": t + expires_in,
              "role": "authenticated", "is_anonymous": anonymous, "aal": aal, "amr": amr,
              "session_id": str(uuid.uuid4()),
              "email": email or ("" if anonymous else "citizen@example.org"),
              "app_metadata": {"provider": "anonymous" if anonymous else "email", **({"role": role} if role else {})},
              "user_metadata": {}}
    return jwt.encode(claims, key or SIGNING_KEY, algorithm=alg, headers={"kid": kid})


def bearer(tok: str) -> dict:
    return {"Authorization": f"Bearer {tok}"}


def staff_id(role: str) -> str:
    return f"00000000-0000-4000-8000-{role[:3].encode().hex():0>12}"


def staff(role: str, aal: str = "aal2", **kw) -> dict:
    """Staff headers; aal2 (TOTP verified) unless a test asks for a password-only sign-in."""
    return bearer(token(staff_id(role), role=role, email=f"{role}@anvaya.test", aal=aal, **kw))


KIOSK_DEVICE = "KD-test-kiosk-0001"


def kiosk(role: str = "operator", device: str = KIOSK_DEVICE, **kw) -> dict:
    """Operator headers at a kiosk device (kiosk sessions are bound to both)."""
    return {**staff(role, **kw), "X-Kiosk-Device": device}

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
                      "SESSION_CREATE_LIMIT_PER_MIN": 100000, "AUTH_EVENT_LIMIT_PER_MIN": 100000,
                      "STAFF_MFA_REQUIRED": True, "DIGILOCKER_ENABLED": False,
                      "SUPABASE_URL": SUPABASE_URL, "SUPABASE_SECRET_KEY": "sb_secret_test_never_sent",
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


@pytest.fixture()
def config(app):
    """Change app.config for one test and put it back afterwards."""
    saved = {}

    def set_(**kw):
        for k, v in kw.items():
            saved.setdefault(k, app.config.get(k))
            app.config[k] = v
    yield set_
    app.config.update(saved)


@pytest.fixture()
def reviewer():
    return staff("reviewer")


@pytest.fixture()
def admin():
    return staff("admin")


@pytest.fixture()
def operator():
    return kiosk("operator")  # an operator works at a kiosk device


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
