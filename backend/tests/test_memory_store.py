import os
from pathlib import Path
import pytest
from backend.app.memory.store import MarkdownStore


def test_atomic_write_and_read(tmp_path: Path):
    store = MarkdownStore(base_dir=tmp_path)
    target = tmp_path / "test_doc.md"
    content = "# Test Document\n\nThis is persistent markdown content."

    store.write_text(target, content)

    # Verify content read back
    assert store.read_text(target) == content

    # Verify no orphaned .tmp files remain
    tmp_files = list(tmp_path.glob("*.tmp"))
    assert len(tmp_files) == 0


def test_read_nonexistent_returns_default(tmp_path: Path):
    store = MarkdownStore(base_dir=tmp_path)
    target = tmp_path / "does_not_exist.md"

    assert store.read_text(target) == ""
    assert store.read_text(target, default="default value") == "default value"


def test_atomic_write_retry_on_transient_lock(tmp_path: Path, monkeypatch):
    store = MarkdownStore(base_dir=tmp_path)
    target = tmp_path / "transient.md"
    content = "transient lock test"

    real_replace = os.replace
    attempts = 0
    delays_called = []

    def mock_replace(src, dst):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError("WinError 32: File locked by external process")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", mock_replace)
    monkeypatch.setattr("time.sleep", lambda s: delays_called.append(s))

    store.write_text(target, content)

    assert attempts == 3
    assert len(delays_called) == 2  # slept before attempt 2 and attempt 3
    assert delays_called == [0.05, 0.1]
    assert store.read_text(target) == content
    assert len(list(tmp_path.glob("*.tmp"))) == 0


def test_atomic_write_persistent_failure_raises_and_cleans_tmp(tmp_path: Path, monkeypatch):
    store = MarkdownStore(base_dir=tmp_path)
    target = tmp_path / "persistent_fail.md"
    content = "this should fail"

    delays_called = []

    def mock_failing_replace(src, dst):
        raise PermissionError("WinError 32: Permanently locked")

    monkeypatch.setattr(os, "replace", mock_failing_replace)
    monkeypatch.setattr("time.sleep", lambda s: delays_called.append(s))

    with pytest.raises(PermissionError, match="Permanently locked"):
        store.write_text(target, content)

    # 1 initial + 5 backoffs = 6 total attempts, 5 sleeps
    assert len(delays_called) == 5
    assert delays_called == [0.05, 0.1, 0.2, 0.4, 0.8]

    # Crucial INV 10 requirement: zero orphaned .tmp files left behind
    assert len(list(tmp_path.glob("*.tmp"))) == 0


@pytest.mark.asyncio
async def test_async_write_text(tmp_path: Path):
    store = MarkdownStore(base_dir=tmp_path)
    target = tmp_path / "async_doc.md"
    content = "async write content"

    await store.write_text_async(target, content)

    assert store.read_text(target) == content
    assert len(list(tmp_path.glob("*.tmp"))) == 0


def test_user_and_memory_profile_helpers(tmp_path: Path):
    store = MarkdownStore(base_dir=tmp_path)

    store.write_user_profile("User: Alice\nPreference: Calm voice")
    assert store.read_user_profile() == "User: Alice\nPreference: Calm voice"
    assert (tmp_path / "USER.md").read_text(encoding="utf-8") == "User: Alice\nPreference: Calm voice"

    store.write_memory("Alice prefers tea over coffee.")
    assert store.read_memory() == "Alice prefers tea over coffee."
    assert (tmp_path / "MEMORY.md").read_text(encoding="utf-8") == "Alice prefers tea over coffee."


@pytest.mark.asyncio
async def test_markdown_store_read_text_async_and_retry(tmp_path: Path, monkeypatch):
    store = MarkdownStore(base_dir=tmp_path)
    target = tmp_path / "async_retry_doc.md"

    # Non-existent file returns default fallback
    val = await store.read_text_async(target, default="fallback")
    assert val == "fallback"

    # Normal write and async read
    store.write_text(target, "persisted markdown")
    content = await store.read_text_async(target, default="fallback")
    assert content == "persisted markdown"

    # Transient lock retry test on read
    real_open = open
    attempts = 0

    def mock_open(file, *args, **kwargs):
        nonlocal attempts
        if str(file) == str(target):
            attempts += 1
            if attempts < 3:
                raise PermissionError("WinError 32: File locked by external process")
        return real_open(file, *args, **kwargs)

    monkeypatch.setattr("builtins.open", mock_open)
    content_retried = await store.read_text_async(target, default="fallback")
    assert content_retried == "persisted markdown"
    assert attempts == 3

