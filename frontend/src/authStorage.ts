// Where supabase-js keeps the sign-in, per mode. Kiosk: memory only — never localStorage or sessionStorage, so a
// reload, a closed tab or the next person at the kiosk finds nothing (the operator signs in again). Personal device:
// localStorage, so a reload does not lose an unsaved passport.
export const isKiosk = () => { try { return sessionStorage.getItem("anvaya.mode") === "kiosk"; } catch { return false; } };

const memory = new Map<string, string>();

export const authStorage = {
  getItem: (k: string): string | null => {
    if (isKiosk()) return memory.get(k) ?? null;
    try { return localStorage.getItem(k); } catch { return memory.get(k) ?? null; }
  },
  setItem: (k: string, v: string) => {
    if (isKiosk()) { memory.set(k, v); return; }
    try { localStorage.setItem(k, v); } catch { memory.set(k, v); }
  },
  removeItem: (k: string) => {
    memory.delete(k);
    try { localStorage.removeItem(k); sessionStorage.removeItem(k); } catch { /* blocked */ }
  },
};

/** Switching a browser to kiosk mode: forget any personal sign-in kept in localStorage on this device. */
export function clearPersistedAuth() {
  try { Object.keys(localStorage).filter((k) => k.startsWith("sb-")).forEach((k) => localStorage.removeItem(k)); } catch { /* */ }
  memory.clear();
}
