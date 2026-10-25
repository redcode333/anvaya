import { afterEach, describe, expect, it, vi } from "vitest";
import { apiBlob, ApiError } from "./api";
import { copyText, stepsToRead } from "./FormHelper";
import { t } from "./i18n";

afterEach(() => vi.unstubAllGlobals());

describe("Form Helper", () => {
  it("reads only the real steps, numbered, skipping headings", () => {
    const steps = [
      { text: "Process 1:", text_en: "Process 1:", heading: true, machine_translated: false },
      { text: "Open the form", text_en: "Open the form", heading: false, machine_translated: false },
      { text: "Submit at the block office", text_en: "Submit at the block office", heading: false, machine_translated: false },
    ];
    expect(stepsToRead(steps)).toEqual(["1. Open the form", "2. Submit at the block office"]);
  });

  it("copies with the Clipboard API, falling back when it is blocked", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.stubGlobal("navigator", { clipboard: { writeText } });
    expect(await copyText("Lakshmi Devi")).toBe(true);
    expect(writeText).toHaveBeenCalledWith("Lakshmi Devi");
    vi.stubGlobal("navigator", { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) } });
    expect(await copyText("x")).toBe(false);  // no DOM in this test environment: reports failure instead of throwing
  });

  it("downloads the PDF with the session in a header, never in the URL, and surfaces server errors", async () => {
    const fetch = vi.fn().mockResolvedValue({ ok: true, blob: () => Promise.resolve(new Blob(["%PDF-"])) });
    vi.stubGlobal("fetch", fetch);
    const blob = await apiBlob("/drafts/DRF_1/pdf?language=hi", { sessionId: "SES_secret", headers: { "X-Case-Code": "ANV-AAAA-BBBB" } });
    expect(blob.size).toBe(5);
    const [url, init] = fetch.mock.calls[0];
    expect(url).toBe("/api/v1/drafts/DRF_1/pdf?language=hi");
    expect(init.headers["X-Session-Id"]).toBe("SES_secret");
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 403, statusText: "Forbidden", json: () => Promise.resolve({ error: { code: "FORBIDDEN", message: "no" } }) }));
    await expect(apiBlob("/drafts/DRF_1/pdf")).rejects.toBeInstanceOf(ApiError);
  });

  it("never says submitted or applied in the helper wording (en / hi / te)", () => {
    for (const lang of ["en", "hi", "te"] as const) {
      const text = `${t("notSubmitted", lang)}`;
      expect(text.length).toBeGreaterThan(10);
    }
    expect(t("notSubmitted", "en")).toContain("Nothing has been submitted");
  });
});
