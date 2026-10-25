"""Database access for SQLite (the default) and PostgreSQL (when DATABASE_URL is set).

SQL is written once, SQLite-style ("?" placeholders, LIKE, rowid) and translated per dialect: for Postgres "?" becomes
"%s", LIKE becomes ILIKE (SQLite's LIKE ignores ASCII case), rowid becomes the identity column `seq`, and text columns
use the "C" collation so sorting matches SQLite byte for byte. Timestamps stay ISO-8601 TEXT and JSON stays TEXT.

A `Database` is one unit of work (one per request, via get_db()) on one connection. To keep round trips low on a
remote Postgres:
- reads run immediately; plain INSERT/UPDATE/DELETE (no RETURNING) are queued and sent together with the next read
  or with COMMIT in one pipeline, so a request's writes plus its COMMIT cost one round trip. A read always sees the
  request's own earlier writes, because queued writes go out ahead of it.
- query_many() sends several reads in one round trip.
- the first queued write opens a transaction; commit() sends the queue plus COMMIT. Inside `with db.transaction():`
  nested commit() calls are deferred to the end of the block, and an exception rolls the whole block back.
Request statistics (queries, round trips, milliseconds; never SQL text or values) are logged per request.
"""
import json
import logging
import re
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from flask import current_app, g

log = logging.getLogger(__name__)


def now() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime | None = None) -> str:
    return (dt or now()).isoformat(timespec="seconds")


def iso_in(hours: float) -> str:
    return iso(now() + timedelta(hours=hours))


def parse_iso(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


# ---------------------------------------------------------------- SQL dialects

_LITERAL = re.compile(r"('(?:[^']|'')*')")
_FOR_UPDATE = re.compile(r"\s+FOR UPDATE(\s+OF\s+\w+)?\s*$", re.IGNORECASE)
_CONTROL = ("BEGIN", "COMMIT", "ROLLBACK", "SAVEPOINT", "RELEASE")


@lru_cache(maxsize=2048)
def to_postgres(sql: str) -> str:
    parts = _LITERAL.split(sql.replace("%", "%%"))  # psycopg reads "%" everywhere, string literals included
    for i in range(0, len(parts), 2):  # even parts are outside string literals
        p = parts[i].replace("?", "%s")
        p = re.sub(r"\browid\b", "seq", p)
        parts[i] = re.sub(r"\bLIKE\b", "ILIKE", p)
    return "".join(parts)


@lru_cache(maxsize=2048)
def to_sqlite(sql: str) -> str:
    if sql == "BEGIN":
        return "BEGIN IMMEDIATE"  # take the write lock up front: no lock upgrade (SQLITE_BUSY) mid-transaction
    return _FOR_UPDATE.sub("", sql)


def _is_queued_write(sql: str) -> bool:
    head = sql.lstrip()[:7].upper()
    return head.startswith(("INSERT", "UPDATE", "DELETE")) and "RETURNING" not in sql.upper()


class Row(tuple):
    """A Postgres row that behaves like sqlite3.Row: r[0], r["column"], keys(), dict(r), tuple unpacking."""

    def __new__(cls, values, index):
        r = super().__new__(cls, values)
        r._index = index
        return r

    def __getitem__(self, k):
        return tuple.__getitem__(self, self._index[k] if isinstance(k, str) else k)

    def keys(self):
        return list(self._index)


def _pg_rows(cursor):
    index: dict[str, int] = {}
    for i, d in enumerate(cursor.description or ()):
        index.setdefault(d.name, i)  # duplicate names resolve to the first column, as in sqlite3.Row
    return lambda values: Row(values, index)


# ---------------------------------------------------------------- backends (one per database, shared by apps)

class Backend:
    dialect = ""

    def __init__(self, cache_check_s: float):
        self.lock = threading.Lock()
        self.cache_check_s = cache_check_s
        self.versions: dict[str, int] = {}
        self.versions_at = float("-inf")
        self.cache: dict[str, tuple[int, object]] = {}
        self.memo: dict = {}  # immutable entries (translations, prerendered audio); see reset_caches()


class SqliteBackend(Backend):
    dialect = "sqlite"

    def __init__(self, path: str, cache_check_s: float):
        super().__init__(cache_check_s)
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)

    def acquire(self):
        conn = sqlite3.connect(self.path, timeout=15, isolation_level=None, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def release(self, conn, broken: bool = False) -> None:
        conn.close()

    def close(self) -> None:
        pass


class PostgresBackend(Backend):
    """A psycopg 3 pool: at most DB_POOL_MAX connections, 10 s connect timeout, 10 s statement timeout, TLS required
    unless the URL sets sslmode, no server-side prepared statements (prepare_threshold=None) so it works through
    Supabase's Supavisor pooler. Never logs the URL."""
    dialect = "postgres"

    def __init__(self, url: str, schema: str | None, pool_max: int, cache_check_s: float):
        super().__init__(cache_check_s)
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
        from psycopg_pool import ConnectionPool
        self.schema = schema
        kwargs = {"autocommit": True, "prepare_threshold": None, "row_factory": _pg_rows, "connect_timeout": 10}
        if "sslmode" not in conninfo_to_dict(url):
            kwargs["sslmode"] = "require"
        self.errors = (psycopg.Error,)
        self.pool = ConnectionPool(url, min_size=1, max_size=pool_max, kwargs=kwargs, configure=self._configure,
                                   timeout=10, max_idle=300, name="anvaya-db", open=True)

    def _configure(self, conn) -> None:
        sql = "SET statement_timeout = '10s'"
        if self.schema:
            sql += f'; SET search_path TO "{self.schema}"'
        conn.execute(sql)

    def acquire(self):
        return self.pool.getconn()

    def release(self, conn, broken: bool = False) -> None:
        if broken:
            conn.close()
        self.pool.putconn(conn)

    def close(self) -> None:
        self.pool.close()


_backends: dict[tuple, Backend] = {}
_backends_lock = threading.Lock()


def _key(target) -> tuple:
    if isinstance(target, (str, Path)):
        return ("sqlite", str(Path(target).resolve()))
    if target.get("DATABASE_URL"):
        return ("postgres", target["DATABASE_URL"], target.get("DB_SCHEMA") or None)
    return ("sqlite", str(Path(target["DB_PATH"]).resolve()))


def backend(target) -> Backend:
    """The shared backend for an app config (DATABASE_URL set → Postgres, else the SQLite file DB_PATH) or a path."""
    key = _key(target)
    with _backends_lock:
        b = _backends.get(key)
        if b is None:
            check = 5.0 if isinstance(target, (str, Path)) else float(target.get("DB_CACHE_CHECK_S", 5.0))
            if key[0] == "postgres":
                b = PostgresBackend(key[1], key[2], int(target.get("DB_POOL_MAX", 5)), check)
            else:
                b = SqliteBackend(key[1], check)
            _backends[key] = b
        return b


def dispose(target) -> None:
    """Close the backend's pool (tests: simulate an app restart)."""
    with _backends_lock:
        b = _backends.pop(_key(target), None)
    if b:
        b.close()


def dialect(target) -> str:
    return _key(target)[0]


# ---------------------------------------------------------------- unit of work

class _Stmt:
    __slots__ = ("sql", "params", "many", "control", "rows", "rowcount", "done")

    def __init__(self, sql, params=None, many=False, control=False):
        self.sql, self.params, self.many, self.control = sql, params, many, control
        self.rows, self.rowcount, self.done = None, -1, False


class Result:
    """Rows of one statement. For a queued write, reading rowcount sends the queue first."""

    def __init__(self, db: "Database", stmt: _Stmt):
        self._db, self._stmt, self._pos = db, stmt, 0

    def _ready(self) -> _Stmt:
        if not self._stmt.done:
            self._db.flush()
        return self._stmt

    @property
    def rowcount(self) -> int:
        return self._ready().rowcount

    def fetchone(self):
        rows = self._ready().rows or []
        if self._pos >= len(rows):
            return None
        self._pos += 1
        return rows[self._pos - 1]

    def fetchall(self) -> list:
        rows = self._ready().rows or []
        out, self._pos = rows[self._pos:], len(rows)
        return out

    def __iter__(self):
        return iter(self.fetchall())


class Database:
    def __init__(self, backend_: Backend):
        self.backend = backend_
        self.dialect = backend_.dialect
        self._conn = None
        self._queue: list[_Stmt] = []
        self._open = False       # a transaction is open (its BEGIN queued or sent)
        self._server_tx = False  # ...and its BEGIN has reached the server
        self._depth = 0          # nesting of transaction() blocks
        self._savepoints = 0
        self.queries = 0         # statements sent, excluding BEGIN/COMMIT/ROLLBACK/SAVEPOINT; executemany counts once
        self.roundtrips = 0
        self.ms = 0.0

    # -- statements

    def execute(self, sql: str, params=()) -> Result:
        if _is_queued_write(sql):
            return self._queue_write(_Stmt(sql, tuple(params)))
        stmt = _Stmt(sql, tuple(params))
        self._send([stmt])
        return Result(self, stmt)

    def executemany(self, sql: str, seq) -> Result:
        seq = [tuple(p) for p in seq]
        stmt = _Stmt(sql, seq, many=True)
        if not seq:
            stmt.done, stmt.rowcount = True, 0
            return Result(self, stmt)
        return self._queue_write(stmt)

    def query_many(self, statements) -> list[Result]:
        """Run several statements in one round trip (after any queued writes); one Result per statement."""
        stmts = [_Stmt(sql, tuple(params)) for sql, params in statements]
        self._send(stmts)
        return [Result(self, s) for s in stmts]

    def flush(self) -> None:
        self._send([])

    # -- transactions

    def _queue_write(self, stmt: _Stmt) -> Result:
        if not self._open:
            self._queue.append(_Stmt("BEGIN", control=True))
            self._open = True
        last = self._queue[-1] if self._queue else None
        if last is not None and not stmt.control and not last.control and last.sql == stmt.sql:
            # The same write queued again right after itself (e.g. one INSERT per extracted fact) becomes one batched
            # statement, run in the same order. Its rowcount is the batch total.
            if not last.many:
                last.params, last.many = [last.params], True
            last.params.extend(stmt.params if stmt.many else [stmt.params])
            return Result(self, last)
        self._queue.append(stmt)
        return Result(self, stmt)

    def commit(self) -> None:
        if self._depth or not self._open:
            return
        self._queue.append(_Stmt("COMMIT", control=True))
        self._send([])

    def rollback(self) -> None:
        self._queue.clear()
        self._savepoints = 0
        if self._server_tx and self._conn is not None:
            try:
                self._send([_Stmt("ROLLBACK", control=True)])
            except Exception:  # noqa: BLE001 - the connection is gone; the server rolled back already
                self._drop_connection(broken=True)
        self._open = self._server_tx = False

    @contextmanager
    def transaction(self):
        """All statements in the block commit together; nested commit() calls wait for the end of the block."""
        outer = self._depth == 0
        if outer and not self._open:
            self._queue.append(_Stmt("BEGIN", control=True))
            self._open = True
        self._depth += 1
        try:
            yield self
        except BaseException:
            self._depth -= 1
            if outer:
                self.rollback()
            raise
        self._depth -= 1
        if outer:
            self.commit()

    @contextmanager
    def savepoint(self):
        """Inside a transaction: an exception undoes only the statements since the savepoint, then propagates."""
        self._savepoints += 1
        name = f"sp{self._savepoints}"
        self._queue_write(_Stmt(f"SAVEPOINT {name}", control=True))
        try:
            yield self
        except BaseException:
            if self._open:  # a database error already rolled the whole transaction back
                self._queue_write(_Stmt(f"ROLLBACK TO SAVEPOINT {name}", control=True))
            raise
        self._queue_write(_Stmt(f"RELEASE SAVEPOINT {name}", control=True))

    def close(self) -> None:
        if self._open:
            self.rollback()
        self._drop_connection()

    # -- transport

    def _connection(self):
        if self._conn is None:
            self._conn = self.backend.acquire()
        return self._conn

    def _drop_connection(self, broken: bool = False) -> None:
        if self._conn is not None:
            conn, self._conn = self._conn, None
            self.backend.release(conn, broken=broken)

    def _send(self, extra: list[_Stmt]) -> None:
        batch, self._queue = self._queue + extra, []
        if not batch:
            return
        ends_tx = any(s.sql in ("COMMIT", "ROLLBACK") for s in batch)
        t0 = time.perf_counter()
        try:
            if self.dialect == "postgres":
                # A dropped connection is retried once, but only when nothing in this transaction reached the server
                # before and the batch does not commit (so a retry can never apply writes twice).
                self._run_postgres(batch, retry=not self._server_tx and not ends_tx)
            else:
                self._run_sqlite(batch)
        except Exception:
            self._queue.clear()
            if batch[-1].sql != "ROLLBACK":
                self._after_error()
            raise
        finally:
            self.ms += (time.perf_counter() - t0) * 1000
            self.roundtrips += 1
            self.queries += sum(1 for s in batch if not s.control)
        if any(s.sql == "BEGIN" for s in batch):
            self._server_tx = True
        if ends_tx:
            self._open = self._server_tx = False

    def _after_error(self) -> None:
        """A failed statement aborts the transaction: roll it back so the connection is clean for the next one."""
        self._savepoints = 0
        if self._open or self._server_tx:
            self._server_tx = True
            self._open = True
            self.rollback()

    def _run_sqlite(self, batch: list[_Stmt]) -> None:
        conn = self._connection()
        for s in batch:
            sql = to_sqlite(s.sql)
            cur = conn.executemany(sql, s.params) if s.many else conn.execute(sql, s.params or ())
            s.rows = cur.fetchall() if cur.description else None
            s.rowcount, s.done = cur.rowcount, True

    def _run_postgres(self, batch: list[_Stmt], retry: bool) -> None:
        import psycopg
        for attempt in (1, 2):
            conn = self._connection()
            try:
                cursors = []
                if len(batch) == 1:
                    cursors.append(self._pg_exec(conn, batch[0]))
                else:
                    with conn.pipeline():
                        cursors = [self._pg_exec(conn, s) for s in batch]
                for s, cur in zip(batch, cursors):
                    s.rows = cur.fetchall() if cur.description else None
                    s.rowcount, s.done = cur.rowcount, True
                return
            except psycopg.OperationalError:
                if attempt == 1 and retry and (conn.broken or conn.closed):
                    log.warning("db: connection dropped; retrying once on a new connection")
                    self._drop_connection(broken=True)
                    continue
                if conn.broken or conn.closed:
                    self._drop_connection(broken=True)
                raise

    @staticmethod
    def _pg_exec(conn, s: _Stmt):
        cur = conn.cursor()
        if s.control:
            cur.execute(s.sql)
        elif s.many:
            cur.executemany(to_postgres(s.sql), s.params)
        else:
            cur.execute(to_postgres(s.sql), s.params)
        return cur


def connect(target) -> Database:
    """A unit of work outside a request (startup, CLI, tests). `target` is an app config or a SQLite file path.
    Call close() when done."""
    return Database(backend(target))


def get_db() -> Database:
    if "db" not in g:
        g.db = Database(backend(current_app.config))
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def row_to_dict(row) -> dict | None:
    return dict(row) if row is not None else None


# ---------------------------------------------------------------- versioned in-memory caches

def cached(db: Database, name: str, key: str, loader):
    """Read-mostly data (rules, catalogue facets, TTS index) kept in memory per database. It is reloaded when the
    `name` row of data_versions changes; that small table is read at most every DB_CACHE_CHECK_S seconds, so most
    requests get these values with no database round trip. Writers call bump(db, name) in the same transaction."""
    b = db.backend
    if time.monotonic() - b.versions_at >= b.cache_check_s:
        versions = {r[0]: r[1] for r in db.execute("SELECT name, version FROM data_versions")}
        with b.lock:
            b.versions, b.versions_at = versions, time.monotonic()
    version = b.versions.get(name, 0)
    hit = b.cache.get(f"{name}:{key}")
    if hit and hit[0] == version:
        return hit[1]
    value = loader()
    with b.lock:
        b.cache[f"{name}:{key}"] = (version, value)
    return value


def bump(db: Database, name: str) -> None:
    db.execute("UPDATE data_versions SET version = version + 1 WHERE name=?", (name,))
    b = db.backend
    with b.lock:
        b.cache = {k: v for k, v in b.cache.items() if not k.startswith(f"{name}:")}
        b.versions_at = float("-inf")


def reset_caches(db: Database) -> None:
    """Tests that change tables directly: forget every in-memory copy."""
    b = db.backend
    with b.lock:
        b.cache.clear()
        b.memo.clear()
        b.versions_at = float("-inf")
