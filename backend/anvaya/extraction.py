"""Deterministic multilingual fact extraction (English, Hindi/Hinglish, Telugu).

Produces *candidate* facts only. Every candidate carries the original span so the citizen
can see what was heard; high-impact candidates must be confirmed before rules run.
"""
import re

HIGH_IMPACT = {"age", "annual_income", "state", "household_size"}

_DIGITS = str.maketrans("०१२३४५६७८९౦౧౨౩౪౫౬౭౮౯", "01234567890123456789")

STATES = [
    "Andaman and Nicobar Islands", "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chandigarh",
    "Chhattisgarh", "Dadra & Nagar Haveli and Daman & Diu", "Delhi", "Goa", "Gujarat", "Haryana",
    "Himachal Pradesh", "Jammu and Kashmir", "Jharkhand", "Karnataka", "Kerala", "Ladakh", "Lakshadweep",
    "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram", "Nagaland", "Odisha", "Puducherry",
    "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal",
]

STATE_ALIASES = {
    "Andhra Pradesh": ["andhra pradesh", "andhra", "आंध्र प्रदेश", "आंध्रप्रदेश", "ఆంధ్ర ప్రదేశ్", "ఆంధ్రప్రదేశ్", "ఆంధ్ర"],
    "Telangana": ["telangana", "तेलंगाना", "తెలంగాణ", "తెలంగాణా"],
    "Bihar": ["bihar", "बिहार", "బీహార్"],
    "Maharashtra": ["maharashtra", "महाराष्ट्र", "మహారాష్ట్ర"],
    "Punjab": ["punjab", "पंजाब", "పంజాబ్"],
    "Tamil Nadu": ["tamil nadu", "tamilnadu", "तमिलनाडु", "तमिल नाडु", "తమిళనాడు"],
    "Uttar Pradesh": ["uttar pradesh", "उत्तर प्रदेश", "ఉత్తర ప్రదేశ్"],
    "Madhya Pradesh": ["madhya pradesh", "मध्य प्रदेश", "మధ్య ప్రదేశ్"],
    "Karnataka": ["karnataka", "कर्नाटक", "కర్ణాటక"],
    "Odisha": ["odisha", "orissa", "ओडिशा", "ఒడిశా"],
    "Rajasthan": ["rajasthan", "राजस्थान", "రాజస్థాన్"],
    "Jharkhand": ["jharkhand", "झारखंड", "జార్ఖండ్"],
    "West Bengal": ["west bengal", "पश्चिम बंगाल", "పశ్చిమ బెంగాల్"],
    "Gujarat": ["gujarat", "गुजरात", "గుజరాత్"],
    "Delhi": ["delhi", "दिल्ली", "ఢిల్లీ"],
}
for _s in STATES:
    STATE_ALIASES.setdefault(_s, [_s.lower()])

DISTRICTS = {
    "guntur": ("Guntur", "Andhra Pradesh"), "గుంటూరు": ("Guntur", "Andhra Pradesh"),
    "krishna": ("Krishna", "Andhra Pradesh"), "కృష్ణా": ("Krishna", "Andhra Pradesh"),
    "kurnool": ("Kurnool", "Andhra Pradesh"), "కర్నూలు": ("Kurnool", "Andhra Pradesh"),
    "anantapur": ("Anantapur", "Andhra Pradesh"), "అనంతపురం": ("Anantapur", "Andhra Pradesh"),
    "visakhapatnam": ("Visakhapatnam", "Andhra Pradesh"), "vizag": ("Visakhapatnam", "Andhra Pradesh"),
    "విశాఖపట్నం": ("Visakhapatnam", "Andhra Pradesh"),
    "warangal": ("Warangal", "Telangana"), "వరంగల్": ("Warangal", "Telangana"),
    "karimnagar": ("Karimnagar", "Telangana"), "కరీంనగర్": ("Karimnagar", "Telangana"),
    "nizamabad": ("Nizamabad", "Telangana"), "నిజామాబాద్": ("Nizamabad", "Telangana"),
    "patna": ("Patna", "Bihar"), "पटना": ("Patna", "Bihar"), "gaya": ("Gaya", "Bihar"), "गया": ("Gaya", "Bihar"),
    "pune": ("Pune", "Maharashtra"), "पुणे": ("Pune", "Maharashtra"), "nagpur": ("Nagpur", "Maharashtra"),
    "नागपुर": ("Nagpur", "Maharashtra"), "ludhiana": ("Ludhiana", "Punjab"), "लुधियाना": ("Ludhiana", "Punjab"),
}

NEGATION = re.compile(
    r"\b(?:no|not|don'?t|do not|doesn'?t|never|without|nahi|nahin|nhi)\b|नहीं|नही|कोई नहीं|లేదు|లేవు|కాదు|లేని|రావడం లేదు"
)

AGE_PATTERNS = [
    re.compile(r"\b(?:age|aged|umar|umr|aayu)\s*(?:is|hai|:)?\s*(\d{1,3})\b", re.I),
    re.compile(r"\b(?:i am|i'm|main|mai)\s*(\d{1,3})\b(?!\s*(?:rs|rupees|₹|lakh|members|people))", re.I),
    re.compile(r"\b(\d{1,3})\s*(?:years?|yrs?|saal|sal|varsh|baras)\b", re.I),
    re.compile(r"(\d{1,3})\s*(?:साल|वर्ष|बरस)"),
    re.compile(r"(?:उम्र|आयु)\s*(?:है\s*)?(\d{1,3})"),
    re.compile(r"(\d{1,3})\s*(?:సంవత్సరాల|సంవత్సరాలు|ఏళ్ల|ఏళ్ళ|ఏళ్లు|ఏళ్ళు|ఏండ్లు)"),
    re.compile(r"(?:వయస్సు|వయసు)\s*(\d{1,3})"),
]

INCOME_WORDS = re.compile(
    r"income|earn|salary|kamai|kamaai|aay\b|aamdani|amdani|आय|आमदनी|कमाई|कमाते|तनख्वाह|ఆదాయం|ఆదాయము|సంపాదన|జీతం", re.I
)
MONTHLY_WORDS = re.compile(r"month|monthly|mahina|mahine|maheena|महीना|महीने|माह|मासिक|నెలకు|నెల|నెలవారీ", re.I)
AMOUNT_RE = re.compile(
    r"(?:₹|rs\.?|inr)?\s*(\d[\d,]*(?:\.\d+)?)\s*(lakhs?|lacs?|लाख|లక్షలు|లక్ష|thousand|hazaa?r|हज़ार|हजार|వేలు|వేల|k\b)?",
    re.I,
)
MULTIPLIERS = {"lakh": 100000, "lac": 100000, "लाख": 100000, "లక్ష": 100000, "thousand": 1000, "hazar": 1000,
               "hazaar": 1000, "हज़ार": 1000, "हजार": 1000, "వేలు": 1000, "వేల": 1000, "k": 1000}

HOUSEHOLD_RE = [
    re.compile(r"\b(\d{1,2})\s*(?:members|people|persons|log)\b", re.I),
    re.compile(r"\bfamily of\s*(\d{1,2})\b", re.I),
    re.compile(r"(\d{1,2})\s*(?:लोग|सदस्य)"),
    re.compile(r"(\d{1,2})\s*(?:మంది|సభ్యులు)"),
]

FEMALE = re.compile(r"\b(?:woman|female|lady|widow|mahila|aurat|girl)\b|महिला|औरत|स्त्री|विधवा|స్త్రీ|మహిళ|వితంతువు|ఆడ", re.I)
MALE = re.compile(r"\b(?:man|male|gent|purush|aadmi)\b|पुरुष|आदमी|పురుషుడు|మగ", re.I)

WIDOW = re.compile(
    r"\b(?:widow|widowed|vidhwa|vidhva)\b|husband (?:died|passed|is dead|expired)|विधवा|पति की मृत्यु|पति नहीं रहे|वितंतु|వితంతువు|భర్త చనిపోయ|భర్త లేరు",
    re.I,
)
SINGLE = re.compile(r"\b(?:unmarried|single|not married)\b|अविवाहित|कुंवारा|कुंवारी|పెళ్లి కాలేదు|అవివాహిత", re.I)
MARRIED = re.compile(r"\b(?:married|shaadi ?shuda)\b|शादीशुदा|विवाहित|పెళ్లి అయింది|వివాహిత", re.I)

BPL = re.compile(
    r"\bbpl\b|below poverty|antyodaya|gareebi rekha|garibi rekha|गरीबी रेखा|बीपीएल|बी\.पी\.एल|अंत्योदय|బీపీఎల్|దారిద్య్ర రేఖ|అంత్యోదయ",
    re.I,
)
WHITE_RATION = re.compile(r"white ration|safed ration|सफेद राशन|తెల్ల రేషన్", re.I)

RURAL = re.compile(r"\b(?:village|rural|gaon|gaav|gaanv)\b|गाँव|गांव|ग्रामीण|గ్రామం|గ్రామ|పల్లె|ఊరు", re.I)
URBAN = re.compile(r"\b(?:city|town|urban|shahar)\b|शहर|नगर|కస్బా|పట్టణం|నగరం", re.I)

OCCUPATIONS = [
    ("farmer", re.compile(r"\b(?:farmer|farming|kisan|kisaan|rythu|raitu|agricultur\w*)\b|किसान|खेती|రైతు|వ్యవసాయ", re.I)),
    ("construction_worker", re.compile(r"\bconstruction\b|mistri|मिस्त्री|निर्माण मज़दूर|భవన నిర్మాణ", re.I)),
    ("weaver", re.compile(r"\b(?:weaver|weaving|bunkar)\b|बुनकर|నేత", re.I)),
    ("labourer", re.compile(r"\b(?:labou?rer|labou?r|mazdoor|majdoor|coolie|kooli)\b|मज़दूर|मजदूर|కూలీ|కూలి", re.I)),
    ("student", re.compile(r"\b(?:student|studying)\b|छात्र|विद्यार्थी|విద్యార్థి", re.I)),
]

PENSION = re.compile(r"\bpension\b|pinchan|पेंशन|पेन्शन|పెన్షన్|పింఛన్|పింఛను|ఫించను", re.I)
RECEIVE = re.compile(r"\b(?:get|gets|getting|receive|receiving|already)\b|milti|milta|मिलती|मिलता|వస్తోంది|అందుతుంది|వస్తుంది", re.I)
OLD_AGE_INTENT = re.compile(r"old age|budhapa|vriddha|बुढ़ापा|वृद्धावस्था|वृद्धा|వృద్ధాప్య|ముసలి", re.I)

LAND = re.compile(r"\b(?:acres?|land|zameen|jameen|khet|pattadar|patta)\b|एकड़|ज़मीन|जमीन|भूमि|खेत|पट्टा|ఎకరా|ఎకరాలు|భూమి|పొలం|పట్టా", re.I)
LANDLESS = re.compile(r"\blandless\b|भूमिहीन|భూమి లేని", re.I)

BANK = re.compile(r"bank account|bank khata|post office account|jan ?dhan|बैंक खाता|बैंक में खाता|जन धन|బ్యాంక్ ఖాతా|బ్యాంకు ఖాతా|బ్యాంక్ అకౌంట్", re.I)

PUCCA = re.compile(r"pucca house|pakka (?:ghar|makan)|पक्का मकान|पक्का घर|పక్కా ఇల్లు|పక్కా ఇంటి", re.I)
NO_HOUSE = re.compile(r"\b(?:kutcha|kachha|homeless)\b|कच्चा|बेघर|ఇల్లు లేదు|సొంత ఇల్లు లేదు", re.I)

NAME_RE = [
    re.compile(r"\bmy name is\s+([A-Za-z][A-Za-z .]{1,40}?)(?:[,.]|\band\b|$)", re.I),
    re.compile(r"मेरा नाम\s+(\S+(?:\s\S+)?)\s+है"),
    re.compile(r"నా పేరు\s+(\S+(?:\s\S+)?)"),
]

# FR-18 dialect / colloquial glossary: original term -> canonical meaning shown to the citizen.
GLOSSARY = [
    (re.compile(r"budhapa pension|बुढ़ापा पेंशन", re.I), "old-age pension"),
    (re.compile(r"వృద్ధాప్య పింఛన్|ముసలి వాళ్ళ పింఛను", re.I), "old-age pension"),
    (re.compile(r"\b(?:rythu|raitu)\b", re.I), "farmer"),
    (re.compile(r"\bkooli\b|కూలి", re.I), "daily-wage labourer"),
    (re.compile(r"pattadar|పట్టాదారు", re.I), "registered land holder"),
    (re.compile(r"white ration|తెల్ల రేషన్|सफेद राशन", re.I), "white ration card (often BPL — please confirm)"),
]


def _clauses(text: str) -> list[str]:
    # Commas split clauses unless they sit inside a number such as 1,20,000.
    parts = re.split(r"[;।!?\n]|\.\s|,(?!\d)|\s(?:and|but|aur|और|लेकिन|మరియు|కానీ)\s", text)
    return [p.strip() for p in parts if p and p.strip()]


def _neg(clause: str) -> bool:
    return bool(NEGATION.search(clause))


def _fact(attr, value, span, confidence=0.9, inferred=False, note=None):
    return {"attribute": attr, "value": value, "raw_text": span.strip(), "confidence": confidence,
            "inferred": inferred, "note": note}


def _amount(clause: str) -> tuple[int, str] | None:
    best = None
    for m in AMOUNT_RE.finditer(clause):
        num_s = m.group(1).replace(",", "")
        if not num_s:
            continue
        tail = clause[m.end(): m.end() + 12].lower()
        if re.match(r"\s*(?:years?|yrs?|saal|sal|साल|वर्ष|సంవత్సర|ఏళ్ల|members|people|लोग|మంది)", tail):
            continue
        val = float(num_s)
        unit = (m.group(2) or "").lower()
        mult = next((v for k, v in MULTIPLIERS.items() if unit.startswith(k)), 1)
        val = int(round(val * mult))
        if val < 100:  # bare small numbers are not incomes
            continue
        if best is None or val > best[0]:
            best = (val, m.group(0))
    return best


def extract(text: str, default_state: str | None = None) -> dict:
    raw = text or ""
    norm = raw.translate(_DIGITS)
    clauses = _clauses(norm)
    facts: list[dict] = []
    intents: set[str] = set()
    glossary_hits = []

    # Income first so its clause can be excluded from age parsing.
    income_clauses = set()
    for c in clauses:
        if INCOME_WORDS.search(c):
            amt = _amount(c)
            if amt:
                val, span = amt
                income_clauses.add(c)
                if MONTHLY_WORDS.search(c):
                    facts.append(_fact("annual_income", val * 12, c, 0.8, inferred=True,
                                       note=f"Stated as ₹{val:,} per month; converted to yearly (×12)."))
                else:
                    facts.append(_fact("annual_income", val, c))
                break

    for c in clauses:
        if c in income_clauses:
            continue
        for pat in AGE_PATTERNS:
            m = pat.search(c)
            if m:
                age = int(m.group(1))
                if 0 < age < 120:
                    facts.append(_fact("age", age, m.group(0)))
                break
        if any(f["attribute"] == "age" for f in facts):
            break

    for pat in HOUSEHOLD_RE:
        m = pat.search(norm)
        if m:
            facts.append(_fact("household_size", int(m.group(1)), m.group(0)))
            break

    low = norm.lower()
    found_state = None
    for canonical, aliases in STATE_ALIASES.items():
        for a in sorted(aliases, key=len, reverse=True):
            idx = low.find(a.lower())
            if idx >= 0 and (found_state is None or len(a) > len(found_state[1])):
                found_state = (canonical, a)
    for key, (district, state) in DISTRICTS.items():
        if key in low:
            facts.append(_fact("district", district, key))
            if not found_state:
                facts.append(_fact("state", state, key, 0.7, inferred=True,
                                   note=f"Inferred from district {district}."))
            break
    if found_state:
        facts.append(_fact("state", found_state[0], found_state[1]))

    if WIDOW.search(norm):
        m = WIDOW.search(norm)
        facts.append(_fact("marital_status", "widowed", m.group(0)))
        facts.append(_fact("gender", "female", m.group(0), 0.8, inferred=True, note="Inferred from widow status."))
        intents.add("widow")
    elif SINGLE.search(norm):
        facts.append(_fact("marital_status", "single", SINGLE.search(norm).group(0)))
    elif MARRIED.search(norm):
        facts.append(_fact("marital_status", "married", MARRIED.search(norm).group(0)))

    if not any(f["attribute"] == "gender" for f in facts):
        fm, mm = FEMALE.search(norm), MALE.search(norm)
        if fm and not mm:
            facts.append(_fact("gender", "female", fm.group(0)))
        elif mm and not fm:
            facts.append(_fact("gender", "male", mm.group(0)))

    for c in clauses:
        m = BPL.search(c)
        if m:
            facts.append(_fact("bpl", not _neg(c), c))
            break
    else:
        for c in clauses:
            m = WHITE_RATION.search(c)
            if m:
                facts.append(_fact("bpl", not _neg(c), c, 0.6, inferred=True,
                                   note="White ration card usually indicates BPL status; please confirm."))
                break

    r, u = RURAL.search(norm), URBAN.search(norm)
    if r and not u:
        facts.append(_fact("area", "rural", r.group(0)))
    elif u and not r:
        facts.append(_fact("area", "urban", u.group(0)))

    for occ, pat in OCCUPATIONS:
        m = pat.search(norm)
        if m:
            facts.append(_fact("occupation", occ, m.group(0)))
            if occ == "farmer":
                intents.add("farmer")
            break

    for c in clauses:
        if PENSION.search(c):
            intents.add("pension")
            if OLD_AGE_INTENT.search(c):
                intents.add("old age")
            if _neg(c):
                facts.append(_fact("receives_other_pension", False, c))
                break
            if RECEIVE.search(c):
                facts.append(_fact("receives_other_pension", True, c))
                break

    if LANDLESS.search(norm):
        facts.append(_fact("owns_cultivable_land", False, LANDLESS.search(norm).group(0)))
    else:
        for c in clauses:
            if LAND.search(c):
                facts.append(_fact("owns_cultivable_land", not _neg(c), c))
                break

    for c in clauses:
        if BANK.search(c):
            facts.append(_fact("has_bank_account", not _neg(c), c))
            break

    for c in clauses:
        if PUCCA.search(c):
            facts.append(_fact("owns_pucca_house", not _neg(c), c))
            break
        if NO_HOUSE.search(c):
            facts.append(_fact("owns_pucca_house", False, c))
            intents.add("housing")
            break

    for pat in NAME_RE:
        m = pat.search(raw)
        if m:
            facts.append(_fact("applicant_name", m.group(1).strip(), m.group(0), 0.8))
            break

    for pat, meaning in GLOSSARY:
        m = pat.search(norm)
        if m:
            glossary_hits.append({"term": m.group(0), "meaning": meaning})

    # One candidate per attribute; the first (most specific) wins.
    dedup: dict[str, dict] = {}
    for f in facts:
        dedup.setdefault(f["attribute"], f)
    for f in dedup.values():
        f["high_impact"] = f["attribute"] in HIGH_IMPACT
    return {"facts": list(dedup.values()), "intents": sorted(intents), "glossary": glossary_hits}
