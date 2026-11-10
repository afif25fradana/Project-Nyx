import type { ClientCommand, ServerEvent } from '../types/websocket';

export type WebSocketStatus = 'CONNECTING' | 'OPEN' | 'CLOSING' | 'CLOSED';

export interface WebSocketClientOptions {
  url?: string;
  wsFactory?: (url: string) => WebSocket;
  webSocketFactory?: (url: string) => WebSocket;
  token?: string;
  baseBackoffMs?: number;
  maxBackoffMs?: number;
}

/**
 * Computes exponential backoff with AWS Full Jitter:
 * Sleep = random_between(0, min(maxBackoff, baseBackoff * 2^attempt))
 */
export function computeFullJitterBackoff(
  attempt: number,
  baseBackoffMs: number = 500,
  maxBackoffMs: number = 10000
): number {
  const ceiling = Math.min(maxBackoffMs, baseBackoffMs * Math.pow(2, attempt));
  return Math.floor(Math.random() * (ceiling + 1));
}

export function getDefaultWebSocketUrl(): string {
  if (typeof window !== 'undefined' && window.location && window.location.host) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${protocol}//${window.location.host}/ws/client`;
  }
  return 'ws://127.0.0.1:8765/ws/client';
}

export class NyxWebSocketClient {
  private readonly url: string;
  private readonly wsFactory: (url: string) => WebSocket;
  private readonly baseBackoffMs: number;
  private readonly maxBackoffMs: number;

  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private isPermanentlyClosed = false;

  private statusListeners = new Set<(status: WebSocketStatus) => void>();
  private eventListeners = new Set<(event: ServerEvent) => void>();
  private errorListeners = new Set<(error: any) => void>();

  constructor(options: WebSocketClientOptions = {}) {
    const rawUrl = options.url || getDefaultWebSocketUrl();
    if (options.token) {
      const separator = rawUrl.includes('?') ? (rawUrl.endsWith('?') || rawUrl.endsWith('&') ? '' : '&') : '?';
      this.url = `${rawUrl}${separator}token=${encodeURIComponent(options.token)}`;
    } else {
      this.url = rawUrl;
    }
    this.wsFactory =
      options.wsFactory ||
      options.webSocketFactory ||
      ((endpoint: string) => new WebSocket(endpoint));
    this.baseBackoffMs = options.baseBackoffMs ?? 500;
    this.maxBackoffMs = options.maxBackoffMs ?? 10000;
  }

  public getUrl(): string {
    return this.url;
  }

  public connect(): void {
    if (this.isPermanentlyClosed) {
      return;
    }

    if (this.ws && (this.ws.readyState === 0 || this.ws.readyState === 1)) {
      return;
    }

    this.notifyStatus('CONNECTING');

    try {
      const socket = this.wsFactory(this.url);
      this.ws = socket;

      socket.onopen = () => {
        this.reconnectAttempts = 0;
        this.notifyStatus('OPEN');
      };

      socket.onmessage = (event: MessageEvent) => {
        try {
          const parsed = typeof event.data === 'string' ? JSON.parse(event.data) : event.data;
          this.notifyEvent(parsed as ServerEvent);
        } catch (err) {
          this.notifyError(err);
        }
      };

      socket.onerror = (event: Event) => {
        this.notifyError(event);
      };

      socket.onclose = (event: CloseEvent) => {
        this.notifyStatus('CLOSED');

        // Permanently halt reconnect on auth failure (1008 Policy Violation or 4401 Unauthorized)
        if (event.code === 1008 || event.code === 4401) {
          this.isPermanentlyClosed = true;
          this.notifyError(
            new Error(`WebSocket authorization failure: code ${event.code} (${event.reason || 'Unauthorized'})`)
          );
          return;
        }

        // Schedule reconnection on unexpected disconnection (e.g. 1006)
        if (!this.isPermanentlyClosed && event.code !== 1000) {
          const delay = computeFullJitterBackoff(
            this.reconnectAttempts,
            this.baseBackoffMs,
            this.maxBackoffMs
          );
          this.reconnectAttempts++;

          if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
          }

          this.reconnectTimer = setTimeout(() => {
            this.connect();
          }, delay);
        }
      };
    } catch (err) {
      this.notifyError(err);
    }
  }

  public send(command: ClientCommand): void {
    if (!this.ws || this.ws.readyState !== 1) {
      return;
    }
    this.ws.send(JSON.stringify(command));
  }

  public sendText(text: string): void {
    this.send({
      action: 'send_text',
      text,
    });
  }

  public toggleMute(muted: boolean): void {
    this.send({
      action: 'mute_toggle',
      muted,
    });
  }

  public interrupt(reason?: string): void {
    this.send({
      action: 'interrupt',
      ...(reason ? { reason } : {}),
    });
  }

  public isConnected(): boolean {
    return Boolean(this.ws && this.ws.readyState === 1 && !this.isPermanentlyClosed);
  }

  public getReconnectAttempts(): number {
    return this.reconnectAttempts;
  }

  public disconnect(): void {
    this.isPermanentlyClosed = true;
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close(1000, 'Client disconnected');
      this.ws = null;
    }
    this.notifyStatus('CLOSED');
  }

  public onStatusChange(listener: (status: WebSocketStatus) => void): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  public onEvent(listener: (event: ServerEvent) => void): () => void {
    this.eventListeners.add(listener);
    return () => this.eventListeners.delete(listener);
  }

  public onError(listener: (error: any) => void): () => void {
    this.errorListeners.add(listener);
    return () => this.errorListeners.delete(listener);
  }

  private notifyStatus(status: WebSocketStatus): void {
    this.statusListeners.forEach((listener) => {
      try {
        listener(status);
      } catch (err) {
        console.error('Error in status change listener:', err);
      }
    });
  }

  private notifyEvent(event: ServerEvent): void {
    this.eventListeners.forEach((listener) => {
      try {
        listener(event);
      } catch (err) {
        console.error('Error in event listener:', err);
      }
    });
  }

  private notifyError(error: any): void {
    this.errorListeners.forEach((listener) => {
      try {
        listener(error);
      } catch (err) {
        console.error('Error in error listener:', err);
      }
    });
  }
}
