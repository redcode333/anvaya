# Anvaya AI — *Every voice, a way forward.*

Multilingual (Telugu / Hindi / English), voice-first welfare-scheme discovery, eligibility **pre-screening**,
document guidance and application-draft preparation — with a hybrid edge/cloud kiosk that keeps working offline.

> The LLM/voice layer is only a conversational interface. **Eligibility is decided by a deterministic,
> versioned rules engine** on facts the citizen has confirmed. Unknown facts stay unknown. Nothing in this app
> is an approval, a benefit guarantee, or a government submission.

---

## Quick start

**Docker (one command)**

```bash
cp .env.example .env                   # optional: fill VERBX_*, LLM keys, ANVAYA_*_PASSWORD, GRAFANA_*
docker compose up --build
# App        → http://localhost:5000
# Prometheus → http://localhost:9090   (scrapes http://anvaya:5000/metrics every 5 s)
# Grafana    → http://localhost:3000   (dashboard "Anvaya AI — Operations" opens as home; anonymous read-only unless
#                                       GRAFANA_ANONYMOUS=false; admin password = GRAFANA_ADMIN_PASSWORD, default anvaya-grafana)
docker compose exec anvaya python -m anvaya.manage prerender-audio   # once, if VerbX is configured (see Read-aloud)
```

All three services have healthchecks (`docker compose ps` shows `healthy`); state lives only in the named volumes
`anvaya-db`, `prometheus-data` and `grafana-data` (the only bind mounts are the read-only configs in `monitoring/`).

### Run without Docker

For when Docker Desktop will not start. In Ubuntu / WSL, from the repo (for example
`cd /mnt/c/Users/<you>/OneDrive/Desktop/anvaya/Anvaya-AI`):

```bash
bash scripts/run_local.sh              # app + built frontend on http://localhost:5000 (Ctrl-C stops)
bash scripts/run_local.sh --prerender-audio   # same, and fill the read-aloud audio cache in the background
bash scripts/run_monitoring_local.sh   # second terminal: Prometheus :9090 + Grafana :3000
```

`run_local.sh` reads the repo-root `.env`, creates a virtualenv, installs `backend/requirements.txt`, runs
`manage init` when the database has no rules yet, builds the frontend once (again only when its sources change, or
with `--rebuild-frontend`) and starts gunicorn on `:5000` serving the API and the built frontend (`PORT` overrides).
Everything it generates lives in `~/.local/anvaya` on the Linux filesystem (venv, `anvaya.db`, a build copy of
`frontend/`), so the repo, its Windows `node_modules` and `backend/.venv` are left untouched. If `python3-venv` is not
installed it bootstraps pip with the official `get-pip.py`; if WSL has no Node ≥ 18 of its own it downloads a pinned,
checksum-verified Node 20 into `~/.local/anvaya/node`. Neither needs sudo.

`run_monitoring_local.sh` downloads the same Prometheus 2.54.1 and Grafana 11.2.2 the compose file uses (pinned,
sha256-verified Linux binaries) into `~/.local/anvaya-monitoring`, never into the repo, and runs them with the repo's
`monitoring/` configs. Only the Docker hostnames (`anvaya:5000`, `prometheus:9090`) and the dashboards path are
rewritten, in a derived copy under `~/.local/anvaya-monitoring/conf`. Grafana uses `GRAFANA_ADMIN_PASSWORD` and
`GRAFANA_ANONYMOUS` from `.env`. `PROMETHEUS_PORT` / `GRAFANA_PORT` move them off 9090 / 3000 when another stack holds
those ports. From Windows, scripts calling the WSL app should use `http://127.0.0.1:5000`: `localhost` there tries IPv6
first, which some HTTP clients only give up on after about 2 s (browsers are unaffected).

**Kubernetes** — `cp k8s/secrets.env.example k8s/secrets.env && kubectl apply -k .` (app + Prometheus + Grafana,
restricted pod security, NetworkPolicies, PVCs). See [`k8s/README.md`](k8s/README.md).

**Local dev**

```bash
# backend (Python 3.11+)
cd backend
pip install -r requirements.txt
python -m anvaya.manage init          # imports data/raw/*.csv, loads curated rules, seeds demo users
set -a; . ../.env; set +a              # optional: VERBX_*, LLM_* / GROQ_* / GEMINI_* (docker compose loads .env itself)
python -c "from anvaya import create_app; create_app().run(port=5000)"

# frontend (Node 20+) — in a second terminal
cd frontend
npm install
npm run dev                            # → http://localhost:5173 (proxies /api to :5000)
# or: npm run build  → Flask serves frontend/dist at http://localhost:5000
```

**Tests**

```bash
cd backend  && python -m pytest -q     # rules engine, extraction, API contracts, VerbX + LLM (mocked HTTP), TC1–TC4
cd backend  && python -m pytest -m live -s   # real VerbX + Groq/Gemini calls (keys from .env); demo sentences only
cd backend  && python -m anvaya.manage eval-extraction   # extraction precision/recall, deterministic vs + LLM
cd backend  && python -m anvaya.manage prerender-audio   # synthesize the fixed spoken prompts (needs VERBX_*)
cd frontend && npm test                # offline TS engine vs the same shared fixtures, confirmation, speech fallback
```

**Staff accounts:** `reviewer`, `operator` (kiosk) and `admin` (data steward). Their passwords come from
`ANVAYA_REVIEWER_PASSWORD`, `ANVAYA_OPERATOR_PASSWORD` and `ANVAYA_ADMIN_PASSWORD` and are re-applied on every start, so
changing one in `.env` also retires the old one. Only when a variable is unset does that account get its public demo
password (`reviewer123`, `operator123`, `admin123`). The app then logs a warning at startup, `/api/v1/ready` lists it
under `warnings`, and the sign-in pages show demo credentials only for accounts that still use them.

**Startup check.** On boot the app logs one line per integration (VerbX, each provider in `LLM_PROVIDERS`, metrics)
as `configured` or `missing (missing VAR, …)` together with what that means. Only variable names are logged, never
values. Unset passwords and unparsable numbers are logged as warnings; unparsable numbers fall back to their defaults.
Missing optional keys never stop the app. `GET /api/v1/ready` returns the same report under `integrations` and
`warnings`, and stays 200 as long as the catalogue and rules are loaded.

---

## Judge demo script (≈4 min)

1. **Kiosk + Telugu** — `/kiosk`, sign in as operator, pick తెలుగు, *Start*. Status bar shows online state and cached bundle version.
2. **Voice + misheard age** — open *Demo phrases* → “వయస్సు తప్పుగా విన్నది” (sent as a voice transcript). Age **26** appears
   highlighted with its fact ID and the original words; *Check schemes* is disabled until confirmed.
3. **Correct it** — *Correct* → 67 → save, confirm the rest, *Check schemes*. A new fact ID supersedes the old one
   (the reviewer sees both). Any later correction after a screening makes the Passport list “what changed”
   (outcome before → after); TC3 shows the explicit misheard-26 vs corrected-62 diff.
4. **Scheme Passport** — expand *Why*: each criterion shows the quoted dataset rule text, expected vs. observed value,
   fact ID, PASS/FAIL/UNKNOWN, source URL, import / review / verification dates. 🔊 plays a localized summary.
5. **Document Guide** — mark BPL card *missing*; the gap appears on the cards. Ticking a box is a declaration, never “verified”.
6. **Draft + consent** — *Prepare draft*: every field is tagged confirmed / inferred / missing / citizen-entered.
   Tick consent → *Send to reviewer* → case code `ANV-XXXX-XXXX`. Retrying returns the same case.
7. **Offline** — tick *simulate network loss*: typed pre-screen runs on the cached bundle in < 1 ms, save a draft to the outbox
   (`SYNC_PENDING`). Untick → *Sync now* → *Retry test (resend)* shows `duplicate` — the reviewer queue gets exactly one case.
8. **Reviewer** — `/reviewer`: open by code, inspect fact history + rule trace + documents, request correction or record review.
   The citizen’s `/case/<code>` shows the new status in their language.
9. **TC1–TC4** — `/test-runs` → *Run all*: input, expected, actual, per-check pass/fail and evidence JSON.

---

## Architecture

```
EDGE (browser / kiosk PWA)                              CLOUD (Flask API, SQLite → PostgreSQL in prod)
─────────────────────────────                           ───────────────────────────────────────────────
React UI (citizen · kiosk · reviewer · admin · TC)      /api/v1  sessions · turns · facts · eligibility
Voice: VerbX STT/TTS → browser Web Speech → text ───▶  extraction (deterministic, en/hi/te + glossary)
Offline: cached signed bundle (sha256-validated,        [optional] LLM cross-check: groq → gemini (validated, merged)
  atomic swap, last-known-good kept)                    rules_engine (pure, versioned)  ◀── golden_rules.json
  + TS mirror of the rules engine                       catalogue + knowledge graph (kg_nodes / kg_edges)
  + durable outbox (event_id + idempotency key)  ─────▶ /sync/events: dedupe · online re-check · conflicts
                                                        drafts (versioned) · handoff (consent, hashed codes)
                                                        reviewer (role-checked) · audit log · TC runner
```

| Spec module | Implementation |
|---|---|
| voice_adapter | `backend/anvaya/voice.py` (VerbX STT/TTS/translate, contract in `docs/vendor/verbx.md`) + `translation.py` (cached MT) + `frontend/src/speech.ts` fallbacks |
| conversation / profile_service | `backend/anvaya/profile.py`, `extraction.py`, optional `llm/` (providers, merge, eval) |
| catalogue / knowledge_graph_service | `backend/anvaya/catalogue.py`, `ingest.py` |
| rules_engine | `backend/anvaya/rules_engine.py` ⇄ `frontend/src/offline/rulesEngine.ts` |
| draft_case / review_service | `backend/anvaya/cases.py` |
| sync_service | `backend/anvaya/sync.py`, `frontend/src/offline/store.ts` |
| audit_service | `common.audit()` → `audit_events` |
| test_runner | `backend/anvaya/testrunner.py`, `/test-runs` |

### Rule outcomes
`MISMATCH` (a confirmed criterion fails) → `INSUFFICIENT_INFORMATION` (a needed fact is missing/unconfirmed) →
`NEEDS_HUMAN_REVIEW` (rule/source ambiguous) → `PROVISIONAL` (criteria pass but documents unverified, officer checks
pending, or source not verified/stale) → `MATCH` (all of the above satisfied). Every result carries
`decision_reason[]`, criterion-level trace, `input_fact_ids`, `source_id`/`source_url`, `rule_version` and bundle version.

### Workflow states
`SESSION_ACTIVE → PROFILE_NEEDS_CONFIRMATION → MATCH_RESULTS_READY → DRAFT_SAVED → PENDING_REVIEW ⇄ CORRECTION_REQUESTED → REVIEWED`;
kiosk outbox events are `SYNC_PENDING / SYNCED / FAILED_RETRYABLE / CONFLICT`. `SUBMITTED_EXTERNAL` is reserved and never produced.

---

## CI/CD (GitHub Actions)

| Workflow | Trigger | What runs |
|---|---|---|
| `.github/workflows/ci.yml` | push to `main`, pull requests | **backend** pytest (Py 3.12) · **frontend** `tsc -b`, vitest, build (Node 20) · **manifests** `kubectl kustomize` + `kubeconform -strict` (k8s 1.30) and `docker compose config` · **docker** image build (buildx + GHA cache), container run with read-only rootfs, TC1–TC4 must pass, `/metrics` check |
| `.github/workflows/cd.yml` | push to `main`, tags `v*.*.*`, manual | push image to **`ghcr.io/<owner>/anvaya-ai`** (tags: semver, `sha-<short>`, `latest` on main) · optional **deploy** to Kubernetes via the `production` environment |
| `.github/dependabot.yml` | weekly | pip, npm, GitHub Actions, Docker base images |

The dataset CSV (24.5 MB, under GitHub's 100 MB limit) should be committed; `.github/actions/dataset` uses it, or extracts it
from `archive (1).zip` if only the ZIP is committed.

**CD deploy secrets** (set on the GitHub Environment `production`; the deploy job skips cleanly without `KUBE_CONFIG`):
`KUBE_CONFIG` (kubeconfig contents), `ANVAYA_METRICS_TOKEN`, `GRAFANA_ADMIN_PASSWORD`; optional `VERBX_BASE_URL`,
`VERBX_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`. The cluster must be able to pull from GHCR (make the package public or add an
`imagePullSecret`).

## Observability (Prometheus + Grafana)

`GET /metrics` (Prometheus text format) exposes, with low-cardinality labels only — never session IDs or profile values:

| Metric | What it shows |
|---|---|
| `anvaya_http_requests_total`, `anvaya_http_request_duration_seconds` | rate / latency / errors per route & status |
| `anvaya_eligibility_outcomes_total{rule_id,outcome}`, `anvaya_eligibility_evaluations_total{origin}` | screening results (online vs offline_sync) |
| `anvaya_rule_evaluation_seconds` | pure rules-engine time (NFR: sub-second local rules) |
| `anvaya_screening_blocked_total`, `anvaya_fact_corrections_total{attribute}`, `anvaya_facts_extracted_total` | confirmation gate & voice-correction loop |
| `anvaya_conversation_turns_total{channel,language}`, `anvaya_voice_requests_total{op,result}` | multilingual usage, VerbX health |
| `anvaya_drafts_total`, `anvaya_case_transitions_total`, `anvaya_idempotent_replays_total`, `anvaya_cases{status}` | draft/case lifecycle, retry safety |
| `anvaya_sync_events_total{status}`, `anvaya_sync_result_changed_total` | kiosk outbox: accepted / duplicate / conflict |
| `anvaya_auth_events_total`, `anvaya_code_lookups_rate_limited_total` | security signals |
| `anvaya_test_runs_total{tc,result}`, `anvaya_catalogue_records{kind}`, `anvaya_active_sessions{mode}` | TC1–TC4 history, catalogue size, live sessions |
| `anvaya_llm_calls_total{provider,result}`, `anvaya_llm_latency_seconds{provider}` | LLM extraction per provider: ok / cache_hit / timeout / rate_limited / quota_exhausted / server_error / invalid_output / skipped_* |
| `anvaya_llm_fallbacks_total{from,to}`, `anvaya_llm_merge_total{outcome}` | provider fallbacks (`to="deterministic"` = all down); merge: agree / llm_only / disagree / dropped_evidence / dropped_invalid / dropped_relative / dropped_scheme_name |

For `anvaya_voice_requests_total{op="tts"}` the results are `cache_hit` / `ok` / `timeout` / `error` / `not_configured`.

Config lives in `monitoring/` (`prometheus/prometheus.yml`, Grafana datasource + dashboard provisioning). The dashboard JSON is
generated by `monitoring/grafana/generate_dashboard.py <out.json>`. Gunicorn runs one worker with threads so the in-process
counters stay complete; scaling to several workers needs `prometheus_client` multiprocess mode.

## Read-aloud (VerbX TTS, cached)

VerbX TTS took 0.9–10.5 s per sentence in testing, so read-aloud never holds up the conversation:

* **Text first.** Replies, the greeting and the Scheme Passport summary appear at once; audio plays when it arrives.
  Turns return `reply_segments` and evaluations return `voice_summary_segments`. The frontend requests every sentence
  at once and plays them in order.
* **Cache.** Each synthesized sentence is stored in the `tts_cache` table, keyed by `sha256(text, language, voice)`.
  The text itself is not stored. Identical requests that arrive together share one VerbX call.
* **Prerendered prompts.** `python -m anvaya.manage prerender-audio` synthesizes and pins, for en/hi/te: the greeting,
  every follow-up question, the confirmation prompts and the summary templates. The templates are the intro, the
  counts up to `--max-count` (default 4), one line per curated scheme for "likely eligible" and "provisional", and a
  single missing document. Re-running it only fills gaps. Sentences that repeat the citizen's own details ("I
  understood: age 67 …") are synthesized live, and `manage cleanup` removes them after `ANVAYA_SESSION_TTL_HOURS`.
* **8 s cap.** If a sentence is not ready within 8 s (`ANVAYA_TTS_WAIT_S` on the server, the same limit in the
  browser) or VerbX fails, playback stops and the UI shows the text with a small "audio unavailable" note. A slow
  synthesis keeps running on the server and lands in the cache, so pressing *Listen* again plays at once.
* Without VerbX configured, read-aloud uses the browser's own speech voice.

## Data provenance

* Source: `structured_govt_schemes_converted.csv` from the supplied ZIP — **3,534 rows, 37 jurisdictions**
  (3,533 distinct names after whitespace/HTML normalization). SHA-256, filename and import time are stored as an immutable
  `source_artifacts` record. Raw values are kept alongside normalized ones.
* Quality flags found at import: 341 rows whose *documents* column is prose rather than a list, 261 with HTML entities,
  8 source lines without a URL, 3 empty document fields. See `/admin/schemes`.
* **Curated rule set: 17 schemes** (`backend/anvaya/data/golden_rules.json`) — IGNOAPS in Bihar / Maharashtra / Punjab /
  Tamil Nadu + central NSAP, AP INDIRAMMA pensions, IGNWPS, PM-KISAN, APY, PMJJBY, PMSBY, PMAY-U, Telangana Rythu Bima,
  PMUY 2.0, AP spectacles. Each criterion quotes the dataset text; import fails a rule to `needs_review` if a quote is not found.
  “team_reviewed” means compared with the dataset text, **not** verified against the official portal — `source_verified_at`
  stays empty until a steward verifies it in `/admin/schemes` (audited). Every other catalogue record is searchable with a
  “not verified” label but is never auto-evaluated.
* The AP spectacles rule is deliberately held as `NEEDS_HUMAN_REVIEW`: its dataset *benefits* text describes a different scheme.

## LLM extraction (optional, free providers)

The deterministic extractor is the primary path and always runs. With `ANVAYA_LLM_EXTRACTION=on` an LLM reads the same
utterance (plus the VerbX English translation for Hindi/Telugu script) and its facts are **merged**, never trusted:

| LLM result vs deterministic | What happens |
|---|---|
| same attribute, same value | deterministic fact kept, note “confirmed by both” |
| attribute only the LLM found | added as an **unconfirmed** candidate (`source=llm`, `inferred=true`); never replaces a fact the profile already holds |
| different value on age / income / state / area / household size | **neither is picked**: the fact is held with both values and the citizen chooses (“उम्र: 60 वर्ष या 70 वर्ष?”); plain confirm returns `409 VALUE_DISPUTED` |
| different value on a low-impact attribute | deterministic value kept but never auto-confirmed |
| evidence not a substring of the utterance or its translation, invalid value, a relative’s age | dropped |

The relative-age rule, confusable-number confirmation and “confirm-all never confirms high-impact facts” apply to LLM facts too.
The LLM never sees or decides eligibility.

**Providers** (`backend/anvaya/llm/`): one OpenAI-compatible chat-completions client over `requests` — `LLM_PROVIDERS=groq,gemini`
(order = fallback order; `ollama` and `anthropic` optional, the `anthropic` package is imported only if that provider is
used). Per call 6 s, per turn 7 s (`LLM_TURN_BUDGET_S`, includes translation); after that the turn is deterministic-only.
Timeout / 429 / 5xx / invalid output → next provider; invalid JSON gets one retry with the validation error. A 429 naming a
daily limit or quota marks the provider exhausted until its reset (persisted in `llm_provider_state`); 5 consecutive failures
open a 60 s circuit. Validated answers are cached in `llm_cache` by `sha256(provider + model + prompt)`. The prompt is
versioned in `llm/prompts/extract_v1.md`. `GET /api/v1/ready` shows each provider as
`not_configured / configured / ok / error / exhausted / open-circuit` — never keys.

**Privacy.** Free tiers may use what they receive, so they get **demo/test data only**: with `LLM_ALLOW_REAL_DATA=false`
(the default) the LLM runs only for TC-runner sessions, sessions created with `POST /sessions {"demo": true}`, and the kiosk’s
built-in demo phrases (`backend/anvaya/data/demo_phrases.json`, shared with the UI). Every other turn is deterministic-only
and nothing leaves the server. Set it to `true` only for a provider whose terms allow real citizen data. Logs carry provider,
model, result, HTTP status, latency and token counts — never utterances, prompts, model output or keys.

**Eval.** `python -m anvaya.manage eval-extraction [--no-llm] [--json]` scores 34 demo utterances (`data/fixtures/extraction_eval.json`;
en, hi, te, Hinglish) per attribute, deterministic-only vs deterministic + LLM, and lists every wrong fact that would reach the
citizen's confirmation step. Target: merged high-impact precision ≥ 0.95. Run 2026-10-23 with Groq `openai/gpt-oss-120b` →
Gemini `gemini-3.5-flash-lite`, prompt `extract-v1.1`:

| | high-impact P | high-impact R | overall P | overall R | wrong facts reaching confirmation (high-impact) |
|---|---|---|---|---|---|
| deterministic only | 1.000 | 0.966 | 1.000 | 0.966 | 0 (0) |
| deterministic + LLM | 1.000 | 1.000 | 1.000 | 0.987 | 0 (0) |

The first run, before the prompt said not to infer area, household size or gender from place names and verb endings,
scored 0.957 merged high-impact precision. Those mistakes were LLM-only candidates such as `area=urban` for “Pune”. They
would still have gone to the citizen unconfirmed.

## Security & privacy (demo scope)

Consent required before handoff · case codes are ~40-bit random, stored as SHA-256, expire (72 h) and lookups are
rate-limited; a code returns status only · reviewer/admin role checked server-side, forbidden attempts audited ·
idempotency keys on draft / handoff / sync, optimistic concurrency (version) on draft edits · kiosk exit deletes
unconsented facts, turns, evaluations and drafts · audit details hold IDs, never raw profile values · request logs hold
method/route/status/timing only · no raw audio stored · uploaded/retrieved text is treated as data · LLM providers get
demo/test data only unless `LLM_ALLOW_REAL_DATA=true`, and LLM logs never contain utterances, prompts, outputs or keys.

## Honest limitations

* **VerbX: translation + speech.** With `VERBX_API_KEY` set, voice input uses VerbX STT (`/v1/stt`), read-aloud uses
  VerbX TTS (`/v1/tts`, WAV) and Hindi/Telugu screens show VerbX machine translations of scheme names (`/v1/translate`,
  cached in the `translations` table, always labelled "machine translation"; never used for eligibility). Every
  endpoint and payload was discovered from VerbX's own `/openapi.json` and live calls — see `docs/vendor/verbx.md`.
  If VerbX is unset, speech uses browser Web Speech (quality varies by browser/OS, Telugu voices may be missing). If
  VerbX STT fails during a visit, voice input switches to browser speech. A slow or failed VerbX read-aloud shows the
  text with an "audio unavailable" note (see [Read-aloud](#read-aloud-verbx-tts-cached)). Scheme names stay in English
  and typed input always works. In testing VerbX STT heard
  "साठ" (60) as "सात" (7) — the confusable-number check holds such ages for explicit confirmation.
* **Hindi/Telugu understanding** is a deterministic pattern extractor + small dialect glossary, tested on the phrasings in
  `tests/test_extraction.py` — not a general NLU. The optional LLM cross-check (`ANVAYA_LLM_EXTRACTION=on`, see
  [LLM extraction](#llm-extraction-optional-free-providers)) only adds unconfirmed candidates or holds disagreements for the
  citizen; by default it sees demo/test data only. Free-tier latency is erratic (Gemini answered the same demo sentence in
  1.7 s and in 43 s), so many real turns would fall back to deterministic-only within the 7 s budget. Scheme names/descriptions come from the dataset in English (names are machine-translated
  for hi/te when VerbX is configured; descriptions are not).
* **Offline edge store** is browser `localStorage` standing in for kiosk SQLite; bundle integrity is a SHA-256 checksum,
  not a cryptographic signature. Only the 17 curated rules work offline.
* SQLite single node; PostgreSQL, real identity, OCR, PDF generation, DigiLocker/CSC and any real government submission are
  out of scope. Demo credentials and codes are not production security.
