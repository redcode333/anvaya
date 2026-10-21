// Mirror of backend/anvaya/rules_engine.py for offline kiosk pre-screening.
// Kept aligned by running backend/tests/fixtures/engine_cases.json in both test suites.

export type Fact = { fact_id: string; value: any; confirmed: boolean };
export type Rule = {
  rule_id: string; scheme_id: string; version: number; jurisdiction: { level: string; state?: string };
  all: { id: string; fact: string; op: string; value?: any; quote: string | null; note?: string }[];
  manual_checks?: { id: string; text: string; quote: string | null }[];
  evidence_requirements?: string[]; review_status?: string; review_note?: string; freshness_days?: number;
};
export type Meta = { review_status: string; source_verified_at: string | null; scheme_name?: string; source_url?: string; bundle_version?: string };

const norm = (v: any) => (typeof v === "string" ? v.trim().toLowerCase() : v);

export function compare(op: string, observed: any, expected: any): boolean {
  switch (op) {
    case "is_true": return observed === true;
    case "is_false": return observed === false;
    case "==": return norm(observed) === norm(expected);
    case "!=": return norm(observed) !== norm(expected);
    case "in": return (expected as any[]).map(norm).includes(norm(observed));
  }
  const n = Number(observed);
  if (Number.isNaN(n)) throw new Error("not a number");
  switch (op) {
    case "between": return Number(expected[0]) <= n && n <= Number(expected[1]);
    case ">=": return n >= expected;
    case "<=": return n <= expected;
    case ">": return n > expected;
    case "<": return n < expected;
  }
  throw new Error(`unsupported operator ${op}`);
}

export function evaluate(rule: Rule, facts: Record<string, Fact>, docs: Record<string, string>, meta: Meta, at = new Date()) {
  const criteria = rule.all.map((c) => {
    const f = facts[c.fact];
    const base = { criterion_id: c.id, fact: c.fact, operator: c.op, expected: c.value, quote: c.quote, fact_id: f?.fact_id ?? null, observed: f?.value ?? null };
    if (!f || !f.confirmed) return { ...base, outcome: "UNKNOWN" as const };
    try {
      return { ...base, outcome: compare(c.op, f.value, c.value) ? ("PASS" as const) : ("FAIL" as const) };
    } catch {
      return { ...base, outcome: "UNKNOWN" as const };
    }
  });
  const evidence = (rule.evidence_requirements || []).map((d) => ({ doc_key: d, status: docs[d] || "unknown", satisfied: docs[d] === "verified" }));
  let stale = true;
  if (meta.source_verified_at) {
    const age = at.getTime() - new Date(meta.source_verified_at).getTime();
    stale = rule.freshness_days != null && age > rule.freshness_days * 86400000;
  }
  let outcome: string;
  const reasons: string[] = [];
  if (criteria.some((c) => c.outcome === "FAIL")) { outcome = "MISMATCH"; reasons.push("CRITERION_FAILED"); }
  else if (criteria.some((c) => c.outcome === "UNKNOWN")) { outcome = "INSUFFICIENT_INFORMATION"; reasons.push("FACT_UNKNOWN"); }
  else if (meta.review_status !== "team_reviewed") { outcome = "NEEDS_HUMAN_REVIEW"; reasons.push("RULE_NEEDS_REVIEW"); }
  else {
    if (evidence.some((e) => !e.satisfied)) reasons.push("EVIDENCE_NOT_VERIFIED");
    if (rule.manual_checks?.length) reasons.push("MANUAL_CHECKS_PENDING");
    if (!meta.source_verified_at) reasons.push("SOURCE_NOT_VERIFIED");
    else if (stale) reasons.push("SOURCE_STALE");
    outcome = reasons.length ? "PROVISIONAL" : "MATCH";
  }
  return {
    scheme_id: rule.scheme_id, scheme_name: meta.scheme_name, rule_id: rule.rule_id, rule_version: rule.version,
    outcome, reasons, criteria, evidence, missing_facts: [...new Set(criteria.filter((c) => c.outcome === "UNKNOWN").map((c) => c.fact))],
    document_gaps: evidence.filter((e) => ["missing", "expired", "unknown"].includes(e.status)).map((e) => e.doc_key),
    source_url: meta.source_url, bundle_version: meta.bundle_version,
  };
}

export type LocalResult = ReturnType<typeof evaluate>;
const ORDER: Record<string, number> = { MATCH: 0, PROVISIONAL: 1, INSUFFICIENT_INFORMATION: 2, NEEDS_HUMAN_REVIEW: 3, MISMATCH: 4 };
export const sortResults = (r: LocalResult[]) => [...r].sort((a, b) => ORDER[a.outcome] - ORDER[b.outcome] || String(a.scheme_name).localeCompare(String(b.scheme_name)));
