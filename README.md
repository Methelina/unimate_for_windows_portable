<h1 align="center">UniMate (Windows Portable Fork)</h1>

<p align="center"><b>Animate any rigged 3D model from a text prompt — no rigging work, no retargeting, no training</b></p>

<p align="center">
  <a href="https://arxiv.org/abs/2609.05415"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2609.05415-B31B1B?style=for-the-badge&logo=arxiv&logoColor=white"></a>
  <a href="https://huggingface.co/Linzhan/UniMate"><img alt="Hugging Face Checkpoints" src="https://img.shields.io/badge/Checkpoints-FF9D00?style=for-the-badge&logo=huggingface&logoColor=000000"></a>
</p>

<p align="center">
  <b>Windows portable build & Linux→Windows adaptation:</b>
  <a href="https://github.com/Methelina">Methelina</a> aka <b>Soror L.'.L.'.</b>
  · English documentation · Русская версия: <a href="README.ru.md">README.ru.md</a>
</p>

<div align="center">
    <img src="assets/teaser.png" alt="UniMate teaser" width="100%">
</div>

---

## 🎬 What is UniMate?

UniMate is an AI model that **creates skeletal animation from a text description**. You give it a rigged 3D model — a character, an animal, a robot, any creature — and a sentence like *"An object flaps its wings."* It produces a skeletal motion, so your model walks, runs, dances, attacks or swims.

What makes it different from conventional animation tools:

- **No retargeting.** Traditional pipelines need a retarget pass (or a full re-rig) for every new character. UniMate was trained on 7,430 different skeletons — bipeds, quadrupeds, birds, fish, insects, snakes, even articulated objects — and drives an unseen rig directly, from its bone structure alone.
- **No animation skills required.** The "input" is a plain English sentence. Want a walk cycle? *"An object walks forward."* A combat move? *"An object attacks forward."*
- **Real-time generation.** A motion takes seconds on a single consumer GPU, not hours in a DCC package.
- **Three extra modes for free** (same model, no extra training): fill the gap between keyframes (**in-betweening**), keep a chosen body part fixed and re-animate the rest under a new prompt (**editing**), or chain several prompts into one long take (**expansion**).

**Who is this for:** 3D artists who need a base motion fast, game developers prototyping creature movement, previz and machinima, VTubers and modders — anyone who has a rigged model and needs it to move.

**What you get on disk:** MP4 preview renders you can watch immediately, raw skeletal motion (`.npy`), and — with one more command — your model **animated and exported as GLB + FBX**, ready to drop into Blender, Unity, Unreal or Godot.

## ✅ What you need

| Requirement | Details |
|---|---|
| Windows 10/11 x64 | everything is portable — no admin rights, no installs into the system |
| NVIDIA GPU | 6 GB VRAM is comfortable; 4 GB works with shorter batches |
| ~15 GB disk space | environment (~8 GB) + model checkpoint (~1.1 GB) + working room |
| Internet | once, for the first-time download of the environment and the model |
| A rigged model | GLB / glTF / FBX with an armature — skinned mesh optional |

You do **not** need: Python, conda, git, a DCC package, or any programming knowledge.

## ⚠️ Honest limitations

- The model is an early research step: **many motions and skeletons still fail**. A giraffe breakdancing will not work; a wolf trotting will.
- Prompts must be short and generic — *"An object flaps its wings."*, not *"A majestic golden eagle soars majestically through the sunset sky."* The closer to the training caption style, the better the result.
- The animation is FK on the given skeleton: no facial animation, no fingers choreography, no physics interaction.
- The released model weights are **CC BY-NC 4.0 — non-commercial use**. The code is MIT.

## 🛠️ Installation (two steps, once)

1. Download or clone this folder to any drive.
2. Right-click `install_unimate.ps1` → **Run with PowerShell** (or run `pwsh -File install_unimate.ps1`). Wait — the first run downloads the environment and takes the longest.

That is everything. The installer builds a fully isolated environment **inside the project folder** (Python, PyTorch with CUDA, Blender-as-a-library) — nothing is installed into Windows itself, and the folder can be moved to another drive afterwards. Re-running the installer is safe.

## 🎮 How to use it

### The easy way: the launcher menu

Run `run_unimate.ps1` (right-click → Run with PowerShell). You get a numbered menu in three groups. In almost every item, pressing **Enter** accepts a sensible default.

---

**1 — Generate motion** (your asset + a text prompt). The main item. It asks for: the asset (Enter = built-in eagle `assets/examples/eagle`; this also accepts a rig prepared by item 6, e.g. `outputs/rig/my_hero`), an English prompt, the number of variants, and prompt adherence.
> Example fill-in: asset `assets/examples/shark`, prompt `An object swims and turns around.`, variants `3`, adherence `3`.
> Result: previews in `outputs\samples_custom\animations\*.mp4`, motions in `motions\*.npy`. Afterwards it asks "Animate the mesh now? (y/N)" — answer `y` to put the motions on the model right away and save GLB + FBX.

**2 — Batch generation** (several scenes from a JSON list). Takes a scene list of "asset + prompt" from a file. A ready example ships as `assets\examples\examples.json` (Garfield dancing, a Gundam kicking, Baymax walking…).
> Example fill-in: path `assets\examples\examples.json`, everything else — Enter.
> Your own file is a JSON list like `[{"asset": "outputs/rig/my_hero", "id": "hero-walk", "prompt": "An object walks forward."}]`.

**3 — Motion editing.** Keeps the chosen joints at their current motion and regenerates everything else under a new prompt. Needs a JSON naming **real clips** (clips come from dataset assets, or from a rig prepared with saved clips) and a joint list.
> Example fill-in: `cases.json` containing `{"mixamo-Cocky_Head_Turn-000": "An object walks forward."}`, joints `Neck,Head`.
> Result: `outputs\samples_edit\motion_edit\` — each result sits next to its source clip for comparison.

**4 — In-betweening.** Keeps chosen keyframes and fills the motion between them. Frame indices are given; negative indices count from the end.
> Example fill-in: `cases.json` like `{"mixamo-Air_Squat-000": "An object squats and then stands up."}`, frames `0,-1` (first and last pose — everything between is generated).
> Result: `outputs\samples_inbetween\inbetween\`.

**5 — Motion expansion** (one long chained take). Several prompts become one continuous motion: the first segment is generated freely, every next one starts from the previous tail.
> Example fill-in: `cases.json` like `{"mixamo-sequence": ["An object stands up.", "An object walks forward.", "An object turns around in place."]}`, overlap `10` frames.
> Result: `outputs\samples_expand\motion_expand\`.

**6 — Prepare own rig.** Turns your GLB/glTF/FBX (any of them, animations optional) into a UniMate asset, once: it reads the skeleton, names the joints automatically and builds `cond.npy` plus the canonical mesh.
> Example fill-in: input `C:\models\my_hero.glb`, output — Enter (it fills `outputs/rig/my_hero` itself).
> Afterwards use `outputs/rig/my_hero` as the asset in items 1–5. To control the joint labels yourself, run without `--no_review` from the command line (see `data_process/rig_preprocess/README.md`).

**7 — Animate samples** (motions → GLB + FBX). Takes a generation output directory and drives every motion through its asset's mesh via Blender: animated GLB and FBX come out, ready for Blender / Unity / Unreal / Godot.
> Example fill-in: `outputs\samples_custom`.
> Result: `outputs\samples_custom\animated\<name>.glb` and `.fbx`. Incompatible motions are skipped with a message.

**8 — Download checkpoint.** Once, fetches the inference set (~1.1 GB): config, normalization statistics, latest checkpoint. Resumable — a dropped connection does not start over.

**9 — Train** and **10 — Precompute text embeddings** are for researchers (they need the UniML3D dataset; not required for inference). **11 — Python shell** is the portable environment's interactive shell for manual work.

Before the menu, the launcher automatically picks the GPU with the most free memory and isolates all caches into the project folder — nothing leaks into `C:\Users\...`.

### A typical first session

```
run_unimate.ps1
  → 8  (download the model, once)
  → 1  (asset: Enter — the eagle, prompt: An object flaps its wings., variants 3)
  → answer "y" to "Animate the mesh now?"
  → open outputs\samples_custom\animations\*.mp4 and outputs\samples_custom\animated\*.glb
```

### Writing prompts that work

Start with **"An object"** and describe **one motion**:

| Works well | Works poorly |
|---|---|
| An object walks forward. | A brave knight walks to the castle. |
| An object flaps its wings. | A golden eagle soars in the sunset. |
| An object attacks forward. | Fight me! |

Generate 3–5 variants and pick the best take. If the model ignores your prompt, raise adherence to 5–7; if motions look twitchy, lower it to 2.

## 🤖 For AI agents and power users: FastMCP + CLI

The whole toolkit is also exposed as a FastMCP server (`mcp_unimate/server.py`) — register it once in your MCP client (Kilo, Claude Desktop, …) and drive UniMate conversationally:

```json
"unimate": {
  "type": "local",
  "command": [
    "K:\\work\\AI\\UniMate\\unimate_env\\Scripts\\python.exe",
    "-m", "mcp_unimate.server"
  ],
  "enabled": true,
  "timeout": 3600000
}
```

Tools: `sample_animation` (text → motion on any rig), `animate_motion` (motion → animated GLB/FBX via Blender), `preprocess_rig` (prepare your GLB/FBX), `animate_manifest`, `list_examples`, `list_checkpoints`, `download_checkpoint`. The same operations work from the terminal: `python -m mcp_unimate sample assets/examples/shark "An object swims and turns around." --reps 3`.

## 📦 Data & Training (out of scope for this fork)

This build targets **inference only**: a released checkpoint plus your own rigged asset. The UniML3D dataset (~88 GB), the pipeline that builds it, and model training are not part of the portable workflow.

For those parts, the code and documentation remain in place: the data-processing pipeline is documented in [`data_process/README.md`](data_process/README.md) (download → export → rendering → captioning → joint annotation → feature extraction → animation), and training lives in [`unimate/training/`](unimate/training/) — launched as `accelerate launch -m unimate.training.train --config <config>` with the JSON configs in [`configs/`](configs/). Text-embedding precomputation for training runs: `python -m unimate.tools.precompute_text_emb --config <config>`.

## 📌 Note

UniMate is an **early step** toward text-to-animation for any skeleton, and many motions and skeletons **still fail**. If you run into failure cases, please open an issue or contact the original authors; they help us improve.

## 📝 Citation

If you find UniMate useful in your research, please consider citing our work:

```bibtex
@article{mou2026unimate,
  title   = {UniMate: One Unified Model to Animate Diverse Skeletons},
  author  = {Mou, Linzhan and Lei, Jiahui and Dou, Zhiyang and Cai, Chenyue and Song, Chaoyue and Finkelstein, Adam and Rusinkiewicz, Szymon},
  journal = {arXiv preprint arXiv:2609.05415},
  year    = {2026}
}
```

## ⚖️ License

The code in this repository is released under the [MIT License](LICENSE). The released checkpoints are under [CC BY-NC 4.0](https://huggingface.co/Linzhan/UniMate/blob/main/LICENSE); see the [model card](https://huggingface.co/Linzhan/UniMate) for details.

The Windows portable build, the launcher/installer tooling, the FastMCP bridge and the Linux→Windows adaptation of this fork are by **Methelina aka Soror L.'.L.'.'**.

The datasets remain governed by the licenses of their original sources: the [Mixamo](https://www.mixamo.com/) assets by Adobe's Mixamo terms of use, the [Objaverse-XL](https://objaverse.allenai.org/) assets by the license attached to each original object, and the Truebones ZOO motions by [Truebones](https://truebones.com)' commercial license. Please review and comply with the respective source licenses before using the data.

## 🤝 Acknowledgement

We thank the authors of [AnyTop](https://github.com/Anytop2025/Anytop) for open-sourcing their codebase, on which parts of this repository build. We thank [@chutch1122](https://github.com/chutch1122) for suggesting several captions per clip, which led to the normal, generic and detailed captions of UniML3D.
