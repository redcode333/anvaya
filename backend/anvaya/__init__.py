import hmac
import logging
import os
import time
import uuid
from pathlib import Path

from flask import Flask, Response, g, jsonify, request, send_from_directory

from . import metrics
from .config import PROJECT_DIR, Config
from .db import close_db, connect


def create_app(overrides: dict | None = None) -> Flask:
    dist = Path(os.environ.get("ANVAYA_FRONTEND_DIST", PROJECT_DIR / "frontend" / "dist"))
    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    if overrides:
        app.config.update(overrides)
    app.json.ensure_ascii = False
    app.json.sort_keys = False

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    log = logging.getLogger("anvaya.http")

    from . import auth, migrations, startup
    db = connect(app.config)
    try:
        applied = migrations.migrate(db)
    finally:
        db.close()
    log.info("database: %s%s", db.dialect, f" (applied migrations {applied})" if applied else "")
    app.extensions["anvaya.startup"] = startup.check(app.config)
    if app.config["LANGFUSE_PUBLIC_KEY"] and app.config["LANGFUSE_SECRET_KEY"] and app.config["LANGFUSE_BASE_URL"]:
        from .llm import tracing
        with app.app_context():
            try:
                tracing.client()  # import + set up once at boot, not inside the first traced turn
            except Exception:  # noqa: BLE001 - tracing is optional
                log.warning("langfuse: client setup failed; LLM extraction runs untraced")

    if app.config["RETENTION_INTERVAL_MIN"] > 0 and not app.config.get("TESTING"):
        _start_retention(app, log)

    @app.before_request
    def _start():
        # 32 hex chars: also the Langfuse trace id of an LLM-extraction turn (W3C / OpenTelemetry trace-id format).
        g.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex
        g.t0 = time.perf_counter()
        auth.authenticate_request()  # verifies a bearer token, if any (401 when it is not valid)

    csp = content_security_policy(app.config)

    @app.after_request
    def _finish(resp):
        resp.headers["X-Request-Id"] = g.get("request_id", "")
        # Only this origin, the Supabase project (sign-in) and Cloudflare Turnstile; responses that set their own
        # policy (document views) keep it.
        resp.headers.setdefault("Content-Security-Policy", csp)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=(self)")
        if request.path.startswith("/api/"):
            elapsed = time.perf_counter() - g.get("t0", time.perf_counter())
            route = request.url_rule.rule if request.url_rule else "unmatched"
            metrics.HTTP_REQUESTS.labels(request.method, route, str(resp.status_code)).inc()
            metrics.HTTP_LATENCY.labels(request.method, route).observe(elapsed)
            db = g.get("db")
            queries, roundtrips, db_ms = (db.queries, db.roundtrips, db.ms) if db else (0, 0, 0.0)
            metrics.DB_QUERIES.labels(request.method, route).observe(queries)
            metrics.DB_ROUNDTRIPS.labels(request.method, route).observe(roundtrips)
            # Path + status + timing + DB counts only: no bodies, no query strings, no SQL, no PII.
            log.info("rid=%s %s %s %s %.1fms db_queries=%d db_roundtrips=%d db_ms=%.1f", g.get("request_id"),
                     request.method, route, resp.status_code, elapsed * 1000, queries, roundtrips, db_ms)
        return resp

    app.teardown_appcontext(close_db)

    from .api import bp
    from .common import ApiError

    @app.errorhandler(ApiError)
    def _api_error(e: ApiError):
        return jsonify({"error": {"code": e.code, "message": e.message, "details": e.details,
                                  "request_id": g.get("request_id")}}), e.status

    @app.errorhandler(404)
    def _not_found(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": {"code": "NOT_FOUND", "message": "No such endpoint.", "request_id": g.get("request_id")}}), 404
        return _spa("index.html")

    @app.errorhandler(500)
    def _server_error(e):
        return jsonify({"error": {"code": "INTERNAL", "message": "Unexpected server error; safe to retry.",
                                  "request_id": g.get("request_id")}}), 500

    app.register_blueprint(bp)

    @app.get("/metrics")
    def prometheus_metrics():
        from .db import get_db, iso
        token = app.config["METRICS_TOKEN"]
        if token and not hmac.compare_digest(request.headers.get("Authorization", ""), f"Bearer {token}"):
            return jsonify({"error": {"code": "UNAUTHENTICATED", "message": "Metrics require a bearer token."}}), 401
        body, ctype = metrics.render(get_db(), iso())
        return Response(body, mimetype=ctype.split(";")[0], headers={"Content-Type": ctype})

    def _spa(path):
        if not dist.exists():
            return jsonify({"message": "Frontend not built. Run `npm run build` in frontend/ or use the Vite dev server."}), 404
        target = dist / path
        if path and target.is_file():
            return send_from_directory(dist, path)
        return send_from_directory(dist, "index.html")

    @app.get("/")
    @app.get("/<path:path>")
    def spa(path=""):
        if path.startswith("api/"):  # unknown API paths are JSON 404s, never the app shell
            return _not_found(None)
        return _spa(path)

    return app


TURNSTILE_ORIGIN = "https://challenges.cloudflare.com"


def content_security_policy(cfg) -> str:
    """Strict CSP: scripts only from this origin and Turnstile, network calls only to this origin and the Supabase
    project, frames only for Turnstile and our own document previews. data: images are the MFA QR code; data:/blob:
    media is synthesized speech. No inline scripts, no eval."""
    supabase = cfg.get("SUPABASE_URL") or ""
    return "; ".join([
        "default-src 'self'",
        f"script-src 'self' {TURNSTILE_ORIGIN}",
        "style-src 'self'",
        "img-src 'self' data: blob:",
        "media-src 'self' data: blob:",
        "font-src 'self'",
        f"connect-src 'self' {supabase}".strip(),
        f"frame-src 'self' {TURNSTILE_ORIGIN}",
        "worker-src 'self'",
        "manifest-src 'self'",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "frame-ancestors 'self'",
    ])


def _start_retention(app: Flask, log: logging.Logger) -> None:
    """Delete expired data (accounts.purge_expired) shortly after start and then every RETENTION_INTERVAL_MIN."""
    import threading

    from .accounts import purge_expired

    def run():
        db = connect(app.config)
        try:
            with app.app_context():
                r = purge_expired(db, app.config)
            if any(r.values()):
                log.info("retention: %s", r)  # counts only
        except Exception as e:  # noqa: BLE001 - retry at the next interval
            log.warning("retention: run failed (%s)", type(e).__name__)
        finally:
            db.close()
        schedule(app.config["RETENTION_INTERVAL_MIN"] * 60)

    def schedule(delay: float):
        t = threading.Timer(delay, run)
        t.daemon = True
        t.start()
    schedule(30)
