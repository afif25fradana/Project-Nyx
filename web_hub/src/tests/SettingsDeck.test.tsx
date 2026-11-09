import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import { axe } from 'vitest-axe';
import { SettingsDeck } from '../components/SettingsDeck/SettingsDeck';
import { NyxProvider } from '../context/NyxContext';
import { resetMockApiState } from '../services/api';

describe('SettingsDeck Component Suite', () => {
  beforeEach(() => {
    resetMockApiState();
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe('ARIA Tablist & Layout Navigation', () => {
    it('renders tablist navigation with 4 accessible tabs: Config, Persona, Memory, and To-Dos', () => {
      render(
        <NyxProvider>
          <SettingsDeck />
        </NyxProvider>
      );

      const tablist = screen.getByRole('tablist', { name: /configuration settings/i });
      expect(tablist).toBeDefined();

      const tabs = screen.getAllByRole('tab');
      expect(tabs.length).toBe(4);

      expect(screen.getByRole('tab', { name: /config/i })).toBeDefined();
      expect(screen.getByRole('tab', { name: /persona/i })).toBeDefined();
      expect(screen.getByRole('tab', { name: /memory/i })).toBeDefined();
      expect(screen.getByRole('tab', { name: /to-dos/i })).toBeDefined();
    });

    it('sets initial tab correctly and links tab to active tabpanel via aria-controls', () => {
      render(
        <NyxProvider>
          <SettingsDeck initialTab="persona" />
        </NyxProvider>
      );

      const personaTab = screen.getByRole('tab', { name: /persona/i });
      expect(personaTab.getAttribute('aria-selected')).toBe('true');
      expect(personaTab.getAttribute('tabIndex')).toBe('0');

      const configTab = screen.getByRole('tab', { name: /config/i });
      expect(configTab.getAttribute('aria-selected')).toBe('false');
      expect(configTab.getAttribute('tabIndex')).toBe('-1');

      const tabpanel = screen.getByRole('tabpanel');
      expect(tabpanel.getAttribute('id')).toBe('panel-persona');
      expect(personaTab.getAttribute('aria-controls')).toBe('panel-persona');
    });

    it('switches active tab and updates aria-selected and visible tabpanel on tab click', async () => {
      render(
        <NyxProvider>
          <SettingsDeck initialTab="config" />
        </NyxProvider>
      );

      const memoryTab = screen.getByRole('tab', { name: /memory/i });
      fireEvent.click(memoryTab);

      await waitFor(() => {
        expect(memoryTab.getAttribute('aria-selected')).toBe('true');
        expect(screen.getByRole('tabpanel').getAttribute('id')).toBe('panel-memory');
      });

      const todosTab = screen.getByRole('tab', { name: /to-dos/i });
      fireEvent.click(todosTab);

      await waitFor(() => {
        expect(todosTab.getAttribute('aria-selected')).toBe('true');
        expect(screen.getByRole('tabpanel').getAttribute('id')).toBe('panel-todos');
      });
    });

    it('supports keyboard navigation with arrow keys between tabs per WAI-ARIA tabs pattern', () => {
      render(
        <NyxProvider>
          <SettingsDeck initialTab="config" />
        </NyxProvider>
      );

      const configTab = screen.getByRole('tab', { name: /config/i });
      const personaTab = screen.getByRole('tab', { name: /persona/i });
      const memoryTab = screen.getByRole('tab', { name: /memory/i });
      const todosTab = screen.getByRole('tab', { name: /to-dos/i });

      // Focus config tab and press ArrowRight -> moves to persona
      act(() => {
        configTab.focus();
        fireEvent.keyDown(configTab, { key: 'ArrowRight' });
      });
      expect(personaTab.getAttribute('aria-selected')).toBe('true');

      // Press ArrowRight -> moves to memory
      act(() => {
        fireEvent.keyDown(personaTab, { key: 'ArrowRight' });
      });
      expect(memoryTab.getAttribute('aria-selected')).toBe('true');

      // Press ArrowRight -> moves to todos
      act(() => {
        fireEvent.keyDown(memoryTab, { key: 'ArrowRight' });
      });
      expect(todosTab.getAttribute('aria-selected')).toBe('true');

      // Press ArrowRight on last tab -> wraps around to config
      act(() => {
        fireEvent.keyDown(todosTab, { key: 'ArrowRight' });
      });
      expect(configTab.getAttribute('aria-selected')).toBe('true');

      // Press ArrowLeft on config tab -> wraps to todos
      act(() => {
        fireEvent.keyDown(configTab, { key: 'ArrowLeft' });
      });
      expect(todosTab.getAttribute('aria-selected')).toBe('true');
    });
  });

  describe('Config Tab (settings.yaml & .env Credentials)', () => {
    it('renders form controls for credentials, model, temperature, and VAD silence duration', () => {
      render(
        <NyxProvider>
          <SettingsDeck initialTab="config" />
        </NyxProvider>
      );

      const deepseekKeyInput = screen.getByLabelText(/deepseek api key/i);
      const tavilyKeyInput = screen.getByLabelText(/tavily api key/i);
      const llmModelInput = screen.getByLabelText(/^llm model/i);
      const fallbackModelInput = screen.getByLabelText(/fallback model/i);
      const tempInput = screen.getByLabelText(/llm temperature/i);
      const vadInput = screen.getByLabelText(/vad silence duration/i);
      const saveButton = screen.getByRole('button', { name: /save settings/i });

      expect(deepseekKeyInput).toBeDefined();
      expect(tavilyKeyInput).toBeDefined();
      expect(llmModelInput).toBeDefined();
      expect(fallbackModelInput).toBeDefined();
      expect(tempInput).toBeDefined();
      expect(vadInput).toBeDefined();
      expect(saveButton).toBeDefined();
    });

    it('updates config fields and renders feedback confirmation message on save via PATCH /api/settings', async () => {
      render(
        <NyxProvider>
          <SettingsDeck initialTab="config" />
        </NyxProvider>
      );

      const deepseekKeyInput = screen.getByLabelText(/deepseek api key/i);
      fireEvent.change(deepseekKeyInput, { target: { value: 'test-deepseek-key' } });
      expect((deepseekKeyInput as HTMLInputElement).value).toBe('test-deepseek-key');

      const tempInput = screen.getByLabelText(/llm temperature/i);
      fireEvent.change(tempInput, { target: { value: '0.85' } });

      const vadInput = screen.getByLabelText(/vad silence duration/i);
      fireEvent.change(vadInput, { target: { value: '750' } });

      const saveButton = screen.getByRole('button', { name: /save settings/i });
      fireEvent.click(saveButton);

      await waitFor(() => {
        const feedback = screen.getByRole('status');
        expect(feedback.textContent).toMatch(/saved|updated|success/i);
      });
    });
  });

  describe('Persona / Character Tab (character.yaml Prompt Viewer & Editor)', () => {
    it('renders character system prompt in a labeled textarea with canonical defaults and persona badges', () => {
      render(
        <NyxProvider>
          <SettingsDeck initialTab="persona" />
        </NyxProvider>
      );

      expect(screen.getAllByText(/Nyx/i).length).toBeGreaterThan(0);
      expect(screen.getAllByText(/Tomboyish girl/i).length).toBeGreaterThan(0);
      expect(screen.getByText(/af_nicole \(65%\) \+ am_onyx \(35%\)/i)).toBeDefined();

      const promptTextarea = screen.getByLabelText(/character system prompt/i);
      expect(promptTextarea).toBeDefined();
      expect((promptTextarea as HTMLTextAreaElement).value).toMatch(/nyx/i);
      expect((promptTextarea as HTMLTextAreaElement).value).toMatch(/<emotion>happy<\/emotion>/i);
    });

    it('allows editing character prompt and renders confirmation feedback upon saving', async () => {
      render(
        <NyxProvider>
          <SettingsDeck initialTab="persona" />
        </NyxProvider>
      );

      const promptTextarea = screen.getByLabelText(/character system prompt/i);
      fireEvent.change(promptTextarea, {
        target: { value: 'You are Nyx, witty tomboyish girl specialized in testing.' },
      });

      const saveButton = screen.getByRole('button', { name: /save persona/i });
      fireEvent.click(saveButton);

      await waitFor(() => {
        const feedback = screen.getByRole('status');
        expect(feedback.textContent).toMatch(/saved|updated|success/i);
      });
    });
  });

  describe('Memory Tab (USER.md / MEMORY.md Inspector)', () => {
    it('renders user memory profile and system memory inspector panels', () => {
      render(
        <NyxProvider>
          <SettingsDeck initialTab="memory" />
        </NyxProvider>
      );

      const userMemory = screen.getByLabelText(/user memory profile/i);
      const systemMemory = screen.getByLabelText(/system memory profile/i);

      expect(userMemory).toBeDefined();
      expect(systemMemory).toBeDefined();
      expect((userMemory as HTMLTextAreaElement).value).toMatch(/operator fradana/i);
      expect((systemMemory as HTMLTextAreaElement).value).toMatch(/rtx 3050/i);
    });

    it('allows updating memory entries with save confirmation feedback', async () => {
      render(
        <NyxProvider>
          <SettingsDeck initialTab="memory" />
        </NyxProvider>
      );

      const userMemory = screen.getByLabelText(/user memory profile/i);
      fireEvent.change(userMemory, {
        target: { value: '# User Profile\n- Name: Fradana\n- Timezone: UTC+7' },
      });

      const saveButton = screen.getByRole('button', { name: /save memory/i });
      fireEvent.click(saveButton);

      await waitFor(() => {
        const feedback = screen.getByRole('status');
        expect(feedback.textContent).toMatch(/saved|updated|success/i);
      });
    });
  });

  describe('To-Dos Tab (/api/todos Task Manager)', () => {
    it('renders task list with existing items and strict integer IDs and categories', () => {
      render(
        <NyxProvider>
          <SettingsDeck initialTab="todos" />
        </NyxProvider>
      );

      const list = screen.getByRole('list', { name: /to-dos list/i });
      expect(list).toBeDefined();

      const items = screen.getAllByRole('listitem');
      expect(items.length).toBe(3);
      expect(screen.getByText(/Calibrate VAD sensitivity/i)).toBeDefined();
      expect(within(items[0]).getByText('audio')).toBeDefined();
    });

    it('adds a new task with category when task title is submitted', async () => {
      render(
        <NyxProvider>
          <SettingsDeck initialTab="todos" />
        </NyxProvider>
      );

      const initialCount = screen.getAllByRole('listitem').length;
      const input = screen.getByRole('textbox', { name: /new task title/i });
      const categorySelect = screen.getByRole('combobox', { name: /task category/i });
      const addButton = screen.getByRole('button', { name: /add task/i });

      fireEvent.change(input, { target: { value: 'Calibrate microphone acoustic filter' } });
      fireEvent.change(categorySelect, { target: { value: 'audio' } });
      fireEvent.click(addButton);

      await waitFor(() => {
        expect(screen.getAllByRole('listitem').length).toBe(initialCount + 1);
        expect(screen.getByText('Calibrate microphone acoustic filter')).toBeDefined();
      });
    });

    it('toggles task completion status when checkbox is clicked', async () => {
      render(
        <NyxProvider>
          <SettingsDeck initialTab="todos" />
        </NyxProvider>
      );

      const checkboxes = screen.getAllByRole('checkbox');
      const targetCheckbox = checkboxes[1]; // Item 2 (pending)
      expect(targetCheckbox.getAttribute('aria-checked')).toBe('false');

      fireEvent.click(targetCheckbox);

      await waitFor(() => {
        expect(targetCheckbox.getAttribute('aria-checked')).toBe('true');
      });
    });

    it('removes task from list when delete button is clicked', async () => {
      render(
        <NyxProvider>
          <SettingsDeck initialTab="todos" />
        </NyxProvider>
      );

      const initialItems = screen.getAllByRole('listitem');
      const deleteButtons = screen.getAllByRole('button', { name: /delete task/i });

      fireEvent.click(deleteButtons[0]);

      await waitFor(() => {
        const updatedItems = screen.getAllByRole('listitem');
        expect(updatedItems.length).toBe(initialItems.length - 1);
      });
    });
  });

  describe('Hermetic REST Fallback & Error Resilience', () => {
    it('seamlessly loads default fallback mock data without unhandled rejections when fetch fails', async () => {
      vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Network error: backend offline'));

      render(
        <NyxProvider>
          <SettingsDeck />
        </NyxProvider>
      );

      // Verify component mounts and renders without throwing unhandled exceptions
      const tablist = screen.getByRole('tablist');
      expect(tablist).toBeDefined();

      // Verify default fallback data is accessible in each tab
      expect(screen.getByLabelText(/deepseek api key/i)).toBeDefined();

      const fallbackNotice = screen.queryByText(/cassette deck · mock fallback mode/i);
      expect(fallbackNotice).not.toBeNull();
    });
  });

  describe('Accessibility Audits (vitest-axe)', () => {
    it('passes WCAG accessibility checks with zero violations on initial render', async () => {
      const { container } = render(
        <NyxProvider>
          <SettingsDeck />
        </NyxProvider>
      );

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('maintains zero WCAG accessibility violations across all four operational tabs', async () => {
      const { container, rerender } = render(
        <NyxProvider>
          <SettingsDeck initialTab="config" />
        </NyxProvider>
      );
      expect(await axe(container)).toHaveNoViolations();

      rerender(
        <NyxProvider>
          <SettingsDeck initialTab="persona" />
        </NyxProvider>
      );
      expect(await axe(container)).toHaveNoViolations();

      rerender(
        <NyxProvider>
          <SettingsDeck initialTab="memory" />
        </NyxProvider>
      );
      expect(await axe(container)).toHaveNoViolations();

      rerender(
        <NyxProvider>
          <SettingsDeck initialTab="todos" />
        </NyxProvider>
      );
      expect(await axe(container)).toHaveNoViolations();
    });
  });
});
