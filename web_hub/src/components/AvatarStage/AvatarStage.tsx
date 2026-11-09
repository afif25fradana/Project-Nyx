import React, { useState, useEffect } from 'react';
import { useNyx } from '../../context/NyxContext';
import {
  resolveAvatarVideoPath,
  AVATAR_VIDEOS,
  pickNextIdleVideo,
} from '../../utils/avatarAssets';
import { DoubleBufferVideo } from './DoubleBufferVideo';
import { cn } from '../../utils/cn';

export interface AvatarStageProps {
  className?: string;
}

/**
 * AvatarStage displays Nyx's responsive visual avatar within
 * a CRT cathode-ray monitor chassis, reacting to state changes and tracking idle inactivity.
 */
export const AvatarStage: React.FC<AvatarStageProps> = ({ className }) => {
  const { state } = useNyx();
  const [idleSeconds, setIdleSeconds] = useState(0);
  const [currentIdleFile, setCurrentIdleFile] = useState<string>(AVATAR_VIDEOS.IDLE);

  useEffect(() => {
    if (state.assistantState !== 'IDLE') {
      setIdleSeconds(0);
      return;
    }

    const interval = window.setInterval(() => {
      setIdleSeconds((prev) => prev + 1);
    }, 1000);

    return () => clearInterval(interval);
  }, [state.assistantState]);

  useEffect(() => {
    if (state.assistantState !== 'IDLE') {
      setCurrentIdleFile(AVATAR_VIDEOS.IDLE);
      return;
    }

    setCurrentIdleFile(AVATAR_VIDEOS.IDLE);

    const rotationInterval = window.setInterval(() => {
      setCurrentIdleFile((prev) => pickNextIdleVideo(prev));
    }, 10_000);

    return () => clearInterval(rotationInterval);
  }, [state.assistantState]);

  const videoSrc = resolveAvatarVideoPath({
    state: state.assistantState,
    emotion: state.emotion,
    isMuted: state.isMuted,
    idleSeconds,
    idleFile: currentIdleFile,
  });

  return (
    <section
      role="region"
      aria-label="Avatar Stage"
      className={cn(
        'relative w-full aspect-video rounded-lg overflow-hidden border border-panel-border bg-panel-recessed crt-scanlines crt-vignette crt-fisheye-tube',
        className
      )}
    >
      <DoubleBufferVideo src={videoSrc} />

      {/* State & Inactivity OSD Overlay */}
      <div className="absolute top-3 left-3 z-20 flex items-center gap-2 px-2.5 py-1 rounded bg-panel-bezel/80 backdrop-blur-sm border border-panel-border text-xs font-mono text-ink-secondary">
        <span
          className={cn(
            'w-2 h-2 rounded-full',
            state.isMuted
              ? 'bg-red-500'
              : state.assistantState === 'SPEAKING'
              ? 'bg-amber-glow animate-pulse'
              : state.assistantState === 'LISTENING'
              ? 'bg-emerald-500 animate-pulse'
              : 'bg-emerald-500/50'
          )}
          aria-hidden="true"
        />
        <span className="uppercase tracking-wider font-semibold">
          {state.isMuted ? 'MUTED' : state.assistantState}
        </span>
        {state.assistantState === 'IDLE' && idleSeconds >= 60 && (
          <span className="text-[10px] text-ink-muted">
            ({idleSeconds}s idle)
          </span>
        )}
      </div>
    </section>
  );
};
