# Project Nyx — Automated Bootstrap Script for Windows 11
# Deterministic 3-step setup enforcing Python 3.12, CUDA 12 wheels, and Zero-PyTorch
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$rootDir = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $rootDir

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Project Nyx Bootstrap: Windows 11 x64 Setup Pipeline " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan

# Step 0: Verify Python 3.12 x64 & Initialize .venv
Write-Host "`n[Step 0/3] Verifying Python 3.12 x64 environment..." -ForegroundColor Yellow

# Try Python Launcher for 3.12 first to avoid picking up incompatible Python 3.14+
$pythonCmd = "python"
$pythonArgs = @()

if (Get-Command "py" -ErrorAction SilentlyContinue) {
    $has312 = & py --list 2>&1 | Select-String "3.12"
    if ($has312) {
        $pythonCmd = "py"
        $pythonArgs = @("-3.12")
    }
}

try {
    $pyVersionRaw = & $pythonCmd @pythonArgs -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
    $is64Bit = & $pythonCmd @pythonArgs -c "import sys; print(sys.maxsize > 2**32)"
} catch {
    Write-Error "Python is not found in PATH or py launcher. Please install Python 3.12 x64."
    exit 1
}

Write-Host "Detected Python executable: $pythonCmd $pythonArgs ($pyVersionRaw, 64-bit: $is64Bit)" -ForegroundColor Gray
$pyMajorMinor = & $pythonCmd @pythonArgs -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($pyMajorMinor -ne "3.12") {
    Write-Error "CRITICAL COMPATIBILITY VIOLATION (INV 4):`nDetected Python $pyVersionRaw. kokoro-onnx==0.6.1 strictly requires Python >=3.10,<3.14 (fails on Python 3.14+).`nPlease install Python 3.12 x64 via: winget install -e --id Python.Python.3.12"
    exit 1
}

$venvPath = Join-Path $rootDir ".venv"
$venvPython = Join-Path $venvPath "Scripts\python.exe"
$venvPip = Join-Path $venvPath "Scripts\pip.exe"

if (-not (Test-Path $venvPath)) {
    Write-Host "Creating virtual environment at $venvPath using Python 3.12..." -ForegroundColor Yellow
    & $pythonCmd @pythonArgs -m venv $venvPath
    Write-Host "Virtual environment created." -ForegroundColor Green
} else {
    Write-Host "Virtual environment already exists at $venvPath." -ForegroundColor Green
}

# Ensure pip is up to date inside venv
Write-Host "Ensuring pip is updated..." -ForegroundColor Gray
& $venvPython -m pip install --upgrade pip

# Step 1: Install core dependencies respecting constraints
Write-Host "`n[Step 1/3] Installing core wheels with constraints (Zero-PyTorch & onnxruntime-gpu)..." -ForegroundColor Yellow
$reqFile = Join-Path $rootDir "backend\requirements.txt"
$constFile = Join-Path $rootDir "backend\constraints.txt"

& $venvPip install -r $reqFile -c $constFile
if ($LASTEXITCODE -ne 0) {
    Write-Error "Step 1 installation failed."
    exit $LASTEXITCODE
}

# Step 1.5: Acquire pure-CPU spaCy English model
Write-Host "`n[Step 1.5/3] Downloading pure-CPU spaCy English model (en_core_web_sm)..." -ForegroundColor Yellow
& $venvPython -m spacy download en_core_web_sm
if ($LASTEXITCODE -ne 0) {
    Write-Error "Step 1.5 spaCy model download failed."
    exit $LASTEXITCODE
}

# Step 2: Install speech engines strictly with --no-deps
Write-Host "`n[Step 2/3] Installing speech engines (--no-deps faster-whisper kokoro-onnx)..." -ForegroundColor Yellow
& $venvPip install --no-deps faster-whisper==1.2.1 kokoro-onnx==0.6.1
if ($LASTEXITCODE -ne 0) {
    Write-Error "Step 2 speech engines installation failed."
    exit $LASTEXITCODE
}

# Verification: Zero-PyTorch Invariant Check
Write-Host "`n[Verifying Invariant #2: Zero-PyTorch Check]..." -ForegroundColor Yellow
& $venvPython -c "import importlib.util, sys; sys.exit(1 if importlib.util.find_spec('torch') else 0)"
if ($LASTEXITCODE -ne 0) {
    Write-Error "CRITICAL INVARIANT VIOLATION: PyTorch was detected in the virtual environment!"
    exit 1
} else {
    Write-Host "Invariant Confirmed: 0 bytes of PyTorch installed." -ForegroundColor Green
}

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host "  Bootstrap Complete! Run 'python scripts/verify_gpu.py' to  " -ForegroundColor Cyan
Write-Host "  validate CUDA 12 and RTX 3050 hardware acceleration.      " -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
