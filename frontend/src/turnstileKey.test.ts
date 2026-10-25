import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// A developer .env may define the key; these tests are about the case where the build has none.
beforeEach(() => { vi.stubEnv("VITE_TURNSTILE_SITE_KEY", ""); });
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.resetModules(); });

describe("Turnstile site key", () => {
  it("comes from the server when it was not baked into the build", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ turnstile_site_key: "0x4AAAA-test" }), { status: 200 })));
    const auth = await import("./auth");
    expect(auth.turnstileSiteKey).toBe("");
    await auth.loadRuntimeTurnstileKey();
    expect(auth.turnstileSiteKey).toBe("0x4AAAA-test");
  });

  it("stays empty (no widget) when the server has none or is unreachable", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    const auth = await import("./auth");
    await auth.loadRuntimeTurnstileKey();
    expect(auth.turnstileSiteKey).toBe("");
  });
});
