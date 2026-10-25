export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number, public details: any = {}, public requestId?: string) {
    super(message);
  }
}

// The Supabase access token (anonymous citizen, linked citizen or staff), sent on every request; the server verifies it.
let tokenProvider: () => Promise<string | null> = async () => null;
export const setTokenProvider = (fn: () => Promise<string | null>) => { tokenProvider = fn; };

export const newKey = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);

// The kiosk device id (sent as X-Kiosk-Device in kiosk mode; kiosk sessions are bound to it). Set by state.tsx.
let kioskDevice: () => string | null = () => null;
export const setKioskDeviceProvider = (fn: () => string | null) => { kioskDevice = fn; };
// Called when the server says this sign-in was revoked (signed out of all devices): forget it locally.
let onRevoked: () => void = () => undefined;
export const setRevokedHandler = (fn: () => void) => { onRevoked = fn; };

/** Session ids never go in a URL: /sessions/<id>/... is sent as /sessions/current/... with the id in X-Session-Id. */
export function sessionInHeader(path: string, headers: Record<string, string>): string {
  const m = /^\/sessions\/([^/?#]+)(.*)$/.exec(path);
  if (!m || m[1] === "current") return path;
  headers["X-Session-Id"] = decodeURIComponent(m[1]);
  return `/sessions/current${m[2]}`;
}

type Opts = { method?: string; body?: any; headers?: Record<string, string>; sessionId?: string; auth?: boolean; signal?: AbortSignal };

export async function api<T = any>(path: string, opts: Opts = {}): Promise<T> {
  const headers: Record<string, string> = { ...(opts.headers || {}) };
  let body: BodyInit | undefined;
  if (opts.body instanceof FormData) body = opts.body;
  else if (opts.body !== undefined) { headers["Content-Type"] = "application/json"; body = JSON.stringify(opts.body); }
  if (opts.sessionId) headers["X-Session-Id"] = opts.sessionId;
  path = sessionInHeader(path, headers);
  const device = kioskDevice();
  if (device) headers["X-Kiosk-Device"] = device;
  if (opts.auth !== false) {
    const token = await tokenProvider().catch(() => null);
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }
  let res: Response;
  try {
    res = await fetch(`/api/v1${path}`, { method: opts.method || (body ? "POST" : "GET"), headers, body, signal: opts.signal });
  } catch (e) {
    if (opts.signal?.aborted) throw new ApiError("ABORTED", "Request cancelled.", 0);
    throw new ApiError("NETWORK", "Cannot reach the Anvaya server. Check the connection; nothing was saved on the server.", 0);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const e = data.error || {};
    if (e.code === "SESSION_REVOKED") onRevoked();
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
  // Deterministic and LLM extraction heard different values: the citizen picks one (plain confirm is refused).
  alternatives?: any[] | null; disputed?: boolean;
  // Read from DigiLocker (official record), not from what was said or typed.
  verified?: boolean;
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
  // VerbX machine translation of the scheme name (hi/te only; null when unavailable).
  scheme_name_localized?: string | null; scheme_name_machine_translated?: boolean;
};
export type Evaluation = {
  eval_id: string; bundle_version: string; results: SchemeResult[]; input_fact_ids?: string[];
  jurisdiction?: { state: string | null; note: string | null }; changes_since_last?: { scheme_id: string; scheme_name: string; before: string | null; after: string | null }[];
  provisional_notice?: string; voice_summary?: string; voice_summary_segments?: string[]; voice_summary_machine_translated?: boolean; origin?: string;
};
export type Draft = {
  draft_id: string; session_id: string; scheme_id: string; scheme_name: string; version: number; status: string; origin: string;
  fields: { key: string; label: string; value: any; provenance: string; fact_id: string | null }[];
  documents: { doc_key: string; status: string }[];
  eligibility_snapshot: { outcome: Outcome; rule_id: string; rule_version: number; bundle_version: string; eval_id: string };
  case: { case_id: string; status: string; review_outcome: string | null; updated_at: string } | null; notice: string; updated_at: string;
};
