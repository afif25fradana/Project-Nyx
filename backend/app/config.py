import os
from pathlib import Path
import re
import time
import dotenv

ALLOWED_ENV_KEYS: frozenset[str] = frozenset(
    {"DEEPSEEK_API_KEY", "TAVILY_API_KEY", "HOST", "PORT", "ENVIRONMENT", "CHARACTER_CONFIG_PATH"}
)


def load_env(env_path: Path | str | None = None) -> None:
    """Load environment variables from .env file without overriding existing variables."""
    dotenv.load_dotenv(dotenv_path=env_path, override=False)


def mask_api_key(key: str | None) -> str | None:
    """Mask an API key for safe display and logging."""
    if not key or not key.strip():
        return None
    stripped = key.strip()
    if len(stripped) <= 8:
        return "********"
    return f"{stripped[:3]}...{stripped[-4:]}"


def save_env_atomic(env_path: Path | str, updates: dict[str, str]) -> None:
    """Atomically write key-value pairs to env_path, preserving existing lines and comments."""
    for k, v in updates.items():
        if k not in ALLOWED_ENV_KEYS:
            raise ValueError(f"Unpermitted environment variable key: {k}")
        if re.search(r"[\r\n\x00-\x1f\x7f]", str(v)):
            raise ValueError(f"Value for {k} contains prohibited newline or control characters")

    path = Path(env_path)
    if path.parent:
        path.parent.mkdir(parents=True, exist_ok=True)

    remaining_updates = dict(updates)
    new_lines: list[str] = []

    if path.exists():
        raw_lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        for line in raw_lines:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue
            if "=" in line:
                key = line.split("=", 1)[0].strip()
                if key in remaining_updates:
                    val = remaining_updates.pop(key)
                    val_str = str(val)
                    if (val_str.startswith('"') and val_str.endswith('"')) or (
                        val_str.startswith("'") and val_str.endswith("'")
                    ):
                        val_str = val_str[1:-1]
                    new_lines.append(f'{key}="{val_str}"\n')
                    continue
            new_lines.append(line)

    if new_lines and not new_lines[-1].endswith("\n"):
        new_lines[-1] += "\n"

    for key, val in remaining_updates.items():
        val_str = str(val)
        if (val_str.startswith('"') and val_str.endswith('"')) or (
            val_str.startswith("'") and val_str.endswith("'")
        ):
            val_str = val_str[1:-1]
        new_lines.append(f'{key}="{val_str}"\n')

    tmp_file = path.parent / f"{path.name}.tmp"
    try:
        with open(tmp_file, "w", encoding="utf-8") as f:
            f.writelines(new_lines)
            f.flush()
            os.fsync(f.fileno())

        delays = [0.0, 0.05, 0.1, 0.2, 0.4, 0.8]
        last_err: Exception | None = None
        for delay in delays:
            if delay > 0:
                time.sleep(delay)
            try:
                os.replace(tmp_file, path)
                break
            except (PermissionError, OSError) as err:
                last_err = err
        else:
            if last_err is not None:
                raise last_err
    finally:
        if tmp_file.exists():
            try:
                tmp_file.unlink()
            except OSError:
                pass
