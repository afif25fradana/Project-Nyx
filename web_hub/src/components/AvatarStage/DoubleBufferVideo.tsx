import React, { useRef, useState, useEffect } from 'react';
import { cn } from '../../utils/cn';

export interface DoubleBufferVideoProps {
  src: string;
  className?: string;
  crossFadeDurationMs?: number;
}

/**
 * Double-buffered WebM video player component.
 * Maintains two persistent <video> slots for glitch-free cross-fading,
 * using requestVideoFrameCallback with an 80ms fallback watchdog.
 */
export const DoubleBufferVideo: React.FC<DoubleBufferVideoProps> = ({
  src,
  className,
  crossFadeDurationMs = 200,
}) => {
  const video0Ref = useRef<HTMLVideoElement | null>(null);
  const video1Ref = useRef<HTMLVideoElement | null>(null);

  const [activeSlot, setActiveSlot] = useState<0 | 1>(0);
  const [slotSources, setSlotSources] = useState<{ 0: string; 1: string }>({
    0: src,
    1: '',
  });

  const [isGlitching, setIsGlitching] = useState(false);
  const fadeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const prevSrcRef = useRef(src);

  // Synchronously update inactive slot source during render when prop changes
  if (prevSrcRef.current !== src) {
    prevSrcRef.current = src;
    const nextIncomingSlot = activeSlot === 0 ? 1 : 0;
    setSlotSources((prev) => ({
      ...prev,
      [nextIncomingSlot]: src,
    }));
  }

  const activeSrc = activeSlot === 0 ? slotSources[0] : slotSources[1];

  // Initial playback on mount
  useEffect(() => {
    const initialVideo = activeSlot === 0 ? video0Ref.current : video1Ref.current;
    if (initialVideo) {
      initialVideo.muted = true;
      initialVideo.playsInline = true;
      initialVideo.loop = true;
      try {
        const p = initialVideo.play();
        if (p && typeof p.catch === 'function') {
          p.catch(() => {});
        }
      } catch {
        // Ignored in headless/jsdom
      }
    }
  }, []);

  // Cross-fade transitions on source change
  useEffect(() => {
    if (src === activeSrc) return;

    const incomingSlot = activeSlot === 0 ? 1 : 0;
    const outgoingSlot = activeSlot;
    const incomingVideo = incomingSlot === 0 ? video0Ref.current : video1Ref.current;
    const outgoingVideo = outgoingSlot === 0 ? video0Ref.current : video1Ref.current;

    if (!incomingVideo) return;

    incomingVideo.muted = true;
    incomingVideo.playsInline = true;
    incomingVideo.loop = true;
    try {
      const p = incomingVideo.play();
      if (p && typeof p.catch === 'function') {
        p.catch(() => {});
      }
    } catch {
      // Ignored in headless/jsdom
    }

    // Clear any previous swap's fade timer when starting a new swap
    if (fadeTimerRef.current !== null) {
      clearTimeout(fadeTimerRef.current);
      fadeTimerRef.current = null;
    }

    let swapped = false;
    let rVFCId: number | null = null;
    let watchdogTimer: ReturnType<typeof setTimeout> | null = null;

    const performSwap = () => {
      if (swapped) return;
      swapped = true;
      if (watchdogTimer !== null) {
        clearTimeout(watchdogTimer);
        watchdogTimer = null;
      }

      setIsGlitching(true);
      setActiveSlot(incomingSlot);

      fadeTimerRef.current = setTimeout(() => {
        outgoingVideo?.pause();
        setIsGlitching(false);
        fadeTimerRef.current = null;
      }, crossFadeDurationMs);
    };

    // Watchdog fallback (80ms)
    watchdogTimer = setTimeout(performSwap, 80);

    // rVFC if supported
    if (
      'requestVideoFrameCallback' in incomingVideo &&
      typeof incomingVideo.requestVideoFrameCallback === 'function'
    ) {
      rVFCId = incomingVideo.requestVideoFrameCallback(() => {
        performSwap();
      });
    }

    return () => {
      if (watchdogTimer !== null) clearTimeout(watchdogTimer);
      // NOTE: fadeTimerRef.current is intentionally NOT cleared here.
      // Cleaning it up on activeSlot re-renders would cancel outgoingVideo.pause() before crossFadeDurationMs elapses.
      if (
        rVFCId !== null &&
        'cancelVideoFrameCallback' in incomingVideo &&
        typeof (incomingVideo as HTMLVideoElement & { cancelVideoFrameCallback?: (id: number) => void }).cancelVideoFrameCallback === 'function'
      ) {
        (incomingVideo as HTMLVideoElement & { cancelVideoFrameCallback: (id: number) => void }).cancelVideoFrameCallback(rVFCId);
      }
    };
  }, [src, activeSrc, activeSlot, crossFadeDurationMs]);

  // Explicit decoder & timer cleanup on unmount
  useEffect(() => {
    const v0 = video0Ref.current;
    const v1 = video1Ref.current;
    return () => {
      if (fadeTimerRef.current !== null) {
        clearTimeout(fadeTimerRef.current);
        fadeTimerRef.current = null;
      }
      [v0, v1].forEach((video) => {
        if (video) {
          video.pause();
          video.removeAttribute('src');
          video.load();
        }
      });
    };
  }, []);

  return (
    <div
      className={cn(
        'relative w-full h-full overflow-hidden',
        isGlitching && 'vhs-glitch-active',
        className
      )}
      data-testid="double-buffer-video"
    >
      <video
        ref={video0Ref}
        src={slotSources[0] || undefined}
        playsInline
        muted
        loop
        autoPlay
        className={cn(
          'absolute inset-0 w-full h-full object-cover transition-opacity duration-200',
          activeSlot === 0 ? 'opacity-100 z-10' : 'opacity-0 z-0 pointer-events-none'
        )}
      />
      <video
        ref={video1Ref}
        src={slotSources[1] || undefined}
        playsInline
        muted
        loop
        autoPlay
        className={cn(
          'absolute inset-0 w-full h-full object-cover transition-opacity duration-200',
          activeSlot === 1 ? 'opacity-100 z-10' : 'opacity-0 z-0 pointer-events-none'
        )}
      />
    </div>
  );
};
