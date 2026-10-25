"""Supabase Storage, server-side only (private bucket SUPABASE_STORAGE_BUCKET, default "documents").

The browser never talks to Storage. Uploads and views go through this backend, which uses SUPABASE_SECRET_KEY in the
`apikey` header (never logged, never returned). Upload and view URLs handed to the browser are this backend's own
signed, short-lived links (see documents.py): Supabase's signed upload URLs live for a fixed 2 hours, longer than the
5 minutes allowed here.

Tests replace the four functions below with an in-memory fake.
"""
import logging

import requests
from flask import current_app

from .common import ApiError

log = logging.getLogger(__name__)


def _base(cfg=None) -> tuple[str, dict, str]:
    cfg = cfg or current_app.config
    if not (cfg["SUPABASE_URL"] and cfg["SUPABASE_SECRET_KEY"]):
        raise ApiError("STORAGE_NOT_CONFIGURED", "Document upload is not available on this server.", 503)
    headers = {"apikey": cfg["SUPABASE_SECRET_KEY"], "User-Agent": "anvaya-backend"}
    return f"{cfg['SUPABASE_URL']}/storage/v1", headers, cfg["STORAGE_BUCKET"]


def _fail(op: str, e) -> ApiError:
    log.warning("storage: %s failed (%s)", op, e if isinstance(e, int) else type(e).__name__)  # status / class only
    return ApiError("STORAGE_UNAVAILABLE", "The document store is not reachable right now; try again.", 502)


def upload(path: str, data: bytes, content_type: str, cfg=None) -> None:
    url, h, bucket = _base(cfg)
    try:
        r = requests.post(f"{url}/object/{bucket}/{path}", data=data, timeout=30,
                          headers={**h, "Content-Type": content_type, "x-upsert": "false", "Cache-Control": "no-store"})
    except requests.RequestException as e:
        raise _fail("upload", e)
    if r.status_code != 200:
        raise _fail("upload", r.status_code)


def probe(path: str, cfg=None) -> tuple[int, bytes] | None:
    """(total size, first 8 bytes) of a stored object, read back with one ranged GET; None when it does not exist."""
    url, h, bucket = _base(cfg)
    try:
        r = requests.get(f"{url}/object/{bucket}/{path}", headers={**h, "Range": "bytes=0-7"}, timeout=15)
    except requests.RequestException as e:
        raise _fail("probe", e)
    if r.status_code in (400, 404):
        return None
    if r.status_code not in (200, 206):
        raise _fail("probe", r.status_code)
    total = r.headers.get("Content-Range", "").rpartition("/")[2]
    return (int(total) if total.isdigit() else len(r.content)), r.content[:8]


def download(path: str, cfg=None) -> bytes:
    url, h, bucket = _base(cfg)
    try:
        r = requests.get(f"{url}/object/{bucket}/{path}", headers=h, timeout=30)
    except requests.RequestException as e:
        raise _fail("download", e)
    if r.status_code in (400, 404):
        raise ApiError("DOCUMENT_NOT_FOUND", "This document is no longer stored.", 404)
    if r.status_code != 200:
        raise _fail("download", r.status_code)
    return r.content


def delete(paths: list[str], cfg=None) -> None:
    """Delete objects (missing ones are fine). Raises ApiError when the store cannot be reached."""
    if not paths:
        return
    url, h, bucket = _base(cfg)
    for i in range(0, len(paths), 1000):
        try:
            r = requests.delete(f"{url}/object/{bucket}", json={"prefixes": paths[i:i + 1000]}, headers=h, timeout=30)
        except requests.RequestException as e:
            raise _fail("delete", e)
        if r.status_code != 200:
            raise _fail("delete", r.status_code)
