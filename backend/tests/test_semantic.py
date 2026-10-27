"""Conversational understanding: short answers to the bot's last question, spoken-style statements, household
listings and gendered verb forms, drawn from tests/fixtures/semantic_cases.json."""
import json
from pathlib import Path

import pytest

from anvaya import extraction

CASES = json.loads((Path(__file__).parent / "fixtures" / "semantic_cases.json").read_text(encoding="utf-8"))["items"]


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_semantic_case(case):
    got = {f["attribute"]: f["value"] for f in extraction.extract(case["utterance"], asked=case.get("asked"))["facts"]}
    for attr, want in case["expected"].items():
        assert got.get(attr) == want, f"{attr}: wanted {want!r}, got {got.get(attr)!r} (all: {got})"
    for attr in case.get("forbid", []):
        assert attr not in got, f"{attr} must not be extracted, got {got[attr]!r}"


def test_a_bare_yes_or_no_is_nothing_without_a_question():
    for text in ("हाँ", "नहीं", "yes", "no", "जी"):
        assert extraction.extract(text)["facts"] == [], text


def test_a_yes_to_a_question_about_another_attribute_is_not_applied():
    # The bot asked about BPL; a bare "no" must not turn into a bank-account fact.
    got = {f["attribute"] for f in extraction.extract("नहीं", asked="bpl")["facts"]}
    assert got == {"bpl"}


def test_inferred_gender_is_marked_inferred():
    f = {f["attribute"]: f for f in extraction.extract("मैं सुंदरनगर में रहती हूँ")["facts"]}["gender"]
    assert f["inferred"] and f["value"] == "female"
