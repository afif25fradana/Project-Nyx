"""Two-Stage Adaptive StreamParser, 510-Phoneme Guard & Emotion Extractor.

Enforces sub-2.0s TTFA via fast Stage 1 clause emission and protects Kokoro TTS
from phoneme overflow via a strict 300-char whitespace hard cap (Invariant #5).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import AsyncIterator

EMOJI_PATTERN = re.compile(
    "[\U00010000-\U0010ffff"
    "\u2600-\u26ff"
    "\u2700-\u27bf"
    "\ufe00-\ufe0f"
    "\u200d"
    "\u2300-\u23ff]+",
    flags=re.UNICODE,
)

_ABBREV_GUARD = r"(?<!\d)(?<!\bDr)(?<!\bMr)(?<!\bMs)(?<!\bMrs)(?<!\bvs)(?<!\betc)(?<!\b[a-zA-Z])"
_PERIOD_GUARD = rf"(?:(?<=\d)\.(?!\d)(?=\s)|{_ABBREV_GUARD}\.(?!\d))"
STAGE1_PATTERN = re.compile(rf"[,;:\n]|[!?]|{_PERIOD_GUARD}", re.IGNORECASE)
STAGE2_PATTERN = re.compile(rf"[!?\n]+|(?:(?<=\d)\.(?!\d)(?=\s)|{_ABBREV_GUARD}\.+(?!\d))", re.IGNORECASE)



def clean_tts_text(text: str) -> str:
    """Purge markdown syntax, code blocks, tags, and emojis for TTS synthesis."""
    # 1. Purge reasoning blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    # 2. Purge code fences and contents
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    # 3. Purge inline code and stray backticks
    text = re.sub(r"`[^`]*`", "", text)
    text = text.replace("`", "")
    # 4. Strip XML/HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # 5. Clean markdown headers
    text = re.sub(r"#+\s*", "", text)
    # 6. Convert markdown links [label](url) -> label
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    # 7. Remove bold, italic, strikethrough markers
    text = re.sub(r"(\*\*|__|\*|_|~~)", "", text)
    # 8. Remove bullet markers at line starts
    text = re.sub(r"(?:^|\n)\s*[-*•]\s+", " ", text)
    # 9. Remove emojis
    text = EMOJI_PATTERN.sub("", text)
    # 10. Collapse whitespace
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class ClauseChunk:
    """Cleaned text chunk emitted for neural TTS playback and avatar state."""

    text: str
    emotion: str | None = None
    is_final: bool = False


class StreamParser:
    """Two-Stage Adaptive Clause Chunker with Invariant #5 phoneme defense."""

    def __init__(
        self,
        stage1_min: int = 40,
        stage1_max: int = 60,
        hard_cap: int = 300,
        hard_cap_min: int = 250,
        permitted_emotions: set[str] | list[str] | None = None,
        default_emotion: str = "neutral",
    ) -> None:
        self.stage1_min = stage1_min
        self.stage1_max = stage1_max
        self.hard_cap = hard_cap
        self.hard_cap_min = hard_cap_min
        self.permitted_emotions = set(permitted_emotions) if permitted_emotions is not None else None
        self.default_emotion = default_emotion
        self._buffer: str = ""
        self._chunk_count: int = 0
        self._current_emotion: str | None = None

    def reset(self) -> None:
        """Reset internal buffer and counters for a fresh stream turn."""
        self._buffer = ""
        self._chunk_count = 0
        self._current_emotion = None

    def feed_token(self, token: str) -> list[ClauseChunk]:
        """Ingest a streaming token delta and emit any ready ClauseChunks."""
        if not token:
            return []

        self._buffer += token

        # Handle reasoning blocks
        pending_think = ""
        lower_buf = self._buffer.lower()
        if "<think>" in lower_buf:
            if "</think>" in lower_buf:
                self._buffer = re.sub(
                    r"<think>.*?</think>", "", self._buffer, flags=re.DOTALL | re.IGNORECASE
                )
            else:
                think_pos = lower_buf.find("<think>")
                if think_pos == 0 or not self._buffer[:think_pos].strip():
                    return []
                pending_think = self._buffer[think_pos:]
                self._buffer = self._buffer[:think_pos]

        # Handle emotion tags
        lower_buf = self._buffer.lower()
        if "<emotion>" in lower_buf:
            if "</emotion>" in lower_buf:
                match = re.search(
                    r"<emotion>(.*?)</emotion>", self._buffer, flags=re.DOTALL | re.IGNORECASE
                )
                while match:
                    raw_emotion = match.group(1).strip().lower()
                    if self.permitted_emotions is not None and raw_emotion not in self.permitted_emotions:
                        self._current_emotion = self.default_emotion
                    else:
                        self._current_emotion = raw_emotion
                    self._buffer = (
                        self._buffer[: match.start()] + self._buffer[match.end() :]
                    )
                    match = re.search(
                        r"<emotion>(.*?)</emotion>", self._buffer, flags=re.DOTALL | re.IGNORECASE
                    )
                self._buffer = self._buffer.lstrip()
            else:
                if self._buffer.strip().lower().startswith("<emotion"):
                    if pending_think:
                        self._buffer = self._buffer + pending_think
                    return []

        # Wait for potential opening tag at prefix (handling leading whitespace)
        stripped = self._buffer.lstrip()
        if stripped.startswith("<") and ">" not in stripped and len(stripped) < 20:
            if pending_think:
                self._buffer = self._buffer + pending_think
            return []

        chunks: list[ClauseChunk] = []

        while True:
            # Secondary Guard (Invariant #5: 510-Phoneme Guard)
            # If buffer >= 280, forcibly split on nearest whitespace before hard_cap
            if len(self._buffer) >= 280:
                search_slice = self._buffer[: self.hard_cap]
                last_space = search_slice.rfind(" ")
                if last_space >= self.hard_cap_min:
                    raw_chunk = self._buffer[:last_space]
                    self._buffer = self._buffer[last_space:].lstrip()
                    clean = clean_tts_text(raw_chunk)
                    if clean:
                        chunks.append(
                            ClauseChunk(
                                text=clean,
                                emotion=self._current_emotion,
                                is_final=False,
                            )
                        )
                        self._chunk_count += 1
                    continue
                elif len(self._buffer) >= self.hard_cap:
                    split_idx = last_space if last_space > 0 else self.hard_cap
                    raw_chunk = self._buffer[:split_idx]
                    self._buffer = self._buffer[split_idx:].lstrip()
                    clean = clean_tts_text(raw_chunk)
                    if clean:
                        chunks.append(
                            ClauseChunk(
                                text=clean,
                                emotion=self._current_emotion,
                                is_final=False,
                            )
                        )
                        self._chunk_count += 1
                    continue

            # Stage 1: Initial clause emits at 40-60 characters on punctuation
            if self._chunk_count == 0:
                if len(self._buffer) >= self.stage1_min:
                    m = STAGE1_PATTERN.search(self._buffer[self.stage1_min :])
                    if m:
                        split_idx = self.stage1_min + m.end()
                        raw_chunk = self._buffer[:split_idx]
                        self._buffer = self._buffer[split_idx:].lstrip()
                        clean = clean_tts_text(raw_chunk)
                        if clean:
                            chunks.append(
                                ClauseChunk(
                                    text=clean,
                                    emotion=self._current_emotion,
                                    is_final=False,
                                )
                            )
                            self._chunk_count += 1
                        break
                break

            # Stage 2: Subsequent clauses split on standard sentence delimiters [.!?\n]
            if self._chunk_count > 0:
                m = STAGE2_PATTERN.search(self._buffer)
                if m:
                    split_idx = m.end()
                    raw_chunk = self._buffer[:split_idx]
                    self._buffer = self._buffer[split_idx:].lstrip()
                    clean = clean_tts_text(raw_chunk)
                    if clean:
                        chunks.append(
                            ClauseChunk(
                                text=clean,
                                emotion=self._current_emotion,
                                is_final=False,
                            )
                        )
                        self._chunk_count += 1
                    continue
                break

        if pending_think:
            self._buffer = self._buffer + pending_think

        return chunks

    def finalize(self) -> list[ClauseChunk]:
        """Flush remaining buffered text upon stream completion."""
        # Purge unclosed think block
        self._buffer = re.sub(r"<think>.*", "", self._buffer, flags=re.DOTALL | re.IGNORECASE)

        # Extract any pending emotion tag
        match = re.search(
            r"<emotion>(.*?)</emotion>", self._buffer, flags=re.DOTALL | re.IGNORECASE
        )
        if match:
            self._current_emotion = match.group(1).strip().lower()
            self._buffer = self._buffer[: match.start()] + self._buffer[match.end() :]

        clean = clean_tts_text(self._buffer)
        self._buffer = ""
        if clean:
            return [
                ClauseChunk(
                    text=clean,
                    emotion=self._current_emotion,
                    is_final=True,
                )
            ]
        return []

    async def parse_stream(
        self, token_generator: AsyncIterator[str]
    ) -> AsyncIterator[ClauseChunk]:
        """Wrap an async token generator into an async stream of ClauseChunks."""
        async for token in token_generator:
            for chunk in self.feed_token(token):
                yield chunk
        for chunk in self.finalize():
            yield chunk
