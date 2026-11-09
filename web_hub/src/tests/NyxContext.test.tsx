import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import React from 'react';
import {
  nyxReducer,
  initialNyxState,
  NyxProvider,
  useNyx,
  type NyxState,
  type NyxAction,
} from '../context/NyxContext';

describe('NyxContext & nyxReducer', () => {
  describe('nyxReducer State Transitions', () => {
    it('initializes with default IDLE state and turn_id 0', () => {
      expect(initialNyxState.assistantState).toBe('IDLE');
      expect(initialNyxState.activeTurnId).toBe(0);
      expect(initialNyxState.emotion).toBe('neutral');
      expect(initialNyxState.isMuted).toBe(false);
      expect(initialNyxState.messages).toEqual([]);
      expect(initialNyxState.latestLatency).toBeNull();
      expect(initialNyxState.lastError).toBeNull();
    });

    it('handles state_change transition to LISTENING with new turn_id', () => {
      const action: NyxAction = {
        type: 'SERVER_EVENT',
        event: {
          type: 'state_change',
          payload: { state: 'LISTENING', turn_id: 1, timestamp: 1731000000 },
        },
      };

      const newState = nyxReducer(initialNyxState, action);

      expect(newState.assistantState).toBe('LISTENING');
      expect(newState.activeTurnId).toBe(1);
    });

    it('enforces monotonic turn_id drop: rejects stale packets where event.turn_id < activeTurnId', () => {
      const currentState: NyxState = {
        ...initialNyxState,
        assistantState: 'THINKING',
        activeTurnId: 5,
        messages: [{ id: 'm1', sender: 'assistant', text: 'Active turn 5', turnId: 5 }],
      };

      // Stale packet from turn 4 arriving late
      const staleAction: NyxAction = {
        type: 'SERVER_EVENT',
        event: {
          type: 'text_delta',
          payload: { delta: ' delayed text', accumulated: 'stale text', turn_id: 4 },
        },
      };

      const stateAfterStale = nyxReducer(currentState, staleAction);

      // Must be completely unchanged
      expect(stateAfterStale).toEqual(currentState);
      expect(stateAfterStale.activeTurnId).toBe(5);
      expect(stateAfterStale.messages[0].text).toBe('Active turn 5');
    });

    it('accumulates stream deltas for active turn assistant message', () => {
      let state: NyxState = {
        ...initialNyxState,
        assistantState: 'SPEAKING',
        activeTurnId: 2,
      };

      // First chunk
      state = nyxReducer(state, {
        type: 'SERVER_EVENT',
        event: {
          type: 'text_delta',
          payload: { delta: 'Good ', accumulated: 'Good ', turn_id: 2 },
        },
      });

      expect(state.messages).toHaveLength(1);
      expect(state.messages[0].text).toBe('Good ');
      expect(state.messages[0].isStreaming).toBe(true);

      // Second chunk
      state = nyxReducer(state, {
        type: 'SERVER_EVENT',
        event: {
          type: 'text_delta',
          payload: { delta: 'evening.', accumulated: 'Good evening.', turn_id: 2 },
        },
      });

      expect(state.messages).toHaveLength(1);
      expect(state.messages[0].text).toBe('Good evening.');
      expect(state.messages[0].isStreaming).toBe(true);
    });

    it('handles barge-in interrupt: marks active stream finalized, resets emotion to neutral, and sets state to IDLE', () => {
      const activeState: NyxState = {
        ...initialNyxState,
        assistantState: 'SPEAKING',
        emotion: 'happy',
        activeTurnId: 3,
        messages: [{ id: 'msg-3', sender: 'assistant', text: 'Partially spoken response...', turnId: 3, isStreaming: true }],
      };

      const interruptedState = nyxReducer(activeState, { type: 'INTERRUPT' });

      expect(interruptedState.assistantState).toBe('IDLE');
      expect(interruptedState.emotion).toBe('neutral');
      expect(interruptedState.messages[0].isStreaming).toBe(false);
      expect(interruptedState.messages[0].text).toBe('Partially spoken response...');
    });

    it('resets emotion to neutral when state_change transitions back to IDLE', () => {
      const activeSpeakingState: NyxState = {
        ...initialNyxState,
        assistantState: 'SPEAKING',
        emotion: 'happy',
        activeTurnId: 2,
      };

      const action: NyxAction = {
        type: 'SERVER_EVENT',
        event: {
          type: 'state_change',
          payload: { state: 'IDLE', turn_id: 2, timestamp: 1731000005 },
        },
      };

      const nextState = nyxReducer(activeSpeakingState, action);

      expect(nextState.assistantState).toBe('IDLE');
      expect(nextState.emotion).toBe('neutral');
    });

    it('resets emotion to neutral on INTERRUPT', () => {
      const activeSpeakingState: NyxState = {
        ...initialNyxState,
        assistantState: 'SPEAKING',
        emotion: 'sad',
        activeTurnId: 4,
      };

      const interruptedState = nyxReducer(activeSpeakingState, { type: 'INTERRUPT' });

      expect(interruptedState.assistantState).toBe('IDLE');
      expect(interruptedState.emotion).toBe('neutral');
    });

    it('updates mute state when server broadcasts mute_state', () => {
      const action: NyxAction = {
        type: 'SERVER_EVENT',
        event: {
          type: 'mute_state',
          payload: { muted: true, timestamp: 1731000001 },
        },
      };

      const state = nyxReducer(initialNyxState, action);
      expect(state.isMuted).toBe(true);
    });

    it('toggles mute state with explicit value or flips current state when omitted', () => {
      let state = nyxReducer(initialNyxState, { type: 'TOGGLE_MUTE', muted: true });
      expect(state.isMuted).toBe(true);

      state = nyxReducer(state, { type: 'TOGGLE_MUTE', muted: false });
      expect(state.isMuted).toBe(false);

      state = nyxReducer(state, { type: 'TOGGLE_MUTE' });
      expect(state.isMuted).toBe(true);

      state = nyxReducer(state, { type: 'TOGGLE_MUTE' });
      expect(state.isMuted).toBe(false);
    });

    it('records telemetry metrics for current turn', () => {
      const stateWithTurn: NyxState = {
        ...initialNyxState,
        activeTurnId: 7,
      };

      const metricAction: NyxAction = {
        type: 'SERVER_EVENT',
        event: {
          type: 'latency_metric',
          payload: {
            turn_id: 7,
            vad_ms: 120,
            stt_ms: 250,
            llm_ttft_ms: 310,
            tts_chunk1_ms: 180,
            total_ttfa_ms: 860,
          },
        },
      };

      const result = nyxReducer(stateWithTurn, metricAction);
      expect(result.latestLatency).not.toBeNull();
      expect(result.latestLatency?.total_ttfa_ms).toBe(860);
    });

    it('handles server error event: sets assistantState to ERROR, emotion to sad, sets lastError, and stops streaming messages', () => {
      const activeState: NyxState = {
        ...initialNyxState,
        assistantState: 'SPEAKING',
        emotion: 'happy',
        activeTurnId: 4,
        messages: [
          {
            id: 'm1',
            sender: 'assistant',
            text: 'Stream interrupted by fault',
            turnId: 4,
            isStreaming: true,
          },
          {
            id: 'm0',
            sender: 'user',
            text: 'Prior message',
            turnId: 3,
            isStreaming: false,
          },
        ],
      };

      const errorAction: NyxAction = {
        type: 'SERVER_EVENT',
        event: {
          type: 'error',
          payload: {
            code: 'INFERENCE_TIMEOUT',
            message: 'Model execution timed out after 30s',
            turn_id: 4,
          },
        },
      };

      const newState = nyxReducer(activeState, errorAction);

      expect(newState.assistantState).toBe('ERROR');
      expect(newState.emotion).toBe('sad');
      expect(newState.lastError).toEqual({
        code: 'INFERENCE_TIMEOUT',
        message: 'Model execution timed out after 30s',
        turn_id: 4,
      });
      expect(newState.messages[0].isStreaming).toBe(false);
      expect(newState.messages[0].text).toBe('Stream interrupted by fault');
      expect(newState.messages[1].isStreaming).toBe(false);
    });
  });

  describe('NyxProvider & useNyx Hook', () => {
    it('provides nyx state and action dispatchers to consumer components', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <NyxProvider>{children}</NyxProvider>
      );

      const { result } = renderHook(() => useNyx(), { wrapper });

      expect(result.current.state.assistantState).toBe('IDLE');
      expect(typeof result.current.sendText).toBe('function');
      expect(typeof result.current.toggleMute).toBe('function');
      expect(typeof result.current.interrupt).toBe('function');

      act(() => {
        result.current.interrupt();
      });

      expect(result.current.state.assistantState).toBe('IDLE');
    });

    it('throws descriptive error if useNyx is called outside of NyxProvider', () => {
      expect(() => {
        renderHook(() => useNyx());
      }).toThrow(/useNyx must be used within a NyxProvider/i);
    });

    it('does not poison activeTurnId to NaN when receiving non-numeric turn_id', () => {
      const wrapper = ({ children }: { children: React.ReactNode }) => (
        <NyxProvider>{children}</NyxProvider>
      );

      const { result } = renderHook(
        () => {
          const nyx = useNyx();
          return {
            ...nyx.state,
            dispatch: nyx.dispatch,
          };
        },
        { wrapper }
      );

      act(() => {
        result.current.dispatch({
          type: 'SERVER_EVENT',
          event: {
            type: 'state_change',
            payload: { state: 'LISTENING', turn_id: 'turn-42' as unknown as number },
          } as any,
        });
      });

      expect(result.current.activeTurnId).toBe(0);
      expect(Number.isNaN(result.current.activeTurnId)).toBe(false);
    });
  });
});
