import asyncio
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import threading
import time
from typing import Any


def validate_int(arg_name: str, val: Any) -> int:
    """Enforce strict integer validation rejecting booleans and coerced types (INV 11)."""
    if type(val) is not int or isinstance(val, bool):
        raise ValueError(f"Argument '{arg_name}' must be an int, got {type(val).__name__}: {val}")
    return val


class TodoStore:
    """SQLite WAL task store with thread-safe BEGIN IMMEDIATE transactions (INV 8 & INV 11)."""

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

            with self.write_transaction():
                self._conn.execute("""
                    CREATE TABLE IF NOT EXISTS todos (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        title TEXT NOT NULL,
                        category TEXT NOT NULL DEFAULT 'general',
                        status TEXT NOT NULL DEFAULT 'pending',
                        completed INTEGER NOT NULL DEFAULT 0,
                        created_at REAL NOT NULL,
                        completed_at REAL
                    );
                """)
                self._conn.execute("""
                    CREATE INDEX IF NOT EXISTS idx_todos_status 
                    ON todos(status);
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

    execute_immediate_write = write_transaction

    def add_todo(self, title: str, category: str = "general") -> dict[str, Any]:
        """Add a new task with pending status."""
        now = time.time()
        with self.write_transaction():
            cur = self._conn.execute(
                """
                INSERT INTO todos (title, category, status, completed, created_at, completed_at)
                VALUES (?, ?, 'pending', 0, ?, NULL)
                """,
                (title, category, now),
            )
            todo_id = cur.lastrowid

        return {
            "id": todo_id,
            "title": title,
            "category": category,
            "status": "pending",
            "completed": 0,
            "created_at": now,
            "completed_at": None,
        }

    def complete_todo(self, todo_id: int) -> dict[str, Any]:
        """Mark a task as completed with strict integer validation (INV 11)."""
        valid_id = validate_int("todo_id", todo_id)
        now = time.time()
        with self.write_transaction():
            cur = self._conn.execute(
                """
                UPDATE todos
                SET status = 'completed', completed = 1, completed_at = ?
                WHERE id = ?
                """,
                (now, valid_id),
            )
            if cur.rowcount == 0:
                raise KeyError(f"Todo with id {valid_id} not found")

        todo = self.get_todo(valid_id)
        if todo is None:
            raise KeyError(f"Todo with id {valid_id} not found")
        return todo

    def list_todos(self, status: str = "pending") -> list[dict[str, Any]]:
        """List tasks filtered by status ('pending', 'completed', 'all')."""
        with self._lock:
            if status == "all":
                cur = self._conn.execute(
                    "SELECT id, title, category, status, completed, created_at, completed_at FROM todos ORDER BY created_at DESC"
                )
            else:
                cur = self._conn.execute(
                    "SELECT id, title, category, status, completed, created_at, completed_at FROM todos WHERE status = ? ORDER BY created_at DESC",
                    (status,),
                )
            return [dict(r) for r in cur.fetchall()]

    def get_todo(self, todo_id: int) -> dict[str, Any] | None:
        """Fetch a single task record by ID with strict type checking."""
        valid_id = validate_int("todo_id", todo_id)
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, title, category, status, completed, created_at, completed_at FROM todos WHERE id = ?",
                (valid_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def delete_todo(self, todo_id: int) -> bool:
        """Delete a task record by ID with strict type checking."""
        valid_id = validate_int("todo_id", todo_id)
        with self.write_transaction():
            cur = self._conn.execute("DELETE FROM todos WHERE id = ?", (valid_id,))
            return cur.rowcount > 0

    async def async_add_todo(self, title: str, category: str = "general") -> dict[str, Any]:
        """Asynchronously add a new task."""
        return await asyncio.to_thread(self.add_todo, title, category)

    async def async_complete_todo(self, todo_id: int) -> dict[str, Any]:
        """Asynchronously mark a task as completed."""
        return await asyncio.to_thread(self.complete_todo, todo_id)

    async def async_list_todos(self, status: str = "pending") -> list[dict[str, Any]]:
        """Asynchronously list tasks filtered by status."""
        return await asyncio.to_thread(self.list_todos, status)

    async def async_delete_todo(self, todo_id: int) -> bool:
        """Asynchronously delete a task record by ID."""
        return await asyncio.to_thread(self.delete_todo, todo_id)

    def close(self) -> None:
        """Close SQLite database connection."""
        with self._lock:
            self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
