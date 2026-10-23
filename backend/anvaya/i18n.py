"""Localized strings for server-generated text (questions, summaries, document guide).

Canonical values (numbers, state names, enum codes) are never translated in storage;
only these display strings vary by language.
"""

SUPPORTED_LANGUAGES = ("en", "hi", "te")

DOCUMENTS = {
    "aadhaar": {
        "en": ("Aadhaar card", "Identity proof used by most schemes."),
        "hi": ("आधार कार्ड", "ज़्यादातर योजनाओं में पहचान के प्रमाण के रूप में।"),
        "te": ("ఆధార్ కార్డు", "చాలా పథకాలకు గుర్తింపు రుజువు."),
    },
    "age_proof": {
        "en": ("Proof of age", "Birth certificate, school certificate or other age record."),
        "hi": ("आयु का प्रमाण", "जन्म प्रमाणपत्र, स्कूल प्रमाणपत्र या अन्य आयु रिकॉर्ड।"),
        "te": ("వయస్సు రుజువు", "జనన ధృవీకరణ పత్రం, పాఠశాల సర్టిఫికేట్ లేదా ఇతర వయస్సు రికార్డు."),
    },
    "bpl_card": {
        "en": ("BPL / ration card", "Shows the household is listed as Below Poverty Line."),
        "hi": ("बीपीएल / राशन कार्ड", "दिखाता है कि परिवार गरीबी रेखा से नीचे सूचीबद्ध है।"),
        "te": ("బీపీఎల్ / రేషన్ కార్డు", "కుటుంబం దారిద్య్ర రేఖకు దిగువన ఉందని చూపిస్తుంది."),
    },
    "bank_passbook": {
        "en": ("Bank passbook / account details", "Benefits are paid by direct bank transfer."),
        "hi": ("बैंक पासबुक / खाता विवरण", "लाभ सीधे बैंक खाते में भेजा जाता है।"),
        "te": ("బ్యాంక్ పాస్‌బుక్ / ఖాతా వివరాలు", "ప్రయోజనాలు నేరుగా బ్యాంక్ ఖాతాకు జమ అవుతాయి."),
    },
    "residence_proof": {
        "en": ("Residence / domicile proof", "Shows you live in the state that runs the scheme."),
        "hi": ("निवास / अधिवास प्रमाण", "दिखाता है कि आप योजना वाले राज्य में रहते हैं।"),
        "te": ("నివాస రుజువు", "పథకం అమలు చేసే రాష్ట్రంలో మీరు నివసిస్తున్నారని చూపిస్తుంది."),
    },
    "photo": {
        "en": ("Passport-size photograph", "Attached to the application form."),
        "hi": ("पासपोर्ट साइज़ फोटो", "आवेदन पत्र के साथ लगाई जाती है।"),
        "te": ("పాస్‌పోర్ట్ సైజు ఫోటో", "దరఖాస్తు ఫారంతో జతచేయాలి."),
    },
    "land_records": {
        "en": ("Land-holding papers", "Shows cultivable land is held in your name."),
        "hi": ("भूमि के कागज़ात", "दिखाता है कि खेती योग्य ज़मीन आपके नाम पर है।"),
        "te": ("భూమి పత్రాలు", "సాగు భూమి మీ పేరు మీద ఉందని చూపిస్తుంది."),
    },
    "pattadar_passbook": {
        "en": ("Pattadar Pass Book (PPB)", "Telangana land-ownership record."),
        "hi": ("पट्टादार पासबुक (PPB)", "तेलंगाना भूमि स्वामित्व रिकॉर्ड।"),
        "te": ("పట్టాదారు పాస్ పుస్తకం (PPB)", "తెలంగాణ భూ యాజమాన్య రికార్డు."),
    },
    "spouse_death_certificate": {
        "en": ("Husband's death certificate", "Supports the widow-status criterion."),
        "hi": ("पति का मृत्यु प्रमाणपत्र", "विधवा होने की शर्त का समर्थन करता है।"),
        "te": ("భర్త మరణ ధృవీకరణ పత్రం", "వితంతువు అనే అర్హతకు ఆధారం."),
    },
    "income_certificate": {
        "en": ("Income certificate / self-declaration", "Supports the household income criterion."),
        "hi": ("आय प्रमाणपत्र / स्व-घोषणा", "परिवार की आय की शर्त का समर्थन करता है।"),
        "te": ("ఆదాయ ధృవీకరణ పత్రం / స్వీయ ప్రకటన", "కుటుంబ ఆదాయ అర్హతకు ఆధారం."),
    },
    "no_pension_affidavit": {
        "en": ("Declaration of no other pension", "States you do not receive another pension."),
        "hi": ("अन्य पेंशन न होने की घोषणा", "बताती है कि आपको कोई अन्य पेंशन नहीं मिलती।"),
        "te": ("ఇతర పెన్షన్ లేదని ప్రకటన", "మీకు వేరే పెన్షన్ రావడం లేదని తెలియజేస్తుంది."),
    },
    "ration_card": {
        "en": ("Ration card", "Household composition and address."),
        "hi": ("राशन कार्ड", "परिवार की संरचना और पता।"),
        "te": ("రేషన్ కార్డు", "కుటుంబ సభ్యులు మరియు చిరునామా."),
    },
}

DOC_STATUS = {
    "available": {"en": "I have it", "hi": "मेरे पास है", "te": "నా దగ్గర ఉంది"},
    "missing": {"en": "Missing", "hi": "नहीं है", "te": "లేదు"},
    "expired": {"en": "Expired", "hi": "समाप्त", "te": "గడువు ముగిసింది"},
    "unknown": {"en": "Not sure", "hi": "पता नहीं", "te": "తెలియదు"},
    "verified": {"en": "Verified by reviewer", "hi": "समीक्षक द्वारा सत्यापित", "te": "సమీక్షకుడు ధృవీకరించారు"},
}

OUTCOMES = {
    "MATCH": {"en": "Likely eligible", "hi": "संभवतः पात्र", "te": "అర్హత ఉండే అవకాశం"},
    "PROVISIONAL": {"en": "Provisional match", "hi": "अस्थायी मिलान", "te": "తాత్కాలిక సరిపోలిక"},
    "MISMATCH": {"en": "Does not match", "hi": "मेल नहीं खाता", "te": "సరిపోలలేదు"},
    "INSUFFICIENT_INFORMATION": {"en": "Need more information", "hi": "और जानकारी चाहिए", "te": "మరింత సమాచారం కావాలి"},
    "NEEDS_HUMAN_REVIEW": {"en": "Needs human review", "hi": "मानव समीक्षा आवश्यक", "te": "మానవ సమీక్ష అవసరం"},
}

# Questions asked when an attribute needed by a candidate rule is unknown.
QUESTIONS = {
    "state": {
        "en": "Which state do you live in?",
        "hi": "आप किस राज्य में रहते हैं?",
        "te": "మీరు ఏ రాష్ట్రంలో నివసిస్తున్నారు?",
    },
    "age": {
        "en": "How old are you (the applicant)?",
        "hi": "आवेदक की उम्र कितनी है?",
        "te": "దరఖాస్తుదారుని వయస్సు ఎంత?",
    },
    "annual_income": {
        "en": "What is your household's total yearly income in rupees?",
        "hi": "आपके परिवार की कुल सालाना आय कितने रुपये है?",
        "te": "మీ కుటుంబ మొత్తం వార్షిక ఆదాయం ఎన్ని రూపాయలు?",
    },
    "household_size": {
        "en": "How many people live in your household?",
        "hi": "आपके परिवार में कितने लोग रहते हैं?",
        "te": "మీ కుటుంబంలో ఎంత మంది ఉంటారు?",
    },
    "bpl": {
        "en": "Does your household have a BPL (Below Poverty Line) card?",
        "hi": "क्या आपके परिवार के पास बीपीएल (गरीबी रेखा) कार्ड है?",
        "te": "మీ కుటుంబానికి బీపీఎల్ (దారిద్య్ర రేఖ) కార్డు ఉందా?",
    },
    "gender": {
        "en": "Is the applicant a woman or a man?",
        "hi": "आवेदक महिला हैं या पुरुष?",
        "te": "దరఖాస్తుదారు స్త్రీయా లేక పురుషుడా?",
    },
    "area": {
        "en": "Do you live in a village (rural) or a town/city (urban)?",
        "hi": "आप गाँव में रहते हैं या शहर में?",
        "te": "మీరు గ్రామంలో ఉంటారా లేక పట్టణం/నగరంలోనా?",
    },
    "occupation": {
        "en": "What work does the applicant do (for example farmer, labourer, weaver)?",
        "hi": "आवेदक क्या काम करते हैं (जैसे किसान, मज़दूर, बुनकर)?",
        "te": "దరఖాస్తుదారు ఏ పని చేస్తారు (ఉదా: రైతు, కూలీ, నేత కార్మికుడు)?",
    },
    "marital_status": {
        "en": "What is the applicant's marital status (married, widowed, single)?",
        "hi": "आवेदक की वैवाहिक स्थिति क्या है (विवाहित, विधवा, अविवाहित)?",
        "te": "దరఖాస్తుదారుని వైవాహిక స్థితి ఏమిటి (వివాహిత, వితంతువు, అవివాహిత)?",
    },
    "receives_other_pension": {
        "en": "Does the applicant already receive any pension?",
        "hi": "क्या आवेदक को पहले से कोई पेंशन मिलती है?",
        "te": "దరఖాస్తుదారుకు ఇప్పటికే ఏదైనా పెన్షన్ వస్తుందా?",
    },
    "owns_cultivable_land": {
        "en": "Does the applicant own cultivable land in their own name?",
        "hi": "क्या आवेदक के नाम पर खेती योग्य ज़मीन है?",
        "te": "దరఖాస్తుదారుని పేరు మీద సాగు భూమి ఉందా?",
    },
    "has_bank_account": {
        "en": "Does the applicant have a bank or post-office savings account?",
        "hi": "क्या आवेदक का बैंक या डाकघर बचत खाता है?",
        "te": "దరఖాస్తుదారుకు బ్యాంక్ లేదా పోస్టాఫీస్ పొదుపు ఖాతా ఉందా?",
    },
    "owns_pucca_house": {
        "en": "Does the family already own a pucca (permanent) house anywhere?",
        "hi": "क्या परिवार के पास कहीं पक्का मकान है?",
        "te": "కుటుంబానికి ఎక్కడైనా పక్కా ఇల్లు ఉందా?",
    },
}

ATTRIBUTE_LABELS = {
    "state": {"en": "State", "hi": "राज्य", "te": "రాష్ట్రం"},
    "district": {"en": "District", "hi": "ज़िला", "te": "జిల్లా"},
    "age": {"en": "Age", "hi": "उम्र", "te": "వయస్సు"},
    "annual_income": {"en": "Yearly household income (₹)", "hi": "सालाना पारिवारिक आय (₹)", "te": "వార్షిక కుటుంబ ఆదాయం (₹)"},
    "household_size": {"en": "Household members", "hi": "परिवार के सदस्य", "te": "కుటుంబ సభ్యులు"},
    "gender": {"en": "Gender", "hi": "लिंग", "te": "లింగం"},
    "area": {"en": "Rural / urban", "hi": "ग्रामीण / शहरी", "te": "గ్రామీణ / పట్టణ"},
    "occupation": {"en": "Occupation", "hi": "व्यवसाय", "te": "వృత్తి"},
    "marital_status": {"en": "Marital status", "hi": "वैवाहिक स्थिति", "te": "వైవాహిక స్థితి"},
    "bpl": {"en": "BPL household", "hi": "बीपीएल परिवार", "te": "బీపీఎల్ కుటుంబం"},
    "receives_other_pension": {"en": "Receives another pension", "hi": "अन्य पेंशन मिलती है", "te": "వేరే పెన్షన్ వస్తుంది"},
    "owns_cultivable_land": {"en": "Owns cultivable land", "hi": "खेती योग्य ज़मीन है", "te": "సాగు భూమి ఉంది"},
    "has_bank_account": {"en": "Has bank account", "hi": "बैंक खाता है", "te": "బ్యాంక్ ఖాతా ఉంది"},
    "owns_pucca_house": {"en": "Owns pucca house", "hi": "पक्का मकान है", "te": "పక్కా ఇల్లు ఉంది"},
    "applicant_name": {"en": "Applicant name", "hi": "आवेदक का नाम", "te": "దరఖాస్తుదారుని పేరు"},
}

MESSAGES = {
    "greeting": {
        "en": "Namaste! Tell me about your household — your state, age, income and work. You can speak or type.",
        "hi": "नमस्ते! अपने परिवार के बारे में बताइए — राज्य, उम्र, आय और काम। आप बोल या लिख सकते हैं।",
        "te": "నమస్తే! మీ కుటుంబం గురించి చెప్పండి — రాష్ట్రం, వయస్సు, ఆదాయం మరియు పని. మీరు మాట్లాడవచ్చు లేదా టైప్ చేయవచ్చు.",
    },
    "heard": {"en": "I understood:", "hi": "मैंने समझा:", "te": "నేను అర్థం చేసుకున్నది:"},
    "nothing_heard": {
        "en": "I could not pick out any details. Could you say it another way?",
        "hi": "मुझे कोई जानकारी समझ नहीं आई। क्या आप दूसरे तरीके से बता सकते हैं?",
        "te": "నాకు ఏ వివరాలూ అర్థం కాలేదు. వేరే విధంగా చెప్పగలరా?",
    },
    "please_confirm": {
        "en": "Please check these on the profile card and confirm or correct them before I look for schemes.",
        "hi": "योजनाएँ खोजने से पहले कृपया प्रोफ़ाइल कार्ड पर इन्हें जाँचें और पुष्टि करें या सुधारें।",
        "te": "పథకాలు వెతకడానికి ముందు దయచేసి ప్రొఫైల్ కార్డులో వీటిని తనిఖీ చేసి నిర్ధారించండి లేదా సరిచేయండి.",
    },
    "ready": {
        "en": "Thank you. Your details are confirmed — you can now check schemes.",
        "hi": "धन्यवाद। आपकी जानकारी की पुष्टि हो गई है — अब आप योजनाएँ देख सकते हैं।",
        "te": "ధన్యవాదాలు. మీ వివరాలు నిర్ధారించబడ్డాయి — ఇప్పుడు మీరు పథకాలు చూడవచ్చు.",
    },
    "relative_age_ignored": {
        "en": "I heard an age for your {relation} ({age}); I did not use it as your own age.",
        "hi": "मैंने आपके {relation} की उम्र ({age}) सुनी; इसे आपकी अपनी उम्र नहीं माना।",
        "te": "మీ {relation} వయస్సు ({age}) విన్నాను; దాన్ని మీ స్వంత వయస్సుగా తీసుకోలేదు.",
    },
    "confusable_number": {
        "en": "Please check the number {value}: I heard “{words}”, which can sound like “{alt}”.",
        "hi": "कृपया संख्या {value} जाँचें: मैंने “{words}” सुना, जो “{alt}” जैसा सुनाई दे सकता है।",
        "te": "దయచేసి సంఖ్య {value} సరిచూడండి: నేను “{words}” విన్నాను, ఇది “{alt}” లాగా వినిపించవచ్చు.",
    },
    "summary_intro": {
        "en": "Here is what I found. These are preliminary results, not an approval.",
        "hi": "मुझे यह मिला। ये प्रारंभिक परिणाम हैं, स्वीकृति नहीं।",
        "te": "నేను కనుగొన్నది ఇదీ. ఇవి ప్రాథమిక ఫలితాలు, ఆమోదం కాదు.",
    },
    "summary_count": {
        "en": "{n} schemes may suit you provisionally, {m} need more information.",
        "hi": "{n} योजनाएँ अस्थायी रूप से उपयुक्त हो सकती हैं, {m} के लिए और जानकारी चाहिए।",
        "te": "{n} పథకాలు తాత్కాలికంగా మీకు సరిపోవచ్చు, {m} పథకాలకు మరింత సమాచారం కావాలి.",
    },
    "summary_missing_docs": {
        "en": "Missing documents: {docs}.",
        "hi": "जो दस्तावेज़ नहीं हैं: {docs}।",
        "te": "లేని పత్రాలు: {docs}.",
    },
    "summary_scheme": {"en": "{name}: {outcome}.", "hi": "{name}: {outcome}।", "te": "{name}: {outcome}."},
    "status_line": {
        "en": "Your case status is: {status}. Updated {ts}.",
        "hi": "आपके केस की स्थिति: {status}। अपडेट {ts}।",
        "te": "మీ కేసు స్థితి: {status}. నవీకరణ {ts}.",
    },
}

CASE_STATUS = {
    "DRAFT_SAVED": {"en": "Draft saved (not submitted to government)", "hi": "ड्राफ़्ट सहेजा गया (सरकार को जमा नहीं)", "te": "డ్రాఫ్ట్ సేవ్ అయింది (ప్రభుత్వానికి సమర్పించలేదు)"},
    "PENDING_REVIEW": {"en": "Waiting for reviewer", "hi": "समीक्षक की प्रतीक्षा में", "te": "సమీక్షకుని కోసం వేచి ఉంది"},
    "CORRECTION_REQUESTED": {"en": "Reviewer asked for a correction", "hi": "समीक्षक ने सुधार माँगा है", "te": "సమీక్షకుడు సవరణ కోరారు"},
    "REVIEWED": {"en": "Reviewed by reviewer", "hi": "समीक्षक द्वारा समीक्षा की गई", "te": "సమీక్షకుడు సమీక్షించారు"},
    "SYNCED": {"en": "Synced from kiosk", "hi": "कियोस्क से सिंक हुआ", "te": "కియోస్క్ నుండి సింక్ అయింది"},
}


def t(table: dict, key: str, lang: str, **kw) -> str:
    entry = table.get(key, {})
    s = entry.get(lang) or entry.get("en") or key
    return s.format(**kw) if kw else s


def doc_label(doc_key: str, lang: str) -> tuple[str, str]:
    entry = DOCUMENTS.get(doc_key)
    if not entry:
        return doc_key, ""
    return entry.get(lang) or entry["en"]
