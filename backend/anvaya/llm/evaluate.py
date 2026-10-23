"""`python -m anvaya.manage eval-extraction`: per-attribute precision/recall of deterministic extraction alone vs
deterministic + LLM (merged exactly as in a conversation turn) on data/fixtures/extraction_eval.json (demo data).

Scoring per (utterance, attribute):
- a fact whose value equals the expected value is a true positive;
- a disputed fact (two readings held for the citizen to choose) counts as correct only if the expected value is one
  of the offered alternatives;
- any other fact is a false positive, i.e. a wrong fact that would reach the citizen's confirmation step;
- an expected attribute without a correct fact is a false negative.
"""
import json
import time
from collections import Counter, defaultdict
from pathlib import Path

from .. import extraction
from ..config import PROJECT_DIR
from . import enabled, merge, run_turn
from .validate import ATTRIBUTES

FIXTURE = PROJECT_DIR / "data" / "fixtures" / "extraction_eval.json"
TARGET_HIGH_IMPACT_PRECISION = 0.95


def _pred(facts: list[dict]) -> dict:
    return {f["attribute"]: f for f in facts if f["attribute"] in ATTRIBUTES}


def _score(pred: dict, expected: dict, tally: dict, wrong: list, item_id: str) -> None:
    for attr in ATTRIBUTES:
        exp, p = expected.get(attr), pred.get(attr)
        correct = p is not None and exp is not None and (p["value"] == exp or exp in (p.get("alternatives") or []))
        if p is not None:
            tally[attr]["tp" if correct else "fp"] += 1
            if not correct:
                wrong.append({"id": item_id, "attribute": attr, "got": p["value"], "expected": exp,
                              "source": p.get("source", "deterministic"), "alternatives": p.get("alternatives")})
        if exp is not None and not correct:
            tally[attr]["fn"] += 1


def _pr(t: Counter) -> tuple[float | None, float | None]:
    p = t["tp"] / (t["tp"] + t["fp"]) if t["tp"] + t["fp"] else None
    r = t["tp"] / (t["tp"] + t["fn"]) if t["tp"] + t["fn"] else None
    return p, r


def _sum(tally: dict, attrs) -> Counter:
    total = Counter()
    for a in attrs:
        total.update(tally[a])
    return total


def run(path: Path = FIXTURE, use_llm: bool = True) -> dict:
    items = json.loads(Path(path).read_text(encoding="utf-8"))["items"]
    use_llm = use_llm and enabled()
    det_t, mrg_t = defaultdict(Counter), defaultdict(Counter)
    det_wrong, mrg_wrong, runs, outcomes, disputes = [], [], Counter(), Counter(), 0
    latencies = []
    for it in items:
        det = extraction.extract(it["utterance"])
        _score(_pred(det["facts"]), it["expected"], det_t, det_wrong, it["id"])
        merged = det["facts"]
        if use_llm:
            t0 = time.perf_counter()
            res = run_turn(it["utterance"])
            latencies.append((time.perf_counter() - t0) * 1000)
            runs[(res["provider"] or "-", res["result"], "cached" if res["cached"] else "live")] += 1
            outcomes.update(d["reason"] == "evidence" and "dropped_evidence" or "dropped_invalid" for d in res["dropped"])
            if res["result"] == "ok":
                merged, info = merge.merge(det["facts"], res["facts"], det["other_people"], it["utterance"])
                outcomes.update(info["outcomes"].values())
                disputes += len(info["disputed"])
        _score(_pred(merged), it["expected"], mrg_t, mrg_wrong, it["id"])
    hi = sorted(extraction.HIGH_IMPACT)
    return {"items": len(items), "llm_used": use_llm, "per_attribute": {
        a: {"deterministic": _pr(det_t[a]), "merged": _pr(mrg_t[a]), "support": det_t[a]["tp"] + det_t[a]["fn"]}
        for a in ATTRIBUTES},
        "high_impact": {"deterministic": _pr(_sum(det_t, hi)), "merged": _pr(_sum(mrg_t, hi))},
        "overall": {"deterministic": _pr(_sum(det_t, ATTRIBUTES)), "merged": _pr(_sum(mrg_t, ATTRIBUTES))},
        "wrong_reaching_confirmation": {"deterministic": det_wrong, "merged": mrg_wrong},
        "llm_runs": {" / ".join(k): v for k, v in sorted(runs.items())}, "merge_outcomes": dict(outcomes),
        "disputes": disputes, "llm_latency_ms": latencies}


def _f(x) -> str:
    return "  -  " if x is None else f"{x:.3f}"


def report(res: dict) -> str:
    lines = [f"extraction eval: {res['items']} demo utterances; LLM {'ON' if res['llm_used'] else 'OFF (deterministic only)'}",
             "", f"{'attribute':<24}{'n':>4}   {'det P':>6} {'det R':>6}   {'mrg P':>6} {'mrg R':>6}"]
    for a, r in res["per_attribute"].items():
        (dp, dr), (mp, mr) = r["deterministic"], r["merged"]
        mark = " *" if a in extraction.HIGH_IMPACT else ""
        lines.append(f"{a + mark:<24}{r['support']:>4}   {_f(dp):>6} {_f(dr):>6}   {_f(mp):>6} {_f(mr):>6}")
    for label in ("high_impact", "overall"):
        (dp, dr), (mp, mr) = res[label]["deterministic"], res[label]["merged"]
        lines.append(f"{label.upper().replace('_', '-') + ' (micro)':<24}{'':>4}   {_f(dp):>6} {_f(dr):>6}   {_f(mp):>6} {_f(mr):>6}")
    lines.append("(* = high-impact: age, annual_income, state, area, household_size)")
    dw, mw = res["wrong_reaching_confirmation"]["deterministic"], res["wrong_reaching_confirmation"]["merged"]
    hi_w = lambda ws: sum(w["attribute"] in extraction.HIGH_IMPACT for w in ws)
    lines += ["", f"wrong facts that would reach confirmation: deterministic {len(dw)} (high-impact {hi_w(dw)}), "
                  f"merged {len(mw)} (high-impact {hi_w(mw)})"]
    for w in mw:
        alt = f" alternatives={w['alternatives']}" if w["alternatives"] else ""
        lines.append(f"  merged  {w['id']:<6} {w['attribute']:<22} got={w['got']!r} expected={w['expected']!r} "
                     f"source={w['source']}{alt}")
    if res["llm_used"]:
        lat = sorted(res["llm_latency_ms"])
        lines += ["", f"LLM runs (provider / result / cache): {res['llm_runs']}",
                  f"merge outcomes: {res['merge_outcomes']}; disputes held for the citizen: {res['disputes']}",
                  f"turn latency ms: median {lat[len(lat) // 2]:.0f}, max {lat[-1]:.0f}" if lat else ""]
    mp = res["high_impact"]["merged"][0]
    ok = mp is not None and mp >= TARGET_HIGH_IMPACT_PRECISION
    lines += ["", f"target merged high-impact precision >= {TARGET_HIGH_IMPACT_PRECISION}: "
                  f"{_f(mp)} -> {'MET' if ok else 'NOT MET'}"]
    return "\n".join(lines)
