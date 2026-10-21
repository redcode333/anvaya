import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from anvaya import rules_engine as re_

RULES = {r["rule_id"]: r for r in json.loads(
    (Path(__file__).resolve().parent.parent / "anvaya" / "data" / "golden_rules.json").read_text(encoding="utf-8"))["rules"]}
META = {"review_status": "team_reviewed", "source_verified_at": None, "scheme_name": "x", "bundle_version": "t"}
FIXTURES = json.loads((Path(__file__).resolve().parent / "fixtures" / "engine_cases.json").read_text(encoding="utf-8"))


def facts(**kw):
    return {k: {"fact_id": f"F-{k}", "value": v, "confirmed": True} for k, v in kw.items()}


def test_pass_gives_provisional_when_source_unverified():
    r = re_.evaluate(RULES["R_IGNOAPS_BIHAR"], facts(state="Bihar", age=62, bpl=True, receives_other_pension=False), {}, META)
    assert r["outcome"] == re_.PROVISIONAL
    assert {c["outcome"] for c in r["criteria"]} == {re_.PASS}
    codes = [x["code"] for x in r["decision_reason"]]
    assert "EVIDENCE_NOT_VERIFIED" in codes and "SOURCE_NOT_VERIFIED" in codes


def test_failed_criterion_is_mismatch():
    r = re_.evaluate(RULES["R_IGNOAPS_MAHARASHTRA"], facts(state="Maharashtra", age=62, bpl=True, receives_other_pension=False), {}, META)
    assert r["outcome"] == re_.MISMATCH
    failed = [c for c in r["criteria"] if c["outcome"] == re_.FAIL]
    assert failed[0]["fact"] == "age" and failed[0]["observed"] == 62 and failed[0]["expected"] == 65


def test_missing_fact_is_unknown_and_insufficient():
    r = re_.evaluate(RULES["R_IGNOAPS_BIHAR"], facts(state="Bihar", age=62), {}, META)
    assert r["outcome"] == re_.INSUFFICIENT
    assert set(r["missing_facts"]) == {"bpl", "receives_other_pension"}


def test_unconfirmed_fact_is_never_used():
    f = facts(state="Bihar", bpl=True, receives_other_pension=False)
    f["age"] = {"fact_id": "F-age", "value": 62, "confirmed": False}
    r = re_.evaluate(RULES["R_IGNOAPS_BIHAR"], f, {}, META)
    age = next(c for c in r["criteria"] if c["fact"] == "age")
    assert age["outcome"] == re_.UNKNOWN and r["outcome"] == re_.INSUFFICIENT


def test_fail_takes_precedence_over_unknown():
    r = re_.evaluate(RULES["R_IGNOAPS_MAHARASHTRA"], facts(age=40), {}, META)
    assert r["outcome"] == re_.MISMATCH


def test_rule_needing_review():
    r = re_.evaluate(RULES["R_AP_SPECTACLES_SENIOR"], facts(state="Andhra Pradesh", age=70), {},
                     {**META, "review_status": "needs_review"})
    assert r["outcome"] == re_.NEEDS_REVIEW


def test_match_requires_verified_docs_verified_source_and_no_manual_checks():
    rule = RULES["R_IGNOAPS_BIHAR"]
    f = facts(state="Bihar", age=62, bpl=True, receives_other_pension=False)
    docs = {d: "verified" for d in rule["evidence_requirements"]}
    fresh = {**META, "source_verified_at": datetime.now(timezone.utc).isoformat()}
    assert re_.evaluate(rule, f, docs, fresh)["outcome"] == re_.MATCH
    # A citizen's "available" declaration is not verification.
    assert re_.evaluate(rule, f, {d: "available" for d in docs}, fresh)["outcome"] == re_.PROVISIONAL
    stale = {**META, "source_verified_at": (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()}
    r = re_.evaluate(rule, f, docs, stale)
    assert r["outcome"] == re_.PROVISIONAL and any(x["code"] == "SOURCE_STALE" for x in r["decision_reason"])


def test_between_operator_bounds_inclusive():
    rule = RULES["R_APY"]
    for age, ok in [(17, False), (18, True), (40, True), (41, False)]:
        r = re_.evaluate(rule, facts(age=age, has_bank_account=True), {}, META)
        assert (r["outcome"] != re_.MISMATCH) == ok, age


def test_trace_links_input_fact_ids_and_quotes():
    r = re_.evaluate(RULES["R_PM_KISAN"], facts(owns_cultivable_land=True), {}, META)
    assert r["input_fact_ids"] == ["F-owns_cultivable_land"]
    assert r["criteria"][0]["quote"].startswith("All landholding farmers")


def test_deterministic():
    f = facts(state="Bihar", age=62, bpl=True, receives_other_pension=False)
    at = datetime(2026, 10, 21, tzinfo=timezone.utc)
    assert re_.evaluate(RULES["R_IGNOAPS_BIHAR"], f, {}, META, at) == re_.evaluate(RULES["R_IGNOAPS_BIHAR"], f, {}, META, at)


@pytest.mark.parametrize("case", FIXTURES, ids=[c["name"] for c in FIXTURES])
def test_shared_fixtures(case):
    """Same fixtures are run by frontend/src/offline/rulesEngine.test.ts to keep the engines aligned."""
    r = re_.evaluate(RULES[case["rule_id"]], facts(**case["facts"]), case.get("docs", {}), {**META, **case.get("meta", {})})
    assert r["outcome"] == case["expected"]
