import { apiBlob } from "./api";
import type { Lang } from "./i18n";

/** The scheme passport (latest screening) as a PDF, saved as a file. `code` (a just-saved Passport code) is printed on it;
 *  the PIN is never part of it. */
export async function downloadPassportPdf(sessionId: string, lang: Lang, code?: string): Promise<void> {
  const blob = await apiBlob(`/sessions/${sessionId}/passport.pdf?language=${lang}`,
    { sessionId, headers: code ? { "X-Passport-Code": code } : undefined });
  const url = URL.createObjectURL(blob);
  Object.assign(document.createElement("a"), { href: url, download: `anvaya-scheme-passport-${lang}.pdf` }).click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
