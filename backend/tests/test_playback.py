import queue
import time
import numpy as np
import pytest

from backend.app.audio.playback import AudioPlayer, SpeakingWatchdog
from backend.app.core.state_machine import TurnManager


def test_audio_player_queue_and_play_chunk():
    """Assert AudioPlayer enqueues 24kHz float32 chunks."""
    player = AudioPlayer(sample_rate=24000, channels=1)
    chunk = np.ones(1024, dtype=np.float32) * 0.25

    player.play_chunk(chunk)
    assert player.queue.qsize() == 1
    assert player.is_playing() is True


def test_audio_player_cancel_clears_queue():
    """Assert player.cancel() immediately drains queue and halts playback."""
    player = AudioPlayer(sample_rate=24000, channels=1)
    for _ in range(5):
        player.play_chunk(np.zeros(512, dtype=np.float32))

    assert player.queue.qsize() == 5
    player.cancel()
    assert player.queue.qsize() == 0
    assert player.is_playing() is False


def test_audio_player_callback_streams_and_silences_on_empty():
    """Assert audio callback writes chunks to outdata and writes zeros when queue empty."""
    player = AudioPlayer(sample_rate=24000, channels=1)
    chunk = np.full(512, 0.5, dtype=np.float32)
    player.play_chunk(chunk)

    outdata = np.zeros((512, 1), dtype=np.float32)
    player._audio_callback(outdata, 512, {}, 0)

    # Output should contain the played chunk
    assert np.allclose(outdata[:, 0], 0.5)

    # Next callback should write zeros because queue is empty
    outdata2 = np.ones((512, 1), dtype=np.float32)
    player._audio_callback(outdata2, 512, {}, 0)
    assert np.allclose(outdata2, 0.0)


def test_speaking_watchdog_timeout_triggers_callback_inv09():
    """Invariant #9: Watchdog triggers callback on timeout without direct FSM mutation."""
    timeout_fired = False

    def on_timeout_cb():
        nonlocal timeout_fired
        timeout_fired = True

    watchdog = SpeakingWatchdog(timeout_sec=0.1)
    watchdog.start(on_timeout=on_timeout_cb)

    assert watchdog.is_active is True
    time.sleep(0.18)

    assert timeout_fired is True
    assert watchdog.is_active is False


def test_speaking_watchdog_stop_cancels_timer():
    """Assert stopping watchdog before timeout prevents callback from firing."""
    timeout_fired = False

    def on_timeout_cb():
        nonlocal timeout_fired
        timeout_fired = True

    watchdog = SpeakingWatchdog(timeout_sec=0.2)
    watchdog.start(on_timeout=on_timeout_cb)

    time.sleep(0.05)
    watchdog.stop()

    time.sleep(0.2)
    assert timeout_fired is False
    assert watchdog.is_active is False


def test_playback_cancel_concurrency_no_crash():
    """Assert concurrent play_chunk, cancel, and _audio_callback do not raise NoneType/deadlock."""
    import threading
    player = AudioPlayer(sample_rate=24000, channels=1, max_queue_size=10)
    stop_event = threading.Event()
    errors: list[Exception] = []

    def feed_worker():
        chunk = np.ones(256, dtype=np.float32) * 0.1
        while not stop_event.is_set():
            try:
                player.play_chunk(chunk)
            except Exception as e:
                errors.append(e)
            time.sleep(0.001)

    def cancel_worker():
        while not stop_event.is_set():
            try:
                player.cancel()
            except Exception as e:
                errors.append(e)
            time.sleep(0.002)

    def callback_worker():
        outdata = np.zeros((128, 1), dtype=np.float32)
        while not stop_event.is_set():
            try:
                player._audio_callback(outdata, 128, {}, 0)
            except Exception as e:
                errors.append(e)
            time.sleep(0.001)

    threads = [
        threading.Thread(target=feed_worker),
        threading.Thread(target=cancel_worker),
        threading.Thread(target=callback_worker),
    ]

    for t in threads:
        t.start()

    time.sleep(0.3)
    stop_event.set()

    for t in threads:
        t.join(timeout=1.0)

    assert errors == [], f"Concurrency errors occurred: {errors}"


def test_play_chunk_dropped_after_cancel_until_reset():
    """Assert late chunks arriving after cancellation are dropped until reset."""
    player = AudioPlayer(sample_rate=24000, channels=1)
    player.cancel()
    player.play_chunk(np.zeros(512, dtype=np.float32))

    assert player.is_playing() is False
    assert player._queue.empty() is True

    player.reset()
    player.play_chunk(np.ones(512, dtype=np.float32))
    assert player.is_playing() is True
    assert player._queue.qsize() == 1


def test_play_chunk_drops_stale_generation_chunk():
    """Assert late chunks from prior generation are dropped."""
    player = AudioPlayer()
    player.reset(generation=2)
    player.play_chunk(np.zeros(512, dtype=np.float32), generation=1)

    assert player.is_playing() is False
    assert player._queue.empty() is True


@pytest.mark.asyncio
async def test_turn_manager_turn_context_resets_playback_after_interrupt():
    """Assert TurnManager.turn_context resets playback cancellation state and tags generation."""
    turn_mgr = TurnManager()
    player = AudioPlayer()
    turn_mgr._playback = player

    turn_mgr.interrupt()
    assert player._cancelled is True

    async with turn_mgr.turn_context() as gen:
        player.play_chunk(np.ones(512, dtype=np.float32), generation=gen)

    assert player.is_playing() is True
    assert player._queue.qsize() == 1


@pytest.mark.asyncio
async def test_real_turn_pipeline_drops_stale_generation_chunk_behavioral():
    turn_mgr = TurnManager()
    player = AudioPlayer()
    turn_mgr._playback = player

    async with turn_mgr.turn_context() as gen_1:
        chunk_1 = np.ones(512, dtype=np.float32)

    turn_mgr.interrupt()

    async with turn_mgr.turn_context() as gen_2:
        assert gen_2 > gen_1
        player.play_chunk(chunk_1, generation=gen_1)
        assert player.is_playing() is False
        assert player._queue.empty() is True

        player.play_chunk(np.ones(512, dtype=np.float32) * 2, generation=gen_2)
        assert player.is_playing() is True
        assert player._queue.qsize() == 1


