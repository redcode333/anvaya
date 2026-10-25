// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";
import { resetConfigCache, type FeatureStatus } from "../featureConfig";
import { AppProvider } from "../state";
import DigiLockerCallback, { stateForError } from "./DigiLockerCallback";
import { VerifiedFactsView } from "./Profile";
import SignIn from "./SignIn";

let fetchMock: ReturnType<typeof vi.fn>;
function serveConfig(dl: FeatureStatus, phone: FeatureStatus, opts: { pending?: boolean } = {}) {
  fetchMock = vi.fn((url: string) => {
    if (url === "/api/config") {
      if (opts.pending) return new Promise(() => {});
      return Promise.resolve(new Response(JSON.stringify({ digilocker_status: dl, phone_otp_status: phone, turnstile_site_key: null }), { status: 200 }));
    }
    return Promise.resolve(new Response(JSON.stringify({ error: { code: "UNEXPECTED" } }), { status: 500 }));
  });
  vi.stubGlobal("fetch", fetchMock);
}
const renderAt = (ui: React.ReactNode, mode?: "kiosk") => {
  if (mode) sessionStorage.setItem("anvaya.mode", mode);
  return render(<MemoryRouter><AppProvider>{ui}</AppProvider></MemoryRouter>);
};
// Requests to the sign-in options themselves (the app also reads its own public settings from /auth/config).
const nonConfigCalls = () => fetchMock.mock.calls.filter(([u]) => /\/auth\/(digilocker|phone)/.test(String(u)));

beforeEach(() => { sessionStorage.clear(); sessionStorage.setItem("anvaya.lang", "en"); resetConfigCache(); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

describe("SignIn", () => {
  it("coming_soon: options are visible, disabled, badged, and clicking fires no request", async () => {
    serveConfig("coming_soon", "coming_soon");
    renderAt(<SignIn />);
    const dl = await screen.findByRole("button", { name: /Meri Pehchaan/ });
    const ph = screen.getByRole("button", { name: /phone OTP/ });
    for (const b of [dl, ph]) {
      expect(b.getAttribute("aria-disabled")).toBe("true");
      expect(b.textContent).toContain("Coming soon");
    }
    expect(screen.getByText("Verified sign-in with DigiLocker is being integrated.")).toBeTruthy();
    fireEvent.click(dl); fireEvent.click(ph);
    await act(async () => { await Promise.resolve(); });
    expect(nonConfigCalls()).toHaveLength(0);
    expect(screen.queryByRole("link", { name: /Meri Pehchaan/ })).toBeNull();
  });

  it("off: the option is not in the DOM", async () => {
    serveConfig("off", "coming_soon");
    renderAt(<SignIn />);
    await screen.findByRole("button", { name: /phone OTP/ });
    expect(screen.queryByText(/Meri Pehchaan/)).toBeNull();
    expect(screen.queryByTestId("opt-digilocker")).toBeNull();
  });

  it("on: DigiLocker is an enabled button (the OIDC start needs the citizen's own session) and fires nothing until clicked", async () => {
    serveConfig("on", "off");
    renderAt(<SignIn />);
    const btn = await screen.findByRole("button", { name: /Meri Pehchaan/ });
    expect(btn.getAttribute("aria-disabled")).toBeNull();
    expect(nonConfigCalls()).toHaveLength(0);
    expect(screen.queryByText(/phone OTP/)).toBeNull();
  });

  it("on: phone OTP opens the number form", async () => {
    serveConfig("off", "on");
    renderAt(<SignIn />);
    fireEvent.click(await screen.findByRole("button", { name: /phone OTP/ }));
    expect(screen.getByLabelText("Mobile number")).toBeTruthy();
  });

  it("shows skeletons while the config loads", () => {
    serveConfig("on", "on", { pending: true });
    renderAt(<SignIn />);
    expect(screen.getByTestId("signin-skeleton")).toBeTruthy();
    expect(screen.queryByText(/Meri Pehchaan/)).toBeNull();
  });

  it.each(["on", "coming_soon"] as FeatureStatus[])("kiosk hides DigiLocker and phone whatever the status (%s)", async (status) => {
    serveConfig(status, status);
    renderAt(<SignIn />, "kiosk");
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await act(async () => { await Promise.resolve(); });
    expect(screen.queryByText(/Meri Pehchaan/)).toBeNull();
    expect(screen.queryByText(/phone OTP/)).toBeNull();
    expect(screen.getByTestId("kiosk-note")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Continue without account" })).toBeTruthy();
  });
});

describe("DigiLocker callback", () => {
  const visit = (qs: string) => { window.history.replaceState(null, "", `/auth/digilocker/callback${qs}`); return renderAt(<DigiLockerCallback />); };

  it("user cancelled", async () => {
    serveConfig("on", "off");
    visit("?error=access_denied");
    expect(await screen.findByText("You cancelled DigiLocker sign-in")).toBeTruthy();
    expect(window.location.search).toBe("");
  });

  it("missing state or code → expired/invalid link", async () => {
    serveConfig("on", "off");
    visit("?code=abc");
    expect(await screen.findByText("This sign-in link has expired")).toBeTruthy();
  });

  it("strips code and state from the URL and shows provider-unavailable when the backend refuses", async () => {
    serveConfig("on", "off");
    visit("?code=abc&state=xyz");
    expect(window.location.search).toBe("");
    expect(await screen.findByText("DigiLocker isn’t responding right now")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Try again" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Continue another way" })).toBeTruthy();
  });

  it("maps backend errors to screens", () => {
    expect(stateForError(new ApiError("ALREADY_LINKED", "x", 409))).toBe("conflict");
    expect(stateForError(new ApiError("INVALID_STATE", "x", 400))).toBe("invalid");
    expect(stateForError(new ApiError("FEATURE_NOT_AVAILABLE", "x", 503))).toBe("unavailable");
    expect(stateForError(new ApiError("NETWORK", "x", 0))).toBe("unavailable");
  });
});

describe("Profile", () => {
  it("DigiLocker-verified facts are read-only: no inputs, no Aadhaar", () => {
    serveConfig("on", "off");
    renderAt(<VerifiedFactsView facts={{ name: "Ramesh Kumar", dob: "12/03/1968", gender: "Male" }} />);
    expect(screen.getAllByTestId("verified-fact")).toHaveLength(3);
    expect(screen.getByText("Ramesh Kumar")).toBeTruthy();
    expect(document.querySelectorAll("input, textarea, select, [contenteditable]")).toHaveLength(0);
    expect(document.body.textContent).not.toMatch(/aadhaar/i);
  });
});
