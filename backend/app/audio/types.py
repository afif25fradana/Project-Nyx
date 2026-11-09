from dataclasses import dataclass, field
import numpy as np


@dataclass(frozen=True)
class AudioChunk:
    """Raw audio frame from WASAPI input stream."""
    data: np.ndarray  # shape: (512,), dtype: float32, sample_rate: 16000
    timestamp: float


@dataclass(frozen=True)
class VADResult:
    """Output state of a single VAD frame inference."""
    is_speech: bool
    probability: float
    accumulated_speech_sec: float
    accumulated_silence_sec: float


# Alias for compatibility with architectural technical plan
VADState = VADResult


@dataclass(frozen=True)
class SpeechTurnContext:
    """State tracked across an active speech turn."""
    turn_id: int
    audio_frames: list[np.ndarray] = field(default_factory=list)
    transcript: str = ""
    is_interrupted: bool = False


@dataclass(frozen=True)
class VoiceBlendConfig:
    """Configuration for Kokoro voice style blending."""
    primary_voice: str = "af_nicole"
    secondary_voice: str = "am_onyx"
    blend_weight: float = 0.65
