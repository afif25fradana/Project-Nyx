import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { NyxWebSocketClient, computeFullJitterBackoff } from '../services/websocket';
import { MockWebSocket } from './fixtures/mockWebSocket';

describe('NyxWebSocketClient Service', () => {
  let createdSockets: MockWebSocket[];
  let wsFactory: (url: string) => WebSocket;

  beforeEach(() => {
    vi.useFakeTimers();
    createdSockets = [];
    wsFactory = (url: string) => {
      const socket = new MockWebSocket(url);
      createdSockets.push(socket);
      return socket as unknown as WebSocket;
    };
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  describe('Connection & Lifecycle', () => {
    it('derives default WebSocket URL from window.location when available', () => {
      const originalLocation = window.location;
      try {
        // @ts-expect-error Mocking window.location for test
        delete window.location;
        window.location = {
          protocol: 'http:',
          host: 'nyx.local:3000',
        } as unknown as Location;

        const client = new NyxWebSocketClient({ wsFactory });
        expect(client.getUrl()).toBe('ws://nyx.local:3000/ws/client');

        window.location = {
          protocol: 'https:',
          host: 'nyx.secure.domain',
        } as unknown as Location;

        const secureClient = new NyxWebSocketClient({ wsFactory });
        expect(secureClient.getUrl()).toBe('wss://nyx.secure.domain/ws/client');
      } finally {
        window.location = originalLocation;
      }
    });

    it('falls back to default ws://127.0.0.1:8765/ws/client when window.location host is empty', () => {
      const originalLocation = window.location;
      try {
        // @ts-expect-error Mocking window.location for test
        delete window.location;
        window.location = {
          protocol: 'http:',
          host: '',
        } as unknown as Location;

        const client = new NyxWebSocketClient({ wsFactory });
        expect(client.getUrl()).toBe('ws://127.0.0.1:8765/ws/client');
      } finally {
        window.location = originalLocation;
      }
    });

    it('initializes connection to the target endpoint using wsFactory', () => {
      const client = new NyxWebSocketClient({
        url: 'ws://127.0.0.1:8765/ws/client',
        wsFactory,
      });

      client.connect();

      expect(createdSockets).toHaveLength(1);
      expect(createdSockets[0].url).toBe('ws://127.0.0.1:8765/ws/client');
    });

    it('notifies status change listeners when connection is established', () => {
      const client = new NyxWebSocketClient({ wsFactory });
      const statusChanges: string[] = [];
      client.onStatusChange((status) => statusChanges.push(status));

      client.connect();
      expect(statusChanges).toContain('CONNECTING');

      createdSockets[0].simulateOpen();
      expect(statusChanges).toContain('OPEN');
    });
  });

  describe('Flat ClientCommand Envelopes', () => {
    let client: NyxWebSocketClient;
    let socket: MockWebSocket;

    beforeEach(() => {
      client = new NyxWebSocketClient({ wsFactory });
      client.connect();
      socket = createdSockets[0];
      socket.simulateOpen();
    });

    it('transmits flat send_text command payload {"action": "send_text", "text": "..."}', () => {
      client.sendText('Hello Nyx');

      expect(socket.sentMessages).toHaveLength(1);
      const parsed = JSON.parse(socket.sentMessages[0]);
      expect(parsed).toEqual({
        action: 'send_text',
        text: 'Hello Nyx',
      });
    });

    it('transmits flat mute_toggle command payload {"action": "mute_toggle", "muted": true}', () => {
      client.toggleMute(true);

      expect(socket.sentMessages).toHaveLength(1);
      const parsed = JSON.parse(socket.sentMessages[0]);
      expect(parsed).toEqual({
        action: 'mute_toggle',
        muted: true,
      });
    });

    it('transmits flat interrupt command payload {"action": "interrupt"}', () => {
      client.interrupt();

      expect(socket.sentMessages).toHaveLength(1);
      const parsed = JSON.parse(socket.sentMessages[0]);
      expect(parsed).toEqual({
        action: 'interrupt',
      });
    });
  });

  describe('Authorization Close Codes (1008 & 4401)', () => {
    it('permanently halts reconnection when closed with code 1008 (Policy Violation)', () => {
      const client = new NyxWebSocketClient({ wsFactory });
      const errorSpy = vi.fn();
      client.onError(errorSpy);

      client.connect();
      const socket = createdSockets[0];
      socket.simulateOpen();

      // Simulate auth rejection by server
      socket.simulateClose(1008, 'Unauthorized: Invalid token');

      // Fast forward time - no new sockets should be created
      vi.advanceTimersByTime(30000);

      expect(createdSockets).toHaveLength(1);
      expect(client.isConnected()).toBe(false);
      expect(errorSpy).toHaveBeenCalled();
    });

    it('permanently halts reconnection when closed with code 4401 (Unauthorized)', () => {
      const client = new NyxWebSocketClient({ wsFactory });
      const errorSpy = vi.fn();
      client.onError(errorSpy);

      client.connect();
      const socket = createdSockets[0];
      socket.simulateOpen();

      socket.simulateClose(4401, 'Unauthorized');

      vi.advanceTimersByTime(30000);

      expect(createdSockets).toHaveLength(1);
      expect(client.isConnected()).toBe(false);
      expect(errorSpy).toHaveBeenCalled();
    });
  });

  describe('AWS Full Jitter Exponential Backoff', () => {
    it('computes backoff within [0, min(maxBackoff, baseBackoff * 2^attempt)]', () => {
      const base = 500;
      const max = 10000;

      for (let attempt = 0; attempt < 8; attempt++) {
        const ceiling = Math.min(max, base * Math.pow(2, attempt));
        for (let run = 0; run < 10; run++) {
          const delay = computeFullJitterBackoff(attempt, base, max);
          expect(delay).toBeGreaterThanOrEqual(0);
          expect(delay).toBeLessThanOrEqual(ceiling);
        }
      }
    });

    it('caps maximum backoff interval at maxBackoff', () => {
      const delay = computeFullJitterBackoff(20, 500, 8000);
      expect(delay).toBeLessThanOrEqual(8000);
    });

    it('schedules automatic reconnection on abnormal disconnect (1006)', () => {
      const client = new NyxWebSocketClient({
        wsFactory,
        baseBackoffMs: 500,
        maxBackoffMs: 5000,
      });

      client.connect();
      expect(createdSockets).toHaveLength(1);

      // Simulate unexpected network drop
      createdSockets[0].simulateClose(1006, 'Abnormal Closure');

      // Advancing timer through backoff triggers reconnect
      vi.advanceTimersByTime(6000);

      expect(createdSockets).toHaveLength(2);
    });

    it('resets retry counter to 0 after connection successfully opens', () => {
      const client = new NyxWebSocketClient({
        wsFactory,
        baseBackoffMs: 500,
        maxBackoffMs: 5000,
      });

      client.connect();
      createdSockets[0].simulateClose(1006);

      vi.advanceTimersByTime(6000);
      expect(createdSockets).toHaveLength(2);

      // Successfully opens
      createdSockets[1].simulateOpen();
      expect(client.getReconnectAttempts()).toBe(0);
    });
  });

  describe('Server Event Dispatching', () => {
    it('parses and dispatches state_change and text_delta events', () => {
      const client = new NyxWebSocketClient({ wsFactory });
      const receivedEvents: any[] = [];

      client.onEvent((event) => receivedEvents.push(event));
      client.connect();
      createdSockets[0].simulateOpen();

      createdSockets[0].simulateMessage({
        type: 'state_change',
        payload: { state: 'LISTENING', turn_id: 1, timestamp: 1731000000 },
      });

      createdSockets[0].simulateMessage({
        type: 'text_delta',
        payload: { delta: 'Greetings', accumulated: 'Greetings', turn_id: 1 },
      });

      expect(receivedEvents).toHaveLength(2);
      expect(receivedEvents[0].type).toBe('state_change');
      expect(receivedEvents[1].payload.delta).toBe('Greetings');
    });
  });
});
