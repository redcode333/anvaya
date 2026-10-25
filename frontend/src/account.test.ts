import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./api";
import {
  CONSENT_VERSION, deleteAccount, ensureAnonymous, formatCode, loadHistory, pinProblem, saveWithConsent, sendEmailCode,
  staffSignIn, verifyEmailCode, whatChanged, type AuthLike,
} from "./account";
import { reasonText } from "./pages/MyPassports";

// A fake of the supabase-js auth calls the app uses; it records every call.
function fakeAuth(session: any = null, errors: Record<string, string> = {}) {
  const calls: [string, any][] = [];
  let current = session;
  const res = (name: string, data: any) => {
    calls.push([name, undefined]);
    return Promise.resolve({ data, error: errors[name] ? { message: errors[name], code: "auth_error" } : null });
  };
  const auth: AuthLike = {
    getSession: () => Promise.resolve({ data: { session: current }, error: null }),
    signInAnonymously: () => { current = { access_token: "anon", user: { id: "u-1", is_anonymous: true } }; return res("signInAnonymously", { user: current.user }); },
    updateUser: (a) => { calls.push(["updateUser", a]); return res("updateUser.done", {}); },
    verifyOtp: (p) => { calls.push(["verifyOtp", p]); return res("verifyOtp.done", {}); },
    signInWithOtp: (p) => { calls.push(["signInWithOtp", p]); return res("signInWithOtp.done", {}); },
    signInWithPassword: (p) => { calls.push(["signInWithPassword", p]); return res("signInWithPassword.done", {}); },
    signOut: (o) => { calls.push(["signOut", o]); current = null; return Promise.resolve({ error: null }); },
  };
  return { auth, calls, named: (n: string) => calls.filter((c) => c[0] === n).map((c) => c[1]) };
}

const store: Record<string, string> = {};
beforeEach(() => {
  for (const k of Object.keys(store)) delete store[k];
  (globalThis as any).sessionStorage = {
    getItem: (k: string) => store[k] ?? null, setItem: (k: string, v: string) => { store[k] = v; },
    removeItem: (k: string) => { delete store[k]; }, key: () => null, length: 0, clear: () => undefined,
  };
});

describe("personal mode starts anonymous", () => {
  it("signs in anonymously only when there is no session", async () => {
    const f = fakeAuth();
    const api = vi.fn().mockResolvedValue({});
    expect(await ensureAnonymous(f.auth, null, api as any)).toBe("u-1");
    expect(await ensureAnonymous(f.auth, null, api as any)).toBe("u-1");
    expect(f.calls.filter((c) => c[0] === "signInAnonymously")).toHaveLength(1);
  });
});

describe("save my passports", () => {
  it("links an email to the anonymous user (same id) and verifies the code as an email change", async () => {
    const f = fakeAuth({ access_token: "a", user: { id: "u-1", is_anonymous: true } });
    expect(await sendEmailCode(f.auth, "asha@example.org")).toBe("link");
    expect(f.named("updateUser")).toEqual([{ email: "asha@example.org" }]);
    await verifyEmailCode(f.auth, "asha@example.org", "123456", "link");
    expect(f.named("verifyOtp")).toEqual([{ email: "asha@example.org", token: "123456", type: "email_change" }]);
    expect(f.named("signInWithOtp")).toEqual([]);
  });

  it("a returning citizen signs in with an email code without creating a new account", async () => {
    const f = fakeAuth(null);
    expect(await sendEmailCode(f.auth, "asha@example.org")).toBe("signin");
    expect(f.named("signInWithOtp")).toEqual([{ email: "asha@example.org", options: { shouldCreateUser: false } }]);
    await verifyEmailCode(f.auth, "asha@example.org", " 654321 ", "signin");
    expect(f.named("verifyOtp")[0].type).toBe("email");
  });

  it("refuses a malformed code before calling Supabase", async () => {
    const f = fakeAuth(null);
    await expect(verifyEmailCode(f.auth, "a@b.c", "12ab", "signin")).rejects.toMatchObject({ code: "INVALID_CODE" });
    expect(f.named("verifyOtp")).toEqual([]);
  });

  it("records consent with the current text version", async () => {
    const api = vi.fn().mockResolvedValue({ saved: true });
    await saveWithConsent("te", api as any);
    expect(api).toHaveBeenCalledWith("/account/consent", { body: { consent: { version: CONSENT_VERSION, accepted: true, language: "te" } } });
  });

  it("surfaces Supabase errors", async () => {
    const f = fakeAuth({ access_token: "a", user: { id: "u-1", is_anonymous: true } }, { "updateUser.done": "Email rate limit exceeded" });
    await expect(sendEmailCode(f.auth, "a@b.c")).rejects.toBeInstanceOf(ApiError);
  });
});

describe("staff sign-in", () => {
  it("accepts a staff account whose server-side role fits the page", async () => {
    const f = fakeAuth(null);
    const api = vi.fn().mockResolvedValue({ user: { user_id: "s", username: "r@x.org", role: "reviewer", display_name: "r@x.org" } });
    const u = await staffSignIn(f.auth, "r@x.org", "pw", ["reviewer", "admin"], api as any);
    expect(u.user.role).toBe("reviewer");
    expect(u.mfa_required).toBe(false);
    expect(f.named("signInWithPassword")).toEqual([{ email: "r@x.org", password: "pw", options: {} }]);
    expect(f.named("signOut")).toEqual([]);
  });

  it("signs out again when the role does not fit (or the account is a citizen)", async () => {
    for (const me of [{ user: { role: "operator" } }, { citizen: { user_id: "c" } }]) {
      const f = fakeAuth(null);
      await expect(staffSignIn(f.auth, "o@x.org", "pw", ["reviewer"], vi.fn().mockResolvedValue(me) as any)).rejects.toMatchObject({ code: "FORBIDDEN" });
      expect(f.named("signOut")).toEqual([{ scope: "local" }]);
    }
  });
});

describe("history and what changed", () => {
  it("reads the account history, or a code holder's through their session", async () => {
    const api = vi.fn().mockResolvedValue({ versions: [] });
    await loadHistory(null, api as any);
    await loadHistory("SES_1", api as any);
    expect(api.mock.calls.map((c) => c[0])).toEqual(["/account/passports", "/sessions/SES_1/passports"]);
  });

  it("encodes the date (a '+' in the time zone must survive the query string)", async () => {
    const api = vi.fn().mockResolvedValue({ changes: [] });
    await whatChanged("2026-10-01T23:59:59+00:00", null, api as any);
    expect(api.mock.calls[0][0]).toBe("/account/passports/changes?since=2026-10-01T23%3A59%3A59%2B00%3A00");
  });

  it("explains each change: a fact, a rule version or a document", () => {
    expect(reasonText({ kind: "fact_changed", attribute: "age", before: 67, after: 52 }, "en")).toBe("your detail changed: Age 67 → 52");
    expect(reasonText({ kind: "rule_changed", rule_id: "R_X", before: 1, after: 2 }, "en")).toBe("the scheme rule was updated: R_X v1 → v2");
    expect(reasonText({ kind: "fact_changed", attribute: "age", before: 67, after: 52 }, "hi")).toContain("उम्र 67 → 52");
  });
});

describe("delete my account", () => {
  it("deletes on the server first, then forgets the local session", async () => {
    const order: string[] = [];
    const f = fakeAuth({ access_token: "a", user: { id: "u-1" } });
    const signOut = f.auth.signOut;
    f.auth.signOut = (o) => { order.push("signOut"); return signOut(o); };
    const api = vi.fn().mockImplementation(async () => { order.push("api"); return { deleted: true }; });
    await deleteAccount(f.auth, {}, api as any);
    expect(api).toHaveBeenCalledWith("/account", { method: "DELETE" });
    expect(order).toEqual(["api", "signOut"]);
  });

  it("keeps the session until a pending case is confirmed, then sends the confirmation", async () => {
    const f = fakeAuth({ access_token: "a", user: { id: "u-1" } });
    const api = vi.fn().mockRejectedValueOnce(new ApiError("PENDING_CASE_DOCUMENTS", "confirm", 409, { pending_cases: 1, documents: 2 }))
      .mockResolvedValueOnce({ deleted: true });
    await expect(deleteAccount(f.auth, {}, api as any)).rejects.toMatchObject({ code: "PENDING_CASE_DOCUMENTS", details: { documents: 2 } });
    expect(f.named("signOut")).toEqual([]);
    await deleteAccount(f.auth, { acknowledgePendingCase: true }, api as any);
    expect(api).toHaveBeenLastCalledWith("/account", { method: "DELETE", body: { acknowledge_pending_case: true } });
    expect(f.named("signOut")).toHaveLength(1);
  });

  it("keeps the session when the server refuses", async () => {
    const f = fakeAuth({ access_token: "a", user: { id: "u-1" } });
    const api = vi.fn().mockRejectedValue(new ApiError("ACCOUNT_DELETE_FAILED", "try again", 502));
    await expect(deleteAccount(f.auth, {}, api as any)).rejects.toMatchObject({ code: "ACCOUNT_DELETE_FAILED" });
    expect(f.named("signOut")).toEqual([]);
  });
});

describe("Passport code + PIN helpers", () => {
  it("mirrors the server's weak-PIN rules", () => {
    for (const weak of ["1111", "1234", "9876", "1212", "1122", "1999", "2580"]) expect(pinProblem(weak)).toBe("weak");
    for (const bad of ["123", "12a4", "12345"]) expect(pinProblem(bad)).toBe("format");
    expect(pinProblem("4826")).toBeNull();
  });
  it("formats typed codes", () => {
    expect(formatCode("psp7k2m9qrt")).toBe("PSP-7K2M-9QRT");
    expect(formatCode("7k2m")).toBe("PSP-7K2M");
  });
});
