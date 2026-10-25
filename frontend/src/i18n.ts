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
  myPassports: { en: "My Passports", hi: "मेरे पासपोर्ट", te: "నా పాస్‌పోర్ట్‌లు" },
  savePassports: { en: "Save my passports", hi: "मेरे पासपोर्ट सहेजें", te: "నా పాస్‌పోర్ట్‌లను సేవ్ చేయండి" },
  saveIntro: {
    en: "Right now nothing is kept after this session. To come back later, save with your email or with a Passport code and PIN.",
    hi: "अभी इस सत्र के बाद कुछ भी नहीं रखा जाता। बाद में लौटने के लिए अपने ईमेल से या पासपोर्ट कोड और पिन से सहेजें।",
    te: "ప్రస్తుతం ఈ సెషన్ తర్వాత ఏదీ ఉంచబడదు. తర్వాత తిరిగి రావడానికి మీ ఈమెయిల్‌తో లేదా పాస్‌పోర్ట్ కోడ్ మరియు పిన్‌తో సేవ్ చేయండి.",
  },
  consentSave: {
    en: "I agree that Anvaya keeps my details, screening results and their history so I can come back to them. I can delete everything at any time.",
    hi: "मैं सहमत हूँ कि Anvaya मेरी जानकारी, जाँच के परिणाम और उनका इतिहास रखे ताकि मैं बाद में लौट सकूँ। मैं कभी भी सब कुछ मिटा सकता/सकती हूँ।",
    te: "నేను తిరిగి రాగలిగేలా Anvaya నా వివరాలు, పరిశీలన ఫలితాలు మరియు వాటి చరిత్రను ఉంచడానికి అంగీకరిస్తున్నాను. నేను ఎప్పుడైనా అన్నింటినీ తొలగించగలను.",
  },
  email: { en: "Email", hi: "ईमेल", te: "ఈమెయిల్" },
  sendCode: { en: "Send code", hi: "कोड भेजें", te: "కోడ్ పంపండి" },
  enterCode: { en: "6-digit code from the email", hi: "ईमेल में आया 6 अंकों का कोड", te: "ఈమెయిల్‌లో వచ్చిన 6 అంకెల కోడ్" },
  verifySave: { en: "Verify and save", hi: "पुष्टि करें और सहेजें", te: "ధృవీకరించి సేవ్ చేయండి" },
  google: { en: "Continue with Google", hi: "Google से जारी रखें", te: "Googleతో కొనసాగండి" },
  orCode: { en: "No email? Save with a Passport code and PIN", hi: "ईमेल नहीं है? पासपोर्ट कोड और पिन से सहेजें", te: "ఈమెయిల్ లేదా? పాస్‌పోర్ట్ కోడ్ మరియు పిన్‌తో సేవ్ చేయండి" },
  choosePin: { en: "Choose a 4-digit PIN", hi: "4 अंकों का पिन चुनें", te: "4 అంకెల పిన్ ఎంచుకోండి" },
  pinFormat: { en: "The PIN must be exactly 4 digits.", hi: "पिन ठीक 4 अंकों का होना चाहिए।", te: "పిన్ సరిగ్గా 4 అంకెలు ఉండాలి." },
  pinWeak: { en: "This PIN is too easy to guess. Choose another.", hi: "यह पिन आसानी से अनुमान लगाया जा सकता है। दूसरा चुनें।", te: "ఈ పిన్ సులభంగా ఊహించవచ్చు. వేరొకటి ఎంచుకోండి." },
  saveWithCode: { en: "Save with code + PIN", hi: "कोड + पिन से सहेजें", te: "కోడ్ + పిన్‌తో సేవ్ చేయండి" },
  yourPassportCode: { en: "Your Passport code", hi: "आपका पासपोर्ट कोड", te: "మీ పాస్‌పోర్ట్ కోడ్" },
  readAgain: { en: "Read it again", hi: "फिर से सुनाएँ", te: "మళ్ళీ చదవండి" },
  saved: { en: "Saved", hi: "सहेजा गया", te: "సేవ్ అయింది" },
  savedAccount: { en: "Your passports are saved to your account.", hi: "आपके पासपोर्ट आपके खाते में सहेजे गए हैं।", te: "మీ పాస్‌పోర్ట్‌లు మీ ఖాతాలో సేవ్ అయ్యాయి." },
  resume: { en: "Resume with Passport code", hi: "पासपोर्ट कोड से फिर शुरू करें", te: "పాస్‌పోర్ట్ కోడ్‌తో కొనసాగించండి" },
  passportCode: { en: "Passport code", hi: "पासपोर्ट कोड", te: "పాస్‌పోర్ట్ కోడ్" },
  pin: { en: "PIN", hi: "पिन", te: "పిన్" },
  open: { en: "Open", hi: "खोलें", te: "తెరవండి" },
  signInEmail: { en: "Already saved? Sign in with your email", hi: "पहले सहेजा है? अपने ईमेल से साइन इन करें", te: "ఇప్పటికే సేవ్ చేశారా? మీ ఈమెయిల్‌తో సైన్ ఇన్ చేయండి" },
  signOut: { en: "Sign out", hi: "साइन आउट", te: "సైన్ అవుట్" },
  savedProfile: { en: "Saved details", hi: "सहेजी गई जानकारी", te: "సేవ్ చేసిన వివరాలు" },
  reconfirm: { en: "Older than 90 days — confirm again", hi: "90 दिन से पुराना — फिर से पुष्टि करें", te: "90 రోజుల కంటే పాతది — మళ్ళీ నిర్ధారించండి" },
  history: { en: "Passport history", hi: "पासपोर्ट इतिहास", te: "పాస్‌పోర్ట్ చరిత్ర" },
  whatChangedSince: { en: "What changed since", hi: "तब से क्या बदला", te: "అప్పటి నుండి ఏమి మారింది" },
  noChanges: { en: "No results changed.", hi: "कोई परिणाम नहीं बदला।", te: "ఏ ఫలితమూ మారలేదు." },
  factChanged: { en: "your detail changed", hi: "आपकी जानकारी बदली", te: "మీ వివరం మారింది" },
  ruleChanged: { en: "the scheme rule was updated", hi: "योजना का नियम बदला गया", te: "పథకం నియమం నవీకరించబడింది" },
  documentChanged: { en: "a document status changed", hi: "एक दस्तावेज़ की स्थिति बदली", te: "ఒక పత్రం స్థితి మారింది" },
  attachCode: { en: "Add a Passport code to this account", hi: "इस खाते में पासपोर्ट कोड जोड़ें", te: "ఈ ఖాతాకు పాస్‌పోర్ట్ కోడ్ జోడించండి" },
  deleteAccount: { en: "Delete my account and data", hi: "मेरा खाता और डेटा मिटाएँ", te: "నా ఖాతా మరియు డేటాను తొలగించండి" },
  deleteConfirm: {
    en: "This deletes your details, every saved passport and your sign-in. Cases you already sent to a reviewer stay with the reviewer. Type DELETE to confirm.",
    hi: "इससे आपकी जानकारी, हर सहेजा पासपोर्ट और आपका साइन-इन मिट जाएगा। समीक्षक को भेजे गए केस समीक्षक के पास रहेंगे। पुष्टि के लिए DELETE लिखें।",
    te: "ఇది మీ వివరాలు, సేవ్ చేసిన ప్రతి పాస్‌పోర్ట్ మరియు మీ సైన్-ఇన్‌ను తొలగిస్తుంది. సమీక్షకునికి పంపిన కేసులు సమీక్షకుని వద్దే ఉంటాయి. నిర్ధారించడానికి DELETE అని టైప్ చేయండి.",
  },
  deleted: { en: "Your account and data were deleted.", hi: "आपका खाता और डेटा मिटा दिया गया।", te: "మీ ఖాతా మరియు డేటా తొలగించబడ్డాయి." },
  stillThere: { en: "Still there?", hi: "क्या आप अभी भी यहाँ हैं?", te: "ఇంకా ఉన్నారా?" },
  stillThereBody: {
    en: "This session will end and your answers will be cleared in",
    hi: "यह सत्र समाप्त होगा और आपके जवाब मिटा दिए जाएँगे —",
    te: "ఈ సెషన్ ముగుస్తుంది, మీ సమాధానాలు తొలగించబడతాయి —",
  },
  imHere: { en: "I'm still here", hi: "मैं यहाँ हूँ", te: "నేను ఇక్కడే ఉన్నాను" },
  uploadDoc: { en: "Upload a photo or PDF", hi: "फ़ोटो या PDF अपलोड करें", te: "ఫోటో లేదా PDF అప్‌లోడ్ చేయండి" },
  maskedAadhaar: {
    en: "Upload a masked Aadhaar — only the last 4 digits visible.",
    hi: "मास्क्ड आधार अपलोड करें — केवल आख़िरी 4 अंक दिखें।",
    te: "మాస్క్ చేసిన ఆధార్ అప్‌లోడ్ చేయండి — చివరి 4 అంకెలు మాత్రమే కనిపించాలి.",
  },
  uploadConsent: {
    en: "I agree to upload this document so a reviewer can check it. It is not read by any AI and is deleted with my data.",
    hi: "मैं यह दस्तावेज़ अपलोड करने के लिए सहमत हूँ ताकि समीक्षक इसे जाँच सके। इसे कोई AI नहीं पढ़ता और यह मेरे डेटा के साथ मिटा दिया जाता है।",
    te: "సమీక్షకుడు తనిఖీ చేయడానికి ఈ పత్రాన్ని అప్‌లోడ్ చేయడానికి అంగీకరిస్తున్నాను. దీన్ని ఏ AI చదవదు, నా డేటాతో పాటు తొలగించబడుతుంది.",
  },
  uploadTypes: { en: "JPEG, PNG or PDF, up to 5 MB", hi: "JPEG, PNG या PDF, अधिकतम 5 MB", te: "JPEG, PNG లేదా PDF, గరిష్ఠంగా 5 MB" },
  uploading: { en: "Uploading", hi: "अपलोड हो रहा है", te: "అప్‌లోడ్ అవుతోంది" },
  notVerifiedYet: { en: "Uploaded — not verified yet", hi: "अपलोड हुआ — अभी सत्यापित नहीं", te: "అప్‌లోడ్ అయింది — ఇంకా ధృవీకరించలేదు" },
  viewDoc: { en: "View", hi: "देखें", te: "చూడండి" },
  fileTypeBad: { en: "Choose a JPEG, PNG or PDF file.", hi: "JPEG, PNG या PDF फ़ाइल चुनें।", te: "JPEG, PNG లేదా PDF ఫైల్ ఎంచుకోండి." },
  fileTooLarge: { en: "The file is larger than 5 MB.", hi: "फ़ाइल 5 MB से बड़ी है।", te: "ఫైల్ 5 MB కంటే పెద్దది." },
  uploadNeedsCase: {
    en: "At a kiosk, documents can be uploaded after the draft is sent to a reviewer.",
    hi: "कियोस्क पर, ड्राफ़्ट समीक्षक को भेजने के बाद दस्तावेज़ अपलोड किए जा सकते हैं।",
    te: "కియోస్క్‌లో, డ్రాఫ్ట్‌ను సమీక్షకునికి పంపిన తర్వాత పత్రాలు అప్‌లోడ్ చేయవచ్చు.",
  },
  uploadCaseClosed: { en: "This case has been reviewed; no more uploads.", hi: "इस केस की समीक्षा हो चुकी है; अब अपलोड नहीं।", te: "ఈ కేసు సమీక్ష పూర్తయింది; ఇక అప్‌లోడ్‌లు లేవు." },
  privacyTitle: { en: "Privacy and retention", hi: "गोपनीयता और डेटा रखने की अवधि", te: "గోప్యత మరియు డేటా నిల్వ కాలం" },
} as const;

export type Key = keyof typeof S;

/** The retention policy, shown wherever something can be saved. */
export function retentionText(lang: Lang, r: { unsaved_hours: number; passport_days: number; stale_fact_days: number }): string {
  const { unsaved_hours: h, passport_days: d, stale_fact_days: s } = r;
  return {
    en: `Unsaved answers are deleted ${h} hours after the session starts (kiosk sessions as soon as they end). Saved passports are deleted after ${d} days without use. Saved age and income older than ${s} days must be confirmed again. You can delete your account and data at any time; only cases you chose to send to a reviewer are kept.`,
    hi: `बिना सहेजे जवाब सत्र शुरू होने के ${h} घंटे बाद मिटा दिए जाते हैं (कियोस्क सत्र समाप्त होते ही)। सहेजे गए पासपोर्ट ${d} दिन तक उपयोग न होने पर मिटा दिए जाते हैं। ${s} दिन से पुरानी सहेजी उम्र और आय की फिर से पुष्टि करनी होगी। आप कभी भी अपना खाता और डेटा मिटा सकते हैं; केवल वे केस रखे जाते हैं जिन्हें आपने समीक्षक को भेजा।`,
    te: `సేవ్ చేయని సమాధానాలు సెషన్ ప్రారంభమైన ${h} గంటల తర్వాత తొలగించబడతాయి (కియోస్క్ సెషన్‌లు ముగిసిన వెంటనే). సేవ్ చేసిన పాస్‌పోర్ట్‌లు ${d} రోజులు ఉపయోగించకపోతే తొలగించబడతాయి. ${s} రోజుల కంటే పాత సేవ్ చేసిన వయస్సు, ఆదాయాన్ని మళ్ళీ నిర్ధారించాలి. మీరు ఎప్పుడైనా మీ ఖాతా మరియు డేటాను తొలగించవచ్చు; మీరు సమీక్షకునికి పంపిన కేసులు మాత్రమే ఉంచబడతాయి.`,
  }[lang];
}
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
