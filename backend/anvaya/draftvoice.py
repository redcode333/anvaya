"""Fill a draft by speaking (or typing): one answer at a time, or several in one sentence.

`plan` lists the fields a citizen can still fill, in form order, each with the question to ask. `parse` turns what was said into values
for those fields. Neither saves anything: the page puts the values into the form for the citizen to review, and saving goes through the
normal draft edit (versioned, audited, re-screened). The same guardrails as the chat apply (no Aadhaar numbers, no abuse), and what was
said is never stored.
"""
from __future__ import annotations

import re

from . import cases, extraction, guardrails, i18n, profile
from .common import ApiError, audit

# Always offered for filling; every other field only while it is still missing.
ALWAYS_EDITABLE = ("applicant_name", "district")

_NAME_PREFIX = re.compile(
    r"^(?:my\s+(?:full\s+)?name\s+is|my\s+name'?s|name\s+is|this\s+is|i\s+am|i'?m|it'?s|call\s+me"
    r"|mera\s+(?:poora\s+)?naam(?:\s+hai)?|मेरा\s+(?:पूरा\s+)?नाम(?:\s+है)?|नाम(?:\s+है)?|मैं|मै|నా\s+(?:పూర్తి\s+)?పేరు)\s+", re.I)
_NAME_SUFFIX = re.compile(r"\s+(?:hai|hoon|hun|है|हूँ|हूं|అండి|ఉంది|అని|please)$", re.I)
_DISTRICT_NOISE = re.compile(
    r"\b(?:district|dist|zila|jila|my|the|in|from|is|i|live|stay|living|staying|at|of|rehta|rehti|hoon|hun|hai|mein|me)\b"
    r"|जिला|ज़िला|जिले|ज़िले|में|से|का|की|रहता|रहती|हूँ|हूं|है|मेरा|జిల్లా|లో|నేను|ఉంటున్నాను", re.I)
_PUNCT = re.compile(r"[.,;:!?।\"“”]+")


def _words_ok(text: str, max_len: int) -> bool:
    """Letters (any script), spaces, dots, apostrophes and hyphens only; no digits; 2..max_len characters."""
    t = text.strip()
    # \w does not cover Devanagari / Telugu vowel signs, so those two blocks are listed explicitly.
    word = r"[\wऀ-ॿఀ-౿]+"
    return (2 <= len(t) <= max_len and not re.search(r"\d", t) and "_" not in t
            and re.fullmatch(rf"{word}(?:[ .'’\-]{word.replace('+', '*')})*\.?", t, re.U) is not None)


def _tidy(text: str) -> str:
    return " ".join(text.split())


def _title(text: str) -> str:
    return " ".join(w[:1].upper() + w[1:] if w.isascii() else w for w in text.split())


def clean_name(utterance: str) -> str | None:
    t = _tidy(_PUNCT.sub(" ", utterance))
    t = _NAME_PREFIX.sub("", t)
    t = re.split(r"\s+(?:and|aur|और|మరియు)\s+", t, maxsplit=1)[0]  # "Ravi and I live in Guntur": the name is the part before "and"
    t = _NAME_SUFFIX.sub("", t).strip()
    words = t.split()
    if not 1 <= len(words) <= 5 or not _words_ok(t, 60):
        return None
    return _title(t)


def clean_district(utterance: str) -> str | None:
    key = extraction._nk(utterance)
    for k, (district, _state) in extraction.DISTRICTS.items():
        if k in key:
            return district
    t = _tidy(_DISTRICT_NOISE.sub(" ", _PUNCT.sub(" ", utterance)))
    words = t.split()
    if not 1 <= len(words) <= 3 or not _words_ok(t, 40):
        return None
    return _title(t)


def _draft(draft_id: str, session_id: str | None) -> dict:
    d = cases.get_draft(draft_id, session_id)
    if d.get("case") and d["case"]["status"] in cases.LOCKED_STATES:
        raise ApiError("DRAFT_LOCKED", "This draft is with the reviewer and cannot be changed now.", 409)
    return d


def _fillable(d: dict) -> list[dict]:
    """Fields still open to the citizen: missing ones, and the name and district even when something is there (to correct it)."""
    return [f for f in d["fields"] if f["provenance"] == "missing" or (f["key"] in ALWAYS_EDITABLE and f["value"] in (None, ""))]


def plan(draft_id: str, session_id: str | None, lang: str) -> dict:
    lang = lang if lang in i18n.SUPPORTED_LANGUAGES else "en"
    d = _draft(draft_id, session_id)
    steps = [{"key": f["key"], "label": i18n.t(i18n.ATTRIBUTE_LABELS, f["key"], lang),
              "question": i18n.t(i18n.QUESTIONS, f["key"], lang)} for f in _fillable(d)]
    return {"draft_id": draft_id, "version": d["version"], "steps": steps}


def parse(draft_id: str, session_id: str | None, utterance: str, asked: str | None, lang: str) -> dict:
    lang = lang if lang in i18n.SUPPORTED_LANGUAGES else "en"
    utterance = (utterance or "").strip()
    if not utterance or len(utterance) > 500:
        raise ApiError("INVALID_UTTERANCE", "Say or type a short answer (up to 500 characters).", 422)
    d = _draft(draft_id, session_id)
    allowed = {f["key"] for f in _fillable(d)}
    out = {"fields": {}, "labels": {}, "understood": False, "skipped": False, "guardrail": None, "heard": None, "message": None}

    blocked = guardrails.screen(utterance)  # no Aadhaar / card numbers, no abuse, no prompt tricks; never echoed back or stored
    if blocked in ("sensitive", "abuse", "injection"):
        out["guardrail"] = blocked
        out["message"] = i18n.t(i18n.MESSAGES, f"guard_{blocked}", lang)
        audit("draft.voice_fill", session_id=session_id, details={"draft_id": draft_id, "blocked": blocked})
        get_db_commit()
        return out
    out["heard"] = utterance

    found = {f["attribute"]: f["value"] for f in extraction.extract(utterance, asked=asked if asked in allowed else None)["facts"]
             if f["attribute"] in allowed}
    if asked == "applicant_name" and "applicant_name" not in found:
        name = clean_name(utterance)
        if name:
            found["applicant_name"] = name
    if asked == "district" and "district" not in found:
        district = clean_district(utterance)
        if district:
            found["district"] = district
    if "applicant_name" in found:  # the extractor's name is taken as heard; make sure it is a name, not a sentence
        name = clean_name(str(found["applicant_name"]))
        if name:
            found["applicant_name"] = name
        else:
            del found["applicant_name"]

    if not found and guardrails.no_details(utterance) == "skip":
        out["skipped"] = True
        out["message"] = i18n.t(i18n.MESSAGES, "skip_ok", lang)
    for attr, value in found.items():
        try:
            out["fields"][attr] = profile.validate_value(attr, value)
        except ApiError:
            continue
    out["labels"] = {a: i18n.t(i18n.ATTRIBUTE_LABELS, a, lang) for a in out["fields"]}
    out["understood"] = bool(out["fields"])
    if out["understood"]:
        heard = ", ".join(f"{out['labels'][a]}: {profile.display_value(a, v, lang)}" for a, v in out["fields"].items())
        out["message"] = f"{i18n.t(i18n.MESSAGES, 'heard', lang)} {heard}."
    elif not out["skipped"]:
        out["message"] = i18n.t(i18n.MESSAGES, "nothing_heard", lang)
    audit("draft.voice_fill", session_id=session_id, details={"draft_id": draft_id, "attributes": sorted(out["fields"]), "understood": out["understood"]})
    get_db_commit()
    return out


_EXPIRED = re.compile(r"\bexpir\w*|\boutdated\b|समाप्त|एक्सपायर|గడువు", re.I)
_UNSURE = re.compile(r"not\s+sure|don'?t\s+know|do\s+not\s+know|no\s+idea|maybe|\bunsure\b|पता\s+नहीं|मालूम\s+नहीं|नहीं\s+पता|తెలియదు|తెలీదు", re.I)
_LOST = re.compile(r"\blost\b|\bmissing\b|don'?t\s+have|do\s+not\s+have|\bhaven'?t\b|नहीं\s+है|खो\s+गया|गुम|లేదు|లేవు", re.I)


def parse_document_status(session_id: str | None, utterance: str, lang: str) -> dict:
    """What a spoken answer says about one document: available (have it), missing, expired or unknown (not sure). Nothing is saved here;
    the page marks the document through the normal call. A question ("why do you need this?") is not an answer."""
    lang = lang if lang in i18n.SUPPORTED_LANGUAGES else "en"
    utterance = (utterance or "").strip()
    if not utterance or len(utterance) > 300:
        raise ApiError("INVALID_UTTERANCE", "Say or type a short answer.", 422)
    out = {"status": None, "understood": False, "message": None}
    if guardrails.screen(utterance) in ("sensitive", "abuse", "injection"):
        out["message"] = i18n.t(i18n.MESSAGES, f"guard_{guardrails.screen(utterance)}", lang)
        return out
    low = utterance.lower()
    if _EXPIRED.search(low):
        status = "expired"
    elif _UNSURE.search(low):
        status = "unknown"
    elif _LOST.search(low):
        status = "missing"
    else:
        pol = extraction.polarity(utterance)
        status = "available" if pol is True else "missing" if pol is False else None
    out["status"], out["understood"] = status, status is not None
    out["message"] = i18n.t(i18n.DOC_STATUS, status, lang) if status else i18n.t(i18n.MESSAGES, "nothing_heard", lang)
    return out


def get_db_commit() -> None:
    from .db import get_db
    get_db().commit()
