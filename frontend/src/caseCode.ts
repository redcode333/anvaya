// The two codes a citizen can hold, and the one mistake between them:
//   ANV-XXXX-XXXX  case code     given when a draft is sent to a reviewer; used on the Case status page
//   PSP-XXXX-XXXX  Passport code saves a profile; reopened with its PIN on the Resume page
export type CodeKind = "case" | "passport" | "empty";

const clean = (v: string) => v.toUpperCase().replace(/[^A-Z0-9]/g, "");

export function codeKind(v: string): CodeKind {
  const raw = clean(v);
  if (!raw) return "empty";
  return raw.startsWith("PSP") ? "passport" : "case";
}

/** Formats while typing: uppercase, no stray characters, dashes after the prefix and after four characters. */
export function formatCaseCode(v: string): string {
  const raw = clean(v);
  const prefix = raw.startsWith("PSP") ? "PSP" : "ANV";
  if (raw.length <= 3 && prefix.startsWith(raw)) return raw;  // still typing the prefix
  const body = raw.startsWith(prefix) ? raw.slice(3) : raw;
  return `${prefix}-${body.slice(0, 4)}${body.length > 4 ? `-${body.slice(4, 8)}` : ""}`;
}

/** A complete case code (ANV- plus eight characters). */
export const isCompleteCaseCode = (v: string) => /^ANV-[A-Z0-9]{4}-[A-Z0-9]{4}$/.test(formatCaseCode(v));
