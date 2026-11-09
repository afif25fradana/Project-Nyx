import asyncio
from contextlib import contextmanager
from pathlib import Path
import re
import sqlite3
import threading
import time
from typing import Any


def sanitize_fts_query(query: str) -> str | None:
    """Extract alphanumeric unicode tokens and quote each to avoid FTS5 syntax errors (INV 8)."""
    tokens = [t.strip("_") for t in re.findall(r"\w+", query, flags=re.UNICODE)]
    tokens = [t for t in tokens if t]
    if not tokens:
        return None
    return " ".join(f'"{token}"' for token in tokens)


class SessionDB:
    """SQLite WAL session database with FTS5 search and BEGIN IMMEDIATE write transactions (INV 8)."""

    def __init__(self, db_path: Path | str = ":memory:") -> None:
        self.db_path = str(db_path)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.RLock()
        self._conn = sqlite3.connect(
            self.db_path,
            isolation_level=None,
            check_same_thread=False,
        )
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode = WAL;")
            self._conn.execute("PRAGMA busy_timeout = 5000;")
            self._conn.execute("PRAGMA synchronous = NORMAL;")
            self._conn.execute("PRAGMA foreign_keys = ON;")

            with self.write_transaction():
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS sessions (
                        session_id TEXT PRIMARY KEY,
                        title TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    );
                """)
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS turns (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        role TEXT NOT NULL,
                        content TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        FOREIGN KEY (session_id) REFERENCES sessions(session_id)
                    );
                """)
                self._conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_turns_session_time 
                    ON turns(session_id, timestamp);
                """)
                self._conn.execute("""
                    CREATE VIRTUAL TABLE IF NOT EXISTS turns_fts USING fts5(
                        content,
                        content='turns',
                        content_rowid='id'
                    );
                """)
                self._conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS turns_ai AFTER INSERT ON turns BEGIN
                        INSERT INTO turns_fts(rowid, content) VALUES (new.id, new.content);
                    END;
                """)
                self._conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS turns_ad AFTER DELETE ON turns BEGIN
                        INSERT INTO turns_fts(turns_fts, rowid, content) VALUES ('delete', old.id, old.content);
                    END;
                """)
                self._conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS turns_au AFTER UPDATE ON turns BEGIN
                        INSERT INTO turns_fts(turns_fts, rowid, content) VALUES ('delete', old.id, old.content);
                        INSERT INTO turns_fts(rowid, content) VALUES (new.id, new.content);
                    END;
                """)

    @contextmanager
    def write_transaction(self):
        """Context manager executing write operations under BEGIN IMMEDIATE."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
                self._conn.execute("COMMIT")
            except Exception:
                if self._conn.in_transaction:
                    try:
                        self._conn.execute("ROLLBACK")
                    except sqlite3.Error:
                        pass
                raise

    # Invariant 8 explicit naming alias
    execute_immediate_write = write_transaction

    def create_session(self, session_id: str, title: str = "New Session") -> dict[str, Any]:
        """Create a new conversation session record."""
        now = time.time()
        with self.write_transaction():
            self._conn.execute(
                "INSERT OR REPLACE INTO sessions (session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, title, now, now),
            )
        return {"session_id": session_id, "title": title, "created_at": now, "updated_at": now}

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Fetch session metadata by ID."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT session_id, title, created_at, updated_at FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def list_sessions(self) -> list[dict[str, Any]]:
        """List all conversation sessions ordered by updated_at descending."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT session_id, title, created_at, updated_at FROM sessions ORDER BY updated_at DESC"
            )
            return [dict(r) for r in cur.fetchall()]

    def add_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        timestamp: float | None = None,
    ) -> int:
        """Add a conversation turn; auto-creates session and updates updated_at."""
        ts = time.time() if timestamp is None else float(timestamp)
        with self.write_transaction():
            self._conn.execute(
                "INSERT OR IGNORE INTO sessions (session_id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
                (session_id, "New Session", ts, ts),
            )
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (ts, session_id),
            )
            cur = self._conn.execute(
                "INSERT INTO turns (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                (session_id, role, content, ts),
            )
            return int(cur.lastrowid)

    def get_recent_turns(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Retrieve recent turns for a session in chronological order."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, session_id, role, content, timestamp FROM turns WHERE session_id = ? ORDER BY timestamp DESC, id DESC LIMIT ?",
                (session_id, limit),
            )
            return [dict(r) for r in reversed(cur.fetchall())]

    def search_turns(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Full-text search on conversational turns with query sanitization (INV 8)."""
        sanitized = sanitize_fts_query(query)
        if not sanitized:
            return []

        with self._lock:
            if session_id:
                sql = """
                    SELECT t.id, t.session_id, t.role, t.content, t.timestamp
                    FROM turns t
                    JOIN turns_fts ON t.id = turns_fts.rowid
                    WHERE turns_fts MATCH ? AND t.session_id = ?
                    ORDER BY t.timestamp DESC
                    LIMIT ?
                """
                cur = self._conn.execute(sql, (sanitized, session_id, limit))
            else:
                sql = """
                    SELECT t.id, t.session_id, t.role, t.content, t.timestamp
                    FROM turns t
                    JOIN turns_fts ON t.id = turns_fts.rowid
                    WHERE turns_fts MATCH ?
                    ORDER BY t.timestamp DESC
                    LIMIT ?
                """
                cur = self._conn.execute(sql, (sanitized, limit))

            return [dict(r) for r in cur.fetchall()]

    def delete_session(self, session_id: str) -> bool:
        """Delete a conversation session and all its associated turns."""
        with self.write_transaction():
            self._conn.execute("DELETE FROM turns WHERE session_id = ?", (session_id,))
            cur = self._conn.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
            return cur.rowcount > 0

    async def async_create_session(self, session_id: str, title: str = "New Session") -> dict[str, Any]:
        """Asynchronously create a new conversation session record."""
        return await asyncio.to_thread(self.create_session, session_id, title)

    async def async_add_turn(
        self,
        session_id: str,
        role: str,
        content: str,
        timestamp: float | None = None,
    ) -> int:
        """Asynchronously add a conversation turn."""
        return await asyncio.to_thread(self.add_turn, session_id, role, content, timestamp)

    async def async_get_recent_turns(self, session_id: str, limit: int = 50) -> list[dict[str, Any]]:
        """Asynchronously retrieve recent turns for a session in chronological order."""
        return await asyncio.to_thread(self.get_recent_turns, session_id, limit)

    async def async_search_turns(
        self,
        query: str,
        session_id: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        """Asynchronously full-text search on conversational turns."""
        return await asyncio.to_thread(self.search_turns, query, session_id, limit)

    async def async_delete_session(self, session_id: str) -> bool:
        """Asynchronously delete a session and its associated turns."""
        return await asyncio.to_thread(self.delete_session, session_id)

    def close(self) -> None:
        """Close SQLite database connection."""
        with self._lock:
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
