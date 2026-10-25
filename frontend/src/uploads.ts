// Document uploads go through the Anvaya backend, never straight to Supabase Storage: the server hands out a signed,
// single-use upload link (5 minutes) and checks the file's real type and size. The browser keeps no copy: the file
// object is dropped after the upload, and view links are no-store.
import { api as defaultApi, ApiError } from "./api";

export const UPLOAD_CONSENT_VERSION = "upload-2026-10";
export const UPLOAD_TYPES = ["image/jpeg", "image/png", "application/pdf"];
export const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;

export function fileProblem(file: { type: string; size: number }): "type" | "size" | null {
  if (!UPLOAD_TYPES.includes(file.type)) return "type";
  if (file.size <= 0 || file.size > MAX_UPLOAD_BYTES) return "size";
  return null;
}

type Put = (url: string, file: Blob, contentType: string, onProgress: (pct: number) => void) => Promise<any>;

/** PUT with progress (XMLHttpRequest reports upload progress; fetch does not). */
export const xhrPut: Put = (url, file, contentType, onProgress) => new Promise((resolve, reject) => {
  const xhr = new XMLHttpRequest();
  xhr.open("PUT", url);
  xhr.setRequestHeader("Content-Type", contentType);
  xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(Math.round((e.loaded / e.total) * 100)); };
  xhr.onload = () => {
    let data: any = {};
    try { data = JSON.parse(xhr.responseText || "{}"); } catch { /* not JSON */ }
    if (xhr.status >= 200 && xhr.status < 300) resolve(data);
    else { const e = data.error || {}; reject(new ApiError(e.code || `HTTP_${xhr.status}`, e.message || "Upload failed.", xhr.status, e.details, e.request_id)); }
  };
  xhr.onerror = () => reject(new ApiError("NETWORK", "Upload failed: no connection to the server.", 0));
  xhr.send(file);
});

/** Ask for an upload link (ownership + consent are checked by the server), then send the file through it. */
export async function uploadDocument(sessionId: string, docKey: string, file: File, onProgress: (pct: number) => void,
  api = defaultApi, put: Put = xhrPut) {
  const problem = fileProblem(file);
  if (problem) throw new ApiError(problem === "type" ? "UNSUPPORTED_TYPE" : "FILE_TOO_LARGE",
    problem === "type" ? "Upload a JPEG, PNG or PDF file." : "Files must be 5 MB or smaller.", 422);
  const link = await api<{ upload_url: string; content_type: string }>(`/sessions/${sessionId}/documents/${docKey}/upload-url`, {
    body: { content_type: file.type, size: file.size, consent: { version: UPLOAD_CONSENT_VERSION, accepted: true } },
  });
  onProgress(0);
  return put(link.upload_url, file, link.content_type, onProgress);
}

export async function viewLink(sessionId: string, docKey: string, api = defaultApi) {
  return api<{ view_url: string; content_type: string; expires_at: string }>(`/sessions/${sessionId}/documents/${docKey}/view-url`);
}
