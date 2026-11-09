import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, within } from '@testing-library/react';
import { axe } from 'vitest-axe';
import React from 'react';
import App from '../App';

describe('App Full 12-Column Layout Integration Suite', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('Heading & Retro Tech Branding', () => {
    it('renders the application heading and retro status badge', () => {
      render(<App />);

      const heading = screen.getByRole('heading', { level: 1, name: /Project Nyx/i });
      expect(heading).toBeDefined();

      const statusBadge = screen.getByRole('status');
      expect(statusBadge.textContent).toMatch(/ready|online|operational/i);
    });

    it('renders sub-header metadata describing the local control deck architecture', () => {
      render(<App />);

      const subHeader = screen.getByText(/Control Deck|Telemetry Deck|Pure ONNX Pipeline/i);
      expect(subHeader).toBeDefined();
    });
  });

  describe('12-Column Operational Grid & Module Integration', () => {
    it('renders the full 12-column layout container', () => {
      const { container } = render(<App />);

      const gridContainer =
        container.querySelector('.grid-cols-12') ||
        container.querySelector('[data-testid="deck-grid"]') ||
        container.querySelector('main');

      expect(gridContainer, 'App must mount a primary layout grid').not.toBeNull();
    });

    it('integrates AvatarStage CRT visualizer', () => {
      render(<App />);

      const avatarStage = screen.getByRole('region', { name: /avatar stage/i });
      expect(avatarStage).toBeDefined();
    });

    it('integrates ControlDeck hardware control pod with mute switch and interrupt actuator', () => {
      render(<App />);

      const muteSwitch = screen.getByRole('switch', { name: /mute|microphone/i });
      expect(muteSwitch).toBeDefined();

      const interruptButton = screen.getByRole('button', { name: /interrupt/i });
      expect(interruptButton).toBeDefined();
    });

    it('integrates PipelineTerminal telemetry waterfall display', () => {
      const { container } = render(<App />);

      const terminal =
        container.querySelector('[data-testid="pipeline-terminal"]') ||
        screen.queryByText(/telemetry waterfall/i);

      expect(terminal, 'PipelineTerminal must be integrated into main layout').not.toBeNull();
    });

    it('integrates ConversationFeed chat stream and message input', () => {
      render(<App />);

      const conversationLog = screen.getByRole('log', { name: /conversation/i });
      expect(conversationLog).toBeDefined();

      const messageInput = screen.getByRole('textbox', { name: /message input|send a message/i });
      expect(messageInput).toBeDefined();
    });

    it('integrates SettingsDeck with 4 operational tabs', () => {
      render(<App />);

      const tablist = screen.getByRole('tablist', { name: /settings|configuration/i });
      expect(tablist).toBeDefined();

      const tabs = within(tablist).getAllByRole('tab');
      expect(tabs.length).toBe(4);

      expect(within(tablist).getByRole('tab', { name: /config|settings/i })).toBeDefined();
      expect(within(tablist).getByRole('tab', { name: /persona|character/i })).toBeDefined();
      expect(within(tablist).getByRole('tab', { name: /memory/i })).toBeDefined();
      expect(within(tablist).getByRole('tab', { name: /to-dos|todos|tasks/i })).toBeDefined();
    });
  });

  describe('WCAG Accessibility Compliance (vitest-axe)', () => {
    it('passes comprehensive WCAG accessibility audits with zero violations', async () => {
      const { container } = render(<App />);

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });
});
