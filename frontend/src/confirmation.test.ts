import { describe, expect, it } from "vitest";
import type { Fact } from "./api";
import { splitPending } from "./confirmation";

const fact = (attribute: string, over: Partial<Fact> = {}): Fact => ({
  fact_id: `F-${attribute}`, attribute, value: 1, source: "voice", confidence: 0.9, confirmed: false, inferred: false,
  high_impact: ["age", "annual_income", "state", "area", "household_size"].includes(attribute), ...over,
});

describe("confirm-all covers only low-impact facts", () => {
  it("keeps age, income, state and area for one-by-one confirmation", () => {
    const facts = ["age", "annual_income", "state", "area", "bpl", "gender"].map((a) => fact(a, { confirm_individually: undefined }));
    const { individual, bulk } = splitPending(facts);
    expect(individual.map((f) => f.attribute)).toEqual(["age", "annual_income", "state", "area"]);
    expect(bulk.map((f) => f.attribute)).toEqual(["bpl", "gender"]);
  });

  it("uses the server's confirm_individually flag and skips confirmed facts", () => {
    const facts = [fact("bpl", { confirm_individually: true, confusable: true }), fact("age", { confirmed: true }), fact("gender")];
    const { individual, bulk } = splitPending(facts);
    expect(individual.map((f) => f.attribute)).toEqual(["bpl"]);
    expect(bulk.map((f) => f.attribute)).toEqual(["gender"]);
  });
});
