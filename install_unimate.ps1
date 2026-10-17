# ==========================================
# SYNOPSIS
#     UniMate Portable Installer v1.0.2
#     Fully portable installer with uv + isolated caches (unimate_env)
# ==========================================
#
# DESCRIPTION
#     Installs a fully portable UniMate environment:
#       - Downloads uv package manager and creates a Python 3.10 venv.
#       - Sets env vars (UV_CACHE_DIR, HF_HOME, TMP/TEMP, etc.) inside the
#         project folder so nothing is written to C:\Users\....
#       - Installs PyTorch 2.5.1 + cu124 from the PyTorch index.
#       - Installs bpy 4.0.0 from the Blender wheel index.
#       - Installs requirements.txt with --no-build-isolation against
#         setuptools<81 (required by the Motion git dependency).
#       - Supports an external UniMate source dir via settings_unimate.yaml
#         (unimate_dir) or auto-detects the repo this script sits in.
#
# ==========================================
# VERSION:     1.0.2
# AUTHOR:      Soror L.'.L.'.
# UPDATED:     2026-10-17
#
# Patch Notes v1.0.2 (Soror L.'.L.'.):
#   [+] uv-managed Python install stage (uv python install - standalone
#       build, CrisTical pattern; survives venv recreation)
#   [+] Idempotent venv stage: skip when a valid venv already exists
#   [+] pip retry-once on requirements install
#   [*] bpy 4.0.0 stays on the Blender index (cp310 wheels are not on PyPI)
#   [FIX] bpy install: --index-url -> --extra-index-url so PyPI deps
#       (cython etc.) resolve alongside the Blender wheel index
#   [FIX] requirements install: add --index-strategy unsafe-best-match so
#       uv considers all indexes for each package (tqdm==4.67.3 not on
#       the PyTorch cu124 index but present on PyPI)
#
# Patch Notes v1.0.0 (Soror L.'.L.'.):
#   [+] Initial release: portable uv venv, cu124 torch, bpy index,
#       --no-build-isolation install, full cache isolation.
# ==========================================
# USAGE
#     1. Place settings_unimate.yaml next to this script.
#     2. Run install_unimate.ps1 (right-click "Run with PowerShell").
#     3. After installation, use run_unimate.ps1 to launch.
# ==========================================

[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$ProgressPreference = 'SilentlyContinue'

$ScriptPath = $PSScriptRoot
if (-not $ScriptPath) { $ScriptPath = "." }
Set-Location $ScriptPath

$T_INFO = '[INFO]'
$T_WARN = '[WARN]'
$T_ERR  = '[ERROR]'
$T_OK   = '[OK]'

function Write-Status {
    param([string]$Message, [string]$Type = "INFO")
    $color = switch ($Type) {
        "INFO"    { "Cyan" }
        "WARN"    { "Yellow" }
        "ERROR"   { "Red" }
        "OK"      { "Green" }
        default   { "White" }
    }
    Write-Host " $Type $Message" -ForegroundColor $color
}

function Write-Step {
    param([string]$Message, [int]$Step, [int]$Total)
    Write-Host ""
    Write-Host ">>> Stage [$Step/$Total]: $Message" -ForegroundColor Magenta
}

function Wait-Enter {
    param([string]$Prompt = "Press Enter to exit")
    if ([Console]::IsInputRedirected) { return }
    Read-Host $Prompt | Out-Null
}

# ==========================================
# PORTABILITY ISOLATION BLOCK
# ==========================================
$CacheDir = Join-Path $ScriptPath ".cache"
$UvCacheDir = Join-Path $CacheDir "uv"
$HfCacheDir = Join-Path $CacheDir "huggingface"
$TmpDir = Join-Path $CacheDir "tmp"

@($CacheDir, $UvCacheDir, $HfCacheDir, $TmpDir) | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -ItemType Directory -Force -Path $_ | Out-Null }
}

$env:UV_CACHE_DIR = $UvCacheDir
$env:HF_HOME = $HfCacheDir
$env:HF_HUB_DOWNLOAD_TIMEOUT = "60"
$env:TMP = $TmpDir
$env:TEMP = $TmpDir

# ==========================================
# Load settings
# ==========================================
$SettingsFile = Join-Path $ScriptPath "settings_unimate.yaml"
if (-not (Test-Path $SettingsFile)) {
    Write-Status "settings_unimate.yaml not found, using built-in defaults." "WARN"
    $config = @{ env_name = "unimate_env"; python_version = "3.10"; uv_version = "0.11.6" }
} else {
    $yamlText = Get-Content $SettingsFile -Raw
    $config = @{}
    $config['env_name'] = if ($yamlText -match "env_name:\s*`"(.+?)`"") { $matches[1] } else { "unimate_env" }
    $config['python_version'] = if ($yamlText -match "python_version:\s*`"(.+?)`"") { $matches[1] } else { "3.10" }
    $config['unimate_dir'] = if ($yamlText -match "unimate_dir:\s*`"(.+?)`"") { $matches[1] } else { "." }
    $config['torch_version'] = if ($yamlText -match "torch_version:\s*`"(.+?)`"") { $matches[1] } else { "2.5.1+cu124" }
    $config['torchvision_version'] = if ($yamlText -match "torchvision_version:\s*`"(.+?)`"") { $matches[1] } else { "0.20.1+cu124" }
    $config['torch_index'] = if ($yamlText -match "torch_index:\s*`"(.+?)`"") { $matches[1] } else { "https://download.pytorch.org/whl/cu124" }
    $config['bpy_index'] = if ($yamlText -match "bpy_index:\s*`"(.+?)`"") { $matches[1] } else { "https://download.blender.org/pypi/" }
    $config['uv_version'] = if ($yamlText -match "uv_version:\s*`"(.+?)`"") { $matches[1] } else { "0.11.6" }
}

$EnvName = $config['env_name']
$UnimateDir = Resolve-Path (Join-Path $ScriptPath $config['unimate_dir']) -ErrorAction SilentlyContinue
if (-not $UnimateDir -or -not (Test-Path (Join-Path $UnimateDir "requirements.txt"))) {
    # Auto-detect: scripts inside the repo root itself
    if (Test-Path (Join-Path $ScriptPath "requirements.txt")) {
        $UnimateDir = $ScriptPath
    } else {
        Write-Status "Cannot locate UniMate source (requirements.txt not found). Set unimate_dir in settings_unimate.yaml." "ERROR"
        Wait-Enter
        exit 1
    }
}
$ReqFile = Join-Path $UnimateDir "requirements.txt"
$PythonExePath = Join-Path $ScriptPath "$EnvName\Scripts\python.exe"

Write-Host ""
Write-Host " ==========================================" -ForegroundColor Green
Write-Host "   UniMate Portable Installer v1.0.0" -ForegroundColor Yellow
Write-Host "   by Soror L.'.L.'." -ForegroundColor Yellow
Write-Host " ==========================================" -ForegroundColor Green
Write-Host "   Source:  $UnimateDir" -ForegroundColor Gray
Write-Host "   Env:     $EnvName (Python $($config['python_version']))" -ForegroundColor Gray
Write-Host ""

# ==========================================
# Stage 0: Download uv
# ==========================================
Write-Step "Downloading uv package manager ($($config['uv_version']))..." 0 6
$UvExePath = Join-Path $ScriptPath "uv.exe"
if (-not (Test-Path $UvExePath)) {
    $UvZipUrl = "https://releases.astral.sh/github/uv/releases/download/$($config['uv_version'])/uv-x86_64-pc-windows-msvc.zip"
    $uvZip = Join-Path $ScriptPath "uv.zip"
    try {
        Invoke-WebRequest -Uri $UvZipUrl -OutFile $uvZip -ErrorAction Stop
    } catch {
        Write-Status "Download failed: $($_.Exception.Message)" "ERROR"
        Wait-Enter
        exit 1
    }
    if ((Get-Item $uvZip).Length -lt 1000) {
        Write-Status "Downloaded file too small (error page)." "ERROR"
        Remove-Item $uvZip -Force -ErrorAction SilentlyContinue
        Wait-Enter
        exit 1
    }
    $uvTmp = Join-Path $ScriptPath "uv_tmp"
    if (Test-Path $uvTmp) { Remove-Item $uvTmp -Recurse -Force }
    Expand-Archive -Path $uvZip -DestinationPath $uvTmp -Force
    $uvExe = Get-ChildItem -Path $uvTmp -Filter "uv.exe" -Recurse | Select-Object -First 1
    Copy-Item $uvExe.FullName $UvExePath -Force
    Remove-Item $uvTmp -Recurse -Force
    Remove-Item $uvZip -Force
    Write-Status "uv extracted." "OK"
} else {
    Write-Status "uv.exe already present, skipping." "OK"
}

# ==========================================
# Stage 1: uv-managed Python (standalone build)
# ==========================================
Write-Step "Installing Python $($config['python_version']) via uv (standalone)..." 1 7
& $UvExePath python install $config['python_version']
if ($LASTEXITCODE -ne 0) {
    Write-Status "Failed to install Python via uv." "ERROR"
    Wait-Enter
    exit 1
}
Write-Status "Python $($config['python_version']) ready." "OK"

# ==========================================
# Stage 2: Create venv (idempotent)
# ==========================================
Write-Step "Creating Python environment ($EnvName)..." 2 7
$EnvDir = Join-Path $ScriptPath $EnvName
$EnvCfg = Join-Path $EnvDir "pyvenv.cfg"
if ((Test-Path $PythonExePath) -and (Test-Path $EnvCfg)) {
    Write-Status "Valid environment already present - skipping creation." "OK"
} else {
    if (Test-Path $EnvDir) {
        Write-Status "Recreating broken environment '$EnvName'." "WARN"
        Remove-Item $EnvDir -Recurse -Force
    }
    & $UvExePath venv $EnvDir --python $config['python_version']
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $PythonExePath)) {
        Write-Status "Failed to create environment." "ERROR"
        Wait-Enter
        exit 1
    }
    Write-Status "Environment created." "OK"
}

# ==========================================
# Stage 3: setuptools<81 (required BEFORE requirements: Motion build
# imports pkg_resources; isolated builds use newest setuptools -> fail)
# ==========================================
Write-Step "Installing setuptools<81..." 3 7
& $UvExePath pip install --python $PythonExePath "setuptools<81" wheel
if ($LASTEXITCODE -ne 0) {
    Write-Status "Failed to install setuptools." "ERROR"
    Wait-Enter
    exit 1
}
Write-Status "setuptools pinned." "OK"

# ==========================================
# Stage 4: PyTorch cu124 + bpy from Blender index
# ==========================================
Write-Step "Installing PyTorch $($config['torch_version']) and bpy 4.0.0..." 4 7
& $UvExePath pip install --python $PythonExePath `
    "torch==$($config['torch_version'])" "torchvision==$($config['torchvision_version'])" `
    --index-url $config['torch_index']
if ($LASTEXITCODE -ne 0) {
    Write-Status "Failed to install PyTorch." "ERROR"
    Wait-Enter
    exit 1
}
& $UvExePath pip install --python $PythonExePath "bpy==4.0.0" --extra-index-url $config['bpy_index']
if ($LASTEXITCODE -ne 0) {
    Write-Status "bpy install failed (EEVEE render stages will not work; export/animate still fine)." "WARN"
} else {
    Write-Status "bpy installed." "OK"
}

# ==========================================
# Stage 5: requirements.txt with --no-build-isolation (+ retry once)
# ==========================================
Write-Step "Installing requirements.txt (--no-build-isolation)..." 5 7
& $UvExePath pip install --python $PythonExePath -r $ReqFile --no-build-isolation --index-strategy unsafe-best-match
if ($LASTEXITCODE -ne 0) {
    Write-Status "requirements install failed - retrying once..." "WARN"
    & $UvExePath pip install --python $PythonExePath -r $ReqFile --no-build-isolation --index-strategy unsafe-best-match
}
if ($LASTEXITCODE -ne 0) {
    Write-Status "requirements install failed. Check the log above." "ERROR"
    Wait-Enter
    exit 1
}
Write-Status "requirements installed." "OK"

# ==========================================
# Stage 6: Verification
# ==========================================
Write-Step "Verifying installation..." 6 7
& $PythonExePath -c "import torch; print('torch', torch.__version__, 'cuda', torch.cuda.is_available())"
& $PythonExePath -c "import bpy; print('bpy', bpy.app.version_string)"
if ($LASTEXITCODE -ne 0) { Write-Status "bpy import failed (EEVEE render stages will not work)." "WARN" }
Push-Location $UnimateDir
& $PythonExePath -c "import unimate; print('unimate import OK')"
Pop-Location
if ($LASTEXITCODE -eq 0) {
    Write-Status "UniMate package verified." "OK"
} else {
    Write-Status "UniMate import failed - check 'unimate_dir' setting." "ERROR"
}

# ==========================================
# Stage 7: smoketest of module entry points
# ==========================================
Write-Step "Smoke-testing entry points..." 7 7
Push-Location $UnimateDir
& $PythonExePath -m unimate.inference.sample --help *> $null
if ($LASTEXITCODE -eq 0) { Write-Status "unimate.inference.sample OK" "OK" } else { Write-Status "unimate.inference.sample FAILED" "ERROR" }
& $PythonExePath -m unimate.training.train --help *> $null
if ($LASTEXITCODE -eq 0) { Write-Status "unimate.training.train OK" "OK" } else { Write-Status "unimate.training.train FAILED" "ERROR" }
Pop-Location

Write-Host ""
Write-Host " ==========================================" -ForegroundColor Green
Write-Host "   INSTALLATION COMPLETE" -ForegroundColor Green
Write-Host "   Launch with: run_unimate.ps1" -ForegroundColor Yellow
Write-Host " ==========================================" -ForegroundColor Green
Write-Host ""
Wait-Enter
