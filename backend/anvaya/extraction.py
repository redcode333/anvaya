"""Deterministic multilingual fact extraction (English, Hindi/Hinglish, Telugu).

Produces *candidate* facts only. Every candidate carries the original span so the citizen
can see what was heard; high-impact candidates must be confirmed before rules run.
"""
import re

HIGH_IMPACT = {"age", "annual_income", "state", "area", "household_size"}

_DIGITS = str.maketrans("०१२३४५६७८९౦౧౨౩౪౫౬౭౮౯", "01234567890123456789")


# ---------------------------------------------------------------- spoken numbers
# Number words (en / hi / te, 0–100) plus hundred / thousand / lakh / crore and the colloquial fractions
# (dedh, dhai, sava, saadhe, paune, Telugu -nnara) are rewritten to digits before the patterns below run,
# so "उम्र साठ साल" is parsed exactly like "उम्र 60 साल". Each rewrite remembers the words that were heard.

def _nk(s: str) -> str:
    """Spelling-insensitive key: drop the Devanagari nukta, chandrabindu → anusvara, lower-case Latin."""
    return s.replace("़", "").replace("ँ", "ं").lower()


def _table(spec: str, start: int = 0) -> dict[str, int]:
    """'a/b c d' → {a: start, b: start, c: start+1, d: start+2}; '/' separates spelling variants."""
    return {_nk(v): n for n, group in enumerate(spec.split(), start) for v in group.split("/")}


_HI_0_99 = _table(
    "शून्य एक दो तीन चार पांच/पाँच छह/छः/छे/छै सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह/पन्द्रह सोलह सत्रह "
    "अठारह उन्नीस बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस/अठ्ठाईस/अठाईस उनतीस तीस इकतीस "
    "बत्तीस तैंतीस चौंतीस पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस/चौवालीस "
    "पैंतालीस छियालीस सैंतालीस अड़तालीस उनचास पचास इक्यावन बावन तिरेपन/तिरपन चौवन पचपन छप्पन सत्तावन "
    "अट्ठावन/अठ्ठावन/अठावन उनसठ साठ इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ/सरसठ अड़सठ उनहत्तर सत्तर इकहत्तर "
    "बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी/उनासी अस्सी इक्यासी बयासी तिरासी चौरासी "
    "पचासी छियासी सत्तासी अट्ठासी/अठ्ठासी/अठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे पचानवे/पंचानवे छियानवे सत्तानवे "
    "अट्ठानवे/अठ्ठानवे/अठानवे निन्यानवे"
)
_EN_0_19 = _table("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
                  "fifteen sixteen seventeen eighteen nineteen")
_EN_TENS = {w: 10 * n for n, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split(), 2)}
_EN_TENS["fourty"] = 40
_TE_0_19 = _table("సున్నా ఒకటి రెండు మూడు నాలుగు ఐదు/అయిదు ఆరు ఏడు ఎనిమిది తొమ్మిది పది పదకొండు పన్నెండు "
                  "పదమూడు పద్నాలుగు పదిహేను/పదేను పదహారు పదిహేడు పద్దెనిమిది పందొమ్మిది")
_TE_TENS = {_nk(v): 10 * n for n, group in enumerate(
    "ఇరవై/ఇరవయ్యి ముప్పై/ముప్ఫై/ముప్పయి నలభై/నలబై యాభై/యాబై/ఏభై అరవై/అరవయ్యి డెబ్బై/డెబ్భై ఎనభై/ఎనబై "
    "తొంభై/తొంబై".split(), 2) for v in group.split("/")}
# Romanized Hindi is only read as a number before a unit (saal, lakh, log…): "saath" is also "with".
_HI_ROMAN = {"ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chhe": 6, "chhah": 6,
             "saat": 7, "aath": 8, "nau": 9, "das": 10, "bees": 20, "pachees": 25, "tees": 30, "chalis": 40,
             "chaalis": 40, "pachas": 50, "pachaas": 50, "pachpan": 55, "saath": 60, "sath": 60, "painsath": 65,
             "sattar": 70, "pachattar": 75, "assi": 80, "nabbe": 90}

UNIT_WORDS = {**_HI_0_99, **_EN_0_19, **_EN_TENS, **_TE_0_19, **_TE_TENS, **_HI_ROMAN}
# Words that are also everyday words ("a", "एक गाँव", "ఒక ఊరు", "पैसे दो") count only before a unit.
CONTEXTUAL = {"a": 1, "an": 1, "एक": 1, "दो": 2, "ఒక": 1, **_HI_ROMAN}
ARTICLES = {"a", "an"}  # only ever start a number ("a lakh"), never continue one ("sixteen thousand a month")

HUNDRED = {"hundred", "hundreds", "सौ", "sau", "వంద", "వందలు", "వందల", "నూరు", "నూట"}
BARE_HUNDRED = {"सौ", "వంద", "నూరు"}  # "सौ रुपये" = 100 without a leading number
MULTIPLIER_WORDS = {
    "thousand": 1000, "thousands": 1000, "हजार": 1000, "hazar": 1000, "hazaar": 1000, "hajar": 1000,
    "lakh": 100000, "lakhs": 100000, "lac": 100000, "lacs": 100000, "लाख": 100000,
    "crore": 10_000_000, "crores": 10_000_000, "करोड": 10_000_000, "karod": 10_000_000,
}
_TE_MULTIPLIER_PREFIXES = [("లక్ష", 100000), ("కోటి", 10_000_000), ("కోట్ల", 10_000_000), ("వేల", 1000),
                           ("వెయ్యి", 1000), ("వేయి", 1000)]
# Stand-alone fractional quantities: only valid in front of a multiplier ("डेढ़ लाख", never "डेढ़ साल").
FRACTIONS = {"डेढ": 1.5, "dedh": 1.5, "derh": 1.5, "ढाई": 2.5, "dhai": 2.5, "dhaai": 2.5, "adhai": 2.5,
             "అర": 0.5}
# Modifiers of the number that follows: सवा दो = 2¼, साढ़े तीन = 3½, पौने दो = 1¾.
MODIFIERS = {"सवा": 0.25, "sava": 0.25, "sawa": 0.25, "साढे": 0.5, "sadhe": 0.5, "saadhe": 0.5,
             "पौने": -0.25, "paune": -0.25}
_TE_HALF_SUFFIX = "న్నర"  # ఒకటిన్నర = 1½, రెండున్నర = 2½

# Spoken numbers that are easily misheard for one another: always held for explicit confirmation.
_CONFUSABLE_PAIRS = [("साठ", "सत्तर"), ("साठ", "सात"), ("सत्तर", "सत्रह"), ("అరవై", "డెబ్బై"),
                     ("saath", "sattar"), ("sath", "sattar"), ("saath", "saat"), ("thirteen", "thirty"), ("fourteen", "forty"), ("fifteen", "fifty"), ("sixteen", "sixty"),
                     ("seventeen", "seventy"), ("eighteen", "eighty"), ("nineteen", "ninety")]
CONFUSABLE: dict[str, list[str]] = {}
for _a, _b in _CONFUSABLE_PAIRS:
    CONFUSABLE.setdefault(_nk(_a), []).append(_b)
    CONFUSABLE.setdefault(_nk(_b), []).append(_a)

# A contextual-only number is accepted when the next word is one of these units.
_UNIT_NEXT = re.compile(
    r"^(?:(?:years?|yrs?|saal|sal|varsh|baras|members|people|persons|log)$|साल|वर्ष|बरस|लोग|सदस्य|సంవత్సర|ఏళ్ల|ఏళ్ళ|ఏండ్ల|మంది)"
)
_WORD = re.compile(r"\d+(?:[.,]\d+)*|[A-Za-z]+|[ऀ-ॣॱ-ॿ]+|[ఀ-౥౰-౿]+")


def _multiplier(key: str) -> int | None:
    if key in MULTIPLIER_WORDS:
        return MULTIPLIER_WORDS[key]
    return next((v for p, v in _TE_MULTIPLIER_PREFIXES if key.startswith(p)), None)


def _unit(key: str) -> int | None:
    """Value of a 0–99 number word, including fused Telugu tens+units such as అరవైఐదు."""
    if key in UNIT_WORDS:
        return UNIT_WORDS[key]
    for tens, tv in _TE_TENS.items():
        if key.startswith(tens) and key[len(tens):] in _TE_0_19 and _TE_0_19[key[len(tens):]] < 10:
            return tv + _TE_0_19[key[len(tens):]]
    return None


def _can_add(current: float, v: int) -> bool:
    r = current % 100
    return current == 0 or (current >= 100 and r == 0 and v < 100) or (r >= 20 and r % 10 == 0 and 0 < v < 10)


def numerize(text: str) -> tuple[str, list[dict]]:
    """Rewrite spoken numbers to digits. Returns (text, rewrites) where each rewrite records
    {digits, words, value, spoken, confusable_with}; 'spoken' is False for '2 lakh'-style digit+unit."""
    toks = [(m.start(), m.end(), m.group(0)) for m in _WORD.finditer(text)]
    out, rewrites, pos, i = [], [], 0, 0
    while i < len(toks):
        res = _read_number(text, toks, i)
        if res is None:
            i += 1
            continue
        j, value, has_word, confusable = res
        start, end = toks[i][0], toks[j - 1][1]
        digits = str(value)
        out.append(text[pos:start] + digits)
        pos = end
        rewrites.append({"digits": digits, "words": text[start:end], "value": value, "spoken": has_word,
                         "confusable_with": confusable})
        i = j
    out.append(text[pos:])
    return "".join(out), rewrites


def _read_number(text, toks, i):
    """Longest number phrase starting at token i → (next index, int value, has number word, confusable alts)."""
    total, current, mod, pending_mod = 0.0, 0.0, 0.0, False
    has_word = has_mult = has_digit = False
    only_contextual = True
    fraction = False
    confusable: list[str] = []
    j = i
    while j < len(toks):
        if j > i and not re.fullmatch(r"[\s-]*", text[toks[j - 1][1]:toks[j][0]]):
            break  # numbers are contiguous: only spaces / hyphens between words
        raw = toks[j][2]
        key = _nk(raw)
        if raw[0].isdigit():
            if current or has_word or fraction:
                break
            current, has_digit = float(raw.replace(",", "")), True
        elif key == "and" and (current or total) and j + 1 < len(toks):
            nxt = _nk(toks[j + 1][2])
            if nxt == "half" or (nxt == "a" and j + 2 < len(toks) and _nk(toks[j + 2][2]) == "half"):
                current += 0.5
                fraction = True
                j += 3 if nxt == "a" else 2
                continue
            if _unit(nxt) is None:
                break
        elif (m := _multiplier(key)) is not None or key in HUNDRED:
            if not (current or pending_mod or key in BARE_HUNDRED):
                break
            has_word = has_word or key in BARE_HUNDRED
            base = (current or 1.0) + (mod if pending_mod and not current else 0.0)
            if pending_mod and not current and mod == 0.5:
                break  # साढ़े needs a number: "साढ़े लाख" is not a quantity
            pending_mod, has_mult = False, True
            if key in HUNDRED:
                current = base * 100
            else:
                total += base * m
                current = 0.0
        elif key in FRACTIONS:
            if current or pending_mod:
                break
            current, fraction, has_word, only_contextual = FRACTIONS[key], True, True, False
        elif key.endswith(_TE_HALF_SUFFIX) and _unit(key[: -len(_TE_HALF_SUFFIX)]) is not None:
            if current or pending_mod:
                break
            current = _unit(key[: -len(_TE_HALF_SUFFIX)]) + 0.5
            fraction, has_word, only_contextual = True, True, False
        elif key in MODIFIERS:
            if current or pending_mod:
                break
            mod, pending_mod, has_word, only_contextual = MODIFIERS[key], True, True, False
        elif (v := _unit(key)) is not None or key in CONTEXTUAL:
            v = v if v is not None else CONTEXTUAL[key]
            if key in ARTICLES and (current or total):
                break
            if pending_mod:
                current, pending_mod = v + mod, False
            elif _can_add(current, v) and not (has_digit and not has_mult):
                current += v
            else:
                break
            has_word = True
            only_contextual = only_contextual and key in CONTEXTUAL
            confusable += CONFUSABLE.get(key, [])
        else:
            break
        j += 1
    if j == i or not (has_word or has_mult) or pending_mod:
        return None
    if has_digit and not has_mult:
        return None  # plain digits are left for the patterns as they are
    if only_contextual and not has_mult:
        nxt = _nk(toks[j][2]) if j < len(toks) else ""
        if not _UNIT_NEXT.match(nxt):
            return None
    value = total + current
    if abs(value - round(value)) > 1e-6:
        return None  # "डेढ़ साल", "two and a half": not a whole quantity
    return j, int(round(value)), has_word, sorted(set(confusable))

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
    r"\b(?:no|not|don'?t|do not|doesn'?t|never|without|neither|nor|none|nobody|no one|nahi|nahin|nhi)\b|नहीं|नही|कोई नहीं|"
    r"లేదు|లేవు|కాదు|లేని|రావడం లేదు|రావట్లేదు|రాదు|రావు|అందదు|అందడం లేదు",
    re.I,  # "No pension", "Neither of us …" start a sentence
)

AGE_PATTERNS = [
    re.compile(r"\b(?:age|aged|umar|umr|aayu)\s*(?:is|hai|:)?\s*(\d{1,3})\b", re.I),
    re.compile(r"\b(?:i am|i'm|main|mai)\s*(\d{1,3})\b(?!\s*(?:rs|rupees|₹|lakh|members|people|of\b))", re.I),
    re.compile(r"\b(\d{1,3})\s*(?:years?|yrs?|saal|sal|varsh|baras)\b", re.I),
    re.compile(r"(\d{1,3})\s*(?:साल|वर्ष|बरस)"),
    re.compile(r"(?:उम्र|आयु)\s*(?:है\s*)?(\d{1,3})"),
    re.compile(r"(\d{1,3})\s*(?:సంవత్సరాల|సంవత్సరాలు|ఏళ్ల|ఏళ్ళ|ఏళ్లు|ఏళ్ళు|ఏండ్లు)"),
    re.compile(r"(?:వయస్సు|వయసు)\s*(\d{1,3})"),
]

INCOME_WORDS = re.compile(
    r"income|earn|salary|kamai|kamaai|kamata|kamati|kamate|aay\b|aamdani|amdani|आय|आमदनी|कमाई|कमात|तनख्वाह|ఆదాయం|ఆదాయము|సంపాద|జీతం",
    re.I,
)
MONTHLY_WORDS = re.compile(r"month|monthly|mahina|mahine|maheena|महीना|महीने|माह|मासिक|నెలకు|నెల|నెలవారీ", re.I)
YEARLY_WORDS = re.compile(
    r"\b(?:years?|yearly|annual(?:ly)?|annum|saal|sal|salana|saalana|varsh|varshik)\b|साल|वर्ष|वार्षिक|సంవత్సర|ఏడాది|ఏటా",
    re.I,
)

# Ages said next to a relation word belong to that relative, not to the applicant.
RELATION = re.compile(
    r"\b(?:mother|mom|mum|mummy|father|dad|daddy|wife|husband|son|daughter|brother|sister|grandmother|grandfather|"
    r"grandson|granddaughter|child|children|in-laws?|maa|papa|pita|pitaji|patni|pati|beta|beti|bete|bhai|behen|bahan|"
    r"dadi|dada|nani|nana|saas|sasur)\b|माँ|मां|माता|पिता|पापा|पत्नी|पति|बेटी|बेटा|बेटे|बच्च|भाई|बहन|दादा|दादी|नाना|नानी|"
    r"सास|ससुर|అమ్మ|నాన్న|భార్య|భర్త|కూతురు|కూతురి|కొడుకు|తల్లి|తండ్రి|తమ్ముడు|చెల్లెలు|చెల్లి|నానమ్మ",
    re.I,
)
SELF = re.compile(
    r"\b(?:i|i'm|me|my age|main|meri umr|meri umar|mera umar)\b|मैं|मेरी उम्र|मेरी आयु|मेरा उम्र|నేను|నా వయస్సు|నా వయసు",
    re.I,
)
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
    re.compile(r"\bwe are (\d{1,2})\b|\b(\d{1,2}) (?:in|of) (?:the|my|our) family\b", re.I),
    re.compile(r"(?:हम|hum)\s*(\d{1,2})\s*(?:हैं|hain|लोग|log)", re.I),
    re.compile(r"(?:परिवार|घर)\s*में\s*(\d{1,2})\s*(?:लोग|सदस्य|हैं)"),
]

# "widow pension" / "विधवा पेंशन" names a scheme the citizen asks about; it says nothing about the speaker.
_NOT_PENSION = r"(?!\s*(?:pension|pinchan|scheme|yojana|पेंशन|पेन्शन|योजना|పెన్షన్|పింఛన్|పింఛను|ఫించను|పథకం))"
WIDOW_PENSION = re.compile(r"\b(?:widow|vidhwa|vidhva)\s+(?:pension|pinchan|scheme|yojana)|विधवा\s*(?:पेंशन|पेन्शन|योजना)|"
                           r"వితంతు(?:వు)?\s*(?:పెన్షన్|పింఛన్|పింఛను|ఫించను|పథకం)", re.I)
FEMALE = re.compile(r"\b(?:woman|female|lady|mahila|aurat|girl)\b|\bwidow\b" + _NOT_PENSION +
                    r"|महिला|औरत|स्त्री|विधवा" + _NOT_PENSION + r"|స్త్రీ|మహిళ|వితంతువు" + _NOT_PENSION + r"|ఆడ", re.I)
MALE = re.compile(r"\b(?:man|male|gent|purush|aadmi)\b|पुरुष|आदमी|పురుషుడు|మగ", re.I)

WIDOW = re.compile(
    r"\b(?:widow|widowed|vidhwa|vidhva)\b" + _NOT_PENSION + r"|husband (?:died|passed|is dead|expired|is no more)|"
    r"late husband|विधवा" + _NOT_PENSION + r"|पति की मृत्यु|पति का (?:निधन|देहांत|स्वर्गवास)|पति नहीं रहे|पति गु(?:ज़|ज)र|"
    r"वितंतु|వితంతువు" + _NOT_PENSION + r"|భర్త చనిపోయ|భర్త మరణించ|భర్త పోయారు|భర్త లేరు",
    re.I,
)
SINGLE = re.compile(r"\b(?:unmarried|single|not married)\b|शादी\s*नहीं\s*हुई|अविवाहित|कुंवारा|कुंवारी|పెళ్లి కాలేదు|అవివాహిత", re.I)
MARRIED = re.compile(r"\b(?:married|shaadi ?shuda)\b|शादी\s*(?:हो\s*(?:गई|गयी|चुकी)|हुई)|शादीशुदा|विवाहित|పెళ్లి అయింది|వివాహిత", re.I)

BPL = re.compile(
    r"\bbpl\b|below poverty|antyodaya|gareebi rekha|garibi rekha|गरीबी रेखा|बीपीएल|बी\.पी\.एल|अंत्योदय|బీపీఎల్|దారిద్య్ర రేఖ|అంత్యోదయ",
    re.I,
)
WHITE_RATION = re.compile(r"white ration|safed ration|सफेद राशन|राशन कार्ड सफेद|सफेद कार्ड|తెల్ల రేషన్", re.I)

RURAL = re.compile(r"\b(?:village|rural|gaon|gaav|gaanv|dehat|dehaat)\b|देहात|गाँव|गांव|ग्रामीण|గ్రామం|గ్రామ|పల్లె|ఊరు", re.I)
URBAN = re.compile(r"\b(?:city|town|urban|shahar)\b|शहर|नगर|కస్బా|పట్టణం|నగరం", re.I)

OCCUPATIONS = [
    ("farmer", re.compile(r"\b(?:farmer|farming|kisan|kisaan|kheti|rythu|raitu|agricultur\w*)\b|किसान|खेती|రైతు|వ్యవసాయ", re.I)),
    ("construction_worker", re.compile(r"\bconstruction\b|mistri|मिस्त्री|निर्माण मज़दूर|భవన నిర్మాణ", re.I)),
    ("weaver", re.compile(r"\b(?:weaver|weaving|bunkar)\b|बुनकर|నేత", re.I)),
    ("labourer", re.compile(r"\b(?:labou?rer|labou?r|mazdoor|majdoor|coolie|kooli)\b|मज़दूर|मजदूर|కూలీ|కూలి", re.I)),
    ("student", re.compile(r"\b(?:student|studying)\b|छात्र|विद्यार्थी|విద్యార్థి", re.I)),
    ("self_employed", re.compile(r"\b(?:self[- ]employed|dukaan|dukan|vyapar|dhandha|business (?:karta|karti|chalata|chalati|hai))\b|"
                                 r"दुकान\s*(?:चला|है)|दुकानदार|व्यापार|धंधा|స్వయం ఉపాధి", re.I)),
    ("salaried", re.compile(r"\b(?:salaried|naukri (?:karta|karti|hai)|job (?:karta|karti|hai))\b|नौकरी\s*(?:करता|करती|करते|है)|"
                            r"सरकारी नौकरी|ఉద్యోగి|ఉద్యోగం చేస్తున్నాను", re.I)),
    ("homemaker", re.compile(r"\b(?:homemaker|housewife|house wife|ghar ka kaam)\b|गृहिणी|घर का काम|ఇంటి పని|గృహిణి", re.I)),
]

# Words that stand for the occupation only as an answer to "what work do you do?".
OCCUPATION_ANSWERS = [
    ("self_employed", re.compile(r"\b(?:shop|business|dukaan|dukan)\b|दुकान|बिज़नेस|बिजनेस|व्यवसाय", re.I)),
    ("salaried", re.compile(r"\b(?:job|naukri|service)\b|नौकरी|नौकर", re.I)),
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
            "inferred": inferred, "note": note, "confusable": False}


def _amount(clause: str) -> tuple[int, str, int, str] | None:
    """Largest amount in the clause → (rupees, matched span, span start, digits as written)."""
    best = None
    for m in AMOUNT_RE.finditer(clause):
        num_s = m.group(1).replace(",", "")
        if not num_s:
            continue
        tail = clause[m.end(): m.end() + 12].lower()
        val = float(num_s)
        # "45 saal" is an age, but "150000 saal ki aay" (a year's income) is not.
        if val < 1000 and re.match(r"\s*(?:years?|yrs?|saal|sal|साल|वर्ष|సంవత్సర|ఏళ్ల|members|people|लोग|మంది)", tail):
            continue
        unit = (m.group(2) or "").lower()
        mult = next((v for k, v in MULTIPLIERS.items() if unit.startswith(k)), 1)
        val = int(round(val * mult))
        if val < 100:  # bare small numbers are not incomes
            continue
        if best is None or val > best[0]:
            best = (val, m.group(0), m.start(1), m.group(1))
    return best


def _is_monthly(clause: str, at: int) -> bool:
    """The period word nearest to the amount decides: "साल भर में … महीने" style clauses are rare but exist."""
    def dist(pat):
        return min((min(abs(m.start() - at), abs(m.end() - at)) for m in pat.finditer(clause)), default=None)
    month, year = dist(MONTHLY_WORDS), dist(YEARLY_WORDS)
    return month is not None and (year is None or month <= year)


# Attributes where a single spoken number word is the whole value (an income like "साठ हज़ार" carries a unit, so its
# sound-alike would have a different scale and is not offered).
SOUND_ALIKE_ATTRS = {"age", "household_size"}


def sound_alike_values(fact: dict) -> list[int] | None:
    """[heard value, then the values of the words it can be mistaken for] for a confusable spoken number such as "सात"
    (7), which speech recognition often returns for "साठ" (60). None when there is nothing to offer."""
    if fact.get("attribute") not in SOUND_ALIKE_ATTRS or not fact.get("confusable")             or len((fact.get("heard_as") or "").split()) != 1 or not isinstance(fact.get("value"), int):
        return None
    values = [fact["value"]]
    for word in fact.get("confusable_with") or []:
        for r in numerize(word)[1]:
            if r["spoken"] and r["value"] not in values:
                values.append(r["value"])
    return values if len(values) > 1 else None


def _heard(fact: dict, digits: str, rewrites: list[dict]) -> dict:
    """Attach the spoken words behind a number; confusable number words lower confidence and need confirmation."""
    rw = next((r for r in rewrites if r["digits"] == digits.replace(",", "") and r["spoken"]), None)
    if not rw:
        return fact
    fact["heard_as"] = rw["words"]
    notes = [fact["note"]] if fact["note"] else []
    if rw["confusable_with"]:
        fact["confusable"] = True
        fact["confusable_with"] = rw["confusable_with"]
        fact["confidence"] = min(fact["confidence"], 0.6)
        notes.append(f"Heard “{rw['words']}” — it can sound like “{' / '.join(rw['confusable_with'])}”; "
                     f"please confirm the number.")
    else:
        notes.append(f"Heard as “{rw['words']}”.")
    fact["note"] = " ".join(notes)
    return fact


def _relation_before(clause: str, at: int) -> str | None:
    """Relation word governing the number at `at`: the nearest one before it with no 'I / my age' in between."""
    rel = None
    for m in RELATION.finditer(clause, 0, at):
        rel = m
    if rel and not SELF.search(clause, rel.end(), at):
        return rel.group(0)
    return None


# ---------------------------------------------------------------- conversational understanding
# Short answers ("नहीं", "चार", "पुरुष"), who is in the household, and masculine/feminine verb forms. Everything here
# is a reading of what the speaker most likely meant, so the facts it adds are marked inferred where they are guesses.

_TOKEN = re.compile(r"[\wऀ-ॿఀ-౿]+")
_STRONG_YES = {"हाँ", "हां", "हा", "हाँजी", "हांजी", "बिल्कुल", "बिलकुल", "अवश्य", "जरूर", "ज़रूर", "सही", "yes", "yeah",
               "yep", "haan", "han", "ha", "haa", "hanji", "bilkul", "sure", "correct", "sahi", "అవును", "సరే", "కరెక్ట్",
               "సరైనది", "ఉంది", "ఉన్నాయి", "ఉన్నది", "ఉన్నారు"}
_WEAK_YES = {"है", "हैं", "जी", "ji", "hai", "hain", "ok", "okay", "ठीक", "theek", "thik", "right", "have", "do"}
_NO = {"नहीं", "नही", "नहि", "ना", "न", "गलत", "no", "nahi", "nahin", "nhi", "na", "nope", "not", "never", "wrong",
       "లేదు", "లేవు", "కాదు", "తప్పు", "లేరు", "none"}


def polarity(text: str) -> bool | None:
    """True for a yes, False for a no, None when the words say neither (or both). "नहीं है" is a no and "जी नहीं" is a no:
    है / जी only count towards yes when no "no" word is present."""
    toks = {t.lower() for t in _TOKEN.findall(text or "")}
    no, strong = bool(toks & _NO), bool(toks & _STRONG_YES)
    if no and strong:
        return None
    if no:
        return False
    if strong or toks & _WEAK_YES:
        return True
    return None


BOOL_ATTRS = ("bpl", "receives_other_pension", "owns_cultivable_land", "has_bank_account", "owns_pucca_house")

# Masculine / feminine first-person verb forms ("रहता हूँ" / "रहती हूँ", "karta hoon" / "karti hoon").
_HOON = r"(?:हूँ|हूं|हुँ|hoon|hun|hu)"
MASC_SELF = re.compile(r"(?:ता|वाला|का|आदमी)\s*" + _HOON + r"(?=\s|$|[।.,?!])|\b\w+(?:ta|wala)\s+" + _HOON + r"\b|अकेला|\bakela\b", re.I)
FEM_SELF = re.compile(r"(?:ती|वाली|की)\s*" + _HOON + r"(?=\s|$|[।.,?!])|\b\w+(?:ti|wali)\s+" + _HOON + r"\b|अकेली|\bakeli\b", re.I)
SELF_BOY_GIRL = re.compile(r"(?:मैं|मै|main|i am|i'm)\s+(?:एक\s+)?(?:(लड़का|ladka|boy)|(लड़की|ladki|girl))", re.I)
# Bare gender words that only mean the speaker when the bot has just asked "woman or man?".
ANSWER_MALE = re.compile(r"मर्द|\bmard\b|लड़का|\bladka\b|\bboy\b|\bmen\b|\bmale\b|पुरुष|\bman\b", re.I)
ANSWER_FEMALE = re.compile(r"औरत|\baurat\b|लड़की|\bladki\b|\bgirl\b|\bfemale\b|\bwoman\b|महिला|स्त्री|మహిళ|స్త్రీ", re.I)

LIVES_ALONE = re.compile(r"अकेला\s*(?:रहता|हूँ|हूं)|अकेली\s*(?:रहती|हूँ|हूं)|अकेले\s*रह|\bakel[ai]\s+(?:rehta|rehti|rahta|rahti|hoon|hun)|"
                         r"\b(?:live|living|stay|staying) (?:alone|by myself)\b|\bby myself\b|ఒంటరిగా", re.I)

_SELF_TOKENS = {"मैं", "मै", "main", "mai", "me", "i", "నేను"}
_MEMBER_GROUPS = {
    "father": {"पिताजी", "पिता", "पापा", "papa", "father", "dad", "daddy", "pita", "pitaji", "నాన్న", "తండ్రి"},
    "mother": {"माता", "माँ", "मां", "माताजी", "मम्मी", "मम्मा", "mother", "mom", "mummy", "maa", "mum", "అమ్మ", "తల్లి"},
    "grandfather": {"दादा", "दादाजी", "नाना", "नानाजी", "grandfather", "dada", "nana", "తాత"},
    "grandmother": {"दादी", "दादीजी", "नानी", "grandmother", "dadi", "nani", "నానమ్మ", "అమ్మమ్మ"},
    "wife": {"पत्नी", "बीवी", "wife", "patni", "భార్య"},
    "husband": {"पति", "husband", "pati", "భర్త"},
    "brother": {"भाई", "bhai", "brother", "తమ్ముడు", "అన్న"},
    "sister": {"बहन", "behen", "bahan", "sister", "చెల్లి", "అక్క"},
    "son": {"बेटा", "son", "beta", "కొడుకు"},
    "daughter": {"बेटी", "daughter", "beti", "కూతురు"},
}
_CHILDREN = {"बच्चे", "बच्चों", "बच्चा", "बच्ची", "children", "kids", "child", "bachche", "bacche"}
_SMALL_NUMBERS = {"एक": 1, "दो": 2, "one": 1, "two": 2, "ఒక": 1, "రెండు": 2}
HOUSEHOLD_CUE = re.compile(r"घर\s*में|परिवार\s*में|\bfamily\b|\bhousehold\b|साथ|\bwith me\b|\b(?:all|together) (?:live|stay)\b", re.I)
# "रहते हैं" alone also counts, unless the speaker then says what *they* do ("… गाँव में रहते हैं और मैं शहर में काम करता हूँ").
WEAK_HOUSEHOLD_CUE = re.compile(r"रहते\s*हैं|\brehte\s+hain\b", re.I)


def household_from_listing(norm: str) -> tuple[int, str] | None:
    """People named as living together ("घर में मेरे पिताजी, माता जी, दादाजी और मैं") → (count, span). Needs a household
    cue and at least two members, and counts each kind of relative once ("दो बच्चे" counts two)."""
    if not HOUSEHOLD_CUE.search(norm) and not (WEAK_HOUSEHOLD_CUE.search(norm) and not (MASC_SELF.search(norm) or FEM_SELF.search(norm))):
        return None
    toks = [t.lower() for t in _TOKEN.findall(norm)]
    seen = set()
    count = 0
    if any(t in _SELF_TOKENS for t in toks):
        count += 1
    for i, t in enumerate(toks):
        for kind, words in _MEMBER_GROUPS.items():
            if t in words and kind not in seen:
                seen.add(kind)
                count += 1
        if t in _CHILDREN and "children" not in seen:
            prev = toks[i - 1] if i else ""
            n = int(prev) if prev.isdigit() else _SMALL_NUMBERS.get(prev)
            if n:
                seen.add("children")
                count += n
    if count < 2 or count > 30:
        return None
    return count, norm.strip()


def _answer(asked: str, norm: str, raw: str, found: set[str]) -> dict | None:
    """The fact a short reply carries when the bot had just asked about `asked` and nothing else was understood."""
    toks = _TOKEN.findall(norm)
    if asked in BOOL_ATTRS:
        pol = polarity(norm)
        if pol is not None and len(toks) <= 8 and not found:
            return _fact(asked, pol, raw, 0.85)
        return None
    if asked == "gender":
        m, f = ANSWER_MALE.search(norm), ANSWER_FEMALE.search(norm)
        if m and not f:
            return _fact("gender", "male", m.group(0))
        if f and not m:
            return _fact("gender", "female", f.group(0))
        return None
    if asked == "occupation":
        for occ, pat in OCCUPATION_ANSWERS:
            m = pat.search(norm)
            if m:
                return _fact("occupation", occ, m.group(0))
        return None
    if asked in ("age", "household_size") and len(toks) == 1 and toks[0].lower() in _SMALL_NUMBERS:
        return _fact(asked, _SMALL_NUMBERS[toks[0].lower()], raw, 0.8)  # "एक" / "दो" alone stay words in numerize
    nums = [m for m in re.finditer(r"\d[\d,]*(?:\.\d+)?", norm)]
    if asked in ("age", "household_size") and len(nums) == 1 and not re.search(r"लाख|हज़ार|हजार|lakh|thousand|₹|rs\b|rupe|रुपय|రూపాయ", norm, re.I):
        n = int(float(nums[0].group(0).replace(",", "")))
        lo, hi = (1, 119) if asked == "age" else (1, 30)
        return _fact(asked, n, raw, 0.8) if lo <= n <= hi else None
    if asked == "annual_income":
        amt = _amount(norm)
        if amt and amt[0] >= 1000:
            val, span, at, digits = amt
            if _is_monthly(norm, at):
                return _fact("annual_income", val * 12, raw, 0.8, inferred=True,
                             note=f"Stated as ₹{val:,} per month; converted to yearly (×12).")
            return _fact("annual_income", val, raw)
    return None


def extract(text: str, default_state: str | None = None, asked: str | None = None) -> dict:
    raw = text or ""
    norm, rewrites = numerize(raw.translate(_DIGITS))
    clauses = _clauses(norm)
    facts: list[dict] = []
    others: list[dict] = []
    intents: set[str] = set()
    glossary_hits = []

    # Income first so its clause can be excluded from age parsing.
    income_clauses = set()
    for c in clauses:
        if INCOME_WORDS.search(c):
            amt = _amount(c)
            if amt:
                val, span, at, digits = amt
                income_clauses.add(c)
                if _is_monthly(c, at):
                    f = _fact("annual_income", val * 12, c, 0.8, inferred=True,
                              note=f"Stated as ₹{val:,} per month; converted to yearly (×12).")
                else:
                    f = _fact("annual_income", val, c)
                facts.append(_heard(f, digits, rewrites))
                break

    age = None
    for c in clauses:
        if c in income_clauses:
            continue
        for pat in AGE_PATTERNS:
            for m in pat.finditer(c):
                n = int(m.group(1))
                if not 0 < n < 120:
                    continue
                relation = _relation_before(c, m.start(1))
                if relation:
                    if not any(o["value"] == n and o["relation"] == relation for o in others):
                        others.append({"attribute": "age", "value": n, "relation": relation, "raw_text": c.strip()})
                elif age is None:
                    age = _heard(_fact("age", n, m.group(0)), m.group(1), rewrites)
    if age:
        facts.append(age)

    for pat in HOUSEHOLD_RE:
        m = pat.search(norm)
        if m:
            digits = next(g for g in m.groups() if g)
            facts.append(_heard(_fact("household_size", int(digits), m.group(0)), digits, rewrites))
            break
    else:
        listed = None if others else household_from_listing(norm)  # a relative named only for their age is not a listing
        if LIVES_ALONE.search(norm):
            facts.append(_fact("household_size", 1, LIVES_ALONE.search(norm).group(0), 0.8, inferred=True,
                               note="Understood as living alone; please confirm."))
        elif listed:
            facts.append(_fact("household_size", listed[0], listed[1], 0.7, inferred=True,
                               note=f"Counted {listed[0]} people from who you named; please confirm."))

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

    if WIDOW_PENSION.search(norm):
        intents.add("widow")  # interest in the scheme, not the speaker's status

    if not any(f["attribute"] == "gender" for f in facts):
        fm, mm = FEMALE.search(norm), MALE.search(norm)
        bg = SELF_BOY_GIRL.search(norm)
        if fm and not mm:
            facts.append(_fact("gender", "female", fm.group(0)))
        elif mm and not fm:
            facts.append(_fact("gender", "male", mm.group(0)))
        elif bg:
            facts.append(_fact("gender", "male" if bg.group(1) else "female", bg.group(0)))
        else:
            # Hindi first-person verbs carry the speaker's gender: "रहता हूँ" (man) / "रहती हूँ" (woman).
            vm, vf = MASC_SELF.search(norm), FEM_SELF.search(norm)
            if vm and not vf:
                facts.append(_fact("gender", "male", vm.group(0), 0.75, inferred=True,
                                   note="Inferred from the masculine verb form you used; please confirm."))
            elif vf and not vm:
                facts.append(_fact("gender", "female", vf.group(0), 0.75, inferred=True,
                                   note="Inferred from the feminine verb form you used; please confirm."))

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

    # A short reply to the bot's last question ("नहीं", "चार", "पुरुष") only means something in that context.
    if asked and not any(f["attribute"] == asked for f in facts):
        ans = _answer(asked, norm, raw, {f["attribute"] for f in facts})
        if ans:
            numeric = isinstance(ans["value"], int) and not isinstance(ans["value"], bool)
            facts.append(_heard(ans, str(ans["value"]), rewrites) if numeric else ans)

    # One candidate per attribute; the first (most specific) wins.
    dedup: dict[str, dict] = {}
    for f in facts:
        dedup.setdefault(f["attribute"], f)
    for f in dedup.values():
        f["high_impact"] = f["attribute"] in HIGH_IMPACT
    return {"facts": list(dedup.values()), "intents": sorted(intents), "glossary": glossary_hits,
            "other_people": others}
