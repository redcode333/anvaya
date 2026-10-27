import { describe, expect, it } from "vitest";
import { codeKind, formatCaseCode, isCompleteCaseCode } from "./caseCode";

describe("case and passport codes", () => {
  it("tells a Passport code from a case code, whatever the typing", () => {
    expect(codeKind("PSP-E19B-ZWJD")).toBe("passport");
    expect(codeKind(" psp e19b zwjd ")).toBe("passport");
    expect(codeKind("ANV-4A8T-PH6Q")).toBe("case");
    expect(codeKind("4a8tph6q")).toBe("case");
    expect(codeKind("  ")).toBe("empty");
  });

  it("formats as you type", () => {
    expect(formatCaseCode("a")).toBe("A");
    expect(formatCaseCode("anv")).toBe("ANV");
    expect(formatCaseCode("anv4a8t")).toBe("ANV-4A8T");
    expect(formatCaseCode("4a8tph6q")).toBe("ANV-4A8T-PH6Q");
    expect(formatCaseCode("anv-4a8t-ph6q-extra")).toBe("ANV-4A8T-PH6Q");
    expect(formatCaseCode("psp e19b zwjd")).toBe("PSP-E19B-ZWJD");
  });

  it("knows when a case code is complete", () => {
    expect(isCompleteCaseCode("anv4a8tph6q")).toBe(true);
    expect(isCompleteCaseCode("ANV-4A8T")).toBe(false);
    expect(isCompleteCaseCode("PSP-E19B-ZWJD")).toBe(false);
  });
});
