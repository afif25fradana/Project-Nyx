from pathlib import Path
import sqlite3
import threading
import pytest
from backend.app.memory.session_db import SessionDB, sanitize_fts_query


def test_sqlite_wal_and_busy_timeout(tmp_path: Path):
    db_file = tmp_path / "sessions.db"
    db = SessionDB(db_file)

    cursor = db._conn.execute("PRAGMA journal_mode;")
    mode = cursor.fetchone()[0]
    assert mode.lower() == "wal"

    cursor = db._conn.execute("PRAGMA busy_timeout;")
    timeout = cursor.fetchone()[0]
    assert timeout == 5000

    db.close()


def test_sanitize_fts_query():
    # Normal queries
    assert sanitize_fts_query("hello world") == '"hello" "world"'
    assert sanitize_fts_query("Python 3.12") == '"Python" "3" "12"'

    # Queries with punctuation, boolean operators or wildcards
    assert sanitize_fts_query("what's *up* (today)?") == '"what" "s" "up" "today"'
    assert sanitize_fts_query("NOT OR AND -term") == '"NOT" "OR" "AND" "term"'

    # Unicode tokens
    assert sanitize_fts_query("halo kawan, apa kabar?") == '"halo" "kawan" "apa" "kabar"'

    # Empty / punctuation-only queries return None
    assert sanitize_fts_query("") is None
    assert sanitize_fts_query("   ") is None
    assert sanitize_fts_query("???") is None
    assert sanitize_fts_query("!@#$%^&*()_+-=[]{}|;':,.<>?/") is None


def test_session_crud():
    db = SessionDB(":memory:")

    # Create session
    sess = db.create_session("sess_101", title="Morning Chat")
    assert sess["session_id"] == "sess_101"
    assert sess["title"] == "Morning Chat"
    assert "created_at" in sess
    assert "updated_at" in sess

    # Get session
    retrieved = db.get_session("sess_101")
    assert retrieved is not None
    assert retrieved["session_id"] == "sess_101"
    assert retrieved["title"] == "Morning Chat"

    # Get non-existent
    assert db.get_session("non_existent") is None

    # List sessions
    db.create_session("sess_102", title="Evening Chat")
    sessions = db.list_sessions()
    assert len(sessions) == 2
    ids = [s["session_id"] for s in sessions]
    assert "sess_101" in ids
    assert "sess_102" in ids

    db.close()


def test_add_and_get_recent_turns():
    db = SessionDB(":memory:")

    # Add turn auto-creates session if not already existing
    turn1_id = db.add_turn("sess_1", "user", "Hi Nyx!", timestamp=100.0)
    assert turn1_id == 1

    turn2_id = db.add_turn("sess_1", "assistant", "Hello! How can I assist you?", timestamp=101.0)
    assert turn2_id == 2

    turn3_id = db.add_turn("sess_1", "user", "What can you do?", timestamp=102.0)
    assert turn3_id == 3

    # Session metadata automatically exists and updated
    sess = db.get_session("sess_1")
    assert sess is not None

    # Full list
    turns = db.get_recent_turns("sess_1", limit=10)
    assert len(turns) == 3
    assert turns[0]["role"] == "user"
    assert turns[0]["content"] == "Hi Nyx!"
    assert turns[0]["timestamp"] == 100.0
    assert turns[1]["role"] == "assistant"
    assert turns[1]["content"] == "Hello! How can I assist you?"
    assert turns[1]["timestamp"] == 101.0
    assert turns[2]["role"] == "user"
    assert turns[2]["content"] == "What can you do?"
    assert turns[2]["timestamp"] == 102.0

    # Limit check: with limit=2 on 3 turns, returns the 2 most recent turns in chronological order
    recent_two = db.get_recent_turns("sess_1", limit=2)
    assert len(recent_two) == 2
    assert recent_two[0]["content"] == "Hello! How can I assist you?"
    assert recent_two[1]["content"] == "What can you do?"

    db.close()


def test_search_turns_fts5():
    db = SessionDB(":memory:")

    db.add_turn("sess_1", "user", "Let's discuss project architecture and databases")
    db.add_turn("sess_1", "assistant", "We use SQLite WAL mode and Kokoro ONNX")
    db.add_turn("sess_2", "user", "What is the capital of France?")
    db.add_turn("sess_2", "assistant", "Paris is the capital of France.")

    # Search keyword matching across sessions
    results = db.search_turns("architecture")
    assert len(results) == 1
    assert results[0]["session_id"] == "sess_1"
    assert "architecture" in results[0]["content"]

    # Search keyword in specific session
    results_france = db.search_turns("capital", session_id="sess_2")
    assert len(results_france) == 2

    results_france_wrong_sess = db.search_turns("capital", session_id="sess_1")
    assert len(results_france_wrong_sess) == 0

    # Search multiple tokens
    results_multi = db.search_turns("SQLite Kokoro")
    assert len(results_multi) == 1
    assert results_multi[0]["role"] == "assistant"

    db.close()


def test_search_turns_empty_or_symbols_returns_empty_list():
    db = SessionDB(":memory:")
    db.add_turn("sess_1", "user", "Sample message")

    assert db.search_turns("") == []
    assert db.search_turns("   ") == []
    assert db.search_turns("???") == []
    assert db.search_turns("!@#$%^") == []

    db.close()


def test_write_transaction_immediate_and_lock():
    db = SessionDB(":memory:")

    # Alias check per INV 8
    assert db.execute_immediate_write == db.write_transaction

    with db.write_transaction():
        db._conn.execute("INSERT INTO sessions (session_id, title, created_at, updated_at) VALUES ('s_tx', 'Tx Title', 1.0, 1.0)")

    assert db.get_session("s_tx") is not None

    # Rollback on error
    with pytest.raises(RuntimeError):
        with db.write_transaction():
            db._conn.execute("INSERT INTO sessions (session_id, title, created_at, updated_at) VALUES ('s_err', 'Err', 2.0, 2.0)")
            raise RuntimeError("Forced abort")

    assert db.get_session("s_err") is None

    db.close()


def test_multithreaded_concurrent_writes():
    db = SessionDB(":memory:")
    errors = []

    def worker(worker_id: int):
        try:
            for i in range(10):
                db.add_turn(f"sess_{worker_id}", "user", f"Worker {worker_id} message {i}")
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(w,)) for w in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    all_sessions = db.list_sessions()
    assert len(all_sessions) == 5

    total_turns = sum(len(db.get_recent_turns(f"sess_{w}", limit=100)) for w in range(5))
    assert total_turns == 50

    db.close()


def test_session_db_pragmas_and_foreign_key_enforcement(tmp_path: Path):
    db_file = tmp_path / "sessions.db"
    db = SessionDB(db_file)

    cursor = db._conn.execute("PRAGMA foreign_keys;")
    assert cursor.fetchone()[0] == 1

    cursor = db._conn.execute("PRAGMA synchronous;")
    assert cursor.fetchone()[0] == 1

    with pytest.raises(sqlite3.IntegrityError):
        with db.write_transaction():
            db._conn.execute(
                "INSERT INTO turns (session_id, role, content, timestamp) VALUES (?, ?, ?, ?)",
                ("non_existent_session", "user", "orphan turn", 100.0),
            )

    db.close()


@pytest.mark.asyncio
async def test_session_db_async_methods(tmp_path: Path):
    db_file = tmp_path / "sessions_async.db"
    db = SessionDB(db_file)

    await db.async_create_session("sess1")
    await db.async_add_turn("sess1", "user", "hello")
    turns = await db.async_get_recent_turns("sess1")
    assert len(turns) == 1
    assert turns[0]["role"] == "user"
    assert turns[0]["content"] == "hello"

    db.close()


def test_delete_session_with_existing_turns_under_foreign_keys(tmp_path: Path):
    db_file = tmp_path / "sessions_del.db"
    session_db = SessionDB(db_file)

    session_db.create_session("sess_to_delete")
    session_db.add_turn("sess_to_delete", "user", "msg1")
    session_db.add_turn("sess_to_delete", "assistant", "resp1")

    deleted = session_db.delete_session("sess_to_delete")
    assert deleted is True
    assert session_db.get_session("sess_to_delete") is None
    assert len(session_db.get_recent_turns("sess_to_delete")) == 0

    session_db.close()

