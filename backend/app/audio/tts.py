import os
import re
import sys
import threading
from typing import Any
import numpy as np

from backend.app.utils.dll_loader import load_cuda_dlls

load_cuda_dlls()

import espeakng_loader
from phonemizer.backend.espeak.wrapper import EspeakWrapper
from misaki import en
from misaki.espeak import EspeakFallback
from kokoro_onnx import Kokoro


EMOJI_PATTERN = re.compile(
    "[\U00010000-\U0010ffff"
    "\u2600-\u26ff"
    "\u2700-\u27bf"
    "\ufe00-\ufe0f"
    "\u200d"
    "\u2300-\u23ff]+",
    flags=re.UNICODE,
)


def init_phonemizer() -> en.G2P:
    """Initialize Misaki G2P phonemizer with bundled espeakng libraries."""
    if getattr(sys, "frozen", False):
        try:
            import spacy.cli
            spacy.cli.download = lambda *args, **kwargs: None
        except Exception:
            pass

    EspeakWrapper.set_library(espeakng_loader.get_library_path())
    EspeakWrapper.set_data_path(espeakng_loader.get_data_path())
    fallback = EspeakFallback(british=False)
    return en.G2P(trf=False, british=False, fallback=fallback)



def strip_markdown_and_tags(text: str) -> str:
    """Remove markdown syntax, code fences, XML tags, and emojis from text."""
    # 1. Purge internal thought blocks entirely
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)

    # 2. Remove code blocks and inline code
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`[^`]*`", "", text)

    # 3. Strip XML/HTML tags (like <emotion>, </emotion>, <b>, etc.) preserving inner text
    text = re.sub(r"<[^>]+>", "", text)

    # 4. Clean markdown headers (#)
    text = re.sub(r"#+\s*", "", text)

    # 5. Convert markdown links [label](url) -> label
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # 6. Remove bold, italic, strikethrough markers
    text = re.sub(r"(\*\*|__|\*|_|~~)", "", text)

    # 7. Remove emojis (surrogates and extended unicode blocks)
    text = EMOJI_PATTERN.sub("", text)

    # 8. Collapse whitespace
    return re.sub(r"\s+", " ", text).strip()


def split_clauses(text: str, max_chars: int = 280) -> list[str]:
    """Split text into clause-level chunks under the character cap (Invariant #5)."""
    text = text.strip()
    if len(text) <= max_chars:
        return [text] if text else []

    # Split by sentence boundaries first
    sentences = re.split(r"(?<=[.!?])\s+", text)
    clauses: list[str] = []
    current_clause = ""

    for sentence in sentences:
        if len(sentence) <= max_chars:
            if current_clause and len(current_clause) + len(sentence) + 1 > max_chars:
                clauses.append(current_clause.strip())
                current_clause = sentence
            else:
                current_clause = f"{current_clause} {sentence}".strip()
        else:
            # Further split long sentences by commas, semicolons, or dashes
            sub_parts = re.split(r"(?<=[,;:\-])\s+", sentence)
            for part in sub_parts:
                if len(part) <= max_chars:
                    if current_clause and len(current_clause) + len(part) + 1 > max_chars:
                        clauses.append(current_clause.strip())
                        current_clause = part
                    else:
                        current_clause = f"{current_clause} {part}".strip()
                else:
                    # Final fallback: word-level split
                    words = part.split()
                    for word in words:
                        if len(word) > max_chars:
                            if current_clause:
                                clauses.append(current_clause.strip())
                                current_clause = ""
                            for i in range(0, len(word), max_chars):
                                clauses.append(word[i : i + max_chars])
                            continue

                        if current_clause and len(current_clause) + len(word) + 1 > max_chars:
                            clauses.append(current_clause.strip())
                            current_clause = word
                        else:
                            current_clause = f"{current_clause} {word}".strip()

    if current_clause:
        clauses.append(current_clause.strip())

    return [c for c in clauses if c]


def get_speed_tensor(session: Any, speed: float = 1.0) -> np.ndarray:
    """Dynamically cast speed tensor to session input dtype (Invariant #3)."""
    if hasattr(session, "get_inputs"):
        for inp in session.get_inputs():
            if inp.name == "speed":
                if "int64" in inp.type:
                    return np.array([int(speed)], dtype=np.int64)
                elif "int32" in inp.type:
                    return np.array([int(speed)], dtype=np.int32)
                else:
                    return np.array([float(speed)], dtype=np.float32)

    return np.array([float(speed)], dtype=np.float32)


class VoiceEngine:
    """Kokoro TTS and NumPy Voice Blending Engine guarded by global mutex."""

    def __init__(self, model_path: str, voices_path: str) -> None:
        load_cuda_dlls()
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Kokoro model not found: {model_path}")
        if not os.path.exists(voices_path):
            raise FileNotFoundError(f"Voices file not found: {voices_path}")

        self._kokoro = Kokoro(model_path, voices_path)
        self._g2p = init_phonemizer()
        self._synth_lock = threading.Lock()
        self._voice_cache: dict[str, np.ndarray] = {}

    def get_blended_voice(
        self,
        primary: str = "af_nicole",
        secondary: str = "am_onyx",
        weight: float = 0.65,
    ) -> np.ndarray:
        """Blend two voice style embeddings via linear NumPy vector interpolation."""
        cache_key = f"{primary}_{secondary}_{weight:.3f}"
        if cache_key in self._voice_cache:
            return self._voice_cache[cache_key]

        v_prim = self._kokoro.get_voice_style(primary)
        v_sec = self._kokoro.get_voice_style(secondary)
        blended = (weight * v_prim + (1.0 - weight) * v_sec).astype(np.float32)

        self._voice_cache[cache_key] = blended
        return blended

    def synthesize_chunk(
        self,
        text: str,
        voice: np.ndarray,
        speed: float = 1.0,
    ) -> np.ndarray:
        """Synthesize clean 24kHz audio under strict _synth_lock mutex protection."""
        with self._synth_lock:
            cleaned = strip_markdown_and_tags(text)
            if not cleaned:
                return np.zeros(0, dtype=np.float32)

            chunks = split_clauses(cleaned, max_chars=280)
            audio_segments: list[np.ndarray] = []

            speed_tensor = get_speed_tensor(getattr(self._kokoro, "sess", None), speed=speed)
            effective_speed = float(speed_tensor.item())

            for chunk in chunks:
                phonemes, _ = self._g2p(chunk)
                if not phonemes or not phonemes.strip():
                    continue
                samples, _ = self._kokoro.create(
                    phonemes,
                    voice=voice,
                    speed=effective_speed,
                    is_phonemes=True,
                )
                if samples is not None and len(samples) > 0:
                    audio_segments.append(samples)

            if not audio_segments:
                return np.zeros(0, dtype=np.float32)

            return np.concatenate(audio_segments).astype(np.float32)
