# -*- coding: utf-8 -*-
"""UniMate MCP bridge - FastMCP server.

Exposes UniMate inference as MCP tools: text-to-animation sampling on
dataset skeletons or user rigs (rig_preprocess outputs / glTF assets),
mesh animation (GLB/FBX via pip bpy), manifest inspection, checkpoint
download (pycurl) and non-interactive rig preprocessing.

Every tool shells out to the portable unimate_env python in a subprocess,
so a tool crash can never poison the server process; the environment is
isolated to the project folder the same way run_unimate.ps1 does it.

FModel.Cli/mcp_unimate/server.py
Version:     1.0.0
Author:      Soror L.'.L.'.
Updated:     2026-10-18

Patch Notes v1.0.0 (Soror L.'.L.'.):
  [+] Initial release: sample_animation, get_manifest, animate_motion,
      animate_manifest, preprocess_rig, download_checkpoint,
      list_examples, list_checkpoints.
"""

import functools
import json
import os
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import List, Optional

from mcp.server.fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[1]
PYEXE = ROOT / "unimate_env" / "Scripts" / "python.exe"
DEFAULT_EXP = "outputs/unimate_uniml3d_f60_v3"
DEFAULT_TIMEOUT = 3600

mcp = FastMCP(
    "unimate",
    instructions=(
        "UniMate text-to-animation bridge. Generate skeletal motion for an "
        "arbitrary rigged GLB asset from a text prompt (sample_animation), "
        "drive the asset's mesh with the generated motion (animate_motion / "
        "animate_manifest), and preprocess new rigs (preprocess_rig)."
    ),
)


def _env() -> dict:
    env = os.environ.copy()
    env.update({
        "PYTHONIOENCODING": "utf-8",
        "HF_HOME": str(ROOT / ".cache" / "huggingface"),
        "HF_HUB_DOWNLOAD_TIMEOUT": "60",
        "MPLCONFIGDIR": str(ROOT / ".cache" / "matplotlib"),
        "TMP": str(ROOT / ".cache" / "tmp"),
        "TEMP": str(ROOT / ".cache" / "tmp"),
        "CUDA_VISIBLE_DEVICES": os.environ.get("UNIMATE_GPU", "0"),
        "PYTORCH_CUDA_ALLOC_CONF":
            "garbage_collection_threshold:0.8,expandable_segments:True,"
            "max_split_size_mb:128",
    })
    return env


def _run(args: List[str], timeout: int = DEFAULT_TIMEOUT, tag: str = "py"):
    """Run a unimate_env python module with LIVE streaming output.

    Every stdout/stderr line is echoed to this process's stderr prefixed
    with ``[unimate:<tag>]`` so a human or an agent can see the stage the
    subprocess is in right now (model load, sampling, encoding...). Only
    the last lines are retained and returned as (rc, tail). A watchdog
    kills the subprocess after *timeout* seconds - a hung backend can
    never outlive the call.
    Returns (rc, tail_str, err_tail_str).
    """
    cmd = [str(PYEXE), *args]
    print(f"[unimate:{tag}] $ {' '.join(args)}", file=sys.stderr, flush=True)
    proc = subprocess.Popen(
        cmd, cwd=str(ROOT), env=_env(),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace", bufsize=1,
    )
    tail = deque(maxlen=80)
    killed = {"flag": False}

    def _fire():
        killed["flag"] = True
        proc.kill()

    watchdog = threading.Timer(timeout, _fire)
    watchdog.daemon = True
    watchdog.start()

    try:
        for line in proc.stdout:
            line = line.rstrip()
            if not line:
                continue
            print(f"[unimate:{tag}] {line}", file=sys.stderr, flush=True)
            tail.append(line)
        rc = proc.wait()
    finally:
        watchdog.cancel()
    err_tail = ""
    if killed["flag"]:
        err_tail = (f"TIMEOUT after {timeout}s - process was killed. "
                    "Partial results may exist in the output dir.")
        print(f"[unimate:{tag}] {err_tail}", file=sys.stderr, flush=True)
        rc = rc if rc else -9
    return rc, "\n".join(tail), err_tail


def _safe(fn):
    """Wrap a tool: every failure becomes a structured JSON error with the
    exception type, message and elapsed time - a tool call can fail loudly
    but never freeze or raise through the MCP layer."""
    @functools.wraps(fn)
    def wrapper(*a, **k):
        t0 = time.time()
        try:
            return fn(*a, **k)
        except subprocess.TimeoutExpired as exc:
            return json.dumps({
                "error": "TIMEOUT",
                "seconds": int(time.time() - t0),
                "message": str(exc),
                "hint": "the subprocess was killed; partial results may "
                        "exist in the output directory",
            }, ensure_ascii=False, indent=2)
        except Exception as exc:  # noqa: BLE001 - tools must report, not crash
            return json.dumps({
                "error": type(exc).__name__,
                "message": str(exc),
                "elapsed_s": round(time.time() - t0, 1),
            }, ensure_ascii=False, indent=2)
    return wrapper


def _pick(out_root: Path) -> dict:
    """Collect generated files under a sample output dir."""
    files = {"motions": [], "animations": [], "other": []}
    if not out_root.is_dir():
        return files
    for p in out_root.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(out_root).as_posix()
        if p.suffix == ".npy":
            files["motions"].append(rel)
        elif p.suffix in (".mp4", ".png"):
            files["animations"].append(rel)
        else:
            files["other"].append(rel)
    return files


# --------------------------------------------------------------------------- #
# Tools
# --------------------------------------------------------------------------- #
@mcp.tool()
@_safe
def list_examples() -> str:
    """List built-in example assets (eagle, shark, unitree_go2) with their
    summary.json metadata. Use these names as the `asset` argument of
    sample_animation."""
    ex_dir = ROOT / "assets" / "examples"
    out = []
    if ex_dir.is_dir():
        for d in sorted(ex_dir.iterdir()):
            if not d.is_dir():
                continue
            entry = {"name": d.name}
            summary = d / "summary.json"
            if summary.is_file():
                try:
                    meta = json.loads(summary.read_text(encoding="utf-8"))
                    entry["summary"] = meta
                except Exception as exc:
                    entry["summary_error"] = str(exc)
            out.append(entry)
    return json.dumps(out, ensure_ascii=False, indent=2)


@mcp.tool()
@_safe
def list_checkpoints() -> str:
    """List available trained-run directories under outputs/ that contain
    config.json + dataset_stats.npy (usable as exp_dir for sampling)."""
    outs = ROOT / "outputs"
    found = []
    if outs.is_dir():
        for d in sorted(outs.rglob("config.json")):
            run = d.parent
            if (run / "dataset_stats.npy").is_file() and list(run.glob("checkpoints/*.pt")):
                found.append(run.relative_to(outs).as_posix())
    return json.dumps(found, indent=2)


@mcp.tool()
@_safe
def sample_animation(
    asset: str,
    prompts: Optional[List[str]] = None,
    num_repetitions: int = 1,
    cfg_scale: Optional[float] = None,
    seed: Optional[int] = None,
    exp_dir: str = DEFAULT_EXP,
    output_dir: Optional[str] = None,
    test_cases_json: Optional[str] = None,
    motion_edit: bool = False,
    keep_joints: str = "Neck,Head",
    inbetween: bool = False,
    keep_frames: str = "0,-1",
    motion_expand: bool = False,
    expand_overlap: int = 10,
) -> str:
    """Generate skeletal motion for an asset from text prompt(s), or run one
    of the advanced modes against a test-cases JSON.

    asset: an assets/examples name (see list_examples), a rig_preprocess
        output directory, a path to a rig directory with cond.npy, or a
        '<dataset>:<object_type>' reference.
    prompts: one or more captions in the training style, e.g.
        'An object flaps its wings.' - start with 'An object', describe one
        motion, not the character.
    test_cases_json: JSON naming clips/scenes (batch generation); REQUIRED
        for the three modes below (their keys must name real clips, e.g.
        {"mixamo-Air_Squat-000": "An object squats and then stands up."}).
    motion_edit + keep_joints: hold those joints at their recorded motion,
        re-animate the rest under the new prompt.
    inbetween + keep_frames: hold signed frame indices (e.g. "0,-1" = first
        and last pose) and generate everything between them.
    motion_expand + expand_overlap: chain the per-case prompt LISTS into one
        long motion, segments sharing expand_overlap frames.
    cfg_scale: prompt adherence (default 3 from the run config; raise to
        5-7 if the prompt is ignored).
    Exactly one of motion_edit / inbetween / motion_expand may be set.
    Returns JSON: output_dir, manifest path and generated file lists.
    """
    def _fail(code, message, hint):
        return json.dumps({"error": code, "message": message, "hint": hint},
                          ensure_ascii=False, indent=2)

    modes = [m for m in (motion_edit, inbetween, motion_expand) if m]
    if len(modes) > 1:
        return _fail("BAD_MODE", "motion_edit, inbetween and motion_expand are "
                     "mutually exclusive",
                     "call sample_animation again with exactly one of them")
    if modes and not test_cases_json:
        return _fail("MISSING_TEST_CASES",
                     "motion_edit / inbetween / motion_expand require "
                     "test_cases_json",
                     "pass a JSON file whose keys name real clips, e.g. "
                     '{"mixamo-Air_Squat-000": "An object squats and then '
                     'stands up."}')
    if test_cases_json:
        cases = Path(test_cases_json)
        if not cases.exists():
            cases = ROOT / test_cases_json
        if not cases.exists():
            return _fail("FILE_NOT_FOUND",
                         f"test_cases_json not found: {test_cases_json}",
                         "pass a path relative to the project root or "
                         "absolute; see assets/examples/examples.json for "
                         "the format")
        if cases.suffix.lower() != ".json":
            return _fail("BAD_EXTENSION",
                         f"test_cases_json must be a .json file, got: {cases.name}",
                         "create a JSON file with the case map and pass its path")
        test_cases_json = str(cases)
    if not test_cases_json:
        if not prompts:
            return _fail("MISSING_PROMPTS",
                         "provide prompts or test_cases_json",
                         'prompts are English captions in the training style, '
                         'e.g. ["An object walks forward."]')
        if not asset:
            return _fail("MISSING_ASSET",
                         "asset is required when prompts are given",
                         "use an assets/examples name (see list_examples), a "
                         "rig_preprocess output dir, or '<dataset>:<type>'")
    else:
        asset = asset or ""
    if asset:
        a = Path(asset)
        if not a.exists():
            a = ROOT / asset
        is_example = (ROOT / "assets" / "examples" / asset).is_dir()
        if not a.exists() and not is_example and ":" not in asset:
            examples = [d.name for d in
                        (ROOT / "assets" / "examples").iterdir() if d.is_dir()
                        ] if (ROOT / "assets" / "examples").is_dir() else []
            return _fail("ASSET_NOT_FOUND",
                         f"asset not found: {asset}",
                         "use one of: " + ", ".join(examples) +
                         "; or a rig_preprocess output dir like outputs/rig/"
                         "<name>; or '<dataset>:<object_type>'")
        if a.exists() and a.is_dir() and not (a / "cond.npy").is_file():
            return _fail("NOT_A_UNIMATE_ASSET",
                         f"{asset} exists but has no cond.npy",
                         "run preprocess_rig(input_path=..., output_dir=...) "
                         f"first, then pass {output_dir or 'outputs/rig/<name>'} "
                         "as the asset")
    out = output_dir or f"outputs/samples_mcp_{Path(asset).name}"
    args = [
        "-m", "unimate.inference.sample",
        "--exp_dir", exp_dir,
        "--output_dir", out,
        "--num_repetitions", str(max(1, int(num_repetitions))),
    ]
    if test_cases_json:
        args += ["--test_cases_json", test_cases_json]
    else:
        args += ["--asset", asset]
        for p in prompts:
            args += ["--prompt", p]
    if motion_edit:
        args += ["--motion_edit", "--keep_joints", keep_joints]
    if inbetween:
        args += ["--inbetween", "--keep_frames", keep_frames]
    if motion_expand:
        args += ["--motion_expand", "--expand_overlap", str(int(expand_overlap))]
    if cfg_scale is not None:
        args += ["--cfg_scale", str(cfg_scale)]
    if seed is not None:
        args += ["--seed", str(seed)]
    rc, so, se = _run(args, timeout=DEFAULT_TIMEOUT, tag="sample")
    result = {
        "returncode": rc,
        "output_dir": str(ROOT / out),
        "files": _pick(ROOT / out),
    }
    if rc != 0:
        result["stderr_tail"] = se[-4000:]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
@_safe
def get_manifest(output_dir: str) -> str:
    """Read manifest.json of a sampling output directory: which motion was
    generated for which asset/prompt, and the cond/character paths needed
    by animate_motion."""
    mf = ROOT / output_dir / "manifest.json"
    if not (ROOT / output_dir).is_dir():
        mf = ROOT / output_dir
    if not mf.is_file():
        return json.dumps({
            "error": "MANIFEST_NOT_FOUND",
            "message": f"manifest.json not found: {mf}",
            "hint": "output_dir must be a sampling run directory produced by "
                    "sample_animation (it contains manifest.json); check "
                    "list of files in the returned 'output_dir' field",
        }, ensure_ascii=False, indent=2)
    return mf.read_text(encoding="utf-8")


@mcp.tool()
@_safe
def animate_motion(
    anim_path: str,
    dataset_type: str = "general",
    char_path: Optional[str] = None,
    cond_path: Optional[str] = None,
    output_dir: Optional[str] = None,
    anim_mode: str = "fk",
) -> str:
    """Drive a rigged GLB with one generated motion (.npy) and export
    animated GLB + FBX via Blender (pip bpy, EEVEE-free path).

    anim_path: path to a <case>-rep_<r>-<i>.npy from a sampling run (or a
        samples dir + manifest entry name).
    char_path: the asset rig directory (GLB + cond) - defaults to what the
        manifest recorded for that motion.
    dataset_type: truebones | objaverse | mixamo | general.
    """
    anim = Path(anim_path)
    if not anim.exists():
        cand = ROOT / anim_path
        if cand.exists():
            anim = cand
        else:
            return json.dumps({
                "error": "FILE_NOT_FOUND",
                "message": f"anim_path does not exist: {anim_path}",
                "hint": "pass a .npy/.npz motion from a sampling run, e.g. "
                        "outputs/samples_custom/motions/<case>-rep_0-0.npy "
                        "(see get_manifest of the run to list valid names)",
            }, ensure_ascii=False, indent=2)
    if anim.suffix.lower() not in (".npy", ".npz"):
        return json.dumps({
            "error": "BAD_EXTENSION",
            "message": f"anim_path must be a .npy or .npz motion, got: {anim.name}",
            "hint": "run sample_animation first; motions land in "
                    "<output_dir>/motions/*.npy",
        }, ensure_ascii=False, indent=2)
    if dataset_type not in ("truebones", "objaverse", "mixamo", "general"):
        return json.dumps({
            "error": "BAD_DATASET_TYPE",
            "message": f"dataset_type must be truebones|objaverse|mixamo|general, got: {dataset_type}",
            "hint": "use 'general' for rig_preprocess outputs",
        }, ensure_ascii=False, indent=2)
    args = [
        "-m", "data_process.mesh_animation.animate_motion",
        "--dataset_type", dataset_type,
        "--anim_path", str(anim),
        "--anim_mode", anim_mode,
        "--output_dir", output_dir or "outputs/animated",
    ]
    if char_path:
        args += ["--char_path", char_path]
    if cond_path:
        args += ["--cond_path", cond_path]
    rc, so, se = _run(args, timeout=DEFAULT_TIMEOUT, tag="animate")
    result = {
        "returncode": rc,
        "output_dir": str(ROOT / (output_dir or "outputs/animated")),
        "stdout_tail": so[-2000:],
    }
    if rc != 0:
        result["stderr_tail"] = se[-4000:]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
@_safe
def animate_manifest(samples_dir: str, skip_invalid: bool = True) -> str:
    """List animatable jobs of a sampling run via its manifest: for every
    motion the rig/cond pair that drives it. Returns the job table that
    animate_motion consumes (anim_path, char_path, cond_path, dataset_type)."""
    d = Path(samples_dir)
    if not d.exists():
        d = ROOT / samples_dir
    if not d.is_dir():
        return json.dumps({
            "error": "DIR_NOT_FOUND",
            "message": f"samples_dir does not exist: {samples_dir}",
            "hint": "run sample_animation first; a manifest.json with its "
                    "mode subdir (or the dir itself) is expected",
        }, ensure_ascii=False, indent=2)
    if not list(d.rglob("manifest.json")):
        return json.dumps({
            "error": "NO_MANIFEST",
            "message": f"no manifest.json under: {d}",
            "hint": "point at a sampling output dir (or its inbetween/ "
                    "motion_edit/ motion_expand/ subdir) produced by "
                    "sample_animation",
        }, ensure_ascii=False, indent=2)
    args = ["-m", "data_process.mesh_animation.sample_manifest", samples_dir]
    if skip_invalid:
        args.append("--skip_invalid")
    rc, so, se = _run(args, timeout=600)
    if rc != 0:
        return json.dumps({
            "error": "MANIFEST_SCAN_FAILED",
            "message": "sample_manifest could not enumerate jobs",
            "stdout_tail": so[-1500:],
            "hint": "pass the sampling output dir itself (or exactly one "
                    "mode subdir); if several manifests exist under it, "
                    "pick one of the listed subdirs",
        }, ensure_ascii=False, indent=2)
    jobs = []
    for line in so.splitlines():
        parts = line.split("\t")
        if len(parts) == 4:
            jobs.append({
                "anim_path": parts[0], "char_path": parts[1],
                "cond_path": parts[2], "dataset_type": parts[3],
            })
    if not jobs:
        return json.dumps({
            "error": "NO_ANIMATABLE_JOBS",
            "message": "the manifest has no motions with a matching mesh",
            "hint": "SKIP-eligible motions (e.g. Truebones without a mesh) "
                    "are excluded by --skip_invalid; check get_manifest of "
                    "the run",
        }, ensure_ascii=False, indent=2)
    return json.dumps({"returncode": rc, "jobs": jobs},
                      ensure_ascii=False, indent=2)


@mcp.tool()
@_safe
def preprocess_rig(
    input_path: str,
    output_dir: str,
    face_right: Optional[str] = None,
    face_left: Optional[str] = None,
) -> str:
    """Turn a rigged GLB/glTF/FBX into a UniMate asset directory usable by
    sample_animation. Runs non-interactively (--no_review builds directly on
    the automatic rule-based annotation); pass face_right/face_left joint
    names to pin the facing pair, otherwise the automatic guess is used."""
    def _fail(code, message, hint):
        return json.dumps({"error": code, "message": message, "hint": hint},
                          ensure_ascii=False, indent=2)
    src = Path(input_path)
    if not src.exists():
        src = ROOT / input_path
    if not src.exists():
        return _fail("FILE_NOT_FOUND", f"input_path does not exist: {input_path}",
                     "pass an absolute path or one relative to the project "
                     "root; check the drive letter and spelling")
    if src.suffix.lower() not in (".glb", ".gltf", ".fbx"):
        suffix = src.suffix or "(none)"
        return _fail("BAD_EXTENSION",
                     f"unsupported format '{suffix}': {src.name}",
                     "export the model as GLB (recommended), glTF or FBX with "
                     "an armature/skeleton, then pass the new file; OBJ/STL/"
                     "images are not rigs")
    if not output_dir or output_dir.strip().lower() in ("outputs", "outputs/", "."):
        name = src.stem or "asset"
        output_dir = f"outputs/rig/{name}"
    args = [
        "-m", "data_process.rig_preprocess", "run",
        "--input", str(src),
        "--output_dir", output_dir,
        "--no_review",
    ]
    if face_right:
        args += ["--face_r", face_right]
    if face_left:
        args += ["--face_l", face_left]
    rc, so, se = _run(args, timeout=DEFAULT_TIMEOUT, tag="rig")
    result = {
        "returncode": rc,
        "output_dir": str(ROOT / output_dir),
        "stdout_tail": so[-2000:],
    }
    if rc != 0:
        result["stderr_tail"] = se[-4000:]
        result["hint"] = ("common causes: no armature/skeleton in the file, "
                          "unsupported rig layout, or a locked output dir; "
                          "re-run with face_right/face_left if the facing "
                          "pair is ambiguous")
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
@_safe
def download_checkpoint(
    repo_id: str = "Linzhan/UniMate",
    include: Optional[List[str]] = None,
    repo_type: str = "model",
) -> str:
    """Download model files via the pycurl downloader (stable, resumable).
    include: glob filters, e.g. 'unimate_uniml3d_f60_v3/*' - without them
    the whole repository downloads."""
    if repo_type not in ("model", "dataset", "space"):
        return json.dumps({
            "error": "BAD_REPO_TYPE",
            "message": f"repo_type must be model|dataset|space, got: {repo_type}",
            "hint": "Linzhan/UniMate checkpoints are repo_type='model'",
        }, ensure_ascii=False, indent=2)
    if "/" not in repo_id:
        return json.dumps({
            "error": "BAD_REPO_ID",
            "message": f"repo_id must look like 'owner/name', got: {repo_id}",
            "hint": "e.g. Linzhan/UniMate",
        }, ensure_ascii=False, indent=2)
    args = [
        "tools/_hf_pycurl_download.py", repo_id, "outputs",
        "--repo-type", repo_type,
    ]
    for pat in (include or []):
        args += ["--include", pat]
    rc, so, se = _run(args, timeout=7200)
    return json.dumps({"returncode": rc,
                       "stdout_tail": so[-2000:],
                       "stderr_tail": se[-2000:] if rc else ""},
                      ensure_ascii=False, indent=2)


@mcp.tool()
@_safe
def train(config: str = "configs/uniml3d_60frames_graph_adaln.json") -> str:
    """(Advanced) Train UniMate on a prepared dataset via accelerate. Requires
    the UniML3D clips under dataset/features/<dataset>/ - out of the
    inference-only workflow."""
    rc, so, se = _run([
        "-m", "accelerate.commands.launch", "--num_processes", "1",
        "-m", "unimate.training.train", "--config", config,
    ], timeout=7200)
    return json.dumps({"returncode": rc,
                       "stdout_tail": so[-2000:],
                       "stderr_tail": se[-2000:] if rc else ""},
                      ensure_ascii=False, indent=2)


@mcp.tool()
@_safe
def precompute_text_emb(config: str = "configs/uniml3d_60frames_graph_adaln.json") -> str:
    """(Advanced) Precompute T5 caption/joint-name embeddings beside the
    dataset features for a training config."""
    rc, so, se = _run(["-m", "unimate.tools.precompute_text_emb", "--config", config],
                      timeout=3600)
    return json.dumps({"returncode": rc,
                       "stdout_tail": so[-2000:],
                       "stderr_tail": se[-2000:] if rc else ""},
                      ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# Entry
# --------------------------------------------------------------------------- #
def serve() -> None:
    mcp.run(transport="stdio")


def selftest() -> int:
    import asyncio
    tools = asyncio.run(mcp.list_tools())
    print(f"[UNIMATE-MCP] {len(tools)} tools registered:", file=sys.stderr)
    for t in tools:
        print(f"[UNIMATE-MCP]   {t.name}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    serve()
