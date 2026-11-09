import React from 'react';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { NyxProvider } from './context/NyxContext';
import { AvatarStage } from './components/AvatarStage/AvatarStage';
import { ControlDeck } from './components/ControlDeck/ControlDeck';
import { PipelineTerminal } from './components/PipelineTerminal/PipelineTerminal';
import { ConversationFeed } from './components/ConversationFeed/ConversationFeed';
import { SettingsDeck } from './components/SettingsDeck/SettingsDeck';

/**
 * Main command deck for Project Nyx.
 * Features an edge-to-edge 12-column responsive layout integrating
 * the CRT avatar stage, tactile hardware controls, telemetry waterfall,
 * conversation feed, and hardware cassette settings deck.
 */
export const App: React.FC = () => {
  return (
    <ErrorBoundary>
      <NyxProvider>
        <div className="min-h-screen bg-chassis-950 text-ink-primary flex flex-col p-4 sm:p-6 lg:p-8">
          {/* Retro Industrial Command Deck Header */}
          <header className="mb-6 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 border-b border-panel-border pb-4">
            <div>
              <div className="flex items-center gap-3">
                <span
                  className="w-3 h-3 rounded-full bg-amber-glow animate-pulse"
                  aria-hidden="true"
                />
                <h1 className="text-xl sm:text-2xl font-bold font-mono tracking-tight text-white uppercase">
                  Project Nyx
                </h1>
              </div>
              <p className="text-xs sm:text-sm font-mono text-ink-secondary mt-1">
                Local Voice & Telemetry Deck · Pure ONNX Pipeline (≤ 2.6 GB VRAM)
              </p>
            </div>

            <div className="flex items-center gap-3">
              <span
                role="status"
                aria-label="System status online"
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded text-xs font-mono uppercase tracking-wider font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
              >
                <span
                  className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"
                  aria-hidden="true"
                />
                Operational
              </span>
            </div>
          </header>

          {/* 12-Column Responsive Operational Grid */}
          <main
            data-testid="deck-grid"
            className="w-full grid grid-cols-1 lg:grid-cols-12 gap-6 flex-1"
          >
            {/* Left Column: Visual & Hardware Stack (7 columns on desktop) */}
            <section
              aria-label="Hardware & Visual Subsystem"
              className="lg:col-span-7 flex flex-col gap-4"
            >
              <AvatarStage />
              <ControlDeck />
              <PipelineTerminal />
            </section>

            {/* Right Column: Interaction & Console Stack (5 columns on desktop) */}
            <section
              aria-label="Console & Interaction Subsystem"
              className="lg:col-span-5 flex flex-col gap-4"
            >
              <div className="h-[460px] flex flex-col">
                <ConversationFeed />
              </div>
              <SettingsDeck />
            </section>
          </main>
        </div>
      </NyxProvider>
    </ErrorBoundary>
  );
};

export default App;
