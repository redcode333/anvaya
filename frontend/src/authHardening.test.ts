import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, sessionInHeader, setKioskDeviceProvider } from "./api";
import {
  changeStaffPassword, downloadMyData, ensureAnonymous, nextMfaStep, normalizePhone, sendEmailCode, signOutEverywhere,
  staffSignIn, startDigiLocker, verifyMfa, type AuthLike, type MfaLike,
} from "./account";
import { authStorage, clearPersistedAuth } from "./authStorage";
import { absoluteLimitMs } from "./idle";
import { consentNotice } from "./i18n";

function memoryStorage() {
  const m: Record<string, string> = {};
  return {
    data: m,
    getItem: (k: string) => m[k] ?? null, setItem: (k: string, v: string) => { m[k] = String(v); },
    removeItem: (k: string) => { delete m[k]; }, key: (i: number) => Object.keys(m)[i] ?? null,
    get length() { return Object.keys(m).length; }, clear: () => { for (const k of Object.keys(m)) delete m[k]; },
  };
}
let local: ReturnType<typeof memoryStorage>, session: ReturnType<typeof memoryStorage>;
beforeEach(() => {
  local = memoryStorage(); session = memoryStorage();
  vi.stubGlobal("localStorage", new Proxy(local, { ownKeys: () => Object.keys(local.data), getOwnPropertyDescriptor: (_, k) => ({ enumerable: true, configurable: true, value: local.data[k as string] }) }));
  vi.stubGlobal("sessionStorage", session);
});

function fakeAuth(over: Partial<AuthLike> = {}) {
  const calls: [string, any][] = [];
  const ok = (name: string, data: any = {}) => (p?: any) => { calls.push([name, p]); return Promise.resolve({ data, error: null }); };
  const auth: AuthLike = {
    getSession: () => Promise.resolve({ data: { session: null }, error: null }),
    signInAnonymously: ok("signInAnonymously", { user: { id: "u-1" } }) as any,
    updateUser: ok("updateUser") as any, verifyOtp: ok("verifyOtp") as any, signInWithOtp: ok("signInWithOtp") as any,
    signInWithPassword: ok("signInWithPassword") as any,
    signOut: (o) => { calls.push(["signOut", o]); return Promise.resolve({ error: null }); },
    ...over,
  };
  return { auth, calls, named: (n: string) => calls.filter((c) => c[0] === n).map((c) => c[1]) };
}

describe("session ids never go in a URL", () => {
  it("moves /sessions/<id>/... into the X-Session-Id header", () => {
    const h: Record<string, string> = {};
    expect(sessionInHeader("/sessions/SES_abc123/turns", h)).toBe("/sessions/current/turns");
    expect(h["X-Session-Id"]).toBe("SES_abc123");
    const h2: Record<string, string> = {};
    expect(sessionInHeader("/sessions/SES_x", h2)).toBe("/sessions/current");
    expect(sessionInHeader("/sessions/SES_x/passports/changes?since=2026", {})).toBe("/sessions/current/passports/changes?since=2026");
    expect(sessionInHeader("/sessions", {})).toBe("/sessions");
    expect(sessionInHeader("/account/passports", {})).toBe("/account/passports");
  });

  it("api() sends the id as a header and the kiosk device id in kiosk mode", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve({}) });
    vi.stubGlobal("fetch", fetch);
    setKioskDeviceProvider(() => "KD-0123456789abcdef");
    await api("/sessions/SES_secret0000/turns", { body: { utterance: "x" } });
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/api/v1/sessions/current/turns");
    expect(String(url)).not.toContain("SES_secret0000");
    expect(init.headers["X-Session-Id"]).toBe("SES_secret0000");
    expect(init.headers["X-Kiosk-Device"]).toBe("KD-0123456789abcdef");
    setKioskDeviceProvider(() => null);
  });
});

describe("supabase-js storage per mode", () => {
  it("kiosk: memory only, never localStorage or sessionStorage", () => {
    session.setItem("anvaya.mode", "kiosk");
    authStorage.setItem("sb-x-auth-token", "secret-session");
    expect(authStorage.getItem("sb-x-auth-token")).toBe("secret-session");
    expect(Object.keys(local.data).filter((k) => k.startsWith("sb-"))).toEqual([]);
    expect(Object.keys(session.data).filter((k) => k.startsWith("sb-"))).toEqual([]);
    authStorage.removeItem("sb-x-auth-token");
    expect(authStorage.getItem("sb-x-auth-token")).toBeNull();
  });

  it("personal: localStorage, so a reload keeps an unsaved passport", () => {
    authStorage.setItem("sb-x-auth-token", "s");
    expect(local.data["sb-x-auth-token"]).toBe("s");
  });

  it("switching to kiosk forgets a personal sign-in kept on the device", () => {
    local.setItem("sb-x-auth-token", "personal");
    local.setItem("anvaya.kioskDevice", "KD-keep-me-000");
    clearPersistedAuth();
    expect(local.data["sb-x-auth-token"]).toBeUndefined();
    expect(local.data["anvaya.kioskDevice"]).toBe("KD-keep-me-000");
  });
});

describe("kiosk session in memory only", () => {
  it("a reload (fresh state) never brings back a kiosk session id", async () => {
    const { initialSessionId } = await import("./state");
    session.setItem("anvaya.session", "SES_old");
    expect(initialSessionId("kiosk")).toBeNull();
    expect(session.getItem("anvaya.session")).toBeNull();
    session.setItem("anvaya.session", "SES_personal");
    expect(initialSessionId("personal")).toBe("SES_personal");
  });

  it("a kiosk device id is random, stable and well-formed", async () => {
    const { kioskDeviceId } = await import("./state");
    const a = kioskDeviceId();
    expect(a).toMatch(/^KD-[0-9a-f]{32}$/);
    expect(kioskDeviceId()).toBe(a);
  });

  it("the 30-minute limit fires at the server's expires_at", () => {
    const now = Date.parse("2026-10-25T10:00:00Z");
    expect(absoluteLimitMs("2026-10-25T10:30:00+00:00", now)).toBe(30 * 60 * 1000);
    expect(absoluteLimitMs("2026-10-25T09:59:00+00:00", now)).toBe(0);
    expect(absoluteLimitMs("garbage", now)).toBe(0);
  });
});

describe("Turnstile token goes to Supabase", () => {
  it("anonymous sign-in and email OTP carry captchaToken; without a site key nothing is added", async () => {
    const f = fakeAuth();
    const report = vi.fn().mockResolvedValue({});
    await ensureAnonymous(f.auth, "tok-1", report as any);
    expect(f.named("signInAnonymously")).toEqual([{ options: { captchaToken: "tok-1" } }]);
    await sendEmailCode(f.auth, "a@b.org", "tok-2", report as any);
    expect(f.named("signInWithOtp")).toEqual([{ email: "a@b.org", options: { shouldCreateUser: false, captchaToken: "tok-2" } }]);
    const g = fakeAuth();
    await ensureAnonymous(g.auth, null, report as any);
    expect(g.named("signInAnonymously")).toEqual([{ options: {} }]);
    expect(report.mock.calls.map((c) => c[1].body)).toEqual([
      { event: "sign_in_success", method: "anonymous" }, { event: "otp_requested", method: "email_otp" },
      { event: "sign_in_success", method: "anonymous" }]);
  });

  it("staff password sign-in carries it too and reports whether the TOTP step is needed", async () => {
    const f = fakeAuth();
    const api = vi.fn().mockImplementation(async (p: string) => (p === "/auth/me"
      ? { user: { user_id: "s", role: "operator" }, mfa_required: true } : {}));
    const me = await staffSignIn(f.auth, "o@x.org", "pw", ["operator"], api as any, "tok-3");
    expect(f.named("signInWithPassword")[0].options).toEqual({ captchaToken: "tok-3" });
    expect(me.mfa_required).toBe(true);
  });
});

function fakeMfa(factors: any[]) {
  const calls: [string, any][] = [];
  const mfa: MfaLike = {
    listFactors: () => Promise.resolve({ data: { totp: factors.filter((f) => f.status === "verified"), all: factors }, error: null }),
    enroll: (p) => { calls.push(["enroll", p]); return Promise.resolve({ data: { id: "f-new", totp: { qr_code: "data:image/svg+xml;utf-8,<svg/>", secret: "JBSWY3DPEHPK3PXP", uri: "otpauth://totp/x" } }, error: null }); },
    challengeAndVerify: (p) => { calls.push(["verify", p]); return Promise.resolve({ data: {}, error: p.code === "000000" ? { message: "Invalid TOTP code" } : null }); },
    unenroll: (p) => { calls.push(["unenroll", p]); return Promise.resolve({ data: {}, error: null }); },
    getAuthenticatorAssuranceLevel: () => Promise.resolve({ data: { currentLevel: "aal1", nextLevel: "aal2" }, error: null }),
  };
  return { mfa, calls };
}

describe("staff TOTP", () => {
  it("first sign-in enrols (QR + manual key), dropping an abandoned unverified factor", async () => {
    const m = fakeMfa([{ id: "f-old", factor_type: "totp", status: "unverified" }]);
    const step = await nextMfaStep({ ...fakeAuth().auth, mfa: m.mfa });
    expect(step).toMatchObject({ kind: "enroll", factorId: "f-new", secret: "JBSWY3DPEHPK3PXP" });
    expect(step.kind === "enroll" && step.qr.startsWith("data:image/svg+xml")).toBe(true);
    expect(m.calls.map((c) => c[0])).toEqual(["unenroll", "enroll"]);
  });

  it("later sign-ins verify the enrolled factor; a wrong code fails and is reported", async () => {
    const m = fakeMfa([{ id: "f-1", factor_type: "totp", status: "verified" }]);
    const auth = { ...fakeAuth().auth, mfa: m.mfa };
    const step = await nextMfaStep(auth);
    expect(step).toEqual({ kind: "verify", factorId: "f-1" });
    const report = vi.fn().mockResolvedValue({});
    await expect(verifyMfa(auth, step, "000000", report as any)).rejects.toBeTruthy();
    await verifyMfa(auth, step, "123456", report as any);
    expect(report.mock.calls.map((c) => c[1].body.event)).toEqual(["mfa_failed", "mfa_verified"]);
    await expect(verifyMfa(auth, step, "12", report as any)).rejects.toMatchObject({ code: "INVALID_CODE" });
  });
});

describe("sign out of all devices", () => {
  it("revokes on the server, then drops the local session even if the server call fails", async () => {
    const f = fakeAuth();
    const api = vi.fn().mockResolvedValue({ signed_out: true });
    await signOutEverywhere(f.auth, api as any);
    expect(api).toHaveBeenCalledWith("/auth/sign-out-all", { body: { reason: "user" } });
    expect(f.named("signOut")).toEqual([{ scope: "local" }]);
    const g = fakeAuth();
    await expect(signOutEverywhere(g.auth, vi.fn().mockRejectedValue(new Error("down")) as any)).rejects.toThrow();
    expect(g.named("signOut")).toEqual([{ scope: "local" }]);
  });

  it("a staff password change signs out everywhere", async () => {
    const f = fakeAuth();
    const api = vi.fn().mockResolvedValue({});
    await expect(changeStaffPassword(f.auth, "short", api as any)).rejects.toMatchObject({ code: "WEAK_PASSWORD" });
    await changeStaffPassword(f.auth, "a-long-new-password", api as any);
    expect(f.named("updateUser")).toEqual([{ password: "a-long-new-password" }]);
    expect(api).toHaveBeenCalledWith("/auth/sign-out-all", { body: { reason: "password_changed" } });
  });
});

describe("citizen rights", () => {
  it("download my data reads the export (account, or a resumed session) and saves it", async () => {
    const api = vi.fn().mockResolvedValue({ format: "anvaya-my-data/1" });
    const saved: string[] = [];
    await downloadMyData(null, api as any, (j) => saved.push(j));
    await downloadMyData("SES_1", api as any, (j) => saved.push(j));
    expect(api.mock.calls.map((c) => c[0])).toEqual(["/account/export", "/sessions/SES_1/export"]);
    expect(JSON.parse(saved[0]).format).toBe("anvaya-my-data/1");
  });

  it("the consent notice states purpose, what is stored, retention and withdrawal in en/hi/te", () => {
    const r = { unsaved_hours: 24, passport_days: 365, stale_fact_days: 90 };
    for (const lang of ["en", "hi", "te"] as const) {
      const n = consentNotice(lang, r);
      expect(n).toHaveLength(4);
      expect(n[2][1]).toContain("24");
      expect(n[2][1]).toContain("365");
    }
    expect(consentNotice("en", r).map((x) => x[0])).toEqual(["Purpose", "What is stored", "How long", "How to withdraw"]);
    expect(consentNotice("en", r)[1][1]).toContain("never ask for or store your Aadhaar number");
  });

  it("DigiLocker start asks the server for the URL with the session in a header", async () => {
    const api = vi.fn().mockResolvedValue({ authorization_url: "https://provider.example/authorize?x=1" });
    expect(await startDigiLocker("SES_9", api as any)).toBe("https://provider.example/authorize?x=1");
    expect(api).toHaveBeenCalledWith("/auth/digilocker/start", { body: {}, sessionId: "SES_9" });
  });

  it("phone OTP accepts Indian mobile numbers only", () => {
    expect(normalizePhone("98765 43210")).toBe("+919876543210");
    expect(normalizePhone("+91-98765-43210")).toBe("+919876543210");
    expect(normalizePhone("09876543210")).toBe("+919876543210");
    expect(normalizePhone("12345")).toBeNull();
    expect(normalizePhone("5876543210")).toBeNull();
  });
});
