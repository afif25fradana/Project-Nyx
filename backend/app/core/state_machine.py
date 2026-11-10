"""7-State Finite State Machine and TurnManager Concurrency Engine.

Enforces strict lifecycle transitions, turn mutual exclusion,
monotonic generation counting, barge-in interrupt handling, and
post-playback 250ms acoustic cooldown with Silero VAD state reset.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from enum import Enum
import logging
import threading
import time
from typing import Any

logger = logging.getLogger(__name__)


class AssistantState(str, Enum):
    """Canonical 7-state runtime lifecycle."""
    IDLE = "IDLE"
    LISTENING = "LISTENING"
    TRANSCRIBING = "TRANSCRIBING"
    THINKING = "THINKING"
    TOOL_RUNNING = "TOOL_RUNNING"
    SPEAKING = "SPEAKING"
    ERROR = "ERROR"


class InvalidStateTransitionError(Exception):
    """Raised when an illegal FSM state transition is attempted."""


class TurnBusyError(Exception):
    """Raised when attempting to execute a turn while another turn holds the mutex."""


class _CompletedAwaitable:
    """Awaitable helper enabling methods to be awaited or invoked synchronously."""

    def __await__(self):
        async def _dummy():
            return None
        return _dummy().__await__()


# Pre-defined valid transition matrix
_VALID_TRANSITIONS: dict[AssistantState, set[AssistantState]] = {
    AssistantState.IDLE: {
        AssistantState.LISTENING,
        AssistantState.ERROR,
    },
    AssistantState.LISTENING: {
        AssistantState.TRANSCRIBING,
        AssistantState.IDLE,  # silence timeout / empty speech
        AssistantState.ERROR,
    },
    AssistantState.TRANSCRIBING: {
        AssistantState.THINKING,
        AssistantState.IDLE,  # empty transcription
        AssistantState.ERROR,
    },
    AssistantState.THINKING: {
        AssistantState.TOOL_RUNNING,
        AssistantState.SPEAKING,
        AssistantState.IDLE,  # barge-in / interrupt during thinking
        AssistantState.ERROR,
    },
    AssistantState.TOOL_RUNNING: {
        AssistantState.THINKING,
        AssistantState.IDLE,  # interrupt during tool running
        AssistantState.ERROR,
    },
    AssistantState.SPEAKING: {
        AssistantState.IDLE,  # playback finished or interrupted
        AssistantState.ERROR,
    },
    AssistantState.ERROR: {
        AssistantState.IDLE,  # recovery
        AssistantState.ERROR,
    },
}


class FiniteStateMachine:
    """Thread-safe 7-state Finite State Machine with listener notifications."""

    def __init__(self, initial_state: AssistantState = AssistantState.IDLE) -> None:
        self._state: AssistantState = AssistantState(initial_state)
        self._lock = threading.Lock()
        self._listeners: list[Callable[[AssistantState, AssistantState, int], Any]] = []
        self._bg_tasks: set[asyncio.Task[Any]] = set()

    @property
    def state(self) -> AssistantState:
        with self._lock:
            return self._state

    def add_listener(
        self, callback: Callable[[AssistantState, AssistantState, int], Any]
    ) -> None:
        """Register a callback invoked on state transitions."""
        with self._lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(
        self, callback: Callable[[AssistantState, AssistantState, int], Any]
    ) -> None:
        """Unregister a previously registered callback."""
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def transition_to(
        self, target_state: AssistantState | str, turn_id: int = 0
    ) -> None:
        """Attempt to transition to target_state, notifying listeners on success."""
        if type(turn_id) is not int or isinstance(turn_id, bool):
            raise TypeError(f"turn_id must be an int, got {type(turn_id).__name__}")

        try:
            target = AssistantState(target_state)
        except ValueError as err:
            raise InvalidStateTransitionError(
                f"Unknown assistant state '{target_state}'"
            ) from err

        with self._lock:
            current = self._state
            allowed = _VALID_TRANSITIONS.get(current, set())
            if target not in allowed:
                raise InvalidStateTransitionError(
                    f"Cannot transition from {current.value} to {target.value}"
                )

            self._state = target
            listeners_snapshot = list(self._listeners)

        # Dispatch listeners outside the lock
        for listener in listeners_snapshot:
            try:
                res = listener(current, target, turn_id)
                if asyncio.iscoroutine(res):
                    try:
                        loop = asyncio.get_running_loop()
                        task = loop.create_task(res)
                        self._bg_tasks.add(task)
                        task.add_done_callback(self._bg_tasks.discard)
                    except RuntimeError:
                        pass
            except Exception:
                logger.exception("Exception in state machine listener callback")

    def transition(
        self, event: str, turn_id: int = 0
    ) -> None:
        """Alias for transition_to."""
        self.transition_to(event, turn_id)


class TurnManager:
    """Orchestrates turn lifecycle, concurrency mutex, and acoustic cooldown."""

    def __init__(
        self,
        fsm: FiniteStateMachine | None = None,
        vad: Any = None,
        mic_gate: Any = None,
        playback: Any = None,
        player: Any = None,
        transcriber: Any = None,
    ) -> None:
        self._fsm = fsm
        self._vad = vad
        self._mic_gate = mic_gate
        self._playback = playback if playback is not None else player
        self._transcriber = transcriber

        self.turn_lock = asyncio.Lock()
        self._turn_lock = self.turn_lock
        self.generation_counter = 0
        self._generation_counter = 0
        self._turn_abort_event = asyncio.Event()

    @property
    def is_interrupted(self) -> bool:
        """True if the active turn received an abort/interrupt signal."""
        return self._turn_abort_event.is_set()

    @property
    def turn_abort_event(self) -> asyncio.Event:
        """Expose internal asyncio event for task cancellation checks."""
        return self._turn_abort_event

    def interrupt(self) -> _CompletedAwaitable:
        """Signal barge-in interrupt.

        Honors Invariant #9: Increments generation_counter and cancels playback,
        without mutating FSM state or reopening MicGate directly.
        """
        self.generation_counter += 1
        self._generation_counter = self.generation_counter
        self._turn_abort_event.set()

        if self._playback is not None and hasattr(self._playback, "cancel"):
            self._playback.cancel()

        return _CompletedAwaitable()

    class _TurnContextManager:
        def __init__(self, manager: TurnManager, reject_if_busy: bool = False):
            self._manager = manager
            self._reject_if_busy = reject_if_busy
            self._acquired = False

        async def __aenter__(self) -> int:
            if self._reject_if_busy and self._manager.turn_lock.locked():
                raise TurnBusyError("TurnManager is busy with an active turn.")

            await self._manager.turn_lock.acquire()
            self._acquired = True
            self._manager.generation_counter += 1
            self._manager._generation_counter = self._manager.generation_counter
            self._manager._turn_abort_event.clear()
            if self._manager._playback is not None and hasattr(self._manager._playback, "reset"):
                self._manager._playback.reset(generation=self._manager.generation_counter)
            return self._manager.generation_counter

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            if self._acquired:
                self._manager.turn_lock.release()

    def turn_context(self, reject_if_busy: bool = False):
        """Async context manager acquiring turn_lock with monotonic counter increment."""
        return self._TurnContextManager(self, reject_if_busy=reject_if_busy)

    async def enforce_acoustic_cooldown(
        self,
        vad: Any = None,
        mic_gate: Any = None,
        cooldown_sec: float = 0.25,
    ) -> None:
        """Post-playback acoustic cooldown and Silero VAD state reset ([GAP-04], [ADR-0008]).

        Guarantees the full cooldown_sec decay window elapses before resetting VAD
        and reopening MicGate, even if the enclosing task receives cancellation.
        Propagates CancelledError to the caller once cleanup is complete.
        """
        target_vad = vad if vad is not None else self._vad
        target_gate = mic_gate if mic_gate is not None else self._mic_gate

        cancelled_exc: asyncio.CancelledError | None = None

        if cooldown_sec > 0:
            target_deadline = time.perf_counter() + cooldown_sec
            while True:
                remaining = target_deadline - time.perf_counter()
                if remaining <= 0:
                    break
                try:
                    await asyncio.sleep(remaining)
                    break
                except asyncio.CancelledError as exc:
                    cancelled_exc = exc

        if target_vad is not None and hasattr(target_vad, "reset_state"):
            target_vad.reset_state()

        if target_gate is not None and hasattr(target_gate, "open"):
            target_gate.open()

        if cancelled_exc is not None:
            raise cancelled_exc

