# Anvaya AI — *Every voice, a way forward.*

Multilingual (Telugu / Hindi / English), voice-first welfare-scheme discovery, eligibility **pre-screening**,
document guidance and application-draft preparation, with a hybrid edge/cloud kiosk that keeps working offline.

> Voice and the optional LLM are only the conversational interface. **Eligibility is decided by a deterministic,
> versioned rules engine** on facts the citizen has confirmed. Unknown facts stay unknown. Results are potential or
> provisional matches; nothing in this app is an approval, a benefit guarantee or a government submission.

---

## Screenshots

All screenshots come from the running app (`docker compose up`) using the built-in demo phrases; no real citizen data.

### Citizen (personal phone)

| Conversation: facts held for confirmation | Scheme Passport: potential / provisional matches |
|---|---|
| ![Citizen conversation](docs/screenshots/02-citizen-conversation.png) | ![Scheme Passport](docs/screenshots/03-scheme-passport.png) |
| Each fact shows its ID and the words heard; high-impact facts (age, income, area…) are read back and confirmed one by one. | Every result quotes the rule text and its source. Documents still to check appear on each card. |

| Document Guide | Draft (with consent before handoff) |
|---|---|
| ![Document Guide](docs/screenshots/04-document-guide.png) | ![Draft](docs/screenshots/05-draft.png) |
| Marking a document is the citizen's declaration; only a reviewer can mark it verified. | Each field is tagged confirmed / inferred / missing; nothing reaches a reviewer without the consent tick. |

| Landing page | Case status by code |
|---|---|
| ![Landing](docs/screenshots/01-landing.png) | ![Case status](docs/screenshots/10-case-status.png) |

### Kiosk (assisted, Telugu)

| Misheard age held for confirmation | Offline pre-screen (simulated network loss) |
|---|---|
| ![Kiosk in Telugu](docs/screenshots/06-kiosk-telugu.png) | ![Kiosk offline](docs/screenshots/07-kiosk-offline.png) |
| An operator starts the session. A voice transcript that says 26 is held, read back in digits, and blocks screening until confirmed or corrected. | The cached, checksummed rule bundle runs in the browser; drafts queue in the outbox and sync exactly once. |

### Reviewer and admin

| Review queue | Case review: fact history, rule trace, documents, decision |
|---|---|
| ![Review queue](docs/screenshots/08-reviewer-queue.png) | ![Reviewer case](docs/screenshots/09-reviewer-case.png) |

| Catalogue & data freshness (admin) | Official scenarios TC1–TC4 |
|---|---|
| ![Admin catalogue](docs/screenshots/11-admin-catalogue.png) | ![TC1–TC4](docs/screenshots/12-test-runs.png) |
| Source artifact hash, quality flags, knowledge graph, and the 17 curated rules with review / official-source verification status. | Each scenario runs the real pipeline and shows input, expected, actual and per-check evidence. |

### Operations (Grafana)

![Grafana dashboard](docs/screenshots/13-grafana.png)

---

## Architecture

```
EDGE (browser / kiosk PWA)                              CLOUD (Flask API + SQLite, gunicorn)
─────────────────────────────                           ─────────────────────────────────────────────────────
React UI (citizen · kiosk · reviewer · admin · TC)      /api/v1  sessions · turns · facts · eligibility
Voice in : VerbX STT ─▶ browser speech ─▶ typing ──────▶ extraction: deterministic en/hi/te patterns + glossary
Voice out: VerbX TTS (cached per sentence) ─▶ text        [optional] LLM candidates: Groq ─▶ Gemini fallback
           + "audio unavailable" note                               validated · merged · never decides
Offline : cached rule bundle (SHA-256 checksum,          rules_engine (pure, versioned) ◀── golden_rules.json
          last-known-good kept) + TS mirror of the       catalogue (3,534 schemes) + knowledge graph
          rules engine + durable outbox ────────────────▶ /sync/events: dedupe · online re-check · conflicts
                                                         drafts · consent handoff · reviewer · audit · TC runner
                                                         VerbX translate: scheme names hi/te (labelled MT)
                                                         /metrics ─▶ Prometheus ─▶ Grafana
                                                         [optional] LLM turns ─▶ Langfuse traces (background)
```

* **VerbX** (`backend/anvaya/voice.py`; contract discovered from VerbX's own `/openapi.json`, see
  `docs/vendor/verbx.md`). It provides three things:
  * **STT** (`/v1/stt`) for voice input.
  * **TTS** (`/v1/tts`) for read-aloud, cached per sentence (see [Read-aloud](#read-aloud-verbx-tts-cached)).
  * **Translate** (`/v1/translate`, `/v1/translate/batch`) for Hindi/Telugu scheme names, always labelled "machine
    translation", and as the English side-input for the LLM.

  Without VerbX: browser speech, then typing. Text input always works.
* **LLM (optional, off by default):** the providers in `LLM_PROVIDERS=groq,gemini` are tried in order. Groq goes
  first; Gemini is used if Groq times out or returns 429, 5xx or invalid output; if both fail, extraction is
  rule-based only. The LLM only proposes *candidate* facts. They are validated against the utterance, merged with the
  deterministic ones, and always need the citizen's confirmation. **It never sees or decides eligibility** (see
  [LLM extraction](#llm-extraction-optional-free-providers)).
* **Langfuse (optional):** each turn that used the LLM becomes one trace, covering translation, every provider
  call, and the merge. Demo/test data is traced in full; everything else is metadata only (see
  [Langfuse tracing](#langfuse-tracing-optional)).
* **Rules engine:** each curated rule is a list of criteria that must *all* pass on confirmed facts. Outcomes, from
  worst to best:
  1. `MISMATCH`: a confirmed criterion fails.
  2. `INSUFFICIENT_INFORMATION`: a fact is missing or unconfirmed.
  3. `NEEDS_HUMAN_REVIEW`: the rule or its source is ambiguous.
  4. `PROVISIONAL`: the criteria pass, but documents are unverified, officer checks are pending, or the source is
     unverified or stale.
  5. `MATCH` (shown as "Potential match"): everything above is satisfied.

  Every result carries the reasons, a per-criterion trace with the quoted rule text, the input fact IDs, the source
  URL, the rule version and the bundle version.

| Spec module | Implementation |
|---|---|
| voice_adapter | `backend/anvaya/voice.py` (VerbX STT/TTS/translate) + `translation.py` (cached MT) + `frontend/src/speech.ts` |
| conversation / profile_service | `backend/anvaya/profile.py`, `extraction.py`, optional `llm/` (providers, merge, eval) |
| catalogue / knowledge_graph_service | `backend/anvaya/catalogue.py`, `ingest.py` |
| rules_engine | `backend/anvaya/rules_engine.py` ⇄ `frontend/src/offline/rulesEngine.ts` |
| draft_case / review_service | `backend/anvaya/cases.py` |
| sync_service | `backend/anvaya/sync.py`, `frontend/src/offline/store.ts` |
| audit_service | `common.audit()` → `audit_events` |
| test_runner | `backend/anvaya/testrunner.py`, `/test-runs` |

**Workflow states:** `SESSION_ACTIVE → PROFILE_NEEDS_CONFIRMATION → MATCH_RESULTS_READY → DRAFT_SAVED → PENDING_REVIEW ⇄
CORRECTION_REQUESTED → REVIEWED`. Kiosk outbox events are `SYNC_PENDING / SYNCED / FAILED_RETRYABLE / CONFLICT`.
`SUBMITTED_EXTERNAL` is reserved and never produced.

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
cd backend  && python -m pytest -q                     # rules engine, extraction, API, VerbX + LLM (mocked), TC1–TC4
cd backend  && python -m pytest -m live -s             # real VerbX + Groq/Gemini calls (keys from .env), demo sentences
cd backend  && python -m anvaya.manage eval-extraction # extraction precision/recall, deterministic vs + LLM
cd frontend && npm test && npm run build               # offline engine vs shared fixtures, confirmation, speech
```

**Staff accounts:** `reviewer`, `operator` (kiosk) and `admin` (data steward).
* Passwords come from `ANVAYA_REVIEWER_PASSWORD`, `ANVAYA_OPERATOR_PASSWORD` and `ANVAYA_ADMIN_PASSWORD`. They are
  re-applied on every start, so changing one in `.env` also retires the old one.
* An account whose variable is unset falls back to its public demo password (`reviewer123`, `operator123`,
  `admin123`). The app then logs a startup warning, `/api/v1/ready` lists it, and the sign-in pages show credentials
  only for those accounts.

**Startup check.** On boot the app logs one line per integration (VerbX, each LLM provider, metrics) as `configured`
or `missing (missing VAR, …)`. It logs variable names, never values. Missing optional keys never stop the app, and
`/api/v1/ready` stays 200 as long as the catalogue and rules are loaded.

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
| `ANVAYA_ADMIN_PASSWORD`, `ANVAYA_REVIEWER_PASSWORD`, `ANVAYA_OPERATOR_PASSWORD` | demo passwords, with a warning | staff passwords, re-applied on every start |
| `ANVAYA_METRICS_TOKEN` | unset | when set, `/metrics` needs `Authorization: Bearer <token>` |
| `ANVAYA_DEMO_TEST_RUNS` | `off` | `on` lets anyone run/reset TC1–TC4 (otherwise admin only) |
| `ANVAYA_SESSION_TTL_HOURS`, `ANVAYA_CASE_CODE_TTL_HOURS`, `ANVAYA_AUTH_TOKEN_TTL_HOURS` | `12`, `72`, `8` | session, case-code and staff-token lifetimes |
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
`db.status: "error"` until the project is resumed in the dashboard. A keep-alive is planned as the next step.

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
| `anvaya_test_runs_total{tc,result}`, `anvaya_catalogue_records{kind}`, `anvaya_active_sessions{mode}` | TC1–TC4 history, catalogue size, live sessions |
| `anvaya_llm_calls_total{provider,result}`, `anvaya_llm_latency_seconds{provider}`, `anvaya_llm_fallbacks_total`, `anvaya_llm_merge_total{outcome}` | LLM per provider, fallbacks (`to="deterministic"` = all down), merge outcomes |

The configs live in `monitoring/`. The dashboard JSON is generated by `monitoring/grafana/generate_dashboard.py`.
Gunicorn runs one worker with threads so the in-process counters stay complete.

## CI/CD (GitHub Actions)

| Workflow | Trigger | What runs |
|---|---|---|
| `ci.yml` | push to `main`, pull requests | backend pytest · frontend `tsc -b`, vitest, build · `kubectl kustomize` + `kubeconform` and `docker compose config` · image build, container run with read-only rootfs, TC1–TC4 must pass, `/metrics` check |
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
* **Access control:** reviewer, admin and test-run routes check the role on the server, and unauthenticated calls get
  `401`.
* **Retry safety:** idempotency keys on draft, handoff and sync; optimistic concurrency on draft edits.
* **Kiosk exit** deletes unconsented facts, turns, evaluations and drafts.
* **Logs:** audit logs hold IDs, never profile values. Request logs hold method, route, status and timing only. A
  full TC1–TC4 run leaves no utterances, names, ages or incomes in the logs.
* **Errors:** responses are JSON (`code`, `message`, `request_id`) and never contain stack traces.
* **Audio:** no recorded (STT) audio is stored. `manage cleanup` deletes cached TTS clips of personal sentences once
  they are older than the session lifetime.
* **Secrets:** keys live only in the gitignored `.env` and are never logged, including `DATABASE_URL`.
* **Hosted database:** Row Level Security is on for every table with no policies, so Supabase's public REST API
  cannot read or write app data (see [Database](#database)).
* **Langfuse:** receives input/output only for demo/test data, and metadata only otherwise (enforced by the SDK
  masking hook, which fails closed).

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
| Everything is slow | Open `/test-runs`: the latest saved TC1–TC4 evidence shows without re-running | — |

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

### Eligibility rules
* **17 curated rules.** The other ~3,500 catalogue records are searchable, labelled "not verified", and never
  evaluated automatically. "team_reviewed" rules were checked against the dataset text, not against the official
  portals.
* **All-of rules only.** Every criterion in a rule must pass. Either/or conditions ("belongs to one of the listed
  categories") are not expressed as logic yet; they become manual checks for an officer, which keeps the result at
  `PROVISIONAL`.
* **One applicant per screening.** Facts about other household members (a parent's age, a spouse's work) are noticed
  so that they are not mistaken for the applicant's, but they are not used for eligibility. Household-level schemes
  are judged only on the applicant's own facts.
* **No time-bound rules.** Application windows, scheme deadlines and annual re-verification are not modelled.
* **Income is a single yearly figure.** A monthly amount is multiplied by 12, and the conversion is shown for
  confirmation. Seasonal or irregular income is not modelled.

### Language understanding
* **Hindi/Telugu understanding** is a deterministic pattern extractor with a small dialect glossary, tested on the
  phrasings in `tests/test_extraction.py`. It is not general NLU.
* **Romanized text:** Hinglish number words are understood ("umar saath saal"), but romanized Telugu numbers are not
  ("vayassu aravai edu" gives no age). Telugu script works.
* **Unrelated numbers in an income sentence:** the largest amount in the income clause is taken. An unrelated number
  there, such as a reference number, can be read as income. It is still held for confirmation, and an LLM
  disagreement makes the citizen choose.
* **Machine translation:** scheme descriptions stay in English. Scheme names are machine-translated for hi/te, are
  sometimes only partly translated ("INDIRAMMA Old Age పెన్షన్"), and are always labelled as machine translation.

### Voice and AI services
* **VerbX STT can mishear numbers:** in testing it heard "साठ" (60) as "सात" (7). The confirmation step handles this.
  High-impact facts (age, income, state, area, household size) are read back in digits, confirmed one by one, and
  never bulk-confirmed. Confusable number words (साठ/सत्तर, sixteen/sixty) are flagged.
* **VerbX TTS** takes 0.9–10.5 s per uncached sentence. Its rate limit is stricter in practice than the documented
  120/min: HTTP 429 after ~60 quick calls. Hence the cache, the prerendered prompts and the 8 s cap.
* **Browser speech fallback:** quality depends on the browser and OS, and many systems have no Telugu voice.
* **Free-tier LLMs get demo data only.** Groq and Gemini free tiers may use what they receive, so real citizen turns
  are rule-based only unless `LLM_ALLOW_REAL_DATA=true`.
* **Gemini's free tier can be slow.** The same demo sentence took 1.7 s once and 43 s another time. In the final run
  every Gemini live call failed: 6 s timeouts, then HTTP 503 from Google. A slow or failing provider is skipped within
  the 7 s turn budget, and the turn falls back to rule-based extraction.
* **Langfuse tracing covers LLM extraction only**, not whole requests, speech or rule evaluation.

### Offline kiosk
* **Browser storage** (`localStorage`) stands in for kiosk SQLite. Clearing the browser loses the cached bundle and
  any unsynced outbox events.
* **Integrity, not authenticity:** the bundle is checked with a SHA-256 checksum, not a cryptographic signature.
* Only the 17 curated rules work offline, and only typed input (no speech).

### Security (demo scope)
* **Staff sign-in** is username + password with a bearer token kept in the browser's `sessionStorage`. There is no
  login throttling or lockout, no MFA, and no SSO.
* **Rate limits live in process memory:** the case-code limiter resets on restart and is not shared between
  processes.
* **Demo credentials and case codes** are not production security.

### Data retention
* **Clean-up is manual.** `python -m anvaya.manage cleanup` ends expired sessions and deletes live TTS clips; nothing
  schedules it.
* **Some caches never expire:** prerendered audio, including clips for wording that has since changed, and validated
  LLM answers stay until deleted by hand. Both hold demo data only by default.
* **No backups** are configured for the SQLite volume. (A hosted Supabase database gets Supabase's own daily backups on paid plans only.)

### Operations and scale
* **Single node:** one gunicorn worker with threads (SQLite locally, or Postgres via `DATABASE_URL`). Prometheus counters are per process, so more workers
  need `prometheus_client` multiprocess mode. The LLM circuit breaker and the TTS background queue are also per
  process.
* **Live checks are manual:** CI runs the mocked suite only. The live VerbX, LLM and Langfuse checks
  (`pytest -m live`, `eval-extraction`) are run by hand.
* **Accessibility** has ARIA labels and large kiosk controls, but no formal WCAG audit or screen-reader testing.

### Out of scope
PostgreSQL, real identity (Aadhaar/eKYC), OCR of documents, PDF or official application forms, DigiLocker/CSC
integration, and any real government submission are not built.
