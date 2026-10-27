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
    "uploaded": {"en": "Uploaded — not verified yet", "hi": "अपलोड हुआ — अभी सत्यापित नहीं", "te": "అప్‌లోడ్ అయింది — ఇంకా ధృవీకరించలేదు"},
    "verified": {"en": "Verified by reviewer", "hi": "समीक्षक द्वारा सत्यापित", "te": "సమీక్షకుడు ధృవీకరించారు"},
    "reupload_requested": {"en": "Reviewer asked for a new upload", "hi": "समीक्षक ने दोबारा अपलोड माँगा", "te": "సమీక్షకుడు మళ్ళీ అప్‌లోడ్ అడిగారు"},
}

OUTCOMES = {
    "MATCH": {"en": "Potential match", "hi": "संभावित मिलान", "te": "సంభావ్య సరిపోలిక"},
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
    "date_of_birth": {"en": "Date of birth", "hi": "जन्मतिथि", "te": "పుట్టిన తేదీ"},
}

# Why each question is asked (answer to "why do you need to know?"); the reason only, never a promise about a result.
WHY_ASK = {
    "state": {"en": 'Schemes differ from state to state, so I need your state to look at the right list.', "hi": 'योजनाएँ राज्य के हिसाब से अलग होती हैं, इसलिए सही सूची देखने के लिए राज्य जानना ज़रूरी है।', "te": 'పథకాలు రాష్ట్రాన్ని బట్టి మారుతాయి, అందుకే సరైన జాబితా చూడటానికి మీ రాష్ట్రం కావాలి.'},
    "age": {"en": 'Many schemes depend on age, for example pensions.', "hi": 'कई योजनाएँ उम्र पर निर्भर करती हैं, जैसे पेंशन।', "te": 'చాలా పథకాలు వయస్సుపై ఆధారపడతాయి, ఉదాహరణకు పెన్షన్లు.'},
    "annual_income": {"en": 'Several schemes have a household income limit.', "hi": 'कई योजनाओं में परिवार की आय की सीमा होती है।', "te": 'చాలా పథకాలకు కుటుంబ ఆదాయ పరిమితి ఉంటుంది.'},
    "household_size": {"en": 'Some schemes look at how many people share the household.', "hi": 'कुछ योजनाएँ देखती हैं कि घर में कितने लोग हैं।', "te": 'కొన్ని పథకాలు ఇంట్లో ఎంతమంది ఉన్నారో చూస్తాయి.'},
    "bpl": {"en": 'Some schemes are only for households with a BPL card.', "hi": 'कुछ योजनाएँ केवल बीपीएल कार्ड वाले परिवारों के लिए हैं।', "te": 'కొన్ని పథకాలు బీపీఎల్ కార్డు ఉన్న కుటుంబాలకే ఉంటాయి.'},
    "area": {"en": 'A few schemes are only for rural or only for urban households.', "hi": 'कुछ योजनाएँ केवल गाँव या केवल शहर के परिवारों के लिए हैं।', "te": 'కొన్ని పథకాలు గ్రామీణ లేదా పట్టణ కుటుంబాలకే ఉంటాయి.'},
    "gender": {"en": 'Some schemes are meant for women or for men.', "hi": 'कुछ योजनाएँ महिलाओं या पुरुषों के लिए होती हैं।', "te": 'కొన్ని పథకాలు మహిళలకు లేదా పురుషులకు ఉద్దేశించినవి.'},
    "marital_status": {"en": 'Widow and similar schemes depend on marital status.', "hi": 'विधवा जैसी योजनाएँ वैवाहिक स्थिति पर निर्भर करती हैं।', "te": 'వితంతు వంటి పథకాలు వైవాహిక స్థితిపై ఆధారపడతాయి.'},
    "occupation": {"en": 'Some schemes are for farmers, workers or other occupations.', "hi": 'कुछ योजनाएँ किसानों, मज़दूरों या अन्य पेशों के लिए हैं।', "te": 'కొన్ని పథకాలు రైతులు, కార్మికులు లేదా ఇతర వృత్తుల వారికి ఉంటాయి.'},
    "receives_other_pension": {"en": 'Two pensions are usually not paid together, so I need to know.', "hi": 'आमतौर पर दो पेंशन एक साथ नहीं मिलतीं, इसलिए यह जानना ज़रूरी है।', "te": 'సాధారణంగా రెండు పెన్షన్లు ఒకేసారి రావు, అందుకే తెలుసుకోవాలి.'},
    "owns_cultivable_land": {"en": 'Farming schemes depend on the land you hold.', "hi": 'खेती की योजनाएँ आपकी ज़मीन पर निर्भर करती हैं।', "te": 'వ్యవసాయ పథకాలు మీ భూమిపై ఆధారపడతాయి.'},
    "has_bank_account": {"en": 'Most benefits are paid into a bank account.', "hi": 'ज़्यादातर लाभ बैंक खाते में आते हैं।', "te": 'చాలా లాభాలు బ్యాంక్ ఖాతాలోకి వస్తాయి.'},
    "owns_pucca_house": {"en": 'Housing schemes look at the kind of house you have.', "hi": 'आवास योजनाएँ घर के प्रकार को देखती हैं।', "te": 'గృహ పథకాలు మీ ఇంటి రకాన్ని చూస్తాయి.'},
    "_default": {"en": 'It helps me match you to the right schemes.', "hi": 'इससे मुझे सही योजनाओं से मिलान करने में मदद मिलती है।', "te": 'సరైన పథకాలతో సరిపోల్చడానికి ఇది నాకు సహాయపడుతుంది.'},
}

MESSAGES = {
    "greeting": {
        "en": "Namaste! Tell me about your household — your state, age, income and work. You can speak or type.",
        "hi": "नमस्ते! अपने परिवार के बारे में बताइए — राज्य, उम्र, आय और काम। आप बोल या लिख सकते हैं।",
        "te": "నమస్తే! మీ కుటుంబం గురించి చెప్పండి — రాష్ట్రం, వయస్సు, ఆదాయం మరియు పని. మీరు మాట్లాడవచ్చు లేదా టైప్ చేయవచ్చు.",
    },
    "passport_code_is": {"en": "Your Passport code is", "hi": "आपका पासपोर्ट कोड है", "te": "మీ పాస్‌పోర్ట్ కోడ్"},
    "passport_code_notice": {
        "en": "Write down this code and remember your PIN. Together they open your saved passport; staff never need them.",
        "hi": "यह कोड लिख लें और अपना पिन याद रखें। दोनों से आपका सहेजा पासपोर्ट खुलता है; कर्मचारियों को इनकी ज़रूरत नहीं होती।",
        "te": "ఈ కోడ్‌ను రాసుకోండి, మీ పిన్ గుర్తుంచుకోండి. రెండూ కలిసి మీ సేవ్ చేసిన పాస్‌పోర్ట్‌ను తెరుస్తాయి; సిబ్బందికి ఇవి అవసరం లేదు.",
    },
    "heard": {"en": "I understood:", "hi": "मैंने समझा:", "te": "నేను అర్థం చేసుకున్నది:"},
    "nothing_heard": {
        "en": "I could not pick out any details. Could you say it another way?",
        "hi": "मुझे कोई जानकारी समझ नहीं आई। क्या आप दूसरे तरीके से बता सकते हैं?",
        "te": "నాకు ఏ వివరాలూ అర్థం కాలేదు. వేరే విధంగా చెప్పగలరా?",
    },
    "why_tail": {
        "en": "You can say “skip” if you'd rather not answer.",
        "hi": "अगर नहीं बताना चाहते तो “छोड़ो” कह दीजिए।",
        "te": "చెప్పకూడదనుకుంటే “వదిలేయండి” అనండి.",
    },
    "skip_ok": {"en": "Okay, I'll skip that.", "hi": "ठीक है, इसे छोड़ देते हैं।", "te": "సరే, దీన్ని వదిలేద్దాం."},
    "guard_decline": {
        "en": "That's fine. You don't have to share anything you don't want to. I can check schemes with what you've told me; some may need more details.",
        "hi": "कोई बात नहीं। जो आप नहीं बताना चाहते, वह बताना ज़रूरी नहीं है। जो जानकारी दी है उसी से मैं योजनाएँ देख सकता हूँ; कुछ के लिए और जानकारी चाहिए होगी।",
        "te": "పర్వాలేదు. మీకు ఇష్టం లేనివి చెప్పాల్సిన అవసరం లేదు. ఇప్పటివరకు చెప్పిన వివరాలతో నేను పథకాలు చూడగలను; కొన్నిటికి మరిన్ని వివరాలు అవసరం కావచ్చు.",
    },
    "quiet_hint": {
        "en": "Tell me more any time, or check schemes now.",
        "hi": "जब चाहें और बताइए, या अभी योजनाएँ देखिए।",
        "te": "ఎప్పుడైనా మరింత చెప్పండి, లేదా ఇప్పుడే పథకాలు చూడండి.",
    },
    "guard_schemes": {
        "en": "I'll check which schemes may suit you as soon as these details are confirmed.",
        "hi": "जैसे ही ये जानकारी पक्की हो जाएगी, मैं देखूँगा कि कौन-सी योजनाएँ आपके लिए उपयुक्त हो सकती हैं।",
        "te": "ఈ వివరాలు నిర్ధారించబడగానే మీకు సరిపోయే పథకాలను చూస్తాను.",
    },
    "guard_login": {
        "en": "You don't need to log in or have an account to check schemes. Just tell me about your household. If you want to save your passport for later, you can sign in at the end.",
        "hi": "योजनाएँ देखने के लिए लॉग इन या खाते की ज़रूरत नहीं है। बस अपने परिवार के बारे में बताइए। बाद के लिए पासपोर्ट सहेजना हो तो अंत में साइन इन कर सकते हैं।",
        "te": "పథకాలు చూడటానికి లాగిన్ లేదా ఖాతా అవసరం లేదు. మీ కుటుంబం గురించి చెప్పండి. తరువాత కోసం పాస్‌పోర్ట్ సేవ్ చేయాలంటే చివర్లో సైన్ ఇన్ చేయవచ్చు.",
    },
    "nothing_heard_tips": {
        "en": "I'm still not catching that. Please say one detail at a time, like “Bihar” or “I am 60 years old”, or type it instead.",
        "hi": "मैं अभी भी समझ नहीं पा रहा हूँ। कृपया एक-एक जानकारी बताइए, जैसे “बिहार” या “मेरी उम्र 60 साल है”, या लिखकर बताइए।",
        "te": "నాకు ఇంకా అర్థం కావడం లేదు. దయచేసి ఒక్కో వివరాన్ని చెప్పండి, ఉదా. “బీహార్” లేదా “నా వయస్సు 60 సంవత్సరాలు”, లేదా టైప్ చేయండి.",
    },
    "guard_abuse": {
        "en": "I can't help with that kind of language. I'm here to find government schemes for your family — please tell me about your household.",
        "hi": "इस तरह की भाषा में मैं मदद नहीं कर सकता। मैं आपके परिवार के लिए सरकारी योजनाएँ खोजने के लिए हूँ — कृपया अपने परिवार के बारे में बताइए।",
        "te": "ఇలాంటి భాషలో నేను సహాయం చేయలేను. మీ కుటుంబానికి ప్రభుత్వ పథకాలు కనుగొనడానికి నేను ఇక్కడ ఉన్నాను — దయచేసి మీ కుటుంబం గురించి చెప్పండి.",
    },
    "guard_injection": {
        "en": "I can't change how I work or share my instructions, and eligibility comes only from the official rules. Tell me about your household and I'll check the schemes.",
        "hi": "मैं अपना काम करने का तरीका नहीं बदल सकता और न अपने निर्देश साझा कर सकता हूँ; योजनाओं का मिलान केवल आधिकारिक नियमों से होता है। अपने परिवार के बारे में बताइए, मैं योजनाएँ जाँचूँगा।",
        "te": "నేను నా పని విధానాన్ని మార్చలేను, నా సూచనలను పంచుకోలేను; అర్హత అధికారిక నియమాల నుండే వస్తుంది. మీ కుటుంబం గురించి చెప్పండి, నేను పథకాలను పరిశీలిస్తాను.",
    },
    "guard_sensitive": {
        "en": "Please don't type Aadhaar, card or PAN numbers, OTPs or passwords here. I don't need them, and I did not save that message.",
        "hi": "कृपया यहाँ आधार, कार्ड या पैन नंबर, ओटीपी या पासवर्ड न लिखें। मुझे इनकी ज़रूरत नहीं है, और मैंने वह संदेश सहेजा नहीं है।",
        "te": "దయచేసి ఇక్కడ ఆధార్, కార్డ్ లేదా పాన్ నంబర్లు, ఓటీపీ, పాస్‌వర్డ్‌లు టైప్ చేయవద్దు. నాకు అవి అవసరం లేదు, ఆ సందేశాన్ని నేను సేవ్ చేయలేదు.",
    },
    "guard_smalltalk": {
        "en": "Hello! I help families find government schemes they may qualify for. Tell me your state, age, income and work, and I'll do the rest.",
        "hi": "नमस्ते! मैं परिवारों को उनके लिए उपयुक्त सरकारी योजनाएँ खोजने में मदद करता हूँ। अपना राज्य, उम्र, आय और काम बताइए, बाकी मैं देख लूँगा।",
        "te": "నమస్తే! కుటుంబాలు అర్హత పొందగల ప్రభుత్వ పథకాలను కనుగొనడంలో నేను సహాయం చేస్తాను. మీ రాష్ట్రం, వయస్సు, ఆదాయం, పని చెప్పండి, మిగతాది నేను చూస్తాను.",
    },
    "guard_offtopic": {
        "en": "I can only help with finding government schemes, so I can't answer that. If you tell me about your household, I can check which schemes may fit.",
        "hi": "मैं केवल सरकारी योजनाएँ खोजने में मदद कर सकता हूँ, इसलिए इसका उत्तर नहीं दे सकता। अपने परिवार के बारे में बताइए, मैं देखूँगा कि कौन-सी योजनाएँ लागू हो सकती हैं।",
        "te": "నేను ప్రభుత్వ పథకాలను కనుగొనడంలో మాత్రమే సహాయం చేయగలను, కాబట్టి దానికి సమాధానం ఇవ్వలేను. మీ కుటుంబం గురించి చెబితే ఏ పథకాలు సరిపోతాయో చూస్తాను.",
    },
    "please_confirm": {
        "en": "Please check these on the profile card and confirm or correct them before I look for schemes.",
        "hi": "योजनाएँ खोजने से पहले कृपया प्रोफ़ाइल कार्ड पर इन्हें जाँचें और पुष्टि करें या सुधारें।",
        "te": "పథకాలు వెతకడానికి ముందు దయచేసి ప్రొఫైల్ కార్డులో వీటిని తనిఖీ చేసి నిర్ధారించండి లేదా సరిచేయండి.",
    },
    "confirm_question": {
        "en": "Is that right?",
        "hi": "क्या यह सही है?",
        "te": "ఇది సరైనదేనా?",
    },
    "okay": {"en": "Okay.", "hi": "ठीक है।", "te": "సరే."},
    "correct_it": {
        "en": "Sorry about that. What is the correct {label}?",
        "hi": "क्षमा करें। सही {label} क्या है?",
        "te": "క్షమించండి. సరైన {label} ఏమిటి?",
    },
    "answer_yes_no": {
        "en": "You can just say yes or no.",
        "hi": "आप बस हाँ या नहीं कह सकते हैं।",
        "te": "మీరు అవును లేదా కాదు అని చెప్పవచ్చు.",
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
    "disputed_value": {
        "en": "{label}: {a} or {b}? Please choose the right one.",
        "hi": "{label}: {a} या {b}? कृपया सही चुनें।",
        "te": "{label}: {a} లేదా {b}? దయచేసి సరైనది ఎంచుకోండి.",
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
    "code_is_passport": {
        "en": "That is a Passport code (PSP-…). With your PIN it reopens your saved profile on the “Resume with Passport code” page. Case status needs a case code (ANV-…), which you get when a draft is sent to a reviewer.",
        "hi": "यह पासपोर्ट कोड (PSP-…) है। पिन के साथ यह “पासपोर्ट कोड से फिर शुरू करें” पेज पर आपकी सहेजी प्रोफ़ाइल खोलता है। केस की स्थिति के लिए केस कोड (ANV-…) चाहिए, जो ड्राफ़्ट समीक्षक को भेजने पर मिलता है।",
        "te": "ఇది పాస్‌పోర్ట్ కోడ్ (PSP-…). పిన్‌తో కలిపి ఇది “పాస్‌పోర్ట్ కోడ్‌తో కొనసాగండి” పేజీలో మీ సేవ్ చేసిన ప్రొఫైల్‌ను తెరుస్తుంది. కేసు స్థితికి కేసు కోడ్ (ANV-…) కావాలి; డ్రాఫ్ట్‌ను సమీక్షకునికి పంపినప్పుడు అది వస్తుంది.",
    },
    "code_bad_format": {
        "en": "Enter a case code like ANV-XXXX-XXXX.",
        "hi": "ANV-XXXX-XXXX जैसा केस कोड लिखिए।",
        "te": "ANV-XXXX-XXXX లాంటి కేసు కోడ్ నమోదు చేయండి.",
    },
    "code_not_found": {
        "en": "No case matches this code. Check it for typing mistakes; case codes look like ANV-XXXX-XXXX.",
        "hi": "इस कोड से कोई केस नहीं मिला। टाइप की गलती जाँचें; केस कोड ANV-XXXX-XXXX जैसे होते हैं।",
        "te": "ఈ కోడ్‌కు ఏ కేసూ సరిపోలలేదు. టైపింగ్ తప్పులు చూడండి; కేసు కోడ్‌లు ANV-XXXX-XXXX లాగా ఉంటాయి.",
    },
    "status_notice": {
        "en": "Status of a draft review. No government submission has been made.",
        "hi": "यह ड्राफ़्ट समीक्षा की स्थिति है। सरकार को कोई आवेदन जमा नहीं किया गया है।",
        "te": "ఇది డ్రాఫ్ట్ సమీక్ష స్థితి. ప్రభుత్వానికి ఎలాంటి దరఖాస్తు సమర్పించలేదు.",
    },
    "status_line": {
        "en": "Your case status is: {status}. Updated {ts}.",
        "hi": "आपके केस की स्थिति: {status}। अपडेट {ts}।",
        "te": "మీ కేసు స్థితి: {status}. నవీకరణ {ts}.",
    },
}

# Reviewer outcomes as the citizen sees them (stored codes stay appears_eligible / not_eligible / needs_more_documents).
REVIEW_OUTCOMES = {
    "appears_eligible": {"en": "Reviewer found a potential match (not an approval)",
                         "hi": "समीक्षक को संभावित मिलान मिला (यह स्वीकृति नहीं है)",
                         "te": "సమీక్షకుడు సంభావ్య సరిపోలికను గుర్తించారు (ఇది ఆమోదం కాదు)"},
    "not_eligible": {"en": "Reviewer found no match", "hi": "समीक्षक को मिलान नहीं मिला",
                     "te": "సమీక్షకుడికి సరిపోలిక కనిపించలేదు"},
    "needs_more_documents": {"en": "More documents needed", "hi": "और दस्तावेज़ चाहिए", "te": "మరిన్ని పత్రాలు అవసరం"},
}

CASE_STATUS = {
    "DRAFT_SAVED": {"en": "Draft ready — submit at the office/portal", "hi": "ड्राफ़्ट तैयार — कार्यालय/पोर्टल पर जमा करें",
                    "te": "డ్రాఫ్ట్ సిద్ధం — కార్యాలయంలో/పోర్టల్‌లో సమర్పించండి"},
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
