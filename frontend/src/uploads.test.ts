import { describe, expect, it, vi } from "vitest";
import { fileProblem, MAX_UPLOAD_BYTES, UPLOAD_CONSENT_VERSION, uploadDocument, viewLink } from "./uploads";

const file = (type: string, size: number) => ({ type, size, name: "f" }) as unknown as File;

describe("document uploads", () => {
  it("accepts only JPEG, PNG and PDF up to 5 MB", () => {
    expect(fileProblem(file("image/png", 10))).toBeNull();
    expect(fileProblem(file("application/pdf", MAX_UPLOAD_BYTES))).toBeNull();
    expect(fileProblem(file("image/gif", 10))).toBe("type");
    expect(fileProblem(file("image/jpeg", MAX_UPLOAD_BYTES + 1))).toBe("size");
    expect(fileProblem(file("image/jpeg", 0))).toBe("size");
  });

  it("asks the server for a link with consent, then sends the file through it with progress", async () => {
    const api = vi.fn().mockResolvedValue({ upload_url: "/api/v1/uploads/tok", content_type: "image/png" });
    const put = vi.fn().mockImplementation(async (_u, _f, _t, onProgress) => { onProgress(50); onProgress(100); return { status: "uploaded", verified: false }; });
    const progress: number[] = [];
    const f = file("image/png", 1234);
    const res = await uploadDocument("SES_1", "bpl_card", f, (p) => progress.push(p), api as any, put);
    expect(api).toHaveBeenCalledWith("/sessions/SES_1/documents/bpl_card/upload-url", {
      body: { content_type: "image/png", size: 1234, consent: { version: UPLOAD_CONSENT_VERSION, accepted: true } },
    });
    expect(put.mock.calls[0].slice(0, 3)).toEqual(["/api/v1/uploads/tok", f, "image/png"]);
    expect(progress).toEqual([0, 50, 100]);
    expect(res).toEqual({ status: "uploaded", verified: false });
  });

  it("refuses a wrong file before contacting the server", async () => {
    const api = vi.fn();
    await expect(uploadDocument("SES_1", "aadhaar", file("image/heic", 10), () => undefined, api as any, vi.fn()))
      .rejects.toMatchObject({ code: "UNSUPPORTED_TYPE" });
    await expect(uploadDocument("SES_1", "aadhaar", file("image/png", MAX_UPLOAD_BYTES + 1), () => undefined, api as any, vi.fn()))
      .rejects.toMatchObject({ code: "FILE_TOO_LARGE" });
    expect(api).not.toHaveBeenCalled();
  });

  it("gets a view link from the server (never from Storage)", async () => {
    const api = vi.fn().mockResolvedValue({ view_url: "/api/v1/uploads/view/t" });
    await viewLink("SES_1", "photo", api as any);
    expect(api).toHaveBeenCalledWith("/sessions/SES_1/documents/photo/view-url");
  });
});
