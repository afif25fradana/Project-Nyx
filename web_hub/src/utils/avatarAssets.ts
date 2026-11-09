import type { AssistantState, EmotionState } from '../types/websocket';

export type AvatarVideoKey =
  | 'idle'
  | 'idle_smoking'
  | 'idle_bed'
  | 'muted'
  | 'listening'
  | 'thinking'
  | 'talk'
  | 'happy'
  | 'sad';

export const AVATAR_VIDEOS = {
  idle: '/avatar/idle.webm',
  idle_smoking: '/avatar/idle_smoking.webm',
  idle_bed: '/avatar/idle-bed.webm',
  muted: '/avatar/muted.webm',
  listening: '/avatar/listening.webm',
  thinking: '/avatar/thinking.webm',
  talk: '/avatar/talk.webm',
  happy: '/avatar/happy.webm',
  sad: '/avatar/sad.webm',
  // Uppercase aliases
  IDLE: '/avatar/idle.webm',
  IDLE_SMOKING: '/avatar/idle_smoking.webm',
  IDLE_BED: '/avatar/idle-bed.webm',
  MUTED: '/avatar/muted.webm',
  LISTENING: '/avatar/listening.webm',
  THINKING: '/avatar/thinking.webm',
  TALK: '/avatar/talk.webm',
  HAPPY: '/avatar/happy.webm',
  SAD: '/avatar/sad.webm',
} as const;

export const IDLE_VIDEO_POOL = [
  AVATAR_VIDEOS.IDLE,
  AVATAR_VIDEOS.IDLE_SMOKING,
  AVATAR_VIDEOS.IDLE_BED,
] as const;

/**
 * Selects a random idle video variant from IDLE_VIDEO_POOL.
 * If length > 1, guarantees not picking currentIdleFile.
 */
export function pickNextIdleVideo(
  currentIdleFile?: string,
  rng: () => number = Math.random
): string {
  const poolList: readonly string[] = IDLE_VIDEO_POOL;
  if (poolList.length === 0) {
    return AVATAR_VIDEOS.IDLE;
  }
  if (poolList.length === 1) {
    return poolList[0];
  }

  const candidates = currentIdleFile
    ? poolList.filter((file) => file !== currentIdleFile)
    : poolList;

  const pool = candidates.length > 0 ? candidates : poolList;
  const index = Math.floor(rng() * pool.length);
  return pool[index] ?? AVATAR_VIDEOS.IDLE;
}

export interface ResolveAvatarOptions {
  state?: AssistantState;
  emotion?: EmotionState;
  isMuted?: boolean;
  idleSeconds?: number;
  idleVariant?: string;
  idleFile?: string;
}

/**
 * Resolves the appropriate WebM video asset path based on assistant state,
 * emotion, mute status, and inactivity duration or specified idle variant.
 */
export function resolveAvatarVideoPath(options: ResolveAvatarOptions = {}): string {
  const {
    state = 'IDLE',
    emotion,
    isMuted = false,
    idleSeconds = 0,
    idleVariant,
    idleFile,
  } = options;

  // 1. Muted Override (Highest Priority)
  if (isMuted) {
    return AVATAR_VIDEOS.MUTED;
  }

  // 2. Standalone Emotion Expression (only when state is not explicitly specified)
  if (options.state === undefined && emotion) {
    if (emotion === 'happy') {
      return AVATAR_VIDEOS.HAPPY;
    }
    if (emotion === 'sad') {
      return AVATAR_VIDEOS.SAD;
    }
    if (emotion === 'thinking') {
      return AVATAR_VIDEOS.THINKING;
    }
  }

  // 3. Active Conversational State Transitions
  switch (state) {
    case 'ERROR':
      return AVATAR_VIDEOS.SAD;
    case 'LISTENING':
      return AVATAR_VIDEOS.LISTENING;
    case 'TRANSCRIBING':
    case 'THINKING':
    case 'TOOL_RUNNING':
      return AVATAR_VIDEOS.THINKING;
    case 'SPEAKING': {
      if (emotion === 'happy') {
        return AVATAR_VIDEOS.HAPPY;
      }
      if (emotion === 'sad') {
        return AVATAR_VIDEOS.SAD;
      }
      if (emotion === 'thinking') {
        return AVATAR_VIDEOS.THINKING;
      }
      return AVATAR_VIDEOS.TALK;
    }
    case 'IDLE':
    default: {
      const activeIdle = idleFile || idleVariant;
      if (activeIdle) {
        return activeIdle;
      }
      if (idleSeconds >= 300) {
        return AVATAR_VIDEOS.IDLE_BED;
      }
      if (idleSeconds >= 60) {
        return AVATAR_VIDEOS.IDLE_SMOKING;
      }
      return AVATAR_VIDEOS.IDLE;
    }
  }
}
