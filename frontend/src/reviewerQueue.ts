// Helpers for the review queue: how long a case has waited, and the order cases are shown in.

/** Hours since an ISO timestamp (never negative; 0 when it cannot be read). */
export function ageHours(iso: string | null | undefined, now = Date.now()): number {
  const t = iso ? Date.parse(iso) : NaN;
  return Number.isFinite(t) ? Math.max(0, (now - t) / 3_600_000) : 0;
}

/** A short "how long ago": "just now", "12 min", "3 h", "2 d". */
export function timeAgo(iso: string | null | undefined, now = Date.now()): string {
  const h = ageHours(iso, now);
  if (!iso || !Number.isFinite(Date.parse(iso))) return "—";
  if (h < 1 / 60) return "just now";
  if (h < 1) return `${Math.round(h * 60)} min`;
  if (h < 48) return `${Math.round(h)} h`;
  return `${Math.round(h / 24)} d`;
}

type Row = { status: string; updated_at: string };

/** Waiting cases first, the longest-waiting at the top (that is the one to open next); everything else newest first. */
export function queueOrder<T extends Row>(cases: T[]): T[] {
  const at = (c: T) => Date.parse(c.updated_at) || 0;
  return [...cases].sort((a, b) => {
    const pa = a.status === "PENDING_REVIEW", pb = b.status === "PENDING_REVIEW";
    if (pa !== pb) return pa ? -1 : 1;
    return pa ? at(a) - at(b) : at(b) - at(a);
  });
}
