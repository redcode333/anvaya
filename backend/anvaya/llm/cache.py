"""DB cache of validated LLM results: repeated utterances (demo phrases, tests, eval) cost no provider call."""
import hashlib
import json

from ..db import dumps, get_db, iso


def key(p: dict, messages: list[dict]) -> str:
    prompt = json.dumps(messages, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(f"{p['name']}\n{p['model']}\n{prompt}".encode()).hexdigest()


def get(cache_key: str) -> list[dict] | None:
    row = get_db().execute("SELECT response_json FROM llm_cache WHERE cache_key=?", (cache_key,)).fetchone()
    return json.loads(row[0]) if row else None


def put(cache_key: str, p: dict, prompt_version: str, items: list[dict]) -> None:
    db = get_db()
    db.execute("INSERT OR REPLACE INTO llm_cache(cache_key, provider, model, prompt_version, response_json, created_at)"
               " VALUES (?,?,?,?,?,?)", (cache_key, p["name"], p["model"], prompt_version, dumps(items), iso()))
    db.commit()
