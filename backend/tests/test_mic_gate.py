import queue
import numpy as np
import pytest

from backend.app.audio.mic_gate import MicGate


def test_gate_initially_closed_and_drops_frames():
    """Assert gate drops incoming frames instantly when closed (queue stays empty)."""
    gate = MicGate(max_queue_size=10)
    assert gate.is_open() is False

    frame = np.zeros(512, dtype=np.float32)
    # Simulate PortAudio callback when gate is closed
    gate._audio_callback(frame, 512, {}, 0)

    assert gate.queue.qsize() == 0


def test_gate_open_enqueues_frames():
    """Assert opening gate allows frames to be buffered in queue."""
    gate = MicGate(max_queue_size=10)
    gate.open()
    assert gate.is_open() is True

    frame = np.ones(512, dtype=np.float32) * 0.5
    gate._audio_callback(frame, 512, {}, 0)

    assert gate.queue.qsize() == 1
    chunk = gate.queue.get_nowait()
    assert np.allclose(chunk, frame)


def test_gate_queue_full_evicts_oldest_chunk_gap03():
    """GAP-03: Under queue saturation, oldest chunk is evicted and live chunk is preserved."""
    gate = MicGate(max_queue_size=2)
    gate.open()

    chunk1 = np.full(512, 1.0, dtype=np.float32)
    chunk2 = np.full(512, 2.0, dtype=np.float32)
    chunk3 = np.full(512, 3.0, dtype=np.float32)

    gate._audio_callback(chunk1, 512, {}, 0)
    gate._audio_callback(chunk2, 512, {}, 0)
    assert gate.queue.qsize() == 2

    # Third frame should cause chunk1 to be evicted, keeping chunk2 and chunk3
    gate._audio_callback(chunk3, 512, {}, 0)
    assert gate.queue.qsize() == 2

    first_out = gate.queue.get_nowait()
    assert np.allclose(first_out, chunk2), "Oldest chunk (chunk1) was not evicted!"

    second_out = gate.queue.get_nowait()
    assert np.allclose(second_out, chunk3), "Incoming live chunk (chunk3) was not preserved!"


def test_shutdown_cancellation_flag_prevents_unmuting_inv07():
    """Invariant #7: Shutdown cancellation flag permanently prevents unmuting."""
    gate = MicGate()
    gate.open()
    assert gate.is_open() is True

    gate.shutdown()
    assert gate.is_open() is False

    # Attempting to reopen in finally blocks or asynchronous handlers must be rejected
    gate.open()
    assert gate.is_open() is False, "Gate must remain closed when cancelled by shutdown"


def test_gate_clear_queue():
    """Assert clear_queue drains all buffered chunks."""
    gate = MicGate(max_queue_size=10)
    gate.open()

    for i in range(5):
        frame = np.full(512, float(i), dtype=np.float32)
        gate._audio_callback(frame, 512, {}, 0)

    assert gate.queue.qsize() == 5
    gate.clear_queue()
    assert gate.queue.qsize() == 0


def test_gate_multichannel_downmix_to_mono():
    """Assert stereo/multichannel input is cleanly extracted to 1D mono channel."""
    gate = MicGate(max_queue_size=5)
    gate.open()

    # 2D frame (512, 2)
    stereo_frame = np.ones((512, 2), dtype=np.float32)
    stereo_frame[:, 0] = 0.75
    stereo_frame[:, 1] = 0.25

    gate._audio_callback(stereo_frame, 512, {}, 0)
    chunk = gate.queue.get_nowait()

    assert chunk.ndim == 1
    assert chunk.shape == (512,)
    assert np.allclose(chunk, 0.75)


def test_gate_stream_lifecycle():
    """Assert InputStream starts and stops cleanly via start() and stop()."""
    gate = MicGate()
    try:
        gate.start()
        assert gate.is_running is True
    finally:
        gate.stop()
        assert gate.is_running is False
