# UniMate Windows-Port Audit — Consolidated Report

Author:      Soror L.'.L.'.
Updated:     2026-10-17
Method:      1 explore subagent per file (14 files, pairs of 2) + repo-wide
             grep sweeps for POSIX-only patterns.

## Verdicts

| File | Verdict |
|------|---------|
| data_process/utils/blender_render.py | FIXED (v4.0.1, pre-audit): top-level `import fcntl` replaced by fcntl/msvcrt dispatch + fallback warning |
| data_process/utils/blender_export.py | CLEAN |
| data_process/utils/blender_rig.py | CLEAN |
| data_process/motion_rendering/render_tpose.py | CLEAN |
| data_process/motion_rendering/render_mixamo.py | CLEAN |
| data_process/motion_rendering/render_objaverse.py | CLEAN |
| data_process/motion_rendering/render_truebones.py | CLEAN |
| data_process/motion_rendering/render_general.py | CLEAN (thin dispatcher over render_objaverse) |
| data_process/vlm_caption/caption_motion.py | CLEAN |
| data_process/vlm_caption/backends.py | CLEAN |
| data_process/feature_extraction/extract_features.py | CLEAN (mp.Pool under `__main__` guard L1000; top-level picklable worker L753; default start-method note only) |
| data_process/rig_preprocess/pipeline.py | CLEAN |
| unimate/inference/sample.py | CLEAN (Windows-safe filenames, os.replace atomic rename) |
| unimate/training/train.py | CLEAN (`__main__` guard L536 for accelerate spawn) |
| unimate/tools/precompute_text_emb.py | CLEAN |

## Grep sweeps (repo-wide)

- `os.symlink | Path.symlink | readlink` — 0 hits in .py
- `subprocess.(run|call|Popen|...)` — 0 hits in .py
- `import fcntl` — only blender_render.py (fixed)
- `SIGALRM` — data_process/joint_annotation/llm.py, guarded by
  `hasattr(signal, "SIGALRM")` at L333 (graceful no-op on Windows)
- `/tmp/` hardcode — blender_render.py `_gpu_lock_path` only, with
  tempfile.gettempdir() fallback (harmless)
- `.sh` wrappers — not executable on Windows; key entry points duplicated
  in run_unimate.ps1 (sample/train/download/precompute/animate)

## Notes (non-breaking)

- blender_export.py L1266: pid-suffixed temp + os.replace — on Windows
  os.replace can fail if target held open by another process (runtime
  caveat only).
- extract_features.py: relies on default mp start method (spawn on
  Windows) — works, implicit.
- SLURM references are comments only; no env reads anywhere audited.

## Conclusion

Python source is fully Windows-portable. Remaining gates are
installation (Phase C) and e2e sampling (Phase D) per roadmap.md.
