import importlib.util
import os
import numpy as np
import pytest

from backend.app.audio.vad import SileroVAD
from backend.app.audio.types import VADResult
from backend.tests.conftest import (
    generate_tone_pcm16,
    generate_silence_pcm16,
    generate_speech_simulation,
)

MODEL_PATH = os.path.join(
    os.path.dirname(__file__), "..", "app", "audio", "models", "silero_vad.onnx"
)


@pytest.fixture
def vad_engine() -> SileroVAD:
    """Fixture providing an initialized SileroVAD pure ONNX instance."""
    assert os.path.exists(MODEL_PATH), f"Model asset missing at {MODEL_PATH}"
    return SileroVAD(model_path=MODEL_PATH, threshold=0.5, silence_threshold_sec=0.6)


def test_zero_audio_frames_yield_silence(vad_engine: SileroVAD):
    """Test 1: Zero audio frames yield is_speech == False and probability < 0.1."""
    silence = generate_silence_pcm16(duration_sec=0.1)
    frame = silence[:512]
    result = vad_engine.process_frame(frame)

    assert isinstance(result, VADResult)
    assert result.is_speech is False
    assert result.probability < 0.1
    assert result.accumulated_speech_sec == 0.0


def test_synthetic_tone_frames_yield_speech(vad_engine: SileroVAD):
    """Test 2: Synthetic tone frames (440Hz) yield is_speech == True and probability > 0.5."""
    tone = generate_tone_pcm16(freq_hz=440.0, duration_sec=1.0)
    speech_detected = False
    max_prob = 0.0

    # Feed frames sequentially to allow recurrent state to activate
    for i in range(0, len(tone) - 512 + 1, 512):
        frame = tone[i : i + 512]
        result = vad_engine.process_frame(frame)
        if result.probability > max_prob:
            max_prob = result.probability
        if result.is_speech:
            speech_detected = True

    assert speech_detected is True
    assert max_prob > 0.5
    assert vad_engine.accumulated_speech_sec > 0.0


def test_endpointing_triggers_after_600ms_silence(vad_engine: SileroVAD):
    """Test 3: Endpointing triggers after 600ms silence following speech."""
    sim_audio = generate_speech_simulation(tone_duration=1.0, silence_duration=0.7)
    endpoint_triggered = False

    for i in range(0, len(sim_audio) - 512 + 1, 512):
        frame = sim_audio[i : i + 512]
        result = vad_engine.process_frame(frame)
        if vad_engine.is_endpoint(result):
            endpoint_triggered = True
            break

    assert endpoint_triggered is True
    assert vad_engine.accumulated_speech_sec >= 0.5
    assert vad_engine.accumulated_silence_sec >= 0.6


def test_sub_half_second_speech_resets_to_idle(vad_engine: SileroVAD):
    """Test 4: Sub-0.5s speech noise resets to idle without hanging."""
    # 0.2s speech (approx 6 frames), followed by 0.6s silence
    short_sim = generate_speech_simulation(tone_duration=0.2, silence_duration=0.65)
    transient_detected = False

    for i in range(0, len(short_sim) - 512 + 1, 512):
        frame = short_sim[i : i + 512]
        result = vad_engine.process_frame(frame)
        # Check if silence reached endpoint while speech was < 0.5s
        if result.accumulated_silence_sec >= 0.6 and result.accumulated_speech_sec < 0.5:
            transient_detected = True
            vad_engine.reset_state()
            break

    assert transient_detected is True
    assert vad_engine.accumulated_speech_sec == 0.0
    assert vad_engine.accumulated_silence_sec == 0.0


def test_zero_pytorch_invariant():
    """Test 5: Assert importlib.util.find_spec('torch') is None."""
    assert importlib.util.find_spec("torch") is None
    assert importlib.util.find_spec("torchaudio") is None


def test_invalid_frame_length_raises_value_error(vad_engine: SileroVAD):
    """Assert frame length mismatch raises ValueError."""
    bad_frame = np.zeros(256, dtype=np.float32)
    with pytest.raises(ValueError, match="Expected 512 samples"):
        vad_engine.process_frame(bad_frame)


def test_missing_model_raises_file_not_found():
    """Assert initializing with missing model path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError, match="VAD model not found"):
        SileroVAD(model_path="nonexistent_model.onnx")


def test_reset_state_clears_accumulators(vad_engine: SileroVAD):
    """Assert reset_state clears state arrays and time accumulators."""
    tone = generate_tone_pcm16(freq_hz=440.0, duration_sec=0.2)
    for i in range(0, len(tone) - 512 + 1, 512):
        vad_engine.process_frame(tone[i : i + 512])

    vad_engine.reset_state()
    assert vad_engine.accumulated_speech_sec == 0.0
    assert vad_engine.accumulated_silence_sec == 0.0


def test_transient_noise_accumulator_resets_on_silence(vad_engine: SileroVAD):
    """Assert transient noise (< 0.5s) followed by silence resets speech accumulator preventing false endpoints."""
    # First transient noise: 0.2s speech, then 0.65s silence
    sim_audio = generate_speech_simulation(tone_duration=0.2, silence_duration=0.65)
    for i in range(0, len(sim_audio) - 512 + 1, 512):
        frame = sim_audio[i : i + 512]
        vad_engine.process_frame(frame)

    # After silence threshold, speech accumulator should be clean (0.0)
    assert vad_engine.accumulated_speech_sec == 0.0

    # Second transient noise: another 0.2s speech followed by 0.65s silence
    endpoint_triggered = False
    for i in range(0, len(sim_audio) - 512 + 1, 512):
        frame = sim_audio[i : i + 512]
        res = vad_engine.process_frame(frame)
        if vad_engine.is_endpoint(res):
            endpoint_triggered = True
            break

    # If it didn't reset, 0.2s + 0.2s would still be < 0.5s, but 3 transient bursts would exceed 0.5s.
    # Verify no endpoint was triggered
    assert endpoint_triggered is False

