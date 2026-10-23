"""Versioned extraction prompt (prompts/extract_v1.md) and the messages built from it."""
import json
from functools import lru_cache
from pathlib import Path

PROMPT_FILE = Path(__file__).resolve().parent / "prompts" / "extract_v1.md"


@lru_cache(maxsize=1)
def _load() -> tuple[str, str]:
    head, _, body = PROMPT_FILE.read_text(encoding="utf-8").partition("\n---\n")
    version = head.removeprefix("version:").strip()
    if not version or not body.strip():
        raise RuntimeError(f"{PROMPT_FILE.name} must start with 'version: …' and a '---' line")
    return version, body.strip()


def version() -> str:
    return _load()[0]


def build(utterance: str, translation: str | None) -> list[dict]:
    data = {"original_message": utterance}
    if translation:
        data["english_translation"] = translation
    return [{"role": "system", "content": _load()[1]},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)}]


def retry(messages: list[dict], bad_output: str, error: str) -> list[dict]:
    """The single retry after invalid output: the previous answer plus the validation error."""
    return messages + [
        {"role": "assistant", "content": bad_output[:2000]},
        {"role": "user", "content": f"That reply was invalid: {error}. Reply again with only the JSON object "
                                    '{"facts": [{"attribute": ..., "value": ..., "evidence": ...}]}.'},
    ]
