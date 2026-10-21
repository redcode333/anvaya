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
