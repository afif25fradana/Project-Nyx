import queue
import sys
import threading
from typing import Any
import numpy as np
import sounddevice as sd


def _resolve_input_device(device: int | None = None) -> tuple[int | None, Any]:
    """Find a WASAPI input device and matching WasapiSettings if on Windows."""
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
            # Check default input device
            default_in = sd.default.device[0]
            if default_in is not None and default_in >= 0:
                dev_info = sd.query_devices(default_in)
                if dev_info["hostapi"] == wasapi_idx and dev_info["max_input_channels"] > 0:
                    return default_in, sd.WasapiSettings(exclusive=False, auto_convert=True)

            # Search available WASAPI devices with input channels
            for dev_idx, dev in enumerate(sd.query_devices()):
                if dev["hostapi"] == wasapi_idx and dev["max_input_channels"] > 0:
                    return dev_idx, sd.WasapiSettings(exclusive=False, auto_convert=True)
    except Exception:
        pass

    return None, None


class MicGate:
    """WASAPI Shared Mode in-callback atomic gate with FIFO eviction."""

    def __init__(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        blocksize: int = 512,
        max_queue_size: int = 100,
        device: int | None = None,
    ) -> None:
        self._sample_rate = sample_rate
        self._channels = channels
        self._blocksize = blocksize
        self._device = device
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=max_queue_size)

        self._is_open = False
        self._cancelled_by_shutdown = False
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None

    @property
    def queue(self) -> queue.Queue[np.ndarray]:
        """Expose thread-safe audio chunk queue."""
        return self._queue

    @property
    def is_running(self) -> bool:
        """Return True if active audio stream is running."""
        return self._stream is not None and getattr(self._stream, "active", False)

    def open(self) -> None:
        """Open the microphone gate to allow audio buffering."""
        with self._lock:
            if self._cancelled_by_shutdown:
                return
            self._is_open = True

    def close(self) -> None:
        """Close the microphone gate to drop audio frames immediately."""
        with self._lock:
            self._is_open = False

    def is_open(self) -> bool:
        """Check whether gate is currently open and not shut down."""
        with self._lock:
            return self._is_open and not self._cancelled_by_shutdown

    def clear_queue(self) -> None:
        """Drain all buffered chunks from the queue."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break

    def start(self) -> None:
        """Initialize and start the PortAudio WASAPI input stream."""
        if self._stream is not None:
            return

        device, extra_settings = _resolve_input_device(self._device)

        self._stream = sd.InputStream(
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
        """Stop and close the PortAudio input stream."""
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            finally:
                self._stream = None

    def shutdown(self) -> None:
        """Permanently shut down the mic gate and discard buffered audio (Invariant #7)."""
        with self._lock:
            self._cancelled_by_shutdown = True
            self._is_open = False
        self.stop()
        self.clear_queue()

    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: Any,
        status: Any,
    ) -> None:
        """PortAudio stream callback. Drops frames if gate closed; evicts oldest on full."""
        if not self._is_open or self._cancelled_by_shutdown:
            return

        chunk = indata[:, 0].copy() if indata.ndim > 1 else indata.copy()
        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(chunk)
            except (queue.Empty, queue.Full):
                pass
