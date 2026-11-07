"""Database access with explicit transactions.

Design notes
------------
* One connection per thread. Writes MUST happen inside ``transaction()``;
  a write outside a transaction raises immediately (catches bugs in tests).
* The outermost transaction is ``BEGIN IMMEDIATE`` (SQLite) which takes the
  write lock up-front, so read-check-write sequences are serialised. On
  PostgreSQL the equivalent is ``SELECT ... FOR UPDATE`` (see ``for_update``)
  plus compare-and-swap ``UPDATE ... WHERE version = ?`` guards, which the
  services use on both backends.
* Nested ``transaction()`` calls become SAVEPOINTs, so use-cases compose
  (e.g. OrderService -> EscrowService -> LedgerService) inside one atomic unit.
* SQL is written with ``?`` placeholders; other dialects translate them.
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Sequence

_READ_PREFIXES = ("SELECT", "WITH", "PRAGMA", "EXPLAIN")
_SQL_DIR = Path(__file__).parent


@dataclass
class ExecResult:
    rowcount: int
    lastrowid: int | None


class Database:
    dialect = "sqlite"
    for_update = ""  # SQLite serialises writers; PG uses " FOR UPDATE"

    def __init__(self, path: str, busy_timeout_ms: int = 15000):
        self.path = path
        self.busy_timeout_ms = busy_timeout_ms
        self._local = threading.local()
        # Every connection ever opened, across every thread, so close() can close all of them -
        # not just the calling thread's. Concurrency tests open connections from worker threads
        # that finish and are never individually torn down; on Windows (unlike POSIX), a file
        # cannot be deleted while any connection to it is still open, so leaving those stray
        # connections open causes the temp-file cleanup in tests to fail with WinError 32.
        self._all_conns: list[sqlite3.Connection] = []
        self._conns_lock = threading.Lock()

    # -- connection management ------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            # check_same_thread=False: each thread still only ever touches its own connection
            # (one per thread, via thread-local storage) - this flag exists only so that
            # close_all(), called from a single thread (e.g. a test's tearDown), may close
            # connections that worker threads opened and have since exited without closing.
            conn = sqlite3.connect(self.path, isolation_level=None, timeout=self.busy_timeout_ms / 1000,
                                   check_same_thread=False)
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(f"PRAGMA busy_timeout={self.busy_timeout_ms}")
            if self.path != ":memory:":
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
            self._local.depth = 0
            with self._conns_lock:
                self._all_conns.append(conn)
        return conn

    @property
    def in_transaction(self) -> bool:
        self._conn()
        return self._local.depth > 0

    def close(self) -> None:
        """Closes every connection this Database ever opened, in any thread. Safe to call more
        than once, and safe to call even if some connections were opened by threads that have
        since exited."""
        with self._conns_lock:
            conns, self._all_conns = self._all_conns, []
        for conn in conns:
            try:
                conn.close()
            except sqlite3.Error:
                pass
        self._local.conn = None

    # -- transactions ---------------------------------------------------------
    @contextmanager
    def transaction(self) -> Iterator[None]:
        conn = self._conn()
        depth = self._local.depth
        if depth == 0:
            conn.execute("BEGIN IMMEDIATE")
            self._local.depth = 1
            try:
                yield
                conn.execute("COMMIT")
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            finally:
                self._local.depth = 0
        else:
            sp = f"sp{depth}"
            conn.execute(f"SAVEPOINT {sp}")
            self._local.depth = depth + 1
            try:
                yield
                conn.execute(f"RELEASE {sp}")
            except BaseException:
                conn.execute(f"ROLLBACK TO {sp}")
                conn.execute(f"RELEASE {sp}")
                raise
            finally:
                self._local.depth = depth

    # -- query helpers --------------------------------------------------------
    def execute(self, sql: str, params: Sequence[Any] = ()) -> ExecResult:
        conn = self._conn()
        if self._local.depth == 0 and not sql.lstrip().upper().startswith(_READ_PREFIXES):
            raise RuntimeError("write outside transaction: " + sql.strip()[:60])
        cur = conn.execute(sql, tuple(params))
        return ExecResult(cur.rowcount, cur.lastrowid)

    def one(self, sql: str, params: Sequence[Any] = ()) -> dict | None:
        row = self._conn().execute(sql, tuple(params)).fetchone()
        return dict(row) if row is not None else None

    def all(self, sql: str, params: Sequence[Any] = ()) -> list[dict]:
        return [dict(r) for r in self._conn().execute(sql, tuple(params)).fetchall()]

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = self._conn().execute(sql, tuple(params)).fetchone()
        return None if row is None else row[0]

    # -- schema ---------------------------------------------------------------
    def init_schema(self) -> None:
        conn = self._conn()
        ddl = (_SQL_DIR / "schema.sql").read_text().replace(
            "{{AUTO_PK}}", "INTEGER PRIMARY KEY AUTOINCREMENT"
        )
        conn.executescript(ddl)
        conn.executescript((_SQL_DIR / "triggers_sqlite.sql").read_text())
        self._create_fts(conn)

    @staticmethod
    def _create_fts(conn: sqlite3.Connection) -> None:
        conn.executescript(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS listings_fts USING fts5(
                title, description, content='listings', content_rowid='rowid', tokenize='unicode61');
            CREATE TRIGGER IF NOT EXISTS listings_ai AFTER INSERT ON listings BEGIN
              INSERT INTO listings_fts(rowid, title, description) VALUES (new.rowid, new.title, new.description);
            END;
            CREATE TRIGGER IF NOT EXISTS listings_au AFTER UPDATE OF title, description ON listings BEGIN
              INSERT INTO listings_fts(listings_fts, rowid, title, description) VALUES('delete', old.rowid, old.title, old.description);
              INSERT INTO listings_fts(rowid, title, description) VALUES (new.rowid, new.title, new.description);
            END;
            """
        )

    def text_search_clause(self, column_alias: str = "l") -> str:
        """SQL predicate matching listings against a full-text query (param: query)."""
        return f"{column_alias}.rowid IN (SELECT rowid FROM listings_fts WHERE listings_fts MATCH ?)"


def fts_query(text: str) -> str:
    """Sanitise free text into a safe FTS5 prefix query (no operator injection)."""
    tokens = ["".join(ch for ch in tok if ch.isalnum()) for tok in text.split()]
    tokens = [t for t in tokens if t]
    return " ".join(f'"{t}"*' for t in tokens[:8])
