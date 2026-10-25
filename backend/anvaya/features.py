"""Runtime switches for sign-in options that are still being integrated: DigiLocker (Meri Pehchaan) and phone OTP.

GET /api/config tells the frontend how to render each option ("off" | "coming_soon" | "on"), so they can be turned
on later without rebuilding the frontend. Until an option is "on", every one of its routes answers
503 FEATURE_NOT_AVAILABLE: disabling a button in the UI is not enough.
"""
from flask import Blueprint, current_app, jsonify

from .common import ApiError

STATUSES = ("off", "coming_soon", "on")


def status(key: str) -> str:
    """Normalised status of a feature flag. Anything unrecognised counts as "coming_soon" (visible, never usable)."""
    value = str(current_app.config.get(key) or "coming_soon").strip().lower()
    return value if value in STATUSES else "coming_soon"


config_bp = Blueprint("public_config", __name__)


@config_bp.get("/api/config")
def public_config():
    resp = jsonify({
        "digilocker_status": status("DIGILOCKER_STATUS"),
        "phone_otp_status": status("PHONE_OTP_STATUS"),
        # A Turnstile *site* key is public by design (it is embedded in the page); the secret key is never sent.
        "turnstile_site_key": current_app.config.get("TURNSTILE_SITE_KEY") or None,
    })
    resp.headers["Cache-Control"] = "no-store"
    return resp


guard_bp = Blueprint("feature_guards", __name__, url_prefix="/api/v1/auth")
_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]


def _guard(key: str, label: str):
    if status(key) != "on":
        raise ApiError("FEATURE_NOT_AVAILABLE", f"{label} is not available yet.", 503, {"feature": key.lower()})
    # Switched on, but the provider integration has not landed in this build.
    raise ApiError("NOT_IMPLEMENTED", f"{label} is switched on but not implemented in this build.", 501, {"feature": key.lower()})


@guard_bp.route("/digilocker", methods=_METHODS)
@guard_bp.route("/digilocker/<path:_rest>", methods=_METHODS)
def digilocker(_rest: str = ""):
    _guard("DIGILOCKER_STATUS", "DigiLocker sign-in")


@guard_bp.route("/phone", methods=_METHODS)
@guard_bp.route("/phone/<path:_rest>", methods=_METHODS)
def phone_otp(_rest: str = ""):
    _guard("PHONE_OTP_STATUS", "Phone OTP sign-in")
