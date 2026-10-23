import pytest

from anvaya.extraction import extract


def got(text):
    return {f["attribute"]: f["value"] for f in extract(text)["facts"]}


def test_english_household():
    f = got("I am a 67 year old farmer from Guntur, Andhra Pradesh. We live in a village, family of 4. "
            "Our yearly income is 60,000 rupees. We have a BPL card and I do not get any pension.")
    assert f["age"] == 67 and f["state"] == "Andhra Pradesh" and f["district"] == "Guntur"
    assert f["household_size"] == 4 and f["annual_income"] == 60000 and f["bpl"] is True
    assert f["area"] == "rural" and f["occupation"] == "farmer" and f["receives_other_pension"] is False


def test_hindi_monthly_income_is_converted_and_marked_inferred():
    r = extract("मेरी उम्र 26 साल है, मैं बिहार के गाँव में रहती हूँ। विधवा हूँ। परिवार की आय 5000 रुपये महीना है। बीपीएल कार्ड है, कोई पेंशन नहीं मिलती।")
    f = {x["attribute"]: x for x in r["facts"]}
    assert f["age"]["value"] == 26 and f["state"]["value"] == "Bihar"
    assert f["annual_income"]["value"] == 60000 and f["annual_income"]["inferred"]
    assert f["marital_status"]["value"] == "widowed" and f["gender"]["value"] == "female"
    assert f["bpl"]["value"] is True and f["receives_other_pension"]["value"] is False


def test_telugu():
    f = got("నా వయస్సు 68 సంవత్సరాలు. నేను ఆంధ్రప్రదేశ్ లో ఒక గ్రామంలో ఉంటాను. మా ఆదాయం సంవత్సరానికి 50 వేలు. బీపీఎల్ కార్డు ఉంది. పెన్షన్ రావడం లేదు.")
    assert f["age"] == 68 and f["state"] == "Andhra Pradesh" and f["annual_income"] == 50000
    assert f["bpl"] is True and f["area"] == "rural" and f["receives_other_pension"] is False


def test_telugu_digits_normalized():
    assert got("నా వయస్సు ౬౫ సంవత్సరాలు")["age"] == 65


def test_lakh_units_and_hinglish():
    f = got("meri umar 62 saal hai, Maharashtra, income 1.5 lakh, no land")
    assert f["age"] == 62 and f["annual_income"] == 150000 and f["owns_cultivable_land"] is False


def test_age_not_confused_with_income():
    f = got("income is 65000 rupees and I am 70 years old")
    assert f["annual_income"] == 65000 and f["age"] == 70


def test_district_infers_state_as_inferred():
    r = extract("I live in Warangal")
    st = next(x for x in r["facts"] if x["attribute"] == "state")
    assert st["value"] == "Telangana" and st["inferred"]


def test_high_impact_flagged():
    r = extract("I am 60 years old in Punjab")
    assert all(f["high_impact"] for f in r["facts"] if f["attribute"] in ("age", "state"))


@pytest.mark.parametrize("text,term", [("I want budhapa pension", "old-age pension"), ("I am a rythu", "farmer")])
def test_dialect_glossary(text, term):
    assert term in [g["meaning"] for g in extract(text)["glossary"]]


def test_nothing_extracted_from_noise():
    assert extract("hello there")["facts"] == []


# ---------------------------------------------------------------- spoken numbers

def fact(text, attr):
    return next(f for f in extract(text)["facts"] if f["attribute"] == attr)


@pytest.mark.parametrize("text,attr,value", [
    ("मेरी उम्र साठ साल है", "age", 60),
    ("मेरी उम्र सत्तर साल है", "age", 70),
    ("साल भर में डेढ़ लाख की कमाई है", "annual_income", 150000),
    ("నా వయస్సు అరవై ఐదు సంవత్సరాలు", "age", 65),
    ("నెలకు పది వేలు సంపాదిస్తాను", "annual_income", 120000),
    ("meri umar saath saal hai", "age", 60),
    ("I am sixty five years old", "age", 65),
    ("my income is two lakh fifty thousand a year", "annual_income", 250000),
    ("I earn sixteen thousand a month", "annual_income", 192000),
    ("मेरी सालाना आय सवा दो लाख है", "annual_income", 225000),
    ("मेरी सालाना आय ढाई लाख है", "annual_income", 250000),
    ("income dedh lakh per year", "annual_income", 150000),
    ("yearly income 2,00,000 rupees", "annual_income", 200000),
    ("मेरी उम्र ६२ साल है", "age", 62),
    ("हम चार लोग हैं", "household_size", 4),
])
def test_number_words(text, attr, value):
    assert fact(text, attr)["value"] == value


def test_monthly_vs_yearly_follows_nearest_period_word():
    yearly = fact("साल भर में डेढ़ लाख की कमाई है", "annual_income")
    assert yearly["value"] == 150000 and not yearly["inferred"]
    monthly = fact("महीने की कमाई दस हज़ार है", "annual_income")
    assert monthly["value"] == 120000 and monthly["inferred"]


@pytest.mark.parametrize("text", ["एक गाँव में रहता हूँ", "I live with my family", "pass me a pen", "दो पैसे दो"])
def test_everyday_words_are_not_numbers(text):
    assert not any(f["attribute"] in ("age", "annual_income", "household_size") for f in extract(text)["facts"])


@pytest.mark.parametrize("text,alt", [
    ("मेरी उम्र साठ साल है", "सत्तर"),
    ("मेरी उम्र सत्तर साल है", "साठ"),
    ("I am sixty years old", "sixteen"),
    ("I am sixteen years old", "sixty"),
    ("నా వయస్సు అరవై సంవత్సరాలు", "డెబ్బై"),
])
def test_confusable_spoken_numbers_flagged(text, alt):
    f = fact(text, "age")
    assert f["confusable"] and alt in f["confusable_with"] and f["confidence"] <= 0.6
    assert f["heard_as"] in text and "confirm" in f["note"]


def test_digits_and_safe_words_are_not_confusable():
    assert not fact("मेरी उम्र 60 साल है", "age")["confusable"]
    assert not fact("मेरी उम्र पैंतीस साल है", "age")["confusable"]
    # A confusable tens word stays flagged inside a compound: అరవై ఐదు (65) can be heard as డెబ్బై ఐదు (75).
    assert fact("నా వయస్సు అరవై ఐదు సంవత్సరాలు", "age")["confusable"]


# ---------------------------------------------------------------- whose age is it

@pytest.mark.parametrize("text,relation", [
    ("मेरी माँ 67 साल की हैं, मेरी उम्र 35 है", "माँ"),
    ("मेरे पिता सड़सठ साल के हैं और मेरी उम्र पैंतीस साल है", "पिता"),
    ("మా అమ్మ వయస్సు 67 సంవత్సరాలు, నా వయస్సు 35 సంవత్సరాలు", "అమ్మ"),
    ("My mother is 67 years old and I am 35", "mother"),
    ("I am 35, my wife is 67 years old", "wife"),
])
def test_relative_age_not_attributed_to_applicant(text, relation):
    r = extract(text)
    assert got(text)["age"] == 35
    assert r["other_people"] == [{"attribute": "age", "value": 67, "relation": relation, "raw_text": r["other_people"][0]["raw_text"]}]


def test_only_relative_age_gives_no_applicant_age():
    r = extract("मेरी बेटी 12 साल की है")
    assert "age" not in got("मेरी बेटी 12 साल की है") and r["other_people"][0]["value"] == 12
