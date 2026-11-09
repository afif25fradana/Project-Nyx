import pytest
from pathlib import Path
from backend.app.config import mask_api_key, save_env_atomic


def test_mask_api_key():
    assert mask_api_key("sk-ant-api03-12345678abcdef") == "sk-...cdef"
    assert mask_api_key("short") == "********"
    assert mask_api_key(None) is None
    assert mask_api_key("") is None


def test_mask_api_key_handles_whitespace_and_short_keys():
    assert mask_api_key("   ") is None
    assert mask_api_key("12345678") == "********"


def test_save_env_atomic_preserves_comments_and_updates_keys(tmp_path: Path):
    env_file = tmp_path / ".env"
    initial_content = (
        "# App settings\n"
        'APP_NAME="Nyx"\n'
        'DEEPSEEK_API_KEY="old-key"\n'
    )
    env_file.write_text(initial_content, encoding="utf-8")

    save_env_atomic(
        env_file,
        {
            "DEEPSEEK_API_KEY": "new-sk-123",
            "TAVILY_API_KEY": "tvly-456",
        },
    )

    updated_content = env_file.read_text(encoding="utf-8")
    assert "# App settings" in updated_content
    assert 'APP_NAME="Nyx"' in updated_content
    assert 'DEEPSEEK_API_KEY="new-sk-123"' in updated_content
    assert 'TAVILY_API_KEY="tvly-456"' in updated_content

    tmp_files = list(tmp_path.glob("*.tmp"))
    assert tmp_files == []


def test_save_env_atomic_rejects_newlines_and_control_chars(tmp_path: Path):
    with pytest.raises(ValueError):
        save_env_atomic(tmp_path / ".env", {"DEEPSEEK_API_KEY": "injected\nEVIL=1"})
    with pytest.raises(ValueError):
        save_env_atomic(tmp_path / ".env", {"DEEPSEEK_API_KEY": "injected\r\nEVIL=1"})
    with pytest.raises(ValueError):
        save_env_atomic(tmp_path / ".env", {"DEEPSEEK_API_KEY": "injected\x00null"})


def test_save_env_atomic_rejects_unpermitted_keys(tmp_path: Path):
    with pytest.raises(ValueError):
        save_env_atomic(tmp_path / ".env", {"UNAUTHORIZED_INJECTION": "value"})

