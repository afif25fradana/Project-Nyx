import React from 'react';
import { useNyx, type LatencyMetric } from '../../context/NyxContext';
import { cn } from '../../utils/cn';

export interface PipelineTerminalProps {
  latencyMetric?: LatencyMetric | null;
  className?: string;
}

const SLA_BUDGET_MS = 2000;

interface StageItem {
  id: string;
  label: string;
  component: string;
  value: number;
}

/**
 * PipelineTerminal renders an amber CRT phosphor latency waterfall display,
 * tracking turn-by-turn speech processing stages against the 2000ms TTFA budget.
 */
export const PipelineTerminal: React.FC<PipelineTerminalProps> = ({
  latencyMetric,
  className,
}) => {
  const { state } = useNyx();
  const metric = latencyMetric ?? state.latestLatency;

  const isWithinBudget = metric ? metric.total_ttfa_ms < SLA_BUDGET_MS : true;

  const stages: StageItem[] = metric
    ? [
        { id: 'vad', label: 'VAD Gate', component: 'Silero VAD ONNX', value: metric.vad_ms },
        { id: 'stt', label: 'STT Transcription', component: 'Faster-Whisper (CTranslate2)', value: metric.stt_ms },
        { id: 'llm', label: 'LLM TTFT', component: 'deepseek-flash Streaming', value: metric.llm_ttft_ms },
        { id: 'tts', label: 'TTS Chunk 1', component: 'Kokoro ONNX', value: metric.tts_chunk1_ms },
      ]
    : [];

  return (
    <div
      data-testid="pipeline-terminal"
      className={cn(
        'flex flex-col bg-panel-recessed border border-panel-border rounded-lg p-4 font-mono select-none crt-scanlines',
        className
      )}
    >
      {/* Header Bar */}
      <div className="flex items-center justify-between pb-3 mb-3 border-b border-panel-border/70 text-xs">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-amber-glow animate-pulse" aria-hidden="true" />
          <h2 className="text-amber-glow uppercase tracking-wider font-semibold">
            Telemetry Waterfall // SLA 2000ms
          </h2>
        </div>
        {metric && (
          <span className="text-ink-secondary text-[11px]">
            TURN #{metric.turn_id}
          </span>
        )}
      </div>

      {!metric ? (
        <div className="flex-1 flex flex-col items-center justify-center p-6 text-center">
          <div className="amber-phosphor-glow text-sm font-semibold tracking-wide">
            STANDBY · TELEMETRY READY
          </div>
          <div className="text-xs text-ink-muted mt-1.5">
            System idle. Speech pipeline uninitialized.
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {/* Stage Waterfall Rows */}
          <div className="space-y-2">
            {stages.map((stage) => {
              const percentage = Math.min(100, Math.round((stage.value / SLA_BUDGET_MS) * 100));
              return (
                <div key={stage.id} className="space-y-1">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-ink-secondary">
                      {stage.label}{' '}
                      <span className="text-ink-muted text-[10px]">({stage.component})</span>
                    </span>
                    <span className="amber-phosphor-glow font-bold">
                      {stage.value} ms
                    </span>
                  </div>
                  {/* Miniature progress bar */}
                  <div className="w-full h-1.5 bg-panel-800 rounded-full overflow-hidden border border-panel-border/50">
                    <div
                      className="h-full bg-amber-glow transition-all duration-300"
                      style={{ width: `${Math.max(2, percentage)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          {/* TTFA Aggregate Summary */}
          <div className="pt-3 mt-3 border-t border-panel-border/70 flex items-center justify-between">
            <div>
              <div className="text-[10px] uppercase tracking-wider text-ink-muted">
                Total Time To First Audio (TTFA)
              </div>
              <div className="text-lg font-bold amber-phosphor-glow">
                {metric.total_ttfa_ms} ms
              </div>
            </div>

            <div className="text-right">
              <div className="text-[10px] uppercase tracking-wider text-ink-muted mb-0.5">
                Budget Status
              </div>
              {isWithinBudget ? (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold text-emerald-400 bg-emerald-500/10 border border-emerald-500/30">
                  OPTIMAL · WITHIN BUDGET
                </span>
              ) : (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold text-red-400 bg-red-500/10 border border-red-500/30">
                  WARNING · OVER BUDGET
                </span>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
