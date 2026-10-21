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
docker compose up --build
# App        → http://localhost:5000
# Prometheus → http://localhost:9090   (scrapes http://anvaya:5000/metrics every 5 s)
# Grafana    → http://localhost:3000   (dashboard "Anvaya AI — Operations" opens as home; anonymous read-only,
#                                       admin password = GRAFANA_ADMIN_PASSWORD, default anvaya-grafana)
```

**Kubernetes** — `cp k8s/secrets.env.example k8s/secrets.env && kubectl apply -k .` (app + Prometheus + Grafana,
restricted pod security, NetworkPolicies, PVCs). See [`k8s/README.md`](k8s/README.md).

**Local dev**

```bash
# backend (Python 3.11+)
cd backend
pip install -r requirements.txt
python -m anvaya.manage init          # imports data/raw/*.csv, loads curated rules, seeds demo users
python -c "from anvaya import create_app; create_app().run(port=5000)"

# frontend (Node 20+) — in a second terminal
cd frontend
npm install
npm run dev                            # → http://localhost:5173 (proxies /api to :5000)
# or: npm run build  → Flask serves frontend/dist at http://localhost:5000
```

**Tests**

```bash
cd backend  && python -m pytest -q     # 60 tests: rules engine, extraction, API contracts, TC1–TC4
cd frontend && npm test                # offline TS engine vs the same shared fixtures
```

**Demo accounts (seeded, demo-only):** `reviewer / reviewer123` · `operator / operator123` (kiosk) · `admin / admin123` (data steward)

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
Voice: VerbX via API → browser Web Speech → text  ───▶  extraction (deterministic, en/hi/te + glossary)
Offline: cached signed bundle (sha256-validated,        [optional] LLM candidate facts (schema-validated, unconfirmed)
  atomic swap, last-known-good kept)                    rules_engine (pure, versioned)  ◀── golden_rules.json
  + TS mirror of the rules engine                       catalogue + knowledge graph (kg_nodes / kg_edges)
  + durable outbox (event_id + idempotency key)  ─────▶ /sync/events: dedupe · online re-check · conflicts
                                                        drafts (versioned) · handoff (consent, hashed codes)
                                                        reviewer (role-checked) · audit log · TC runner
```

| Spec module | Implementation |
|---|---|
| voice_adapter | `backend/anvaya/voice.py` (VerbX, env-configured) + `frontend/src/speech.ts` fallbacks |
| conversation / profile_service | `backend/anvaya/profile.py`, `extraction.py`, optional `llm.py` |
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
`VERBX_API_KEY`, `ANTHROPIC_API_KEY`. The cluster must be able to pull from GHCR (make the package public or add an
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

Config lives in `monitoring/` (`prometheus/prometheus.yml`, Grafana datasource + dashboard provisioning). The dashboard JSON is
generated by `monitoring/grafana/generate_dashboard.py <out.json>`. Gunicorn runs one worker with threads so the in-process
counters stay complete; scaling to several workers needs `prometheus_client` multiprocess mode.

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

## Security & privacy (demo scope)

Consent required before handoff · case codes are ~40-bit random, stored as SHA-256, expire (72 h) and lookups are
rate-limited; a code returns status only · reviewer/admin role checked server-side, forbidden attempts audited ·
idempotency keys on draft / handoff / sync, optimistic concurrency (version) on draft edits · kiosk exit deletes
unconsented facts, turns, evaluations and drafts · audit details hold IDs, never raw profile values · request logs hold
method/route/status/timing only · no raw audio stored · uploaded/retrieved text is treated as data.

## Honest limitations

* **VerbX**: the adapter is implemented but its request shape is configurable because the organizer API contract was not
  available; set `VERBX_*` in `.env` and reconcile paths. Without it the app uses browser speech (quality varies by
  browser/OS, Telugu voices may be missing) and always keeps text input.
* **Hindi/Telugu understanding** is a deterministic pattern extractor + small dialect glossary, tested on the phrasings in
  `tests/test_extraction.py` — not a general NLU. The optional Claude extractor (`ANVAYA_LLM_EXTRACTION=on`) only proposes
  unconfirmed candidate facts. Scheme names/descriptions come from the dataset in English.
* **Offline edge store** is browser `localStorage` standing in for kiosk SQLite; bundle integrity is a SHA-256 checksum,
  not a cryptographic signature. Only the 17 curated rules work offline.
* SQLite single node; PostgreSQL, real identity, OCR, PDF generation, DigiLocker/CSC and any real government submission are
  out of scope. Demo credentials and codes are not production security.
