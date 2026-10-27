def edit(p, pairs):
    s = open(p, encoding="utf-8", newline="").read()
    for old, new in pairs:
        assert s.count(old) == 1, (p, old[:80])
        s = s.replace(old, new)
    open(p, "w", encoding="utf-8", newline="").write(s)


edit("anvaya/catalogue.py", [
 ('def evaluate_session(session_id: str, *, require_confirmed=True, origin="online", loaded: dict | None = None) -> dict:',
  'def evaluate_session(session_id: str, *, require_confirmed=True, origin="online", loaded: dict | None = None, language: str | None = None) -> dict:'),
 ('''    evaluation in one round trip and writes in one more. `loaded` (if given) receives the session and marks."""''',
  '''    evaluation in one round trip and writes in one more. `loaded` (if given) receives the session and marks. `language` (en / hi / te)
    is the language the citizen is viewing the site in: the text comes back in it, whatever language the session started in."""'''),
 ('''    lang = session["language"]
    pending = fact_set.unconfirmed_critical()''', '''    lang = language if language in i18n.SUPPORTED_LANGUAGES else session["language"]
    pending = fact_set.unconfirmed_critical()'''),
 ('def document_guide(session_id: str) -> dict:', 'def document_guide(session_id: str, language: str | None = None) -> dict:'),
 ('''    session = profile._checked_session(session.fetchone(), allow_ended=False)
    lang = session["language"]
    ev = latest_evaluation(session_id, ev_row.fetchone())''', '''    session = profile._checked_session(session.fetchone(), allow_ended=False)
    lang = language if language in i18n.SUPPORTED_LANGUAGES else session["language"]
    ev = latest_evaluation(session_id, ev_row.fetchone())'''),
])
edit("anvaya/api.py", [
 ('''    loaded = {}
    ev = catalogue.evaluate_session(sid, loaded=loaded)
    return with_summary(ev, sid, loaded["session"]["language"], loaded["marks"])''', '''    loaded = {}
    lang = body().get("language")
    ev = catalogue.evaluate_session(sid, loaded=loaded, language=lang)
    return with_summary(ev, sid, lang if lang in i18n.SUPPORTED_LANGUAGES else loaded["session"]["language"], loaded["marks"])'''),
 ('''    s = profile.get_session(sid)
    ev = catalogue.latest_evaluation(sid)
    if not ev:
        raise ApiError("NO_EVALUATION", "No screening has been run yet.", 404)
    ev["results"] = [catalogue.localize_result(r, s["language"]) for r in ev["results"]]
    return with_summary(ev, sid, s["language"])''', '''    s = profile.get_session(sid)
    lang = request.args.get("language")
    lang = lang if lang in i18n.SUPPORTED_LANGUAGES else s["language"]
    ev = catalogue.latest_evaluation(sid)
    if not ev:
        raise ApiError("NO_EVALUATION", "No screening has been run yet.", 404)
    ev["results"] = [catalogue.localize_result(r, lang) for r in ev["results"]]
    return with_summary(ev, sid, lang)'''),
 ('''    return catalogue.document_guide(sid)''', '''    return catalogue.document_guide(sid, request.args.get("language"))'''),
])

# test
s = open("tests/test_api.py", encoding="utf-8", newline="").read()
s = s.rstrip("\n") + '''


def test_results_and_documents_follow_the_language_the_site_is_shown_in_not_the_one_the_session_started_in(client):
    sid = client.post("/api/v1/sessions", json={"mode": "personal", "language": "hi"}).json["session_id"]
    client.post(f"/api/v1/sessions/{sid}/turns", json={"utterance": BIHAR})
    for fid in client.post(f"/api/v1/sessions/{sid}/profile/confirm-all").json["needs_confirmation"]:
        client.patch(f"/api/v1/sessions/{sid}/profile/facts/{fid}", json={"confirmed": True})
    hi = client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate").json
    assert any("\\u0900" <= ch <= "\\u097f" for ch in hi["voice_summary"])  # no language given: the session's (Hindi)
    en = client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate", json={"language": "en"}).json
    assert not any("\\u0900" <= ch <= "\\u097f" for ch in en["voice_summary"]) and en["results"][0]["outcome_label"].isascii()
    te = client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate", json={"language": "te"}).json
    assert any("\\u0c00" <= ch <= "\\u0c7f" for ch in te["voice_summary"])
    assert client.post(f"/api/v1/sessions/{sid}/eligibility/evaluate", json={"language": "xx"}).json["results"][0]["outcome_label"] == hi["results"][0]["outcome_label"]
    latest = client.get(f"/api/v1/sessions/{sid}/eligibility/latest?language=en").json
    assert latest["results"][0]["outcome_label"].isascii()
    docs_en = client.get(f"/api/v1/sessions/{sid}/documents?language=en").json["documents"]
    docs_hi = client.get(f"/api/v1/sessions/{sid}/documents").json["documents"]
    assert docs_en and docs_en[0]["label"].isascii() and not docs_hi[0]["label"].isascii()
'''
open("tests/test_api.py", "w", encoding="utf-8", newline="").write(s)
print("ok")
