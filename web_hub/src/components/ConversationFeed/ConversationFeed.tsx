import React, { useState, useRef, useEffect } from 'react';
import { useNyx, type NyxMessage } from '../../context/NyxContext';
import { cn } from '../../utils/cn';

export interface ConversationFeedProps {
  initialMessages?: NyxMessage[];
  className?: string;
}

/**
 * ConversationFeed displays bidirectional turn-by-turn chat history
 * between user and assistant, streaming deltas, and an accessible message input.
 */
export const ConversationFeed: React.FC<ConversationFeedProps> = ({
  initialMessages,
  className,
}) => {
  const { state, sendText } = useNyx();
  const [inputText, setInputText] = useState('');
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const messages = initialMessages ?? state.messages;

  useEffect(() => {
    if (typeof messagesEndRef.current?.scrollIntoView === 'function') {
      messagesEndRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages]);

  const handleSend = () => {
    const trimmed = inputText.trim();
    if (!trimmed) return;
    sendText(trimmed);
    setInputText('');
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    handleSend();
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div
      className={cn(
        'flex flex-col h-full bg-panel-800 border border-panel-border rounded-lg overflow-hidden',
        className
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-panel-border bg-panel-750">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-amber-glow" aria-hidden="true" />
          <h2 className="text-xs font-mono uppercase tracking-wider text-ink-primary font-semibold">
            Conversation Stream
          </h2>
        </div>
        <span className="text-[10px] font-mono text-ink-secondary">
          {messages.length} TURNS
        </span>
      </div>

      {/* Message Feed / Log */}
      <div
        role="log"
        aria-label="Conversation log"
        aria-live="polite"
        className="flex-1 overflow-y-auto p-4 space-y-3 bg-panel-recessed"
      >
        {messages.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center text-center p-6 text-ink-muted">
            <span className="text-sm font-mono tracking-wide text-ink-secondary">
              Standby · Ready for conversation
            </span>
            <span className="text-xs text-ink-muted mt-1">
              Transmit a text query or speak into the microphone.
            </span>
          </div>
        ) : (
          messages.map((msg) => {
            const isUser = msg.sender === 'user';
            return (
              <div
                key={msg.id}
                className={cn('flex flex-col', isUser ? 'items-end' : 'items-start')}
              >
                <div className="flex items-center gap-2 mb-1 text-[10px] font-mono text-ink-secondary">
                  <span className="uppercase font-semibold text-ink-muted">
                    {isUser ? 'Operator' : 'Nyx'}
                  </span>
                  {msg.turnId !== undefined && (
                    <span className="text-ink-muted">#{msg.turnId}</span>
                  )}
                </div>

                <div
                  className={cn(
                    'max-w-[85%] rounded px-3 py-2 text-sm leading-relaxed whitespace-pre-wrap break-words border',
                    isUser
                      ? 'bg-panel-700 text-ink-primary border-panel-border'
                      : 'bg-panel-850 text-ink-primary border-panel-border/80'
                  )}
                >
                  {msg.text}

                  {/* Streaming pulse indicator */}
                  {msg.isStreaming && (
                    <div
                      data-testid="streaming-indicator"
                      role="status"
                      aria-label="Generating response"
                      className="inline-flex items-center gap-1 mt-2 text-xs font-mono text-amber-glow"
                    >
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-glow animate-pulse" />
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-glow animate-pulse delay-100" />
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-glow animate-pulse delay-200" />
                      <span className="ml-1 text-[11px] text-ink-muted">Synthesizing...</span>
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Accessible Input Form */}
      <form
        onSubmit={handleSubmit}
        className="p-3 border-t border-panel-border bg-panel-750 flex items-end gap-2"
      >
        <textarea
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          aria-label="Message input"
          placeholder="Type a message... (Enter to send, Shift+Enter for newline)"
          rows={1}
          className="flex-1 px-3 py-2 text-sm text-ink-primary bg-panel-recessed border border-panel-border rounded resize-none focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow placeholder:text-ink-muted/50"
        />
        <button
          type="submit"
          aria-label="Send message"
          className="px-4 py-2 text-xs font-mono uppercase tracking-wider rounded bg-panel-700 hover:bg-panel-800 text-amber-glow border border-panel-border transition-colors cursor-pointer"
        >
          Send
        </button>
      </form>
    </div>
  );
};
