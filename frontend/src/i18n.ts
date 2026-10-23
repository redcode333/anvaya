export type Lang = "en" | "hi" | "te";
export const LANGS: { code: Lang; name: string; speech: string }[] = [
  { code: "te", name: "తెలుగు", speech: "te-IN" },
  { code: "hi", name: "हिन्दी", speech: "hi-IN" },
  { code: "en", name: "English", speech: "en-IN" },
];

const S = {
  tagline: { en: "Every voice, a way forward.", hi: "हर आवाज़, एक राह।", te: "ప్రతి గొంతుకకూ ఒక దారి." },
  intro: {
    en: "Find government welfare schemes your household may qualify for, understand the documents needed, and prepare a draft for review.",
    hi: "जानिए कि आपका परिवार किन सरकारी योजनाओं के लिए पात्र हो सकता है, कौन से दस्तावेज़ चाहिए, और समीक्षा के लिए ड्राफ़्ट तैयार करें।",
    te: "మీ కుటుంబానికి అర్హత ఉండే ప్రభుత్వ సంక్షేమ పథకాలను తెలుసుకోండి, అవసరమైన పత్రాలను అర్థం చేసుకోండి, సమీక్ష కోసం డ్రాఫ్ట్ సిద్ధం చేయండి.",
  },
  start: { en: "Start", hi: "शुरू करें", te: "ప్రారంభించండి" },
  personal: { en: "On my phone", hi: "अपने फ़ोन पर", te: "నా ఫోన్‌లో" },
  kiosk: { en: "Kiosk / assisted", hi: "कियोस्क / सहायता", te: "కియోస్క్ / సహాయంతో" },
  chooseLang: { en: "Choose your language", hi: "अपनी भाषा चुनें", te: "మీ భాష ఎంచుకోండి" },
  speak: { en: "Speak", hi: "बोलें", te: "మాట్లాడండి" },
  listening: { en: "Listening… tap to stop", hi: "सुन रहे हैं… रोकने के लिए दबाएँ", te: "వింటున్నాం… ఆపడానికి నొక్కండి" },
  send: { en: "Send", hi: "भेजें", te: "పంపండి" },
  typeHere: { en: "Type about your household…", hi: "अपने परिवार के बारे में लिखें…", te: "మీ కుటుంబం గురించి టైప్ చేయండి…" },
  profile: { en: "Your details", hi: "आपकी जानकारी", te: "మీ వివరాలు" },
  confirm: { en: "Confirm", hi: "पुष्टि करें", te: "నిర్ధారించండి" },
  confirmAll: { en: "Other details are correct — confirm them", hi: "बाकी जानकारी सही है — पुष्टि करें", te: "మిగిలిన వివరాలు సరైనవే — నిర్ధారించండి" },
  confirmEach: { en: "Check each number and confirm it on its own", hi: "हर संख्या जाँचें और अलग से पुष्टि करें", te: "ప్రతి సంఖ్యను సరిచూసి విడిగా నిర్ధారించండి" },
  machineTranslated: { en: "Machine translation", hi: "मशीनी अनुवाद", te: "యంత్ర అనువాదం" },
  isThisRight: { en: "Is this right?", hi: "क्या यह सही है?", te: "ఇది సరైనదేనా?" },
  whichIsRight: { en: "Two values were heard — which is right?", hi: "दो अलग मान सुने गए — कौन सा सही है?", te: "రెండు విలువలు వినిపించాయి — ఏది సరైనది?" },
  correct: { en: "Correct", hi: "सुधारें", te: "సరిచేయండి" },
  save: { en: "Save", hi: "सहेजें", te: "సేవ్ చేయండి" },
  cancel: { en: "Cancel", hi: "रद्द करें", te: "రద్దు" },
  heard: { en: "heard", hi: "सुना", te: "విన్నది" },
  needsConfirm: { en: "Please confirm", hi: "कृपया पुष्टि करें", te: "దయచేసి నిర్ధారించండి" },
  confirmed: { en: "Confirmed", hi: "पुष्टि हुई", te: "నిర్ధారించబడింది" },
  checkSchemes: { en: "Check schemes", hi: "योजनाएँ देखें", te: "పథకాలు చూడండి" },
  passport: { en: "Scheme Passport", hi: "योजना पासपोर्ट", te: "పథకాల పాస్‌పోర్ట్" },
  documents: { en: "Document Guide", hi: "दस्तावेज़ गाइड", te: "పత్రాల గైడ్" },
  draft: { en: "Draft", hi: "ड्राफ़्ट", te: "డ్రాఫ్ట్" },
  why: { en: "Why", hi: "क्यों", te: "ఎందుకు" },
  source: { en: "Source", hi: "स्रोत", te: "మూలం" },
  prepareDraft: { en: "Prepare draft", hi: "ड्राफ़्ट तैयार करें", te: "డ్రాఫ్ట్ సిద్ధం చేయండి" },
  listen: { en: "Listen to summary", hi: "सारांश सुनें", te: "సారాంశం వినండి" },
  audioUnavailable: { en: "Audio unavailable — please read the text.", hi: "ऑडियो उपलब्ध नहीं — कृपया लिखा हुआ पढ़ें।", te: "ఆడియో అందుబాటులో లేదు — దయచేసి వచనం చదవండి." },
  notApproval: {
    en: "Preliminary screening only — not an approval and not a guarantee of benefit.",
    hi: "यह केवल प्रारंभिक जाँच है — स्वीकृति या लाभ की गारंटी नहीं।",
    te: "ఇది ప్రాథమిక పరిశీలన మాత్రమే — ఆమోదం లేదా ప్రయోజనానికి హామీ కాదు.",
  },
  consent: {
    en: "I agree to share my details, document status and this screening result with an authorised reviewer.",
    hi: "मैं अपनी जानकारी, दस्तावेज़ों की स्थिति और यह जाँच परिणाम अधिकृत समीक्षक के साथ साझा करने के लिए सहमत हूँ।",
    te: "నా వివరాలు, పత్రాల స్థితి మరియు ఈ పరిశీలన ఫలితాన్ని అధీకృత సమీక్షకునితో పంచుకోవడానికి అంగీకరిస్తున్నాను.",
  },
  sendReview: { en: "Send to reviewer", hi: "समीक्षक को भेजें", te: "సమీక్షకునికి పంపండి" },
  yourCode: { en: "Your case code", hi: "आपका केस कोड", te: "మీ కేసు కోడ్" },
  codeNote: {
    en: "Use this code to check status. It is not an ID and does not show your personal details.",
    hi: "स्थिति देखने के लिए यह कोड रखें। यह पहचान पत्र नहीं है और आपकी निजी जानकारी नहीं दिखाता।",
    te: "స్థితి తెలుసుకోవడానికి ఈ కోడ్ ఉపయోగించండి. ఇది గుర్తింపు కాదు, మీ వ్యక్తిగత వివరాలు చూపదు.",
  },
  endSession: { en: "End session & clear screen", hi: "सत्र समाप्त करें और स्क्रीन साफ़ करें", te: "సెషన్ ముగించి స్క్రీన్ క్లియర్ చేయండి" },
  online: { en: "Online", hi: "ऑनलाइन", te: "ఆన్‌లైన్" },
  offline: { en: "Offline", hi: "ऑफ़लाइन", te: "ఆఫ్‌లైన్" },
  checkStatus: { en: "Check case status", hi: "केस की स्थिति देखें", te: "కేసు స్థితి చూడండి" },
  docNote: {
    en: "Ticking a box is your own declaration — it is not official verification.",
    hi: "टिक करना आपकी अपनी घोषणा है — यह आधिकारिक सत्यापन नहीं है।",
    te: "టిక్ చేయడం మీ స్వంత ప్రకటన మాత్రమే — ఇది అధికారిక ధృవీకరణ కాదు.",
  },
  neededFor: { en: "Needed for", hi: "इनके लिए ज़रूरी", te: "వీటికి అవసరం" },
  missingInfo: { en: "Missing information", hi: "छूटी जानकारी", te: "లేని సమాచారం" },
  changed: { en: "What changed after your correction", hi: "सुधार के बाद क्या बदला", te: "సవరణ తర్వాత ఏమి మారింది" },
  addDetail: { en: "Add a detail", hi: "जानकारी जोड़ें", te: "వివరం జోడించండి" },
} as const;

export type Key = keyof typeof S;
export const t = (k: Key, lang: Lang) => S[k][lang] ?? S[k].en;

export const ATTR: Record<string, Record<Lang, string>> = {
  state: { en: "State", hi: "राज्य", te: "రాష్ట్రం" },
  district: { en: "District", hi: "ज़िला", te: "జిల్లా" },
  age: { en: "Age", hi: "उम्र", te: "వయస్సు" },
  annual_income: { en: "Yearly income (₹)", hi: "सालाना आय (₹)", te: "వార్షిక ఆదాయం (₹)" },
  household_size: { en: "Household members", hi: "परिवार के सदस्य", te: "కుటుంబ సభ్యులు" },
  gender: { en: "Gender", hi: "लिंग", te: "లింగం" },
  marital_status: { en: "Marital status", hi: "वैवाहिक स्थिति", te: "వైవాహిక స్థితి" },
  area: { en: "Rural / urban", hi: "ग्रामीण / शहरी", te: "గ్రామీణ / పట్టణ" },
  occupation: { en: "Occupation", hi: "व्यवसाय", te: "వృత్తి" },
  bpl: { en: "BPL household", hi: "बीपीएल परिवार", te: "బీపీఎల్ కుటుంబం" },
  receives_other_pension: { en: "Gets another pension", hi: "अन्य पेंशन मिलती है", te: "వేరే పెన్షన్ వస్తుంది" },
  owns_cultivable_land: { en: "Owns farm land", hi: "खेती की ज़मीन है", te: "సాగు భూమి ఉంది" },
  has_bank_account: { en: "Has bank account", hi: "बैंक खाता है", te: "బ్యాంక్ ఖాతా ఉంది" },
  owns_pucca_house: { en: "Owns pucca house", hi: "पक्का मकान है", te: "పక్కా ఇల్లు ఉంది" },
  applicant_name: { en: "Applicant name", hi: "आवेदक का नाम", te: "దరఖాస్తుదారుని పేరు" },
};
export const attrLabel = (a: string, lang: Lang) => ATTR[a]?.[lang] ?? a;

export const ENUMS: Record<string, string[]> = {
  gender: ["female", "male", "other"],
  marital_status: ["married", "widowed", "single", "divorced"],
  area: ["rural", "urban"],
  occupation: ["farmer", "construction_worker", "weaver", "labourer", "student", "self_employed", "salaried", "homemaker", "other"],
};
export const BOOL_ATTRS = ["bpl", "receives_other_pension", "owns_cultivable_land", "has_bank_account", "owns_pucca_house"];
export const NUM_ATTRS = ["age", "annual_income", "household_size"];
export const STATES = [
  "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh", "Chhattisgarh",
  "Dadra & Nagar Haveli and Daman & Diu", "Delhi", "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jammu and Kashmir",
  "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
  "Mizoram", "Nagaland", "Odisha", "Puducherry", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura",
  "Uttar Pradesh", "Uttarakhand", "West Bengal",
];

const YES = { en: "Yes", hi: "हाँ", te: "అవును" };
const NO = { en: "No", hi: "नहीं", te: "కాదు" };
export function showValue(attr: string, v: any, lang: Lang): string {
  if (v === null || v === undefined) return "—";
  if (typeof v === "boolean") return v ? YES[lang] : NO[lang];
  if (attr === "annual_income") return `₹${Number(v).toLocaleString("en-IN")}`;
  return String(v).replace(/_/g, " ");
}

export const OUTCOME_LABEL: Record<string, Record<Lang, string>> = {
  MATCH: { en: "Potential match", hi: "संभावित मिलान", te: "సంభావ్య సరిపోలిక" },
  PROVISIONAL: { en: "Provisional match", hi: "अस्थायी मिलान", te: "తాత్కాలిక సరిపోలిక" },
  MISMATCH: { en: "Does not match", hi: "मेल नहीं खाता", te: "సరిపోలలేదు" },
  INSUFFICIENT_INFORMATION: { en: "Need more information", hi: "और जानकारी चाहिए", te: "మరింత సమాచారం కావాలి" },
  NEEDS_HUMAN_REVIEW: { en: "Needs human review", hi: "मानव समीक्षा आवश्यक", te: "మానవ సమీక్ష అవసరం" },
};
