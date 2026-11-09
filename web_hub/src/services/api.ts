/**
 * REST API client helpers for Project Nyx Command Deck.
 * Strictly aligned with backend/config/settings.yaml, backend/config/character.yaml,
 * MarkdownStore (USER.md / MEMORY.md), TodoStore, and PRD.md §6.5 specifications.
 * Includes resilient offline mock fallbacks for hermetic testing and disconnected execution.
 */

export interface SettingsConfig {
  vad_silence_duration_ms: number;
  vad_threshold: number;
  llm_model: string;
  llm_temperature: number;
  fallback_model: string;
  deepseek_api_key?: string;
  tavily_api_key?: string;
}

export interface CharacterConfig {
  name: string;
  persona: {
    archetype: string;
    tone: string;
    language_policy: {
      bilingual_comprehension: boolean;
      spoken_language: string;
      indonesian_acknowledgments: string[];
    };
  };
  voice: {
    model: string;
    voice_id: string;
    blend_enabled: boolean;
    blend_voice_id: string;
    blend_weight: number;
    speed: number;
    pitch: number;
  };
  default_emotion: string;
  permitted_emotions: string[];
  system_prompt: string;
}

export interface MemoryFile {
  name: 'USER.md' | 'MEMORY.md';
  content: string;
  last_modified?: number;
}

export interface TodoItem {
  id: number;
  title: string;
  category: string;
  status: 'pending' | 'completed';
  completed?: number;
  created_at?: number | string;
  completed_at?: number | string | null;
}

export const DEFAULT_SETTINGS: SettingsConfig = {
  vad_silence_duration_ms: 600,
  vad_threshold: 0.5,
  llm_model: 'deepseek-flash',
  llm_temperature: 0.7,
  fallback_model: 'qwen2.5:3b',
  deepseek_api_key: '<API_KEY>',
  tavily_api_key: '<API_KEY>',
};

export const DEFAULT_CHARACTER: CharacterConfig = {
  name: 'Nyx',
  persona: {
    archetype: 'Tomboyish girl',
    tone: 'Reflective, witty, candid, low-energy warm',
    language_policy: {
      bilingual_comprehension: true,
      spoken_language: 'English',
      indonesian_acknowledgments: ['siap', 'oke', 'santai', 'ngerti'],
    },
  },
  voice: {
    model: 'kokoro-v1.0.onnx',
    voice_id: 'af_nicole',
    blend_enabled: true,
    blend_voice_id: 'am_onyx',
    blend_weight: 0.65,
    speed: 1.0,
    pitch: 1.0,
  },
  default_emotion: 'neutral',
  permitted_emotions: ['neutral', 'happy', 'sad', 'surprised', 'thinking'],
  system_prompt: `You are Nyx, a candid, reflective, and witty tomboyish girl.
You speak in natural, succinct English. You effortlessly understand mixed Indonesian and English.
Always anchor an emotion tag at the very start of your response, e.g. <emotion>happy</emotion>.
Never use markdown formatting, code blocks, or bullet points in voice conversation turns.`,
};

export const DEFAULT_USER_MEMORY: MemoryFile = {
  name: 'USER.md',
  content: `# User Profile
- Name: Operator Fradana
- Timezone: UTC+7
- Language: English & Indonesian
- Preferences: Concise replies, technical clarity, terminal-first`,
};

export const DEFAULT_SYSTEM_MEMORY: MemoryFile = {
  name: 'MEMORY.md',
  content: `# Agent Memory
- Role: Project Nyx Local Voice AI
- Hardware: RTX 3050 Laptop GPU (6GB VRAM, CUDA 12)
- Pipeline: Zero-PyTorch Silero VAD, Whisper Turbo, Kokoro TTS
- Web Hub: Tier 2 Double-Buffered CRT Console`,
};

export const DEFAULT_TODOS: TodoItem[] = [
  {
    id: 1,
    title: 'Calibrate VAD sensitivity & noise gate',
    category: 'audio',
    status: 'completed',
    completed: 1,
    created_at: '2026-11-07T10:00:00.000Z',
  },
  {
    id: 2,
    title: 'Profile CTranslate2 Whisper int8 execution latency',
    category: 'models',
    status: 'pending',
    completed: 0,
    created_at: '2026-11-07T11:00:00.000Z',
  },
  {
    id: 3,
    title: 'Tune Kokoro ONNX audio playback streaming buffer',
    category: 'audio',
    status: 'pending',
    completed: 0,
    created_at: '2026-11-07T12:00:00.000Z',
  },
];

// In-memory state for offline mock fallback
let mockSettings: SettingsConfig = { ...DEFAULT_SETTINGS };
let mockCharacter: CharacterConfig = JSON.parse(JSON.stringify(DEFAULT_CHARACTER));
let mockUserMemory: MemoryFile = { ...DEFAULT_USER_MEMORY };
let mockSystemMemory: MemoryFile = { ...DEFAULT_SYSTEM_MEMORY };
let mockTodos: TodoItem[] = JSON.parse(JSON.stringify(DEFAULT_TODOS));

export function resetMockApiState(): void {
  mockSettings = { ...DEFAULT_SETTINGS };
  mockCharacter = JSON.parse(JSON.stringify(DEFAULT_CHARACTER));
  mockUserMemory = { ...DEFAULT_USER_MEMORY };
  mockSystemMemory = { ...DEFAULT_SYSTEM_MEMORY };
  mockTodos = JSON.parse(JSON.stringify(DEFAULT_TODOS));
}

// ==========================================
// 1. Settings Endpoints (PRD §6.5: GET / PATCH)
// ==========================================

export async function fetchSettings(): Promise<SettingsConfig> {
  try {
    const res = await fetch('/api/settings');
    if (!res.ok) return { ...mockSettings };
    return (await res.json()) as SettingsConfig;
  } catch {
    return { ...mockSettings };
  }
}

export async function saveSettings(
  patch: Partial<SettingsConfig>
): Promise<{ success: boolean; data: SettingsConfig }> {
  try {
    const res = await fetch('/api/settings', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
    if (!res.ok) {
      mockSettings = { ...mockSettings, ...patch };
      return { success: true, data: { ...mockSettings } };
    }
    const data = (await res.json()) as SettingsConfig;
    return { success: true, data };
  } catch {
    mockSettings = { ...mockSettings, ...patch };
    return { success: true, data: { ...mockSettings } };
  }
}

// ==========================================
// 2. Character Endpoints (PRD §6.5: GET / PATCH)
// ==========================================

export async function fetchCharacter(): Promise<CharacterConfig> {
  try {
    const res = await fetch('/api/character');
    if (!res.ok) return JSON.parse(JSON.stringify(mockCharacter));
    return (await res.json()) as CharacterConfig;
  } catch {
    return JSON.parse(JSON.stringify(mockCharacter));
  }
}

export async function saveCharacter(
  patch: Partial<CharacterConfig>
): Promise<{ success: boolean; data: CharacterConfig }> {
  try {
    const res = await fetch('/api/character', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(patch),
    });
    if (!res.ok) {
      mockCharacter = { ...mockCharacter, ...patch };
      return { success: true, data: JSON.parse(JSON.stringify(mockCharacter)) };
    }
    const data = (await res.json()) as CharacterConfig;
    return { success: true, data };
  } catch {
    mockCharacter = { ...mockCharacter, ...patch };
    return { success: true, data: JSON.parse(JSON.stringify(mockCharacter)) };
  }
}

// ==========================================
// 3. Memory Endpoints (PRD §6.5: GET / PUT /api/memory/{name})
// ==========================================

export async function fetchMemoryFile(
  name: 'USER.md' | 'MEMORY.md'
): Promise<MemoryFile> {
  try {
    const res = await fetch(`/api/memory/${encodeURIComponent(name)}`);
    if (!res.ok) {
      return name === 'USER.md' ? { ...mockUserMemory } : { ...mockSystemMemory };
    }
    return (await res.json()) as MemoryFile;
  } catch {
    return name === 'USER.md' ? { ...mockUserMemory } : { ...mockSystemMemory };
  }
}

export async function saveMemoryFile(
  name: 'USER.md' | 'MEMORY.md',
  content: string
): Promise<{ status: string; name: string }> {
  try {
    const res = await fetch(`/api/memory/${encodeURIComponent(name)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content }),
    });
    if (!res.ok) {
      if (name === 'USER.md') mockUserMemory.content = content;
      else mockSystemMemory.content = content;
      return { status: 'saved', name };
    }
    return (await res.json()) as { status: string; name: string };
  } catch {
    if (name === 'USER.md') mockUserMemory.content = content;
    else mockSystemMemory.content = content;
    return { status: 'saved', name };
  }
}

// ==========================================
// 4. To-Do Endpoints (PRD §6.5 & Invariant #11: strict integer IDs)
// ==========================================

export async function fetchTodos(
  status: 'pending' | 'completed' | 'all' = 'all'
): Promise<TodoItem[]> {
  try {
    const res = await fetch(`/api/todos?status=${encodeURIComponent(status)}`);
    if (!res.ok) {
      return status === 'all'
        ? [...mockTodos]
        : mockTodos.filter((t) => t.status === status);
    }
    return (await res.json()) as TodoItem[];
  } catch {
    return status === 'all'
      ? [...mockTodos]
      : mockTodos.filter((t) => t.status === status);
  }
}

export async function createTodo(
  title: string,
  category: string = 'general'
): Promise<TodoItem> {
  try {
    const res = await fetch('/api/todos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title, category }),
    });
    if (!res.ok) {
      const nextId = mockTodos.length > 0 ? Math.max(...mockTodos.map((t) => t.id)) + 1 : 1;
      const item: TodoItem = {
        id: nextId,
        title,
        category,
        status: 'pending',
        completed: 0,
        created_at: new Date().toISOString(),
      };
      mockTodos = [...mockTodos, item];
      return item;
    }
    return (await res.json()) as TodoItem;
  } catch {
    const nextId = mockTodos.length > 0 ? Math.max(...mockTodos.map((t) => t.id)) + 1 : 1;
    const item: TodoItem = {
      id: nextId,
      title,
      category,
      status: 'pending',
      completed: 0,
      created_at: new Date().toISOString(),
    };
    mockTodos = [...mockTodos, item];
    return item;
  }
}

export async function updateTodoStatus(
  id: number,
  status: 'pending' | 'completed'
): Promise<TodoItem> {
  try {
    const res = await fetch(`/api/todos/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    if (!res.ok) {
      mockTodos = mockTodos.map((t) =>
        t.id === id ? { ...t, status, completed: status === 'completed' ? 1 : 0 } : t
      );
      const updated = mockTodos.find((t) => t.id === id);
      if (!updated) throw new Error(`Todo ${id} not found`);
      return updated;
    }
    return (await res.json()) as TodoItem;
  } catch {
    mockTodos = mockTodos.map((t) =>
      t.id === id ? { ...t, status, completed: status === 'completed' ? 1 : 0 } : t
    );
    const updated = mockTodos.find((t) => t.id === id);
    if (!updated) throw new Error(`Todo ${id} not found`);
    return updated;
  }
}

export async function deleteTodo(
  id: number
): Promise<{ deleted: boolean; id: number }> {
  try {
    const res = await fetch(`/api/todos/${id}`, {
      method: 'DELETE',
    });
    if (!res.ok) {
      mockTodos = mockTodos.filter((t) => t.id !== id);
      return { deleted: true, id };
    }
    return (await res.json()) as { deleted: boolean; id: number };
  } catch {
    mockTodos = mockTodos.filter((t) => t.id !== id);
    return { deleted: true, id };
  }
}
