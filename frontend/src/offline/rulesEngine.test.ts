import { describe, expect, it } from "vitest";
import cases from "../../../backend/tests/fixtures/engine_cases.json";
import bundle from "../../../backend/anvaya/data/golden_rules.json";
import { evaluate, type Rule } from "./rulesEngine";

const rules = Object.fromEntries((bundle.rules as Rule[]).map((r) => [r.rule_id, r]));
const meta = { review_status: "team_reviewed", source_verified_at: null };

describe("offline engine matches backend fixtures", () => {
  for (const c of cases as any[]) {
    it(c.name, () => {
      const facts = Object.fromEntries(Object.entries(c.facts).map(([k, v]) => [k, { fact_id: `F-${k}`, value: v, confirmed: true }]));
      expect(evaluate(rules[c.rule_id], facts, c.docs || {}, { ...meta, ...(c.meta || {}) }).outcome).toBe(c.expected);
    });
  }
});
