"""Live Supabase Storage check (pytest -m live): upload a tiny PNG through the app into the real private bucket, view it
through a signed view link, then end the (unsaved) session, which deletes it. Reads SUPABASE_URL / SUPABASE_SECRET_KEY
from the environment or the repo-root .env; never prints them. Uses a scratch SQLite database, not the hosted one."""
import base64
import os
from pathlib import Path

import pytest

from anvaya import create_app, storage
from anvaya.db import connect

pytestmark = pytest.mark.live

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")


def _env() -> dict:
    env = {k: v for k, v in os.environ.items() if k.startswith("SUPABASE_")}
    dotenv = Path(__file__).resolve().parents[2] / ".env"
    if dotenv.exists():
        for line in dotenv.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    return env


def test_upload_view_and_delete_in_the_real_bucket(tmp_path):
    env = _env()
    if not (env.get("SUPABASE_URL") and env.get("SUPABASE_SECRET_KEY")):
        pytest.skip("SUPABASE_URL / SUPABASE_SECRET_KEY not set")
    app = create_app({"DATABASE_URL": "", "DB_PATH": str(tmp_path / "live.db"), "TESTING": True,
                      "SUPABASE_URL": env["SUPABASE_URL"].rstrip("/"), "SUPABASE_SECRET_KEY": env["SUPABASE_SECRET_KEY"],
                      "LLM_EXTRACTION": False, "LLM_PROVIDERS": [], "LANGFUSE_PUBLIC_KEY": ""})
    c = app.test_client()
    sid = c.post("/api/v1/sessions", json={"mode": "personal", "language": "en"}).json["session_id"]
    issued = c.post(f"/api/v1/sessions/{sid}/documents/photo/upload-url",
                    json={"content_type": "image/png", "size": len(PNG),
                          "consent": {"version": app.config["UPLOAD_CONSENT_VERSION"], "accepted": True}}).json
    db = connect(app.config)
    path = None
    try:
        put = c.put(issued["upload_url"], data=PNG, headers={"Content-Type": "image/png"})
        assert put.status_code == 200 and put.json["status"] == "uploaded", put.json
        path = db.execute("SELECT storage_path FROM document_uploads WHERE upload_id=?", (issued["upload_id"],)).fetchone()[0]
        with app.app_context():
            assert storage.probe(path) == (len(PNG), PNG[:8])  # really in the bucket
        view = c.get(f"/api/v1/sessions/{sid}/documents/photo/view-url").json
        got = c.get(view["view_url"])
        assert got.status_code == 200 and got.data == PNG and "no-store" in got.headers["Cache-Control"]
        assert db.execute("SELECT COUNT(*) FROM audit_events WHERE action='document.viewed' AND session_id=?",
                          (sid,)).fetchone()[0] == 1
        assert c.post(f"/api/v1/sessions/{sid}/end", json={}).status_code == 200
        with app.app_context():
            assert storage.probe(path) is None  # unsaved session ended: the file is gone
        path = None
    finally:
        if path:
            with app.app_context():
                storage.delete([path])
        db.close()
