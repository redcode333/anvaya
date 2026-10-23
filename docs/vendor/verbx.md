# VerbX API — what Anvaya uses (discovered 2026-10-23)

Everything below was observed against the live API with the team's key, or read from VerbX's own
machine-readable spec. Nothing here is guessed. The key has been removed from every example.

## How this was discovered

| Probe | Result |
|---|---|
| `POST /v1/translate` (VerbX's own example) | **200**, works for en→hi, en→te, hi→en, te→en |
| `GET /` | 200 `{"service":"VerbX AI","status":"operational","version":"1.0.0"}` |
| `GET /openapi.json` | **200** — OpenAPI 3.1.0, 658 paths, 613 schemas (FastAPI) |
| `GET /docs` | 200 — Swagger UI that loads `/openapi.json` |
| `GET /v1/openapi.json`, `/swagger.json`, `/v1/models`, `/v1/languages` | 404 `ERR_HTTP` |

The spec lists, among many product-specific routes, these generic ones that Anvaya needs:

| Spec tag | Endpoint | Used by Anvaya |
|---|---|---|
| `translate` | `POST /v1/translate` | yes — `/sessions/<sid>/translate`, scheme names |
| `translate` | `POST /v1/translate/batch` | yes — scheme names for one result list in one call |
| `stt` | `POST /v1/stt` | yes — voice input |
| `tts` | `POST /v1/tts` | yes — reading the summary aloud |
| `tts` | `GET /v1/tts/voices` | discovery only |
| `language` | `GET /v1/language/supported` | discovery only |

No other path was tried. Product-specific routes in the spec (`/v1/personal/*`, `/v1/travel/*`, `/saas/playground/*`, …)
were not called.

## Base URL and headers

```
Base URL: https://api.verbxeco.com
x-api-key:        <VERBX_API_KEY>          # required; never logged
X-VerbX-Shell:    saas
Content-Type:     application/json
Idempotency-Key:  <new UUID per logical request; Anvaya reuses it for its single retry>
```

The spec declares an OAuth2 `Bearer` scheme on these routes, but `x-api-key` + `X-VerbX-Shell: saas` is what works
for API keys (VerbX's own example). Without `x-api-key` the API answers `401 unauthorized.tenant_missing`.

Useful response headers: `x-request-id`, `x-correlation-id`, `x-ratelimit-limit: 120`, `x-ratelimit-windowms: 60000`,
`x-ratelimit-scope: per_token`, `x-api-plan: free`, `x-verbx-credits-deducted`, `x-verbx-credits-remaining`.
**Rate limit: 120 requests per minute per key.**

## Language codes

`GET /v1/language/supported` → `{"languages":[{"code":"hi","iso639_3":"hin"}, {"code":"te","iso639_3":"tel"},
{"code":"en","iso639_3":"eng"}, …]}` — plain ISO 639-1 codes. Anvaya sends `en`, `hi`, `te` (not `hi-IN`).

`GET /v1/tts/voices` → for each of `en`, `hi`, `te`: `verbx-female` and `verbx-male`.

## POST /v1/translate

Request (schema `TranslateRequest`; required: `text` 1–10000 chars, `source_lang`, `target_lang`; optional `options`,
`idempotency_key`, `clean`):

```json
{"text": "Hello world", "source_lang": "en", "target_lang": "hi"}
```

Response 200 (schema `TranslateResponse`; required `text`, `confidence`, `diagnostics`, `usage`):

```json
{"text": "हैलो वर्ल्ड", "confidence": 0.1001,
 "diagnostics": {"provider": "verbx", "model": "verbx-langshift", "cached": false,
                 "quality": {"score": 0.1001, "components": {"token_f1": 1.0, "chrf_lite": 1.0, "length_ratio": 1.0,
                             "symbol_sanity": 1.0, "latency_penalty": 0.1001}, "details": {"mode": "mt", "has_reference": false}},
                 "latency_ms": 2490},
 "usage": {"characters": 11, "billable": true}, "degraded": false, "served_by_tier": "onnx"}
```

Observed translations:

| Direction | Input | Output | Round trip | Server `latency_ms` |
|---|---|---|---|---|
| en→hi | Hello world | हैलो वर्ल्ड | 3084 ms (cold) | 2490 |
| en→te | Hello world | హలో వరల్డ్ | 501 ms | 61 |
| hi→en | मेरी उम्र साठ साल है | I am sixty years old | 2675 ms | 2295 |
| te→en | నా వయస్సు అరవై ఐదు సంవత్సరాలు | I am sixty-five years old | 483 ms | 114 |

Note: `confidence` is the quality score, which includes a **latency penalty** — the en→hi result above scored 0.10
only because it was slow; every content component was 1.0. Anvaya therefore does not reject translations on
`confidence`. The schema also has `translation_failed`, `degraded`, `degraded_reason`; Anvaya treats
`translation_failed: true` or empty `text` as a failure and does not cache `degraded: true` results.

## POST /v1/translate/batch

Request: `{"items": [{"source": "en", "target": "hi", "text": "Old age pension"}, {"source": "en", "target": "te", "text": "Old age pension"}]}`
(note: `source`/`target`, not `source_lang`/`target_lang`; `items` is 1–**50** entries per the spec).
Response 200: a JSON **array** of `TranslateResponse`, in item order —
`[{"text": "वृद्धावस्था पेंशन", …}, {"text": "వృద్ధాప్య పింఛను", …}]`. 451 ms for two items.

## POST /v1/stt

Request (schema `STTRequest`, JSON — not multipart): `audio_base64` ("Base64 audio (wav/mp3/ogg/webm)") or
`audio_url`, plus `language`, and optional `punctuate`, `hints`, `max_latency_ms`, … .

```json
{"audio_base64": "<base64 WAV>", "language": "hi"}
```

Response 200 (schema `STTResponse`, required `text`):

```json
{"text": "నా వయసు అరవై అయిదు సంవత్సరాలు", "language": "te", "confidence": 0.9, "segments": null, "duration_sec": null,
 "model": "verbx-vocaline", "offline": null, "cache": null, "latency_ms": 266, "usage_units": null,
 "degraded": false, "served_by_tier": "onnx"}
```

Live round trip (VerbX TTS clip → VerbX STT):

| Lang | Spoken (TTS input) | Transcribed | Round trip |
|---|---|---|---|
| hi | मेरी उम्र **साठ** साल है | मेरी उम्र **सात** साल है | 663 ms |
| te | నా వయస్సు అరవై ఐదు సంవత్సరాలు | నా వయసు అరవై అయిదు సంవత్సరాలు | 996 ms |

**The Hindi clip came back as सात (7) instead of साठ (60)** — exactly the confusable pair Anvaya's extraction flags,
so this transcript is held for explicit confirmation rather than used.

**Unusable audio is not an HTTP error**: 12 bytes of non-audio returned **200** with
`{"text": "", "language": null, "degraded": true, "degraded_reason": "provider_outage", "served_by_tier": "refuse"}`.
Anvaya treats an empty transcript as "nothing heard" and falls back to typing.

## POST /v1/tts

Request (schema `TTSRequestBody`, `additionalProperties: false`; required `text` 1–10000 chars):

```json
{"text": "मेरी उम्र साठ साल है", "options": {"language": "hi", "format": "wav"}}
```

`options` (schema `TTSOptions`): `voice_id`, `language`, `emotion`, `style`, `speed` 0.5–2, `pitch`, `sample_rate`,
`format` ∈ mp3|wav|ogg|flac|pcm_s16le (default mp3), `stream`, `ssml`, `cache_key`.

Response 200: **raw audio bytes**, `Content-Type: audio/wav`, headers `x-verbx-audio-format: wav`,
`x-verbx-sample-rate: 22050` (the spec documents `application/json` with an empty schema; the live API returns binary).

| Lang | Text | Size | Round trip |
|---|---|---|---|
| hi | मेरी उम्र साठ साल है | 82,834 bytes WAV | 955 ms |
| te | నా వయస్సు అరవై ఐదు సంవత్సరాలు | 109,176 bytes WAV | 1061 ms |

With `"voice_id": "verbx-female"` and `"language": "te"` ("నమస్కారం"): 200, 48,966 bytes WAV, 921 ms.
Only `format: "wav"` was exercised; Anvaya requests WAV with `voice_id` from `VERBX_TTS_VOICE`.

## Latency across runs (client round trip, same day)

| Call | Fastest | Slowest |
|---|---|---|
| `/v1/translate` (one short text) | 373 ms | 4,471 ms (cold start: 3,084 ms) |
| `/v1/translate/batch` (2–10 names) | 451 ms | 1,253 ms |
| `/v1/tts` (one short sentence, WAV) | 905 ms | **10,530 ms** |
| `/v1/stt` (3–5 s clip) | 663 ms | 1,447 ms |

TTS can come close to the default `VERBX_TIMEOUT_S=15`; on timeout Anvaya retries once and then the browser reads the
text aloud instead.

## Errors seen

| Situation | Status | Body |
|---|---|---|
| no `x-api-key` | 401 | `{"error":{"code":"unauthorized.tenant_missing","message":"Tenant context is required for this endpoint.","correlation_id":"cx_…"}}` |
| invalid key | 401 | `{"error":{"code":"unauthorized.key_invalid","message":"API key is invalid or revoked.","correlation_id":"cx_…"}}` |
| empty `text` | 422 | `{"error":{"status":422,"code":"ERR_REQUEST_SCHEMA","message":"The request could not be processed.","details":{"validation_error_count":1,"fields":["body.text"]}}}` |
| unsupported language `xx` | **503 after 5.1 s** | `{"error":{"status":503,"code":"ERR_HTTP","message":"upstream.empty_translation"}}` |
| unknown path | 404 | `{"error":{"status":404,"code":"ERR_HTTP","message":"Not Found"}}` |
| non-audio to STT | 200 | empty `text`, `degraded: true` (see above) |

Error envelope: `{"error": {"code", "message", "correlation_id", "status"?, "details"?}}`.
Anvaya only sends `en`/`hi`/`te`, so the slow 503 should not occur in normal use.

## How Anvaya calls it (`backend/anvaya/voice.py`)

* Headers as above; one `Idempotency-Key` per logical request, reused on its retry.
* Timeout `VERBX_TIMEOUT_S` (default 15 s); **one retry** on 5xx, timeout or connection error; no retry on 4xx.
* Any failure → `503 VOICE_UNAVAILABLE` (speech) or `503 TRANSLATION_UNAVAILABLE` (translate); the frontend falls back
  to browser speech, then typing, and shows original English text when translation is unavailable.
* Logs carry only the endpoint, HTTP status, latency and VerbX correlation id — never text, audio or the key.
* Translations are cached in the `translations` table, so each (text, source, target) is sent to VerbX once.
