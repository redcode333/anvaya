"""Runtime switches for sign-in options, read by the frontend from GET /api/config ("off" | "coming_soon" | "on"), so an
option can be turned on without rebuilding the frontend.

* DigiLocker (Meri Pehchaan): "on" exactly when the adapter is enabled and fully configured (digilocker.enabled); otherwise
  the configured value, where an "on" that cannot work is shown as "coming_soon". Its routes live in api.py.
* Phone OTP: still being integrated. Until "on", its routes answer 503 FEATURE_NOT_AVAILABLE (a disabled button in the UI is
  not enough); switched on without an integration they answer 501, never a silent success.
"""
from flask import Blueprint, current_app, jsonify

from . import digilocker
from .common import ApiError

STATUSES = ("off", "coming_soon", "on")


def status(key: str) -> str:
    """Normalised status of a feature flag. Anything unrecognised counts as "coming_soon" (visible, never usable)."""
    value = str(current_app.config.get(key) or "coming_soon").strip().lower()
    return value if value in STATUSES else "coming_soon"


def digilocker_status() -> str:
    if digilocker.enabled(current_app.config):
        return "on"
    configured = status("DIGILOCKER_STATUS")
    return "coming_soon" if configured == "on" else configured


config_bp = Blueprint("public_config", __name__)


@config_bp.get("/api/config")
def public_config():
    resp = jsonify({
        "digilocker_status": digilocker_status(),
        "phone_otp_status": status("PHONE_OTP_STATUS"),
        # A Turnstile *site* key is public by design (it is embedded in the page); the secret key is never sent.
        "turnstile_site_key": current_app.config.get("TURNSTILE_SITE_KEY") or None,
    })
    resp.headers["Cache-Control"] = "no-store"
    return resp


guard_bp = Blueprint("feature_guards", __name__, url_prefix="/api/v1/auth")
_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


@guard_bp.route("/phone", methods=_METHODS)
@guard_bp.route("/phone/<path:_rest>", methods=_METHODS)
def phone_otp(_rest: str = ""):
    if status("PHONE_OTP_STATUS") != "on":
        raise ApiError("FEATURE_NOT_AVAILABLE", "Phone OTP sign-in is not available yet.", 503, {"feature": "phone_otp_status"})
    raise ApiError("NOT_IMPLEMENTED", "Phone OTP sign-in is switched on but not implemented in this build.", 501,
                   {"feature": "phone_otp_status"})
