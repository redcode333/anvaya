// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const app: { staff: unknown } = { staff: null };
vi.mock("../state", () => ({ useApp: () => ({ staff: app.staff, lang: "en", staffPendingMfa: null, signOut: vi.fn(), signOutAll: vi.fn(), refreshAuth: vi.fn() }) }));
vi.mock("../auth", () => ({ supabase: {}, turnstileSiteKey: "" }));

import Staff from "./Staff";

afterEach(cleanup);
const show = () => render(<MemoryRouter><Staff /></MemoryRouter>);

describe("/staff", () => {
  beforeEach(() => { app.staff = null; });

  it("signed out: shows the staff sign-in, not any tool", () => {
    show();
    expect(screen.getByRole("heading", { name: "Staff sign-in" })).toBeTruthy();
    expect(screen.queryByText("Security")).toBeNull();
  });

  it.each([
    ["operator", ["Kiosk"], ["Reviewer", "Security", "TC1–TC5"]],
    ["reviewer", ["Reviewer", "Catalogue"], ["Security", "TC1–TC5", "Kiosk"]],
    ["admin", ["Reviewer", "Catalogue", "Security", "TC1–TC5", "Kiosk"], []],
  ])("%s sees only their tools", (role, yes, no) => {
    app.staff = { user_id: "u", username: "x", role, display_name: "X" };
    show();
    yes.forEach((n) => expect(screen.getByRole("heading", { name: n })).toBeTruthy());
    no.forEach((n) => expect(screen.queryByRole("heading", { name: n })).toBeNull());
  });
});
