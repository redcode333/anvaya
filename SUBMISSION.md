# Anvaya AI — submission

Voice-first welfare-scheme pre-screening in Telugu, Hindi and English. A citizen speaks or types about their household;
Anvaya extracts candidate facts and reads them back. The citizen confirms or corrects every important one. A
deterministic, versioned rules engine then shows **potential and provisional matches**, each with quoted rule text,
the source and the missing documents. Drafts go to a human reviewer only with consent. Nothing is an approval or a
government submission.

## What works, with evidence

All results below are from the final pre-submission run on 2026-10-23, against the Docker stack built from this
repository.

| Area | Result | Evidence |
|---|---|---|
| Backend tests | **237 passed** | `cd backend && python -m pytest -q`: rules engine, extraction (en/hi/te), API contracts, VerbX + LLM with mocked HTTP, TTS cache, startup checks, TC1–TC4 |
| Frontend | **23 tests passed**, typecheck + production build OK | `cd frontend && npm test && npm run build`: offline rules engine vs the shared fixtures, confirmation rules, speech fallback |
| Official scenarios TC1–TC4 | **4/4 PASS, 26/26 checks** | `/test-runs` → *Run all*, or `POST /api/v1/test-runs/TC1…TC4` |
| Extraction quality | **0 wrong facts reach confirmation**; high-impact precision 1.000 | `python -m anvaya.manage eval-extraction`, 40 demo utterances, rule-based alone and with the LLM |
| Live VerbX | translate en↔hi/te in ~0.4–0.5 s; TTS → STT round trip in hi and te | `python -m pytest -m live` |
| Live LLM | Groq: 3/3 ok in ~2 s. Gemini: 3/3 failed (6 s timeouts, then HTTP 503 from Google), so those turns fell back to rule-based extraction | same command; see Limitations in README |
| Read-aloud | 267 fixed prompts prerendered in en/hi/te; a cached clip returns in ~10–25 ms; an uncached sentence takes ~1.5 s; anything over 8 s shows text + "audio unavailable" | `python -m anvaya.manage prerender-audio`, `/api/v1/ready` → `tts_cache` |
| Docker | app, Prometheus and Grafana all `healthy`; named volumes only | `docker compose up --build`, `docker compose ps` |
| Langfuse tracing (optional) | one trace per LLM turn, trace ID = correlation ID; demo turns in full, others metadata only (verified live: no utterance text stored); unreachable Langfuse adds ~1 ms; eval pushed as dataset + 3 experiments, 0 wrong facts each | `tests/test_tracing.py`, `LANGFUSE_TRACE_EVAL=1 python -m anvaya.manage eval-extraction` |
| Monitoring | Prometheus target `up`; Grafana dashboard (32 panels) opens read-only without login | http://localhost:9090/targets, http://localhost:3000 |
| Security | staff and test-run routes return 401 without a valid token. No stack traces in responses. No keys in tracked files or git history. `.env` gitignored and never committed. Logs of a full TC run contain no utterances, names, ages or incomes | see README → Security & privacy |

## Run it in 3 commands

```bash
cp .env.example .env              # fill VERBX_* and LLM keys and the ANVAYA_*_PASSWORDs (all optional)
docker compose up --build         # app :5000 · Prometheus :9090 · Grafana :3000
docker compose exec anvaya python -m anvaya.manage prerender-audio   # once: instant read-aloud
```

**Without Docker (Ubuntu / WSL):**

```bash
bash scripts/run_local.sh --prerender-audio    # app on :5000, audio cache filled in the background
bash scripts/run_monitoring_local.sh           # second terminal: Prometheus :9090 + Grafana :3000
```

Then open http://localhost:5000. The operator, reviewer and admin passwords are the ones set in `.env`.

## Before the demo (5 minutes earlier)

1. Check `docker compose ps`: all three services should be `healthy`. In `http://localhost:5000/api/v1/ready`,
   `"ready": true`, VerbX `configured` and `tts_cache.prerendered` ≥ 267 mean everything is set.
2. While online, open `/kiosk` once and sign in as the operator. This caches the offline rule bundle.
3. Open Grafana (http://localhost:3000) in a second tab and run TC1–TC4 once, so the dashboard has data.
4. Allow microphone access in the browser for `localhost:5000`.

## Demo script (4 minutes)

Each step works by speaking (🎤) or by tapping the same sentence under *Demo phrases*. Taps are sent as voice
transcripts, so every fact still needs confirmation. The 🎤 button records until you tap it again.

### 1. Telugu kiosk, misheard age (0:00–1:30)

`/kiosk` → sign in as operator → **తెలుగు** → *ప్రారంభించండి* (Start). The greeting shows immediately and plays from the
audio cache.

**Speak** (demo phrase "వయస్సు తప్పుగా విన్నది"):

> నా వయస్సు 26 సంవత్సరాలు. ఆంధ్రప్రదేశ్ గ్రామంలో ఉంటాను. బీపీఎల్ కార్డు ఉంది. పెన్షన్ రావడం లేదు.
>
> *Naa vayassu iravai aaru samvatsaraalu. Aandhrapradesh graamamlo untaanu. BPL kaardu undi. Pension raavadam ledu.*

* **Shows:** age **26**, state Andhra Pradesh, rural area, BPL card, no other pension. Each fact has an ID and the
  words heard. *Check schemes* stays disabled: high-impact facts must each be confirmed, and "confirm all" never
  covers them.
* **Say:** "Speech recognition can mishear numbers. Nothing is screened until the citizen confirms."
* **Do:** age → *సరిచేయండి* (Correct) → **67** → *Save*. Confirm the remaining facts. *పథకాలు చూడండి* (Check schemes).
* **Expect:** INDIRAMMA Old Age Pension (Rural) and NSAP old-age pension show as **తాత్కాలిక సరిపోలిక** (provisional
  match). The AP spectacles scheme shows as *needs human review*. 🔊 reads: "ఇవి ప్రాథమిక ఫలితాలు, ఆమోదం కాదు…"
  ("these are preliminary results, not an approval").
* **Then:** open *Why* on one card. It shows each criterion with the quoted rule text, expected vs observed value, the
  fact ID and the source URL.

### 2. Hindi, widow household (1:30–2:15)

*End session* → **हिन्दी** → *शुरू करें* (Start).

**Speak** (demo phrase "विधवा, बिहार"):

> मैं 52 साल की विधवा हूँ, बिहार के गाँव में रहती हूँ। परिवार में 3 लोग। आय 3000 रुपये महीना। बीपीएल कार्ड है।
>
> *Main baawan saal ki vidhwa hoon, Bihar ke gaon mein rehti hoon. Parivaar mein teen log. Aay teen hazaar rupaye mahina. BPL card hai.*

* **Shows:** age 52, widowed, female, Bihar, rural, 3 members and **₹36,000 a year**. The citizen said ₹3000 a month;
  the conversion is shown and needs confirmation.
* **Do:** confirm the facts, then *योजनाएँ देखें* (Check schemes).
* **Expect:** Indira Gandhi National Widow Pension Scheme and PM Ujjwala Yojana 2.0 as **अस्थायी मिलान** (provisional
  match). Scheme names appear in Hindi, labelled "मशीनी अनुवाद" (machine translation).

Alternative for the Hindi misheard-age story, demo phrase "बिहार, उम्र गलत सुनी":

> मेरी उम्र 26 साल है। मैं बिहार के गाँव में रहता हूँ। बीपीएल कार्ड है, कोई पेंशन नहीं मिलती। सालाना आय 40000 रुपये।
>
> *Meri umr chhabbees saal hai. Main Bihar ke gaon mein rehta hoon. BPL card hai, koi pension nahin milti. Saalaana aay chaalees hazaar rupaye.*

Correct the age to **62**. Bihar IGNOAPS and NSAP then show as provisional matches; this is TC3.

### 3. Documents, draft, reviewer (2:15–3:00)

* On *Document Guide*, mark the **BPL card** as *missing*; the gap appears on the scheme cards.
* *Prepare draft*: every field is tagged confirmed / inferred / missing.
* Tick consent → *Send to reviewer* → case code `ANV-XXXX-XXXX`.
* In a second tab, `/reviewer` (reviewer sign-in) → open the case. It shows the fact history (26 superseded by 67),
  the rule trace and the documents.

### 4. Offline and the official tests (3:00–4:00)

* Back in the kiosk, tick **simulate network loss**. The typed pre-screen still runs on the cached rule bundle.
  Save to the outbox, untick, *Sync now*, then *Retry test (resend)*: the resend shows `duplicate`, so the reviewer
  gets exactly one case.
* `/test-runs` → *Run all*: TC1–TC4 with input, expected, actual and per-check evidence.
* Switch to Grafana: outcome mix, latency, and VerbX / LLM health.

## If something fails during the demo

| What fails | What you see | What to do and say |
|---|---|---|
| **Microphone or speech recognition** | error note under the chat, or the 🎤 button switches to browser speech | Tap the same sentence under *Demo phrases*. "VerbX speech isn't reachable here, so I'll send the same sentence as a transcript; it goes through exactly the same pipeline, including the confirmation step." |
| **Read-aloud** | text stays on screen with 🔇 "audio unavailable" | "Audio has an 8-second limit by design, so a slow network never blocks the citizen; the text is always shown." Pressing *Listen* again usually plays, because the clip finished in the background. |
| **Venue Wi-Fi (internet down, laptop still serving localhost)** | VerbX and the LLM drop out; the app keeps running | "Speech falls back to the browser and typing, and extraction is rule-based, which is the primary path anyway. Eligibility never depended on the internet." Type or tap the demo phrases. Names stay in English. |
| **No network at all in the browser** | kiosk switches to the offline pre-screen | "This is the kiosk's offline mode: the rules run locally on the cached, checksummed bundle, and drafts queue in the outbox until it reconnects." |
| **LLM slow or failing** (e.g. Gemini free tier) | nothing visible; the turn takes at most ~7 s | "The LLM is optional and only proposes candidates. When it's slow, the turn falls back to rule-based extraction within the 7-second budget." |
| **Grafana won't load** | — | Show `http://localhost:5000/metrics` or `/api/v1/ready` instead. |
| **Docker won't start** | — | `bash scripts/run_local.sh` in Ubuntu/WSL serves the same app on :5000. |
| **Everything is slow** | — | Open `/test-runs`: the latest saved TC1–TC4 runs, with full evidence, are shown without re-running. |

## Team

* **Abhinav Anand**
* **Aman Agrawal**
