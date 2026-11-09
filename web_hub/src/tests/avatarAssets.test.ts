import { describe, it, expect } from 'vitest';
import {
  AVATAR_VIDEOS,
  IDLE_VIDEO_POOL,
  pickNextIdleVideo,
  resolveAvatarVideoPath,
  type AvatarVideoKey,
  type ResolveAvatarOptions,
} from '../utils/avatarAssets';
import type { AssistantState, EmotionState } from '../types/websocket';

describe('avatarAssets & resolveAvatarVideoPath', () => {
  describe('AVATAR_VIDEOS Asset Manifest', () => {
    it('defines exact video asset paths for all required avatar states', () => {
      const requiredKeys: AvatarVideoKey[] = [
        'idle',
        'idle_smoking',
        'idle_bed',
        'muted',
        'listening',
        'thinking',
        'talk',
        'happy',
        'sad',
      ];

      requiredKeys.forEach((key) => {
        expect(AVATAR_VIDEOS[key], `AVATAR_VIDEOS.${key} must be defined`).toBeDefined();
        expect(typeof AVATAR_VIDEOS[key]).toBe('string');
        expect(AVATAR_VIDEOS[key]).toMatch(/^\/avatar\/[\w-]+\.webm$/);
      });
    });

    it('maps specific WebM assets matching public/avatar directory files', () => {
      expect(AVATAR_VIDEOS.idle).toBe('/avatar/idle.webm');
      expect(AVATAR_VIDEOS.idle_smoking).toBe('/avatar/idle_smoking.webm');
      expect(AVATAR_VIDEOS.idle_bed).toBe('/avatar/idle-bed.webm');
      expect(AVATAR_VIDEOS.muted).toBe('/avatar/muted.webm');
      expect(AVATAR_VIDEOS.listening).toBe('/avatar/listening.webm');
      expect(AVATAR_VIDEOS.thinking).toBe('/avatar/thinking.webm');
      expect(AVATAR_VIDEOS.talk).toBe('/avatar/talk.webm');
      expect(AVATAR_VIDEOS.happy).toBe('/avatar/happy.webm');
      expect(AVATAR_VIDEOS.sad).toBe('/avatar/sad.webm');
    });

    it('provides uppercase aliases matching asset constants', () => {
      expect(AVATAR_VIDEOS.IDLE).toBe('/avatar/idle.webm');
      expect(AVATAR_VIDEOS.IDLE_SMOKING).toBe('/avatar/idle_smoking.webm');
      expect(AVATAR_VIDEOS.IDLE_BED).toBe('/avatar/idle-bed.webm');
      expect(AVATAR_VIDEOS.MUTED).toBe('/avatar/muted.webm');
      expect(AVATAR_VIDEOS.TALK).toBe('/avatar/talk.webm');
    });
  });

  describe('IDLE_VIDEO_POOL & pickNextIdleVideo', () => {
    it('exports IDLE_VIDEO_POOL containing the three standard idle variants', () => {
      expect(IDLE_VIDEO_POOL).toEqual([
        AVATAR_VIDEOS.IDLE,
        AVATAR_VIDEOS.IDLE_SMOKING,
        AVATAR_VIDEOS.IDLE_BED,
      ]);
      expect(IDLE_VIDEO_POOL).toHaveLength(3);
    });

    it('picks a random idle video from the pool when currentIdleFile is omitted', () => {
      const picked = pickNextIdleVideo();
      expect(IDLE_VIDEO_POOL).toContain(picked);
    });

    it('never picks the current idle video variant when pool length > 1', () => {
      IDLE_VIDEO_POOL.forEach((currentVariant) => {
        // Run multiple randomized trials
        for (let i = 0; i < 20; i++) {
          const next = pickNextIdleVideo(currentVariant);
          expect(next).not.toBe(currentVariant);
          expect(IDLE_VIDEO_POOL).toContain(next);
        }
      });
    });

    it('deterministically selects expected variant based on injected rng', () => {
      // With current = IDLE, candidates are [IDLE_SMOKING, IDLE_BED] (length = 2)
      // rng = 0 -> index 0 (IDLE_SMOKING)
      expect(pickNextIdleVideo(AVATAR_VIDEOS.IDLE, () => 0)).toBe(AVATAR_VIDEOS.IDLE_SMOKING);
      // rng = 0.99 -> index 1 (IDLE_BED)
      expect(pickNextIdleVideo(AVATAR_VIDEOS.IDLE, () => 0.99)).toBe(AVATAR_VIDEOS.IDLE_BED);

      // With current = IDLE_SMOKING, candidates are [IDLE, IDLE_BED]
      expect(pickNextIdleVideo(AVATAR_VIDEOS.IDLE_SMOKING, () => 0)).toBe(AVATAR_VIDEOS.IDLE);
      expect(pickNextIdleVideo(AVATAR_VIDEOS.IDLE_SMOKING, () => 0.99)).toBe(AVATAR_VIDEOS.IDLE_BED);
    });
  });

  describe('resolveAvatarVideoPath', () => {
    describe('Muted Override (Highest Priority)', () => {
      it('returns muted video path whenever isMuted is true regardless of state', () => {
        const states: AssistantState[] = [
          'IDLE',
          'LISTENING',
          'TRANSCRIBING',
          'THINKING',
          'TOOL_RUNNING',
          'SPEAKING',
          'ERROR',
        ];

        states.forEach((state) => {
          const path = resolveAvatarVideoPath({ state, isMuted: true });
          expect(path).toBe('/avatar/muted.webm');
        });
      });

      it('returns muted video path when isMuted is true even with active emotions', () => {
        const emotions: EmotionState[] = ['happy', 'sad', 'thinking', 'surprised', 'neutral'];
        emotions.forEach((emotion) => {
          const path = resolveAvatarVideoPath({
            state: 'SPEAKING',
            emotion,
            isMuted: true,
          });
          expect(path).toBe('/avatar/muted.webm');
        });
      });
    });

    describe('Active Conversational State Transitions', () => {
      it('returns listening video when state is LISTENING', () => {
        const path = resolveAvatarVideoPath({ state: 'LISTENING', isMuted: false });
        expect(path).toBe('/avatar/listening.webm');
      });

      it('returns thinking video when state is THINKING', () => {
        const path = resolveAvatarVideoPath({ state: 'THINKING', isMuted: false });
        expect(path).toBe('/avatar/thinking.webm');
      });

      it('returns thinking video when state is TRANSCRIBING', () => {
        const path = resolveAvatarVideoPath({ state: 'TRANSCRIBING', isMuted: false });
        expect(path).toBe('/avatar/thinking.webm');
      });

      it('returns thinking video when state is TOOL_RUNNING', () => {
        const path = resolveAvatarVideoPath({ state: 'TOOL_RUNNING', isMuted: false });
        expect(path).toBe('/avatar/thinking.webm');
      });

      it('returns talk video when state is SPEAKING and emotion is neutral', () => {
        const path = resolveAvatarVideoPath({
          state: 'SPEAKING',
          emotion: 'neutral',
          isMuted: false,
        });
        expect(path).toBe('/avatar/talk.webm');
      });

      it('returns sad video when state is ERROR', () => {
        const path = resolveAvatarVideoPath({ state: 'ERROR', isMuted: false });
        expect(path).toBe('/avatar/sad.webm');
      });
    });

    describe('Emotional Expression Overrides & State Isolation', () => {
      it('returns happy video when speaking with happy emotion', () => {
        const path = resolveAvatarVideoPath({
          state: 'SPEAKING',
          emotion: 'happy',
          isMuted: false,
        });
        expect(path).toBe('/avatar/happy.webm');
      });

      it('returns sad video when speaking with sad emotion', () => {
        const path = resolveAvatarVideoPath({
          state: 'SPEAKING',
          emotion: 'sad',
          isMuted: false,
        });
        expect(path).toBe('/avatar/sad.webm');
      });

      it('returns thinking video when speaking with thinking emotion', () => {
        const path = resolveAvatarVideoPath({
          state: 'SPEAKING',
          emotion: 'thinking',
          isMuted: false,
        });
        expect(path).toBe('/avatar/thinking.webm');
      });

      it('resolves standalone emotion correctly when state is omitted', () => {
        expect(resolveAvatarVideoPath({ emotion: 'happy' })).toBe('/avatar/happy.webm');
        expect(resolveAvatarVideoPath({ emotion: 'sad' })).toBe('/avatar/sad.webm');
        expect(resolveAvatarVideoPath({ emotion: 'thinking' })).toBe('/avatar/thinking.webm');
      });

      it('preserves active state videos without hijacking by lingering emotion', () => {
        // IDLE state preserves idle rotation and idle files
        expect(
          resolveAvatarVideoPath({ state: 'IDLE', emotion: 'happy', idleSeconds: 10 })
        ).toBe('/avatar/idle.webm');
        expect(
          resolveAvatarVideoPath({
            state: 'IDLE',
            emotion: 'happy',
            idleFile: AVATAR_VIDEOS.IDLE_BED,
          })
        ).toBe('/avatar/idle-bed.webm');
        expect(
          resolveAvatarVideoPath({ state: 'IDLE', emotion: 'sad', idleSeconds: 120 })
        ).toBe('/avatar/idle_smoking.webm');

        // LISTENING state preserves listening.webm
        expect(
          resolveAvatarVideoPath({ state: 'LISTENING', emotion: 'happy' })
        ).toBe('/avatar/listening.webm');
        expect(
          resolveAvatarVideoPath({ state: 'LISTENING', emotion: 'sad' })
        ).toBe('/avatar/listening.webm');

        // THINKING state preserves thinking.webm
        expect(
          resolveAvatarVideoPath({ state: 'THINKING', emotion: 'happy' })
        ).toBe('/avatar/thinking.webm');

        // ERROR state preserves sad.webm
        expect(
          resolveAvatarVideoPath({ state: 'ERROR', emotion: 'happy' })
        ).toBe('/avatar/sad.webm');
      });
    });

    describe('Inactivity Ladder for IDLE State', () => {
      it('returns standard idle video when idleSeconds < 60', () => {
        expect(resolveAvatarVideoPath({ state: 'IDLE', idleSeconds: 0 })).toBe('/avatar/idle.webm');
        expect(resolveAvatarVideoPath({ state: 'IDLE', idleSeconds: 30 })).toBe('/avatar/idle.webm');
        expect(resolveAvatarVideoPath({ state: 'IDLE', idleSeconds: 59 })).toBe('/avatar/idle.webm');
      });

      it('returns idle_smoking video when idleSeconds is between 60 and 299 seconds', () => {
        expect(resolveAvatarVideoPath({ state: 'IDLE', idleSeconds: 60 })).toBe('/avatar/idle_smoking.webm');
        expect(resolveAvatarVideoPath({ state: 'IDLE', idleSeconds: 120 })).toBe('/avatar/idle_smoking.webm');
        expect(resolveAvatarVideoPath({ state: 'IDLE', idleSeconds: 299 })).toBe('/avatar/idle_smoking.webm');
      });

      it('returns idle-bed video when idleSeconds >= 300 seconds', () => {
        expect(resolveAvatarVideoPath({ state: 'IDLE', idleSeconds: 300 })).toBe('/avatar/idle-bed.webm');
        expect(resolveAvatarVideoPath({ state: 'IDLE', idleSeconds: 600 })).toBe('/avatar/idle-bed.webm');
        expect(resolveAvatarVideoPath({ state: 'IDLE', idleSeconds: 3600 })).toBe('/avatar/idle-bed.webm');
      });
    });

    describe('Extensible Idle Variant & File Overrides', () => {
      it('returns specified idleFile when in IDLE state', () => {
        expect(
          resolveAvatarVideoPath({ state: 'IDLE', idleFile: AVATAR_VIDEOS.IDLE_SMOKING })
        ).toBe('/avatar/idle_smoking.webm');
        expect(
          resolveAvatarVideoPath({ state: 'IDLE', idleFile: AVATAR_VIDEOS.IDLE_BED })
        ).toBe('/avatar/idle-bed.webm');
      });

      it('returns specified idleVariant when in IDLE state', () => {
        expect(
          resolveAvatarVideoPath({ state: 'IDLE', idleVariant: AVATAR_VIDEOS.IDLE_SMOKING })
        ).toBe('/avatar/idle_smoking.webm');
        expect(
          resolveAvatarVideoPath({ state: 'IDLE', idleVariant: AVATAR_VIDEOS.IDLE_BED })
        ).toBe('/avatar/idle-bed.webm');
      });

      it('does not use idleFile when active conversation state takes precedence', () => {
        expect(
          resolveAvatarVideoPath({
            state: 'SPEAKING',
            idleFile: AVATAR_VIDEOS.IDLE_BED,
          })
        ).toBe('/avatar/talk.webm');
      });
    });

    describe('Fallback to Default Idle', () => {
      it('falls back to default idle video when options are empty or default', () => {
        expect(resolveAvatarVideoPath({})).toBe('/avatar/idle.webm');
        expect(resolveAvatarVideoPath({ state: 'IDLE' })).toBe('/avatar/idle.webm');
      });

      it('falls back to default idle video when unknown state is passed', () => {
        const invalidOptions = { state: 'UNKNOWN_STATE' as AssistantState };
        expect(resolveAvatarVideoPath(invalidOptions)).toBe('/avatar/idle.webm');
      });

      it('handles negative idleSeconds gracefully by returning idle video', () => {
        expect(resolveAvatarVideoPath({ state: 'IDLE', idleSeconds: -10 })).toBe('/avatar/idle.webm');
      });
    });
  });
});
