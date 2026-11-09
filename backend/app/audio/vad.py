import os
import numpy as np
import onnxruntime as ort

from backend.app.audio.types import VADResult


class SileroVAD:
    """Pure ONNX Silero VAD v6 processor operating on 16kHz audio."""

    def __init__(
        self,
        model_path: str,
        threshold: float = 0.5,
        silence_threshold_sec: float = 0.6,
        sample_rate: int = 16000,
    ) -> None:
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"VAD model not found at: {model_path}")

        opts = ort.SessionOptions()
        opts.inter_op_num_threads = 1
        opts.intra_op_num_threads = 1
        self._session = ort.InferenceSession(
            model_path,
            sess_options=opts,
            providers=["CPUExecutionProvider"],
        )

        self._threshold = threshold
        self._silence_threshold_sec = silence_threshold_sec
        self._sample_rate = sample_rate

        self._sr_tensor = np.array(sample_rate, dtype=np.int64)
        self._context = np.zeros((1, 64), dtype=np.float32)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)

        self._accumulated_speech_sec = 0.0
        self._accumulated_silence_sec = 0.0

    @property
    def accumulated_speech_sec(self) -> float:
        return self._accumulated_speech_sec

    @property
    def accumulated_silence_sec(self) -> float:
        return self._accumulated_silence_sec

    @property
    def silence_threshold_sec(self) -> float:
        return self._silence_threshold_sec

    def reset_state(self) -> None:
        """Clear recurrent state, rolling context, and duration accumulators."""
        self._context = np.zeros((1, 64), dtype=np.float32)
        self._state = np.zeros((2, 1, 128), dtype=np.float32)
        self._accumulated_speech_sec = 0.0
        self._accumulated_silence_sec = 0.0

    def is_endpoint(self, result: VADResult | None = None) -> bool:
        """Return True when minimum speech length and silence threshold are met."""
        speech_sec = result.accumulated_speech_sec if result else self._accumulated_speech_sec
        silence_sec = result.accumulated_silence_sec if result else self._accumulated_silence_sec
        return speech_sec >= 0.5 and silence_sec >= self._silence_threshold_sec

    def process_frame(self, frame: np.ndarray) -> VADResult:
        """Process a single 512-sample float32 frame and update recurrent state."""
        if frame.ndim == 1:
            if len(frame) != 512:
                raise ValueError(f"Expected 512 samples, got {len(frame)}")
            frame_2d = frame.reshape(1, 512)
        elif frame.ndim == 2:
            if frame.shape != (1, 512):
                raise ValueError(f"Expected shape (1, 512), got {frame.shape}")
            frame_2d = frame
        else:
            raise ValueError(f"Invalid frame dimensions: {frame.ndim}")

        if frame_2d.dtype != np.float32:
            frame_2d = frame_2d.astype(np.float32)

        # Concatenate 64-sample trailing context with 512-sample frame -> (1, 576)
        x = np.concatenate([self._context, frame_2d], axis=-1)

        ort_inputs = {
            "input": x,
            "state": self._state,
            "sr": self._sr_tensor,
        }
        ort_outs = self._session.run(None, ort_inputs)

        prob = float(ort_outs[0][0, 0])
        self._state = ort_outs[1]
        self._context = x[:, -64:]

        frame_duration = 512.0 / float(self._sample_rate)
        is_speech = prob >= self._threshold

        if is_speech:
            self._accumulated_speech_sec += frame_duration
            self._accumulated_silence_sec = 0.0
        else:
            self._accumulated_silence_sec += frame_duration

        result = VADResult(
            is_speech=is_speech,
            probability=prob,
            accumulated_speech_sec=self._accumulated_speech_sec,
            accumulated_silence_sec=self._accumulated_silence_sec,
        )

        if (
            not is_speech
            and 0.0 < self._accumulated_speech_sec < 0.5
            and self._accumulated_silence_sec >= self._silence_threshold_sec
        ):
            self._accumulated_speech_sec = 0.0
            self._accumulated_silence_sec = 0.0

        return result
