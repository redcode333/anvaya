// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CaptchaStatusLine, type CaptchaStatus } from "./Turnstile";

afterEach(cleanup);

describe("the security check is always visible", () => {
  it.each<[CaptchaStatus, string]>([
    ["off", "not enabled in this build"],
    ["checking", "Security check in progress"],
    ["challenge", "Please complete the security check above"],
    ["passed", "Security check passed"],
    ["failed", "could not finish"],
  ])("says what state it is in: %s", (status, text) => {
    render(<CaptchaStatusLine status={status} lang="en" />);
    expect(screen.getByTestId("captcha-status").textContent).toContain(text);
  });

  it("offers a retry only when it failed, and the retry runs", () => {
    const retry = vi.fn();
    const { rerender } = render(<CaptchaStatusLine status="passed" lang="en" onRetry={retry} />);
    expect(screen.queryByRole("button")).toBeNull();
    rerender(<CaptchaStatusLine status="failed" lang="en" onRetry={retry} />);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledTimes(1);
  });

  it("speaks Hindi and Telugu, and falls back to English", () => {
    const { rerender } = render(<CaptchaStatusLine status="passed" lang="hi" />);
    expect(screen.getByTestId("captcha-status").textContent).toMatch(/[ऀ-ॿ]/);
    rerender(<CaptchaStatusLine status="passed" lang="te" />);
    expect(screen.getByTestId("captcha-status").textContent).toMatch(/[ఀ-౿]/);
    rerender(<CaptchaStatusLine status="passed" lang="fr" />);
    expect(screen.getByTestId("captcha-status").textContent).toContain("Security check passed");
  });
});
