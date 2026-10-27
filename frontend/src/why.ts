// Plain-language wording for the "Why this result" panel and for statuses: no internal codes (CRITERIA_PASSED, DRAFT_SAVED, citizen_entered)
// in front of a citizen. English, Hindi and Telugu; an unknown code falls back to the server's own text.
import type { Lang } from "./i18n";

type Tr = Record<Lang, string>;

const REASONS: Record<string, Tr> = {
  CRITERIA_PASSED: { en: "You meet every condition we can check.", hi: "आप वे सभी शर्तें पूरी करते हैं जिन्हें हम जाँच सकते हैं।", te: "మేము తనిఖీ చేయగల అన్ని షరతులను మీరు నెరవేరుస్తున్నారు." },
  CRITERION_FAILED: { en: "At least one condition is not met.", hi: "कम से कम एक शर्त पूरी नहीं हुई।", te: "కనీసం ఒక షరతు నెరవేరలేదు." },
  EVIDENCE_NOT_VERIFIED: { en: "A reviewer still has to verify your documents.", hi: "आपके दस्तावेज़ों की जाँच समीक्षक को करनी है।", te: "మీ పత్రాలను సమీక్షకుడు ఇంకా ధృవీకరించాలి." },
  FACT_UNKNOWN: { en: "We need a few more details from you.", hi: "हमें आपसे कुछ और जानकारी चाहिए।", te: "మీ నుండి మరికొన్ని వివరాలు కావాలి." },
  MANUAL_CHECKS_PENDING: { en: "An officer checks a few of the conditions.", hi: "कुछ शर्तें अधिकारी जाँचते हैं।", te: "కొన్ని షరతులను అధికారి తనిఖీ చేస్తారు." },
  RULE_NEEDS_REVIEW: { en: "This scheme's rule is being reviewed.", hi: "इस योजना के नियम की समीक्षा चल रही है।", te: "ఈ పథకం నియమం సమీక్షలో ఉంది." },
  SOURCE_NOT_VERIFIED: { en: "The rule has not yet been checked against the official website.", hi: "नियम की आधिकारिक वेबसाइट से जाँच अभी नहीं हुई।", te: "నియమాన్ని అధికారిక వెబ్‌సైట్‌తో ఇంకా సరిచూడలేదు." },
  SOURCE_STALE: { en: "The official source was last checked a while ago.", hi: "आधिकारिक स्रोत की जाँच कुछ समय पहले हुई थी।", te: "అధికారిక మూలాన్ని కొంతకాలం క్రితం తనిఖీ చేశారు." },
};

const TEXT = {
  conditions: { en: "Conditions", hi: "शर्तें", te: "షరతులు" },
  needs: { en: "needs", hi: "ज़रूरी", te: "కావాలి" },
  yours: { en: "yours", hi: "आपका", te: "మీది" },
  met: { en: "Met", hi: "पूरी", te: "నెరవేరింది" },
  notMet: { en: "Not met", hi: "पूरी नहीं", te: "నెరవేరలేదు" },
  unknown: { en: "Need info", hi: "जानकारी चाहिए", te: "సమాచారం కావాలి" },
  officer: { en: "An officer will check", hi: "अधिकारी जाँचेंगे", te: "అధికారి తనిఖీ చేస్తారు" },
  docs: { en: "Documents to bring", hi: "साथ ले जाने वाले दस्तावेज़", te: "తీసుకెళ్లాల్సిన పత్రాలు" },
  updateDocs: { en: "Update my documents →", hi: "मेरे दस्तावेज़ अपडेट करें →", te: "నా పత్రాలను నవీకరించండి →" },
  source: { en: "Official source", hi: "आधिकारिक स्रोत", te: "అధికారిక మూలం" },
  sourceUnverified: { en: "Not yet verified against the official website", hi: "आधिकारिक वेबसाइट से अभी सत्यापित नहीं", te: "అధికారిక వెబ్‌సైట్‌తో ఇంకా ధృవీకరించలేదు" },
  tech: { en: "Technical details", hi: "तकनीकी विवरण", te: "సాంకేతిక వివరాలు" },
  quotes: { en: "Show the official wording", hi: "आधिकारिक शब्द देखें", te: "అధికారిక పదాలు చూడండి" },
  yes: { en: "yes", hi: "हाँ", te: "అవును" },
  no: { en: "no", hi: "नहीं", te: "కాదు" },
  atLeast: { en: "at least {v}", hi: "कम से कम {v}", te: "కనీసం {v}" },
  moreThan: { en: "more than {v}", hi: "{v} से अधिक", te: "{v} కంటే ఎక్కువ" },
  atMost: { en: "at most {v}", hi: "ज़्यादा से ज़्यादा {v}", te: "గరిష్టంగా {v}" },
  lessThan: { en: "less than {v}", hi: "{v} से कम", te: "{v} కంటే తక్కువ" },
  between: { en: "between {a} and {b}", hi: "{a} और {b} के बीच", te: "{a} మరియు {b} మధ్య" },
  not: { en: "not {v}", hi: "{v} नहीं", te: "{v} కాదు" },
  or: { en: "or", hi: "या", te: "లేదా" },
} satisfies Record<string, Tr>;
export type WhyKey = keyof typeof TEXT;

export const whyText = (key: WhyKey, lang: Lang) => TEXT[key][lang];
export const WHY_KEYS = Object.keys(TEXT) as WhyKey[];
export const REASON_CODES = Object.keys(REASONS);

/** A decision reason in plain words. The server's code never shows; an unknown code shows the server's own sentence. */
export const reasonText = (code: string, fallback: string, lang: Lang) => REASONS[code]?.[lang] ?? fallback;
export const reasonTone = (code: string): "ok" | "warn" => (code === "CRITERIA_PASSED" ? "ok" : "warn");

type Show = (fact: string, value: any, lang: Lang) => string;

/** What a rule needs ("≥ 60", "yes", "18–60", "rural / urban") as a sentence fragment ("at least 60 years"). */
export function humanExpected(expected: string, fact: string, lang: Lang, show: Show): string {
  const e = (expected ?? "").trim();
  const val = (v: string) => { const n = Number(v.replace(/,/g, "")); return Number.isFinite(n) && v.trim() !== "" ? show(fact, n, lang) : v.trim(); };
  const fill = (key: WhyKey, vars: Record<string, string>) => Object.entries(vars).reduce((s, [k, v]) => s.replace(`{${k}}`, v), whyText(key, lang));
  if (e === "yes") return whyText("yes", lang);
  if (e === "no") return whyText("no", lang);
  const range = /^(.+?)[–-](.+)$/.exec(e);
  if (range && /^[\d.,\s]+$/.test(range[1]) && /^[\d.,\s]+$/.test(range[2])) return fill("between", { a: val(range[1]), b: val(range[2]) });
  const op = /^(>=|<=|!=|==|>|<|=)\s*(.+)$/.exec(e);
  if (op) {
    const v = val(op[2]);
    return ({ ">=": fill("atLeast", { v }), "<=": fill("atMost", { v }), ">": fill("moreThan", { v }), "<": fill("lessThan", { v }),
      "!=": fill("not", { v }), "==": v, "=": v } as Record<string, string>)[op[1]];
  }
  return e.split(" / ").map((x) => x.replace(/_/g, " ")).join(` ${whyText("or", lang)} `);
}
