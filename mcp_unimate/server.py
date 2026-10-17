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

import json
import os
import subprocess
import sys
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


def _run(args: List[str], timeout: int = DEFAULT_TIMEOUT):
    """Run a unimate_env python module; returns (rc, stdout, stderr)."""
    proc = subprocess.run(
        [str(PYEXE), *args], cwd=str(ROOT), env=_env(),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout,
    )
    return proc.returncode, proc.stdout, proc.stderr


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
    modes = [m for m in (motion_edit, inbetween, motion_expand) if m]
    if len(modes) > 1:
        return json.dumps({"error":
            "motion_edit, inbetween and motion_expand are mutually exclusive"})
    if modes and not test_cases_json:
        return json.dumps({"error":
            "motion_edit / inbetween / motion_expand require test_cases_json"})
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
        if not prompts:
            return json.dumps({"error": "provide prompts or test_cases_json"})
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
    rc, so, se = _run(args, timeout=DEFAULT_TIMEOUT)
    result = {
        "returncode": rc,
        "output_dir": str(ROOT / out),
        "files": _pick(ROOT / out),
    }
    if rc != 0:
        result["stderr_tail"] = se[-4000:]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def get_manifest(output_dir: str) -> str:
    """Read manifest.json of a sampling output directory: which motion was
    generated for which asset/prompt, and the cond/character paths needed
    by animate_motion."""
    mf = ROOT / output_dir / "manifest.json"
    if not (ROOT / output_dir).is_dir():
        mf = ROOT / output_dir
    if not mf.is_file():
        return json.dumps({"error": f"manifest not found: {mf}"})
    return mf.read_text(encoding="utf-8")


@mcp.tool()
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
    args = [
        "-m", "data_process.mesh_animation.animate_motion",
        "--dataset_type", dataset_type,
        "--anim_path", anim_path,
        "--anim_mode", anim_mode,
        "--output_dir", output_dir or "outputs/animated",
    ]
    if char_path:
        args += ["--char_path", char_path]
    if cond_path:
        args += ["--cond_path", cond_path]
    rc, so, se = _run(args, timeout=DEFAULT_TIMEOUT)
    result = {
        "returncode": rc,
        "output_dir": str(ROOT / (output_dir or "outputs/animated")),
        "stdout_tail": so[-2000:],
    }
    if rc != 0:
        result["stderr_tail"] = se[-4000:]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def animate_manifest(samples_dir: str, skip_invalid: bool = True) -> str:
    """List animatable jobs of a sampling run via its manifest: for every
    motion the rig/cond pair that drives it. Returns the job table that
    animate_motion consumes (anim_path, char_path, cond_path, dataset_type)."""
    args = ["-m", "data_process.mesh_animation.sample_manifest", samples_dir]
    if skip_invalid:
        args.append("--skip_invalid")
    rc, so, se = _run(args, timeout=600)
    jobs = []
    for line in so.splitlines():
        parts = line.split("\t")
        if len(parts) == 4:
            jobs.append({
                "anim_path": parts[0], "char_path": parts[1],
                "cond_path": parts[2], "dataset_type": parts[3],
            })
    return json.dumps({"returncode": rc, "jobs": jobs,
                       "stderr_tail": se[-2000:] if rc else ""},
                      ensure_ascii=False, indent=2)


@mcp.tool()
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
    args = [
        "-m", "data_process.rig_preprocess", "run",
        "--input", input_path,
        "--output_dir", output_dir,
        "--no_review",
    ]
    if face_right:
        args += ["--face_r", face_right]
    if face_left:
        args += ["--face_l", face_left]
    proc = subprocess.run(
        [str(PYEXE), *args],
        cwd=str(ROOT), env=_env(), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=DEFAULT_TIMEOUT,
    )
    result = {
        "returncode": proc.returncode,
        "output_dir": str(ROOT / output_dir),
        "stdout_tail": proc.stdout[-2000:],
    }
    if proc.returncode != 0:
        result["stderr_tail"] = proc.stderr[-4000:]
    return json.dumps(result, ensure_ascii=False, indent=2)


@mcp.tool()
def download_checkpoint(
    repo_id: str = "Linzhan/UniMate",
    include: Optional[List[str]] = None,
    repo_type: str = "model",
) -> str:
    """Download model files via the pycurl downloader (stable, resumable).
    include: glob filters, e.g. 'unimate_uniml3d_f60_v3/*' - without them
    the whole repository downloads."""
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
