import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import React from 'react';
import { AvatarStage } from '../components/AvatarStage/AvatarStage';
import { DoubleBufferVideo } from '../components/AvatarStage/DoubleBufferVideo';
import { NyxProvider } from '../context/NyxContext';
import { NyxWebSocketClient } from '../services/websocket';
import { MockWebSocket } from './fixtures/mockWebSocket';

describe('AvatarStage & DoubleBufferVideo Component Suite', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  describe('DoubleBufferVideo Dual-Slot Buffer Architecture', () => {
    it('renders exactly two video element slots for seamless double-buffered cross-fading', () => {
      const { container } = render(<DoubleBufferVideo src="/avatar/idle.webm" />);
      const videos = container.querySelectorAll('video');

      expect(videos).toHaveLength(2);
    });

    it('enforces playsInline and muted attributes on both video slots for autoplay compliance', () => {
      const { container } = render(<DoubleBufferVideo src="/avatar/idle.webm" />);
      const videos = container.querySelectorAll('video');

      videos.forEach((video) => {
        expect(video.hasAttribute('playsinline') || (video as HTMLVideoElement).playsInline).toBe(true);
        expect(video.hasAttribute('muted') || (video as HTMLVideoElement).muted).toBe(true);
      });
    });

    it('sets loop on video slots to maintain continuous background animation', () => {
      const { container } = render(<DoubleBufferVideo src="/avatar/idle.webm" />);
      const videos = container.querySelectorAll('video');

      videos.forEach((video) => {
        expect(video.hasAttribute('loop') || (video as HTMLVideoElement).loop).toBe(true);
      });
    });

    it('initializes active slot with initial src and calls play', () => {
      const { container } = render(<DoubleBufferVideo src="/avatar/idle.webm" />);
      const videos = Array.from(container.querySelectorAll('video'));

      const activeVideo = videos.find((v) => v.getAttribute('src')?.includes('idle.webm'));
      expect(activeVideo).toBeDefined();
      expect(HTMLMediaElement.prototype.play).toHaveBeenCalled();
    });

    it('triggers rVFC cross-fade swap when src changes', async () => {
      const { container, rerender } = render(<DoubleBufferVideo src="/avatar/idle.webm" />);

      rerender(<DoubleBufferVideo src="/avatar/talk.webm" />);

      act(() => {
        vi.advanceTimersByTime(50);
      });

      const videos = Array.from(container.querySelectorAll('video'));
      const talkVideo = videos.find((v) => v.getAttribute('src')?.includes('talk.webm'));
      expect(talkVideo).toBeDefined();
    });

    it('falls back to 80ms timer swap when requestVideoFrameCallback is unsupported', () => {
      // Temporarily remove rVFC on prototype to simulate environments lacking rVFC
      const originalRVFC = HTMLVideoElement.prototype.requestVideoFrameCallback;
      delete (HTMLVideoElement.prototype as Partial<HTMLVideoElement>).requestVideoFrameCallback;

      try {
        const { container, rerender } = render(<DoubleBufferVideo src="/avatar/idle.webm" />);

        rerender(<DoubleBufferVideo src="/avatar/thinking.webm" />);

        act(() => {
          vi.advanceTimersByTime(80);
        });

        const videos = Array.from(container.querySelectorAll('video'));
        const incomingVideo = videos.find((v) => v.getAttribute('src')?.includes('thinking.webm'));
        expect(incomingVideo).toBeDefined();
      } finally {
        HTMLVideoElement.prototype.requestVideoFrameCallback = originalRVFC;
      }
    });

    it('reliably pauses outgoing video slot after crossFadeDurationMs elapses without being cancelled by activeSlot re-render', () => {
      const pauseSpy = vi.spyOn(HTMLMediaElement.prototype, 'pause');
      const { rerender } = render(<DoubleBufferVideo src="/avatar/idle.webm" crossFadeDurationMs={200} />);

      pauseSpy.mockClear();

      // Trigger swap to new src
      rerender(<DoubleBufferVideo src="/avatar/talk.webm" crossFadeDurationMs={200} />);

      // At 50ms, swap has initiated, but crossFadeDurationMs (200ms) has not elapsed
      act(() => {
        vi.advanceTimersByTime(50);
      });
      expect(pauseSpy).not.toHaveBeenCalled();

      // Advance through crossFadeDurationMs
      act(() => {
        vi.advanceTimersByTime(200);
      });
      expect(pauseSpy).toHaveBeenCalled();
    });

    it('applies vhs-glitch-active class during cross-fade and removes it after crossFadeDurationMs', () => {
      const { container, rerender } = render(<DoubleBufferVideo src="/avatar/idle.webm" crossFadeDurationMs={200} />);
      const wrapper = container.querySelector('[data-testid="double-buffer-video"]');

      expect(wrapper?.classList.contains('vhs-glitch-active')).toBe(false);

      rerender(<DoubleBufferVideo src="/avatar/talk.webm" crossFadeDurationMs={200} />);

      act(() => {
        vi.advanceTimersByTime(50);
      });
      expect(wrapper?.classList.contains('vhs-glitch-active')).toBe(true);

      act(() => {
        vi.advanceTimersByTime(200);
      });
      expect(wrapper?.classList.contains('vhs-glitch-active')).toBe(false);
    });

    it('releases WebM decoders on unmount by removing src attribute and calling load()', () => {
      const removeAttributeSpy = vi.spyOn(HTMLVideoElement.prototype, 'removeAttribute');
      const loadSpy = vi.spyOn(HTMLMediaElement.prototype, 'load');

      const { unmount } = render(<DoubleBufferVideo src="/avatar/idle.webm" />);

      unmount();

      expect(removeAttributeSpy).toHaveBeenCalledWith('src');
      expect(loadSpy).toHaveBeenCalled();
    });
  });

  describe('AvatarStage Shell & Reactive Context Integration', () => {
    it('wraps the stage in CRT scanlines container with crt-scanlines class', () => {
      const { container } = render(
        <NyxProvider>
          <AvatarStage />
        </NyxProvider>
      );

      const crtElement = container.querySelector('.crt-scanlines');
      expect(crtElement, 'Must include .crt-scanlines container').not.toBeNull();
    });

    it('includes crt-vignette container for cathode tube shading', () => {
      const { container } = render(
        <NyxProvider>
          <AvatarStage />
        </NyxProvider>
      );

      const vignetteElement = container.querySelector('.crt-vignette');
      expect(vignetteElement, 'Must include .crt-vignette container').not.toBeNull();
    });

    it('exposes accessible landmark region semantics with appropriate aria-label', () => {
      render(
        <NyxProvider>
          <AvatarStage />
        </NyxProvider>
      );

      const region = screen.getByRole('region', { name: /avatar stage/i });
      expect(region).toBeDefined();
    });

    it('includes crt-fisheye-tube container for cathode tube shading and curvature', () => {
      const { container } = render(
        <NyxProvider>
          <AvatarStage />
        </NyxProvider>
      );

      const fisheyeElement = container.querySelector('.crt-fisheye-tube');
      expect(fisheyeElement, 'Must include .crt-fisheye-tube container').not.toBeNull();
    });

    it('rotates idle video variants every 10 seconds while in IDLE state', () => {
      const { container } = render(
        <NyxProvider>
          <AvatarStage />
        </NyxProvider>
      );

      // Initial state is IDLE -> starts on idle.webm
      let videos = Array.from(container.querySelectorAll('video'));
      expect(videos.some((v) => v.getAttribute('src')?.includes('idle.webm'))).toBe(true);

      // Advance timer by 10s (first rotation)
      act(() => {
        vi.advanceTimersByTime(10000);
      });

      videos = Array.from(container.querySelectorAll('video'));
      const rotatedSrc = videos.map((v) => v.getAttribute('src')).filter(Boolean);
      const hasRotatedVariant = rotatedSrc.some(
        (src) => src?.includes('idle_smoking.webm') || src?.includes('idle-bed.webm')
      );
      expect(hasRotatedVariant).toBe(true);
    });

    it('resets idle rotation back to AVATAR_VIDEOS.IDLE when transitioning away and returning to IDLE', () => {
      let mockWsInstance: MockWebSocket | null = null;
      const client = new NyxWebSocketClient({
        webSocketFactory: (url) => {
          mockWsInstance = new MockWebSocket(url);
          return mockWsInstance as unknown as WebSocket;
        },
      });
      client.connect();

      const { container } = render(
        <NyxProvider client={client}>
          <AvatarStage />
        </NyxProvider>
      );

      // Advance past 10s so it rotates to an idle variant
      act(() => {
        vi.advanceTimersByTime(10000);
      });

      // Transition to SPEAKING
      act(() => {
        mockWsInstance?.triggerOpen();
        mockWsInstance?.triggerMessage(
          JSON.stringify({
            type: 'state_change',
            payload: { state: 'SPEAKING', turn_id: 1 },
          })
        );
        vi.advanceTimersByTime(100);
      });

      let videos = Array.from(container.querySelectorAll('video'));
      expect(videos.some((v) => v.getAttribute('src')?.includes('talk.webm'))).toBe(true);

      // Return to IDLE
      act(() => {
        mockWsInstance?.triggerMessage(
          JSON.stringify({
            type: 'state_change',
            payload: { state: 'IDLE', turn_id: 2 },
          })
        );
        vi.advanceTimersByTime(100);
      });

      // Must reset immediately back to idle.webm for initial 0-10s cycle
      videos = Array.from(container.querySelectorAll('video'));
      expect(videos.some((v) => v.getAttribute('src')?.includes('idle.webm'))).toBe(true);

      client.disconnect();
    });

    it('dynamically switches video stream when Nyx state transitions', () => {
      let mockWsInstance: MockWebSocket | null = null;
      const client = new NyxWebSocketClient({
        url: 'ws://localhost:8000/api/v1/ws',
        token: 'test-token',
        webSocketFactory: (url) => {
          mockWsInstance = new MockWebSocket(url);
          return mockWsInstance as unknown as WebSocket;
        },
      });
      client.connect();

      const { container } = render(
        <NyxProvider client={client}>
          <AvatarStage />
        </NyxProvider>
      );

      // Initial state is IDLE -> idle.webm
      let videos = Array.from(container.querySelectorAll('video'));
      expect(videos.some((v) => v.getAttribute('src')?.includes('idle.webm'))).toBe(true);

      // Transition to SPEAKING
      act(() => {
        mockWsInstance?.triggerOpen();
        mockWsInstance?.triggerMessage(
          JSON.stringify({
            type: 'state_change',
            payload: { state: 'SPEAKING', turn_id: 1 },
          })
        );
        vi.advanceTimersByTime(100);
      });

      videos = Array.from(container.querySelectorAll('video'));
      expect(videos.some((v) => v.getAttribute('src')?.includes('talk.webm'))).toBe(true);

      // Mute event overrides video
      act(() => {
        mockWsInstance?.triggerMessage(
          JSON.stringify({
            type: 'mute_state',
            payload: { muted: true },
          })
        );
        vi.advanceTimersByTime(100);
      });

      videos = Array.from(container.querySelectorAll('video'));
      expect(videos.some((v) => v.getAttribute('src')?.includes('muted.webm'))).toBe(true);

      client.disconnect();
    });
  });
});
