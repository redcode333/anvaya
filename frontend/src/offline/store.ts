// Kiosk edge storage: versioned rule bundle (atomic swap, last-known-good kept) + durable outbox.
// Browser localStorage stands in for the kiosk's local SQLite in this prototype.
import { api, newKey } from "../api";
import type { Meta, Rule } from "./rulesEngine";

export type Bundle = { bundle_version: string; generated_at: string; checksum: string; rules: { rule: Rule; meta: Meta & { scheme_state?: string } }[]; documents: Record<string, Record<string, [string, string]>> };
export type OutboxEvent = {
  event_id: string; idempotency_key: string; type: "offline_draft"; schema_version: 1; created_at: string;
  bundle_version: string; payload: any; sync: { state: "SYNC_PENDING" | "SYNCED" | "FAILED_RETRYABLE" | "CONFLICT"; attempts: number; last_error?: string; result?: any };
};

const K_BUNDLE = "anvaya.bundle.active";
const K_PREV = "anvaya.bundle.lastKnownGood";
const K_OUTBOX = "anvaya.outbox";
const K_DEVICE = "anvaya.deviceId";

const read = <T,>(k: string): T | null => { try { const v = localStorage.getItem(k); return v ? JSON.parse(v) : null; } catch { return null; } };
const write = (k: string, v: any) => { try { localStorage.setItem(k, JSON.stringify(v)); return true; } catch { return false; } };

export const deviceId = () => {
  let id = read<string>(K_DEVICE);
  if (!id) { id = `KIOSK-${newKey().slice(0, 8).toUpperCase()}`; write(K_DEVICE, id); }
  return id;
};

export const getBundle = () => read<Bundle>(K_BUNDLE);

async function sha256(text: string) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// Python json.dumps(sort_keys=True, ensure_ascii=False) equivalent for checksum validation.
function canonical(v: any): string {
  if (Array.isArray(v)) return `[${v.map(canonical).join(", ")}]`;
  if (v && typeof v === "object") return `{${Object.keys(v).sort().map((k) => `${JSON.stringify(k)}: ${canonical(v[k])}`).join(", ")}}`;
  return JSON.stringify(v);
}

export async function refreshBundle(): Promise<{ ok: boolean; bundle: Bundle | null; message: string }> {
  const current = getBundle();
  try {
    const b = await api<Bundle>("/sync/bundle");
    const { generated_at: _g, checksum, ...body } = b;
    const valid = (await sha256(canonical(body))) === checksum;
    if (!valid || !b.rules?.length) return { ok: false, bundle: current, message: "Downloaded bundle failed validation; keeping last-known-good." };
    if (current) write(K_PREV, current);
    write(K_BUNDLE, b); // switch only after validation
    return { ok: true, bundle: b, message: `Bundle ${b.bundle_version} installed.` };
  } catch (e: any) {
    return { ok: false, bundle: current, message: `Refresh failed (${e.code || "error"}); using cached bundle.` };
  }
}

export const getOutbox = () => read<OutboxEvent[]>(K_OUTBOX) || [];
const saveOutbox = (o: OutboxEvent[]) => write(K_OUTBOX, o);

export function enqueue(payload: any, bundle_version: string): OutboxEvent {
  const ev: OutboxEvent = {
    event_id: newKey(), idempotency_key: newKey(), type: "offline_draft", schema_version: 1,
    created_at: new Date().toISOString(), bundle_version, payload, sync: { state: "SYNC_PENDING", attempts: 0 },
  };
  saveOutbox([...getOutbox(), ev]);
  return ev;
}

export function clearSynced() { saveOutbox(getOutbox().filter((e) => e.sync.state !== "SYNCED")); }

// Upload pending events; server dedupes by idempotency key. `resendSynced` demonstrates retry safety.
export async function syncOutbox(resendSynced = false) {
  const box = getOutbox();
  const toSend = box.filter((e) => resendSynced || e.sync.state !== "SYNCED");
  if (!toSend.length) return { sent: 0, results: [] as any[] };
  try {
    const res = await api<{ results: any[]; server_bundle_version: string }>("/sync/events", {
      body: { device_id: deviceId(), events: toSend.map(({ sync: _s, ...e }) => e) },
    });
    for (const r of res.results) {
      const ev = box.find((e) => e.event_id === r.event_id);
      if (!ev) continue;
      ev.sync.attempts += 1;
      if (r.status === "accepted" || r.status === "accepted_no_draft") ev.sync = { ...ev.sync, state: "SYNCED", result: r };
      else if (r.status === "duplicate") ev.sync = { ...ev.sync, state: "SYNCED", result: { ...r.original, duplicate_ack: true } };
      else if (r.status === "conflict") ev.sync = { ...ev.sync, state: "CONFLICT", result: r };
      else ev.sync = { ...ev.sync, state: "FAILED_RETRYABLE", last_error: r.reason };
    }
    saveOutbox(box);
    return { sent: toSend.length, results: res.results };
  } catch (e: any) {
    for (const ev of toSend) { ev.sync.attempts += 1; ev.sync.state = "FAILED_RETRYABLE"; ev.sync.last_error = e.code; }
    saveOutbox(box);
    throw e;
  }
}
