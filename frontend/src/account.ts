// Citizen accounts and staff sign-in, written against a small slice of the supabase-js auth client so the flows can
// be tested with a fake. Calls used (supabase-js v2): signInAnonymously, updateUser({ email }) + verifyOtp
// type "email_change" to link an email to an anonymous user (same user id), signInWithOtp + verifyOtp type "email"
// to come back on another device, linkIdentity / signInWithOAuth for Google, signInWithPassword for staff.
import { api as defaultApi, ApiError } from "./api";
import type { Lang } from "./i18n";

type Res<T = any> = Promise<{ data: T; error: { message: string; code?: string } | null }>;
type Captcha = { captchaToken?: string };
export type Factor = { id: string; factor_type: string; status: "verified" | "unverified"; friendly_name?: string };
export type MfaLike = {
  listFactors(): Res<{ totp: Factor[]; all?: Factor[] }>;
  enroll(params: { factorType: "totp"; friendlyName?: string; issuer?: string }): Res<{ id: string; totp: { qr_code: string; secret: string; uri: string } }>;
  challengeAndVerify(params: { factorId: string; code: string }): Res;
  unenroll(params: { factorId: string }): Res;
  getAuthenticatorAssuranceLevel(): Res<{ currentLevel: string | null; nextLevel: string | null }>;
};
export type AuthLike = {
  getSession(): Res<{ session: { access_token: string; user: { id: string; is_anonymous?: boolean; email?: string } } | null }>;
  signInAnonymously(params?: { options?: Captcha }): Res;
  updateUser(attrs: { email?: string; password?: string }): Res;
  verifyOtp(params: { email?: string; phone?: string; token: string; type: "email" | "email_change" | "sms" }): Res;
  signInWithOtp(params: { email?: string; phone?: string; options?: { shouldCreateUser?: boolean } & Captcha }): Res;
  signInWithPassword(params: { email: string; password: string; options?: Captcha }): Res;
  signOut(options?: { scope?: "global" | "local" | "others" }): Promise<{ error: any }>;
  linkIdentity?(params: { provider: "google"; options?: { redirectTo?: string } }): Res;
  signInWithOAuth?(params: { provider: "google"; options?: { redirectTo?: string } }): Res;
  mfa?: MfaLike;
};
export type ApiFn = typeof defaultApi;

// Bumped with the backend's CONSENT_VERSION whenever the consent notice changes.
export const CONSENT_VERSION = "save-2026-10-dpdp";
const PENDING_CONSENT = "anvaya.pendingConsent";

function check<T>(r: { data: T; error: { message: string; code?: string } | null }): T {
  if (r.error) throw new ApiError(r.error.code || "AUTH_ERROR", r.error.message, 400);
  return r.data;
}

const captchaOpts = (captchaToken?: string | null) => (captchaToken ? { captchaToken } : {});

export type AuthEvent = "sign_in_success" | "sign_in_failure" | "otp_requested" | "mfa_enrolled" | "mfa_verified" | "mfa_failed";
/** Tell the server about a sign-in step that happened between the browser and Supabase (event + method only; never
 *  the email, code or token). Best effort: a failed report never blocks sign-in. */
export async function reportAuthEvent(event: AuthEvent, method: string, api: ApiFn = defaultApi) {
  await api("/auth/events", { body: { event, method } }).catch(() => undefined);
}

/** Personal mode: make sure there is a Supabase session, starting an anonymous one if needed (with the Turnstile
 *  token when the widget is on; Supabase checks it). */
export async function ensureAnonymous(auth: AuthLike, captchaToken?: string | null, api: ApiFn = defaultApi): Promise<string> {
  const { session } = check(await auth.getSession());
  if (session) return session.user.id;
  const r = await auth.signInAnonymously({ options: captchaOpts(captchaToken) });
  if (r.error) { await reportAuthEvent("sign_in_failure", "anonymous", api); }
  const id = check(r).user.id;
  await reportAuthEvent("sign_in_success", "anonymous", api);
  return id;
}

export type EmailFlow = "link" | "signin";

/** Send a 6-digit code. An anonymous user links the email to the same account; anyone else signs in to an existing one. */
export async function sendEmailCode(auth: AuthLike, email: string, captchaToken?: string | null, api: ApiFn = defaultApi): Promise<EmailFlow> {
  const { session } = check(await auth.getSession());
  if (session?.user.is_anonymous) {
    check(await auth.updateUser({ email }));
    await reportAuthEvent("otp_requested", "email_otp", api);
    return "link";
  }
  check(await auth.signInWithOtp({ email, options: { shouldCreateUser: false, ...captchaOpts(captchaToken) } }));
  await reportAuthEvent("otp_requested", "email_otp", api);
  return "signin";
}

export async function verifyEmailCode(auth: AuthLike, email: string, code: string, flow: EmailFlow, api: ApiFn = defaultApi): Promise<void> {
  if (!/^\d{6}$/.test(code.trim())) throw new ApiError("INVALID_CODE", "Enter the 6-digit code from the email.", 400);
  const r = await auth.verifyOtp({ email, token: code.trim(), type: flow === "link" ? "email_change" : "email" });
  await reportAuthEvent(r.error ? "sign_in_failure" : "sign_in_success", "email_otp", api);
  check(r);
}

/** Phone OTP (Supabase phone auth). Off unless PHONE_OTP_ENABLED: Indian SMS needs DLT registration and a paid
 *  SMS provider. +91 numbers only; the number is never sent to our server. */
export const normalizePhone = (raw: string) => {
  const d = raw.replace(/\D/g, "").replace(/^0+/, "");
  const ten = d.length === 12 && d.startsWith("91") ? d.slice(2) : d;
  return /^[6-9]\d{9}$/.test(ten) ? `+91${ten}` : null;
};
export async function sendPhoneCode(auth: AuthLike, phone: string, captchaToken?: string | null, api: ApiFn = defaultApi) {
  const p = normalizePhone(phone);
  if (!p) throw new ApiError("INVALID_PHONE", "Enter a 10-digit Indian mobile number.", 400);
  check(await auth.signInWithOtp({ phone: p, options: { shouldCreateUser: true, ...captchaOpts(captchaToken) } }));
  await reportAuthEvent("otp_requested", "phone_otp", api);
  return p;
}
export async function verifyPhoneCode(auth: AuthLike, phone: string, code: string, api: ApiFn = defaultApi) {
  const r = await auth.verifyOtp({ phone, token: code.trim(), type: "sms" });
  await reportAuthEvent(r.error ? "sign_in_failure" : "sign_in_success", "phone_otp", api);
  check(r);
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

export type StaffUser = { user_id: string; username: string; role: string; display_name: string; aal?: string };
export type StaffMe = { user: StaffUser; mfa_required: boolean };

/** Staff sign in with Supabase email + password; the role is whatever the server reads from app_metadata. The
 *  result says whether the TOTP step is still needed (every staff API call needs an aal2 token). */
export async function staffSignIn(auth: AuthLike, email: string, password: string, roles: string[],
  api: ApiFn = defaultApi, captchaToken?: string | null): Promise<StaffMe> {
  const r = await auth.signInWithPassword({ email, password, options: captchaOpts(captchaToken) });
  if (r.error) await reportAuthEvent("sign_in_failure", "password", api);
  check(r);
  let me: { user?: StaffUser; mfa_required?: boolean } = {};
  try { me = await api<{ user?: StaffUser; mfa_required?: boolean }>("/auth/me"); } catch { me = {}; }
  if (!me.user || !roles.includes(me.user.role)) {
    await auth.signOut({ scope: "local" });
    throw new ApiError("FORBIDDEN", `This page needs a ${roles.join(" or ")} account.`, 403);
  }
  await reportAuthEvent("sign_in_success", "password", api);
  return { user: me.user, mfa_required: !!me.mfa_required };
}

export type MfaStep = { kind: "verify"; factorId: string } | { kind: "enroll"; factorId: string; qr: string; secret: string; uri: string };

/** After the password: verify the enrolled authenticator, or (first sign-in) enrol a new TOTP factor. Stale
 *  unverified factors from an abandoned enrolment are removed first, so enrolment can always start again. */
export async function nextMfaStep(auth: AuthLike): Promise<MfaStep> {
  const mfa = auth.mfa!;
  const factors = check(await mfa.listFactors());
  const all = factors.all ?? factors.totp;
  const verified = factors.totp.find((f) => f.status === "verified");
  if (verified) return { kind: "verify", factorId: verified.id };
  for (const f of all.filter((x) => x.factor_type === "totp" && x.status !== "verified")) check(await mfa.unenroll({ factorId: f.id }));
  const e = check(await mfa.enroll({ factorType: "totp", friendlyName: `Anvaya staff ${new Date().toISOString().slice(0, 10)}`, issuer: "Anvaya AI" }));
  const qr = e.totp.qr_code.startsWith("data:") ? e.totp.qr_code : `data:image/svg+xml;utf-8,${encodeURIComponent(e.totp.qr_code)}`;
  return { kind: "enroll", factorId: e.id, qr, secret: e.totp.secret, uri: e.totp.uri };
}

/** Verify the 6-digit code: the session becomes aal2. Reports mfa_enrolled / mfa_verified / mfa_failed. */
export async function verifyMfa(auth: AuthLike, step: MfaStep, code: string, api: ApiFn = defaultApi): Promise<void> {
  if (!/^\d{6}$/.test(code.trim())) throw new ApiError("INVALID_CODE", "Enter the 6-digit code from the authenticator app.", 400);
  const r = await auth.mfa!.challengeAndVerify({ factorId: step.factorId, code: code.trim() });
  if (r.error) { await reportAuthEvent("mfa_failed", "totp", api); check(r); }
  await reportAuthEvent(step.kind === "enroll" ? "mfa_enrolled" : "mfa_verified", "totp", api);
}

/** Sign out of every device: the server revokes this account's sessions (Supabase global sign-out + its own check),
 *  then the local copy is dropped. */
export async function signOutEverywhere(auth: AuthLike, api: ApiFn = defaultApi, reason: "user" | "password_changed" = "user") {
  try { await api("/auth/sign-out-all", { body: { reason } }); }
  finally { await auth.signOut({ scope: "local" }); }
}

/** Staff password change: set the new password, then sign out of all devices (including this one). */
export async function changeStaffPassword(auth: AuthLike, password: string, api: ApiFn = defaultApi) {
  if (password.length < 12) throw new ApiError("WEAK_PASSWORD", "Use at least 12 characters.", 400);
  check(await auth.updateUser({ password }));
  await signOutEverywhere(auth, api, "password_changed");
}

/** "Download my data": the JSON export, saved as a file (account holders, or through a resumed session). */
export async function downloadMyData(sessionId?: string | null, api: ApiFn = defaultApi, save: (json: string) => void = saveJson) {
  const data = await api(sessionId ? `/sessions/${sessionId}/export` : "/account/export");
  save(JSON.stringify(data, null, 2));
  return data;
}
function saveJson(json: string) {
  const url = URL.createObjectURL(new Blob([json], { type: "application/json" }));
  const a = Object.assign(document.createElement("a"), { href: url, download: "anvaya-my-data.json" });
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

/** DigiLocker (only when the server has it enabled): ask the server for the provider's authorization URL. */
export async function startDigiLocker(sessionId: string, api: ApiFn = defaultApi): Promise<string> {
  return (await api<{ authorization_url: string }>("/auth/digilocker/start", { body: {}, sessionId })).authorization_url;
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

/** Delete the account on the server (data + Supabase Auth user), then forget the local session. While a case waits
 *  for a reviewer the server refuses with PENDING_CASE_DOCUMENTS until the citizen confirms a second time. */
export async function deleteAccount(auth: AuthLike, { acknowledgePendingCase = false } = {}, api: ApiFn = defaultApi) {
  const res = await api("/account", acknowledgePendingCase ? { method: "DELETE", body: { acknowledge_pending_case: true } } : { method: "DELETE" });
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
