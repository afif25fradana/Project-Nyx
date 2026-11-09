import os
import sys

# Ensure repository root is on sys.path for direct pytest invocation
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import numpy as np
import pytest


def generate_tone_pcm16(
    freq_hz: float = 440.0,
    duration_sec: float = 1.0,
    sample_rate: int = 16000,
) -> np.ndarray:
    """Generate synthetic speech-like harmonic tone audio frames (float32)."""
    num_samples = int(sample_rate * duration_sec)
    t = np.linspace(0, duration_sec, num_samples, endpoint=False, dtype=np.float32)
    # Fundamental vocal pitch with harmonic at freq_hz and speech envelope
    pitch = freq_hz / 3.0
    wave = (
        np.sin(2 * np.pi * pitch * t)
        + 0.8 * np.sin(2 * np.pi * 2 * pitch * t)
        + np.sin(2 * np.pi * freq_hz * t)
    ) * (np.sin(2 * np.pi * 4.0 * t) ** 2)
    norm = np.max(np.abs(wave))
    if norm > 0:
        wave = wave / norm
    return (0.7 * wave).astype(np.float32)


def generate_silence_pcm16(
    duration_sec: float = 1.0,
    sample_rate: int = 16000,
) -> np.ndarray:
    """Generate synthetic silence audio frames (float32 zeros)."""
    num_samples = int(sample_rate * duration_sec)
    return np.zeros(num_samples, dtype=np.float32)


def generate_speech_simulation(
    tone_duration: float = 1.0,
    silence_duration: float = 0.6,
    sample_rate: int = 16000,
) -> np.ndarray:
    """Generate concatenated synthetic speech tone followed by silence."""
    tone = generate_tone_pcm16(duration_sec=tone_duration, sample_rate=sample_rate)
    silence = generate_silence_pcm16(duration_sec=silence_duration, sample_rate=sample_rate)
    return np.concatenate([tone, silence]).astype(np.float32)


# Alias conforming to spec task checklist
generate_pcm16_speech_simulation = generate_speech_simulation


@pytest.fixture
def tone_generator():
    return generate_tone_pcm16


@pytest.fixture
def silence_generator():
    return generate_silence_pcm16


@pytest.fixture
def speech_simulation_generator():
    return generate_speech_simulation
