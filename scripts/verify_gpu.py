#!/usr/bin/env python3
"""
Project Nyx — Hardware Diagnostic & CUDA 12 Preflight Verifier
Target: Windows 11 x64 · NVIDIA GeForce RTX 3050 Laptop GPU (6GB VRAM)
Enforces:
  1. Python 3.12 runtime standard (INV 4)
  2. Zero-PyTorch package footprint (INV 2)
  3. Windows dynamic CUDA 12 DLL registration (INV 1)
  4. ONNX Runtime CUDAExecutionProvider registration
  5. NVML VRAM inspection (<= 2600 MB idle baseline)
"""

import importlib.util
import os
import site
import sys
from pathlib import Path


def register_cuda_dlls() -> list[str]:
    """Dynamically register NVIDIA pip wheel DLL paths into os.add_dll_directory and PATH."""
    registered = []
    site_dirs = site.getsitepackages()
    if hasattr(site, "getusersitepackages"):
        site_dirs.append(site.getusersitepackages())

    for s in site_dirs:
        nvidia_path = Path(s) / "nvidia"
        if nvidia_path.is_dir():
            for subpkg in nvidia_path.iterdir():
                if subpkg.is_dir():
                    for target_subdir in ("bin", "lib"):
                        candidate = subpkg / target_subdir
                        if candidate.is_dir():
                            dir_str = str(candidate.resolve())
                            registered.append(dir_str)
                            # Register with Python 3.8+ Windows DLL loader
                            if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
                                try:
                                    os.add_dll_directory(dir_str)
                                except OSError:
                                    pass
                            # Prepend to PATH for C++ runtime dlopen / LoadLibrary
                            if dir_str not in os.environ.get("PATH", ""):
                                os.environ["PATH"] = dir_str + os.pathsep + os.environ.get("PATH", "")

    return registered


def verify_python_version() -> None:
    """Assert Python 3.12 runtime standard (INV 4)."""
    major, minor = sys.version_info.major, sys.version_info.minor
    print(f"[Preflight] Python version detected: {major}.{minor}.{sys.version_info.micro}")
    if (major, minor) != (3, 12):
        raise RuntimeError(
            f"Python runtime standard violation (INV 4). Current: {major}.{minor}. "
            "Required: Python 3.12 (kokoro-onnx==0.6.1 strictly requires >=3.10,<3.14)."
        )
    print("  -> PASS: Python 3.12 runtime standard satisfied.")


def verify_zero_pytorch() -> None:
    """Assert zero PyTorch package footprint (INV 2)."""
    banned_modules = ["torch", "torchaudio", "torchvision"]
    for mod in banned_modules:
        spec = importlib.util.find_spec(mod)
        if spec is not None:
            raise RuntimeError(
                f"Invariant Violation (INV 2): '{mod}' found at {spec.origin}. "
                "Project Nyx mandates 0 MB PyTorch bloat in the environment."
            )
    print("  -> PASS: Zero PyTorch packages detected (torch, torchaudio, torchvision absent).")


def verify_onnxruntime_gpu() -> None:
    """Assert CUDAExecutionProvider is active and available in ONNX Runtime."""
    try:
        import onnxruntime as ort
    except ImportError as e:
        raise RuntimeError(f"onnxruntime-gpu is not installed: {e}") from e

    available_providers = ort.get_available_providers()
    print(f"[Preflight] Available ONNX Runtime execution providers: {available_providers}")
    if "CUDAExecutionProvider" not in available_providers:
        raise RuntimeError(
            "CRITICAL: CUDAExecutionProvider is NOT available in ONNX Runtime! "
            "Ensure onnxruntime-gpu==1.26.0 is installed and CUDA 12 DLLs are linked."
        )
    print("  -> PASS: CUDAExecutionProvider verified in ONNX Runtime.")


def verify_vram_and_gpu(max_vram: float = 2600.0) -> None:
    """Query NVML for GPU specifications and assert VRAM consumption budget."""
    try:
        import pynvml
    except ImportError as e:
        raise RuntimeError(f"nvidia-ml-py is not installed: {e}") from e

    pynvml.nvmlInit()
    try:
        device_count = pynvml.nvmlDeviceGetCount()
        if device_count == 0:
            raise RuntimeError("NVML reported 0 NVIDIA GPU devices.")

        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        gpu_name = pynvml.nvmlDeviceGetName(handle)
        if isinstance(gpu_name, bytes):
            gpu_name = gpu_name.decode("utf-8")

        mem_info = pynvml.nvmlDeviceGetMemoryInfo(handle)
        total_mb = mem_info.total / (1024 * 1024)
        used_mb = mem_info.used / (1024 * 1024)
        free_mb = mem_info.free / (1024 * 1024)

        print(f"[Preflight] Primary GPU: {gpu_name}")
        print(f"[Preflight] VRAM Total: {total_mb:.1f} MB | Used: {used_mb:.1f} MB | Free: {free_mb:.1f} MB")

        # Invariant: Idle VRAM Baseline Budget <= max_vram MB
        if used_mb > max_vram:
            raise RuntimeError(
                f"VRAM usage ({used_mb:.1f} MB) exceeds maximum budget ({max_vram:.1f} MB). "
                f"Ensure heavy external GPU applications are closed."
            )
        print(f"  -> PASS: VRAM usage ({used_mb:.1f} MB) within baseline budget (<= {max_vram:.1f} MB).")
    finally:
        pynvml.nvmlShutdown()


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Project Nyx Preflight Hardware & CUDA 12 Verifier")
    parser.add_argument("--max-vram", type=float, default=2600.0, help="Maximum allowed idle VRAM in MB")
    args = parser.parse_args()

    print("=" * 60)
    print("  Project Nyx — Preflight Hardware & CUDA 12 Verifier   ")
    print("=" * 60)

    try:
        # 1. Python version assert
        verify_python_version()

        # 2. Zero-PyTorch assert
        verify_zero_pytorch()

        # 3. DLL registration
        dll_dirs = register_cuda_dlls()
        print(f"[Preflight] Registered {len(dll_dirs)} CUDA 12 pip wheel DLL directories.")

        # 4. ONNX Runtime CUDA provider check
        verify_onnxruntime_gpu()

        # 5. NVML GPU and VRAM check
        verify_vram_and_gpu(max_vram=args.max_vram)

        print("\nAll Preflight Diagnostics PASSED successfully!")
        return 0
    except Exception as exc:
        print(f"\n[FAIL] Preflight Diagnostic Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
