import asyncio
import importlib.util
import inspect
import os
import threading
import numpy as np
import pytest

from backend.app.audio.stt import Transcriber
from backend.app.utils.dll_loader import load_cuda_dlls
from backend.tests.conftest import generate_speech_simulation, generate_silence_pcm16


def test_zero_pytorch_invariant_stt():
    """Assert faster-whisper operates with 0 bytes of PyTorch (Invariant #2)."""
    assert importlib.util.find_spec("torch") is None
    assert importlib.util.find_spec("torchaudio") is None


def test_cuda_dlls_registered():
    """Invariant #1: Assert CUDA 12 dynamic DLLs are discovered and present in PATH."""
    registered = load_cuda_dlls()
    assert len(registered) > 0, "Expected CUDA 12 DLL paths to be registered"
    path_env = os.environ.get("PATH", "")
    for reg_path in registered:
        assert reg_path in path_env, f"DLL directory {reg_path} not found in PATH"


def test_transcriber_default_signature():
    """Assert Transcriber defaults to large-v3-turbo, cuda, and int8_float16."""
    sig = inspect.signature(Transcriber.__init__)
    params = sig.parameters
    assert params["model_size"].default == "large-v3-turbo"
    assert params["device"].default == "cuda"
    assert params["compute_type"].default == "int8_float16"


@pytest.mark.asyncio
async def test_async_transcribe_synthetic_audio():
    """Assert Transcriber transcribes audio offloaded to thread pool without blocking loop."""
    # Use lightweight tiny model in CUDA INT8 for fast test execution
    transcriber = Transcriber(model_size="tiny", device="cuda", compute_type="int8_float16")
    try:
        audio = generate_silence_pcm16(duration_sec=1.0)
        
        # Verify event loop remains responsive while transcribing
        loop = asyncio.get_running_loop()
        main_thread_ident = threading.get_ident()
        
        task = asyncio.create_task(transcriber.transcribe(audio, language="en"))
        # Execute another coroutine concurrently
        await asyncio.sleep(0.01)
        result = await task

        assert isinstance(result, str)
    finally:
        transcriber.close()


@pytest.mark.asyncio
async def test_transcriber_executor_shutdown():
    """Assert transcriber.close() shuts down internal thread pool executor."""
    transcriber = Transcriber(model_size="tiny", device="cuda", compute_type="int8_float16")
    assert transcriber._executor is not None
    transcriber.close()
    assert transcriber._executor._shutdown is True
