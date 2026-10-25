"""GET /api/config and the 503 guards on sign-in options that are still being integrated."""
import pytest

DIGILOCKER_ROUTES = [("GET", "/api/v1/auth/digilocker/start"), ("GET", "/api/v1/auth/digilocker/callback?code=x&state=y"),
                     ("POST", "/api/v1/auth/digilocker/link"), ("DELETE", "/api/v1/auth/digilocker/link"),
                     ("GET", "/api/v1/auth/digilocker/me")]
PHONE_ROUTES = [("POST", "/api/v1/auth/phone/otp/send"), ("POST", "/api/v1/auth/phone/otp/verify")]


def test_config_defaults_to_coming_soon(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    assert r.json == {"digilocker_status": "coming_soon", "phone_otp_status": "coming_soon", "turnstile_site_key": None}
    assert r.headers["Cache-Control"] == "no-store"


def test_config_reflects_runtime_values(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "DIGILOCKER_STATUS", "on")
    monkeypatch.setitem(app.config, "PHONE_OTP_STATUS", "OFF")
    monkeypatch.setitem(app.config, "TURNSTILE_SITE_KEY", "1x00000000000000000000AA")
    assert client.get("/api/config").json == {"digilocker_status": "on", "phone_otp_status": "off",
                                              "turnstile_site_key": "1x00000000000000000000AA"}


def test_unknown_status_is_treated_as_coming_soon(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "DIGILOCKER_STATUS", "maybe")
    assert client.get("/api/config").json["digilocker_status"] == "coming_soon"


@pytest.mark.parametrize("flag", ["coming_soon", "off"])
@pytest.mark.parametrize("method,path", DIGILOCKER_ROUTES)
def test_digilocker_routes_503_unless_on(client, app, monkeypatch, flag, method, path):
    monkeypatch.setitem(app.config, "DIGILOCKER_STATUS", flag)
    r = client.open(path, method=method)
    assert r.status_code == 503
    assert r.json["error"]["code"] == "FEATURE_NOT_AVAILABLE"


@pytest.mark.parametrize("flag", ["coming_soon", "off"])
@pytest.mark.parametrize("method,path", PHONE_ROUTES)
def test_phone_routes_503_unless_on(client, app, monkeypatch, flag, method, path):
    monkeypatch.setitem(app.config, "PHONE_OTP_STATUS", flag)
    r = client.open(path, method=method, json={"phone": "9876543210"})
    assert r.status_code == 503
    assert r.json["error"]["code"] == "FEATURE_NOT_AVAILABLE"


def test_switched_on_without_integration_is_501_not_a_silent_success(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "DIGILOCKER_STATUS", "on")
    monkeypatch.setitem(app.config, "PHONE_OTP_STATUS", "on")
    assert client.get("/api/v1/auth/digilocker/start").status_code == 501
    assert client.post("/api/v1/auth/phone/otp/send", json={}).status_code == 501


def test_staff_login_untouched(client):
    r = client.post("/api/v1/auth/login", json={"username": "reviewer", "password": "reviewer123"})
    assert r.status_code == 200 and r.json["token"]
