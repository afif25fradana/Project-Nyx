import React, { useState, useEffect, useRef } from 'react';
import {
  fetchSettings,
  saveSettings,
  fetchCharacter,
  saveCharacter,
  fetchMemoryFile,
  saveMemoryFile,
  fetchTodos,
  createTodo,
  updateTodoStatus,
  deleteTodo,
  DEFAULT_SETTINGS,
  DEFAULT_CHARACTER,
  DEFAULT_USER_MEMORY,
  DEFAULT_SYSTEM_MEMORY,
  DEFAULT_TODOS,
  type SettingsConfig,
  type CharacterConfig,
  type TodoItem,
} from '../../services/api';
import { cn } from '../../utils/cn';

export interface SettingsDeckProps {
  initialTab?: 'config' | 'persona' | 'memory' | 'todos';
  className?: string;
}

interface TabItem {
  id: 'config' | 'persona' | 'memory' | 'todos';
  label: string;
}

const TABS: TabItem[] = [
  { id: 'config', label: 'Config' },
  { id: 'persona', label: 'Persona' },
  { id: 'memory', label: 'Memory' },
  { id: 'todos', label: 'To-Dos' },
];

/**
 * SettingsDeck provides a retro hardware cassette configuration console
 * strictly matching backend/config/settings.yaml, backend/config/character.yaml,
 * MarkdownStore (USER.md / MEMORY.md), and SQLite TodoStore contracts.
 */
export const SettingsDeck: React.FC<SettingsDeckProps> = ({
  initialTab = 'config',
  className,
}) => {
  const [activeTab, setActiveTab] = useState<'config' | 'persona' | 'memory' | 'todos'>(initialTab);
  const [config, setConfig] = useState<SettingsConfig>(DEFAULT_SETTINGS);
  const [character, setCharacter] = useState<CharacterConfig>(DEFAULT_CHARACTER);
  const [userMemory, setUserMemory] = useState<string>(DEFAULT_USER_MEMORY.content);
  const [systemMemory, setSystemMemory] = useState<string>(DEFAULT_SYSTEM_MEMORY.content);
  const [todos, setTodos] = useState<TodoItem[]>(DEFAULT_TODOS);
  const [newTodoTitle, setNewTodoTitle] = useState('');
  const [newTodoCategory, setNewTodoCategory] = useState('general');
  const [statusFeedback, setStatusFeedback] = useState<string | null>(null);

  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const configRef = useRef(config);
  configRef.current = config;
  const characterRef = useRef(character);
  characterRef.current = character;
  const userMemRef = useRef(userMemory);
  userMemRef.current = userMemory;
  const sysMemRef = useRef(systemMemory);
  sysMemRef.current = systemMemory;
  const todosRef = useRef(todos);
  todosRef.current = todos;

  useEffect(() => {
    let isMounted = true;

    Promise.allSettled([
      fetchSettings(),
      fetchCharacter(),
      fetchMemoryFile('USER.md'),
      fetchMemoryFile('MEMORY.md'),
      fetchTodos('all'),
    ]).then(([settingsRes, charRes, userMemRes, sysMemRes, todosRes]) => {
      if (!isMounted) return;
      if (
        settingsRes.status === 'fulfilled' &&
        JSON.stringify(settingsRes.value) !== JSON.stringify(configRef.current)
      ) {
        setConfig(settingsRes.value);
      }
      if (
        charRes.status === 'fulfilled' &&
        JSON.stringify(charRes.value) !== JSON.stringify(characterRef.current)
      ) {
        setCharacter(charRes.value);
      }
      if (
        userMemRes.status === 'fulfilled' &&
        userMemRes.value.content !== userMemRef.current
      ) {
        setUserMemory(userMemRes.value.content);
      }
      if (
        sysMemRes.status === 'fulfilled' &&
        sysMemRes.value.content !== sysMemRef.current
      ) {
        setSystemMemory(sysMemRes.value.content);
      }
      if (
        todosRes.status === 'fulfilled' &&
        JSON.stringify(todosRes.value) !== JSON.stringify(todosRef.current)
      ) {
        setTodos(todosRes.value);
      }
    }).catch(() => {
      // Offline fallback state already initialized synchronously
    });

    return () => {
      isMounted = false;
    };
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent, index: number) => {
    let targetIndex: number | null = null;

    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      e.preventDefault();
      targetIndex = (index + 1) % TABS.length;
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      e.preventDefault();
      targetIndex = (index - 1 + TABS.length) % TABS.length;
    } else if (e.key === 'Home') {
      e.preventDefault();
      targetIndex = 0;
    } else if (e.key === 'End') {
      e.preventDefault();
      targetIndex = TABS.length - 1;
    }

    if (targetIndex !== null) {
      setActiveTab(TABS[targetIndex].id);
      setStatusFeedback(null);
      tabRefs.current[targetIndex]?.focus();
    }
  };

  const handleSaveConfig = async () => {
    try {
      await saveSettings(config);
    } finally {
      setStatusFeedback('Configuration saved successfully');
    }
  };

  const handleSaveCharacter = async () => {
    try {
      await saveCharacter(character);
    } finally {
      setStatusFeedback('Character prompt saved successfully');
    }
  };

  const handleSaveMemory = async () => {
    try {
      await Promise.all([
        saveMemoryFile('USER.md', userMemory),
        saveMemoryFile('MEMORY.md', systemMemory),
      ]);
    } finally {
      setStatusFeedback('Memory profile saved successfully');
    }
  };

  const handleAddTodo = async () => {
    const trimmed = newTodoTitle.trim();
    if (!trimmed) return;

    const nextId = todos.length > 0 ? Math.max(...todos.map((t) => t.id)) + 1 : 1;
    const optimisticItem: TodoItem = {
      id: nextId,
      title: trimmed,
      category: newTodoCategory,
      status: 'pending',
      completed: 0,
      created_at: new Date().toISOString(),
    };

    setTodos((prev) => [...prev, optimisticItem]);
    setNewTodoTitle('');

    try {
      const created = await createTodo(trimmed, newTodoCategory);
      setTodos((prev) =>
        prev.map((t) => (t.id === optimisticItem.id ? created : t))
      );
    } catch {
      // Optimistic item retained
    }
  };

  const handleToggleTodo = async (id: number) => {
    const target = todos.find((t) => t.id === id);
    if (!target) return;
    const nextStatus: 'pending' | 'completed' =
      target.status === 'completed' ? 'pending' : 'completed';

    setTodos((prev) =>
      prev.map((t) =>
        t.id === id
          ? { ...t, status: nextStatus, completed: nextStatus === 'completed' ? 1 : 0 }
          : t
      )
    );

    try {
      await updateTodoStatus(id, nextStatus);
    } catch {
      // Optimistic update retained
    }
  };

  const handleDeleteTodo = async (id: number) => {
    setTodos((prev) => prev.filter((t) => t.id !== id));
    try {
      await deleteTodo(id);
    } catch {
      // Optimistic deletion retained
    }
  };

  const currentTabItem = TABS.find((t) => t.id === activeTab) || TABS[0];

  return (
    <div
      className={cn(
        'flex flex-col bg-panel-800 border border-panel-border rounded-lg overflow-hidden',
        className
      )}
    >
      {/* Console Header Bar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-panel-750 border-b border-panel-border">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-amber-glow" aria-hidden="true" />
          <h2 className="text-xs font-mono uppercase tracking-wider text-ink-primary font-semibold">
            Configuration Console
          </h2>
        </div>
        <span className="text-[10px] font-mono text-ink-secondary uppercase tracking-wider">
          Cassette Deck · Mock Fallback Mode
        </span>
      </div>

      {/* Accessible Tablist */}
      <div
        role="tablist"
        aria-label="Configuration Settings"
        className="flex items-center gap-1 border-b border-panel-border bg-panel-850 px-3 pt-2"
      >
        {TABS.map((tab, index) => {
          const isSelected = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              ref={(el) => {
                tabRefs.current[index] = el;
              }}
              type="button"
              role="tab"
              id={`tab-${tab.id}`}
              aria-selected={isSelected}
              aria-controls={`panel-${tab.id}`}
              tabIndex={isSelected ? 0 : -1}
              onClick={() => {
                setActiveTab(tab.id);
                setStatusFeedback(null);
              }}
              onKeyDown={(e) => handleKeyDown(e, index)}
              className={cn(
                'px-3 py-1.5 text-xs font-mono uppercase tracking-wider transition-colors border-t border-x rounded-t cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow',
                isSelected
                  ? 'bg-panel-800 text-amber-phosphor border-panel-border font-semibold shadow-sm'
                  : 'bg-transparent text-ink-secondary border-transparent hover:text-ink-primary hover:bg-panel-800/40'
              )}
            >
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Active Tabpanel */}
      <div
        role="tabpanel"
        id={`panel-${activeTab}`}
        title={currentTabItem.label}
        tabIndex={0}
        className="p-4 flex-1 overflow-y-auto focus:outline-none"
      >
        {activeTab === 'config' && (
          <div className="space-y-4">
            {/* Credentials Section */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1">
                <label
                  htmlFor="settings-deepseek-api-key"
                  className="block text-xs font-mono uppercase tracking-wider text-ink-secondary"
                >
                  DeepSeek API Key
                </label>
                <input
                  id="settings-deepseek-api-key"
                  type="password"
                  value={config.deepseek_api_key ?? ''}
                  onChange={(e) =>
                    setConfig({ ...config, deepseek_api_key: e.target.value })
                  }
                  placeholder="<API_KEY>"
                  className="w-full px-3 py-2 text-sm text-ink-primary bg-panel-recessed border border-panel-border rounded font-mono focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow"
                />
              </div>

              <div className="space-y-1">
                <label
                  htmlFor="settings-tavily-api-key"
                  className="block text-xs font-mono uppercase tracking-wider text-ink-secondary"
                >
                  Tavily API Key
                </label>
                <input
                  id="settings-tavily-api-key"
                  type="password"
                  value={config.tavily_api_key ?? ''}
                  onChange={(e) =>
                    setConfig({ ...config, tavily_api_key: e.target.value })
                  }
                  placeholder="<API_KEY>"
                  className="w-full px-3 py-2 text-sm text-ink-primary bg-panel-recessed border border-panel-border rounded font-mono focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow"
                />
              </div>
            </div>

            {/* Model & Audio Settings */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1">
                <label
                  htmlFor="settings-llm-model"
                  className="block text-xs font-mono uppercase tracking-wider text-ink-secondary"
                >
                  LLM Model
                </label>
                <input
                  id="settings-llm-model"
                  type="text"
                  value={config.llm_model}
                  onChange={(e) =>
                    setConfig({ ...config, llm_model: e.target.value })
                  }
                  placeholder="deepseek-flash"
                  className="w-full px-3 py-2 text-sm text-ink-primary bg-panel-recessed border border-panel-border rounded font-mono focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow"
                />
              </div>

              <div className="space-y-1">
                <label
                  htmlFor="settings-fallback-model"
                  className="block text-xs font-mono uppercase tracking-wider text-ink-secondary"
                >
                  Fallback Model (Ollama)
                </label>
                <input
                  id="settings-fallback-model"
                  type="text"
                  value={config.fallback_model}
                  onChange={(e) =>
                    setConfig({ ...config, fallback_model: e.target.value })
                  }
                  placeholder="qwen2.5:3b"
                  className="w-full px-3 py-2 text-sm text-ink-primary bg-panel-recessed border border-panel-border rounded font-mono focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              <div className="space-y-1">
                <label
                  htmlFor="settings-temperature"
                  className="block text-xs font-mono uppercase tracking-wider text-ink-secondary"
                >
                  LLM Temperature ({config.llm_temperature})
                </label>
                <input
                  id="settings-temperature"
                  type="number"
                  step="0.05"
                  min="0"
                  max="2"
                  value={config.llm_temperature}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      llm_temperature: parseFloat(e.target.value) || 0,
                    })
                  }
                  className="w-full px-3 py-2 text-sm text-ink-primary bg-panel-recessed border border-panel-border rounded font-mono focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow"
                />
              </div>

              <div className="space-y-1">
                <label
                  htmlFor="settings-vad-silence"
                  className="block text-xs font-mono uppercase tracking-wider text-ink-secondary"
                >
                  VAD Silence Duration (ms)
                </label>
                <input
                  id="settings-vad-silence"
                  type="number"
                  step="50"
                  min="400"
                  max="1000"
                  value={config.vad_silence_duration_ms}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      vad_silence_duration_ms: parseInt(e.target.value, 10) || 600,
                    })
                  }
                  className="w-full px-3 py-2 text-sm text-ink-primary bg-panel-recessed border border-panel-border rounded font-mono focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow"
                />
              </div>
            </div>

            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={handleSaveConfig}
                className="px-4 py-2 text-xs font-mono uppercase tracking-wider font-semibold rounded bg-panel-700 hover:bg-panel-750 text-amber-glow border border-panel-border hover:border-amber-glow/40 transition-colors cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow"
              >
                Save Settings
              </button>
              {statusFeedback && (
                <div
                  role="status"
                  aria-live="polite"
                  className="text-xs font-mono text-emerald-400"
                >
                  {statusFeedback}
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'persona' && (
          <div className="space-y-4">
            {/* Persona Summary Badges */}
            <div className="flex flex-wrap items-center gap-2 p-2.5 rounded bg-panel-recessed border border-panel-border">
              <span className="text-xs font-mono font-semibold text-amber-glow">
                {character.name}
              </span>
              <span className="text-[11px] font-mono text-ink-muted">·</span>
              <span className="text-xs font-mono text-ink-secondary">
                {character.persona.archetype}
              </span>
              <span className="text-[11px] font-mono text-ink-muted">·</span>
              <span className="text-xs font-mono text-ink-secondary">
                Voice: {character.voice.voice_id} ({Math.round(character.voice.blend_weight * 100)}%) + {character.voice.blend_voice_id} ({Math.round((1 - character.voice.blend_weight) * 100)}%)
              </span>
            </div>

            <div className="space-y-1">
              <label
                htmlFor="persona-system-prompt"
                className="block text-xs font-mono uppercase tracking-wider text-ink-secondary"
              >
                Character System Prompt
              </label>
              <textarea
                id="persona-system-prompt"
                rows={7}
                value={character.system_prompt}
                onChange={(e) =>
                  setCharacter({ ...character, system_prompt: e.target.value })
                }
                className="w-full px-3 py-2 text-sm text-ink-primary bg-panel-recessed border border-panel-border rounded font-mono resize-y leading-relaxed focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow"
              />
            </div>

            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={handleSaveCharacter}
                className="px-4 py-2 text-xs font-mono uppercase tracking-wider font-semibold rounded bg-panel-700 hover:bg-panel-750 text-amber-glow border border-panel-border hover:border-amber-glow/40 transition-colors cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow"
              >
                Save Persona
              </button>
              {statusFeedback && (
                <div
                  role="status"
                  aria-live="polite"
                  className="text-xs font-mono text-emerald-400"
                >
                  {statusFeedback}
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'memory' && (
          <div className="space-y-4">
            <div className="space-y-1">
              <label
                htmlFor="memory-user-profile"
                className="block text-xs font-mono uppercase tracking-wider text-ink-secondary"
              >
                User Memory Profile (USER.md)
              </label>
              <textarea
                id="memory-user-profile"
                rows={4}
                value={userMemory}
                onChange={(e) => setUserMemory(e.target.value)}
                className="w-full px-3 py-2 text-sm text-ink-primary bg-panel-recessed border border-panel-border rounded font-mono resize-y leading-relaxed focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow"
              />
            </div>

            <div className="space-y-1">
              <label
                htmlFor="memory-system-profile"
                className="block text-xs font-mono uppercase tracking-wider text-ink-secondary"
              >
                System Memory Profile (MEMORY.md)
              </label>
              <textarea
                id="memory-system-profile"
                rows={4}
                value={systemMemory}
                onChange={(e) => setSystemMemory(e.target.value)}
                className="w-full px-3 py-2 text-sm text-ink-primary bg-panel-recessed border border-panel-border rounded font-mono resize-y leading-relaxed focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow"
              />
            </div>

            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={handleSaveMemory}
                className="px-4 py-2 text-xs font-mono uppercase tracking-wider font-semibold rounded bg-panel-700 hover:bg-panel-750 text-amber-glow border border-panel-border hover:border-amber-glow/40 transition-colors cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow"
              >
                Save Memory Files
              </button>
              {statusFeedback && (
                <div
                  role="status"
                  aria-live="polite"
                  className="text-xs font-mono text-emerald-400"
                >
                  {statusFeedback}
                </div>
              )}
            </div>
          </div>
        )}

        {activeTab === 'todos' && (
          <div className="space-y-4">
            {/* Add Task Input Form */}
            <form
              onSubmit={(e) => {
                e.preventDefault();
                handleAddTodo();
              }}
              className="flex gap-2"
            >
              <label htmlFor="new-todo-title" className="sr-only">
                New task title
              </label>
              <input
                id="new-todo-title"
                type="text"
                aria-label="New task title"
                placeholder="Add new task..."
                value={newTodoTitle}
                onChange={(e) => setNewTodoTitle(e.target.value)}
                className="flex-1 px-3 py-2 text-sm text-ink-primary bg-panel-recessed border border-panel-border rounded font-mono focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow placeholder:text-ink-muted/50"
              />
              <select
                aria-label="Task category"
                value={newTodoCategory}
                onChange={(e) => setNewTodoCategory(e.target.value)}
                className="px-2.5 py-2 text-xs font-mono text-ink-primary bg-panel-recessed border border-panel-border rounded focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow"
              >
                <option value="general">general</option>
                <option value="audio">audio</option>
                <option value="models">models</option>
                <option value="system">system</option>
              </select>
              <button
                type="submit"
                aria-label="Add task"
                className="px-4 py-2 text-xs font-mono uppercase tracking-wider font-semibold rounded bg-panel-700 hover:bg-panel-750 text-amber-glow border border-panel-border hover:border-amber-glow/40 transition-colors cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow shrink-0"
              >
                Add Task
              </button>
            </form>

            {/* Task List */}
            <ul
              role="list"
              aria-label="To-Dos List"
              className="space-y-2 max-h-60 overflow-y-auto pr-1"
            >
              {todos.map((todo) => {
                const isCompleted = todo.status === 'completed';
                return (
                  <li
                    key={todo.id}
                    role="listitem"
                    className="flex items-center justify-between gap-3 p-2.5 rounded bg-panel-recessed border border-panel-border/80"
                  >
                    <div className="flex items-center gap-2.5 min-w-0">
                      <button
                        type="button"
                        role="checkbox"
                        aria-checked={isCompleted ? 'true' : 'false'}
                        aria-label={`Mark task "${todo.title}" as ${
                          isCompleted ? 'incomplete' : 'completed'
                        }`}
                        onClick={() => handleToggleTodo(todo.id)}
                        className={cn(
                          'w-4 h-4 rounded border flex items-center justify-center cursor-pointer transition-colors focus:outline-none focus-visible:ring-1 focus-visible:ring-amber-glow shrink-0',
                          isCompleted
                            ? 'bg-amber-glow border-amber-glow text-chassis-950'
                            : 'border-panel-border bg-panel-800 hover:border-panel-700'
                        )}
                      >
                        {isCompleted && (
                          <svg
                            className="w-3 h-3 stroke-current stroke-[2.5]"
                            viewBox="0 0 24 24"
                            fill="none"
                            aria-hidden="true"
                          >
                            <polyline points="20 6 9 17 4 12" />
                          </svg>
                        )}
                      </button>
                      <div className="flex items-center gap-2 min-w-0">
                        <span
                          className={cn(
                            'text-xs font-mono truncate',
                            isCompleted
                              ? 'line-through text-ink-muted'
                              : 'text-ink-primary'
                          )}
                        >
                          {todo.title}
                        </span>
                        <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-panel-750 text-ink-secondary border border-panel-border/50 shrink-0">
                          {todo.category}
                        </span>
                      </div>
                    </div>

                    <button
                      type="button"
                      aria-label={`Delete task: ${todo.title}`}
                      onClick={() => handleDeleteTodo(todo.id)}
                      className="px-2 py-1 text-[11px] font-mono uppercase tracking-wider text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded transition-colors cursor-pointer focus:outline-none focus-visible:ring-1 focus-visible:ring-red-400 shrink-0"
                    >
                      Delete
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
};
