"""
Project Nyx — Windows CUDA 12 Dynamic DLL Loader (Invariant #1)
Dynamically discovers and registers NVIDIA pip wheel DLL paths
via os.add_dll_directory() and PATH prepending.
"""

import os
import site
import sys
from pathlib import Path


def load_cuda_dlls() -> list[str]:
    """
    Discover and register CUDA 12 DLLs from bundled pip wheels:
      - nvidia-cublas-cu12
      - nvidia-cudnn-cu12
      - nvidia-cuda-runtime-cu12
      - nvidia-cufft-cu12
    Must be invoked before importing C-extensions or ONNX Runtime / CTranslate2.
    """
    registered = []
    site_dirs = site.getsitepackages()
    if hasattr(site, "getusersitepackages"):
        site_dirs.append(site.getusersitepackages())
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        site_dirs.append(meipass)

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
                            if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
                                try:
                                    os.add_dll_directory(dir_str)
                                except OSError:
                                    pass
                            if dir_str not in os.environ.get("PATH", ""):
                                os.environ["PATH"] = dir_str + os.pathsep + os.environ.get("PATH", "")

    return registered
