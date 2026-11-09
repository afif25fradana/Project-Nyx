# Project Nyx: Technical Architecture & System Specifications

System topology, neural speech pipeline, concurrency model, latency budgets, interface tiers, and local security policies for Project Nyx.

---

## 1. Monorepo Directory Hierarchy

```
Project-Nyx/
├── backend/                  # Core speech runtime, turn manager, persistence, and API stubs
│   ├── app/
│   │   ├── api/              # REST endpoints and WebSocket server (scaffolding stubs)
│   │   ├── audio/            # Silero VAD, faster-whisper STT, Kokoro TTS, WASAPI playback
│   │   ├── core/             # 7-State FSM, TurnManager, StreamParser, LLM client
│   │   ├── memory/           # MarkdownStore (USER/MEMORY) and SQLite persistence
│   │   ├── tools/            # Web search tools and SQLite task tools
│   │   ├── utils/            # Windows CUDA 12 dynamic DLL loader
│   │   └── config.py         # App settings and atomic .env configuration
│   ├── config/               # character.yaml and settings.yaml
│   ├── data/                 # Local SQLite databases and Markdown user memory
│   ├── tests/                # Pytest unit, audio, and integration test suite
│   ├── requirements.txt      # Production dependencies pinned for CUDA 12
│   └── constraints.txt       # Hard namespace blocks against PyTorch and CPU ONNX
├── desktop_pet/              # Tier 1 PySide6 transparent overlay widget (scaffolding stub)
│   └── assets/               # Pre-scaled character sprites for CPU QPainter
├── web_hub/                  # Tier 2 React 19 + Vite 6 + Tailwind CSS v4 web hub prototype (mockup with offline fallbacks)
│   ├── src/
│   │   ├── components/
│   │   │   ├── AvatarStage/        # DoubleBufferVideo WebM avatar preview
│   │   │   ├── ConversationFeed/   # Real-time chat stream and tool status badges
│   │   │   ├── ControlDeck/        # Microphone toggle switches and status indicators
│   │   │   ├── PipelineTerminal/   # Latency waterfall telemetry readout
│   │   │   ├── SettingsDeck/       # Settings console (4 accessible ARIA tabs)
│   │   │   └── common/             # Handcrafted SVG icons and ErrorBoundary
│   │   ├── context/                # NyxContext application state provider
│   │   ├── services/               # REST API and WebSocket client services
│   │   └── tests/                  # Vitest unit and vitest-axe WCAG accessibility tests
│   └── public/avatar/        # Pre-rendered WebM character video loops
├── scripts/                  # Bootstrap setup and GPU verification scripts
└── run.py                    # Unified CLI launcher coordinating service lifecycles
```

---

## 2. Speech Pipeline Architecture

The audio pipeline runs locally on Windows 11 without a PyTorch runtime, using ONNX Runtime GPU with dynamic CUDA 12 wheel linkage and CTranslate2.

### Voice Activity Detection (VAD)
- **Engine**: Pure ONNX Silero VAD (`silero_vad.onnx`) running in 512-sample frames (32ms at 16kHz).
- **Execution**: Evaluated on CPU or CUDA via ONNX Runtime without loading PyTorch or TorchAudio.
- **Endpointing**: Silence duration threshold defaults to 600ms (`vad_silence_duration_ms: 600`) to mark natural turn boundaries without clipping trailing syllables.

### Speech-to-Text (STT)
- **Engine**: `faster-whisper` (`large-v3-turbo`) running on CTranslate2.
- **Quantization**: `int8_float16` precision mapped to NVIDIA Ampere Tensor Cores.
- **Throughput**: Processes typical user utterances (2 to 5 seconds of audio) in approximately 350 to 650 ms on an RTX 3050 Laptop GPU.

### Text-to-Speech (TTS)
- **Engine**: Pure ONNX Kokoro TTS (`kokoro-v1.0.onnx`) with Misaki G2P phonemization.
- **Voice Blending**: Default voice persona blends two models: 65% `af_nicole` (breathy texture) and 35% `am_onyx` (grounded resonance), producing a raspy, lower-register tone. Weights are normalized and mixed directly in NumPy at 0 MB VRAM cost.
- **Synthesis Guardrails**:
  - Sentences are segmented into clause chunks (<= 280 characters) by `StreamParser` to prevent Kokoro ONNX runtime crashes on inputs exceeding 510 phonemes.
  - Runtime dynamically inspects session inputs and casts the speed tensor to the target ONNX export dtype (`int64`, `int32`, or `float32`).

### Acoustic Echo Shielding & Audio I/O
- **Audio Host API**: PortAudio WASAPI Shared Mode via `sounddevice`.
- **In-Callback FIFO Queue**: Ingestion callbacks drop the oldest chunk via `get_nowait()` before `put_nowait()` if downstream processing lags, which prioritizes live speech over stale buffers.
- **Acoustic Cooldown**: A mandatory 250ms quiet window (`time.perf_counter` monotonic loop) runs immediately after playback finishes, followed by an explicit `vad_engine.reset_state()` before the microphone gate reopens. This prevents Nyx from transcribing her own voice output.

---

## 3. Turn Management & Latency SLA Budget

### 7-State Finite State Machine (FSM)
Voice turns are governed by deterministic state transitions in `backend/app/core/state_machine.py`:
- `IDLE`: Microphone gate open; listening for incoming speech via VAD.
- `LISTENING`: Speech detected; accumulating 16kHz audio frames.
- `TRANSCRIBING`: Silence endpoint reached; microphone gate closed; Whisper transcribing.
- `THINKING`: Transcript ready; prompt submitted to LLM client under `turn_lock`.
- `TOOL_RUNNING`: LLM emitted a structured tool call; executing tool and appending result.
- `SPEAKING`: First clause synthesized; audio streaming through WASAPI playback buffer.
- `ERROR`: Recoverable failure encountered; dispatched to error handlers and returned to `IDLE`.

### Concurrency & Interruption Handling
- **Turn Mutex**: `TurnManager.turn_lock` ensures single-turn execution to prevent race conditions from overlapping audio triggers.
- **Monotonic Generation Counter**: Every turn and barge-in interrupt increments a monotonic counter (`generation_counter`). Playback workers verify their generation tag before writing PCM buffers and discard stale audio from interrupted turns.
- **Barge-in Interrupt**: When the user presses the interrupt button or speaks during assistant playback, `turn_manager.interrupt()` cancels active asyncio tasks, silences PortAudio output, runs the 250ms cooldown, resets VAD state, and returns the FSM to `IDLE`.

### StreamParser Clause Chunking
`StreamParser` monitors token deltas from DeepSeek-Flash (with thinking disabled) or local Ollama fallback. It emits text chunks at punctuation boundaries (40 to 60 characters for the initial chunk, <= 280 characters for subsequent chunks) and queues audio synthesis while remaining tokens generate.

### Stage-by-Stage Latency Waterfall

Target latency budget for typical turns: p50 < 2.0s, p95 < 3.5s.

```
[User stops speaking]
       │
       ▼ 450ms - 600ms
[Silero VAD silence endpointing]
       │
       ▼ 350ms - 650ms
[faster-whisper turbo int8_float16 transcription]
       │
       ▼ 400ms - 800ms
[DeepSeek-Flash streaming TTFT (thinking disabled)]
       │
       ▼ 150ms - 250ms
[StreamParser clause chunk 1 (40-60 characters)]
       │
       ▼ 120ms - 220ms
[Kokoro ONNX initial clause synthesis]
       │
       ▼ 40ms - 80ms
[WASAPI 24kHz PCM playback buffer feed]
       │
       ▼
[First audio heard by user] -> Estimated p50 TTFA: ~1.5s - 1.9s
```

---

## 4. Interface Tiers & Implementation Status

Project Nyx defines a two-tier presentation architecture. The core backend audio pipeline, FSM turn manager, and local storage layers are fully implemented and verified via unit tests; the presentation interfaces and communication bridge are currently prototypes and scaffolding stubs:

### Tier 1: Floating Desktop Pet (PySide6) (Scaffolding Stub)

> [!NOTE]
> The PySide6 desktop overlay is currently a scaffolding stub (`desktop_pet/`) under active development. The underlying sprite rendering loop and WebSocket bridge are planned specifications being wired up to the backend.

- **Overlay Window**: Planned borderless, translucent desktop overlay (`Qt.Tool`, `WA_TranslucentBackground`) with click-through toggle.
- **Rendering Architecture**: Pre-scaled sprite animations (idle breathing, eye blinks, mouth flaps) drawn with CPU `QPainter`, targeting 0 MB discrete GPU memory.
- **IPC Protocol**: Designed to connect to the local backend WebSocket (`ws://127.0.0.1:8765/ws/avatar`) to synchronize mouth flaps with audio playback and switch emotional poses.

### Tier 2: Web Hub (React 19 + Vite 6 + Tailwind CSS v4 Prototype)

> [!NOTE]
> The Web Hub is an interactive frontend mockup and layout prototype. While the live backend loopback WebSocket bridge is being wired up, the UI operates standalone using built-in offline mock data (`web_hub/src/services/api.ts`) to test layout, telemetry readouts, and controls.

- **Amber Visual Theme**: Exploratory amber styling using Tailwind CSS v4 `@theme` tokens and lightweight CSS scanline pseudo-elements at 0 MB GPU VRAM overhead.
- **DoubleBufferVideo Avatar (`AvatarStage.tsx`, `DoubleBufferVideo.tsx`)**:
  - Two pre-mounted `<video>` elements crossfade with hardware opacity transitions.
  - Video synchronization is confirmed via `requestVideoFrameCallback` (`rVFC`) with an 80ms fallback watchdog to prevent black flashes during loop transitions.
  - Includes a 10-second random idle pool (`idle.webm`, `idle_smoking.webm`, `idle-bed.webm`) and conversational reaction loops (`talk.webm`, `listening.webm`, `thinking.webm`, `happy.webm`, `sad.webm`, `muted.webm`).
- **Telemetry Readout (`PipelineTerminal.tsx`)**: Displays stage-by-stage timings (VAD, STT, LLM TTFT, TTS chunk, and total TTFA) against the sub-2.0s SLA target.
- **Controls & Settings (`ControlDeck.tsx`, `SettingsDeck.tsx`)**: Toggle controls and four accessible ARIA tabs (`Config`, `Persona`, `Memory`, `To-Dos`) with offline mock fallbacks for standalone preview.
- **Accessibility**: Verified with automated `vitest-axe` test suites across all controls and navigation.

---

## 5. Security & Local Isolation

The system operates under a strict local trust boundary:

> [!NOTE]
> The policies below define architectural boundaries and target communication contracts. Local file isolation and startup session token generation are implemented in backend modules, while HTTP/WebSocket Origin validation and cookie handshakes are being integrated as part of the loopback API bridge.

1. **Loopback Binding**: The backend binds exclusively to `127.0.0.1:8765`. It never listens on `0.0.0.0` or local network adapters.
2. **Origin Validation**: Strict allowlist validation on incoming HTTP and WebSocket `Origin` headers (`127.0.0.1:8765`, `localhost:8765`, `localhost:5173`, `[::1]:8765`, `[::1]:5173`) prevents Cross-Site WebSocket Hijacking (CSWSH). Desktop clients without Origin headers authenticate via bootstrap token.
3. **Session Authentication**: A high-entropy session token is generated at startup in `data/.auth_token`. Browser clients obtain an `HttpOnly` cookie (`nyx_token`) during the initial handshake, while native desktop clients supply `X-Nyx-Token`. Mutating REST endpoints require authentication.
4. **Data Isolation**: Conversation logs (`sessions.db`), task records (`todos.db`), and user memory (`USER.md`, `MEMORY.md`) remain on local disk in `backend/data/`.
5. **Sequenced Teardown**: Shutdown handlers halt PortAudio C-threads, cancel pending asyncio tasks within a 3.0s shielded window, shut down thread pools, and flush SQLite WAL databases to prevent Windows access violations (`0xC0000005`).

---

## 6. Technical Invariants & Excluded Components

To preserve system responsiveness on consumer hardware, Project Nyx excludes:

- **Zero PyTorch Runtime**: Excludes `torch`, `torchaudio`, and `torchvision`, saving over 2.5 GB of disk and runtime memory.
- **Zero Cloud Audio Exfiltration**: Voice activity detection, speech transcription, and audio synthesis run entirely on local hardware; microphone audio is never transmitted over the network.
- **Zero Heavy 3D WebGL Contexts**: The UI avoids WebGL and Three.js runtimes (which consume 300MB to 1GB+ VRAM), preserving GPU memory for speech models.
