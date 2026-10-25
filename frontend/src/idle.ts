// Kiosk idle timeout: after (idle - warning) seconds without input a "Still there?" warning appears; if nobody
// answers within `warning` seconds the session ends exactly like the End session button (server-side deletion of
// unconsented data). Any input during the warning keeps the session.
export type IdleTimer = { activity: () => void; stop: () => void };

/** Milliseconds until a kiosk session's absolute end (the server's expires_at); 0 if already past. */
export function absoluteLimitMs(expiresAt: string, nowMs: number): number {
  const end = Date.parse(expiresAt);
  return Number.isFinite(end) ? Math.max(0, end - nowMs) : 0;
}

export function createIdleTimer(opts: {
  idleSeconds: number; warningSeconds: number;
  onWarn: () => void; onActive: () => void; onTimeout: () => void;
}): IdleTimer {
  const warnAfter = Math.max(1, opts.idleSeconds - opts.warningSeconds) * 1000;
  let warnTimer: ReturnType<typeof setTimeout> | undefined;
  let endTimer: ReturnType<typeof setTimeout> | undefined;
  let warned = false, stopped = false;
  const clear = () => { clearTimeout(warnTimer); clearTimeout(endTimer); };
  const arm = () => {
    clear();
    warnTimer = setTimeout(() => {
      warned = true;
      opts.onWarn();
      endTimer = setTimeout(() => { stopped = true; opts.onTimeout(); }, opts.warningSeconds * 1000);
    }, warnAfter);
  };
  arm();
  return {
    activity: () => {
      if (stopped) return;
      if (warned) { warned = false; opts.onActive(); }
      arm();
    },
    stop: () => { stopped = true; clear(); },
  };
}
