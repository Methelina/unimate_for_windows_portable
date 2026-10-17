# -*- coding: utf-8 -*-
"""UniMate MCP bridge - command line front-end.

Same operations as the MCP tools, callable directly from the terminal:

    python -m mcp_unimate serve                          # stdio MCP server
    python -m mcp_unimate examples
    python -m mcp_unimate checkpoints
    python -m mcp_unimate sample <asset> "prompt 1" "prompt 2" ^
        [--reps 3] [--cfg 5] [--seed 7] [--exp outputs/...] [--out dir]
    python -m mcp_unimate manifest <samples_dir>
    python -m mcp_unimate jobs <samples_dir>
    python -m mcp_unimate animate <anim.npy> [--char dir] [--type general]
    python -m mcp_unimate rig <input.glb> <out_dir> [--face-r J --face-l J]
    python -m mcp_unimate download [glob ...]

FModel.Cli/mcp_unimate/cli.py
Version:     1.0.0
Author:      Soror L.'.L.'.
Updated:     2026-10-18

Patch Notes v1.0.0 (Soror L.'.L.'.):
  [+] Initial release.
"""

import argparse
import json
import sys

from . import server


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="mcp_unimate",
                                 description="UniMate portable CLI / MCP bridge")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("serve", help="run the FastMCP stdio server")
    sub.add_parser("examples", help="list built-in example assets")
    sub.add_parser("checkpoints", help="list usable checkpoints")

    p_sample = sub.add_parser("sample", help="text-to-animation sampling")
    p_sample.add_argument("asset")
    p_sample.add_argument("prompts", nargs="+")
    p_sample.add_argument("--reps", type=int, default=1)
    p_sample.add_argument("--cfg", type=float, default=None)
    p_sample.add_argument("--seed", type=int, default=None)
    p_sample.add_argument("--exp", default=server.DEFAULT_EXP)
    p_sample.add_argument("--out", default=None)

    p_man = sub.add_parser("manifest", help="read a run's manifest.json")
    p_man.add_argument("output_dir")

    p_jobs = sub.add_parser("jobs", help="list animatable manifest jobs")
    p_jobs.add_argument("samples_dir")

    p_anim = sub.add_parser("animate", help="drive a GLB with a motion (.npy)")
    p_anim.add_argument("anim_path")
    p_anim.add_argument("--char", default=None)
    p_anim.add_argument("--cond", default=None)
    p_anim.add_argument("--type", dest="dtype", default="general")
    p_anim.add_argument("--out", default=None)
    p_anim.add_argument("--mode", default="fk", choices=["fk", "ik"])

    p_rig = sub.add_parser("rig", help="preprocess a rigged GLB/FBX")
    p_rig.add_argument("input_path")
    p_rig.add_argument("output_dir")
    p_rig.add_argument("--face-r", default=None)
    p_rig.add_argument("--face-l", default=None)

    p_dl = sub.add_parser("download", help="download checkpoint files (pycurl)")
    p_dl.add_argument("include", nargs="*")
    p_dl.add_argument("--repo", default="Linzhan/UniMate")
    p_dl.add_argument("--repo-type", default="model")

    args = ap.parse_args(argv)

    if args.cmd == "serve":
        server.serve()
        return 0
    if args.cmd == "examples":
        print(server.list_examples())
        return 0
    if args.cmd == "checkpoints":
        print(server.list_checkpoints())
        return 0
    if args.cmd == "sample":
        print(server.sample_animation(
            asset=args.asset, prompts=args.prompts, num_repetitions=args.reps,
            cfg_scale=args.cfg, seed=args.seed, exp_dir=args.exp,
            output_dir=args.out))
        return 0
    if args.cmd == "manifest":
        print(server.get_manifest(args.output_dir))
        return 0
    if args.cmd == "jobs":
        print(server.animate_manifest(args.samples_dir))
        return 0
    if args.cmd == "animate":
        print(server.animate_motion(
            anim_path=args.anim_path, dataset_type=args.dtype,
            char_path=args.char, cond_path=args.cond,
            output_dir=args.out, anim_mode=args.mode))
        return 0
    if args.cmd == "rig":
        print(server.preprocess_rig(
            input_path=args.input_path, output_dir=args.output_dir,
            face_right=args.face_r, face_left=args.face_l))
        return 0
    if args.cmd == "download":
        print(server.download_checkpoint(
            repo_id=args.repo, include=args.include or None,
            repo_type=args.repo_type))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
