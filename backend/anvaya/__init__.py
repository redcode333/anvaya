import hmac
import logging
import os
import time
import uuid
from pathlib import Path

from flask import Flask, Response, g, jsonify, request, send_from_directory

from . import metrics
from .config import PROJECT_DIR, Config
from .db import close_db, connect, init_schema


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

    from . import startup
    from .ingest import seed_users
    conn = connect(app.config["DB_PATH"])
    try:
        init_schema(conn)
        demo_users = seed_users(conn)
    finally:
        conn.close()
    app.extensions["anvaya.startup"] = startup.check(app.config, demo_users)

    @app.before_request
    def _start():
        g.request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:16]
        g.t0 = time.perf_counter()

    @app.after_request
    def _finish(resp):
        resp.headers["X-Request-Id"] = g.get("request_id", "")
        if request.path.startswith("/api/"):
            elapsed = time.perf_counter() - g.get("t0", time.perf_counter())
            route = request.url_rule.rule if request.url_rule else "unmatched"
            metrics.HTTP_REQUESTS.labels(request.method, route, str(resp.status_code)).inc()
            metrics.HTTP_LATENCY.labels(request.method, route).observe(elapsed)
            # Path + status + timing only: no bodies, no query strings, no PII.
            log.info("rid=%s %s %s %s %.1fms", g.get("request_id"), request.method, route, resp.status_code, elapsed * 1000)
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
        return _spa(path)

    return app
