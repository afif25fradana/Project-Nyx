import React, { createContext, useContext, useReducer, useEffect, useMemo, type ReactNode } from 'react';
import { flushSync } from 'react-dom';
import type {
  AssistantState,
  EmotionState,
  LatencyMetricEvent,
  ServerEvent,
  ErrorEvent,
} from '../types/websocket';
import { NyxWebSocketClient } from '../services/websocket';

export type LatencyMetric = LatencyMetricEvent['payload'];

export interface NyxMessage {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  turnId?: number;
  isStreaming?: boolean;
  timestamp?: number;
}

export interface NyxState {
  assistantState: AssistantState;
  activeTurnId: number;
  emotion: EmotionState;
  isMuted: boolean;
  messages: NyxMessage[];
  latestLatency: LatencyMetric | null;
  lastError: ErrorEvent['payload'] | null;
}

export const initialNyxState: NyxState = {
  assistantState: 'IDLE',
  activeTurnId: 0,
  emotion: 'neutral',
  isMuted: false,
  messages: [],
  latestLatency: null,
  lastError: null,
};

export type NyxAction =
  | { type: 'SERVER_EVENT'; event: ServerEvent }
  | { type: 'INTERRUPT' }
  | { type: 'SEND_TEXT'; text: string }
  | { type: 'TOGGLE_MUTE'; muted?: boolean };

export function nyxReducer(
  state: NyxState,
  action: NyxAction
): NyxState {
  switch (action.type) {
    case 'SERVER_EVENT': {
      const { event } = action;

      // Monotonic turn_id sequence validation:
      // Drop any frame where event.payload.turn_id < state.activeTurnId
      if (
        'payload' in event &&
        event.payload &&
        typeof (event.payload as { turn_id?: unknown }).turn_id === 'number' &&
        Number.isFinite((event.payload as { turn_id: number }).turn_id)
      ) {
        const payloadTurnId = (event.payload as { turn_id: number }).turn_id;
        if (payloadTurnId < state.activeTurnId) {
          return state;
        }
      }

      switch (event.type) {
        case 'state_change': {
          const rawTurnId = event.payload.turn_id;
          const newTurnId =
            typeof rawTurnId === 'number' && Number.isFinite(rawTurnId)
              ? Math.max(state.activeTurnId, rawTurnId)
              : state.activeTurnId;
          const isReturningToIdle = event.payload.state === 'IDLE';

          return {
            ...state,
            assistantState: event.payload.state,
            activeTurnId: newTurnId,
            emotion: isReturningToIdle ? 'neutral' : state.emotion,
            messages: isReturningToIdle
              ? state.messages.map((m) =>
                  m.isStreaming ? { ...m, isStreaming: false } : m
                )
              : state.messages,
          };
        }

        case 'text_delta': {
          const { delta, accumulated, turn_id } = event.payload;
          const existingIndex = state.messages.findIndex(
            (m) => m.turnId === turn_id && m.sender === 'assistant'
          );

          let updatedMessages: NyxMessage[];
          if (existingIndex >= 0) {
            updatedMessages = state.messages.map((msg, idx) => {
              if (idx === existingIndex) {
                return {
                  ...msg,
                  text: accumulated || msg.text + delta,
                  isStreaming: true,
                };
              }
              return msg;
            });
          } else {
            updatedMessages = [
              ...state.messages,
              {
                id: `assistant-turn-${turn_id}`,
                sender: 'assistant',
                text: accumulated || delta,
                turnId: turn_id,
                isStreaming: true,
                timestamp: Date.now(),
              },
            ];
          }

          return {
            ...state,
            activeTurnId:
              typeof turn_id === 'number' && Number.isFinite(turn_id)
                ? Math.max(state.activeTurnId, turn_id)
                : state.activeTurnId,
            messages: updatedMessages,
          };
        }

        case 'mute_state':
          return {
            ...state,
            isMuted: event.payload.muted,
          };

        case 'latency_metric':
          return {
            ...state,
            latestLatency: event.payload,
          };

        case 'emotion':
          return {
            ...state,
            emotion: event.payload.emotion,
          };

        case 'error':
          return {
            ...state,
            assistantState: 'ERROR',
            emotion: 'sad',
            lastError: event.payload,
            messages: state.messages.map((m) =>
              m.isStreaming ? { ...m, isStreaming: false } : m
            ),
          };

        default:
          return state;
      }
    }

    case 'INTERRUPT': {
      return {
        ...state,
        assistantState: 'IDLE',
        emotion: 'neutral',
        messages: state.messages.map((msg) =>
          msg.isStreaming ? { ...msg, isStreaming: false } : msg
        ),
      };
    }

    case 'SEND_TEXT': {
      const userMessage: NyxMessage = {
        id: `user-${Date.now()}`,
        sender: 'user',
        text: action.text,
        turnId: state.activeTurnId + 1,
        timestamp: Date.now(),
      };
      return {
        ...state,
        messages: [...state.messages, userMessage],
      };
    }

    case 'TOGGLE_MUTE': {
      return {
        ...state,
        isMuted: action.muted ?? !state.isMuted,
      };
    }

    default:
      return state;
  }
}

export interface NyxContextValue {
  state: NyxState;
  dispatch: React.Dispatch<NyxAction>;
  client?: NyxWebSocketClient;
  sendText: (text: string) => void;
  toggleMute: (muted?: boolean) => void;
  interrupt: () => void;
}

const NyxContext = createContext<NyxContextValue | null>(null);

export interface NyxProviderProps {
  children: ReactNode;
  client?: NyxWebSocketClient;
}

export const NyxProvider: React.FC<NyxProviderProps> = ({
  children,
  client,
}) => {
  const [state, dispatch] = useReducer(nyxReducer, initialNyxState);

  useEffect(() => {
    if (!client) return;

    const unsubscribe = client.onEvent((event) => {
      try {
        flushSync(() => {
          dispatch({ type: 'SERVER_EVENT', event });
        });
      } catch {
        dispatch({ type: 'SERVER_EVENT', event });
      }
    });

    return unsubscribe;
  }, [client]);

  const sendText = (text: string) => {
    dispatch({ type: 'SEND_TEXT', text });
    client?.sendText(text);
  };

  const toggleMute = (muted?: boolean) => {
    const targetMuted = typeof muted === 'boolean' ? muted : !state.isMuted;
    dispatch({ type: 'TOGGLE_MUTE', muted: targetMuted });
    client?.toggleMute(targetMuted);
  };

  const interrupt = () => {
    dispatch({ type: 'INTERRUPT' });
    client?.interrupt();
  };

  const value = useMemo<NyxContextValue>(
    () => ({
      state,
      dispatch,
      client,
      sendText,
      toggleMute,
      interrupt,
    }),
    [state, client]
  );

  return (
    <NyxContext.Provider value={value}>
      {children}
    </NyxContext.Provider>
  );
};

export function useNyx(): NyxContextValue {
  const context = useContext(NyxContext);
  if (!context) {
    throw new Error('useNyx must be used within a NyxProvider');
  }
  return context;
}
