import { useEffect, useState } from "react";

export type FeatureStatus = "off" | "coming_soon" | "on";
export type PublicConfig = { digilocker_status: FeatureStatus; phone_otp_status: FeatureStatus; turnstile_site_key: string | null };

const STATUSES: FeatureStatus[] = ["off", "coming_soon", "on"];
// If the config can't be loaded, show the options but keep them unusable: no request can fire from "coming_soon".
export const FALLBACK_CONFIG: PublicConfig = { digilocker_status: "coming_soon", phone_otp_status: "coming_soon", turnstile_site_key: null };

const norm = (v: unknown): FeatureStatus => (STATUSES.includes(v as FeatureStatus) ? (v as FeatureStatus) : "coming_soon");

let cached: Promise<PublicConfig> | null = null;

/** GET /api/config: read at runtime (not baked into the build) so options can be switched on without a rebuild. */
export function loadConfig(): Promise<PublicConfig> {
  if (!cached) {
    cached = fetch("/api/config", { headers: { Accept: "application/json" } })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => ({ digilocker_status: norm(d.digilocker_status), phone_otp_status: norm(d.phone_otp_status), turnstile_site_key: d.turnstile_site_key || null }))
      .catch(() => { cached = null; return FALLBACK_CONFIG; });
  }
  return cached;
}

/** Test hook: forget the cached config. */
export function resetConfigCache() { cached = null; }

export function useFeatureConfig(): { loading: boolean; config: PublicConfig } {
  const [config, setConfig] = useState<PublicConfig | null>(null);
  useEffect(() => {
    let live = true;
    loadConfig().then((c) => { if (live) setConfig(c); });
    return () => { live = false; };
  }, []);
  return { loading: config === null, config: config ?? FALLBACK_CONFIG };
}
