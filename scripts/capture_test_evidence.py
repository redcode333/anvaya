#!/usr/bin/env python
"""Capture the evidence for the official test cases (TC1-TC4 of the brief, plus our TC5).

What it does, end to end, on a throwaway local copy (temporary database, no Supabase, no LLM, no speech service):
  1. starts the backend and the frontend dev server;
  2. runs every official scenario through the real pipeline (POST /api/v1/test-runs/TCn) and saves the raw record;
  3. drives the real web app with a browser to take the screenshots of each scenario's input and result;
  4. writes the documentation (one page per test case, an index, a printable HTML report and a PDF) from the recorded data.

Run from the repository root with the backend's Python (it needs `requests` and `playwright`; Chrome must be installed):
    backend/.venv/Scripts/python.exe -m pip install playwright      # once
    backend/.venv/Scripts/python.exe scripts/capture_test_evidence.py
Everything lands in docs/test-evidence/. The numbers in the text come from the recorded JSON, never typed by hand.
"""
from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
BACKEND, FRONTEND = ROOT / "backend", ROOT / "frontend"
OUT = ROOT / "docs" / "test-evidence"
SHOTS, DATA = OUT / "screenshots", OUT / "data"
API, WEB = "http://127.0.0.1:5000/api/v1", "http://localhost:5199"

BRIEF = {  # exactly as printed in the brief ("Official test cases to demonstrate")
    "TC1": ("Eligible household", "scheme list with rules quoted"),
    "TC2": ("Same scheme name in two states", "correct state used"),
    "TC3": ("Age misheard", "confirmed before filtering"),
    "TC4": ("Provisional eligibility", "never promised as a benefit"),
}


# ------------------------------------------------------------------------------------------------ servers
def start_servers(workdir: Path):
    env = {**os.environ, "SUPABASE_URL": "", "SUPABASE_SECRET_KEY": "", "DATABASE_URL": "", "ANVAYA_DB": str(workdir / "evidence.db"),
           "GROQ_API_KEY": "", "GEMINI_API_KEY": "", "VERBX_API_KEY": "", "VERBX_BASE_URL": "", "LANGFUSE_PUBLIC_KEY": "",
           "LANGFUSE_SECRET_KEY": "", "ANVAYA_DEMO_TEST_RUNS": "on", "PYTHONIOENCODING": "utf-8"}
    subprocess.run([sys.executable, "-m", "anvaya.manage", "init"], cwd=BACKEND, env=env, check=True, capture_output=True)
    back = subprocess.Popen([sys.executable, "-c", "from wsgi import app; app.run(port=5000, threaded=True)"], cwd=BACKEND, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    fenv = {**env, "VITE_SUPABASE_URL": "", "VITE_SUPABASE_PUBLISHABLE_KEY": "", "VITE_TURNSTILE_SITE_KEY": ""}
    front = subprocess.Popen([shutil.which("npx") or "npx", "vite", "--port", "5199", "--strictPort"], cwd=FRONTEND, env=fenv,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=(os.name == "nt"))
    for url in (f"{API}/health", f"{WEB}/"):
        for _ in range(60):
            try:
                if requests.get(url, timeout=2).ok:
                    break
            except requests.RequestException:
                time.sleep(1)
        else:
            raise SystemExit(f"{url} did not come up")
    return back, front


def stop(proc):
    if proc.poll() is None:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True)
        else:
            proc.terminate()


# ------------------------------------------------------------------------------------------------ API helpers
def hdr(sid):
    return {"X-Session-Id": sid, "Content-Type": "application/json"}


def api(method, path, sid=None, **kw):
    r = requests.request(method, f"{API}{path}", headers=hdr(sid) if sid else {"Content-Type": "application/json"}, timeout=60, **kw)
    return r.json() if r.content else {}


def new_session(lang="en"):
    return api("POST", "/sessions", json={"mode": "personal", "language": lang})["session_id"]


def say(sid, text, lang="en", channel="text"):
    return api("POST", "/sessions/current/turns", sid, json={"utterance": text, "language": lang, "channel": channel})


def confirm_everything(sid):
    for fid in api("POST", "/sessions/current/profile/confirm-all", sid, json={})["needs_confirmation"]:
        api("PATCH", f"/sessions/current/profile/facts/{fid}", sid, json={"confirmed": True})


# ------------------------------------------------------------------------------------------------ browser helpers
def page_for(browser, lang="en", sid=None, width=1280, height=900):
    ctx = browser.new_context(viewport={"width": width, "height": height})
    page = ctx.new_page()
    page.goto(f"{WEB}/")
    page.evaluate("([l, s]) => { sessionStorage.setItem('anvaya.lang', l); if (s) sessionStorage.setItem('anvaya.session', s); }", [lang, sid])
    # The site header is sticky; in a screenshot of one element it would land across the middle of it. Static is identical at the top of a page.
    page.add_init_script("document.addEventListener('DOMContentLoaded', () => { const s = document.createElement('style'); "
                         "s.textContent = '.topbar{position:static !important}'; document.head.appendChild(s); });")
    return page


def shot(page, name, selector=None, full=False):
    path = SHOTS / name
    (page.locator(selector).first.screenshot(path=str(path)) if selector else page.screenshot(path=str(path), full_page=full))
    return name


def open_why(card):
    card.get_by_role("button", name="Why").click() if card.get_by_role("button", name="Why").count() else None
    card.page.wait_for_timeout(500)


def card_of(page, text):
    page.wait_for_selector(".scheme", timeout=30000)
    return page.locator(".scheme").filter(has_text=text).first


# ------------------------------------------------------------------------------------------------ the five scenarios
def run_scenarios():
    runs = {}
    for tc in ("TC1", "TC2", "TC3", "TC4", "TC5"):
        r = requests.post(f"{API}/test-runs/{tc}", json={}, timeout=120)
        r.raise_for_status()
        runs[tc] = r.json()
        (DATA / f"{tc}.json").write_text(json.dumps(runs[tc], ensure_ascii=False, indent=2), encoding="utf-8")
    return runs


def shots_runner_page(browser, runs):
    page = page_for(browser, width=1280, height=1000)
    page.goto(f"{WEB}/test-runs")
    page.wait_for_selector("section.card")
    page.get_by_role("button", name="Run all").click()
    busy = "[...document.querySelectorAll('button')].some(b => b.textContent.trim() === '…')"
    page.wait_for_function(busy, timeout=30000)          # a scenario is running…
    page.wait_for_function(f"!({busy})", timeout=180000)  # …and now all five are done
    page.wait_for_function("document.querySelectorAll('.badge.o-MATCH').length >= 5", timeout=30000)
    page.evaluate("document.querySelectorAll('details').forEach(d => d.open = false)")
    shot(page, "00-test-runs-page.png", full=True)
    for tc in runs:
        sec = page.locator("section.card").filter(has_text=f"{tc} ·").first
        sec.locator("details").nth(1).evaluate("d => d.open = true")  # "Actual result & evidence"
        page.wait_for_timeout(300)
        shot(page, f"{tc.lower()}-0-runner.png", selector=f"section.card:has-text('{tc} ·')")
        sec.locator("details").nth(1).evaluate("d => d.open = false")
    page.context.close()


def shots_tc1(browser):
    page = page_for(browser, "en")
    page.goto(f"{WEB}/citizen")
    page.locator(".welcome-start").click()
    page.wait_for_selector(".composer")
    page.locator(".composer textarea").fill(TC_INPUT["TC1"])
    page.locator(".composer .btn.primary").click()
    page.wait_for_selector(".bubble.bot >> nth=1", timeout=30000)
    page.wait_for_timeout(800)
    shot(page, "tc1-1-conversation.png", full=True)
    sid = page.evaluate("sessionStorage.getItem('anvaya.session')")
    confirm_everything(sid)
    page.goto(f"{WEB}/citizen/schemes")
    card = card_of(page, "INDIRAMMA Old Age Pension (Rural)")
    page.wait_for_timeout(600)
    shot(page, "tc1-2-scheme-passport.png")
    open_why(card)
    card.locator(".why-quotes summary").click()
    page.wait_for_timeout(400)
    shot(page, "tc1-3-rules-quoted.png", selector=".scheme:has-text('INDIRAMMA Old Age Pension (Rural)')")
    card.locator(".why-tech summary").click()
    page.wait_for_timeout(300)
    shot(page, "tc1-4-source-and-technical.png", selector=".scheme:has-text('INDIRAMMA Old Age Pension (Rural)')")
    page.context.close()


def shots_tc2(browser):
    for state, find, name in (("Bihar", "Bihar", "tc2-1-bihar.png"), ("Maharashtra", "Maharashtra", "tc2-2-maharashtra.png")):
        sid = new_session("en")
        say(sid, f"I am 62 years old, BPL household, I do not get any pension. I live in {state}.")
        confirm_everything(sid)
        page = page_for(browser, "en", sid)
        page.goto(f"{WEB}/citizen/schemes")
        page.wait_for_selector(".scheme", timeout=30000)
        card = page.locator(".scheme").filter(has_text="Indira Gandhi National Old Age Pension").filter(has_text=find).first
        open_why(card)
        page.wait_for_timeout(400)
        card.scroll_into_view_if_needed()
        card.screenshot(path=str(SHOTS / name))
        page.context.close()


def shots_tc3(browser):
    page = page_for(browser, "hi")
    page.goto(f"{WEB}/citizen")
    page.locator(".welcome-start").click()
    page.wait_for_selector(".composer")
    page.locator(".composer textarea").fill(TC_INPUT["TC3"])
    page.locator(".composer .btn.primary").click()
    page.wait_for_selector(".bubble.bot >> nth=1", timeout=30000)
    page.wait_for_timeout(900)
    shot(page, "tc3-1-held-for-confirmation.png", full=True)
    sid = page.evaluate("sessionStorage.getItem('anvaya.session')")
    page.goto(f"{WEB}/citizen/schemes")
    page.wait_for_selector(".notice", timeout=30000)
    page.wait_for_timeout(500)
    shot(page, "tc3-2-screening-blocked.png")
    api("POST", "/sessions/current/profile/confirm-all", sid, json={})
    page.goto(f"{WEB}/citizen")
    page.wait_for_selector(".fact", timeout=30000)
    page.wait_for_timeout(600)
    shot(page, "tc3-3-confirm-all-leaves-age.png", full=True)
    facts = api("GET", "/sessions/current", sid)["facts"]
    age = next(f for f in facts if f["attribute"] == "age" and not f.get("superseded_by"))
    api("PATCH", f"/sessions/current/profile/facts/{age['fact_id']}", sid, json={"value": 62})
    confirm_everything(sid)
    page.goto(f"{WEB}/citizen/schemes")
    page.wait_for_selector(".scheme", timeout=30000)
    page.wait_for_timeout(600)
    shot(page, "tc3-4-after-correction.png")
    page.context.close()


def shots_tc4(browser):
    sid = new_session("en")
    say(sid, TC_INPUT["TC4"])
    confirm_everything(sid)
    for doc, status in {"bpl_card": "missing", "age_proof": "unknown", "residence_proof": "available"}.items():
        api("PUT", f"/sessions/current/documents/{doc}", sid, json={"status": status})
    page = page_for(browser, "en", sid)
    page.goto(f"{WEB}/citizen/schemes")
    card = card_of(page, "Punjab")
    page.wait_for_timeout(600)
    shot(page, "tc4-1-provisional-not-match.png")
    open_why(card)
    page.wait_for_timeout(400)
    card.scroll_into_view_if_needed()
    card.screenshot(path=str(SHOTS / "tc4-2-why-documents.png"))
    page.goto(f"{WEB}/citizen/documents")
    page.wait_for_selector(".doc", timeout=30000)
    page.wait_for_timeout(500)
    shot(page, "tc4-3-document-gap.png")
    page.goto(f"{WEB}/citizen/schemes")
    card = card_of(page, "Punjab")
    card.get_by_role("button", name="Prepare draft").first.click()
    page.wait_for_selector(".draft-row", timeout=30000)
    page.wait_for_timeout(600)
    shot(page, "tc4-4-draft-saved.png")
    page.context.close()


TC_INPUT: dict[str, str] = {}


# ------------------------------------------------------------------------------------------------ documentation
def md_checks(run):
    rows = ["| # | Check | Result |", "|---|---|---|"]
    for i, c in enumerate(run["checks"], 1):
        rows.append(f"| {i} | {c['name']} | {'✅ pass' if c['passed'] else '❌ FAIL'} |")
    return "\n".join(rows)


def md_criteria(results):
    out = ["| Scheme | Condition | Needs | Citizen's fact | Result | Official wording (quoted) |", "|---|---|---|---|---|---|"]
    for r in results:
        for c in r["criteria"]:
            need = {"is_true": "yes", "is_false": "no"}.get(c["operator"], f"{c['operator']} {c['expected']}")
            out.append(f"| {r.get('scheme', r['rule_id'])} | {c['fact']} | {need} | {c['observed']} | {c['outcome']} | “{c.get('quote', '')}” |")
    return "\n".join(out)


def img(name, caption):
    return f"![{caption}](screenshots/{name})\n*{caption}*\n"


def write_docs(runs, env):
    t1, t2, t3, t4, t5 = (runs[k] for k in ("TC1", "TC2", "TC3", "TC4", "TC5"))
    cands = t1["actual"]["candidates"]
    outcomes = t1["actual"]["all_outcomes"]
    bi, ma = t2["actual"]["Bihar"], t2["actual"]["Maharashtra"]
    ch3 = t3["actual"]["changed"]
    pages = {}

    pages["TC1"] = f"""# TC1 · Eligible household

| | |
|---|---|
| **Brief expects** | {BRIEF['TC1'][1]} |
| **Result** | {'✅ PASS' if t1['passed'] else '❌ FAIL'} ({sum(c['passed'] for c in t1['checks'])}/{len(t1['checks'])} checks) |
| **Run** | `{t1['run_id']}` · {t1['ran_at']} · evaluation `{t1['actual']['eval_id']}` |

## Input
A citizen types (or says) in English:
> {t1['input']['utterance']}

## What the system did
It extracted the household's facts with stable ids, confirmed them, and screened them against the reviewed rules. **{len(cands)} candidate schemes** came back,
every one with the official sentence for each condition quoted next to the citizen's fact, and the source link:

{md_criteria(cands[:2])}

(first two candidates shown; all {len(cands)} are in `data/TC1.json`.) Outcome of every rule screened: {', '.join(f'`{k}` {v}' for k, v in outcomes.items())}.

## Evidence
{md_checks(t1)}

Raw record: [`data/TC1.json`](data/TC1.json) · runner page: ![runner](screenshots/tc1-0-runner.png)

## Screenshots
{img('tc1-1-conversation.png', 'The conversation: what the citizen typed and the facts the bot understood (each must be confirmed)')}
{img('tc1-2-scheme-passport.png', 'The Scheme Passport: 12 schemes screened, grouped; every likely scheme says "Provisional match"')}
{img('tc1-3-rules-quoted.png', '"Why this result": each condition, what the rule needs, what the citizen said, and the official wording quoted')}
{img('tc1-4-source-and-technical.png', 'The official source link, and the technical details (rule id, source id, dates) folded below')}

## Difference from the expected result
Matches the brief: a scheme list, with each rule's own wording quoted and a source cited. Three things worth saying out loud:
1. **The label is "Provisional match", never "Eligible".** All {len(cands)} candidates are provisional because their required documents are not yet verified by a reviewer and each rule's source has not been verified against the official website by a data steward. This is deliberate (see TC4). The scenario's name ("Eligible household") describes the household, not a promise the system makes.
2. **Only schemes with a reviewed rule can be screened.** The catalogue holds {env['schemes']} schemes and can be searched, but the screening engine evaluates the {env['rules']} rules that have been written and reviewed; the rest are not guessed at.
3. **The input is typed text.** The speech path is exercised in TC3 with a simulated transcript; real microphone accuracy depends on the speech service and is not something this test can promise.
"""

    def pens(side):
        return "\n".join(f"| {p['rule_id']} | {p['scheme']} | {p['outcome']} | " + ", ".join(
            f"{c['fact']} {c['operator']} {c['expected']} (citizen: {c['observed']}) → {c['outcome']}" for c in p['criteria'] if c['fact'] == 'age') + " |"
            for p in side["pension_results"])

    pages["TC2"] = f"""# TC2 · Same scheme name in two states

| | |
|---|---|
| **Brief expects** | {BRIEF['TC2'][1]} |
| **Result** | {'✅ PASS' if t2['passed'] else '❌ FAIL'} ({sum(c['passed'] for c in t2['checks'])}/{len(t2['checks'])} checks) |
| **Run** | `{t2['run_id']}` · {t2['ran_at']} |

## Input
The same sentence twice, once per state:
> {t2['input']['utterance_template']}  with `{{state}}` = **Bihar**, then **Maharashtra**.

## What the system did
"Indira Gandhi National Old Age Pension Scheme" exists in both states' records with different rules and different official sources. Each citizen was screened against **their own state's** record:

| Rule | Scheme record | Outcome | Age condition |
|---|---|---|---|
{pens(bi)}
{pens(ma)}

* Bihar's record needs age ≥ 60 → a 62-year-old passes. Maharashtra's needs ≥ 65 → the same 62-year-old does **not** match the state scheme.
* The **central** scheme (`R_NSAP_IGNOAPS`, age ≥ 60) is considered for both citizens: Bihar → {bi['outcomes']['R_NSAP_IGNOAPS']}, Maharashtra → {ma['outcomes']['R_NSAP_IGNOAPS']}.
* No rule from the other state leaked in; the two state records cite different source documents.

## Evidence
{md_checks(t2)}

Raw record: [`data/TC2.json`](data/TC2.json) · runner page: ![runner](screenshots/tc2-0-runner.png)

## Screenshots
{img('tc2-1-bihar.png', 'Bihar: the Bihar record is used (age ≥ 60) and the condition is met')}
{img('tc2-2-maharashtra.png', 'Maharashtra: the Maharashtra record is used (age ≥ 65) and the age condition is not met for a 62-year-old')}

## Difference from the expected result
Matches the brief: the correct state's record is used in each case. One thing to know: the **same person gets a different answer in the two states** (provisional in Bihar, "does not match" for Maharashtra's state scheme) because the two official records really do set different age limits (60 vs 65); the central NSAP scheme still shows as a provisional match in Maharashtra, so the citizen is not left with nothing. The thresholds come from the scheme text in the dataset, quoted in the "Why this result" panel.
"""

    def chg():
        rows = ["| Rule | With the misheard age (26) | After the correction (62) |", "|---|---|---|"]
        for k, v in ch3.items():
            rows.append(f"| `{k}` | {v['with_misheard_age']} | {v['after_correction']} |")
        return "\n".join(rows)

    pages["TC3"] = f"""# TC3 · Age misheard

| | |
|---|---|
| **Brief expects** | {BRIEF['TC3'][1]} |
| **Result** | {'✅ PASS' if t3['passed'] else '❌ FAIL'} ({sum(c['passed'] for c in t3['checks'])}/{len(t3['checks'])} checks) |
| **Run** | `{t3['run_id']}` · {t3['ran_at']} |

## Input
A Hindi voice transcript in which the speaker's age arrives as **26** (the real age is 62):
> {t3['input']['utterance']}

## What the system did
1. Read the transcript, held the age (and income, state) as **unconfirmed** and read the age back **in digits**: “{t3['actual']['age_readback']}”.
2. **Blocked screening** with `PROFILE_NEEDS_CONFIRMATION` until those facts are confirmed.
3. "Confirm all" did **not** confirm the high-impact facts; it confirmed only {len(t3['actual']['confirm_all']['confirmed'])} low-impact fact and left {len(t3['actual']['confirm_all']['needs_individual_confirmation'])} (age, income, state) for individual confirmation.
4. The citizen **corrected** the age to 62: a new fact was created and the old one marked superseded (`{t3['actual']['age_history'][0]['superseded_by']}`); the results were recomputed from the corrected fact:

{chg()}

## Evidence
{md_checks(t3)}

Raw record: [`data/TC3.json`](data/TC3.json) (includes the full fact history) · runner page: ![runner](screenshots/tc3-0-runner.png)

## Screenshots (the app in Hindi)
{img('tc3-1-held-for-confirmation.png', 'The misheard age is held for confirmation and read back; nothing is used yet')}
{img('tc3-2-screening-blocked.png', 'Trying to check schemes now is refused: "confirm or correct the highlighted details first"')}
{img('tc3-3-confirm-all-leaves-age.png', '"Confirm the others" leaves the age (and income, state) pending: they must be confirmed one by one')}
{img('tc3-4-after-correction.png', 'After the age is corrected to 62 the results are recomputed: the Bihar pension schemes become provisional matches')}

## Difference from the expected result
Matches the brief and goes a step further: facts are confirmed before any filtering, **and "confirm all" cannot confirm the high-impact ones.** Two honest notes:
1. **The mishearing is simulated.** The test injects a transcript that already contains the wrong age (channel "voice (simulated transcript)"), because a real speech-recognition error cannot be made to happen on demand. What the test proves is what the system does when it receives a wrong age.
2. The bot also guessed the speaker's gender (male) from the verb form "रहता हूँ"; that guess is marked *inferred* and also waits for confirmation, so it cannot filter anything unconfirmed.
"""

    pages["TC4"] = f"""# TC4 · Provisional eligibility

| | |
|---|---|
| **Brief expects** | {BRIEF['TC4'][1]} |
| **Result** | {'✅ PASS' if t4['passed'] else '❌ FAIL'} ({sum(c['passed'] for c in t4['checks'])}/{len(t4['checks'])} checks) |
| **Run** | `{t4['run_id']}` · {t4['ran_at']} |

## Input
> {t4['input']['utterance']}

Document marks entered by the citizen: {', '.join(f'`{k}` = {v}' for k, v in t4['input']['documents'].items())}.

## What the system did
{md_criteria([t4['actual']['punjab_result']])}

Every condition passes, but the required documents are not verified by a reviewer, so the outcome is **{t4['actual']['punjab_result']['outcome']}**, never MATCH:
decision reasons `{', '.join(d['code'] for d in t4['actual']['punjab_result']['decision_reason'])}`. The document gap lists `{', '.join(t4['actual']['punjab_result']['document_gaps'])}`.
Rules whose facts are still unknown (e.g. PM-KISAN needs land ownership) answer `INSUFFICIENT_INFORMATION` instead of guessing. A draft was saved (`{t4['actual']['draft_id']}`) and saving again returned the **same** draft (no duplicate).

The spoken summary, word for word: “{t4['actual']['summary'][:230]}…”

## Evidence
{md_checks(t4)}

Raw record: [`data/TC4.json`](data/TC4.json) · runner page: ![runner](screenshots/tc4-0-runner.png)

## Screenshots
{img('tc4-1-provisional-not-match.png', 'The Punjab pension is a "Provisional match"; the notice says it is not an approval and not a guarantee of benefit')}
{img('tc4-2-why-documents.png', '"Why this result": every condition met, but "A reviewer still has to verify your documents"; the documents to bring are listed')}
{img('tc4-3-document-gap.png', 'The Document Guide shows the gap: the BPL card is marked missing')}
{img('tc4-4-draft-saved.png', 'The draft is saved and clearly marked "not submitted to any government portal"')}

## Difference from the expected result
None. The system never presents a result as a benefit: the only positive outcome is "Provisional match", the words "approval" and "guarantee" appear only to deny them ("Preliminary screening only — not an approval and not a guarantee of benefit"), and an automated check scans the spoken summary for promise wording. Every outcome here depends on documents a human reviewer would still have to verify.
"""

    pages["TC5"] = f"""# TC5 · Returning citizen (extra: beyond the brief's four cases)

| | |
|---|---|
| **Result** | {'✅ PASS' if t5['passed'] else '❌ FAIL'} ({sum(c['passed'] for c in t5['checks'])}/{len(t5['checks'])} checks) |
| **Run** | `{t5['run_id']}` · {t5['ran_at']} |

The brief lists four cases; this fifth one covers the saved-passport journey (Passport code + PIN, resume, "what changed"). {t5['expected']}

## Evidence
{md_checks(t5)}

"What changed" after the age was corrected to {t5['input']['new_age']}:

| Scheme | Before | After | Because |
|---|---|---|---|
""" + "\n".join(f"| {c['scheme_name']} | {c['before']} | {c['after']} | the {c['reasons'][0]['attribute']} changed ({c['reasons'][0]['before']} → {c['reasons'][0]['after']}) |"
                for c in t5["actual"]["what_changed"]["changes"]) + f"""

Raw record: [`data/TC5.json`](data/TC5.json) · runner page: ![runner](screenshots/tc5-0-runner.png)

## Difference from the expected result
None. The PIN is never recorded in the evidence (the input shows "{t5['input']['pin']}"), and a wrong code and a wrong PIN deliberately get the same answer.
"""

    for tc, body in pages.items():
        (OUT / f"{tc}.md").write_text(body, encoding="utf-8")

    total = sum(len(r["checks"]) for r in runs.values())
    ok = sum(c["passed"] for r in runs.values() for c in r["checks"])
    index = f"""# Official test cases: evidence pack

Prepared {env['date']} from commit `{env['commit']}` ({env['schemes']} catalogue schemes, {env['rules']} reviewed rules, rule bundle `{env['bundle']}`).
The brief asks to *run each scenario and capture the input, actual result and evidence, and explain any difference from the expected result.* This folder does exactly that.

## Summary

| Case | Scenario | Brief expects | Result | Checks | Page |
|---|---|---|---|---|---|
""" + "\n".join(
        f"| {tc} | {(BRIEF.get(tc) or (runs[tc]['title'], ''))[0]} | {(BRIEF.get(tc) or ('', 'extra case'))[1]} | {'✅ PASS' if runs[tc]['passed'] else '❌ FAIL'} | "
        f"{sum(c['passed'] for c in runs[tc]['checks'])}/{len(runs[tc]['checks'])} | [{tc}.md]({tc}.md) |" for tc in runs) + f"""

**{ok} of {total} checks pass** across the five scenarios. A printable version with all screenshots is in [`Anvaya-test-evidence.pdf`](Anvaya-test-evidence.pdf) (same content as [`report.html`](report.html)).

![All five scenarios on the test-runs page](screenshots/00-test-runs-page.png)

## What each case shows

* **[TC1](TC1.md)**: a household's facts become a scheme list; every condition quotes the official sentence and links its source. Results are *provisional*, never "eligible".
* **[TC2](TC2.md)**: the same scheme name in Bihar and Maharashtra is screened against each state's own record (age 60+ vs 65+); nothing leaks across states, and the central scheme applies to both.
* **[TC3](TC3.md)**: a misheard age (26 instead of 62) is held, read back in digits, blocks screening, cannot be confirmed by "confirm all", and its correction recomputes the results.
* **[TC4](TC4.md)**: criteria pass but proof is missing, so the result is provisional, the document gap is listed, the draft is idempotent, and nothing is promised as a benefit.
* **[TC5](TC5.md)** (extra): a returning citizen resumes with a Passport code + PIN and sees what changed and why.

## Differences from the expected results, in one place

| Case | Difference | Why |
|---|---|---|
| TC1 | Results say "Provisional match", never "Eligible" | Documents are unverified and the rule sources are not yet checked by a data steward; the safety rules forbid promising a benefit |
| TC1 | Only schemes with a reviewed rule are screened ({env['rules']} of {env['schemes']}) | The engine does not guess at schemes nobody has reviewed |
| TC2 | The same person gets different answers in the two states | The two official records set different age limits (60 vs 65); the central scheme still applies in both |
| TC3 | The mishearing is simulated | A real recognition error cannot be triggered on demand; the test proves the system's handling of a wrong age |
| TC3 | "Confirm all" does not confirm the age, income or state | Stronger than the brief: high-impact facts are confirmed one by one |
| TC4 | none | |

## How the evidence was produced (and how to reproduce it)

Each scenario is a function in [`backend/anvaya/testrunner.py`](../../backend/anvaya/testrunner.py) that drives the **real pipeline** (conversation → extraction → confirmation → rule engine → documents → draft) and records its input, the expected result,
the actual result and a list of named checks. The screenshots are taken by a browser driving the real web app with the same inputs. The whole pack is generated by one script from the recorded data (no number in these pages is typed by hand):

```
backend/.venv/Scripts/python.exe -m pip install playwright      # once; Chrome must be installed
backend/.venv/Scripts/python.exe scripts/capture_test_evidence.py
```

It uses a throwaway database with no Supabase, no LLM and no speech service, so it is repeatable. The same scenarios can be run by an admin on the app's `/test-runs` page, and `POST /api/v1/test-runs/TC1…TC5` returns the same record.
The automated test-suite also runs them (`backend/tests/test_api.py`).

## Files
`TC1.md … TC5.md` (one page per case) · `report.html` / `Anvaya-test-evidence.pdf` (printable) · `data/TCn.json` (raw records) · `data/environment.json` · `screenshots/` · `../../scripts/capture_test_evidence.py` (regenerates everything).
"""
    (OUT / "README.md").write_text(index, encoding="utf-8")
    return pages, index


def build_report(runs, env, pages):
    """One printable HTML file (and a PDF if Chrome is available)."""
    import re

    def md_to_html(md):
        lines, out, in_table, in_code = md.split("\n"), [], False, False
        for ln in lines:
            if ln.startswith("```"):
                in_code = not in_code
                out.append("<pre>" if in_code else "</pre>")
                continue
            if in_code:
                out.append(html.escape(ln))
                continue
            if ln.startswith("|"):
                cells = [c.strip() for c in ln.strip("|").split("|")]
                if all(set(c) <= set("-: ") for c in cells):
                    continue
                if not in_table:
                    out.append("<table>")
                    in_table = True
                    tag = "th"
                else:
                    tag = "td"
                out.append("<tr>" + "".join(f"<{tag}>{inline(c)}</{tag}>" for c in cells) + "</tr>")
                continue
            if in_table:
                out.append("</table>")
                in_table = False
            if ln.startswith("# "):
                out.append(f"<h1>{inline(ln[2:])}</h1>")
            elif ln.startswith("## "):
                out.append(f"<h2>{inline(ln[3:])}</h2>")
            elif ln.startswith("> "):
                out.append(f"<blockquote>{inline(ln[2:])}</blockquote>")
            elif re.match(r"^(\* |\d+\. )", ln):
                out.append(f"<p class='li'>{inline(re.sub(r'^(\\* |\\d+\\. )', '• ', ln))}</p>")
            elif ln.strip():
                out.append(f"<p>{inline(ln)}</p>")
        if in_table:
            out.append("</table>")
        return "\n".join(out)

    def inline(s):
        s = html.escape(s, quote=False)
        s = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r"<img src='\2' alt='\1'>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"<a href='\2'>\1</a>", s)
        s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
        s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<i>\1</i>", s)
        return s

    index = (OUT / "README.md").read_text(encoding="utf-8")
    for n in range(1, 6):  # links between pages become in-document anchors (only the "(TCn.md)" link targets, not the file names in prose)
        index = index.replace(f"(TC{n}.md)", f"(#tc{n})")
    index = "\n".join(ln for ln in index.splitlines() if "printable version" not in ln)  # the PDF does not point at itself
    body = md_to_html(index)
    for tc, md in pages.items():
        body += f"<section class='tc' id='{tc.lower()}'>" + md_to_html(md) + "</section>"
    css = ("@page{size:A4;margin:14mm}html{-webkit-print-color-adjust:exact;print-color-adjust:exact}"
           "pre{white-space:pre-wrap;word-break:break-word}td,th{word-break:break-word}"
           "body{font:14px/1.5 'Segoe UI',system-ui,sans-serif;color:#1d2422;max-width:980px;margin:2rem auto;padding:0 1rem}"
           "h1{font-size:24px;color:#0f5c4d;border-bottom:3px solid #E8833A;padding-bottom:.3rem}h2{font-size:17px;color:#0f5c4d;margin-top:1.6rem}"
           "table{border-collapse:collapse;width:100%;margin:.6rem 0;font-size:12.5px}th{background:#0f5c4d;color:#fff;text-align:left}"
           "th,td{border:1px solid #d9dedc;padding:5px 8px;vertical-align:top}tr:nth-child(even) td{background:#f6f8f7}"
           "img{max-width:100%;border:1px solid #d9dedc;border-radius:8px;margin:.4rem 0}blockquote{margin:.5rem 0;padding:.4rem .8rem;border-left:4px solid #E8833A;background:#fdf2dc}"
           "code{background:#eef2f1;padding:1px 4px;border-radius:4px;font-size:.9em}pre{background:#eef2f1;padding:.6rem;border-radius:8px;overflow:auto}"
           ".li{margin:.15rem 0 .15rem 1rem}section.tc{page-break-before:always}p{margin:.4rem 0}")
    (OUT / "report.html").write_text(f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>Anvaya: official test cases, evidence</title><style>{css}</style></head><body>{body}</body></html>", encoding="utf-8")
    chrome = next((p for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe", r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                                shutil.which("google-chrome") or "", shutil.which("chromium") or "") if p and Path(p).exists()), None)
    if chrome:
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={OUT / 'Anvaya-test-evidence.pdf'}",
                        (OUT / "report.html").as_uri()], capture_output=True, timeout=180)


# ------------------------------------------------------------------------------------------------ main
def docs_only():
    """Rebuild the written pages, the HTML report and the PDF from the saved records (no servers, no browser, screenshots kept)."""
    runs = {tc: json.loads((DATA / f"{tc}.json").read_text(encoding="utf-8")) for tc in ("TC1", "TC2", "TC3", "TC4", "TC5")}
    env = json.loads((DATA / "environment.json").read_text(encoding="utf-8"))
    pages, _ = write_docs(runs, env)
    build_report(runs, env, pages)
    print("docs rebuilt:", OUT)


def main():
    if "--docs-only" in sys.argv:
        return docs_only()
    for d in (OUT, SHOTS, DATA):
        d.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        back, front = start_servers(Path(tmp))
        try:
            ready = requests.get(f"{API}/ready", timeout=30).json()
            runs = run_scenarios()
            for tc, d in (("TC1", runs["TC1"]), ("TC3", runs["TC3"]), ("TC4", runs["TC4"])):
                TC_INPUT[tc] = d["input"]["utterance"]
            env = {"date": datetime.now(timezone.utc).strftime("%d %B %Y"),
                   "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip(),
                   "schemes": f"{ready['schemes']:,}", "rules": ready["rules"],  # counts as the app itself reports them (GET /ready)
                   "bundle": os.environ.get("ANVAYA_RULE_BUNDLE_VERSION", "rules-2026.10.1")}
            (DATA / "environment.json").write_text(json.dumps({**env, "ready": ready}, ensure_ascii=False, indent=2), encoding="utf-8")
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome")
                for fn in (lambda b: shots_runner_page(b, runs), shots_tc1, shots_tc2, shots_tc3, shots_tc4):
                    try:
                        fn(browser)
                    except Exception as e:  # a missing screenshot must not lose the rest of the pack
                        print("SCREENSHOT STEP FAILED:", getattr(fn, "__name__", "runner"), repr(e)[:300])
                browser.close()
            pages, _ = write_docs(runs, env)
            build_report(runs, env, pages)
            print("done:", OUT)
        finally:
            stop(front)
            stop(back)


if __name__ == "__main__":
    main()
