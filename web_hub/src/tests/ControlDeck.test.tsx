import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { axe } from 'vitest-axe';
import React from 'react';
import { ControlDeck } from '../components/ControlDeck/ControlDeck';
import { NyxProvider } from '../context/NyxContext';
import { NyxWebSocketClient } from '../services/websocket';
import { MockWebSocket } from './fixtures/mockWebSocket';

describe('ControlDeck Hardware Control Pod Suite', () => {
  it('renders mute toggle switch with standard role="switch" and accessible name', () => {
    render(
      <NyxProvider>
        <ControlDeck />
      </NyxProvider>
    );

    const muteSwitch = screen.getByRole('switch', { name: /mute|microphone/i });
    expect(muteSwitch).toBeDefined();
    expect(muteSwitch.getAttribute('aria-checked')).toBe('false');
  });

  it('toggles aria-checked state when mute switch is clicked and dispatches toggleMute', () => {
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

    const muteSpy = vi.spyOn(client, 'toggleMute');

    render(
      <NyxProvider client={client}>
        <ControlDeck />
      </NyxProvider>
    );

    const muteSwitch = screen.getByRole('switch', { name: /mute|microphone/i });
    expect(muteSwitch.getAttribute('aria-checked')).toBe('false');

    fireEvent.click(muteSwitch);

    expect(muteSpy).toHaveBeenCalledWith(true);
    expect(muteSwitch.getAttribute('aria-checked')).toBe('true');

    client.disconnect();
  });

  it('illuminates red LED indicator when muted', () => {
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

    const { container } = render(
      <NyxProvider client={client}>
        <ControlDeck />
      </NyxProvider>
    );

    // Initial state: unmuted -> LED red is off
    const muteSwitch = screen.getByRole('switch', { name: /mute|microphone/i });
    let ledElement =
      container.querySelector('[data-testid="led-mute"]') ||
      container.querySelector('.led-mute-active') ||
      container.querySelector('.bg-red-500');

    // Click mute to engage mute state
    fireEvent.click(muteSwitch);

    ledElement =
      container.querySelector('[data-testid="led-mute"]') ||
      container.querySelector('.led-mute-active') ||
      container.querySelector('.bg-red-500');

    expect(ledElement, 'Red LED indicator must illuminate when muted').not.toBeNull();

    client.disconnect();
  });

  it('renders interrupt button and dispatches interrupt on click', () => {
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

    const interruptSpy = vi.spyOn(client, 'interrupt');

    render(
      <NyxProvider client={client}>
        <ControlDeck />
      </NyxProvider>
    );

    const interruptButton = screen.getByRole('button', { name: /interrupt|abort|stop/i });
    fireEvent.click(interruptButton);

    expect(interruptSpy).toHaveBeenCalled();

    client.disconnect();
  });

  it('passes automated accessibility audit with zero axe violations', async () => {
    const { container } = render(
      <NyxProvider>
        <ControlDeck />
      </NyxProvider>
    );

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
