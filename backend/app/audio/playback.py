import logging
import queue
import sys
import threading
import time
from typing import Any, Callable
import numpy as np
import sounddevice as sd

logger = logging.getLogger(__name__)


def _resolve_output_device(device: int | None = None) -> tuple[int | None, Any]:
    """Find a WASAPI output device and matching WasapiSettings if on Windows."""
    if sys.platform != "win32" or not hasattr(sd, "WasapiSettings"):
        return device, None

    if device is not None:
        try:
            dev_info = sd.query_devices(device)
            hostapi_info = sd.query_hostapis(dev_info["hostapi"])
            if "WASAPI" in hostapi_info["name"]:
                return device, sd.WasapiSettings(exclusive=False, auto_convert=True)
        except Exception:
            pass
        return device, None

    try:
        hostapis = sd.query_hostapis()
        wasapi_idx = next(
            (i for i, api in enumerate(hostapis) if "WASAPI" in api["name"]), None
        )
        if wasapi_idx is not None:
            default_out = sd.default.device[1]
            if default_out is not None and default_out >= 0:
                dev_info = sd.query_devices(default_out)
                if dev_info["hostapi"] == wasapi_idx and dev_info["max_output_channels"] > 0:
                    return default_out, sd.WasapiSettings(exclusive=False, auto_convert=True)

            for dev_idx, dev in enumerate(sd.query_devices()):
                if dev["hostapi"] == wasapi_idx and dev["max_output_channels"] > 0:
                    return dev_idx, sd.WasapiSettings(exclusive=False, auto_convert=True)
    except Exception:
        pass

    return None, None


class AudioPlayer:
    """Non-blocking cancellable 24kHz float32 PCM output stream."""

    def __init__(
        self,
        sample_rate: int = 24000,
        channels: int = 1,
        blocksize: int = 512,
        max_queue_size: int = 200,
        device: int | None = None,
    ) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._blocksize = blocksize
        self._device = device

        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=max_queue_size)
        self._current_chunk: np.ndarray | None = None
        self._chunk_offset: int = 0

        self._is_playing = False
        self._cancelled = False
        self._generation: int = 0
        self._lock = threading.Lock()
        self._stream: sd.OutputStream | None = None

    @property
    def queue(self) -> queue.Queue[np.ndarray]:
        """Expose thread-safe audio playback queue."""
        return self._queue

    def is_playing(self) -> bool:
        """Return True if stream is playing or queue is non-empty."""
        with self._lock:
            return (
                self._is_playing
                or not self._queue.empty()
                or self._current_chunk is not None
            )

    def play_chunk(self, chunk: np.ndarray, generation: int | None = None) -> None:
        """Enqueue a 24kHz float32 audio chunk for playback."""
        if chunk.ndim > 1:
            chunk = chunk[:, 0].copy()
        if chunk.dtype != np.float32:
            chunk = chunk.astype(np.float32)

        with self._lock:
            if self._cancelled:
                logger.debug("AudioPlayer: chunk dropped due to active cancellation")
                return
            if generation is not None and generation != self._generation:
                logger.debug(
                    "AudioPlayer: stale chunk dropped (chunk generation %d != active generation %d)",
                    generation,
                    self._generation,
                )
                return
            self._is_playing = True

        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(chunk)
            except (queue.Empty, queue.Full):
                pass

    def cancel(self) -> None:
        """Immediately abort active playback and clear pending queue chunks."""
        with self._lock:
            self._cancelled = True
            self._is_playing = False
            self._current_chunk = None
            self._chunk_offset = 0

            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break

    def reset(self, generation: int | None = None) -> None:
        """Clear cancellation state to permit playback for a new turn."""
        with self._lock:
            self._cancelled = False
            if generation is not None:
                self._generation = generation

    def start(self) -> None:
        """Initialize and start the PortAudio output stream."""
        if self._stream is not None:
            return

        device, extra_settings = _resolve_output_device(self._device)

        self._stream = sd.OutputStream(
            device=device,
            samplerate=self._sample_rate,
            channels=self._channels,
            dtype="float32",
            blocksize=self._blocksize,
            callback=self._audio_callback,
            extra_settings=extra_settings,
        )
        self._stream.start()

    def stop(self) -> None:
        """Stop and close the PortAudio output stream."""
        self.cancel()
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            finally:
                self._stream = None

    def _audio_callback(
        self,
        outdata: np.ndarray,
        frames: int,
        time_info: Any,
        status: Any,
    ) -> None:
        """PortAudio stream callback writing queue chunks to output buffer."""
        filled = 0
        while filled < frames:
            slice_data = None
            to_copy = 0

            with self._lock:
                if self._cancelled:
                    break

                if self._current_chunk is None or self._chunk_offset >= len(self._current_chunk):
                    try:
                        self._current_chunk = self._queue.get_nowait()
                        self._chunk_offset = 0
                    except queue.Empty:
                        self._current_chunk = None
                        self._chunk_offset = 0
                        self._is_playing = False
                        break

                curr = self._current_chunk
                if curr is None:
                    break

                offset = self._chunk_offset
                available = len(curr) - offset
                needed = frames - filled
                to_copy = min(available, needed)

                slice_data = curr[offset : offset + to_copy]
                self._chunk_offset += to_copy

            if slice_data is not None:
                if outdata.ndim > 1:
                    outdata[filled : filled + to_copy, 0] = slice_data
                else:
                    outdata[filled : filled + to_copy] = slice_data
                filled += to_copy

        if filled < frames:
            if outdata.ndim > 1:
                outdata[filled:, 0].fill(0.0)
            else:
                outdata[filled:].fill(0.0)


class SpeakingWatchdog:
    """Monitors maximum speech playback timeout without mutating FSM state directly."""

    def __init__(self, timeout_sec: float = 30.0) -> None:
        self._timeout_sec = timeout_sec
        self._on_timeout: Callable[[], None] | None = None
        self._timer: threading.Timer | None = None
        self._start_time: float | None = None
        self._is_active = False
        self._lock = threading.Lock()

    @property
    def is_active(self) -> bool:
        """Return True if watchdog timer is currently running."""
        with self._lock:
            return self._is_active

    @property
    def elapsed(self) -> float:
        """Return elapsed duration since watchdog activation in seconds."""
        with self._lock:
            if self._start_time is None or not self._is_active:
                return 0.0
            return time.perf_counter() - self._start_time

    def start(self, on_timeout: Callable[[], None] | None = None) -> None:
        """Start watchdog countdown timer."""
        self.stop()
        with self._lock:
            self._is_active = True
            self._start_time = time.perf_counter()
            self._on_timeout = on_timeout
            self._timer = threading.Timer(self._timeout_sec, self._fire_timeout)
            self._timer.daemon = True
            self._timer.start()

    def stop(self) -> None:
        """Stop watchdog timer and disarm timeout handler."""
        with self._lock:
            self._is_active = False
            self._start_time = None
            if self._timer is not None:
                self._timer.cancel()
                self._timer = None

    def _fire_timeout(self) -> None:
        """Internal callback invoked when timer expires."""
        cb = None
        with self._lock:
            if not self._is_active:
                return
            self._is_active = False
            cb = self._on_timeout

        if cb is not None:
            cb()
