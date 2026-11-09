export class MockWebSocket {
  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  readonly CONNECTING = 0;
  readonly OPEN = 1;
  readonly CLOSING = 2;
  readonly CLOSED = 3;

  url: string;
  protocols?: string | string[];
  readyState: number = MockWebSocket.CONNECTING;
  sentMessages: string[] = [];

  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;

  private listeners: Map<string, Set<(event: any) => void>> = new Map();

  constructor(url: string, protocols?: string | string[]) {
    this.url = url;
    this.protocols = protocols;
  }

  send(data: string): void {
    if (this.readyState !== MockWebSocket.OPEN) {
      throw new Error(`InvalidStateError: WebSocket is not open (readyState=${this.readyState})`);
    }
    this.sentMessages.push(data);
  }

  close(code: number = 1000, reason: string = ''): void {
    if (this.readyState === MockWebSocket.CLOSED || this.readyState === MockWebSocket.CLOSING) {
      return;
    }
    this.readyState = MockWebSocket.CLOSING;
    setTimeout(() => {
      this.readyState = MockWebSocket.CLOSED;
      const event = { type: 'close', code, reason, wasClean: code === 1000 } as CloseEvent;
      this.onclose?.(event);
      this.dispatchEvent('close', event);
    }, 0);
  }

  addEventListener(type: string, listener: (event: any) => void): void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type)!.add(listener);
  }

  removeEventListener(type: string, listener: (event: any) => void): void {
    this.listeners.get(type)?.delete(listener);
  }

  dispatchEvent(type: string, event: any): boolean {
    const set = this.listeners.get(type);
    if (set) {
      set.forEach((listener) => listener(event));
    }
    return true;
  }

  // --- Test Simulation Helpers ---

  simulateOpen(): void {
    this.readyState = MockWebSocket.OPEN;
    const event = { type: 'open' } as Event;
    this.onopen?.(event);
    this.dispatchEvent('open', event);
  }

  simulateMessage(data: unknown): void {
    const rawData = typeof data === 'string' ? data : JSON.stringify(data);
    const event = { type: 'message', data: rawData } as MessageEvent;
    this.onmessage?.(event);
    this.dispatchEvent('message', event);
  }

  simulateError(errorEvent?: any): void {
    const event = errorEvent || ({ type: 'error' } as Event);
    this.onerror?.(event);
    this.dispatchEvent('error', event);
  }

  simulateClose(code: number = 1000, reason: string = ''): void {
    this.readyState = MockWebSocket.CLOSED;
    const event = { type: 'close', code, reason, wasClean: code === 1000 } as CloseEvent;
    this.onclose?.(event);
    this.dispatchEvent('close', event);
  }

  triggerOpen(): void {
    this.simulateOpen();
  }

  triggerMessage(data: unknown): void {
    this.simulateMessage(data);
  }

  triggerError(errorEvent?: any): void {
    this.simulateError(errorEvent);
  }

  triggerClose(code: number = 1000, reason: string = ''): void {
    this.simulateClose(code, reason);
  }
}
