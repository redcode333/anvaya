"""Machine translation through VerbX with a DB cache, so each (text, source, target) is sent to VerbX once.

Used only where no curated translation exists (scheme names, free text), and as the English side-input of the optional
LLM extractor. Results are always labelled as machine translated; they never feed deterministic extraction or
eligibility, which work on canonical values.
"""
from . import voice
from .common import ApiError
from .db import get_db, iso


def _memo(db) -> dict:
    """Stored translations never change, so each process keeps the ones it has seen: (source, target, text) → text."""
    return db.backend.memo.setdefault("translations", {})


def _cached(texts: list[str], source: str, target: str) -> dict[str, str]:
    db = get_db()
    memo = _memo(db)
    out = {t: memo[(source, target, t)] for t in texts if (source, target, t) in memo}
    missing = [t for t in texts if t not in out]
    if missing:  # one query for all of them, not one per text
        rows = db.execute(
            "SELECT source_text, translated_text FROM translations WHERE source_lang=? AND target_lang=?"
            f" AND source_text IN ({','.join('?' * len(missing))})", (source, target, *missing)).fetchall()
        for text, translated in rows:
            out[text] = memo[(source, target, text)] = translated
    return out


def _store(source: str, target: str, pairs: list[tuple[str, dict]]) -> None:
    db = get_db()
    db.executemany(
        "INSERT INTO translations(source_lang, target_lang, source_text, translated_text, provider, model, created_at)"
        " VALUES (?,?,?,?,?,?,?) ON CONFLICT DO NOTHING",
        [(source, target, t, r["text"], "verbx", r["model"], iso()) for t, r in pairs if not r["degraded"]],
    )
    db.commit()


def translate_many(texts: list[str], source: str, target: str) -> dict[str, str]:
    """Best effort: {text: translation} for every text VerbX (or the cache) could translate; missing keys mean
    'show the original'. Degraded VerbX results are used but not cached."""
    texts = sorted({t for t in texts if t and t.strip()})
    if source == target or not texts:
        return {}
    found = _cached(texts, source, target)
    missing = [t for t in texts if t not in found]
    if missing and voice.configured():
        try:
            results = voice.translate_batch(missing, source, target)
        except voice.VerbXError:
            return found
        found.update({t: r["text"] for t, r in zip(missing, results)})
        _store(source, target, list(zip(missing, results)))
    return found


def translate_for_extraction(text: str, source: str, timeout: float) -> str | None:
    """English version of an utterance for the LLM extractor (cached; one attempt within the turn budget).
    None when VerbX is not configured or fails — the LLM then sees the original only."""
    hit = _cached([text], source, "en").get(text)
    if hit or not voice.configured():
        return hit
    try:
        r = voice.translate(text, source, "en", timeout=timeout)
    except voice.VerbXError:
        return None
    _store(source, "en", [(text, r)])
    return r["text"]


def translate_text(text: str, source: str, target: str) -> dict:
    """Single text for POST /sessions/<sid>/translate; raises TRANSLATION_UNAVAILABLE when VerbX cannot help."""
    for lang in (source, target):
        if lang not in voice.LANGS:
            raise ApiError("UNSUPPORTED_LANGUAGE", "Supported languages: en, hi, te.", 422)
    text = (text or "").strip()
    if not text or len(text) > 2000:
        raise ApiError("INVALID_TEXT", "Text must be 1–2000 characters.", 422)
    base = {"source_text": text, "source_lang": source, "target_lang": target}
    if source == target:
        return {**base, "text": text, "machine_translated": False, "cached": False}
    hit = _cached([text], source, target).get(text)
    if hit:
        return {**base, "text": hit, "machine_translated": True, "provider": "verbx", "cached": True}
    if not voice.configured():
        raise ApiError("TRANSLATION_UNAVAILABLE", "Translation service is not configured.", 503)
    try:
        r = voice.translate(text, source, target)
    except voice.VerbXError as e:
        raise ApiError("TRANSLATION_UNAVAILABLE", f"Translation is unavailable ({e}); showing the original text.", 503)
    _store(source, target, [(text, r)])
    return {**base, "text": r["text"], "machine_translated": True, "provider": "verbx", "cached": False}


def localize_scheme_names(evaluation: dict, lang: str) -> dict:
    """Add machine-translated scheme names (hi/te) to each result and build the voice summary with them."""
    names = translate_many([r["scheme_name"] for r in evaluation["results"]], "en", lang) if lang != "en" else {}
    for r in evaluation["results"]:
        r["scheme_name_localized"] = names.get(r["scheme_name"])
        r["scheme_name_machine_translated"] = r["scheme_name"] in names
    return names
