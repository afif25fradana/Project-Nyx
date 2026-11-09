from pathlib import Path
import asyncio
import os
import time
import uuid


class MarkdownStore:
    """Atomic file persistence for Markdown documents with retry loop & fsync (INV 10)."""

    def __init__(self, base_dir: Path | str | None = None) -> None:
        self.base_dir = Path(base_dir) if base_dir else Path("data/memory")

    def write_text(self, target_path: Path | str, content: str) -> None:
        """Write content atomically via unique .tmp, fsync, and exponential backoff replace."""
        target = Path(target_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = target.with_name(f"{target.name}.{uuid.uuid4().hex[:8]}.tmp")

        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())

            delays = [0.0, 0.05, 0.1, 0.2, 0.4, 0.8]
            last_err: Exception | None = None
            for delay in delays:
                if delay > 0.0:
                    time.sleep(delay)
                try:
                    os.replace(tmp_path, target)
                    return
                except (PermissionError, OSError) as err:
                    last_err = err

            if last_err is not None:
                raise last_err
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except Exception:
                    pass

    async def write_text_async(self, target_path: Path | str, content: str) -> None:
        """Non-blocking asynchronous wrapper running atomic file write in a worker thread."""
        await asyncio.to_thread(self.write_text, target_path, content)

    def read_text(self, target_path: Path | str, default: str = "") -> str:
        """Read text from file; return default if file does not exist."""
        path = Path(target_path)
        if not path.exists():
            return default

        delays = [0.0, 0.025, 0.05, 0.1, 0.2]
        last_err: Exception | None = None
        for delay in delays:
            if delay > 0.0:
                time.sleep(delay)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            except PermissionError as err:
                last_err = err
            except FileNotFoundError:
                return default

        if last_err is not None:
            raise last_err
        return default

    async def read_text_async(self, target_path: Path | str, default: str = "") -> str:
        """Non-blocking asynchronous wrapper running file read in a worker thread."""
        return await asyncio.to_thread(self.read_text, target_path, default)

    def read_user_profile(self) -> str:
        return self.read_text(self.base_dir / "USER.md")

    def write_user_profile(self, content: str) -> None:
        self.write_text(self.base_dir / "USER.md", content)

    def read_memory(self) -> str:
        return self.read_text(self.base_dir / "MEMORY.md")

    def write_memory(self, content: str) -> None:
        self.write_text(self.base_dir / "MEMORY.md", content)
