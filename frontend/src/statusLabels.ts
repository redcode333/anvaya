// Statuses and field sources in plain words (never DRAFT_SAVED, PENDING_REVIEW, citizen_entered, missing).
import type { Lang } from "./i18n";

const STATUS: Record<string, Record<Lang, string>> = {
  DRAFT_SAVED: { en: "Draft saved", hi: "ड्राफ़्ट सहेजा गया", te: "డ్రాఫ్ట్ సేవ్ అయింది" },
  PENDING_REVIEW: { en: "With a reviewer", hi: "समीक्षक के पास", te: "సమీక్షకుని వద్ద" },
  CORRECTION_REQUESTED: { en: "Correction requested", hi: "सुधार माँगा गया", te: "సవరణ కోరారు" },
  REVIEWED: { en: "Reviewed", hi: "समीक्षा हो गई", te: "సమీక్షించారు" },
  SYNCED: { en: "Synced from kiosk", hi: "कियोस्क से सिंक हुआ", te: "కియోస్క్ నుండి సింక్ అయింది" },
  SYNC_PENDING: { en: "Waiting to sync", hi: "सिंक होना बाकी", te: "సింక్ కావాల్సి ఉంది" },
  SESSION_ACTIVE: { en: "In progress", hi: "जारी है", te: "కొనసాగుతోంది" },
  PROFILE_NEEDS_CONFIRMATION: { en: "Needs your confirmation", hi: "आपकी पुष्टि चाहिए", te: "మీ నిర్ధారణ కావాలి" },
};
const humanize = (s: string) => s.toLowerCase().replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
export const statusLabel = (code: string | null | undefined, lang: Lang) => (!code ? "" : STATUS[code]?.[lang] ?? humanize(code));

const SOURCE: Record<string, Record<Lang, string>> = {
  confirmed: { en: "Confirmed", hi: "पुष्टि हुई", te: "నిర్ధారించబడింది" },
  citizen_entered: { en: "You entered", hi: "आपने भरा", te: "మీరు నమోదు చేశారు" },
  inferred: { en: "Please check", hi: "कृपया जाँचें", te: "దయచేసి తనిఖీ చేయండి" },
  unconfirmed: { en: "Not confirmed", hi: "पुष्टि नहीं हुई", te: "నిర్ధారించలేదు" },
  missing: { en: "To fill in", hi: "भरना बाकी", te: "నింపాలి" },
};
export const sourceLabel = (code: string, lang: Lang) => SOURCE[code]?.[lang] ?? humanize(code);
