export type AssistantState =
  | 'IDLE'
  | 'LISTENING'
  | 'TRANSCRIBING'
  | 'THINKING'
  | 'TOOL_RUNNING'
  | 'SPEAKING'
  | 'ERROR';

export type EmotionState =
  | 'neutral'
  | 'happy'
  | 'sad'
  | 'surprised'
  | 'thinking';

// ============================================================================
// Server -> Client Inbound Event Envelopes
// ============================================================================

export interface StateChangeEvent {
  readonly type: 'state_change';
  readonly payload: {
    readonly state: AssistantState;
    readonly turn_id: number;
    readonly timestamp?: number;
  };
}

export interface LipsyncEvent {
  readonly type: 'lipsync';
  readonly payload: {
    readonly is_mouth_open: boolean;
    readonly amplitude: number;
    readonly turn_id: number;
  };
}

export interface EmotionEvent {
  readonly type: 'emotion';
  readonly payload: {
    readonly emotion: EmotionState;
    readonly turn_id: number;
  };
}

export interface TextDeltaEvent {
  readonly type: 'text_delta';
  readonly payload: {
    readonly delta: string;
    readonly accumulated: string;
    readonly turn_id: number;
  };
}

export interface LatencyMetricEvent {
  readonly type: 'latency_metric';
  readonly payload: {
    readonly turn_id: number;
    readonly vad_ms: number;
    readonly stt_ms: number;
    readonly llm_ttft_ms: number;
    readonly tts_chunk1_ms: number;
    readonly total_ttfa_ms: number;
  };
}

export interface MuteStateEvent {
  readonly type: 'mute_state';
  readonly payload: {
    readonly muted: boolean;
    readonly timestamp?: number;
  };
}

export interface ErrorEvent {
  readonly type: 'error';
  readonly payload: {
    readonly code: string;
    readonly message: string;
    readonly turn_id?: number;
  };
}

export interface PongEvent {
  readonly type: 'pong';
  readonly payload: {
    readonly timestamp: number;
  };
}

export type ServerEvent =
  | StateChangeEvent
  | LipsyncEvent
  | EmotionEvent
  | TextDeltaEvent
  | LatencyMetricEvent
  | MuteStateEvent
  | ErrorEvent
  | PongEvent;

// ============================================================================
// Client -> Server Outbound Command Envelopes (Flat)
// ============================================================================

export interface SendTextCommand {
  readonly action: 'send_text';
  readonly text: string;
}

export interface InterruptCommand {
  readonly action: 'interrupt';
  readonly reason?: string;
}

export interface MuteToggleCommand {
  readonly action: 'mute_toggle';
  readonly muted: boolean;
}

export interface PingCommand {
  readonly action: 'ping';
  readonly timestamp?: number;
}

export type ClientCommand =
  | SendTextCommand
  | InterruptCommand
  | MuteToggleCommand
  | PingCommand;
