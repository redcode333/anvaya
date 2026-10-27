# Anvaya AI — *Every voice, a way forward.*

Multilingual (Telugu / Hindi / English), voice-first welfare-scheme discovery, eligibility **pre-screening**, document
guidance and application-draft preparation. It runs on a citizen's phone, or at an operator-assisted **kiosk** that keeps
working offline.

> Voice and the optional LLM are only the conversational interface. **Eligibility is decided by a deterministic,
> versioned rules engine** on facts the citizen has confirmed. Unknown facts stay unknown. Results are potential or
> provisional matches; nothing in this app is an approval, a benefit guarantee or a government submission.

## At a glance

| | |
|---|---|
| **What it does** | Hears (or reads) a household's story in Telugu, Hindi or English → proposes facts → the citizen confirms them → a rules engine screens against curated scheme rules → lists documents to bring → prepares a draft and a copy-ready **Form Helper** → optionally hands the draft to a human reviewer, with consent |
| **What it never does** | Decide eligibility with an LLM · submit anything to a government portal · read, OCR or store Aadhaar numbers · keep data without consent |
| **Catalogue** | 3,534 schemes in 37 jurisdictions (searchable) · **17 curated, quoted rules** that are screened automatically |
| **Surfaces** | Citizen (phone) · **Kiosk** (operator-assisted, offline-capable) · Reviewer · Admin (catalogue, security, background jobs) · Official scenarios TC1–TC5 |
| **Stack** | React + Vite PWA · Flask API (gunicorn) · Supabase (Postgres with Row Level Security, Auth with TOTP for staff, private Storage) · VerbX speech · optional Groq → Gemini LLM · Langfuse tracing · Prometheus + Grafana · GitHub Actions |
| **Verified by** | 386 backend tests on SQLite and 387 on Postgres 16 · 95 frontend tests · TC1–TC5 against the live Supabase project (checks 6/6, 6/6, 7/7, 7/7, 8/8) — re-run on 2026-10-25 against the merged code, all passing |
| **Runs on** | A sleeping free tier (Render) with no Redis, queue, gateway or separate worker — see [Scaling](#scaling) |

**Contents:**
[Product tour](#product-tour) ·
[High-level design](#high-level-design) ·
[How the agent works](#how-the-agent-works) ·
[Kiosk](#kiosk-assisted-operator-run-offline-capable) ·
[Quick start](#quick-start) ·
[Accounts and modes](#accounts-and-modes) ·
[Configuration](#configuration-env) ·
[Database](#database) ·
[Read-aloud](#read-aloud-verbx-tts-cached) ·
[LLM extraction](#llm-extraction-optional-free-providers) ·
[Langfuse](#langfuse-tracing-optional) ·
[Scaling](#scaling) ·
[Observability](#observability-prometheus--grafana) ·
[Metrics, latency and scores](#metrics-latency-and-scores) ·
[Integrations and roadmap](#integrations-and-roadmap) ·
[Failure modes](#failure-modes--fallbacks) ·
[Limitations](#limitations)

---

## Product tour

All screenshots are from the real, current frontend build running against a throwaway local database, with Supabase
sign-in mocked at the network layer (so no real account, key or citizen data appears). The Grafana image is from the
live monitoring stack. Rules, text and numbers on screen are what the app produces.

### Landing and sign-in

| Landing: a headline that rotates through Hinglish, Hindi, English and Telugu, with a live demo | Sign in: no account needed; verified options are visible and honest |
|---|---|
| ![Landing, desktop](docs/screenshots/01d-landing-desktop.png) | ![Sign in](docs/screenshots/18d-signin-desktop.png) |
| One tap on the microphone starts a conversation. The demo card plays a Telugu / Hinglish exchange; below it the page explains how it works and races a seven-step portal against one sentence. Beside the microphone, *Kiosk / assisted*, *Case status*, *Resume with Passport code* and *My Passports* are four equal tiles in a two-by-two grid (one column on a narrow phone), each with its own icon and a soft lift on hover; the line "No login · No forms · Hindi, English, Telugu" closes the block under a thin rule. The landing header is only the logo and name, so nothing competes with the headline; the crowd of citizens walking past is on the first screen, with the demo card kept compact. The site opens in **English**; the hero's language tabs switch it. On the other pages the header shows the public tabs (*Citizen*, *My Passports*, *Case status*, *Sign in*, *Staff*), centred, with a language pill that slides to the chosen language, an underline that grows under the current tab, and a short fade-in on page change (all off for visitors who prefer reduced motion). The *Staff* tab opens `/staff`: the staff sign-in when signed out, and a hub listing only the tools the signed-in role may use (see [Staff access](#staff-access)). The role tabs (*Reviewer*, *Catalogue*, *Security*, *TC1–TC5*) appear only inside the staff area, so an admin who is still signed in never sees *Security* while browsing as a citizen. Connection and offline-bundle details show only at a kiosk, when the connection is down, or while kiosk events wait to sync. | *Continue without account* is the main path. **Meri Pehchaan (DigiLocker)** and **phone OTP** show as "Coming soon" until they are switched on (`GET /api/config`); a disabled option never fires a request. At a kiosk, verified and phone sign-in are never offered. |

| Landing on a phone | How it works | Seven steps, or one sentence |
|---|---|---|
| ![Landing, phone](docs/screenshots/01-landing.png) | ![How it works](docs/screenshots/01b-landing-how.png) | ![Portal race](docs/screenshots/01c-landing-portal.png) |

### Citizen (personal phone)

| 1. Conversation: facts held for confirmation |
|---|
| ![Citizen conversation](docs/screenshots/02-citizen-conversation.png) |
| Each fact shows its ID and the words heard. High-impact facts (age, state, income, area, household size) are read back and confirmed **one by one**; "confirm the rest" never covers them. |

| 2. Scheme Passport: potential / provisional matches | 2b. "Why?": the rule trace behind a result |
|---|---|
| ![Scheme Passport](docs/screenshots/03-scheme-passport.png) | ![Rule trace](docs/screenshots/03b-rule-trace.png) |
| Results are *potential* or *provisional*, never approvals. Each card shows criteria passed and documents still to check. | Every criterion quotes the rule's source text, the fact IDs compared, the rule version and the bundle version. |

| 3. Document Guide (with consented upload) | 4. Draft for review |
|---|---|
| ![Document Guide](docs/screenshots/04-document-guide.png) | ![Draft](docs/screenshots/05-draft.png) |
| Marking a document is the citizen's own declaration; only a reviewer can mark it *verified*. Uploads are optional, consented, and never read by AI or OCR. | Each field is tagged confirmed / inferred / citizen-entered / missing. Nothing reaches a reviewer without the consent tick. |

| 5. Form Helper: copy-ready fields | 6. Form Helper: application steps, official link, PDF |
|---|---|
| ![Form Helper fields](docs/screenshots/05b-form-helper.png) | ![Form Helper steps](docs/screenshots/05c-form-helper-steps.png) |
| "Draft ready — submit at the office/portal". Missing fields say what to bring. Aadhaar and bank account numbers are never collected. | Numbered steps (machine-translated for hi/te and labelled so), the official link with a QR code, and a watermarked PDF. |

| 7. Case status by code |
|---|
| ![Case status](docs/screenshots/10-case-status.png) |
| A case code shows **status only**. Codes are ~40-bit random, stored hashed, expire after 72 h, and lookups are rate-limited. |

### Kiosk (assisted, Telugu)

| Operator sign-in | A misheard age, held for confirmation | Offline pre-screen (simulated network loss) |
|---|---|---|
| ![Kiosk operator sign-in](docs/screenshots/06a-kiosk-operator-signin.png) | ![Kiosk in Telugu](docs/screenshots/06-kiosk-telugu.png) | ![Kiosk offline](docs/screenshots/07-kiosk-offline.png) |
| Password plus authenticator code. The sign-in lives in memory only. | The transcript says 26; it is read back in digits and blocks screening until confirmed or corrected. | The cached, checksummed rule bundle runs in the browser; drafts queue in the outbox and sync exactly once. |

The full kiosk design is in [Kiosk](#kiosk-assisted-operator-run-offline-capable).

### Reviewer and admin

| Review queue | Case review: fact history, rule trace, documents, decision |
|---|---|
| ![Review queue](docs/screenshots/08-reviewer-queue.png) | ![Reviewer case](docs/screenshots/09-reviewer-case.png) |

| Catalogue and data freshness (admin) | Official scenarios TC1–TC5 |
|---|---|
| ![Admin catalogue](docs/screenshots/11-admin-catalogue.png) | ![TC1–TC5](docs/screenshots/12-test-runs.png) |
| Source artifact hash, quality flags, knowledge graph, and the 17 curated rules with review and official-source verification status. | Each scenario runs the real pipeline and shows input, expected, actual and per-check evidence. |

| Security: staff two-step sign-in, **background jobs**, auth audit |
|---|
| ![Admin security and jobs](docs/screenshots/14-admin-security-jobs.png) |
| Who has an authenticator (reset when a phone is lost); every retention / cleanup run with trigger, status and counts (counts only, never personal data); the last 500 auth events (IP prefix only). |

### Operations

| Grafana "Anvaya AI — Operations": overview, screening, conversation |
|---|
| ![Grafana, overview and screening](docs/screenshots/13-grafana.png) |
| Catalogue and rule counts, API p95, screening outcomes per scheme rule, the confirmation gate (screenings vs blocks), citizen corrections and facts extracted per attribute, and conversation turns by language and channel. |

| LLM extraction, cases and offline sync | API, security, **background jobs and database**, official scenarios |
|---|---|
| ![Grafana, LLM and sync](docs/screenshots/13b-grafana-llm-sync.png) | ![Grafana, API and jobs](docs/screenshots/13c-grafana-api-jobs.png) |
| Provider calls, latency and fallbacks, merge outcomes, case states, idempotent replays and kiosk sync events (empty here: this demo run has no LLM keys and no offline kiosk). | Per-route rate and p95, error responses, **hours since the last successful retention / cleanup**, job runs by status, database round trips and queries per route, and TC1–TC5 runs. |

These were captured on 2026-10-25 from the real dashboard (Prometheus 2.54.1 + Grafana 11.2.2 from the repo's configs) while a script drove about 400 synthetic citizen journeys, test runs and job calls through the app for five minutes: a local run with demo data, not production traffic. The empty panels (VerbX calls, LLM, auth events, rate-limited lookups) simply had no events.

Measured latency and Langfuse charts are in [Metrics, latency and scores](#metrics-latency-and-scores).

---

## High-level design

```mermaid
flowchart TB
  subgraph EDGE["Edge: browser / kiosk PWA (React + Vite)"]
    direction LR
    UI["Citizen · Kiosk<br/>Reviewer · Admin"]
    VOICE["Voice in/out<br/>VerbX → browser speech → typing"]
    OFFLINE["Offline pre-screen<br/>cached rule bundle · outbox"]
    UI --- VOICE --- OFFLINE
  end

  subgraph CLOUD["Cloud: Flask API, gunicorn (1 worker × 8 threads)"]
    direction LR
    AUTH["Auth<br/>JWT checked on every request<br/>TOTP (aal2) for staff"] --> CONV["Conversation<br/>rules extractor + optional LLM,<br/>merged, always confirmed"]
    CONV --> RULES["Rules engine<br/>pure · versioned · quoted"]
    RULES --> CASES["Drafts · Form Helper<br/>cases · review · audit"]
    SYNC["Offline sync<br/>dedupe · re-check"] --> RULES
    DOCS["Documents<br/>signed short-lived links"]
    JOBS["Jobs<br/>retention · cleanup"]
    LIMITS["Rate limits<br/>DB counters"]
  end

  subgraph DATA["Data: Supabase"]
    direction LR
    PG[("Postgres<br/>RLS on, no policies")]
    STORE[("Private Storage")]
    SBAUTH["Supabase Auth<br/>anonymous · email OTP · password + TOTP"]
  end

  subgraph EXT["External services: optional, each with a fallback"]
    direction LR
    VERBX["VerbX<br/>STT · TTS · translate"]
    LLM["Groq → Gemini<br/>candidate facts only"]
    LF["Langfuse<br/>traces · experiments"]
    TURN["Cloudflare Turnstile"]
  end

  subgraph OPS["Operations"]
    direction LR
    GHA["GitHub Actions<br/>hourly cron"]
    PROM["Prometheus"] --> GRAF["Grafana"]
  end

  subgraph SOON["Planned"]
    direction LR
    DL["DigiLocker / Meri Pehchaan<br/>adapter built, awaiting onboarding"]
    SETU["API Setu live scheme data<br/>requested; scheduled sync"]
  end

  EDGE -->|"HTTPS + JWT"| CLOUD
  EDGE <-->|"sign-in only"| DATA
  EDGE -.->|"speech · CAPTCHA"| EXT
  CLOUD --> DATA
  CLOUD -.->|"candidate facts · traces"| EXT
  OPS -->|"hourly job call · metrics scrape"| CLOUD
  SOON -.->|"verified facts · live scheme data"| CLOUD
```

Solid lines are built and used; dotted lines are optional (they degrade gracefully) or planned.

| Layer | Responsibility | Where |
|---|---|---|
| **Edge UI** | A landing page with a rotating Hinglish / Hindi / English / Telugu headline and live demo, then four role-specific surfaces, three languages, voice with fallbacks, offline kiosk mode; Supabase is used for sign-in only | `frontend/src/` |
| **Auth** | Every request's JWT is verified against the project's JWKS; staff need an `aal2` (TOTP) token; kiosk sessions are bound to device + operator | `auth.py`, `common.py` |
| **Conversation** | Deterministic en/hi/te extractor is the primary path; the LLM may *add candidates* that are validated, merged and always confirmed | `extraction.py`, `llm/`, `profile.py` |
| **Rules engine** | Pure function of confirmed facts and a versioned rule; mirrored in TypeScript for offline | `rules_engine.py` ⇄ `offline/rulesEngine.ts` |
| **Cases** | Drafts, Form Helper, consent hand-off, review decisions, idempotency keys, audit | `cases.py`, `formhelper.py` |
| **Data** | One Postgres (or SQLite locally) behind a dual-dialect unit of work; RLS on every table | `db.py`, `migrations.py` |
| **Background work** | Retention and cleanup as idempotent jobs behind a lock; rate limits as database counters | `jobs.py`, `ratelimit.py` |
| **Operations** | `/metrics` → Prometheus → Grafana; LLM traces → Langfuse; scheduled workflow | `metrics.py`, `monitoring/`, `.github/workflows/` |

| Spec module | Implementation |
|---|---|
| voice_adapter | `backend/anvaya/voice.py` (VerbX STT/TTS/translate) + `translation.py` (cached MT) + `frontend/src/speech.ts` |
| conversation / profile_service | `backend/anvaya/profile.py`, `extraction.py`, optional `llm/` (providers, merge, eval) |
| catalogue / knowledge_graph_service | `backend/anvaya/catalogue.py`, `ingest.py` |
| rules_engine | `backend/anvaya/rules_engine.py` ⇄ `frontend/src/offline/rulesEngine.ts` |
| draft_case / review_service | `backend/anvaya/cases.py` |
| sync_service | `backend/anvaya/sync.py`, `frontend/src/offline/store.ts` |
| audit_service | `common.audit()` → `audit_events` |
| accounts / auth | `backend/anvaya/accounts.py`, `auth.py`, `digilocker.py` |
| documents | `backend/anvaya/documents.py`, `storage.py` |
| jobs / limits | `backend/anvaya/jobs.py`, `ratelimit.py` |
| test_runner | `backend/anvaya/testrunner.py`, `/test-runs` |

**Workflow states:** `SESSION_ACTIVE → PROFILE_NEEDS_CONFIRMATION → MATCH_RESULTS_READY → DRAFT_SAVED → PENDING_REVIEW ⇄
CORRECTION_REQUESTED → REVIEWED`. Kiosk outbox events are `SYNC_PENDING / SYNCED / FAILED_RETRYABLE / CONFLICT`.
`SUBMITTED_EXTERNAL` is reserved and never produced.

**Rules engine outcomes**, from worst to best (a result takes the worst applicable one):

```mermaid
flowchart TD
  A["Confirmed facts + one curated rule"] --> B{"A confirmed criterion fails?"}
  B -- yes --> M1["MISMATCH"]
  B -- no --> C{"A needed fact is missing or unconfirmed?"}
  C -- yes --> M2["INSUFFICIENT_INFORMATION"]
  C -- no --> D{"Rule or its source is ambiguous?"}
  D -- yes --> M3["NEEDS_HUMAN_REVIEW"]
  D -- no --> E{"Documents unverified, officer checks pending,<br/>or source unverified / stale?"}
  E -- yes --> M4["PROVISIONAL"]
  E -- no --> M5["MATCH — shown as 'Potential match'"]
```

Every result carries the reasons, a per-criterion trace with the quoted rule text, the input fact IDs, the source URL,
the rule version and the bundle version.

---

## How the agent works

"Agent" here means the conversational layer. It is deliberately **not autonomous**: it proposes, the citizen confirms,
and a deterministic engine decides. One conversation turn:

```mermaid
sequenceDiagram
  autonumber
  actor C as Citizen
  participant UI as Browser UI
  participant V as VerbX STT/TTS
  participant API as Flask API
  participant X as Deterministic extractor
  participant L as LLM (optional)
  participant R as Rules engine
  participant DB as Postgres

  C->>UI: speaks or types (te / hi / en)
  UI->>V: audio (falls back to browser speech, then typing)
  V-->>UI: transcript
  UI->>API: POST /sessions/current/turns (JWT, X-Session-Id)
  API->>X: patterns + dialect glossary
  X-->>API: candidate facts with evidence
  opt LLM on, and data class is demo/test (or LLM_ALLOW_REAL_DATA)
    API->>L: utterance (+ English translation) with 6 s call cap
    L-->>API: candidate facts
    Note over API: merge: agree / llm_only / disagree / dropped,<br/>evidence must appear in the utterance
  end
  API->>DB: facts stored unconfirmed, with IDs and evidence
  API-->>UI: reply + facts + next question
  UI-->>C: read back in digits (high-impact facts)
  C->>UI: confirm or correct each high-impact fact
  UI->>API: PATCH fact (confirmed) / POST confirm-all
  C->>UI: "Check schemes"
  UI->>API: POST /eligibility/evaluate
  API->>R: confirmed facts only
  R-->>API: outcome + trace per rule
  API->>DB: passport version, audit event
  API-->>UI: Scheme Passport (potential / provisional)
  UI->>V: summary sentences (cached TTS, 8 s cap)
```

Design rules that follow from this:

* **Confirmation gate.** Screening is blocked (`409 PROFILE_NEEDS_CONFIRMATION`) until every high-impact fact is confirmed
  individually. A misheard "साठ" (60) as "सात" (7) is caught here, not downstream.
* **The LLM can only add or disagree, never replace.** If the LLM and the rules disagree on a high-impact value,
  *neither* is picked and the citizen chooses.
* **Every fact has provenance**: `source` (text / voice / llm / digilocker), the words heard, and a stable ID that the
  rule trace later cites.
* **Every external call has a fallback** (see [Failure modes](#failure-modes--fallbacks)); eligibility never depends on one.
* **Everything is observable**: each LLM turn is a Langfuse trace (`extract-facts` → `translate-utterance`,
  `extract-candidate-facts`, `merge-facts`), and each request is a Prometheus sample and a log line without personal data.

---

## Kiosk (assisted, operator-run, offline-capable)

The kiosk is the product's reach: a shared device (tablet or PC with a microphone) at a panchayat office, CSC or
camp, operated by a trained **operator**, used by **citizens who never sign in**. Everything about it is built around
three facts: the next person must find nothing of the last, the network may drop, and the citizen may not read.

```mermaid
stateDiagram-v2
  [*] --> OperatorSignedOut
  OperatorSignedOut --> OperatorReady: operator signs in (password + authenticator code)
  OperatorReady --> CitizenSession: Start (language chosen) — session bound to device + operator
  CitizenSession --> CitizenSession: speak / type → confirm facts → screen → draft
  CitizenSession --> HandedOff: citizen consents → case code (and optional Passport code + PIN)
  CitizenSession --> Ended: End session
  CitizenSession --> IdleWarning: no input for 180 s
  IdleWarning --> CitizenSession: "Still there?" answered within 30 s
  IdleWarning --> Ended: no answer
  CitizenSession --> Ended: 30 minutes since start, whatever the activity
  HandedOff --> Ended
  Ended --> OperatorReady: unconsented data deleted on the server
  OperatorReady --> OperatorSignedOut: Operator sign out (ends every open session on the device)
  CitizenSession --> OfflinePrescreen: network lost
  OfflinePrescreen --> CitizenSession: network back — outbox syncs once
```

| Concern | How the kiosk handles it |
|---|---|
| **Who may start a session** | Only a signed-in operator (Supabase password + TOTP, role from `app_metadata`). Citizens get no account on a kiosk. |
| **Operator sign-in storage** | In memory only (never `localStorage` / `sessionStorage`): a reload, a new tab or the next person finds nothing. |
| **Session binding** | A kiosk session answers only to its **device id** (`X-Kiosk-Device`) and the **operator** who started it; anything else gets `403 SESSION_FORBIDDEN`. Session IDs are 128-bit random, sent in a header, never in a URL, never shown on screen. |
| **Nothing left behind** | *End session*, the idle timeout, the 30-minute cap and operator sign-out all run the same server-side deletion of everything not consented. After that the server answers `410` for that session. |
| **Saving anything** | Possible only with citizen consent: a **Passport code + 4-digit PIN** shown large and read aloud (40-bit random code, argon2 PIN, weak PINs refused), or a hand-off case for a reviewer. |
| **Language and voice** | Telugu, Hindi, English; read-aloud of every reply and summary from the cached TTS; typing always works; demo phrases (simulated transcripts) run through exactly the same pipeline. |
| **Offline** | A cached, SHA-256-checked bundle of the 17 rules runs in the browser (typed input only). Drafts and results queue in a **durable outbox** (`Sync now`, `Retry`, `Refresh bundle`) and sync **exactly once** (event IDs deduplicate; the server re-checks online and reports changed results). |
| **Accessibility intent** | Large controls, ARIA labels, number read-back in digits, spoken prompts. No formal WCAG audit yet ([Limitations](#limitations)). |
| **Operations** | `anvaya_active_sessions{mode="kiosk"}`, `anvaya_sync_events_total{status}` and `anvaya_sync_result_changed_total` show kiosk load and offline health in Grafana. |

Details of the session rules, idle timer and sign-out are under [Accounts and modes](#accounts-and-modes); the offline
engine and sync under [Failure modes](#failure-modes--fallbacks).

---

## Quick start

**Docker**

```bash
cp .env.example .env          # optional: VerbX / LLM keys, staff passwords, Grafana settings (see Configuration)
docker compose up --build
docker compose exec anvaya python -m anvaya.manage prerender-audio   # once, if VerbX is configured
```

| Service | URL | Notes |
|---|---|---|
| App | http://localhost:5000 | API + UI; `GET /api/v1/ready` shows catalogue, rules and integration status |
| Prometheus | http://localhost:9090 | scrapes `anvaya:5000/metrics` every 5 s |
| Grafana | http://localhost:3000 | dashboard "Anvaya AI — Operations" opens as home; read-only anonymous viewing unless `GRAFANA_ANONYMOUS=false` |

All three services have healthchecks (`docker compose ps` shows `healthy`). State lives only in the named volumes
`anvaya-db`, `prometheus-data` and `grafana-data`; the only bind mounts are the read-only configs in `monitoring/`.

### Run without Docker

For when Docker Desktop will not start. In Ubuntu / WSL, from the repo (for example
`cd /mnt/c/Users/<you>/OneDrive/Desktop/anvaya/Anvaya-AI`):

```bash
bash scripts/run_local.sh                     # app + built frontend on http://localhost:5000 (Ctrl-C stops)
bash scripts/run_local.sh --prerender-audio   # same, and fill the read-aloud audio cache in the background
bash scripts/run_monitoring_local.sh          # second terminal: Prometheus :9090 + Grafana :3000
```

**`run_local.sh`**
* Reads the repo-root `.env`, creates a virtualenv and installs `backend/requirements.txt`.
* Runs `manage init` when the database has no rules yet.
* Builds the frontend once. It rebuilds only when the frontend sources change, or with `--rebuild-frontend`.
* Starts gunicorn on `:5000`, serving the API and the built frontend. `PORT` changes the port.
* Keeps everything it generates in `~/.local/anvaya` on the Linux filesystem: the venv, `anvaya.db` and a build copy of
  `frontend/`. The repo, its Windows `node_modules` and `backend/.venv` are left untouched.
* Needs no sudo. Without `python3-venv` it bootstraps pip with the official `get-pip.py`. Without a Linux Node ≥ 18 it
  downloads a pinned, checksum-verified Node 20 into `~/.local/anvaya/node`.

**`run_monitoring_local.sh`**
* Downloads the same Prometheus 2.54.1 and Grafana 11.2.2 the compose file uses (pinned, sha256-verified) into
  `~/.local/anvaya-monitoring`, never into the repo.
* Runs them with the repo's `monitoring/` configs. Only the Docker hostnames are rewritten, in a derived copy.
* `PROMETHEUS_PORT` / `GRAFANA_PORT` move them off 9090 / 3000 if another stack holds those ports.

From Windows, scripts calling the WSL app should use `http://127.0.0.1:5000`. There, `localhost` tries IPv6 first,
which some HTTP clients only give up on after about 2 s; browsers are unaffected.

**Kubernetes:** `cp k8s/secrets.env.example k8s/secrets.env && kubectl apply -k .` deploys the app, Prometheus and
Grafana with restricted pod security, NetworkPolicies and PVCs. See [`k8s/README.md`](k8s/README.md).

**Local dev**

```bash
cd backend && pip install -r requirements.txt
python -m anvaya.manage init       # imports data/raw/*.csv, loads the curated rules, seeds staff accounts
set -a; . ../.env; set +a           # optional (docker compose and run_local.sh load .env themselves)
python -c "from anvaya import create_app; create_app().run(port=5000)"
cd ../frontend && npm install && npm run dev    # http://localhost:5173, proxies /api to :5000
```

**Tests**

```bash
cd backend  && python -m pytest -q                     # rules engine, extraction, API, accounts (mock JWKS), TC1–TC5
cd backend  && python -m pytest -m live -s             # real VerbX + Groq/Gemini calls (keys from .env), demo sentences
cd backend  && python -m anvaya.manage eval-extraction # extraction precision/recall, deterministic vs + LLM
cd frontend && npm test && npm run build               # offline engine, confirmation, speech, sign-in/save/history/delete, kiosk idle
```

**Staff accounts** (operator = kiosk, reviewer, admin = data steward) are Supabase Auth users who sign in with email +
password. Their role lives in `app_metadata`, which only the server can set: `python -m anvaya.manage seed-staff`
creates or updates them from `ANVAYA_<ROLE>_EMAIL` + `ANVAYA_<ROLE>_PASSWORD`. There are no demo passwords. See
[Accounts and modes](#accounts-and-modes).

**Startup check.** On boot the app logs one line per integration (VerbX, each LLM provider, metrics) as `configured`
or `missing (missing VAR, …)`. It logs variable names, never values. Missing optional keys never stop the app, and
`/api/v1/ready` stays 200 as long as the catalogue and rules are loaded.

---

## Accounts and modes

| Who | How they sign in | What is kept |
|---|---|---|
| Citizen, personal phone | Automatically an **anonymous Supabase session**. "Save my passports" links an email (6-digit code) to the same user id, or Google when `GOOGLE_AUTH_ENABLED=true` | Nothing beyond the session until the citizen ticks the consent (text version + time are recorded) and links an email / Google identity or sets a Passport code + PIN |
| Citizen without email | **Passport code + PIN** (`PSP-XXXX-XXXX` + 4 digits), on a phone or at a kiosk | The saved passport; the code can later be attached to an account |
| Kiosk | The **operator** signs in; citizens never get an account on a kiosk | Nothing. Saving is possible only with a Passport code + PIN, shown large and read aloud. Idle sessions end on their own |
| Operator / reviewer / admin | Supabase email + password **+ TOTP** (authenticator app, enrolled on first sign-in); role from `app_metadata.role` | — |

**How it fits together**

* The browser uses `@supabase/supabase-js` **for sign-in only** (`VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY`).
  It never queries tables or storage; every data call goes to Flask with the access token.
* Flask verifies the token on **every request** (`backend/anvaya/auth.py`): ES256/RS256 signature against the
  project's JWKS (`/auth/v1/.well-known/jwks.json`, cached 10 minutes, re-read at most every 30 s for an unknown key
  id), issuer `<SUPABASE_URL>/auth/v1`, audience `authenticated`, expiry. Invalid tokens get `401`; symmetric (HS256)
  tokens are never accepted. The auth user id maps to the app's citizen (`citizen_id = CIT_<user id>`, no lookup), and
  a signed-in citizen's sessions answer only to that user's token.
* `SUPABASE_SECRET_KEY` is used only server-side, for the Auth admin API (delete an account, seed staff). It is sent in
  the `apikey` header, never logged, never returned and never in the browser bundle.
* Row Level Security stays on with no policies for every table, including `citizens`, `passport_versions` and
  `passport_attempts`.

**Saved passports**

* Every screening of a saved citizen is a **passport version**: rule ids + versions, the fact ids (and values compared),
  document marks and outcomes. *My Passports* lists them.
* **What changed since <date>** compares the passport as it was then with the latest one and gives, per scheme, the
  outcome before → after and the reason: a fact the rule reads changed (e.g. age 67 → 52), the rule's version changed,
  or a document status changed.
* A new session of a saved citizen starts from the **saved profile**. Age and income confirmed more than 90 days ago
  come back unconfirmed and block screening until confirmed again; eligibility and confirmation rules are unchanged.
* **Delete my account and data** removes facts, passport versions, sessions and the Supabase Auth user (admin API,
  done first: if it fails nothing is deleted). Only cases the citizen consented to hand to a reviewer stay. The audit
  event records counts, never values. (Audio is never stored. Uploaded documents are deleted with the account; see
  [Document uploads](#document-uploads).)

**Passport code + PIN**

* Code: 8 symbols from Crockford base32 (no I/L/O/U) = 40 random bits, stored as `sha256(ANVAYA_PASSPORT_PEPPER +
  code)`. PIN: 4 digits, argon2-hashed; repeated, sequential, paired and year-like PINs (1111, 1234, 1212, 1122,
  1990 …) are refused.
* At most 5 failed attempts per code and per IP address in 15 minutes; after 10 failures a code is locked for 1 hour.
  A wrong code and a wrong PIN get the same answer (`401 PASSPORT_CODE_OR_PIN_WRONG`); limits give `429`.
* Signed-in citizens can attach a code to their account (*My Passports → Add a Passport code*).

**Kiosk temporary sessions**

* The operator's sign-in is kept **in memory only** at a kiosk (supabase-js storage adapter, `frontend/src/authStorage.ts`):
  never `localStorage` or `sessionStorage`, so a reload or a new tab finds nothing and the operator signs in again.
  Switching a browser to kiosk mode also drops any personal sign-in stored on it.
* Session ids are **128-bit random** (`SES_` + 32 hex). The browser never puts one in a URL: every
  `/sessions/<id>/...` call is sent as `/sessions/current/...` with the id in the `X-Session-Id` header, and request
  logs hold the route pattern only. The kiosk keeps the id in memory only and never shows it on screen.
* A kiosk session is **bound to the kiosk device id** (random, `X-Kiosk-Device`) **and the operator** who started it:
  any other device, operator or citizen token gets `403 SESSION_FORBIDDEN`.
* After `KIOSK_IDLE_SECONDS` (default 180) without input, a 30-second **"Still there?"** warning appears (and is read
  aloud). Without an answer the session ends exactly like *End session*: the server deletes everything not consented.
* Absolute limit: a kiosk session ends after `KIOSK_MAX_SESSION_MINUTES` (default **30**) whatever the activity
  (server `expires_at`; the page ends it at that moment too).
* **Operator sign-out** (`POST /api/v1/kiosk/sign-out`) ends every citizen session still open on that device, with the
  same deletion as *End session*. After *End session*, refreshing the browser cannot restore anything: the id is gone
  from memory, the server answers `410` for it, and its unconsented data is already deleted.

### Document uploads

Citizens can upload a photo or PDF of each required document into the private Supabase Storage bucket `documents`.
The browser never talks to Storage; everything goes through the backend (`backend/anvaya/documents.py`, `storage.py`).

1. `POST /api/v1/sessions/<sid>/documents/<doc_key>/upload-url` checks session ownership and the citizen's upload
   consent (at a kiosk also a consented hand-off case) and returns the backend's own **signed, single-use upload link,
   valid 5 minutes**. (Supabase's own signed upload URLs live a fixed 2 hours, so they are not used.) Stored at
   `<user id or session id>/<case id or session id>/<doc_key>/<uuid>`.
2. `PUT /api/v1/uploads/<token>`: JPEG, PNG or PDF, at most 5 MB. The type is checked by magic bytes, not by the
   declared type; after storing, the object is read back (size + magic bytes) and deleted if anything differs.
3. The document state becomes **uploaded** (between the citizen's "I have it" and **verified**). Only a reviewer can
   verify it; until then outcomes stay PROVISIONAL (`EVIDENCE_NOT_VERIFIED`). *Request re-upload* deletes the file.
4. `GET .../documents/<doc_key>/view-url` gives a **2-minute** link to the owner, or to a reviewer when the session has a
   case the citizen consented to share. Every view is audited (who, when, which document; never the content). View
   responses are `no-store`; kiosks keep no copy (the file is dropped from the page after upload and not previewed).
5. Uploads are never read for content: no OCR, no ID-number extraction, never sent to an LLM. Before uploading, the page
   asks (en/hi/te) for a masked Aadhaar with only the last 4 digits visible.
6. Deleted with the account, with unsaved sessions (end of session / 24 h), `REVIEWED_UPLOAD_RETENTION_DAYS` (default
   30) after the case is reviewed, and right away on *Request re-upload* — inside the hourly retention job. If Storage
   is unreachable, the rows stay and the next run retries; account deletion stops with nothing deleted.

### Form Helper (prepared drafts)

The draft page has a **Form Helper**. Anvaya never submits anything to a government portal; the status reads
"Draft ready — submit at the office/portal" and the citizen takes the details there.

* **Copy-ready view** (`GET /api/v1/drafts/<id>/helper?language=en|hi|te`): every field in the order official forms
  usually follow, each with a copy button and a source tag (confirmed / inferred / citizen-entered / missing). Missing
  fields are highlighted with what to bring. **Aadhaar and bank account numbers are never collected**: they are listed
  as "provide at the office", and any run of 9+ digits typed into a draft field is masked in the view and the PDF.
* **Steps:** the dataset's `application_process` as a numbered checklist. For hi / te the steps are VerbX machine
  translations (cached in `translations`), labelled "machine translation"; without VerbX the English steps are shown
  with a note. A read-aloud button uses the cached TTS. The official link comes from the dataset's source URLs
  (http/https only) with a QR code (`GET /api/v1/schemes/<id>/portal-qr.svg`).
* **PDF** (`GET /api/v1/drafts/<id>/pdf?language=…`): fields with source tags, the document checklist, the case code
  (only if the citizen's browser sends it in `X-Case-Code` and it matches: codes are stored hashed), the steps, the
  link + QR, and the watermark "Draft prepared by Anvaya AI — not submitted to any government office" on every page.
  Layout (A4): a green brand band with a "DRAFT · NOT SUBMITTED" badge on every page; a title block (scheme name, status pill,
  a strip with draft id, version, date and case code); a ruled table with a coloured source tag per value (green confirmed /
  citizen-entered, blue inferred, amber missing, whose row is shaded); an amber "Bring to the office" panel; a tick-box
  document checklist; numbered steps; the official link in a card with its QR code and a "Scan to open the official page"
  line; and a footer with the disclaimer and the page number. All labels come in English, Hindi and Telugu
  (`TEXT` in `formhelper.py`); the colours are the `INK/BRAND/AMBER…` constants above `render_pdf`.
  Noto Sans / Devanagari / Telugu (SIL OFL, `backend/anvaya/data/fonts/`) are embedded, shaped with HarfBuzz
  (fpdf2 + uharfbuzz). Only the draft's owner (same session rules as the draft, including kiosk device + operator) or a
  reviewer / admin once the draft has a case can read it (aal2 for staff); each download is audited without values.
  Shaped Indic glyphs that have no Unicode value of their own are mapped to a zero-width space so the PDF's text layer
  keeps the real letters; some viewers still show a space inside Telugu conjuncts.

### Privacy and retention

| Data | Deleted |
|---|---|
| Unsaved session data (facts, turns, screenings, drafts) | when a kiosk session ends; otherwise **24 h** after the session started |
| Unsaved anonymous Supabase users | with their data after 24 h (admin API) |
| Saved passports | after `PASSPORT_RETENTION_DAYS` (default **365**) without use, Auth user included |
| Uploaded documents | with the account; with unsaved sessions; `REVIEWED_UPLOAD_RETENTION_DAYS` (default **30**) after the case is reviewed; at once on *Request re-upload* |
| Rate-limit counters (client address and code only as hashes) | when their window ends; deleted by the retention job |
| Consented hand-off cases | kept for the reviewer, also after account deletion |

Retention runs as a scheduled job: hourly from the in-app timer, hourly from the GitHub Actions call to `POST /internal/jobs/run` (which also
wakes a sleeping server), and on demand with `python -m anvaya.manage cleanup`. Each run is recorded in `job_runs`; see [Scaling](#scaling). The policy is shown in English, Hindi and Telugu wherever something can be saved.

### Supabase Auth setup

1. **Authentication → Sign In / Providers:** enable *Allow anonymous sign-ins*, *Email*, and (optional) *Google*.
   Turn on *Allow manual linking* if Google linking is used. Keep CAPTCHA in mind for anonymous sign-ins (Supabase
   allows 30 per hour per IP by default).
2. **JWT signing keys:** use asymmetric keys (ES256 or RS256; new projects have them). The backend refuses HS256.
3. **Email templates:** put `{{ .Token }}` in *Magic Link* (returning sign-in) and *Change Email Address* (linking an
   email to an anonymous user) so citizens receive a 6-digit code rather than a link.
4. **URL configuration:** add the app's URL to the redirect allow-list (needed for Google).
5. **MFA:** keep *TOTP (App Authenticator)* enabled (it is by default). The backend refuses staff tokens below `aal2`.
6. **CAPTCHA:** *Authentication → Attack Protection → Enable CAPTCHA protection*, provider *Cloudflare Turnstile*, with
   the Turnstile **secret** key; put the **site** key in `VITE_TURNSTILE_SITE_KEY`. Supabase then requires a valid token
   on sign-in requests (anonymous, email OTP, password), which the app sends. (Enabled on the live project.)
7. Put the keys in `.env` (names below), then create staff accounts:
   `set -a && source .env && set +a && cd backend && python -m anvaya.manage seed-staff`.
8. For the free tier: `.github/workflows/scheduled-jobs.yml` runs hourly. It calls `POST APP_URL/internal/jobs/run`
   (which also wakes a sleeping server) and, in the 03:xx UTC run, `APP_URL/api/v1/ready`, whose cheap database queries
   keep the project from being paused. Repository secrets: `APP_URL` and `INTERNAL_JOBS_TOKEN` (see *Scaling*).

### Auth hardening

**Staff MFA (TOTP).** Operators, reviewers and admins enrol an authenticator app at their first sign-in (QR code, or
the setup key typed in by hand) and enter its 6-digit code on every sign-in after that. The backend enforces it, not
only the UI: `common.current_user()` / `require_role()` refuse a staff token whose `aal` claim is not `aal2` with
`403 MFA_REQUIRED` on **every** staff call (reviewer, admin, kiosk session creation, Passport-code resume at a kiosk,
reviewer document views). Only `GET /auth/me` answers at `aal1`, with `mfa_required: true`, so the page can ask for
the code. *Security → Reset* (admin) removes a staff member's factors through the Auth admin API and signs their
sessions out; they enrol again at the next sign-in. `ANVAYA_STAFF_MFA_REQUIRED=false` exists for a local demo only.

**Bot protection.** A Cloudflare Turnstile widget (`VITE_TURNSTILE_SITE_KEY`) guards anonymous sign-in, email OTP and
staff password sign-in; its token goes to supabase-js as `captchaToken` and Supabase verifies it. Tokens are single
use: the widget resets after every attempt. Without a site key (local dev) the widget is skipped and both the browser
console and the backend startup report warn. Our own session-creating endpoints are rate-limited per IP
(`POST /sessions`, `POST /passport/resume`: `ANVAYA_SESSION_CREATE_LIMIT`, default 20/min; `POST /auth/events`:
`ANVAYA_AUTH_EVENT_LIMIT`, 30/min), on top of the Passport-code attempt limits.

**Sign out of all devices.** *My Passports* (citizens) and the staff bar have *Sign out of all devices*:
`POST /api/v1/auth/sign-out-all` calls Supabase's global sign-out (all refresh tokens revoked) **and** records the
time in `auth_revocations`. Supabase leaves already-issued access tokens valid until they expire, so the backend also
refuses every token whose sign-in began before that time (the earliest `amr` timestamp, which a token refresh does
not change) with `401 SESSION_REVOKED`. A staff password change (*Change password*) and `manage seed-staff` (which
sets the password again) force the same global sign-out.

**Citizen rights (DPDP Act 2023).** *Download my data* (`GET /api/v1/account/export`, or `/sessions/current/export`
for a Passport-code holder or an unsaved session) returns JSON with the citizen's current facts and their source,
passport versions, consents, the document list (names and states, never the files), document marks, case statuses
and linked identities — nothing about other people (utterances and reviewer notes are left out because they can
describe others). The consent notice (en/hi/te, version `save-2026-10-dpdp`) states the purpose, what is stored, how
long, and how to withdraw. *Withdraw consent* is the existing *Delete my account and data*. Both are audited without
values.

**Auth audit.** `auth_events` records sign-in success/failure, OTP requested, MFA enrolled/verified/failed/required/
reset, role changes, password changes, global and kiosk sign-outs, data exports, deletions and DigiLocker links:
actor id, event, time and the **IP prefix only** (/24 or /48), with enums and counts as details — never emails, phone
numbers, codes or tokens. Sign-in itself happens between the browser and Supabase, so those events are reported by
the browser (`POST /auth/events`; the actor is the verified token's user when there is one). *Security* (admin) shows
the last 500.

**DigiLocker / Meri Pehchaan (disabled).** `backend/anvaya/digilocker.py` is a generic OAuth 2.0 / OpenID Connect
authorization-code flow with **PKCE (S256)**, a single-use `state` (10 minutes, bound to the signed-in user) and a
`nonce`; the ID token's signature is checked against `DIGILOCKER_JWKS_URL` (asymmetric algorithms only), with
audience = client id, expiry and the optional `DIGILOCKER_ISSUER`. On success the provider subject is linked to the
citizen (peppered hash; no tokens kept — Supabase's own identity linking supports only its built-in OAuth providers)
and name, date of birth and gender become facts with `source="digilocker"`, confirmed and verified. Scopes naming
Aadhaar are dropped and no Aadhaar number is ever read or stored. Everything comes from the environment
(`DIGILOCKER_ENABLED=false`, `DIGILOCKER_CLIENT_ID`, `DIGILOCKER_CLIENT_SECRET`, `DIGILOCKER_AUTH_URL`,
`DIGILOCKER_TOKEN_URL`, `DIGILOCKER_JWKS_URL`, `DIGILOCKER_REDIRECT_URI` → the app's `/auth/digilocker/callback`,
`DIGILOCKER_SCOPES`); no real endpoint is in the code. The option on the **Sign in** page shows "Coming soon" unless `DIGILOCKER_ENABLED=true` and every
value is set; the verified details appear on the **Profile** page (`GET /auth/digilocker/me`), and *unlink* (`DELETE /auth/digilocker/link`) releases them for editing. It is tested end to end against a local mock OIDC provider (`tests/test_auth_hardening.py`: code
exchange, PKCE, invalid / replayed state, expired code, bad signature, wrong nonce). **Not enabled in this build:**
DigiLocker / Meri Pehchaan access requires partner onboarding — a registered Indian entity, an official domain, a
digital signature, and approval by the onboarding committee.

**Phone OTP (disabled).** `PHONE_OTP_ENABLED=false`. The sign-in UI (Indian mobile numbers, `+91`) and the backend
paths (a phone-verified Supabase user is a linked citizen like an email one) are ready for Supabase phone auth. Indian
SMS needs **DLT registration** (TRAI: the entity, sender ID and message templates) and a paid SMS provider configured
in Supabase, so it is off here.

**Browser security.** Flask sends a strict `Content-Security-Policy`: scripts only from this origin and
`challenges.cloudflare.com`, network calls only to this origin and `SUPABASE_URL`, frames only for Turnstile and our
own document previews, `data:` images for the MFA QR code, no inline scripts, no `eval`, `object-src 'none'` (plus
`nosniff` and `Referrer-Policy: no-referrer`). supabase-js uses the PKCE flow, so an OAuth redirect carries a one-time
code in the URL, never tokens; tokens are never logged. Sign-in storage per mode: kiosk memory only, personal device
`localStorage`. (The Vite dev server does not send the CSP; the built app served by Flask does.)

---

## Configuration (`.env`)

Copy `.env.example` to `.env`; every variable is optional. Docker compose, `scripts/run_local.sh` and the live tests
read it, and `.env` is gitignored.

| Variable | Default | Purpose |
|---|---|---|
| `VERBX_BASE_URL`, `VERBX_API_KEY` | unset | VerbX STT / TTS / translation. Unset: browser speech + text, English scheme names |
| `VERBX_SHELL`, `VERBX_TTS_VOICE` | `saas`, `verbx-female` | VerbX shell header; TTS voice (`verbx-female` / `verbx-male`) |
| `VERBX_TIMEOUT_S` | `15` | per VerbX HTTP call (one retry on 5xx/timeout) |
| `ANVAYA_TTS_WAIT_S` | `8` | longest a read-aloud request waits before answering "audio unavailable" |
| `ANVAYA_LLM_EXTRACTION` | `off` | `on` enables LLM candidate facts |
| `LLM_PROVIDERS` | unset | fallback order, e.g. `groq,gemini` (also `ollama`, `anthropic`) |
| `GROQ_API_KEY`, `GROQ_MODEL`, `GROQ_BASE_URL` | unset, unset, Groq's OpenAI URL | Groq; example model `openai/gpt-oss-120b` |
| `GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_BASE_URL` | unset, unset, Gemini's OpenAI URL | Gemini; example model `gemini-3.5-flash-lite` |
| `<NAME>_REASONING_EFFORT`, `<NAME>_DAILY_REQUESTS` | unset, `0` | per provider: `low` keeps Gemini inside the call cap; soft daily cap (0 = none) |
| `LLM_CALL_TIMEOUT_S`, `LLM_TURN_BUDGET_S` | `6`, `7` | per LLM call; per turn including translation (then rule-based only) |
| `LLM_CIRCUIT_FAILURES`, `LLM_CIRCUIT_OPEN_S` | `5`, `60` | consecutive failures that open a provider's circuit, and for how long |
| `LLM_ALLOW_REAL_DATA` | `false` | `false`: LLMs see demo/test data only |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | unset | all three set → LLM turns traced to Langfuse (`LANGFUSE_HOST` also accepted). Any unset → SDK never imported |
| `LANGFUSE_TIMEOUT_S`, `LANGFUSE_TRACING_ENVIRONMENT` | `2`, `default` | export HTTP timeout (export runs in the background); Langfuse environment label |
| `LANGFUSE_TRACE_EVAL` | unset | `1`: `eval-extraction` also pushes a Langfuse dataset and one experiment per configuration |
| `SUPABASE_URL`, `SUPABASE_SECRET_KEY` | unset | server: token verification (URL) and the Auth admin API (secret key, server only). Unset URL: no staff sign-in or accounts; Passport code + PIN still works |
| `VITE_SUPABASE_URL`, `VITE_SUPABASE_PUBLISHABLE_KEY` | unset | browser sign-in only (baked into the frontend build; Docker build args) |
| `GOOGLE_AUTH_ENABLED` | `false` | show "Continue with Google" |
| `ANVAYA_PASSPORT_PEPPER` | dev pepper, with a warning | pepper for Passport code hashes; set a long random value in production |
| `PASSPORT_RETENTION_DAYS`, `ANVAYA_UNSAVED_RETENTION_HOURS`, `ANVAYA_RETENTION_INTERVAL_MIN` | `365`, `24`, `60` | retention of saved / unsaved data; how often retention runs in the app (0 = only `manage cleanup`) |
| `INTERNAL_JOBS_TOKEN` | unset (endpoint answers 404) | secret for `POST /internal/jobs/run`, sent in the `X-Internal-Token` header; also a GitHub secret of the same name |
| `KIOSK_IDLE_SECONDS` | `180` | kiosk idle timeout (a 30 s warning comes first) |
| `KIOSK_MAX_SESSION_MINUTES` | `30` | absolute length of a kiosk citizen session |
| `VITE_TURNSTILE_SITE_KEY` | unset | Cloudflare Turnstile site key (public). Unset: no CAPTCHA widget, startup warning |
| `DIGILOCKER_STATUS`, `PHONE_OTP_STATUS` | `coming_soon` | `off` / `coming_soon` / `on`, read at runtime by the frontend from `GET /api/config`. `DIGILOCKER_STATUS` is reported `on` exactly when the DigiLocker adapter is enabled and fully configured (`DIGILOCKER_ENABLED` + all its variables); an `on` that cannot work is shown as `coming_soon`. Phone OTP routes answer `503 FEATURE_NOT_AVAILABLE` until `on` (and `501` if switched on without an integration) |
| `TURNSTILE_SITE_KEY` (or `VITE_TURNSTILE_SITE_KEY`) | unset | Cloudflare Turnstile **site** key (public). Either name works. The server returns it from `GET /api/config`, so setting it on the server alone is enough; no rebuild is needed (a build-time `VITE_TURNSTILE_SITE_KEY` also works) |
| `ANVAYA_STAFF_MFA_REQUIRED` | `true` | staff API calls need an `aal2` (TOTP) token; `false` only for a local demo |
| `ANVAYA_SESSION_CREATE_LIMIT`, `ANVAYA_AUTH_EVENT_LIMIT` | `20`, `30` | per-IP requests per minute: session creation and Passport resume; browser auth-event reports |
| `PHONE_OTP_ENABLED` | `false` | phone OTP sign-in (needs DLT registration and an SMS provider) |
| `DIGILOCKER_ENABLED`, `DIGILOCKER_CLIENT_ID`, `DIGILOCKER_CLIENT_SECRET`, `DIGILOCKER_AUTH_URL`, `DIGILOCKER_TOKEN_URL`, `DIGILOCKER_JWKS_URL`, `DIGILOCKER_REDIRECT_URI`, `DIGILOCKER_SCOPES`, `DIGILOCKER_ISSUER` | `false`, unset, `openid` | DigiLocker / Meri Pehchaan OIDC adapter (see [Auth hardening](#auth-hardening)) |
| `SUPABASE_STORAGE_BUCKET`, `REVIEWED_UPLOAD_RETENTION_DAYS` | `documents`, `30` | private bucket for uploads; days uploads are kept after the case is reviewed |
| `SUPABASE_JWKS_CACHE_S` | `600` | how long signing keys are cached |
| `ANVAYA_ADMIN_EMAIL` / `_PASSWORD`, `ANVAYA_REVIEWER_EMAIL` / `_PASSWORD`, `ANVAYA_OPERATOR_EMAIL` / `_PASSWORD` | unset | read only by `manage seed-staff` (Supabase staff accounts; password ≥ 8 characters) |
| `ANVAYA_METRICS_TOKEN` | unset | when set, `/metrics` needs `Authorization: Bearer <token>` |
| `ANVAYA_DEMO_TEST_RUNS` | `off` | `on` lets anyone run/reset TC1–TC5 (otherwise admin only) |
| `ANVAYA_SESSION_TTL_HOURS`, `ANVAYA_CASE_CODE_TTL_HOURS` | `12`, `72` | session and case-code lifetimes |
| `ANVAYA_CODE_LOOKUP_LIMIT` | `10` | case-code lookups per minute |
| `ANVAYA_RULE_BUNDLE_VERSION`, `ANVAYA_DEFAULT_FRESHNESS_DAYS` | `rules-2026.10.1`, `180` | rule bundle label; source-freshness fallback |
| `DATABASE_URL` | unset | set → PostgreSQL (Supabase Session pooler URI); unset → SQLite. See [Database](#database) |
| `ANVAYA_DB_POOL_MAX`, `ANVAYA_DB_CACHE_CHECK_S` | `5`, `5` | Postgres connections per process; seconds between in-memory cache version checks |
| `ANVAYA_DB`, `ANVAYA_DATASET`, `ANVAYA_FRONTEND_DIST` | `backend/instance/anvaya.db`, the CSV in `data/raw/`, `frontend/dist` | paths |
| `GRAFANA_ADMIN_PASSWORD` | `anvaya-grafana` | Grafana `admin` password (applied when its data volume is first created) |
| `GRAFANA_ANONYMOUS` | `true` | read-only anonymous dashboard viewing |
| `PORT`, `PROMETHEUS_PORT`, `GRAFANA_PORT` | `5000`, `9090`, `3000` | no-Docker scripts only |

A number that cannot be parsed falls back to its default, with a startup warning.

---

## Database

The backend picks its database from `DATABASE_URL`:

| `DATABASE_URL` | Database | Used by |
|---|---|---|
| unset (default) | SQLite file `ANVAYA_DB` (`backend/instance/anvaya.db`) | local development, tests, CI, the offline kiosk |
| set | PostgreSQL (psycopg 3 + a connection pool) | the hosted deployment, on Supabase |

Both run the same SQL, translated per dialect in `backend/anvaya/db.py`. Timestamps stay ISO-8601 text and JSON stays
text, so the app behaves the same on both. The full test suite runs on both: `pytest` (SQLite), and
`TEST_DATABASE_URL=postgresql://…@localhost:5432/… pytest` (a throwaway local `postgres:16`; CI starts one as a
service). Tests never read `DATABASE_URL` and refuse a Supabase `TEST_DATABASE_URL`.

**Schema and migrations.** Numbered migrations (`backend/anvaya/migrations.py`) are applied at startup and recorded in
`schema_migrations`. On Postgres they run under an advisory lock, so several processes can start at once. An older
SQLite file is upgraded in place. `python -m anvaya.manage init` is idempotent: it skips the catalogue import when
the CSV's sha256 is unchanged, upserts the curated rules (keeping who verified them against the source), and
creates staff accounts only if they are missing.

**Supabase setup**

1. Dashboard → **Connect** → **Session pooler**. Copy the URI
   (`postgresql://postgres.<project-ref>:<password>@aws-0-<region>.pooler.supabase.com:5432/postgres`) into `.env` as
   `DATABASE_URL`. The direct connection is IPv6-only on the free plan; the Session pooler works over IPv4.
   Session mode (port 5432) is used rather than transaction mode.
2. Run `python -m anvaya.manage init` once. The first import over the network takes about 30 s; later runs take a
   few seconds.
3. Connection settings:
   - TLS is required (`sslmode=require` is added unless the URL sets `sslmode`).
   - Connect timeout 10 s, statement timeout 10 s, at most `ANVAYA_DB_POOL_MAX` (5) connections per process.
   - `prepare_threshold=None`: no server-side prepared statements, which the pooler does not support.
   - A dropped connection is retried once, but only when nothing in the transaction was sent yet.
   - The URL and password are never logged. `/api/v1/ready` reports only
     `"db": {"backend": "postgres", "status": "ok"|"error", "rls": "ok"|"error"}`.

**Row Level Security.** After the migrations, every table has RLS enabled with **no policies**. Supabase's public
REST API (the `anon` / `authenticated` roles behind the publishable key) can therefore read or write nothing:
`GET /rest/v1/schemes` returns `[]`, and an insert fails with `42501`. The backend connects as the tables' owner,
which RLS does not restrict. `/ready` is not ready (503) on Postgres if any table lacks RLS. Do not add policies and
do not use the publishable key for app data.

**Free plan pause.** A free Supabase project pauses after 7 days without activity, and the app then reports
`db.status: "error"` until the project is resumed in the dashboard. The scheduled workflow (`scheduled-jobs.yml`) calls `/api/v1/ready` daily to prevent that.

**Latency.** The hosted database is in Seoul and the app runs on Render Singapore, about 70 ms per round trip.
Requests are written to need as few round trips as possible:

- One pooled connection and at most one write transaction per request.
- A request's INSERT/UPDATE/DELETEs are queued and sent together with the next read or with `COMMIT`, in one
  pipeline. The same insert repeated (one per extracted fact) becomes one batched statement.
- Independent reads go in one round trip (`query_many`). Joins and `IN (…)` replace per-row lookups.
- Rules, catalogue facets, the graph summary and TTS cache counts stay in memory, keyed by a `data_versions` row.
  That row is re-checked at most every `ANVAYA_DB_CACHE_CHECK_S` (5) seconds. Prerendered audio clips and
  translations are kept in memory too. UI strings (`i18n.py`) live in code and never touched the database.
- Every API request logs `db_queries`, `db_roundtrips` and `db_ms` (no SQL, no values). Prometheus histograms:
  `anvaya_db_queries_per_request`, `anvaya_db_roundtrips_per_request`.

Queries per request (statements, excluding BEGIN/COMMIT; a batched insert counts once). "Before" is the previous code
traced on SQLite; on Postgres each of its statements, plus BEGIN and COMMIT, would have been a round trip:

| Request | Before: queries (round trips on Postgres) | After: queries / round trips |
|---|---|---|
| create session | 3 (5) | 2 / 1 |
| conversation turn (TC1 sentence, 9 facts) | 53 (55) | 6 / 2 (+1 / +1 with LLM extraction on: cache lookup) |
| evaluate | 11 (13) | 7 / 2 (8 / 3 when the cache version check is due) |
| create draft | 12 (16) | 10 / 4 |
| hand-off | 13 (17) | 10 / 3 |

**Concurrency.** Draft and hand-off idempotency keys, case-code issuance and offline-sync dedupe use unique
constraints with `INSERT … ON CONFLICT DO NOTHING RETURNING`, never read-then-write:
- The key (or sync event) is claimed in the same transaction as the work. A concurrent duplicate waits for that
  commit, then replays the stored response.
- Hand-off locks the draft row (`SELECT … FOR UPDATE`).
- Case codes have a unique index.
- `tests/test_db.py` sends 10 identical hand-offs in parallel and checks that exactly one case and one code result,
  on both databases.

---

## Read-aloud (VerbX TTS, cached)

VerbX TTS took 0.9–10.5 s per sentence in testing, so read-aloud never holds up the conversation:

* **Text first.** Replies, the greeting and the Scheme Passport summary appear at once; audio plays when it arrives.
  Turns return `reply_segments` and evaluations return `voice_summary_segments`. The browser requests every sentence at
  once and plays them in order.
* **Cache.** Each synthesized sentence is stored in `tts_cache`, keyed by `sha256(text, language, voice)`. The text
  itself is not stored. Identical requests that arrive together share one VerbX call. A cached clip comes back in
  about 10–25 ms.
* **Prerendered prompts.** `python -m anvaya.manage prerender-audio` synthesizes and pins 267 prompts across en, hi
  and te:
  * the greeting;
  * every follow-up question;
  * the confirmation prompts;
  * the summary templates: the intro, the counts up to `--max-count` (default 4), one line per curated scheme for
    "potential match" and "provisional match", and a single missing document.

  It paces itself (`--per-minute 40`) and retries on VerbX HTTP 429. Re-running it only fills gaps.
* **Live sentences.** Sentences that repeat the citizen's own details are synthesized live. `manage cleanup` removes
  them after `ANVAYA_SESSION_TTL_HOURS`.
* **8 s cap.** If a sentence isn't ready within 8 s, or VerbX fails, the UI keeps the text and shows a small "audio
  unavailable" note. The synthesis finishes in the background, so pressing *Listen* again plays at once.

## LLM extraction (optional, free providers)

The deterministic extractor is the primary path and always runs. With `ANVAYA_LLM_EXTRACTION=on` an LLM reads the same
utterance (plus the VerbX English translation for Hindi/Telugu script), and its facts are **merged**, never trusted:

| LLM result vs deterministic | What happens |
|---|---|
| same attribute, same value | deterministic fact kept, noted "confirmed by both" |
| attribute only the LLM found | added as an **unconfirmed** candidate (`source=llm`); never replaces a fact the profile holds |
| different value on age / income / state / area / household size | **neither is picked**: the citizen chooses between the two ("उम्र: 60 वर्ष या 70 वर्ष?") |
| different value on a low-impact attribute | deterministic value kept, never auto-confirmed |
| evidence not found in the utterance or its translation; an invalid value; a relative's age; "widowed" read off a scheme name ("widow pension") | dropped |

Other safeguards:
* **Budgets:** 6 s per call and 7 s per turn. A timeout, 429, 5xx or invalid output moves on to the next provider;
  after that the turn is rule-based only.
* **Quota and circuit:** a 429 that names a daily limit marks the provider exhausted until its reset. Five consecutive
  failures open a 60 s circuit.
* **Cache:** validated answers are cached by `sha256(provider + model + prompt)`. The prompt is versioned in
  `llm/prompts/extract_v1.md`.
* **Privacy:** free tiers may use what they receive, so with `LLM_ALLOW_REAL_DATA=false` (the default) the LLM runs
  only for:
  * TC-runner sessions;
  * sessions created with `{"demo": true}`;
  * the kiosk's built-in demo phrases.

  Every other turn is rule-based only and nothing leaves the server. Logs carry provider, model, result, status,
  latency and token counts; never utterances, prompts, outputs or keys.

**Eval.** `python -m anvaya.manage eval-extraction` scores 40 demo utterances (`data/fixtures/extraction_eval.json`: en,
hi, te, Hinglish, plus scheme-name and negation cases) per attribute. It lists every wrong fact that would reach the
citizen's confirmation step. Run 2026-10-23 with Groq `openai/gpt-oss-120b` → Gemini `gemini-3.5-flash-lite`, prompt
`extract-v1.1`:

| | high-impact P | high-impact R | overall P | overall R | wrong facts reaching confirmation |
|---|---|---|---|---|---|
| deterministic only | 1.000 | 0.958 | 1.000 | 0.962 | 0 |
| deterministic + LLM | 1.000 | 1.000 | 1.000 | 0.987 | 0 |

## Langfuse tracing (optional)

Set `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` and `LANGFUSE_BASE_URL` (e.g. `https://cloud.langfuse.com`) to trace LLM
extraction with the Langfuse Python SDK v5 (`backend/anvaya/llm/tracing.py`). With any of them unset, the SDK is never
imported and nothing is sent. The startup log and `/api/v1/ready` show `langfuse` as configured or missing.

**One trace per conversation turn that used the LLM.** The trace ID is the request's correlation ID (`X-Request-Id`,
32 hex characters). When one request runs several turns, as the TC runner does, the later turns get IDs derived from
it, and every trace keeps `correlation_id` in its metadata.

```
extract-facts            chain       input: the utterance · output: candidate facts after the merge
├─ translate-utterance   tool        VerbX hi/te → en (only when the utterance needed it)
├─ extract-candidate-facts generation one per provider call or retry: model, input/output tokens, latency,
│                                    attempt / retry, result (ok, cache_hit, timeout, server_error, invalid_output…)
└─ merge-facts           span        outcome per attribute: agree / llm_only / disagree / dropped_*
```

Each trace also carries:
* **Session ID:** the Anvaya session, so a conversation's turns group in the Sessions view.
* **Tags:** `llm-extraction` and `prompt:extract-v1.1`.
* **Metadata:** `prompt_version`, `correlation_id`, `data_class`.
* **Environment:** TC-runner turns use `tc-runner`; everything else uses `LANGFUSE_TRACING_ENVIRONMENT`.

**Privacy.** Input and output are recorded only for demo/test data, which is the same test the LLM privacy gate uses:
TC-runner sessions, sessions created with `"demo": true`, and the kiosk demo phrases. Every other turn is traced as
**metadata only** (structure, model, tokens, timings, outcomes), and two layers enforce that:
* The code never sets input or output on those spans.
* The SDK's export-stage masking hook (`mask_otel_spans`) deletes every attribute outside an allowlist from them.

A span the hook cannot classify makes it raise, and the SDK then drops the whole export batch (fail closed).
`LLM_ALLOW_REAL_DATA=false` (the default) means real citizen turns don't reach the LLM at all, so they are never traced.

**Failure isolation.** Spans are exported by the SDK's background batch processor with a 2 s HTTP timeout, and every
tracing call swallows its own errors. With Langfuse unreachable (connection refused, or a black-holed address), a turn
takes +0.1 to +1.7 ms longer (median of paired turns, `tests/test_tracing.py`) and nothing is raised.

**Datasets and experiments.** `LANGFUSE_TRACE_EVAL=1 python -m anvaya.manage eval-extraction`:
* Upserts the 40 eval utterances into the Langfuse dataset `anvaya-extraction-eval`, with stable IDs
  `anvaya-eval-<id>`.
* Runs one experiment per configuration: `rules-only`, then rule-based + each configured provider on its own.
* Each experiment records per-item `wrong_facts`, `wrong_high_impact_facts` and `recall` scores, plus run-level
  `wrong_facts_reaching_confirmation` and `mean_recall`.

Run of 2026-10-23:

| Experiment | Items | Wrong facts reaching confirmation | Mean recall |
|---|---|---|---|
| rules-only | 40 | 0 | 0.958 |
| rules + groq `openai/gpt-oss-120b` | 40 | 0 | 0.988 |
| rules + gemini `gemini-3.5-flash-lite` | 40 | 0 | 0.970 |

### Charts from the Langfuse project

These two figures are drawn from the project's own data, read through the Langfuse API (`/api/public/v2/observations`,
`/api/public/v3/scores`) on 2026-10-25. The project holds demo and test data only; the counts are small and say so.

![Langfuse experiment scores](docs/screenshots/16-langfuse-eval.png)

*The three experiments on the dataset `anvaya-extraction-eval`: mean recall per configuration (left) and per-utterance
recall (right). The dots below 1.0 are the utterances where a fact was missed. No configuration let a wrong fact reach
the confirmation step.*

![Langfuse traces](docs/screenshots/17-langfuse-traces.png)

*What is in the project: 51 LLM generations, of which 44 (86 %) were answered from the validated-answer cache and 7
were live provider calls taking 1.5–2.8 s, well under the 6 s call cap. Each `extract-facts` trace has one
`extract-candidate-facts` generation and one `merge-facts` span; `translate-utterance` appears only for Hindi/Telugu
script. 36 of the 51 traces came from the TC runner and 15 from the default environment.*

How to read a trace in the Langfuse UI: open *Tracing → Traces*, filter by tag `llm-extraction`, and open one
`extract-facts` trace. The `extract-candidate-facts` generation shows the model, tokens, latency and `result`
(`ok`, `cache_hit`, `timeout`, `server_error`, `invalid_output`); `merge-facts` shows, per attribute, whether the LLM
agreed with the rules, only it found the fact, disagreed (the citizen then chooses) or was dropped. *Datasets →
anvaya-extraction-eval* lists the three experiment runs with their `recall`, `wrong_facts` and
`wrong_high_impact_facts` scores per utterance.


## Scaling

Written for a sleeping free-tier server (Render free) with one app instance, Supabase Postgres, and **no Redis, Kafka,
API gateway or separate worker**. Background work and limits live in the database and in one scheduled HTTP call.

**Capacity estimate.** A 50-kiosk pilot at about 6 citizen sessions per kiosk per day and about 50 API requests per
session (turns, confirmations, documents, status polls) is ≈ 15,000 requests/day, i.e. ≈ 0.2 requests/s on average
(a few requests/s in a busy hour). One gunicorn process with 8 threads handles tens of requests/s, so the web tier is
not the limit; the database round trips per request are (budgets are enforced in `tests/test_db.py`).

**Scheduled jobs (`backend/anvaya/jobs.py`).**
- `retention` (expired unsaved sessions and citizens, passports inactive past `PASSPORT_RETENTION_DAYS`, document
  uploads and their Storage files, expired rate-limit counters) and `cleanup` (ended sessions, cached audio, stale
  sign-in state, job records older than 90 days). Both are idempotent deletes.
- They run from the in-app hourly timer (`ANVAYA_RETENTION_INTERVAL_MIN`), from `POST /internal/jobs/run` with body
  `{"job": "retention" | "cleanup" | "all"}`, and from `python -m anvaya.manage cleanup`. The endpoint needs the
  `X-Internal-Token` header (compared in constant time, separate from user sign-in) and answers 404 while
  `INTERNAL_JOBS_TOKEN` is unset.
- Two runs of a job never overlap: a Postgres advisory lock, or on SQLite a lock row that expires after 15 minutes. A
  run that finds the lock taken is recorded as `skipped`.
- Every run is stored in `job_runs` (job, trigger, start, finish, status, counts; Row Level Security on) and shown to
  admins on the **Security** page (`GET /api/v1/admin/jobs`). Prometheus: `anvaya_job_runs_total{job,status}` and
  `anvaya_job_last_success_timestamp{job}` (rebuilt from `job_runs`, so it survives restarts). `/api/v1/ready` adds a
  warning when retention has not succeeded in 26 hours; readiness itself never depends on it.
- `.github/workflows/scheduled-jobs.yml` calls the endpoint hourly. A sleeping server starts on that request, which is
  what keeps the schedule alive when the in-app timer is asleep. The call does not keep a free-tier server awake for
  the next citizen (Render sleeps again after about 15 idle minutes), so the first request after an idle period still
  pays a cold start.

**Rate limits are in the database** (`rate_limits`: fixed-window counters with an expiry, client IPs only as peppered
hashes): Passport code/PIN attempts (failed attempts only), case-code lookups, session creation, Passport resume and
sign-in event reports. A restart never resets them and several instances share one count; the retention job deletes
expired counters. Cost: one extra database round trip on the rate-limited endpoints. A fixed window allows up to twice
the limit across a window boundary.

**Caching.** Hashed Vite files under `/assets/` are served `Cache-Control: public, max-age=31536000, immutable`;
`index.html`, `sw.js` and the manifest are `no-cache` (revalidated with an ETag); `/api/`, `/internal/` and `/metrics`
responses are `no-store` unless an endpoint sets its own policy. Text responses are compressed with brotli or gzip. The
service worker only caches same-origin app files: it never sees API calls or document links, and skips any response
marked `no-store`.

**When to add more (and why not now).**

| Add | Trigger | Why not now |
|---|---|---|
| Redis | more than one app instance that needs shared in-memory state (today: rate limits, the job lock and the caches are in Postgres or safe to rebuild per process) | the only shared state is already in the database, at about 0.2 req/s |
| A queue (and a worker) | sustained background work: jobs that regularly run longer than the schedule interval, or per-request work (speech, LLM calls) that must be retried and cannot run inside the request | retention takes about a second and runs hourly; per-request calls are synchronous with fallbacks |
| An API gateway | a public partner API: per-key quotas, key issue and revocation, versioned contracts | the only clients are the app's own frontend and staff; limits are per IP in the app |

**New configuration.** Environment variable `INTERNAL_JOBS_TOKEN` (app and `.env`; generate with
`python3 -c "import secrets; print(secrets.token_urlsafe(32))"`). GitHub repository secrets: `APP_URL` (public base
URL of the deployment) and `INTERNAL_JOBS_TOKEN` (the same value).

## Observability (Prometheus + Grafana)

`GET /metrics` exposes these, with low-cardinality labels only (never session IDs or profile values):

| Metric | What it shows |
|---|---|
| `anvaya_http_requests_total`, `anvaya_http_request_duration_seconds` | rate / latency / errors per route & status |
| `anvaya_eligibility_outcomes_total{rule_id,outcome}`, `anvaya_eligibility_evaluations_total{origin}` | screening results (online vs offline_sync) |
| `anvaya_rule_evaluation_seconds` | pure rules-engine time |
| `anvaya_screening_blocked_total`, `anvaya_fact_corrections_total{attribute}`, `anvaya_facts_extracted_total` | confirmation gate & correction loop |
| `anvaya_conversation_turns_total{channel,language}`, `anvaya_voice_requests_total{op,result}` | usage per language; VerbX health (`tts`: cache_hit / ok / timeout / error) |
| `anvaya_drafts_total`, `anvaya_case_transitions_total`, `anvaya_idempotent_replays_total`, `anvaya_cases{status}` | draft/case lifecycle, retry safety |
| `anvaya_sync_events_total{status}`, `anvaya_sync_result_changed_total` | kiosk outbox: accepted / duplicate / conflict |
| `anvaya_auth_events_total`, `anvaya_code_lookups_rate_limited_total` | security signals |
| `anvaya_test_runs_total{tc,result}`, `anvaya_catalogue_records{kind}`, `anvaya_active_sessions{mode}` | TC1–TC5 history, catalogue size, live sessions |
| `anvaya_job_runs_total{job,status}`, `anvaya_job_last_success_timestamp{job}` | background jobs (success / failed / skipped); the timestamp is rebuilt from `job_runs`, so it survives restarts |
| `anvaya_db_queries_per_request`, `anvaya_db_roundtrips_per_request` | database cost of each route |
| `anvaya_llm_calls_total{provider,result}`, `anvaya_llm_latency_seconds{provider}`, `anvaya_llm_fallbacks_total`, `anvaya_llm_merge_total{outcome}` | LLM per provider, fallbacks (`to="deterministic"` = all down), merge outcomes |

The configs live in `monitoring/`. The dashboard JSON is generated by `monitoring/grafana/generate_dashboard.py`.

**Scrape with `honor_labels: true`** (both repo Prometheus configs do). The job metrics carry their own `job` label (`retention`, `cleanup`); without it Prometheus renames that label to `exported_job` because `job` is also the scrape job's name, and the job panels show "No data" or are labelled `anvaya`. Any other Prometheus (for example a managed one) needs the same setting, or queries on `exported_job`.
Gunicorn runs one worker with threads so the in-process counters stay complete.

## Metrics, latency and scores

How the system is measured: the metrics Prometheus holds, the Langfuse scores, the formulas behind every number in the
UI and in this README, and latency, measured and modelled.

### Grafana panels and their queries

The dashboard "Anvaya AI — Operations" (45 panels, generated by `monitoring/grafana/generate_dashboard.py`) is organised in
rows. The queries below are the exact PromQL behind the key panels.

| Row | Panel | Query | Why it matters |
|---|---|---|---|
| Overview | API p95 latency | `histogram_quantile(0.95, sum by (le) (rate(anvaya_http_request_duration_seconds_bucket[5m])))` | the headline SLO |
| Screening | Rule evaluation time (p50 / p95) | `histogram_quantile(0.5\|0.95, sum by (le) (rate(anvaya_rule_evaluation_seconds_bucket[5m])))` | the engine is not the bottleneck (≈ 0.15 ms mean) |
| Screening | Screenings vs confirmation blocks | `rate(anvaya_eligibility_evaluations_total[1m]) * 60` vs `rate(anvaya_screening_blocked_total[1m]) * 60` | how often the confirmation gate stops a screening |
| Screening | Citizen corrections by attribute | `sum by (attribute) (anvaya_fact_corrections_total)` | which facts the voice pipeline gets wrong most |
| Conversation | Turns by language / channel | `sum by (language) (rate(anvaya_conversation_turns_total[1m])) * 60` | adoption per language and text vs voice |
| Conversation | VerbX voice calls | `sum by (op, result) (rate(anvaya_voice_requests_total[1m])) * 60` | TTS cache hits vs live syntheses vs timeouts |
| LLM | Call latency p50 / p95 per provider | `histogram_quantile(0.95, sum by (le, provider) (rate(anvaya_llm_latency_seconds_bucket[5m])))` | free-tier providers are slow and uneven |
| LLM | Provider fallbacks; all providers down | `increase(anvaya_llm_fallbacks_total[5m])`, `anvaya_llm_fallbacks_total{to="deterministic"}` | how often the LLM is skipped entirely |
| Cases & sync | Kiosk sync events by status; offline results changed | `increase(anvaya_sync_events_total[5m])`, `increase(anvaya_sync_result_changed_total[5m])` | offline kiosks: accepted / duplicate / conflict |
| API & security | p95 latency by route, error responses | `histogram_quantile(0.95, sum by (le, route) (rate(anvaya_http_request_duration_seconds_bucket[5m])))` | per-route SLOs; 4xx/5xx split |
| API & security | Auth events, rate-limited lookups | `increase(anvaya_auth_events_total[5m])`, `increase(anvaya_code_lookups_rate_limited_total[5m])` | brute-force and sign-in health |
| **Background jobs & database** | Hours since last successful retention / cleanup | `(time() - anvaya_job_last_success_timestamp{job="retention"}) / 3600` | alert above 26 h (`/ready` warns at the same threshold) |
| **Background jobs & database** | Job runs by status | `sum by (job, status) (increase(anvaya_job_runs_total[1h]))` | `skipped` = another run held the lock |
| **Background jobs & database** | DB round trips / queries per request (p95, per route) | `histogram_quantile(0.95, sum by (le, route) (rate(anvaya_db_roundtrips_per_request_bucket[5m])))` | each round trip costs ≈ 70 ms on the hosted database |
| Official scenarios | TC1–TC5 runs | `sum by (tc, result) (anvaya_test_runs_total)` | evidence that the pipeline still passes |

Prometheus cannot scrape a server that is asleep, and in-process counters restart from zero when it wakes. That is why
the job gauges are rebuilt from the `job_runs` table (not memory) and why Grafana's rate panels are best read while
the server is up; see [Scaling](#scaling) and [Limitations](#limitations).

### Formulas and scores

| Quantity | Definition | Where it appears |
|---|---|---|
| **Extraction precision** | `P = TP / (TP + FP)` over facts proposed (per attribute and overall) | `manage eval-extraction`, README table |
| **Extraction recall** | `R = TP / (TP + FN)` over the facts a careful human reads from the utterance | same |
| **Per-utterance recall** | `found expected facts / expected facts` for one utterance | Langfuse score `recall` |
| **Wrong facts reaching confirmation** | `Σ` facts that survive the merge with a value different from the gold value | Langfuse scores `wrong_facts`, `wrong_high_impact_facts`, `wrong_facts_reaching_confirmation`; the safety metric: target **0** |
| **Screening outcome** | worst of the rule's criteria, in the order `MISMATCH > INSUFFICIENT_INFORMATION > NEEDS_HUMAN_REVIEW > PROVISIONAL > MATCH` | Scheme Passport |
| **Criteria score** | `criteria passed / criteria total` (e.g. "4/4 criteria pass"), shown per scheme | Scheme Passport, reviewer trace |
| **Rule staleness** | stale when `now − source_verified_at > freshness_days` (default 180); a stale or unverified source caps the outcome at `PROVISIONAL` | admin catalogue |
| **Fact staleness** | a saved `age` or `annual_income` confirmed more than 90 days ago returns unconfirmed and blocks screening | saved passports |
| **Income** | `yearly = monthly × 12`, the conversion is shown for confirmation | extraction |
| **Request latency (hosted)** | `T ≈ T_app + RT × 70 ms`, where `RT` = database round trips of the request (Seoul ↔ Singapore) | chart and table below |
| **Rate limit** | fixed window: `start = t − (t mod W)`; allowed while `hits(bucket, key, start) ≤ limit`; counters expire at `start + W` | `ratelimit.py` |
| **Passport-code lockout** | 5 failed attempts per code and per IP per 15 min → `429`; 10 failures → code locked 1 h; only failures count | `accounts.py` |
| **LLM budgets** | call ≤ 6 s; turn (translation + calls) ≤ 7 s; 5 consecutive failures open a provider's circuit for 60 s | `llm/` |
| **Read-aloud wait** | cached clip ≈ 10–25 ms; uncached 0.9–10.5 s, capped at 8 s, after which the text stays and audio arrives later | `voice.py` |
| **LLM cache hit ratio** | `cache_hit / all generations` = 44 / 51 = 86 % in the Langfuse project (demo data repeats) | Langfuse chart |
| **Capacity** | `requests/day = kiosks × sessions per kiosk × requests per session` = 50 × 6 × 50 = 15,000; mean rate = 15,000 / 86,400 ≈ 0.17 req/s; a busy hour carrying 10 % of the day ≈ 0.42 req/s | [Scaling](#scaling) |

### Latency

Measured on 2026-10-25 against the real API (production build, local SQLite, one process): 120 full citizen journeys
(session → turn → confirmations → screening → draft for a third of them → Form Helper) plus 60 `/ready` calls, over
HTTP from the same machine. This isolates **application compute**. The hosted figure applies the formula above with the
database round trips each request needs (asserted in `tests/test_db.py` for session creation, a turn, screening and a draft; estimated for the others, marked *est.*); it is a model, not a measurement of the Render + Supabase deployment.

![API latency by request](docs/screenshots/15-latency-budget.png)

| Request | n | p50 (ms) | p95 (ms) | DB round trips | Modelled p50, hosted DB (ms) |
|---|---|---|---|---|---|
| `POST /sessions` | 120 | 7.8 | 10.9 | 2 | 148 |
| `POST /sessions/{id}/turns` | 120 | 9.4 | 12.7 | 2 | 149 |
| `POST …/profile/confirm-all` | 120 | 8.3 | 12.5 | 2 *(est.)* | 148 |
| `PATCH …/profile/facts/{id}` | 320 | 8.5 | 12.0 | 2 *(est.)* | 148 |
| `POST …/eligibility/evaluate` | 120 | 10.6 | 14.8 | 2 | 151 |
| `POST …/drafts` | 40 | 9.5 | 13.0 | 4 | 289 |
| `GET …/drafts/{id}/helper` | 40 | 6.6 | 11.5 | 2 *(est.)* | 147 |
| `GET /api/v1/ready` | 60 | 4.7 | 8.2 | 1 *(est.)* | 75 |

Other measured and configured figures:

| Stage | Figure | Source |
|---|---|---|
| Rules engine, one screening of 17 rules | ≈ 0.15 ms mean (0.0202 s over 133 screenings) | `anvaya_rule_evaluation_seconds` |
| Uncached LLM extraction call | 1.5–2.8 s (7 live calls, Groq `gpt-oss-120b`), cap 6 s | Langfuse |
| LLM answer from cache | ≈ 0 ms (86 % of generations in the Langfuse project) | Langfuse |
| Read-aloud, cached / uncached | ≈ 10–25 ms / 0.9–10.5 s (cap 8 s) | testing, `voice.py` |
| Langfuse export, when unreachable | +0.1 to +1.7 ms per turn (background, 2 s timeout) | `tests/test_tracing.py` |
| Offline pre-screen | no network; rules run in the browser | `frontend/src/offline/` |

Not measured, and therefore not claimed: VerbX speech-to-text latency, end-to-end latency in a browser on a 3G
connection, and behaviour under concurrent load beyond the pilot estimate.


## CI/CD (GitHub Actions)

| Workflow | Trigger | What runs |
|---|---|---|
| `ci.yml` | push to `main`, pull requests | backend pytest · frontend `tsc -b`, vitest, build · `kubectl kustomize` + `kubeconform` and `docker compose config` · image build, container run with read-only rootfs, TC1–TC5 must pass, `/metrics` check |
| `cd.yml` | push to `main`, tags `v*.*.*`, manual | image to `ghcr.io/<owner>/anvaya-ai`; optional Kubernetes deploy via the `production` environment |
| `dependabot.yml` | weekly | pip, npm, GitHub Actions, Docker base images |

## Data provenance

* **Source:** `structured_govt_schemes_converted.csv` from the supplied ZIP, **3,534 rows across 37 jurisdictions**.
  Its SHA-256, filename and import time are stored as an immutable `source_artifacts` record. Raw values are kept
  alongside the normalized ones.
* **Quality flags found at import:** 341 rows whose *documents* column is prose, 261 with HTML entities, 8 lines
  without a URL and 3 empty document fields. See `/admin/schemes`.
* **Curated rule set: 17 schemes** (`backend/anvaya/data/golden_rules.json`):
  * IGNOAPS in Bihar, Maharashtra, Punjab and Tamil Nadu, plus the central NSAP;
  * AP INDIRAMMA pensions;
  * IGNWPS, PM-KISAN, APY, PMJJBY, PMSBY, PMAY-U and PMUY 2.0;
  * Telangana Rythu Bima;
  * AP spectacles for senior citizens.

  Each criterion quotes the dataset text. "team_reviewed" means compared with the dataset, **not** verified against
  the official portal. A steward records that verification in `/admin/schemes`, and it is audited.
* **Held for review:** the AP spectacles rule is deliberately `NEEDS_HUMAN_REVIEW`, because its dataset *benefits*
  text describes a different scheme.

## Security & privacy (demo scope)

* **Handoff and case codes:** consent is required before handoff. Case codes are ~40-bit random, stored as SHA-256,
  expire after 72 h and are rate-limited, and a code returns status only.
* **Access control:** every bearer token is verified by the backend (JWKS signature, issuer, audience, expiry, and
  not revoked by a global sign-out). Reviewer, admin and test-run routes check the role from `app_metadata` on the
  server and require an `aal2` (TOTP) token; unauthenticated calls get `401`. A signed-in citizen's sessions answer
  only to that citizen's token, a kiosk session only to its device and operator. See [Auth hardening](#auth-hardening).
* **Accounts:** nothing is kept beyond the session without recorded consent; Passport codes are 40-bit random,
  stored as peppered SHA-256, PINs argon2-hashed, with per-code / per-IP limits and lockout (see
  [Accounts and modes](#accounts-and-modes)).
* **Retry safety:** idempotency keys on draft, handoff and sync; optimistic concurrency on draft edits.
* **Kiosk exit** (button or idle timeout) deletes unconsented facts, turns, evaluations, drafts and passport versions.
* **Uploads:** private bucket reached only by the backend; 5-minute single-use upload links and 2-minute view links
  signed by the backend; type checked by magic bytes; every view audited; never OCR'd or sent to an LLM.
* **Logs:** audit logs hold IDs, never profile values. Request logs hold method, route, status and timing only. A
  full TC1–TC5 run leaves no utterances, names, ages or incomes in the logs.
* **Errors:** responses are JSON (`code`, `message`, `request_id`) and never contain stack traces.
* **Audio:** no recorded (STT) audio is stored. `manage cleanup` deletes cached TTS clips of personal sentences once
  they are older than the session lifetime.
* **Secrets:** keys live only in the gitignored `.env` and are never logged, including `DATABASE_URL`.
* **Hosted database:** Row Level Security is on for every table with no policies, so Supabase's public REST API
  cannot read or write app data (see [Database](#database)).
* **Langfuse:** receives input/output only for demo/test data, and metadata only otherwise (enforced by the SDK
  masking hook, which fails closed).

## Integrations and roadmap

What is live, what is built but switched off, and what is next. "Built" means code and tests exist; "planned" means it
does not exist yet.

| Integration | Status | What it adds | What is needed |
|---|---|---|---|
| Supabase Postgres / Auth / Storage | **Live** | Data with RLS, anonymous + email OTP + staff password/TOTP sign-in, private uploads | — |
| VerbX (STT, TTS, translation) | **Live**, optional | Voice in/out in te/hi/en, machine-translated scheme names | key; falls back to browser speech and text |
| Groq → Gemini | **Live**, optional, off by default | Candidate facts for messy phrasing | keys; real citizen data stays rule-based unless `LLM_ALLOW_REAL_DATA=true` |
| Langfuse | **Live**, optional | LLM traces, datasets, experiments | keys |
| Cloudflare Turnstile | **Live** | Bot protection on sign-in | site + secret key |
| Prometheus + Grafana | **Live** | Operations dashboard, job health | Docker, Kubernetes or the local scripts |
| GitHub Actions scheduled jobs | **Live** | Hourly retention/cleanup call that also wakes the server; daily database keep-alive | secrets `APP_URL`, `INTERNAL_JOBS_TOKEN` |
| **DigiLocker / Meri Pehchaan** | **Built, switched off** | Sign-in and verified name / date of birth / gender as `verified` facts (no Aadhaar number is ever read) | partner onboarding: registered entity, official domain, digital signature, committee approval |
| **API Setu (live scheme data)** | **Requested — planned** | Replace the static CSV snapshot with live scheme records, refreshed on a schedule | API access granted by API Setu; contract and sample payloads |
| Phone OTP | Built, switched off | Mobile-number sign-in | TRAI DLT registration and a paid SMS provider |
| SMS / WhatsApp case-status notices | Planned | Tell a citizen when a reviewer acts | DLT-registered templates, consent text |
| CSC / e-District hand-off | Planned | Pass a reviewed draft to the office that files it | MoU, API or file format from the office |

### Live scheme data via API Setu (planned design)

The catalogue today is one imported CSV (3,534 rows, hash-pinned, with quality flags). Once API Setu access is
granted, the same job machinery that already runs retention would also keep the catalogue fresh, **without a new
service**:

```mermaid
flowchart LR
  CRON["GitHub Actions cron<br/>hourly (wakes the server)"] -->|"POST /internal/jobs/run {job: catalogue-sync}"| JOB["catalogue-sync job<br/>advisory lock · idempotent · recorded in job_runs"]
  JOB --> FETCH["Fetch changed records from API Setu<br/>(ETag / updated-since, rate-limit aware)"]
  FETCH --> NORM["Normalise into the existing schema<br/>content hash per record"]
  NORM --> DIFF{"Record changed?"}
  DIFF -- no --> SKIP["Touch last_seen_at only"]
  DIFF -- yes --> STORE["Write new version into source_artifacts<br/>+ quality flags"]
  STORE --> RULECHK{"Does a curated rule<br/>cite this record?"}
  RULECHK -- no --> DONE["Search index updated"]
  RULECHK -- yes --> STALE["Mark the rule's source unverified<br/>→ outcomes drop to PROVISIONAL"]
  STALE --> ADMIN["Admin catalogue page: review diff,<br/>re-verify against the official portal"]
  ADMIN --> BUNDLE["New rule bundle version<br/>→ kiosks refresh their offline cache"]
```

Principles carried over from the current design:
* **A changed source never silently changes an eligibility result.** A curated rule whose cited record changed becomes
  *unverified* (outcomes cap at `PROVISIONAL`) until an admin re-verifies it; that is already how `source_verified_at`
  and `freshness_days` work.
* **Idempotent and lock-protected**, so an hourly call, a manual call and a retry can overlap safely; every run is a
  `job_runs` row with counts, a Prometheus counter and a `/ready` warning when it has not succeeded in 26 hours.
* **The offline bundle is versioned**: kiosks keep the last-known-good bundle and refresh on reconnect.
* Until access is granted, nothing in the app depends on it: the CSV import and `manage init` keep working.

### Engineering that should accompany DigiLocker / Meri Pehchaan and live data

* **Production onboarding checklist:** a registered entity and domain, redirect URIs per environment, client secret in
  the secret store (never `.env` in production), a staging tenant, and a written data-flow note for the DPDP notice.
* **Verified facts:** facts from DigiLocker carry `source="digilocker"` and skip the high-impact read-back, but remain
  visible and correctable; the consent notice must name the fields read. Re-consent when the field set changes.
* **Rule authoring pipeline:** today a rule is hand-edited JSON. Next: a schema-validated editor in the admin page,
  a second reviewer for every rule change, golden test cases per rule, and a signed (not only checksummed) offline bundle.
* **Either/or criteria and household rules** in the rules engine, so fewer schemes fall back to officer checks.
* **Reliability:** database backups and a restore drill, a staging environment, load tests against the pilot estimate,
  alerting on `anvaya_job_last_success_timestamp`, error rate and p95 latency, and an on-call note.
* **Scale triggers** (Redis, queue, gateway) are listed with their thresholds in [Scaling](#scaling).

---

## Failure modes & fallbacks

Every external dependency is optional, and each failure has a defined fallback. Eligibility never depends on any of
them.

### Built into the app

| What fails | What the app does | Where |
|---|---|---|
| **VerbX speech recognition** (error, outage) | Voice input switches to browser speech for the rest of the visit; typing always works. An empty clip just asks to try again. | `frontend/src/speech.ts` |
| **VerbX read-aloud** slower than 8 s, or failing | The text stays on screen with a small 🔇 "audio unavailable" note. The synthesis finishes in the background and is cached, so *Listen* again plays at once. | `voice.speak`, `TTS_WAIT_S` |
| **VerbX translation** | Scheme names stay in English; the LLM gets the original utterance only. | `translation.py` |
| **LLM provider** timeout, 429, 5xx or invalid output | Next provider in `LLM_PROVIDERS`. Invalid JSON gets one retry. A daily-quota 429 marks the provider exhausted until its reset; 5 failures in a row open a 60 s circuit. | `llm/__init__.py` |
| **All LLM providers** down, or the 7 s turn budget used up | The turn is rule-based only, which is the primary path anyway. | `LLM_TURN_BUDGET_S` |
| **LLM and rules disagree** on a high-impact value | Neither value is picked: the citizen chooses between the two. | `llm/merge.py` |
| **Speech mishears a number** (साठ → सात) | High-impact facts are read back in digits and confirmed one by one. Confusable number words are flagged. Screening stays blocked until they are confirmed. | `extraction.py`, `profile.py` |
| **Network lost at the kiosk** | Offline pre-screen on the cached, checksummed rule bundle. Drafts go to a durable outbox; sync deduplicates them, so a resend shows `duplicate`. | `frontend/src/offline/` |
| **Langfuse** unreachable or slow | Export happens in the background with a 2 s timeout. A turn takes about 1 ms longer and nothing is raised. If masking cannot classify a span, the batch is dropped. | `llm/tracing.py` |
| **Missing or invalid config** | Startup logs `missing (missing VAR…)` per integration and falls back to defaults. `/api/v1/ready` stays 200 while the catalogue and rules are loaded. | `startup.py` |
| **Retry of a draft, handoff or sync** | Idempotency keys return the original result; no duplicate case. | `common.py`, `cases.py` |

### During a live demo

| What fails | What to do | What to say |
|---|---|---|
| Microphone or speech recognition | Tap the same sentence under *Demo phrases* | "The same sentence goes through exactly the same pipeline as a voice transcript, including the confirmation step." |
| Read-aloud | Carry on reading the text; press *Listen* again later | "Audio has an 8-second limit by design, so a slow network never blocks the citizen." |
| Venue Wi-Fi (laptop still serving localhost) | Type or tap the demo phrases | "Speech falls back to the browser and typing, and extraction is rule-based. Eligibility never depended on the internet." |
| No network in the browser | Show the kiosk offline pre-screen | "The rules run locally on the cached bundle; drafts queue and sync once it reconnects." |
| LLM slow (e.g. Gemini free tier) | Nothing to do; the turn finishes within ~7 s | "The LLM only proposes candidates; when it's slow the turn is rule-based." |
| Grafana won't load | Open `http://localhost:5000/metrics` or `/api/v1/ready` | — |
| Docker won't start | `bash scripts/run_local.sh` in Ubuntu/WSL | — |
| Everything is slow | Open `/test-runs`: the latest saved TC1–TC5 evidence shows without re-running | — |

Run `docker compose exec anvaya python -m anvaya.manage prerender-audio` once before the demo, so the greeting,
questions and summaries play from the cache.

### Known issues found in final testing (2026-10-23)

| Issue | Impact | Status / workaround |
|---|---|---|
| **Gemini free tier**: the live tests timed out at the 6 s call cap, then Google answered HTTP 503 | None for users: Groq answers first, and the turn falls back to rule-based extraction | Provider-side; keep Groq first in `LLM_PROVIDERS` |
| **VerbX TTS rate limit**: HTTP 429 after ~60 quick calls, though 120/min is documented | Bulk prerendering only | `prerender-audio` paces itself (`--per-minute 40`) and retries; re-running fills gaps |
| **Malformed query input** (`/schemes?limit=abc`, a numeric case code) returns a generic JSON 500 rather than a 4xx | No data exposed and no stack trace; the UI never sends these | Open: validate those two parameters |
| **`localhost` from Windows** to the WSL app can add ~2 s per request (IPv6 tried first) in some HTTP clients | Scripts only; browsers are unaffected | Use `http://127.0.0.1:5000` |
| **Port 3000 already in use** by another local stack | Grafana fails to start | Stop the other stack, or use `GRAFANA_PORT` with the no-Docker monitoring script |

## Limitations

Grouped by area. Items marked **(planned)** are covered in [Integrations and roadmap](#integrations-and-roadmap).

### Eligibility rules
* **17 curated rules.** The other ~3,500 catalogue records are searchable, labelled "not verified", and never
  evaluated automatically. "team_reviewed" rules were checked against the dataset text, not against the official
  portals.
* **The catalogue is a snapshot.** It is one imported CSV, so a scheme that changed after the import is stale until the
  next import. Live data through API Setu, refreshed by a scheduled job and gated by re-verification, is requested and
  **planned**.
* **All-of rules only.** Every criterion in a rule must pass. Either/or conditions ("belongs to one of the listed
  categories") are not expressed as logic yet; they become manual checks for an officer, which keeps the result at
  `PROVISIONAL`.
* **One applicant per screening.** Facts about other household members (a parent's age, a spouse's work) are noticed
  so that they are not mistaken for the applicant's, but they are not used for eligibility. Household-level schemes
  are judged only on the applicant's own facts.
* **No time-bound rules.** Application windows, scheme deadlines and annual re-verification are not modelled.
* **Income is a single yearly figure.** A monthly amount is multiplied by 12, and the conversion is shown for
  confirmation. Seasonal or irregular income is not modelled.
* **Rules are hand-authored.** There is no in-app rule editor, no second-reviewer workflow and no per-rule golden test
  harness beyond TC1–TC5 and the unit tests. **(planned)**

### Language understanding
* **Hindi/Telugu understanding** is a deterministic pattern extractor with a small dialect glossary, tested on the
  phrasings in `tests/test_extraction.py`. It is not general NLU, and the eval set is 40 utterances.
* **Romanized text:** Hinglish number words are understood ("umar saath saal"), but romanized Telugu numbers are not
  ("vayassu aravai edu" gives no age). Telugu script works.
* **Unrelated numbers in an income sentence:** the largest amount in the income clause is taken. An unrelated number
  there, such as a reference number, can be read as income. It is still held for confirmation, and an LLM
  disagreement makes the citizen choose.
* **Only three languages.** Telugu, Hindi and English; other Indian languages and many regional dialects are not covered.
* **Machine translation:** scheme descriptions stay in English. Scheme names are machine-translated for hi/te, are
  sometimes only partly translated ("INDIRAMMA Old Age పెన్షన్"), and are always labelled as machine translation.

### Voice agent
Voice is the interface, so its limits are the product's limits.
* **Push-to-talk, not a live conversation.** The browser records a clip and sends it for transcription; there are no
  streaming partial transcripts, no wake word and no **barge-in** (speaking over the read-aloud does not interrupt it).
* **Speaking a different language than the screen is handled.** VerbX STT forces its output into the language it is
  told: English spoken on a Hindi screen comes back as Devanagari gibberish ("आईम टवटी टू इयर्स"), or as a stage direction
  such as "(speaking in foreign language)". So the backend asks for the screen language first and accepts the answer only
  when it is believable (not a placeholder, not repeated-token noise, written in that language's script) and convincing
  (two or more facts, or a short reply like "yes" or "Bihar"). Anything thinner is compared with what VerbX hears when
  told the audio is English (and then the third language), and the believable transcript with the most extracted facts
  wins. Typical cost is one call; a mismatch costs one or two more (about +1 s each). Measured live on 9 combinations
  (English, Hindi and Telugu speech on each screen language): every one produced a usable transcript. English
  spoken on a Hindi or Telugu screen is recovered from the English pass. The reported language of the transcript is not used to
  change the screen language.
* **STT can mishear numbers:** in testing VerbX heard "साठ" (60) as "सात" (7). The confirmation step handles this:
  high-impact facts (age, income, state, area, household size) are read back in digits, confirmed one by one, and
  never bulk-confirmed. Confusable number words (साठ/सत्तर, sixteen/sixty) are flagged. Speech-recognition
  confidence is not used to decide anything.
  **Sound-alike numbers heard by voice become one-tap choices.** When a spoken number word is one speech recognition
  confuses (साठ 60 / सात 7 / सत्तर 70 / सत्रह 17, sixty / sixteen, అరవై / డెబ్బై) and it is an age or household size, the
  screen asks "Age: 7 years or 60 years? Please choose the right one." with a button for each value (the heard value first)
  instead of a bare "Is 7 right?". Confirming without choosing is refused. Typed numbers and digits are unchanged. VerbX's
  `hints` option (a list of words) is accepted but did not change what it heard in a live test, so it is not used.
* **Noisy rooms and several speakers.** A busy office, a fan or a family talking at once degrade recognition, and the
  app does not separate speakers: whatever is heard is attributed to the applicant until the citizen corrects it.
* **Code-switching and dialect.** Telugu–English or Hindi–English mixes and strong regional pronunciations are the
  weakest cases; the typed fallback exists for them.
* **Manual start and stop.** The citizen (or operator) taps the microphone to start and again to stop; there is no automatic end-of-speech detection, so a clip can include long pauses or be stopped too early. Re-recording or typing always works.
* **VerbX TTS** takes 0.9–10.5 s per uncached sentence. Its rate limit is stricter in practice than the documented
  120/min: HTTP 429 after ~60 quick calls. Hence the cache, the prerendered prompts and the 8 s cap. One configurable voice
  (`verbx-female` by default, `verbx-male` available) is used for every language.
* **Audio leaves the device.** Recorded clips go to the speech provider for transcription (they are not stored by Anvaya);
  this needs to be stated in the consent notice and the provider's terms reviewed before a real deployment.
* **Browser speech fallback:** quality depends on the browser and OS, and many systems have no Telugu voice.
* **Free-tier LLMs get demo data only.** Groq and Gemini free tiers may use what they receive, so real citizen turns
  are rule-based only unless `LLM_ALLOW_REAL_DATA=true`.
* **Gemini's free tier can be slow.** The same demo sentence took 1.7 s once and 43 s another time. In the final run
  every Gemini live call failed: 6 s timeouts, then HTTP 503 from Google. A slow or failing provider is skipped within
  the 7 s turn budget, and the turn falls back to rule-based extraction.
* **Langfuse tracing covers LLM extraction only**, not whole requests, speech or rule evaluation, and its data is small
  (51 generations).

### Kiosk and offline
* **Browser storage** (`localStorage`) stands in for kiosk SQLite. Clearing the browser loses the cached bundle and
  any unsynced outbox events.
* **Integrity, not authenticity:** the bundle is checked with a SHA-256 checksum, not a cryptographic signature. **(planned)**
* **Offline is typed-only and limited to the 17 curated rules**; there is no speech, no catalogue search and no uploads
  offline.
* **One operator per device, no shift hand-over view.** The operator signs out to end every open session; there is no
  fleet console, remote wipe or device attestation.
* **Hardware is not specified or tested:** microphone quality, kiosk lockdown mode, printers for the Passport code and
  the PDF, and screen privacy are the deployer's responsibility.
* **Accessibility** has ARIA labels, large kiosk controls and spoken prompts, but no formal WCAG audit, screen-reader
  testing or sign-language/low-literacy testing with real users.
* **Phone layout** is checked at 390–430 px and 1100–1280 px only.

### Integrations
* **DigiLocker / Meri Pehchaan** is built and tested against a mock OpenID Connect provider but **not enabled**; it needs
  partner onboarding (registered entity, domain, digital signature, approval). **(planned)**
* **API Setu** access has been requested; nothing depends on it yet. **(planned)**
* **No notifications:** nothing is sent to the citizen when a reviewer acts (SMS needs DLT registration). **(planned)**
* **No filing:** drafts are prepared for a citizen to take to an office or portal; there is no submission, status sync
  from a government system, or CSC hand-off.

### Citizen start screen
`/citizen` before a conversation begins is a welcome screen, not a bare card: a hero card with the pulsing mic orb, the headline, a one-line promise, a
large *Start* button (with *Resume with Passport code* beside it) and three reassurance chips (*Free*, *No Aadhaar number asked*, *Audio is not stored*), and
beside it three numbered steps (*Tell us about your family*, *Check what we understood*, *See your schemes*). It stacks to one column on a phone. All text
is English, Hindi and Telugu (`wStep*`, `wChip*` in `frontend/src/i18n.ts`). The Turnstile check, error notes, the retention notice and the voice line are
unchanged, and the Start button stays disabled until the check passes.

### Case status and a fresh start
* **Case status** (`/case`, `POST /cases/status`) answers in the language the site is showing, not the one the case was started in: the request carries
  `language` (`en`/`hi`/`te`; anything else falls back to the case's language). The status, the notice, the labels and the scheme name (machine-translated,
  cached) follow it, and the page asks again when the language is switched. After a lookup the summary is **read aloud automatically**, and the button
  becomes *Stop* while it plays; opening the page from a link or switching language never starts audio by itself (browsers block it, and it would surprise
  the visitor). If audio cannot play, the text stays on screen with an "audio unavailable" note.
* **New conversation by default.** Opening the *Citizen* tab from any page other than a conversation in progress (profile, schemes, documents, draft) ends the
  old session and starts a new one, so earlier details are not loaded again. A saved session returns only on purpose: *Resume with Passport code*, or *My Passports*.
  A reload inside the same tab still keeps the conversation going.

### Conversation guardrails
Every typed or spoken turn passes through `backend/anvaya/guardrails.py` **before** extraction and before any LLM call. The checks are plain
pattern rules (no model), so they cannot be talked around, and the reply comes in the session language (English, Hindi, Telugu).

| Kind | Triggers on | What happens |
|---|---|---|
| `injection` | "ignore previous instructions", "system prompt", "you are now…", "mark me eligible" | Refused; the assistant says it cannot change how it works. Nothing extracted, no LLM call. |
| `sensitive` | 12-digit Aadhaar-style numbers, card numbers, PAN, "OTP", "password" | Refused with a note not to type these; the message is **not stored**. |
| `abuse` | profanity and sexual terms (English, romanised Hindi/Telugu, Devanagari, Telugu script) | Polite refusal. A soft word such as "sex" only counts when nothing else was understood, so "sex: female" still works. |
| `smalltalk` | hello, thanks, "what can you do" | A short answer about what the assistant is for. |
| `offtopic` | a question that is not about the household or schemes | Says it only helps with schemes. |

Every reply, blocked or not, still ends with the next question, so the conversation keeps moving. Blocked turns are stored as
`[withheld: <kind>]`, never as typed, and the audit event records the kind. The `/turns` response carries `guardrail`
(the kind, or `null`) and the chat shows refusals in an amber bubble. Tests: `backend/tests/test_guardrails.py`.
The new guardrail sentences are not in the prerendered audio cache, so they are spoken live (or shown as text only).

The citizen chat is a fixed-height scroll area (long conversations scroll inside it), shows a typing indicator while a reply is on its way, and
smooth-scrolls to the newest message.

### Staff access
Staff have one entry point, **`/staff`** (the *Staff* tab, and the footer link on the landing page).

| State | What `/staff` shows |
|---|---|
| Signed out | The staff sign-in (email + password, then the authenticator code). Operators, reviewers and admins all use it. The header's *Sign in* / profile button opens the **citizen** sign-in, which never accepts staff accounts; that page ends with a *Staff, reviewer or admin? Staff sign-in →* link to `/staff` (shown on shared devices too). |
| Signed in | A hub with only the tools that role may use, and the sign-out buttons. |

| Role | Tools |
|---|---|
| operator | Kiosk (`/kiosk`) |
| reviewer | Reviewer (`/reviewer`), Catalogue (`/admin/schemes`) |
| admin | everything above, Security (`/admin/security`), TC1–TC5 (`/test-runs`) |

* The role tabs show only on staff pages (`/staff`, `/reviewer`, `/admin/*`, `/test-runs`), never beside *Citizen*.
* *Sign out* keeps you on the same page, which turns back into the sign-in form, so signing in again (as the same or a different role) is one step.
* Hiding a tab is convenience only: every staff page asks for a sign-in again if the role does not fit, and the server checks the role and the authenticator (aal2) on every staff request.
* If the *Sign in* button is greyed out, the Cloudflare Turnstile check is still running; a short note says so, and it unlocks when the check finishes.

### Security (demo scope)
* **Staff sign-in** is Supabase email + password + TOTP; there is no SSO and there are no recovery codes (an admin
  resets a lost authenticator). Roles are only as good as whoever holds `SUPABASE_SECRET_KEY`.
* **Rate limits** are fixed-window counters in the database: a client can send up to twice the limit across a window
  boundary, and each limited request costs one extra database round trip.
* **Document links** (5-minute upload, 2-minute view) are short-lived signed capability URLs, the one kind of token
  that appears in a URL path; they are single purpose and the app never logs them.
* **Client addresses** are counted as the app sees them; behind a proxy that hides them, all citizens share one address
  (configure the proxy to pass the real address).
* **Case codes** are locators, not identity.
* **No penetration test or formal threat-model review** has been done; the controls are described in
  [Auth hardening](#auth-hardening) and [Security & privacy](#security--privacy-demo-scope).

### Data retention and jobs
* **A sleeping server only works when woken.** On Render's free tier the app sleeps after about 15 idle minutes; the
  hourly workflow wakes it and runs retention, but the first citizen request after an idle period waits for a cold
  start (tens of seconds). If the workflow's secrets are missing or Actions is disabled, retention stops and
  `/api/v1/ready` warns after 26 hours.
* **Jobs are hourly at best** (GitHub's cron can also run late by minutes), so "deleted within 24 hours" means
  24 hours plus the schedule's jitter.
* **A crashed run leaves a `running` row** in `job_runs`; the lock frees itself (Postgres: with the connection; SQLite:
  after 15 minutes) and the next run proceeds.
* **Some caches never expire:** prerendered audio, including clips for wording that has since changed, and validated
  LLM answers stay until deleted by hand. Both hold demo data only by default.
* **No backups** are configured for the SQLite volume. (A hosted Supabase database gets Supabase's own daily backups on
  paid plans only.) There is no restore drill.

### Operations and scale
* **Single node:** one gunicorn worker with threads (SQLite locally, or Postgres via `DATABASE_URL`). Prometheus
  counters are per process and restart from zero when a sleeping server wakes, and Prometheus cannot scrape it while it
  sleeps. The LLM circuit breaker, the TTS background queue and the in-memory caches are also per process.
* **No staging environment, load test or alerting rules** are included; the pilot capacity is an estimate
  ([Scaling](#scaling)), and latency over a real mobile network was not measured.
* **Live checks are manual:** CI runs the mocked suite only. The live VerbX, LLM and Langfuse checks
  (`pytest -m live`, `eval-extraction`) are run by hand.
* **Free-tier dependencies** (Render, Supabase free plan, Groq/Gemini free tiers, Langfuse cloud) can pause, throttle or
  change terms; a Supabase free project pauses after 7 days without activity (the scheduled workflow prevents that).

### Out of scope
Real identity verification (Aadhaar / eKYC), OCR or any reading of uploaded documents, official application forms filled
on a government site, CSC / e-District filing, and any real government submission are not built. A citizen takes the
prepared draft to the office or portal.

---

## Status and what comes next

**Finished and verified:** the citizen journey in three languages, the confirmation gate, 17 curated rules with traces,
Document Guide with consented private uploads, Form Helper with PDF, consent hand-off and review, the operator-run
**kiosk with offline mode and exactly-once sync**, saved passports (Passport code + PIN or account), staff two-step
sign-in, retention and cleanup as scheduled jobs, database-backed rate limits, observability (Prometheus, Grafana,
Langfuse), and TC1–TC5 passing against the live database.

**Next, in order:** API Setu live scheme data and the catalogue-sync job → DigiLocker / Meri Pehchaan onboarding →
rule-authoring workflow and signed offline bundle → notifications → pilot with 50 kiosks (alerting, backups, load
test). Redis, a queue and an API gateway are added only when the triggers in [Scaling](#scaling) are met.
