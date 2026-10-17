# ==========================================================
# UniMate Portable Launcher (PowerShell)
# ==========================================================
# Version: 1.0.0
# Author:  Soror L.'.L.'.
# Updated: 2026-10-17
#
# Patchnote v1.1.0 (By Soror L.'.L.'.):
#   [+] Full capability menu: motion editing, in-betweening, expansion,
#       rig preprocessing, real mesh animation (GLB+FBX per manifest job)
#   [+] Checkpoint download switched to the pycurl downloader (inference
#       files only, resumable)
#   [+] "Animate now?" offer after generation; job-loop with per-job status
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
# Helpers
# ==========================================================
function Ask-Exp {
    $e = Read-Host "Checkpoint dir (default: outputs/unimate_uniml3d_f60_v3)"
    if (-not $e) { $e = "outputs/unimate_uniml3d_f60_v3" }
    return $e
}

function Invoke-AnimJobs {
    param([string]$Dir)
    $env:PYTHONIOENCODING = "utf-8"
    $jobLines = & $PythonExe -m data_process.mesh_animation.sample_manifest $Dir --skip_invalid 2>$null
    $jobs = @($jobLines | Where-Object { $_ -match "`t" })
    if ($jobs.Count -eq 0) {
        Write-Host "$T_WARN No animatable jobs found in $Dir" -ForegroundColor Yellow
        return
    }
    Write-Host "$T_INFO $($jobs.Count) job(s) to animate -> GLB + FBX" -ForegroundColor Cyan
    $i = 0
    foreach ($job in $jobs) {
        $i++
        $p = $job -split "`t"
        if ($p.Count -lt 4) { continue }
        $anim = $p[0]; $char = $p[1]; $cond = $p[2]; $dtype = $p[3]
        $stem = [System.IO.Path]::GetFileNameWithoutExtension($anim)
        $out = Join-Path $Dir "animated"
        Write-Host "[$i/$($jobs.Count)] $stem (char=$char)" -ForegroundColor Gray
        & $PythonExe -m data_process.mesh_animation.animate_motion --dataset_type $dtype `
            --anim_path $anim --char_path $char --cond_path $cond --output_dir $out
        if ($LASTEXITCODE -ne 0) { Write-Host "$T_WARN job $stem failed, continuing." -ForegroundColor Yellow }
    }
    Write-Host "$T_OK Animated files in $Dir\animated" -ForegroundColor Green
}

# ==========================================================
# Menu
# ==========================================================
Write-Host "  --- Generate ---" -ForegroundColor DarkGray
Write-Host "  1. Generate motion        (your asset + a text prompt)" -ForegroundColor White
Write-Host "  2. Generate batch         (several scenes from a JSON list)" -ForegroundColor White
Write-Host "  3. Motion editing         (keep joints, re-animate the rest)" -ForegroundColor White
Write-Host "  4. In-betweening          (fill between keyframes)" -ForegroundColor White
Write-Host "  5. Motion expansion       (chain prompts into one long take)" -ForegroundColor White
Write-Host "  --- Your model ---" -ForegroundColor DarkGray
Write-Host "  6. Prepare own rig        (GLB/glTF/FBX -> UniMate asset)" -ForegroundColor White
Write-Host "  7. Animate samples        (motions -> animated GLB + FBX)" -ForegroundColor White
Write-Host "  --- Model files ---" -ForegroundColor DarkGray
Write-Host "  8. Download checkpoint    (once, ~1.1 GB, inference files only)" -ForegroundColor White
Write-Host "  --- Advanced ---" -ForegroundColor DarkGray
Write-Host "  9. Train" -ForegroundColor White
Write-Host " 10. Precompute text embeddings" -ForegroundColor White
Write-Host " 11. Portable Python shell" -ForegroundColor White
Write-Host ""
$choice = Read-Host "Select mode [1-11]"

Set-Location $UnimateDir

switch ($choice) {
    "1" {
        $exp = Ask-Exp
        $asset = Read-Host "Asset dir or example name (default: assets/examples/eagle)"
        if (-not $asset) { $asset = "assets/examples/eagle" }
        $prompt = Read-Host "Prompt, English, e.g. 'An object walks forward.'"
        if (-not $prompt) { $prompt = "An object walks forward." }
        $reps = Read-Host "Variants to generate (default: 3)"
        if (-not $reps) { $reps = "3" }
        $cfg = Read-Host "Prompt adherence 1-10 (default: 3; raise to 5-7 if ignored)"
        if (-not $cfg) { $cfg = "3" }
        & $PythonExe -m unimate.inference.sample --exp_dir $exp --asset $asset --prompt $prompt `
            --num_repetitions $reps --cfg_scale $cfg --output_dir "$env:OUTPUT_DIR\samples_custom"
        Write-Host "$T_OK Previews: $env:OUTPUT_DIR\samples_custom\animations ; motions: motions\" -ForegroundColor Green
        $anim = Read-Host "Animate the mesh now? (y/N)"
        if ($anim -eq 'y' -or $anim -eq 'Y') { Invoke-AnimJobs -Dir "$env:OUTPUT_DIR\samples_custom" }
    }
    "2" {
        $exp = Ask-Exp
        $cases = Read-Host "test_cases_json path (default: assets/examples/examples.json)"
        if (-not $cases) { $cases = "assets/examples/examples.json" }
        & $PythonExe -m unimate.inference.sample --exp_dir $exp --test_cases_json $cases `
            --num_repetitions 3 --output_dir "$env:OUTPUT_DIR\samples_examples"
        Write-Host "$T_OK Results in $env:OUTPUT_DIR\samples_examples" -ForegroundColor Green
        $anim = Read-Host "Animate the meshes now? (y/N)"
        if ($anim -eq 'y' -or $anim -eq 'Y') { Invoke-AnimJobs -Dir "$env:OUTPUT_DIR\samples_examples" }
    }
    "3" {
        $exp = Ask-Exp
        $cases = Read-Host "test_cases_json naming clips to edit (required, e.g. {`"mixamo-Air_Squat-000`": `"An object squats.`"})"
        if (-not $cases) { Write-Host "$T_ERR A cases JSON is required." -ForegroundColor Red; break }
        $joints = Read-Host "Joints to keep, comma-separated (default: Neck,Head)"
        if (-not $joints) { $joints = "Neck,Head" }
        & $PythonExe -m unimate.inference.sample --exp_dir $exp --test_cases_json $cases `
            --motion_edit --keep_joints $joints --output_dir "$env:OUTPUT_DIR\samples_edit"
        Write-Host "$T_OK Results in $env:OUTPUT_DIR\samples_edit\motion_edit" -ForegroundColor Green
    }
    "4" {
        $exp = Ask-Exp
        $cases = Read-Host "test_cases_json naming clips (required)"
        if (-not $cases) { Write-Host "$T_ERR A cases JSON is required." -ForegroundColor Red; break }
        $frames = Read-Host "Frames to keep, signed indices (default: 0,-1 = first and last pose)"
        if (-not $frames) { $frames = "0,-1" }
        & $PythonExe -m unimate.inference.sample --exp_dir $exp --test_cases_json $cases `
            --inbetween --keep_frames $frames --output_dir "$env:OUTPUT_DIR\samples_inbetween"
        Write-Host "$T_OK Results in $env:OUTPUT_DIR\samples_inbetween\inbetween" -ForegroundColor Green
    }
    "5" {
        $exp = Ask-Exp
        $cases = Read-Host "test_cases_json with prompt LISTS per case (required)"
        if (-not $cases) { Write-Host "$T_ERR A cases JSON is required." -ForegroundColor Red; break }
        $overlap = Read-Host "Frames shared between segments (default: 10)"
        if (-not $overlap) { $overlap = "10" }
        & $PythonExe -m unimate.inference.sample --exp_dir $exp --test_cases_json $cases `
            --motion_expand --expand_overlap $overlap --output_dir "$env:OUTPUT_DIR\samples_expand"
        Write-Host "$T_OK Results in $env:OUTPUT_DIR\samples_expand\motion_expand" -ForegroundColor Green
    }
    "6" {
        $inp = Read-Host "Path to your rigged GLB/glTF/FBX"
        if (-not $inp) { Write-Host "$T_ERR No input given." -ForegroundColor Red; break }
        $out = Read-Host "Output asset dir (default: outputs/rig/<name>)"
        if (-not $out) {
            $name = [System.IO.Path]::GetFileNameWithoutExtension($inp)
            $out = "outputs/rig/$name"
        }
        & $PythonExe -m data_process.rig_preprocess run --input $inp --output_dir $out --no_review
        if ($LASTEXITCODE -eq 0) {
            Write-Host "$T_OK Asset ready: $out" -ForegroundColor Green
            Write-Host "$T_INFO Use it in menu 1 as: $out" -ForegroundColor Cyan
        } else {
            Write-Host "$T_ERR Preprocessing failed - see log above." -ForegroundColor Red
        }
    }
    "7" {
        $dir = Read-Host "Samples dir to animate (e.g. outputs\samples_custom)"
        if (-not $dir) { Write-Host "$T_ERR No dir given." -ForegroundColor Red; break }
        Invoke-AnimJobs -Dir $dir
    }
    "8" {
        Write-Host "$T_INFO Downloading inference files (~1.1 GB) via pycurl downloader..." -ForegroundColor Cyan
        & $PythonExe "tools\_hf_pycurl_download.py" Linzhan/UniMate outputs --repo-type model `
            --include "unimate_uniml3d_f60_v3/config.json" `
            --include "unimate_uniml3d_f60_v3/dataset_stats.npy" `
            --include "unimate_uniml3d_f60_v3/checkpoints/checkpoint_step_150000.pt"
        Write-Host "$T_OK Checkpoint in outputs\unimate_uniml3d_f60_v3" -ForegroundColor Green
    }
    "9" {
        $cfg = Read-Host "Config (default: configs/uniml3d_60frames_graph_adaln.json)"
        if (-not $cfg) { $cfg = "configs/uniml3d_60frames_graph_adaln.json" }
        & $PythonExe -m accelerate.commands.launch --num_processes 1 -m unimate.training.train --config $cfg
    }
    "10" {
        $cfg = Read-Host "Config (default: configs/uniml3d_60frames_graph_adaln.json)"
        if (-not $cfg) { $cfg = "configs/uniml3d_60frames_graph_adaln.json" }
        & $PythonExe -m unimate.tools.precompute_text_emb --config $cfg
    }
    "11" {
        Write-Host "$T_INFO Portable shell. 'exit' to leave." -ForegroundColor Cyan
        & $PythonExe
    }
    default {
        Write-Host "$T_WARN Unknown choice." -ForegroundColor Yellow
    }
}

Write-Host ""
Read-Host "Press Enter to exit"
