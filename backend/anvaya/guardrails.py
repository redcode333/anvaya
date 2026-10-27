"""Conversation guardrails: deterministic checks on what a citizen types or says, run before any extraction or LLM call.

Nothing here calls a model, so it cannot be argued out of its rules. Each check returns a kind; the reply text lives in
i18n.MESSAGES under ``guard_<kind>`` (English, Hindi, Telugu). Blocked turns are never extracted, never sent to an LLM and
are stored as a placeholder, not as typed.

  abuse      profanity, sexual or hateful words (clear terms always; soft ones only when no detail was found)
  injection  attempts to override the assistant's instructions or read its prompt
  sensitive  Aadhaar / card / PAN numbers, OTPs, passwords: they must never be typed here
  smalltalk  hello / thanks / "what can you do" (answered, then the pending question is asked again)
  offtopic   a question that is not about schemes or the household (answered with what this assistant is for)
"""
from __future__ import annotations

import re
import unicodedata

# Always blocked. Latin (English and romanised Hindi/Telugu) plus Devanagari and Telugu script.
_STRONG = (
    r"fuck\w*|motherfuck\w*|shit\w*|bitch\w*|bastard|asshole|dickhead|pussy|cunt|whore|slut|porn\w*|nudes?|blowjob"
    r"|chutiy\w*|madarchod|behenchod|bhenchod|bhosd\w*|gaand\w*|gandu|randi|harami\w*|lund|lauda|kamina|dengu\w*|denga\w*"
    r"|lanja\w*|pukku|modda|sulli"
    r"|चूतिया|मादरचोद|बहनचोद|भोसड़ी\w*|रंडी|हरामी|गांडू|गांड|लंड|कमीना"
    r"|దెంగు\w*|లంజ\w*|పూకు|సుల్లి"
)
# Ambiguous words: "sex" is also a form field ("sex: female"), so these count only when no detail was understood.
_SOFT = r"sex\w*|krogi|karogi|nangi|సెక్స్|सेक्स|नंगी"
_INJECTION = (
    r"ignore\s+(all\s+|any\s+|the\s+|your\s+)*(previous\s+|prior\s+|above\s+|earlier\s+)*(instructions?|rules?|prompts?)"
    r"|disregard\s+(all\s+|the\s+|your\s+)*(previous\s+|prior\s+|above\s+)*(instructions?|rules?)"
    r"|(system|developer|hidden)\s+prompt|reveal\s+(your|the)\s+(prompt|instructions|rules)"
    r"|you\s+are\s+now\s+|pretend\s+(to\s+be|you\s+are)|act\s+as\s+(a|an|if)\s+|jailbreak|developer\s+mode|\bdan\s+mode"
    r"|forget\s+(everything|all|your)\s*(instructions|rules)?|override\s+(the\s+)?(rules|eligibility|safety)"
    r"|mark\s+me\s+(as\s+)?eligible|सारे\s+निर्देश\s+भूल|पिछले\s+निर्देश"
)
_SENSITIVE_WORDS = (r"\b(otp|cvv|password|passwd|pan\s*(number|no)|card\s*number|"
                    r"aadhaar\s*(number|no)|aadhar\s*(number|no))\b|पासवर्ड|ओटीपी")

_GREETING = (r"^\s*(hi+|hello+|hey+|namaste|namaskar|namaskaram|hola|good\s+(morning|afternoon|evening)"
             r"|नमस्ते|नमस्कार|హలో|నమస్తే|నమస్కారం)\W*$")
_THANKS = r"^\s*(thanks?( you)?|thank u|thx|ok(ay)?|okk+|shukriya|dhanyavad|धन्यवाद|शुक्रिया|ధన్యవాదాలు)\W*$"
_HELP = (r"\b(help|what can you do|who are you|what are you|how does this work|how do i use|kya kar sakte|aap kaun)\b"
         r"|मदद|आप कौन|సహాయం")
_QUESTION = r"(\?|^\s*(what|why|how|when|where|who|which|can you|could you|tell me about|explain|write|give me|show me)\b)"

_rx = {k: re.compile(v, re.I | re.U) for k, v in {
    "strong": rf"(?<!\w)(?:{_STRONG})(?!\w)", "soft": rf"(?<!\w)(?:{_SOFT})(?!\w)", "inj": _INJECTION,
    "words": _SENSITIVE_WORDS, "greet": _GREETING, "thanks": _THANKS, "help": _HELP, "q": _QUESTION}.items()}

_LOOKALIKE = str.maketrans({"*": "u", "@": "a", "$": "s", "0": "o", "3": "e", "!": "i"})


def _norm(text: str) -> str:
    """Lower-case, drop zero-width characters, and fold look-alike spellings (f*ck, sh!t) inside letter runs."""
    t = unicodedata.normalize("NFKC", text).replace("​", "").replace("‍", "").lower()
    return re.sub(r"(?<=[a-z])[*@$03!](?=[a-z])", lambda m: m.group().translate(_LOOKALIKE), t)


def _number_run(text: str) -> bool:
    """A 12-digit Aadhaar-style number (spaces or dashes allowed), a 13-19 digit card number, or a PAN."""
    compact = re.sub(r"(?<=\d)[\s-]+(?=\d)", "", text)
    return bool(re.search(r"(?<!\d)\d{12}(?!\d)", compact) or re.search(r"(?<!\d)\d{13,19}(?!\d)", compact)
                or re.search(r"\b[a-z]{5}\d{4}[a-z]\b", text, re.I))


def screen(utterance: str) -> str | None:
    """Kind of block for a turn that must not be processed at all, else None."""
    t = _norm(utterance)
    if _rx["inj"].search(t):
        return "injection"
    if _number_run(utterance) or _rx["words"].search(t):
        return "sensitive"
    if _rx["strong"].search(t):
        return "abuse"
    return None


def no_details(utterance: str) -> str:
    """Kind of reply for a turn from which no household detail was understood."""
    t = _norm(utterance)
    if _rx["soft"].search(t):
        return "abuse"
    if _rx["greet"].match(t) or _rx["thanks"].match(t) or _rx["help"].search(t):
        return "smalltalk"
    if _rx["q"].search(t) and len(t.split()) >= 3:
        return "offtopic"
    return "nothing_heard"


def placeholder(kind: str) -> str:
    """What is stored in the turn log instead of a blocked utterance."""
    return f"[withheld: {kind}]"
