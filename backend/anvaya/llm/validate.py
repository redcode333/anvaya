"""Validation of LLM output: shape → schema → value (profile.validate_value) → evidence grounding."""
import json
import re

# Profile attributes the LLM may propose (no applicant_name or other identifiers).
ATTRIBUTES = ["state", "district", "age", "annual_income", "household_size", "gender", "marital_status", "area",
              "occupation", "bpl", "receives_other_pension", "owns_cultivable_land", "has_bank_account",
              "owns_pucca_house"]


class InvalidOutput(Exception):
    """The reply is not the expected JSON shape; the message is fed back to the model on the one retry."""


def parse(content: str) -> list[dict]:
    text = content.strip()
    fence = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", text, re.S)
    if fence:
        text = fence.group(1)
    try:
        data = json.loads(text)
    except ValueError as e:
        raise InvalidOutput(f"not valid JSON ({e.msg} at position {e.pos})")
    if not isinstance(data, dict) or not isinstance(data.get("facts"), list):
        raise InvalidOutput('expected an object with a "facts" array')
    for i, item in enumerate(data["facts"]):
        if not isinstance(item, dict) or not {"attribute", "value", "evidence"} <= item.keys():
            raise InvalidOutput(f"facts[{i}] must have attribute, value and evidence")
        if not isinstance(item["attribute"], str) or not isinstance(item["evidence"], str):
            raise InvalidOutput(f"facts[{i}].attribute and .evidence must be strings")
    return data["facts"]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


def grounded(evidence: str, sources: list[str]) -> bool:
    """Evidence must be a (case- and whitespace-insensitive) substring of the original or its translation."""
    ev = _norm(evidence)
    return len(ev) >= 2 and any(ev in _norm(s) for s in sources if s)


def check(items: list[dict], utterance: str, translation: str | None) -> tuple[list[dict], list[dict]]:
    """→ (valid facts, dropped [{attribute, reason}]) where reason is invalid | evidence. One fact per attribute."""
    from ..common import ApiError
    from ..profile import validate_value

    facts, dropped, seen = [], [], set()
    for item in items:
        attr = item["attribute"]
        if attr not in ATTRIBUTES:
            dropped.append({"attribute": "unknown", "reason": "invalid"})
            continue
        try:
            value = validate_value(attr, item["value"])
        except ApiError:
            dropped.append({"attribute": attr, "reason": "invalid"})
            continue
        if not grounded(item["evidence"], [utterance, translation]):
            dropped.append({"attribute": attr, "reason": "evidence"})
            continue
        if attr in seen:
            continue
        seen.add(attr)
        facts.append({"attribute": attr, "value": value, "evidence": item["evidence"].strip()[:200]})
    return facts, dropped
