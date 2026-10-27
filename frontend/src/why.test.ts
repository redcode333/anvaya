import { describe, expect, it } from "vitest";
import { showValue as showValueReal } from "./i18n";
import { statusLabel, sourceLabel } from "./statusLabels";
import { humanExpected, reasonText, reasonTone, REASON_CODES, WHY_KEYS, whyText } from "./why";

const show = (fact: string, v: any) => (typeof v === "number" ? (fact === "age" ? `${v} years` : String(v)) : String(v));
const LANGS = ["en", "hi", "te"] as const;

describe("plain wording for the Why panel", () => {
  it("has every string in English, Hindi and Telugu", () => {
    for (const l of LANGS) {
      for (const k of WHY_KEYS) expect(whyText(k, l).trim(), `${k}/${l}`).not.toBe("");
      for (const c of REASON_CODES) expect(reasonText(c, "", l).trim(), `${c}/${l}`).not.toBe("");
    }
    expect(whyText("met", "hi")).toMatch(/[ऀ-ॿ]/);
    expect(whyText("met", "te")).toMatch(/[ఀ-౿]/);
  });

  it("never shows a reason code; an unknown code shows the server's sentence", () => {
    expect(reasonText("CRITERIA_PASSED", "x", "en")).toBe("You meet every condition we can check.");
    expect(reasonText("SOMETHING_NEW", "Server says this.", "en")).toBe("Server says this.");
    expect(reasonTone("CRITERIA_PASSED")).toBe("ok");
    expect(reasonTone("EVIDENCE_NOT_VERIFIED")).toBe("warn");
  });

  it("turns rule operators into sentences", () => {
    expect(humanExpected(">= 60", "age", "en", show)).toBe("at least 60 years");
    expect(humanExpected("<= 300,000", "annual_income", "en", show)).toBe("at most 300000");
    expect(humanExpected("> 18", "age", "en", show)).toBe("more than 18 years");
    expect(humanExpected("< 5", "household_size", "en", show)).toBe("less than 5");
    expect(humanExpected("18–60", "age", "en", show)).toBe("between 18 years and 60 years");
    expect(humanExpected("yes", "bpl", "en", show)).toBe("yes");
    expect(humanExpected("no", "bpl", "hi", show)).toBe("नहीं");
    expect(humanExpected("rural / urban", "area", "en", show)).toBe("rural or urban");
    expect(humanExpected("== rural", "area", "en", show)).toBe("rural");
    expect(humanExpected("!= widowed", "marital_status", "en", show)).toBe("not widowed");
    expect(humanExpected(">= 60", "age", "te", show)).toBe("కనీసం 60 years");
  });

  it("shows the fixed choices in the site language, and anything unknown as readable text", () => {
    expect(showValueReal("area", "rural", "hi")).toBe("ग्रामीण");
    expect(showValueReal("area", "urban", "te")).toBe("పట్టణ");
    expect(showValueReal("gender", "female", "en")).toBe("Female");
    expect(showValueReal("marital_status", "widowed", "hi")).toBe("विधवा");
    expect(showValueReal("occupation", "self_employed", "en")).toBe("Self-employed");
    expect(showValueReal("occupation", "something_new", "en")).toBe("something new");
    expect(showValueReal("bpl", true, "hi")).toBe("हाँ");
    expect(showValueReal("annual_income", 60000, "en")).toBe("₹60,000");
    expect(showValueReal("district", "Guntur", "hi")).toBe("Guntur");
  });

  it("names statuses and sources in words", () => {
    expect(statusLabel("DRAFT_SAVED", "en")).toBe("Draft saved");
    expect(statusLabel("PENDING_REVIEW", "hi")).toBe("समीक्षक के पास");
    expect(statusLabel("SOME_NEW_STATE", "en")).toBe("Some new state");
    expect(statusLabel(null, "en")).toBe("");
    expect(sourceLabel("citizen_entered", "en")).toBe("You entered");
    expect(sourceLabel("missing", "te")).toBe("నింపాలి");
  });
});
