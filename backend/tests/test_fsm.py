import asyncio
import time
from typing import Any
from unittest.mock import MagicMock
import numpy as np
import pytest

from backend.app.core.state_machine import (
    AssistantState,
    FiniteStateMachine,
    InvalidStateTransitionError,
    TurnBusyError,
    TurnManager,
)
from backend.app.audio.mic_gate import MicGate
from backend.app.audio.playback import AudioPlayer


# ---------------------------------------------------------------------------
# 1. AssistantState & FiniteStateMachine Tests
# ---------------------------------------------------------------------------

def test_assistant_state_enum_members():
    """Verify all 7 canonical states exist and inherit from str."""
    expected_states = {
        "IDLE",
        "LISTENING",
        "TRANSCRIBING",
        "THINKING",
        "TOOL_RUNNING",
        "SPEAKING",
        "ERROR",
    }
    actual_states = {s.value for s in AssistantState}
    assert actual_states == expected_states
    assert len(AssistantState) == 7
    for state in AssistantState:
        assert isinstance(state, str)


def test_fsm_initial_state_idle():
    """Verify FSM initializes in IDLE state."""
    fsm = FiniteStateMachine()
    assert fsm.state == AssistantState.IDLE


def test_fsm_normal_lifecycle_transitions():
    """Verify full normal turn lifecycle: IDLE -> LISTENING -> TRANSCRIBING -> THINKING -> TOOL_RUNNING -> THINKING -> SPEAKING -> IDLE."""
    fsm = FiniteStateMachine()

    fsm.transition_to(AssistantState.LISTENING)
    assert fsm.state == AssistantState.LISTENING

    fsm.transition_to(AssistantState.TRANSCRIBING)
    assert fsm.state == AssistantState.TRANSCRIBING

    fsm.transition_to(AssistantState.THINKING)
    assert fsm.state == AssistantState.THINKING

    fsm.transition_to(AssistantState.TOOL_RUNNING)
    assert fsm.state == AssistantState.TOOL_RUNNING

    fsm.transition_to(AssistantState.THINKING)
    assert fsm.state == AssistantState.THINKING

    fsm.transition_to(AssistantState.SPEAKING)
    assert fsm.state == AssistantState.SPEAKING

    fsm.transition_to(AssistantState.IDLE)
    assert fsm.state == AssistantState.IDLE


@pytest.mark.parametrize(
    "start_state",
    [
        AssistantState.LISTENING,     # silence timeout / empty speech
        AssistantState.TRANSCRIBING,  # empty transcription
        AssistantState.THINKING,      # barge-in / interrupt during thinking
        AssistantState.TOOL_RUNNING,   # interrupt during tool execution
        AssistantState.SPEAKING,      # normal playback finish or interrupt
    ],
)
def test_fsm_early_return_to_idle(start_state: AssistantState):
    """Verify direct recovery / cancellation back to IDLE from intermediate states."""
    fsm = FiniteStateMachine()
    # Walk to start_state
    if start_state == AssistantState.LISTENING:
        fsm.transition_to(AssistantState.LISTENING)
    elif start_state == AssistantState.TRANSCRIBING:
        fsm.transition_to(AssistantState.LISTENING)
        fsm.transition_to(AssistantState.TRANSCRIBING)
    elif start_state == AssistantState.THINKING:
        fsm.transition_to(AssistantState.LISTENING)
        fsm.transition_to(AssistantState.TRANSCRIBING)
        fsm.transition_to(AssistantState.THINKING)
    elif start_state == AssistantState.TOOL_RUNNING:
        fsm.transition_to(AssistantState.LISTENING)
        fsm.transition_to(AssistantState.TRANSCRIBING)
        fsm.transition_to(AssistantState.THINKING)
        fsm.transition_to(AssistantState.TOOL_RUNNING)
    elif start_state == AssistantState.SPEAKING:
        fsm.transition_to(AssistantState.LISTENING)
        fsm.transition_to(AssistantState.TRANSCRIBING)
        fsm.transition_to(AssistantState.THINKING)
        fsm.transition_to(AssistantState.SPEAKING)

    fsm.transition_to(AssistantState.IDLE)
    assert fsm.state == AssistantState.IDLE


@pytest.mark.parametrize(
    "from_state",
    [
        AssistantState.IDLE,
        AssistantState.LISTENING,
        AssistantState.TRANSCRIBING,
        AssistantState.THINKING,
        AssistantState.TOOL_RUNNING,
        AssistantState.SPEAKING,
    ],
)
def test_fsm_wildcard_transition_to_error_and_recovery(from_state: AssistantState):
    """Verify * -> ERROR transition from any state, and ERROR -> IDLE recovery."""
    fsm = FiniteStateMachine()
    # Reach target from_state
    if from_state != AssistantState.IDLE:
        fsm.transition_to(AssistantState.LISTENING)
        if from_state != AssistantState.LISTENING:
            fsm.transition_to(AssistantState.TRANSCRIBING)
            if from_state != AssistantState.TRANSCRIBING:
                fsm.transition_to(AssistantState.THINKING)
                if from_state == AssistantState.TOOL_RUNNING:
                    fsm.transition_to(AssistantState.TOOL_RUNNING)
                elif from_state == AssistantState.SPEAKING:
                    fsm.transition_to(AssistantState.SPEAKING)

    assert fsm.state == from_state

    # Wildcard -> ERROR
    fsm.transition_to(AssistantState.ERROR)
    assert fsm.state == AssistantState.ERROR

    # Recovery -> IDLE
    fsm.transition_to(AssistantState.IDLE)
    assert fsm.state == AssistantState.IDLE


@pytest.mark.parametrize(
    "source,target",
    [
        (AssistantState.IDLE, AssistantState.TRANSCRIBING),
        (AssistantState.IDLE, AssistantState.THINKING),
        (AssistantState.IDLE, AssistantState.TOOL_RUNNING),
        (AssistantState.IDLE, AssistantState.SPEAKING),
        (AssistantState.LISTENING, AssistantState.SPEAKING),
        (AssistantState.LISTENING, AssistantState.TOOL_RUNNING),
        (AssistantState.TRANSCRIBING, AssistantState.SPEAKING),
        (AssistantState.SPEAKING, AssistantState.LISTENING),
        (AssistantState.SPEAKING, AssistantState.THINKING),
        (AssistantState.SPEAKING, AssistantState.TOOL_RUNNING),
        (AssistantState.ERROR, AssistantState.LISTENING),
        (AssistantState.ERROR, AssistantState.SPEAKING),
    ],
)
def test_fsm_invalid_transitions_raise_error(source: AssistantState, target: AssistantState):
    """Verify attempting unauthorized transitions raises InvalidStateTransitionError."""
    fsm = FiniteStateMachine()
    # Force state for testing source -> target
    fsm._state = source

    with pytest.raises(InvalidStateTransitionError) as exc_info:
        fsm.transition_to(target)

    assert str(source.value) in str(exc_info.value)
    assert str(target.value) in str(exc_info.value)


def test_fsm_accepts_strings_and_enum_identically():
    """Verify transition_to accepts string literals and AssistantState enums seamlessly."""
    fsm = FiniteStateMachine()
    fsm.transition_to("LISTENING")
    assert fsm.state == AssistantState.LISTENING
    assert fsm.state == "LISTENING"

    fsm.transition_to("TRANSCRIBING")
    assert fsm.state == AssistantState.TRANSCRIBING


def test_fsm_listeners_dispatched_with_turn_id():
    """Verify registered callbacks receive (prev_state, new_state, turn_id)."""
    fsm = FiniteStateMachine()
    events = []

    def on_change(prev, new, turn_id):
        events.append((prev, new, turn_id))

    fsm.add_listener(on_change)

    fsm.transition_to(AssistantState.LISTENING, turn_id=42)
    fsm.transition_to(AssistantState.TRANSCRIBING, turn_id=42)

    assert events == [
        (AssistantState.IDLE, AssistantState.LISTENING, 42),
        (AssistantState.LISTENING, AssistantState.TRANSCRIBING, 42),
    ]

    # Remove listener
    fsm.remove_listener(on_change)
    fsm.transition_to(AssistantState.IDLE, turn_id=42)
    assert len(events) == 2  # No new event after removal


def test_fsm_rejects_non_integer_turn_id():
    """Verify transition_to rejects non-integer turn_id values (strings, booleans)."""
    fsm = FiniteStateMachine()

    with pytest.raises(TypeError):
        fsm.transition_to(AssistantState.LISTENING, turn_id="turn-42")

    with pytest.raises(TypeError):
        fsm.transition_to(AssistantState.LISTENING, turn_id=True)



# ---------------------------------------------------------------------------
# 2. TurnManager Mutex & Concurrency Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_turn_manager_initial_state():
    """Verify TurnManager initialized with zero counter, unlocked mutex, and cleared abort flag."""
    tm = TurnManager()
    assert tm.generation_counter == 0
    assert tm.turn_lock is not None
    assert tm.turn_lock.locked() is False
    assert tm.is_interrupted is False


@pytest.mark.asyncio
async def test_turn_manager_mutex_serializes_concurrent_turns():
    """Verify turn_lock guarantees mutual exclusion for concurrent turn requests."""
    tm = TurnManager()
    execution_order = []

    async def simulate_turn(turn_num: int, duration_sec: float):
        async with tm.turn_context():
            execution_order.append(f"start_{turn_num}")
            await asyncio.sleep(duration_sec)
            execution_order.append(f"end_{turn_num}")

    # Launch two turns concurrently
    await asyncio.gather(
        simulate_turn(1, 0.05),
        simulate_turn(2, 0.02),
    )

    # Turn 1 must completely finish before Turn 2 enters
    assert execution_order == ["start_1", "end_1", "start_2", "end_2"]
    assert tm.generation_counter == 2


@pytest.mark.asyncio
async def test_turn_manager_reject_when_busy():
    """Verify reject_if_busy=True raises TurnBusyError when mutex is locked."""
    tm = TurnManager()

    async def slow_turn():
        async with tm.turn_context():
            await asyncio.sleep(0.1)

    task = asyncio.create_task(slow_turn())
    await asyncio.sleep(0.01)  # Allow slow_turn to acquire lock

    with pytest.raises(TurnBusyError):
        async with tm.turn_context(reject_if_busy=True):
            pass

    await task


# ---------------------------------------------------------------------------
# 3. Invariant #9: Interrupt, Generation Counter & Playback Cancellation
# ---------------------------------------------------------------------------

def test_turn_manager_interrupt_honors_invariant_09():
    """Invariant #9: interrupt() increments generation_counter, cancels playback, but never directly mutates FSM."""
    fsm = FiniteStateMachine()
    # Advance FSM to SPEAKING
    fsm.transition_to(AssistantState.LISTENING)
    fsm.transition_to(AssistantState.TRANSCRIBING)
    fsm.transition_to(AssistantState.THINKING)
    fsm.transition_to(AssistantState.SPEAKING)

    player = AudioPlayer()
    for _ in range(3):
        player.play_chunk(np.zeros(512, dtype=np.float32))
    assert player.queue.qsize() == 3

    mic_gate = MicGate()
    assert mic_gate.is_open() is False

    tm = TurnManager(fsm=fsm, playback=player, mic_gate=mic_gate)
    assert tm.generation_counter == 0
    assert tm.is_interrupted is False

    # Execute interrupt
    tm.interrupt()

    # 1. Generation counter incremented
    assert tm.generation_counter == 1
    # 2. Interrupted flag set
    assert tm.is_interrupted is True
    # 3. Playback queue drained / cancelled
    assert player.queue.qsize() == 0
    # 4. CRITICAL (Invariant #9): FSM was NOT mutated directly by interrupt()!
    assert fsm.state == AssistantState.SPEAKING
    # 5. MicGate was NOT unmuted directly by interrupt()!
    assert mic_gate.is_open() is False


@pytest.mark.asyncio
async def test_turn_manager_interrupt_is_awaitable_and_cleared_on_next_turn():
    """Verify interrupt can be awaited or called synchronously, and is_interrupted resets on next turn."""
    tm = TurnManager()
    await tm.interrupt()
    assert tm.generation_counter == 1
    assert tm.is_interrupted is True

    # Next turn context should reset is_interrupted and increment generation_counter
    async with tm.turn_context() as gen_id:
        assert gen_id == 2
        assert tm.generation_counter == 2
        assert tm.is_interrupted is False


# ---------------------------------------------------------------------------
# 4. GAP-04 & ADR-0008: 250ms Acoustic Cooldown & Silero VAD State Reset
# ---------------------------------------------------------------------------

class _SpyVAD:
    """Spy recorder for Silero VAD state resets."""
    def __init__(self):
        self.reset_called = False
        self.call_log = []

    def reset_state(self):
        self.reset_called = True
        self.call_log.append("reset_state")


class _SpyMicGate:
    """Spy recorder for MicGate opening."""
    def __init__(self):
        self.is_opened = False
        self.call_log = []

    def open(self):
        self.is_opened = True
        self.call_log.append("open")


@pytest.mark.asyncio
async def test_turn_manager_enforce_acoustic_cooldown_order_and_delay_gap04():
    """GAP-04 & ADR-0008: Cooldown delays 250ms, resets VAD recurrent state, then opens MicGate in strict order."""
    timeline = []

    class EventSpyVAD:
        def reset_state(self):
            timeline.append(("vad_reset", time.perf_counter()))

    class EventSpyGate:
        def open(self):
            timeline.append(("gate_open", time.perf_counter()))

    vad = EventSpyVAD()
    mic_gate = EventSpyGate()
    tm = TurnManager(vad=vad, mic_gate=mic_gate)

    t_start = time.perf_counter()
    # Cooldown 0.1s for test velocity
    await tm.enforce_acoustic_cooldown(cooldown_sec=0.1)
    t_end = time.perf_counter()

    elapsed = t_end - t_start
    assert elapsed >= 0.09, f"Acoustic cooldown sleep too short: {elapsed:.4f}s"

    assert len(timeline) == 2
    # 1. VAD state reset must happen
    assert timeline[0][0] == "vad_reset"
    # 2. Gate open must happen after VAD reset
    assert timeline[1][0] == "gate_open"
    # Delay occurred before VAD reset
    assert timeline[0][1] - t_start >= 0.09


@pytest.mark.asyncio
async def test_turn_manager_enforce_acoustic_cooldown_with_explicit_args():
    """Verify enforce_acoustic_cooldown accepts explicit vad and mic_gate instances."""
    tm = TurnManager()  # empty manager
    spy_vad = _SpyVAD()
    spy_gate = _SpyMicGate()

    await tm.enforce_acoustic_cooldown(vad=spy_vad, mic_gate=spy_gate, cooldown_sec=0.01)

    assert spy_vad.reset_called is True
    assert spy_gate.is_opened is True


@pytest.mark.asyncio
async def test_enforce_acoustic_cooldown_cancellation_guarantees_cleanup_and_duration():
    """Verify acoustic cooldown preserves decay duration and executes cleanup on task cancellation."""
    fsm = TurnManager()
    mock_vad = MagicMock()
    mock_vad.reset_state = MagicMock()

    class MockMicGate:
        def __init__(self):
            self._is_open = False

        def is_open(self) -> bool:
            return self._is_open

        def open(self):
            self._is_open = True

    mock_gate = MockMicGate()
    assert mock_gate.is_open() is False

    t_start = time.perf_counter()
    task = asyncio.create_task(
        fsm.enforce_acoustic_cooldown(vad=mock_vad, mic_gate=mock_gate, cooldown_sec=0.1)
    )

    await asyncio.sleep(0.01)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    t_end = time.perf_counter()

    assert mock_gate.is_open() is True
    assert mock_vad.reset_state.called is True
    assert t_end - t_start >= 0.1

