// Citizen accounts and staff sign-in, written against a small slice of the supabase-js auth client so the flows can
// be tested with a fake. Calls used (supabase-js v2): signInAnonymously, updateUser({ email }) + verifyOtp
// type "email_change" to link an email to an anonymous user (same user id), signInWithOtp + verifyOtp type "email"
// to come back on another device, linkIdentity / signInWithOAuth for Google, signInWithPassword for staff.
import { api as defaultApi, ApiError } from "./api";
import type { Lang } from "./i18n";

type Res<T = any> = Promise<{ data: T; error: { message: string; code?: string } | null }>;
export type AuthLike = {
  getSession(): Res<{ session: { access_token: string; user: { id: string; is_anonymous?: boolean; email?: string } } | null }>;
  signInAnonymously(): Res;
  updateUser(attrs: { email?: string }): Res;
  verifyOtp(params: { email: string; token: string; type: "email" | "email_change" }): Res;
  signInWithOtp(params: { email: string; options?: { shouldCreateUser?: boolean } }): Res;
  signInWithPassword(params: { email: string; password: string }): Res;
  signOut(options?: { scope?: "global" | "local" | "others" }): Promise<{ error: any }>;
  linkIdentity?(params: { provider: "google"; options?: { redirectTo?: string } }): Res;
  signInWithOAuth?(params: { provider: "google"; options?: { redirectTo?: string } }): Res;
};
export type ApiFn = typeof defaultApi;

export const CONSENT_VERSION = "save-2026-10";
const PENDING_CONSENT = "anvaya.pendingConsent";

function check<T>(r: { data: T; error: { message: string; code?: string } | null }): T {
  if (r.error) throw new ApiError(r.error.code || "AUTH_ERROR", r.error.message, 400);
  return r.data;
}

/** Personal mode: make sure there is a Supabase session, starting an anonymous one if needed. */
export async function ensureAnonymous(auth: AuthLike): Promise<string> {
  const { session } = check(await auth.getSession());
  if (session) return session.user.id;
  return check(await auth.signInAnonymously()).user.id;
}

export type EmailFlow = "link" | "signin";

/** Send a 6-digit code. An anonymous user links the email to the same account; anyone else signs in to an existing one. */
export async function sendEmailCode(auth: AuthLike, email: string): Promise<EmailFlow> {
  const { session } = check(await auth.getSession());
  if (session?.user.is_anonymous) {
    check(await auth.updateUser({ email }));
    return "link";
  }
  check(await auth.signInWithOtp({ email, options: { shouldCreateUser: false } }));
  return "signin";
}

export async function verifyEmailCode(auth: AuthLike, email: string, code: string, flow: EmailFlow): Promise<void> {
  if (!/^\d{6}$/.test(code.trim())) throw new ApiError("INVALID_CODE", "Enter the 6-digit code from the email.", 400);
  check(await auth.verifyOtp({ email, token: code.trim(), type: flow === "link" ? "email_change" : "email" }));
}

export const consentBody = (lang: Lang) => ({ consent: { version: CONSENT_VERSION, accepted: true, language: lang } });

/** Record consent on the server (needs a linked account). */
export async function saveWithConsent(lang: Lang, api: ApiFn = defaultApi) {
  return api("/account/consent", { body: consentBody(lang) });
}

/** Google: remember the consent across the redirect, then link (anonymous) or sign in. */
export async function startGoogle(auth: AuthLike, lang: Lang, redirectTo: string) {
  try { sessionStorage.setItem(PENDING_CONSENT, lang); } catch { /* storage blocked */ }
  const { session } = check(await auth.getSession());
  if (session?.user.is_anonymous && auth.linkIdentity) return check(await auth.linkIdentity({ provider: "google", options: { redirectTo } }));
  if (auth.signInWithOAuth) return check(await auth.signInWithOAuth({ provider: "google", options: { redirectTo } }));
}

/** After a Google redirect: post the consent the citizen gave before leaving. */
export async function finishPendingConsent(auth: AuthLike, api: ApiFn = defaultApi): Promise<boolean> {
  let lang: string | null = null;
  try { lang = sessionStorage.getItem(PENDING_CONSENT); } catch { /* */ }
  if (!lang) return false;
  const { session } = check(await auth.getSession());
  if (!session || session.user.is_anonymous) return false;
  await saveWithConsent(lang as Lang, api);
  try { sessionStorage.removeItem(PENDING_CONSENT); } catch { /* */ }
  return true;
}

export type StaffUser = { user_id: string; username: string; role: string; display_name: string };

/** Staff sign in with Supabase email + password; the role is whatever the server reads from app_metadata. */
export async function staffSignIn(auth: AuthLike, email: string, password: string, roles: string[], api: ApiFn = defaultApi): Promise<StaffUser> {
  check(await auth.signInWithPassword({ email, password }));
  let user: StaffUser | undefined;
  try { user = (await api<{ user?: StaffUser }>("/auth/me")).user; } catch { user = undefined; }
  if (!user || !roles.includes(user.role)) {
    await auth.signOut({ scope: "local" });
    throw new ApiError("FORBIDDEN", `This page needs a ${roles.join(" or ")} account.`, 403);
  }
  return user;
}

export type PassportVersion = {
  version_id: string; created_at: string; session_id: string; eval_id: string; bundle_version: string;
  rule_versions: Record<string, number>; fact_ids: string[]; counts: Record<string, number>;
  outcomes: { scheme_id: string; scheme_name: string; rule_id: string; rule_version: number; outcome: string }[];
};
export type Reason =
  | { kind: "fact_changed"; attribute: string; before: any; after: any; fact_before?: string | null; fact_after?: string | null }
  | { kind: "rule_changed"; rule_id: string; before: number; after: number }
  | { kind: "document_changed"; doc_key: string; before: string | null; after: string | null };
export type Change = { scheme_id: string; scheme_name: string; rule_id: string; before: string | null; after: string | null; reasons: Reason[] };

/** History and "what changed" for the signed-in account, or for a session resumed with a Passport code. */
export const historyPath = (sessionId?: string | null) => (sessionId ? `/sessions/${sessionId}/passports` : "/account/passports");
export async function loadHistory(sessionId?: string | null, api: ApiFn = defaultApi) {
  return api<{ versions: PassportVersion[] }>(historyPath(sessionId));
}
export async function whatChanged(since: string, sessionId?: string | null, api: ApiFn = defaultApi) {
  return api<{ before: { created_at: string } | null; after: { created_at: string } | null; changes: Change[] }>(
    `${historyPath(sessionId)}/changes?since=${encodeURIComponent(since)}`);
}

/** Delete the account on the server (data + Supabase Auth user), then forget the local session. */
export async function deleteAccount(auth: AuthLike, api: ApiFn = defaultApi) {
  const res = await api("/account", { method: "DELETE" });
  await auth.signOut({ scope: "local" });
  try { Object.keys(sessionStorage).filter((k) => k.startsWith("anvaya.")).forEach((k) => sessionStorage.removeItem(k)); } catch { /* */ }
  return res;
}

/** Mirrors the server's PIN rules for instant feedback (the server decides). */
export function pinProblem(pin: string): "format" | "weak" | null {
  if (!/^\d{4}$/.test(pin)) return "format";
  const d = pin.split("").map(Number);
  const steps = new Set([d[1] - d[0], d[2] - d[1], d[3] - d[2]]);
  const seq = steps.size === 1 && (steps.has(1) || steps.has(-1));
  const year = Number(pin) >= 1900 && Number(pin) <= 2029;
  const weak = new Set(d).size === 1 || seq || (d[0] === d[2] && d[1] === d[3]) || (d[0] === d[1] && d[2] === d[3])
    || ["1004", "2580", "0852", "6969", "1010", "0007", "1230"].includes(pin) || year;
  return weak ? "weak" : null;
}

export const formatCode = (raw: string) => {
  const c = raw.toUpperCase().replace(/[^0-9A-Z]/g, "").replace(/^PSP/, "");
  return c.length ? `PSP-${c.slice(0, 4)}${c.length > 4 ? `-${c.slice(4, 8)}` : ""}` : "";
};
