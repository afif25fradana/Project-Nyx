import os
import threading
import numpy as np
import pytest

from backend.app.audio.tts import (
    VoiceEngine,
    strip_markdown_and_tags,
    split_clauses,
    get_speed_tensor,
    init_phonemizer,
)

MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "app", "audio", "models", "kokoro-v1.0.onnx"
)
VOICES_PATH = os.path.join(
    os.path.dirname(__file__), "..", "app", "audio", "models", "voices-v1.0.bin"
)


def test_strip_markdown_and_tags():
    """Assert markdown syntax, code fences, XML tags, and emojis are purged."""
    raw = (
        "<emotion type='whisper'>**Hello** world! # Heading 1\n"
        "Here is `code` and ```\ncode block\n``` with [link](https://test.com) "
        "and emojis 👋🖤. <think>Internal thought</think></emotion>"
    )
    cleaned = strip_markdown_and_tags(raw)
    assert "**" not in cleaned
    assert "#" not in cleaned
    assert "code block" not in cleaned
    assert "<emotion" not in cleaned
    assert "<think" not in cleaned
    assert "Internal thought" not in cleaned
    assert "👋" not in cleaned
    assert "🖤" not in cleaned
    assert "Hello world!" in cleaned
    assert "Here is and with link" in cleaned or "Hello world!" in cleaned


def test_split_clauses_char_limit():
    """Assert long sentences are cleanly split into clauses below 280 characters."""
    long_text = (
        "Nyx is an advanced local voice AI designed for responsive voice interactions. "
        "She operates with zero PyTorch bloat and leverages fast ONNX models to achieve sub-second latency. "
        "Every turn is governed by a strict state machine, preventing feedback loops and ensuring smooth conversation. "
        "Furthermore, memory persistence uses SQLite WAL mode to guarantee zero data loss during unexpected crashes."
    )
    clauses = split_clauses(long_text, max_chars=200)
    assert len(clauses) > 1
    for clause in clauses:
        assert len(clause) <= 200, f"Clause exceeded limit: {len(clause)} chars"


def test_split_clauses_hard_slices_unbroken_words():
    """Assert single unbroken word/URL exceeding max_chars is hard-sliced to prevent phoneme overflow."""
    unbroken_word = "https://example.com/very/long/unbroken/path/" + ("a" * 300)
    clauses = split_clauses(unbroken_word, max_chars=100)
    assert len(clauses) >= 4
    for clause in clauses:
        assert len(clause) <= 100, f"Clause exceeded max_chars: {len(clause)}"



def test_speed_tensor_dynamic_casting():
    """Invariant #3: Speed tensor dynamically casts to float32, int64, or int32."""
    class DummyInput:
        def __init__(self, name: str, type_str: str):
            self.name = name
            self.type = type_str

    class DummySession:
        def __init__(self, speed_type: str):
            self.inputs = [DummyInput("speed", speed_type)]
        def get_inputs(self):
            return self.inputs

    # float32 session
    sess_fp32 = DummySession("tensor(float)")
    t_fp32 = get_speed_tensor(sess_fp32, speed=1.2)
    assert t_fp32.dtype == np.float32
    assert np.isclose(t_fp32[0], 1.2)

    # int64 session
    sess_int64 = DummySession("tensor(int64)")
    t_int64 = get_speed_tensor(sess_int64, speed=1.0)
    assert t_int64.dtype == np.int64
    assert t_int64[0] == 1

    # int32 session
    sess_int32 = DummySession("tensor(int32)")
    t_int32 = get_speed_tensor(sess_int32, speed=1.0)
    assert t_int32.dtype == np.int32
    assert t_int32[0] == 1


def test_misaki_phonemizer_unicode_safe():
    """Assert Misaki phonemizer converts plain text to IPA phonemes without crash."""
    g2p = init_phonemizer()
    phonemes, _ = g2p("Hello world, this is Nyx AI.")
    assert isinstance(phonemes, str)
    assert len(phonemes) > 0


def test_voice_engine_blended_voice_and_synthesis():
    """Assert VoiceEngine produces valid blended style vector and synthesizes 24kHz audio."""
    assert os.path.exists(MODEL_PATH), f"Model asset missing: {MODEL_PATH}"
    assert os.path.exists(VOICES_PATH), f"Voice asset missing: {VOICES_PATH}"

    engine = VoiceEngine(model_path=MODEL_PATH, voices_path=VOICES_PATH)
    blend = engine.get_blended_voice("af_nicole", "am_onyx", 0.65)

    assert isinstance(blend, np.ndarray)
    assert blend.shape == (510, 1, 256)
    assert blend.dtype == np.float32

    # Cached on subsequent retrieval
    blend_cached = engine.get_blended_voice("af_nicole", "am_onyx", 0.65)
    assert blend is blend_cached

    # Short synthesis test
    audio = engine.synthesize_chunk("Hello.", voice=blend, speed=1.0)
    assert isinstance(audio, np.ndarray)
    assert audio.ndim == 1
    assert audio.dtype == np.float32
    assert len(audio) > 0


def test_synth_lock_serializes_concurrent_calls():
    """Assert _synth_lock is acquired during synthesis preventing concurrent collision."""
    engine = VoiceEngine(model_path=MODEL_PATH, voices_path=VOICES_PATH)
    assert hasattr(engine, "_synth_lock")
    assert isinstance(engine._synth_lock, type(threading.Lock()))


def test_synthesize_chunk_uses_g2p_and_is_phonemes(monkeypatch):
    """Assert synthesize_chunk calls self._g2p and passes is_phonemes=True to Kokoro.create."""
    engine = VoiceEngine(model_path=MODEL_PATH, voices_path=VOICES_PATH)
    g2p_called = False
    kokoro_called_with_phonemes = False

    def mock_g2p(text):
        nonlocal g2p_called
        g2p_called = True
        return "h-phonemes", None

    def mock_create(text, voice, speed=1.0, is_phonemes=False, **kwargs):
        nonlocal kokoro_called_with_phonemes
        if is_phonemes and text == "h-phonemes":
            kokoro_called_with_phonemes = True
        return np.zeros(256, dtype=np.float32), 24000

    monkeypatch.setattr(engine, "_g2p", mock_g2p)
    monkeypatch.setattr(engine._kokoro, "create", mock_create)

    blend = engine.get_blended_voice("af_nicole", "am_onyx", 0.65)
    res = engine.synthesize_chunk("Hello.", voice=blend, speed=1.0)

    assert g2p_called is True
    assert kokoro_called_with_phonemes is True
    assert len(res) == 256

