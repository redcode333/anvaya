"""Generated conversational utterances: every combination of age, state, speaker gender, income and short answer below is
built from templates in Hindi, Hinglish, English and Telugu, and must extract exactly what was meant (and nothing that
was not)."""
import itertools

import pytest

from anvaya import extraction


def got(text, asked=None):
    return {f["attribute"]: f["value"] for f in extraction.extract(text, asked=asked)["facts"]}


AGES = [(24, "चौबीस"), (35, "पैंतीस"), (42, "बयालीस"), (58, "अट्ठावन"), (63, "तिरसठ"), (71, "इकहत्तर"), (19, "उन्नीस"), (88, "अठासी")]
STATES = [("Bihar", "बिहार"), ("Jharkhand", "झारखंड"), ("Uttar Pradesh", "उत्तर प्रदेश"), ("Maharashtra", "महाराष्ट्र"),
          ("Gujarat", "गुजरात"), ("Rajasthan", "राजस्थान"), ("Odisha", "ओडिशा"), ("Tamil Nadu", "तमिलनाडु")]
VERBS = [("male", "रहता", "karta", "rehta"), ("female", "रहती", "karti", "rehti")]


@pytest.mark.parametrize("age,state,verb", list(itertools.product(AGES, STATES, VERBS)),
                         ids=lambda x: str(x[0]) if isinstance(x, tuple) else str(x))
def test_hindi_statement_with_age_state_and_gendered_verb(age, state, verb):
    n, words = age
    canonical, hi_state = state
    gender, rahta, _, _ = verb
    for text in (f"मेरी उम्र {words} साल है और मैं {hi_state} में {rahta} हूँ",
                 f"मैं {hi_state} में {rahta} हूँ, मेरी उम्र {n} साल है"):
        g = got(text)
        assert g.get("age") == n and g.get("state") == canonical and g.get("gender") == gender, (text, g)


@pytest.mark.parametrize("age,verb", list(itertools.product(AGES, VERBS)), ids=lambda x: str(x[0]) if isinstance(x, tuple) else str(x))
def test_hinglish_statement(age, verb):
    n, _ = age
    gender, _, karta, rehta = verb
    g = got(f"main Bihar mein {rehta} hoon aur meri umar {n} saal hai, main kheti {karta} hoon")
    assert g.get("age") == n and g.get("state") == "Bihar" and g.get("gender") == gender and g.get("occupation") == "farmer", g


INCOMES = [("साढ़े तीन लाख", 350000), ("दो लाख", 200000), ("डेढ़ लाख", 150000), ("पचास हज़ार", 50000),
           ("एक लाख बीस हज़ार", 120000), ("छह लाख", 600000), ("पचहत्तर हज़ार", 75000), ("ढाई लाख", 250000)]


@pytest.mark.parametrize("amount", INCOMES, ids=[a for a, _ in INCOMES])
def test_income_as_a_bare_answer_and_in_a_sentence(amount):
    words, value = amount
    assert got(words, asked="annual_income").get("annual_income") == value
    assert got(f"हमारे परिवार की सालाना आय {words} रुपये है").get("annual_income") == value
    assert got(f"{words} रुपये सालाना कमाई है").get("annual_income") == value


@pytest.mark.parametrize("words,monthly", [("दस हज़ार", 10000), ("पंद्रह हज़ार", 15000), ("बीस हज़ार", 20000), ("पच्चीस हज़ार", 25000)])
def test_monthly_income_is_converted_to_yearly(words, monthly):
    g = got(f"हम महीने का {words} कमाते हैं")
    assert g.get("annual_income") == monthly * 12


YES = ["हाँ", "हां", "हाँ जी", "जी हाँ", "हाँ है", "बिल्कुल", "haan", "haan hai", "yes", "yeah", "yes we do", "అవును", "ఉంది", "जी है", "सही"]
NO = ["नहीं", "नहीं है", "जी नहीं", "नहीं जी", "nahi", "nahi hai", "no", "no we don't", "nope", "లేదు", "కాదు", "ना", "नहीं नहीं"]
BOOLS = ["bpl", "receives_other_pension", "owns_cultivable_land", "has_bank_account", "owns_pucca_house"]


@pytest.mark.parametrize("attr,text", list(itertools.product(BOOLS, YES)))
def test_every_yes_answers_the_question_that_was_asked(attr, text):
    assert got(text, asked=attr) == {attr: True}, text


@pytest.mark.parametrize("attr,text", list(itertools.product(BOOLS, NO)))
def test_every_no_answers_the_question_that_was_asked(attr, text):
    assert got(text, asked=attr) == {attr: False}, text


@pytest.mark.parametrize("text", YES + NO)
def test_yes_and_no_mean_nothing_without_a_question(text):
    assert got(text) == {}, text


RELATIONS = ["मेरे पिताजी", "मेरी माँ", "मेरे दादाजी", "मेरी पत्नी", "मेरे पति", "मेरे भाई", "my father", "my mother", "mere papa"]


@pytest.mark.parametrize("rel,n", list(itertools.product(RELATIONS, [30, 55, 68, 80])))
def test_a_relatives_age_is_never_the_speakers(rel, n):
    suffix = "साल के हैं" if rel.startswith("मे") and rel != "mere papa" else "years old"
    text = f"{rel} की उम्र {n} साल है" if suffix == "साल के हैं" else f"{rel} is {n} years old"
    g = got(text)
    assert "age" not in g, (text, g)
    assert "household_size" not in g, (text, g)


@pytest.mark.parametrize("n,word", [(1, "एक"), (2, "दो"), (3, "तीन"), (4, "चार"), (5, "पाँच"), (6, "छह"), (7, "सात"), (8, "आठ")])
def test_household_size_as_a_bare_answer_and_a_sentence(n, word):
    assert got(word, asked="household_size").get("household_size") == n
    assert got(f"हम {word} लोग हैं").get("household_size") == n
    assert got(f"मेरे परिवार में {word} लोग हैं").get("household_size") == n


MEMBERS = [(["मेरे पिताजी", "माता जी", "दादाजी", "मैं"], 4), (["मैं", "मेरी पत्नी", "दो बच्चे"], 4), (["मैं", "मेरी पत्नी"], 2),
           (["मेरे पिताजी", "मेरी माँ", "मेरा भाई", "मैं"], 4), (["मैं", "मेरी माँ"], 2), (["मैं", "मेरी पत्नी", "मेरी बेटी", "मेरा बेटा"], 4)]


@pytest.mark.parametrize("members,n", MEMBERS, ids=[str(n) + "-" + str(i) for i, (_, n) in enumerate(MEMBERS)])
def test_people_named_as_living_together_are_counted(members, n):
    text = "हमारे घर में " + " ".join(members[:-1]) + " और " + members[-1] + " हैं"
    assert got(text).get("household_size") == n, text


@pytest.mark.parametrize("text", [
    "मैं गाँव में रहता हूँ", "my wife and I are both 70", "मेरे पिताजी बीमार हैं", "I have two children", "मेरी बहन शहर में रहती है",
    "मेरी माँ और पिताजी गाँव में रहते हैं और मैं शहर में काम करता हूँ",
])
def test_no_household_size_is_guessed_from_a_passing_mention(text):
    assert "household_size" not in got(text), text


TELUGU = [("నా వయసు 62 సంవత్సరాలు", {"age": 62}), ("నేను ఆంధ్రప్రదేశ్ లో ఉంటాను", {"state": "Andhra Pradesh"}),
          ("మాది తెలంగాణ", {"state": "Telangana"}), ("నేను రైతును", {"occupation": "farmer"}),
          ("మా కుటుంబంలో 5 మంది ఉన్నారు", {"household_size": 5}), ("మాకు బీపీఎల్ కార్డు లేదు", {"bpl": False}),
          ("మాకు బీపీఎల్ కార్డు ఉంది", {"bpl": True}), ("నేను ఒక మహిళను", {"gender": "female"})]


@pytest.mark.parametrize("text,want", TELUGU, ids=[t for t, _ in TELUGU])
def test_telugu_statements(text, want):
    g = got(text)
    for k, v in want.items():
        assert g.get(k) == v, (text, g)


GENDER_ANSWERS = [("पुरुष", "male"), ("महिला", "female"), ("male", "male"), ("female", "female"), ("मर्द", "male"), ("औरत", "female"),
                  ("मैं लड़का हूँ", "male"), ("मैं लड़की हूँ", "female"), ("man", "male"), ("woman", "female")]


@pytest.mark.parametrize("text,want", GENDER_ANSWERS)
def test_gender_answers(text, want):
    assert got(text, asked="gender").get("gender") == want


@pytest.mark.parametrize("text", ["मेरा लड़का पाँच साल का है", "my son is a boy of ten", "मेरी लड़की स्कूल जाती है"])
def test_a_childs_gender_is_not_the_speakers(text):
    assert "gender" not in got(text), text
