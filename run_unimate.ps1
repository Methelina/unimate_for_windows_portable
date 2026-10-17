# ==========================================================
# UniMate Portable Launcher (PowerShell)
# ==========================================================
# Version: 1.0.0
# Author:  Soror L.'.L.'.
# Updated: 2026-10-17
#
# Patchnote v1.0.0 (By Soror L.'.L.'.):
#   [+] Initial release
#   [+] FULL ISOLATION: all runtime data inside project folder
#       (UV_CACHE_DIR, HF_HOME, TMP/TEMP, MPLCONFIGDIR, outputs)
#   [+] Menu: sample text / custom asset / train / HF download /
#       portable shell / precompute text embeddings
# ==========================================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = "UniMate Portable Launcher by L.'.L.'."
Set-Location $PSScriptRoot

$T_INFO = '[INFO]'
$T_WARN = '[WARN]'
$T_ERR  = '[ERROR]'
$T_OK   = '[OK]'

# ==========================================================
# Resolve UniMate source dir (repo root when scripts live in it)
# ==========================================================
$UnimateDir = $PSScriptRoot
if (-not (Test-Path (Join-Path $UnimateDir "unimate"))) {
    # standalone layout: look for a subfolder containing the package
    $cand = Get-ChildItem -Path $PSScriptRoot -Directory | Where-Object {
        Test-Path (Join-Path $_.FullName "unimate\__init__.py")
    } | Select-Object -First 1
    if ($cand) { $UnimateDir = $cand.FullName }
}
if (-not (Test-Path (Join-Path $UnimateDir "unimate\__init__.py"))) {
    Write-Host "$T_ERR UniMate source not found near $PSScriptRoot" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

# ==========================================================
# PORTABILITY ISOLATION BLOCK - Environment Variables
# ==========================================================
$env:SCRIPT_DIR   = $PSScriptRoot
$env:UV_CACHE_DIR = "$PSScriptRoot\.cache\uv"
$env:HF_HOME      = "$PSScriptRoot\.cache\huggingface"
$env:HF_HUB_DOWNLOAD_TIMEOUT = "60"
$env:PYTHONIOENCODING = "utf-8"
$env:TMP          = "$PSScriptRoot\.cache\tmp"
$env:TEMP         = "$PSScriptRoot\.cache\tmp"
$env:MPLCONFIGDIR = "$PSScriptRoot\.cache\matplotlib"
$env:TORCH_HOME   = "$PSScriptRoot\.cache\torch"
$env:SPACY_DATA   = "$PSScriptRoot\.cache\spacy"

# Outputs stay inside the project
$env:OUTPUT_DIR   = "$PSScriptRoot\outputs"
if (-not (Test-Path $env:OUTPUT_DIR)) { New-Item -ItemType Directory -Path $env:OUTPUT_DIR -Force | Out-Null }

# Create cache dirs
@($env:UV_CACHE_DIR, $env:HF_HOME, $env:TMP, $env:MPLCONFIGDIR, $env:TORCH_HOME, $env:SPACY_DATA) | ForEach-Object {
    if (-not (Test-Path $_)) { New-Item -ItemType Directory -Force -Path $_ | Out-Null }
}

# ==========================================================
# HF endpoint (uncomment if needed)
# ==========================================================
# $env:HF_ENDPOINT = "https://hf-mirror.com"

# ==========================================================
# CPU / threads
# ==========================================================
$env:NUMEXPR_MAX_THREADS = "32"
$env:OMP_NUM_THREADS     = "32"
$env:MKL_NUM_THREADS     = "32"
$env:MKL_DYNAMIC         = "TRUE"

# ==========================================================
# GPU settings
# ==========================================================
$env:CUDA_MODULE_LOADING    = "LAZY"
$env:CUDA_DEVICE_ORDER      = "PCI_BUS_ID"
$env:CUDA_VISIBLE_DEVICES   = "0"
$env:PYTORCH_CUDA_ALLOC_CONF = "garbage_collection_threshold:0.8,expandable_segments:True,max_split_size_mb:128"

# ==========================================================
# Environment check
# ==========================================================
$PythonExe = "$PSScriptRoot\unimate_env\Scripts\python.exe"
if (-not (Test-Path $PythonExe)) {
    Write-Host "$T_ERR python.exe not found: $PythonExe" -ForegroundColor Red
    Write-Host "$T_INFO Run install_unimate.ps1 first." -ForegroundColor Yellow
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host " ======================================================" -ForegroundColor Cyan
Write-Host "   UniMate Portable Launcher by Soror L.'.L.'." -ForegroundColor White
Write-Host "   Source: $UnimateDir" -ForegroundColor Gray
Write-Host " ======================================================" -ForegroundColor Cyan
Write-Host ""

# ==========================================================
# GPU pick (most free memory), like select_gpu in _common.sh
# ==========================================================
function Select-Gpu {
    if ($env:CUDA_VISIBLE_DEVICES) { return }
    try {
        $free = & nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>$null
        if ($free) {
            $best = 0; $bestVal = -1
            for ($i = 0; $i -lt $free.Count; $i++) {
                if ([int]$free[$i] -gt $bestVal) { $bestVal = [int]$free[$i]; $best = $i }
            }
            $env:CUDA_VISIBLE_DEVICES = "$best"
            Write-Host "$T_INFO GPU: $best (most free memory)" -ForegroundColor Green
        }
    } catch { Write-Host "$T_WARN nvidia-smi unavailable, using GPU 0" -ForegroundColor Yellow }
}
Select-Gpu

# ==========================================================
# Menu
# ==========================================================
Write-Host "  1. Sample motion - text + custom asset (e.g. assets/examples/eagle)" -ForegroundColor White
Write-Host "  2. Sample motion - test_cases_json" -ForegroundColor White
Write-Host "  3. Train" -ForegroundColor White
Write-Host "  4. Download checkpoint from HuggingFace" -ForegroundColor White
Write-Host "  5. Precompute text embeddings" -ForegroundColor White
Write-Host "  6. Animate samples (drive meshes)" -ForegroundColor White
Write-Host "  7. Portable Python shell" -ForegroundColor White
Write-Host ""
$choice = Read-Host "Select mode [1-7]"

Set-Location $UnimateDir

switch ($choice) {
    "1" {
        $exp = Read-Host "Checkpoint dir (default: outputs/unimate_uniml3d_f60_v3)"
        if (-not $exp) { $exp = "outputs/unimate_uniml3d_f60_v3" }
        $asset = Read-Host "Asset dir (default: assets/examples/eagle)"
        if (-not $asset) { $asset = "assets/examples/eagle" }
        $prompt = Read-Host "Prompt (default: 'An object walks forward.')"
        if (-not $prompt) { $prompt = "An object walks forward." }
        & $PythonExe -m unimate.inference.sample --exp_dir $exp --asset $asset --prompt $prompt --output_dir "$env:OUTPUT_DIR\samples_custom"
        Write-Host "$T_OK Results in $env:OUTPUT_DIR\samples_custom" -ForegroundColor Green
    }
    "2" {
        $exp = Read-Host "Checkpoint dir (default: outputs/unimate_uniml3d_f60_v3)"
        if (-not $exp) { $exp = "outputs/unimate_uniml3d_f60_v3" }
        $cases = Read-Host "test_cases_json path (default: assets/examples/examples.json)"
        if (-not $cases) { $cases = "assets/examples/examples.json" }
        & $PythonExe -m unimate.inference.sample --exp_dir $exp --test_cases_json $cases --num_repetitions 3 --output_dir "$env:OUTPUT_DIR\samples_examples"
        Write-Host "$T_OK Results in $env:OUTPUT_DIR\samples_examples" -ForegroundColor Green
    }
    "3" {
        $cfg = Read-Host "Config (default: configs/uniml3d_60frames_graph_adaln.json)"
        if (-not $cfg) { $cfg = "configs/uniml3d_60frames_graph_adaln.json" }
        & $PythonExe -m accelerate.commands.launch --num_processes 1 -m unimate.training.train --config $cfg
    }
    "4" {
        Write-Host "$T_INFO Downloading Linzhan/UniMate checkpoint (~GBs)..." -ForegroundColor Cyan
        & $PythonExe -m huggingface_hub.commands.huggingface_cli download Linzhan/UniMate --repo-type model --local-dir outputs `
            --include "unimate_uniml3d_f60_v3/*"
        Write-Host "$T_OK Done. Checkpoint in outputs\unimate_uniml3d_f60_v3" -ForegroundColor Green
    }
    "5" {
        $cfg = Read-Host "Config (default: configs/uniml3d_60frames_graph_adaln.json)"
        if (-not $cfg) { $cfg = "configs/uniml3d_60frames_graph_adaln.json" }
        & $PythonExe -m unimate.tools.precompute_text_emb --config $cfg
    }
    "6" {
        $dir = Read-Host "Samples dir to animate"
        if (-not $dir) { Write-Host "$T_ERR No dir given." -ForegroundColor Red; break }
        $env:SKIP_INVALID = "1"
        & $PythonExe -m data_process.mesh_animation.sample_manifest $dir --skip_invalid
    }
    "7" {
        Write-Host "$T_INFO Portable shell. 'exit' to leave." -ForegroundColor Cyan
        & $PythonExe
    }
    default {
        Write-Host "$T_WARN Unknown choice." -ForegroundColor Yellow
    }
}

Write-Host ""
Read-Host "Press Enter to exit"
