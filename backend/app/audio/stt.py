import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any
import numpy as np

from backend.app.utils.dll_loader import load_cuda_dlls

load_cuda_dlls()

from faster_whisper import WhisperModel


class Transcriber:
    """faster-whisper STT worker running in a dedicated single-threaded pool."""

    def __init__(
        self,
        model_size: str = "large-v3-turbo",
        device: str = "cuda",
        compute_type: str = "int8_float16",
        download_root: str | None = None,
    ) -> None:
        load_cuda_dlls()
        self._model_size = model_size
        self._device = device
        self._compute_type = compute_type

        try:
            self._model = WhisperModel(
                model_size,
                device=device,
                compute_type=compute_type,
                download_root=download_root,
            )
        except Exception as exc:
            if device == "cuda":
                # Fallback to CPU if CUDA context allocation or device is unavailable
                self._device = "cpu"
                self._compute_type = "int8"
                self._model = WhisperModel(
                    model_size,
                    device=self._device,
                    compute_type=self._compute_type,
                    download_root=download_root,
                )
            else:
                raise exc

        self._executor = ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="WhisperWorker",
        )

    async def transcribe(self, audio_data: np.ndarray, language: str = "en") -> str:
        """Asynchronously transcribe 16kHz float32 audio via worker thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor,
            self._sync_transcribe,
            audio_data,
            language,
        )

    def _sync_transcribe(self, audio_data: np.ndarray, language: str) -> str:
        """Synchronous transcription execution within thread pool."""
        if audio_data.ndim > 1:
            audio_data = audio_data.flatten()
        if audio_data.dtype != np.float32:
            audio_data = audio_data.astype(np.float32)

        segments, _ = self._model.transcribe(
            audio_data,
            language=language,
            beam_size=1,
            vad_filter=False,
            condition_on_previous_text=False,
        )
        return " ".join(seg.text for seg in segments).strip()

    def close(self) -> None:
        """Shut down worker thread pool executor."""
        self._executor.shutdown(wait=False)

    def __enter__(self) -> "Transcriber":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()
