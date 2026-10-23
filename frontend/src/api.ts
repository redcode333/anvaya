export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number, public details: any = {}, public requestId?: string) {
    super(message);
  }
}

let staffToken: string | null = sessionStorage.getItem("anvaya.staffToken");
export const setStaffToken = (t: string | null) => {
  staffToken = t;
  try { t ? sessionStorage.setItem("anvaya.staffToken", t) : sessionStorage.removeItem("anvaya.staffToken"); } catch { /* storage blocked */ }
};
export const getStaffToken = () => staffToken;

export const newKey = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);

type Opts = { method?: string; body?: any; headers?: Record<string, string>; sessionId?: string; auth?: boolean };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers || {}) };
  let body: BodyInit | undefined;
  if (opts.body instanceof FormData) body = opts.body;
  else if (opts.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.body); }
  if (opts.sessionId) headers["X-Session-Id"] = opts.sessionId;
  if (staffToken && opts.auth !== false) headers["Authorization"] = `Bearer ${staffToken}`;
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, { method: opts.method || (body ? "POST" : "GET"), headers, body });
  } catch {
    throw new ApiError("NETWORK", "Cannot reach the Anvaya server. Check the connection; nothing was saved on the server.", 0);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = data.error || {};
    throw new ApiError(e.code || `HTTP_${res.status}`, e.message || res.statusText, res.status, e.details, e.request_id);
  }
  return data as T;
}

// ---- shared types (mirror backend payloads)
export type Fact = {
  fact_id: string; attribute: string; value: any; raw_text?: string; source: string; confidence: number;
  confirmed: boolean; inferred: boolean; note?: string; high_impact: boolean; superseded_by?: string | null;
  // High-impact facts and confusable spoken numbers: read back in digits and confirmed one by one, never in bulk.
  confusable?: boolean; confirm_individually?: boolean; readback?: string;
};

export type Criterion = {
  criterion_id: string; fact: string; operator: string; expected: any; expected_text: string; observed: any;
  outcome: "PASS" | "FAIL" | "UNKNOWN"; fact_id: string | null; quote: string | null; note?: string; explanation: string;
};
export type Evidence = { doc_key: string; status: string; satisfied: boolean; label?: string; purpose?: string; status_label?: string };
export type Outcome = "MATCH" | "PROVISIONAL" | "MISMATCH" | "INSUFFICIENT_INFORMATION" | "NEEDS_HUMAN_REVIEW";
export type SchemeResult = {
  scheme_id: string; scheme_name: string; rule_id: string; rule_version: number; bundle_version: string;
  jurisdiction: { level: string; state?: string }; outcome: Outcome; outcome_label?: string;
  decision_reason: { code: string; text: string; criterion_id?: string; docs?: string[] }[];
  criteria: Criterion[]; manual_checks: { id: string; text: string; quote: string | null }[];
  evidence: Evidence[]; evidence_note?: string; document_gaps: string[]; missing_facts: string[];
  missing_questions?: { attribute: string; text: string }[]; input_fact_ids: string[];
  source: { source_id: string; source_url: string; imported_at: string; rule_reviewed_at: string; source_verified_at: string | null; review_status: string; stale_or_unverified: boolean };
  evaluated_at: string;
};
export type Evaluation = {
  eval_id: string; bundle_version: string; results: SchemeResult[]; input_fact_ids?: string[];
  jurisdiction?: { state: string | null; note: string | null }; changes_since_last?: { scheme_id: string; scheme_name: string; before: string | null; after: string | null }[];
  provisional_notice?: string; voice_summary?: string; origin?: string;
};
export type Draft = {
  draft_id: string; session_id: string; scheme_id: string; scheme_name: string; version: number; status: string; origin: string;
  fields: { key: string; label: string; value: any; provenance: string; fact_id: string | null }[];
  documents: { doc_key: string; status: string }[];
  eligibility_snapshot: { outcome: Outcome; rule_id: string; rule_version: number; bundle_version: string; eval_id: string };
  case: { case_id: string; status: string; review_outcome: string | null; updated_at: string } | null; notice: string; updated_at: string;
};
