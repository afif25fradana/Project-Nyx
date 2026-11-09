import React from 'react';
import { useNyx } from '../../context/NyxContext';
import { Mic, MicOff } from '../common/Icons';
import { cn } from '../../utils/cn';

export interface ControlDeckProps {
  className?: string;
}

/**
 * ControlDeck provides tactile operational controls for Project Nyx,
 * including a microphone mute switch with physical LED indicator
 * and a tactile barge-in interrupt actuator.
 */
export const ControlDeck: React.FC<ControlDeckProps> = ({ className }) => {
  const { state, toggleMute, interrupt } = useNyx();

  return (
    <div
      className={cn(
        'flex flex-col sm:flex-row items-center justify-between gap-4 p-4 rounded-lg bg-panel-800 border border-panel-border',
        className
      )}
    >
      {/* Microphone Mute Control Pod */}
      <div className="flex items-center gap-3">
        {/* Hardware Status LED */}
        <div className="flex items-center gap-2">
          <span
            {...(state.isMuted ? { 'data-testid': 'led-mute' } : {})}
            className={cn(
              'w-3 h-3 rounded-full transition-colors duration-200 border border-panel-border/60',
              state.isMuted
                ? 'bg-red-500 shadow-[0_0_8px_rgba(239,68,68,0.8)] led-mute-active'
                : 'bg-neutral-700'
            )}
            aria-hidden="true"
          />
          <span className="text-xs font-mono uppercase tracking-wider text-ink-secondary">
            MIC {state.isMuted ? 'OFFLINE' : 'LIVE'}
          </span>
        </div>

        {/* Tactile Toggle Switch */}
        <button
          type="button"
          role="switch"
          aria-checked={state.isMuted}
          aria-label="Mute microphone"
          onClick={() => toggleMute()}
          className={cn(
            'flex items-center gap-2 px-3 py-1.5 rounded text-xs font-mono uppercase tracking-wider border transition-colors cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-glow',
            state.isMuted
              ? 'bg-red-500/20 border-red-500/40 text-red-300 hover:bg-red-500/30'
              : 'bg-panel-700 border-panel-border text-ink-primary hover:bg-panel-750'
          )}
        >
          {state.isMuted ? (
            <>
              <MicOff size={16} aria-hidden="true" />
              <span>Unmute</span>
            </>
          ) : (
            <>
              <Mic size={16} aria-hidden="true" />
              <span>Mute</span>
            </>
          )}
        </button>
      </div>

      {/* Barge-In Interrupt Actuator */}
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={interrupt}
          aria-label="Interrupt speech synthesis"
          className="flex items-center gap-2 px-4 py-1.5 rounded text-xs font-mono uppercase tracking-wider font-semibold bg-panel-700 hover:bg-red-950/40 text-amber-glow hover:text-red-400 border border-panel-border hover:border-red-500/50 transition-colors cursor-pointer active:scale-95 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-glow"
        >
          <span className="w-2 h-2 rounded-full bg-amber-glow" aria-hidden="true" />
          <span>Interrupt</span>
        </button>
      </div>
    </div>
  );
};
