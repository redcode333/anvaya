"""Deterministic, versioned eligibility evaluator.

The evaluator is a pure function of (rule, confirmed facts, document marks, rule metadata,
evaluation time). It never consults an LLM. Unconfirmed or missing facts are UNKNOWN.

The same algorithm is mirrored in frontend/src/offline/rulesEngine.ts for offline kiosk
pre-screening; tests/test_rules_engine.py and the shared fixtures keep them aligned.
"""
from datetime import datetime, timedelta, timezone

PASS, FAIL, UNKNOWN = "PASS", "FAIL", "UNKNOWN"

MATCH = "MATCH"
PROVISIONAL = "PROVISIONAL"
MISMATCH = "MISMATCH"
INSUFFICIENT = "INSUFFICIENT_INFORMATION"
NEEDS_REVIEW = "NEEDS_HUMAN_REVIEW"

OUTCOME_ORDER = {MATCH: 0, PROVISIONAL: 1, INSUFFICIENT: 2, NEEDS_REVIEW: 3, MISMATCH: 4}

OPS = {"==", "!=", ">=", "<=", ">", "<", "between", "in", "is_true", "is_false"}


def _describe_expected(op: str, value) -> str:
    if op == "is_true":
        return "yes"
    if op == "is_false":
        return "no"
    if op == "between":
        return f"{value[0]}–{value[1]}"
    if op == "in":
        return " / ".join(map(str, value))
    return f"{op} {value}"


def compare(op: str, observed, expected) -> bool:
    if op not in OPS:
        raise ValueError(f"unsupported operator {op}")
    if op == "is_true":
        return observed is True
    if op == "is_false":
        return observed is False
    if op == "==":
        return _norm(observed) == _norm(expected)
    if op == "!=":
        return _norm(observed) != _norm(expected)
    if op == "in":
        return _norm(observed) in {_norm(v) for v in expected}
    num = float(observed)
    if op == "between":
        return float(expected[0]) <= num <= float(expected[1])
    return {">=": num >= expected, "<=": num <= expected, ">": num > expected, "<": num < expected}[op]


def _norm(v):
    return v.strip().lower() if isinstance(v, str) else v


def evaluate_criterion(crit: dict, facts: dict) -> dict:
    fact = facts.get(crit["fact"])
    base = {
        "criterion_id": crit["id"],
        "fact": crit["fact"],
        "operator": crit["op"],
        "expected": crit.get("value"),
        "expected_text": _describe_expected(crit["op"], crit.get("value")),
        "quote": crit.get("quote"),
        "note": crit.get("note"),
        "fact_id": None,
        "observed": None,
    }
    if fact is None or not fact.get("confirmed"):
        reason = "not provided" if fact is None else "not yet confirmed by the citizen"
        return {**base, "outcome": UNKNOWN, "fact_id": fact and fact["fact_id"],
                "explanation": f"{crit['fact']} is {reason}, so this criterion cannot be checked."}
    observed = fact["value"]
    try:
        ok = compare(crit["op"], observed, crit.get("value"))
    except (TypeError, ValueError):
        return {**base, "outcome": UNKNOWN, "fact_id": fact["fact_id"], "observed": observed,
                "explanation": f"{crit['fact']} value {observed!r} could not be compared."}
    return {
        **base,
        "outcome": PASS if ok else FAIL,
        "fact_id": fact["fact_id"],
        "observed": observed,
        "explanation": (
            f"{crit['fact']} = {observed} satisfies {base['expected_text']}"
            if ok else f"{crit['fact']} = {observed} does not satisfy {base['expected_text']}"
        ),
    }


def evaluate(rule: dict, facts: dict, doc_marks: dict, meta: dict, at: datetime | None = None) -> dict:
    """Evaluate one rule.

    facts: {attribute: {"fact_id", "value", "confirmed"}}
    doc_marks: {doc_key: status} where status in available|missing|expired|unknown|verified.
        Only "verified" (settable by a reviewer) satisfies an evidence requirement.
    meta: {"review_status", "source_verified_at", "source_url", "source_id", "imported_at",
           "bundle_version", "scheme_name"}
    """
    at = at or datetime.now(timezone.utc)
    criteria = [evaluate_criterion(c, facts) for c in rule["all"]]
    failed = [c for c in criteria if c["outcome"] == FAIL]
    unknown = [c for c in criteria if c["outcome"] == UNKNOWN]

    evidence = []
    for doc in rule.get("evidence_requirements", []):
        status = doc_marks.get(doc, "unknown")
        evidence.append({"doc_key": doc, "status": status, "satisfied": status == "verified"})
    gaps = [e["doc_key"] for e in evidence if e["status"] in ("missing", "expired", "unknown")]
    unverified = [e["doc_key"] for e in evidence if not e["satisfied"]]

    verified_at = meta.get("source_verified_at")
    freshness_days = rule.get("freshness_days")
    stale = True
    if verified_at:
        vdt = datetime.fromisoformat(verified_at)
        if vdt.tzinfo is None:
            vdt = vdt.replace(tzinfo=timezone.utc)
        stale = freshness_days is not None and at - vdt > timedelta(days=freshness_days)

    reasons: list[dict] = []
    if failed:
        outcome = MISMATCH
        for c in failed:
            reasons.append({"code": "CRITERION_FAILED", "criterion_id": c["criterion_id"], "text": c["explanation"]})
    elif unknown:
        outcome = INSUFFICIENT
        for c in unknown:
            reasons.append({"code": "FACT_UNKNOWN", "criterion_id": c["criterion_id"], "fact": c["fact"], "text": c["explanation"]})
    elif meta.get("review_status") != "team_reviewed":
        outcome = NEEDS_REVIEW
        reasons.append({"code": "RULE_NEEDS_REVIEW", "text": rule.get("review_note") or "Rule text or source is ambiguous and awaits steward review."})
    else:
        reasons.append({"code": "CRITERIA_PASSED", "text": "All structured criteria pass on confirmed facts."})
        blockers = []
        if unverified:
            blockers.append({"code": "EVIDENCE_NOT_VERIFIED", "docs": unverified,
                             "text": "Required documents are not verified by a reviewer: " + ", ".join(unverified)})
        if rule.get("manual_checks"):
            blockers.append({"code": "MANUAL_CHECKS_PENDING", "text": "Some conditions can only be checked by an officer."})
        if not verified_at:
            blockers.append({"code": "SOURCE_NOT_VERIFIED", "text": "Rule has not been verified against the official source."})
        elif stale:
            blockers.append({"code": "SOURCE_STALE", "text": f"Source verification is older than {freshness_days} days."})
        reasons.extend(blockers)
        outcome = PROVISIONAL if blockers else MATCH

    return {
        "scheme_id": rule["scheme_id"],
        "scheme_name": meta.get("scheme_name"),
        "rule_id": rule["rule_id"],
        "rule_version": rule["version"],
        "bundle_version": meta.get("bundle_version"),
        "jurisdiction": rule["jurisdiction"],
        "outcome": outcome,
        "decision_reason": reasons,
        "criteria": criteria,
        "manual_checks": rule.get("manual_checks", []),
        "evidence": evidence,
        "evidence_note": rule.get("evidence_note"),
        "document_gaps": gaps,
        "missing_facts": sorted({c["fact"] for c in unknown}),
        "input_fact_ids": sorted({c["fact_id"] for c in criteria if c["fact_id"]}),
        "source": {
            "source_id": f"SRC_{rule['scheme_id']}",
            "source_url": meta.get("source_url"),
            "imported_at": meta.get("imported_at"),
            "rule_reviewed_at": meta.get("reviewed_at"),
            "source_verified_at": verified_at,
            "review_status": meta.get("review_status"),
            "stale_or_unverified": stale,
        },
        "evaluated_at": at.isoformat(timespec="seconds"),
    }


def sort_results(results: list[dict]) -> list[dict]:
    return sorted(results, key=lambda r: (OUTCOME_ORDER[r["outcome"]], r["scheme_name"] or ""))
