"""`python -m anvaya.manage prerender-audio`: synthesize the fixed spoken prompts in en/hi/te into the TTS cache.

Covers every sentence the app reads aloud that does not depend on what a citizen said: the greeting, every follow-up
question, the confirmation prompts, and the summary templates (intro, "n schemes may suit you, m need more
information" for small n/m, one line per curated scheme and outcome, a single missing document). Replies and
summaries are read sentence by sentence, so these come straight from the cache; only sentences that repeat the
citizen's own details are synthesized live.
"""
from . import catalogue, i18n, translation

FIXED_MESSAGES = ("greeting", "nothing_heard", "please_confirm", "ready", "summary_intro")
SPOKEN_OUTCOMES = ("MATCH", "PROVISIONAL")  # the outcomes summary_parts() reads out per scheme


def texts(max_count: int = 4, langs=i18n.SUPPORTED_LANGUAGES) -> list[tuple[str, str, str]]:
    """[(text, language, kind)] in a stable order; needs an app context (scheme names come from the active rules)."""
    names_en = sorted({item["meta"]["scheme_name"] for item in catalogue.active_rules()})
    out = []
    for lang in langs:
        out += [(i18n.t(i18n.MESSAGES, k, lang), lang, "message") for k in FIXED_MESSAGES]
        out += [(i18n.t(i18n.QUESTIONS, k, lang), lang, "question") for k in i18n.QUESTIONS]
        out += [(i18n.t(i18n.MESSAGES, "summary_count", lang, n=n, m=m), lang, "summary")
                for n in range(max_count + 1) for m in range(max_count + 1)]
        local = translation.translate_many(names_en, "en", lang) if lang != "en" else {}
        out += [(i18n.t(i18n.MESSAGES, "summary_scheme", lang, name=local.get(name, name),
                        outcome=i18n.t(i18n.OUTCOMES, o, lang)), lang, "summary")
                for name in names_en for o in SPOKEN_OUTCOMES]
        out += [(i18n.t(i18n.MESSAGES, "summary_missing_docs", lang, docs=i18n.doc_label(d, lang)[0]), lang, "summary")
                for d in i18n.DOCUMENTS]
    return out
