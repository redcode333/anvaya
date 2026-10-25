import json
import sys

DS = {"type": "prometheus", "uid": "prometheus"}
panels, state = [], {"id": 1, "y": 0}


def add(p, w, h, x):
    p.update({"id": state["id"], "datasource": DS, "gridPos": {"x": x, "y": state["y"], "w": w, "h": h}})
    state["id"] += 1
    panels.append(p)


def row(title):
    panels.append({"type": "row", "title": title, "id": state["id"], "collapsed": False,
                   "gridPos": {"x": 0, "y": state["y"], "w": 24, "h": 1}})
    state["id"] += 1
    state["y"] += 1


def stat(title, expr, x, w=4, unit="none", desc=""):
    add({"type": "stat", "title": title, "description": desc,
         "targets": [{"expr": expr, "refId": "A", "instant": True}],
         "fieldConfig": {"defaults": {"unit": unit, "color": {"mode": "thresholds"},
                                      "thresholds": {"mode": "absolute", "steps": [{"color": "green", "value": None}]}},
                         "overrides": []},
         "options": {"reduceOptions": {"calcs": ["lastNotNull"]}, "colorMode": "value", "graphMode": "none",
                     "textMode": "auto"}}, w, 4, x)


def ts(title, targets, x, w=12, h=8, unit="short", stack=False, desc=""):
    add({"type": "timeseries", "title": title, "description": desc,
         "targets": [{"expr": e, "legendFormat": l, "refId": chr(65 + i)} for i, (e, l) in enumerate(targets)],
         "fieldConfig": {"defaults": {"unit": unit, "custom": {"fillOpacity": 18, "lineWidth": 2, "showPoints": "never",
                                                               "stacking": {"mode": "normal" if stack else "none"}}},
                         "overrides": []},
         "options": {"legend": {"displayMode": "list", "placement": "bottom"}, "tooltip": {"mode": "multi"}}}, w, h, x)


def bars(title, expr, legend, x, w=12, h=8, desc=""):
    add({"type": "bargauge", "title": title, "description": desc,
         "targets": [{"expr": expr, "legendFormat": legend, "refId": "A", "instant": True}],
         "fieldConfig": {"defaults": {"unit": "short", "min": 0, "color": {"mode": "continuous-BlYlRd"}}, "overrides": []},
         "options": {"orientation": "horizontal", "displayMode": "gradient", "showUnfilled": True,
                     "reduceOptions": {"calcs": ["lastNotNull"]}}}, w, h, x)


OUTCOME_COLORS = [("MATCH", "green"), ("PROVISIONAL", "blue"), ("INSUFFICIENT_INFORMATION", "orange"),
                  ("MISMATCH", "red"), ("NEEDS_HUMAN_REVIEW", "purple")]


def pie(title, expr, legend, x, w=8, h=8, desc=""):
    add({"type": "piechart", "title": title, "description": desc,
         "targets": [{"expr": expr, "legendFormat": legend, "refId": "A", "instant": True}],
         "fieldConfig": {"defaults": {"unit": "short"}, "overrides": [
             {"matcher": {"id": "byName", "options": n},
              "properties": [{"id": "color", "value": {"mode": "fixed", "fixedColor": c}}]} for n, c in OUTCOME_COLORS]},
         "options": {"pieType": "donut", "reduceOptions": {"calcs": ["lastNotNull"]},
                     "legend": {"displayMode": "table", "placement": "right", "values": ["value"]}}}, w, h, x)


R = "$__range"

row("Overview")
stat("Catalogue schemes", 'anvaya_catalogue_records{kind="schemes"}', 0)
stat("Curated rules", 'anvaya_catalogue_records{kind="curated_rules"}', 4)
stat("Rules verified vs official source", 'anvaya_catalogue_records{kind="rules_source_verified"}', 8,
     desc="Set by a data steward in /admin/schemes")
stat("Cases pending review", 'anvaya_cases{status="PENDING_REVIEW"}', 12)
stat("Active sessions", "sum(anvaya_active_sessions)", 16)
stat("API p95 latency", "histogram_quantile(0.95, sum by (le) (rate(anvaya_http_request_duration_seconds_bucket[5m])))",
     20, unit="s")
state["y"] += 4

row("Screening (deterministic rules)")
pie("Outcomes (since server start)", f"sum by (outcome) (anvaya_eligibility_outcomes_total)", "{{outcome}}", 0,
    desc="Per-scheme outcomes. PROVISIONAL dominates by design until documents and sources are verified.")
ts("Screenings vs confirmation blocks", [
    ("sum(rate(anvaya_eligibility_evaluations_total[1m])) * 60", "screenings / min"),
    ("rate(anvaya_screening_blocked_total[1m]) * 60", "blocked until confirmed / min")], 8, w=8,
   desc="Blocked = screening refused because high-impact facts (age, income, state, household) were unconfirmed.")
ts("Rule evaluation time (p50 / p95)", [
    ("histogram_quantile(0.5, sum by (le) (rate(anvaya_rule_evaluation_seconds_bucket[5m])))", "p50"),
    ("histogram_quantile(0.95, sum by (le) (rate(anvaya_rule_evaluation_seconds_bucket[5m])))", "p95")], 16, w=8,
   unit="s", desc="Pure rules-engine time per screening, excluding I/O. NFR target: sub-second.")
state["y"] += 8
bars("Outcomes by scheme rule (since server start)", f"sum by (rule_id, outcome) (anvaya_eligibility_outcomes_total)",
     "{{rule_id}} · {{outcome}}", 0, w=12, h=12)
bars("Citizen corrections by attribute (since server start)", f"sum by (attribute) (anvaya_fact_corrections_total)",
     "{{attribute}}", 12, w=6, h=12, desc="Voice-correction loop: how often extracted facts were corrected.")
bars("Facts extracted by attribute (since server start)", f"sum by (attribute) (anvaya_facts_extracted_total)",
     "{{attribute}}", 18, w=6, h=12)
state["y"] += 12

row("Conversation & voice")
ts("Turns by language", [("sum by (language) (rate(anvaya_conversation_turns_total[1m])) * 60", "{{language}}")], 0,
   w=8, stack=True)
ts("Turns by channel", [("sum by (channel) (rate(anvaya_conversation_turns_total[1m])) * 60", "{{channel}}")], 8,
   w=8, stack=True)
ts("VerbX voice calls", [("sum by (op, result) (rate(anvaya_voice_requests_total[1m])) * 60", "{{op}} {{result}}")],
   16, w=8, desc="not_configured / error: clients fall back to browser speech or text.")
state["y"] += 8

row("LLM extraction (optional; never decides eligibility)")
ts("LLM calls by provider and result", [
    ("sum by (provider, result) (rate(anvaya_llm_calls_total[1m])) * 60", "{{provider}} {{result}}")], 0, w=8,
   desc="ok / cache_hit = answered; timeout, rate_limited, quota_exhausted, server_error, invalid_output = moved on to "
        "the next provider; skipped_* = exhausted or open circuit.")
ts("LLM call latency (p50 / p95)", [
    ("histogram_quantile(0.5, sum by (le, provider) (rate(anvaya_llm_latency_seconds_bucket[5m])))", "p50 {{provider}}"),
    ("histogram_quantile(0.95, sum by (le, provider) (rate(anvaya_llm_latency_seconds_bucket[5m])))", "p95 {{provider}}")],
   8, w=8, unit="s", desc="Per call; capped at 6 s, and at 7 s for the whole turn.")
ts("Provider fallbacks", [
    ('sum by (from, to) (increase(anvaya_llm_fallbacks_total[5m]))', "{{from}} → {{to}}")], 16, w=8,
   desc="to=deterministic: every provider failed; the turn used deterministic extraction only.")
state["y"] += 8
bars("LLM facts by merge outcome (since server start)", "sum by (outcome) (anvaya_llm_merge_total)", "{{outcome}}", 0,
     w=12, h=6, desc="agree = same as deterministic; llm_only = added as an unconfirmed candidate; disagree = held for "
                     "the citizen to choose; dropped_* = evidence not in the utterance, invalid value, relative's age.")
stat("LLM answers served from cache", 'sum(anvaya_llm_calls_total{result="cache_hit"})', 12, w=6)
stat("Turns with all providers down", 'sum(anvaya_llm_fallbacks_total{to="deterministic"})', 18, w=6)
state["y"] += 6

row("Cases, idempotency & offline sync")
ts("Cases by status", [("anvaya_cases", "{{status}}")], 0, w=8)
ts("Case transitions", [("sum by (action) (increase(anvaya_case_transitions_total[5m]))", "{{action}}")], 8, w=8)
ts("Drafts & idempotent replays", [
    ("sum by (action) (increase(anvaya_drafts_total[5m]))", "draft {{action}}"),
    ("sum by (scope) (increase(anvaya_idempotent_replays_total[5m]))", "replay {{scope}}")], 16, w=8,
   desc="Replays = retried writes answered from the original result (no duplicates).")
state["y"] += 8
ts("Kiosk sync events by status", [("sum by (status) (increase(anvaya_sync_events_total[5m]))", "{{status}}")], 0,
   w=12, stack=True, desc="duplicate = outbox resend deduplicated by idempotency key.")
ts("Offline results changed on online re-check", [("increase(anvaya_sync_result_changed_total[5m])", "changed")], 12,
   w=12)
state["y"] += 8

row("API & security")
ts("Request rate by route", [("sum by (route) (rate(anvaya_http_requests_total[1m]))", "{{route}}")], 0, w=12,
   unit="reqps")
ts("p95 latency by route",
   [("histogram_quantile(0.95, sum by (le, route) (rate(anvaya_http_request_duration_seconds_bucket[5m])))", "{{route}}")],
   12, w=12, unit="s")
state["y"] += 8
ts("Error responses", [
    ('sum(rate(anvaya_http_requests_total{status=~"5.."}[1m]))', "5xx"),
    ('sum by (status) (rate(anvaya_http_requests_total{status=~"4.."}[1m]))', "{{status}}")], 0, w=8, unit="reqps",
   desc="409 = confirmation/version conflicts, 428 = missing idempotency key, 429 = rate-limited lookups.")
ts("Auth events", [("sum by (result) (increase(anvaya_auth_events_total[5m]))", "{{result}}")], 8, w=8)
ts("Rate-limited code lookups", [("sum by (bucket) (increase(anvaya_code_lookups_rate_limited_total[5m]))", "{{bucket}}")],
   16, w=8)
state["y"] += 8

row("Background jobs & database")
stat("Hours since last successful retention", "(time() - anvaya_job_last_success_timestamp{job=\"retention\"}) / 3600", 0, w=6, unit="h",
     desc="/api/v1/ready warns above 26 h. Rebuilt from the job_runs table, so it survives restarts.")
stat("Hours since last successful cleanup", "(time() - anvaya_job_last_success_timestamp{job=\"cleanup\"}) / 3600", 6, w=6, unit="h")
ts("Job runs by status", [("sum by (job, status) (increase(anvaya_job_runs_total[1h]))", "{{job}} {{status}}")], 12, w=12, h=4,
   desc="skipped = another run of the same job held the lock.")
state["y"] += 4
ts("DB round trips per request (p95, by route)",
   [("histogram_quantile(0.95, sum by (le, route) (rate(anvaya_db_roundtrips_per_request_bucket[5m])))", "{{route}}")], 0, w=12,
   desc="Each round trip costs about 70 ms on the hosted database; budgets are asserted in tests/test_db.py.")
ts("DB queries per request (p95, by route)",
   [("histogram_quantile(0.95, sum by (le, route) (rate(anvaya_db_queries_per_request_bucket[5m])))", "{{route}}")], 12, w=12)
state["y"] += 8

row("Official scenarios")
bars("TC1–TC4 runs (since server start)", f"sum by (tc, result) (anvaya_test_runs_total)", "{{tc}} {{result}}", 0,
     w=24, h=6)

dash = {"uid": "anvaya-overview", "title": "Anvaya AI — Operations", "tags": ["anvaya"], "timezone": "browser",
        "schemaVersion": 39, "version": 1, "refresh": "5s", "time": {"from": "now-30m", "to": "now"},
        "panels": panels, "templating": {"list": []}, "annotations": {"list": []}, "editable": False,
        "description": "Live operational view of the Anvaya API. Labels never contain profile values or IDs."}
with open(sys.argv[1], "w", encoding="utf-8") as f:
    json.dump(dash, f, indent=2, ensure_ascii=False)
print(len(panels), "panels")
