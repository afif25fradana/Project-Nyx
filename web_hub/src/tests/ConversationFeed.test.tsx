import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import { ConversationFeed } from '../components/ConversationFeed/ConversationFeed';
import {
  NyxProvider,
  type NyxMessage,
} from '../context/NyxContext';
import { NyxWebSocketClient } from '../services/websocket';
import { MockWebSocket } from './fixtures/mockWebSocket';

describe('ConversationFeed Component Suite', () => {
  it('renders empty feed placeholder or standby notice when message history is empty', () => {
    render(
      <NyxProvider>
        <ConversationFeed />
      </NyxProvider>
    );

    const logContainer = screen.getByRole('log', { name: /conversation/i });
    expect(logContainer).toBeDefined();
  });

  it('renders conversation history with distinct user and assistant messages', () => {
    const initialMessages: NyxMessage[] = [
      {
        id: 'msg-1',
        sender: 'user',
        text: 'What is the system status?',
        turnId: 1,
        timestamp: 1731000001,
      },
      {
        id: 'msg-2',
        sender: 'assistant',
        text: 'All local speech pipelines operational.',
        turnId: 1,
        isStreaming: false,
        timestamp: 1731000002,
      },
    ];

    render(
      <NyxProvider>
        <ConversationFeed initialMessages={initialMessages} />
      </NyxProvider>
    );

    expect(screen.getByText('What is the system status?')).toBeDefined();
    expect(screen.getByText('All local speech pipelines operational.')).toBeDefined();
  });

  it('displays streaming indicator on active assistant turn during text delta accumulation', () => {
    const streamingMessages: NyxMessage[] = [
      {
        id: 'msg-streaming',
        sender: 'assistant',
        text: 'Generating thought process',
        turnId: 2,
        isStreaming: true,
        timestamp: 1731000010,
      },
    ];

    const { container } = render(
      <NyxProvider>
        <ConversationFeed initialMessages={streamingMessages} />
      </NyxProvider>
    );

    const streamingElement =
      container.querySelector('[data-testid="streaming-indicator"]') ||
      screen.queryByRole('status');

    expect(streamingElement, 'Streaming indicator must be visible on streaming turn').not.toBeNull();
  });

  it('does not display streaming indicator when message streaming is complete', () => {
    const completedMessages: NyxMessage[] = [
      {
        id: 'msg-complete',
        sender: 'assistant',
        text: 'Completed synthesis.',
        turnId: 3,
        isStreaming: false,
        timestamp: 1731000020,
      },
    ];

    const { container } = render(
      <NyxProvider>
        <ConversationFeed initialMessages={completedMessages} />
      </NyxProvider>
    );

    const streamingElement = container.querySelector('[data-testid="streaming-indicator"]');
    expect(streamingElement).toBeNull();
  });

  it('submits text and invokes sendText when form is submitted with non-empty input', () => {
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

    const sendSpy = vi.spyOn(client, 'sendText');

    render(
      <NyxProvider client={client}>
        <ConversationFeed />
      </NyxProvider>
    );

    const input = screen.getByRole('textbox', { name: /message input|type a message/i });
    const submitButton = screen.getByRole('button', { name: /send|submit/i });

    fireEvent.change(input, { target: { value: 'Hello Nyx' } });
    fireEvent.click(submitButton);

    expect(sendSpy).toHaveBeenCalledWith('Hello Nyx');
    expect((input as HTMLInputElement).value).toBe('');

    client.disconnect();
  });

  it('prevents submission when input text is empty or contains only whitespace', () => {
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

    const sendSpy = vi.spyOn(client, 'sendText');

    render(
      <NyxProvider client={client}>
        <ConversationFeed />
      </NyxProvider>
    );

    const input = screen.getByRole('textbox', { name: /message input|type a message/i });
    const submitButton = screen.getByRole('button', { name: /send|submit/i });

    // Attempt 1: Empty string
    fireEvent.change(input, { target: { value: '' } });
    fireEvent.click(submitButton);
    expect(sendSpy).not.toHaveBeenCalled();

    // Attempt 2: Whitespace only
    fireEvent.change(input, { target: { value: '   \n  \t  ' } });
    fireEvent.click(submitButton);
    expect(sendSpy).not.toHaveBeenCalled();

    client.disconnect();
  });

  it('supports Enter key submission while allowing Shift+Enter for multiline inputs', () => {
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

    const sendSpy = vi.spyOn(client, 'sendText');

    render(
      <NyxProvider client={client}>
        <ConversationFeed />
      </NyxProvider>
    );

    const input = screen.getByRole('textbox', { name: /message input|type a message/i });

    // Shift+Enter should NOT submit
    fireEvent.change(input, { target: { value: 'Line 1' } });
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: true });
    expect(sendSpy).not.toHaveBeenCalled();

    // Plain Enter SHOULD submit
    fireEvent.keyDown(input, { key: 'Enter', shiftKey: false });
    expect(sendSpy).toHaveBeenCalledWith('Line 1');

    client.disconnect();
  });
});
