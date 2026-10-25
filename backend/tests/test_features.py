"""GET /api/config, the phone OTP guard and the DigiLocker status that follows the adapter."""
import pytest

PHONE_ROUTES = [("POST", "/api/v1/auth/phone/otp/send"), ("POST", "/api/v1/auth/phone/otp/verify")]


def test_config_defaults_to_coming_soon(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    assert r.json == {"digilocker_status": "coming_soon", "phone_otp_status": "coming_soon", "turnstile_site_key": None}
    assert r.headers["Cache-Control"] == "no-store"


def test_config_reflects_runtime_values(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "PHONE_OTP_STATUS", "OFF")
    monkeypatch.setitem(app.config, "DIGILOCKER_STATUS", "off")
    monkeypatch.setitem(app.config, "TURNSTILE_SITE_KEY", "1x00000000000000000000AA")
    assert client.get("/api/config").json == {"digilocker_status": "off", "phone_otp_status": "off",
                                              "turnstile_site_key": "1x00000000000000000000AA"}


def test_unknown_status_is_treated_as_coming_soon(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "PHONE_OTP_STATUS", "maybe")
    assert client.get("/api/config").json["phone_otp_status"] == "coming_soon"


def test_digilocker_on_only_when_the_adapter_works(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "DIGILOCKER_STATUS", "on")  # asked for, but the adapter is not configured
    assert client.get("/api/config").json["digilocker_status"] == "coming_soon"
    from anvaya import digilocker
    monkeypatch.setattr(digilocker, "enabled", lambda cfg: True)
    assert client.get("/api/config").json["digilocker_status"] == "on"


@pytest.mark.parametrize("flag", ["coming_soon", "off"])
@pytest.mark.parametrize("method,path", PHONE_ROUTES)
def test_phone_routes_503_unless_on(client, app, monkeypatch, flag, method, path):
    monkeypatch.setitem(app.config, "PHONE_OTP_STATUS", flag)
    r = client.open(path, method=method, json={"phone": "9876543210"})
    assert r.status_code == 503
    assert r.json["error"]["code"] == "FEATURE_NOT_AVAILABLE"


def test_phone_switched_on_without_integration_is_501_not_a_silent_success(client, app, monkeypatch):
    monkeypatch.setitem(app.config, "PHONE_OTP_STATUS", "on")
    assert client.post("/api/v1/auth/phone/otp/send", json={}).status_code == 501


def test_turnstile_key_accepts_either_variable_name(monkeypatch):
    import importlib

    from anvaya import config
    try:
        monkeypatch.delenv("VITE_TURNSTILE_SITE_KEY", raising=False)
        monkeypatch.setenv("TURNSTILE_SITE_KEY", "0xserver")
        assert importlib.reload(config).Config.TURNSTILE_SITE_KEY == "0xserver"
        monkeypatch.setenv("VITE_TURNSTILE_SITE_KEY", " 0xvite ")
        assert importlib.reload(config).Config.TURNSTILE_SITE_KEY == "0xvite"
    finally:
        monkeypatch.undo()
        importlib.reload(config)
