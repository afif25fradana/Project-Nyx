import { describe, it, expect } from 'vitest';
import { render, screen, act } from '@testing-library/react';
import React from 'react';
import { PipelineTerminal } from '../components/PipelineTerminal/PipelineTerminal';
import {
  NyxProvider,
  type LatencyMetric,
} from '../context/NyxContext';
import { NyxWebSocketClient } from '../services/websocket';
import { MockWebSocket } from './fixtures/mockWebSocket';

describe('PipelineTerminal Telemetry Waterfall Suite', () => {
  it('displays standby readout when no latency telemetry has arrived yet', () => {
    render(
      <NyxProvider>
        <PipelineTerminal />
      </NyxProvider>
    );

    const standbyElement = screen.getByText(/standby|awaiting turn|telemetry ready/i);
    expect(standbyElement).toBeDefined();
  });

  it('applies amber phosphor glow styling for authentic CRT readout', () => {
    const { container } = render(
      <NyxProvider>
        <PipelineTerminal />
      </NyxProvider>
    );

    const terminalContainer =
      container.querySelector('.amber-phosphor-glow') ||
      container.querySelector('.font-mono') ||
      container.querySelector('[data-testid="pipeline-terminal"]');

    expect(terminalContainer, 'Terminal must apply monospace/amber phosphor aesthetics').not.toBeNull();
  });

  it('renders complete latency waterfall breakdown when metrics are received', () => {
    const sampleLatency: LatencyMetric = {
      turn_id: 12,
      vad_ms: 115,
      stt_ms: 340,
      llm_ttft_ms: 460,
      tts_chunk1_ms: 215,
      total_ttfa_ms: 1130,
    };

    render(
      <NyxProvider>
        <PipelineTerminal latencyMetric={sampleLatency} />
      </NyxProvider>
    );

    expect(screen.getByText(/115\s*ms/i)).toBeDefined(); // VAD
    expect(screen.getByText(/340\s*ms/i)).toBeDefined(); // STT
    expect(screen.getByText(/460\s*ms/i)).toBeDefined(); // LLM TTFT
    expect(screen.getByText(/215\s*ms/i)).toBeDefined(); // TTS Chunk 1
    expect(screen.getByText(/1130\s*ms/i)).toBeDefined(); // Total TTFA
    expect(screen.getByText(/12/)).toBeDefined(); // Turn ID
  });

  it('indicates WITHIN BUDGET status when total_ttfa_ms is below the 2000ms threshold', () => {
    const passingLatency: LatencyMetric = {
      turn_id: 15,
      vad_ms: 90,
      stt_ms: 280,
      llm_ttft_ms: 390,
      tts_chunk1_ms: 180,
      total_ttfa_ms: 940, // 940ms < 2000ms SLA
    };

    render(
      <NyxProvider>
        <PipelineTerminal latencyMetric={passingLatency} />
      </NyxProvider>
    );

    const budgetStatus = screen.getByText(/within budget|pass|optimal/i);
    expect(budgetStatus).toBeDefined();
  });

  it('indicates OVER BUDGET warning when total_ttfa_ms exceeds the 2000ms threshold', () => {
    const failingLatency: LatencyMetric = {
      turn_id: 16,
      vad_ms: 180,
      stt_ms: 850,
      llm_ttft_ms: 1100,
      tts_chunk1_ms: 450,
      total_ttfa_ms: 2580, // 2580ms >= 2000ms SLA breach
    };

    render(
      <NyxProvider>
        <PipelineTerminal latencyMetric={failingLatency} />
      </NyxProvider>
    );

    const warningStatus = screen.getByText(/over budget|budget exceeded|sla breach|warning/i);
    expect(warningStatus).toBeDefined();
  });

  it('updates telemetry readout reactively from NyxContext WebSocket events', () => {
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
    mockWsInstance?.triggerOpen();

    render(
      <NyxProvider client={client}>
        <PipelineTerminal />
      </NyxProvider>
    );

    act(() => {
      mockWsInstance?.triggerMessage(
        JSON.stringify({
          type: 'latency_metric',
          payload: {
            turn_id: 42,
            vad_ms: 105,
            stt_ms: 295,
            llm_ttft_ms: 410,
            tts_chunk1_ms: 190,
            total_ttfa_ms: 1000,
          },
        })
      );
    });

    expect(screen.getByText(/1000\s*ms/i)).toBeDefined();
    expect(screen.getByText(/42/)).toBeDefined();

    client.disconnect();
  });
});
