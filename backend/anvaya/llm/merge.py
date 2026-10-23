"""Merge LLM facts into the deterministic extraction. The deterministic extractor stays primary:

- same attribute, same value      → keep the deterministic fact, note that both agree            (outcome agree)
- attribute only the LLM found    → add an unconfirmed candidate, source=llm, inferred=true     (outcome llm_only)
- different value, high-impact    → keep neither silently: hold the fact with both values, the
                                    citizen picks one ("60 या 70?")                             (outcome disagree)
- different value, low-impact     → keep the deterministic value but never auto-confirm it       (outcome disagree)

The existing safety rules apply to LLM facts as well: an age said next to a relation word (or equal to a relative's
age the deterministic extractor found) is never the applicant's age, naming the widow pension scheme says nothing
about the speaker's marital status (outcome dropped_scheme_name), and confusable spoken numbers are flagged.
Pure function: no DB, no Flask, so the eval command uses exactly the same code.
"""
import re

from .. import extraction


def _relative_age(fact: dict, relative_ages: set[int]) -> bool:
    if fact["value"] in relative_ages:
        return True
    norm, _ = extraction.numerize(fact["evidence"].translate(extraction._DIGITS))
    at = norm.find(str(fact["value"]))
    if at >= 0:
        return extraction._relation_before(norm, at) is not None
    return bool(extraction.RELATION.search(norm)) and not extraction.SELF.search(norm)


_WIDOW_WORD = re.compile(r"widow|vidhwa|vidhva|विधवा|వితంతు|విధవ", re.I)


def _scheme_name_only(fact: dict, utterance: str) -> bool:
    """An LLM reading of "widowed" (or "female" taken from the word widow) when the utterance only names the widow
    pension scheme ("विधवा पेंशन के बारे में बताइए") and says nothing about the speaker being a widow."""
    if not utterance or not extraction.WIDOW_PENSION.search(utterance) or extraction.WIDOW.search(utterance):
        return False
    if fact["attribute"] == "marital_status":
        return fact["value"] == "widowed"
    return fact["attribute"] == "gender" and bool(_WIDOW_WORD.search(fact["evidence"]))


def _llm_candidate(f: dict) -> dict:
    cand = {"attribute": f["attribute"], "value": f["value"], "raw_text": f["evidence"], "confidence": 0.6,
            "inferred": True, "source": "llm", "note": "Proposed by LLM extraction only; please confirm.",
            "confusable": False, "high_impact": f["attribute"] in extraction.HIGH_IMPACT}
    if isinstance(f["value"], int) and not isinstance(f["value"], bool):
        _, rewrites = extraction.numerize(f["evidence"].translate(extraction._DIGITS))
        extraction._heard(cand, str(f["value"]), rewrites)
    return cand


def merge(det_facts: list[dict], llm_facts: list[dict], other_people: list[dict],
          utterance: str = "") -> tuple[list[dict], dict]:
    """→ (candidates, {"outcomes": {attribute: outcome}, "disputed": [attribute]}). `utterance` is the original text,
    used for the scheme-name check."""
    relative_ages = {o["value"] for o in other_people if o["attribute"] == "age"}
    out = [dict(f) for f in det_facts]
    by_attr = {f["attribute"]: f for f in out}
    outcomes: dict[str, str] = {}
    disputed: list[str] = []
    for lf in llm_facts:
        attr = lf["attribute"]
        if attr == "age" and _relative_age(lf, relative_ages):
            outcomes[attr] = "dropped_relative"
            continue
        d = by_attr.get(attr)
        if d is None and _scheme_name_only(lf, utterance):
            outcomes[attr] = "dropped_scheme_name"
            continue
        if d is None:
            cand = _llm_candidate(lf)
            out.append(cand)
            by_attr[attr] = cand
            outcomes[attr] = "llm_only"
        elif d["value"] == lf["value"]:
            d["note"] = " ".join(filter(None, [d.get("note"), "Confirmed by both deterministic and LLM extraction."]))
            outcomes[attr] = "agree"
        else:
            outcomes[attr] = "disagree"
            d["hold"] = True  # never auto-confirmed
            if attr in extraction.HIGH_IMPACT:
                d["alternatives"] = [d["value"], lf["value"]]
                d["note"] = " ".join(filter(None, [d.get("note"), "Two different readings were heard; "
                                                                  "please choose the right one."]))
                disputed.append(attr)
            else:
                d["note"] = " ".join(filter(None, [d.get("note"), f"LLM extraction read this as “{lf['value']}”; "
                                                                  "please check."]))
    return out, {"outcomes": outcomes, "disputed": disputed}
