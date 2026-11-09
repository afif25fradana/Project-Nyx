# Project Nyx

<p align="center">
  <img src="assets/preview/idle-bed.gif" alt="Project Nyx Web Hub Preview" width="600" />
  <br />
  <em>Project Nyx Web Hub: Double-buffered WebM video loop prototype</em>
</p>

Project Nyx is a personal side project and experimental sandbox for exploring local, low-latency voice pipelines and lightweight web interfaces on Windows 11. It investigates how much conversational capability can run within a 2.6 GB VRAM ceiling on an entry-level laptop GPU (NVIDIA RTX 3050 6GB) without loading gigabytes of PyTorch dependencies.

---

## Why It Exists

Built between larger projects to test practical tools and ideas:

1. **Lightweight Neural Voice Pipeline**: Testing whether voice activity detection (pure ONNX Silero VAD), speech transcription (faster-whisper on CTranslate2 with `int8_float16`), and speech synthesis (Kokoro ONNX TTS with CPU Misaki G2P) can run with low latency under 2.6 GB VRAM on a 6 GB laptop GPU, completely bypassing 4 to 6 GB of PyTorch runtime overhead.
2. **Lean Retro UI**: Experimenting with an amber CRT-styled React 19 + Tailwind CSS v4 dashboard that uses double-buffered WebM video loops (`requestVideoFrameCallback`) instead of heavy 3D WebGL or Three.js canvases that eat 300 MB to 1 GB+ of GPU memory.

### Current Status & Scaffolding
- **Core Backend Audio & Logic**: The audio ingestion, Silero VAD, faster-whisper STT, Kokoro TTS voice blending, 7-state turn manager FSM, and local memory stores (`backend/app/`) are fully implemented and unit-tested.
- **Web Hub Prototype**: The React 19 interface (`web_hub/`) is an interactive frontend mockup. When the backend server is not running, it falls back to built-in offline mock data (`web_hub/src/services/api.ts`) for testing layouts, telemetry waterfalls, and controls.
- **Scaffolding Stubs**: The FastAPI loopback WebSocket server (`backend/app/api/`, `run.py`) and the PySide6 desktop overlay (`desktop_pet/`) are scaffolding stubs currently being wired up to the core engine.

### Test Persona
For testing prompt formatting and voice synthesis, the default configuration (`backend/config/character.yaml`) sets up a test persona named Nyx: a laid-back, dry-witted tomboy. Her voice blends two Kokoro ONNX vectors in NumPy (65% `af_nicole` + 35% `am_onyx`) to achieve a raspy, lower-register tone with 0 MB extra VRAM. She understands mixed Indonesian and English code-switching with colloquial anchors (`siap`, `santai`, `ngerti`). The persona is fully modular and editable in `character.yaml`.

---

## Requirements
- **OS & Hardware**: Windows 10/11 x64, NVIDIA GPU with 6 GB VRAM (RTX 3050 baseline) and CUDA 12.x driver, 16 GB system RAM.
- **Runtimes**: Python 3.12 64-bit, Node.js >= 20.

---

## Quick Start

### 1. Bootstrap Python Environment
```powershell
git clone https://github.com/afif25fradana/Project-Nyx.git
cd Project-Nyx
powershell -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
```

### 2. Verify Hardware & CUDA Environment
Verify Python 3.12, CUDA 12 DLL linkage, ONNX Runtime `CUDAExecutionProvider`, and baseline VRAM:
```powershell
.\.venv\Scripts\python.exe scripts\verify_gpu.py
```

### 3. Run Test Suites
```powershell
# Python backend test suite (FSM, VAD, STT, TTS voice blend, session memory)
.\.venv\Scripts\pytest.exe -v

# Web Hub test suite (Vitest unit, component, and WCAG accessibility tests)
npm --prefix web_hub test
```

### 4. Preview Web Hub Prototype
```powershell
npm --prefix web_hub install
npm --prefix web_hub run dev
```
Open `http://localhost:5173` to explore the frontend prototype using offline mock telemetry and controls.

---

## Technical Specifications

Detailed architecture diagrams, latency waterfalls, FSM transitions, and local security policies are documented in **[`TECHNICAL.md`](TECHNICAL.md)**.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
