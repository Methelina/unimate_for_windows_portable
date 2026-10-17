<h1 align="center">UniMate (Windows Portable Fork)</h1>

<p align="center"><b>Animate any rigged 3D model from a text prompt — no rigging work, no retargeting, no training</b></p>

<p align="center">
  <a href="https://arxiv.org/abs/2609.05415"><img alt="arXiv" src="https://img.shields.io/badge/arXiv-2609.05415-B31B1B?style=for-the-badge&logo=arxiv&logoColor=white"></a>
  <a href="https://huggingface.co/Linzhan/UniMate"><img alt="Hugging Face Checkpoints" src="https://img.shields.io/badge/Checkpoints-FF9D00?style=for-the-badge&logo=huggingface&logoColor=000000"></a>
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

Run `run_unimate.ps1` (right-click → Run with PowerShell). It offers a numbered menu:

- **1 — Sample motion on your asset.** It asks for three things: which model to animate (press Enter for the built-in eagle example), what it should do (the sentence), and where to save. Results appear in `outputs\`.
- **2 — Batch of scenes** from a prepared JSON list (see `assets\examples\examples.json`).
- **4 — Download the model** (needed once; ~1.1 GB).
- **7 — Built-in Python shell** for advanced use.

Before the menu, the launcher automatically picks the GPU with the most free memory and isolates all caches into the project folder — nothing leaks into `C:\Users\...`.

### A typical first session

```
run_unimate.ps1
  → 4  (download the model, once)
  → 1  (asset: assets/examples/eagle, prompt: An object flaps its wings.)
```

Open `outputs\samples_custom\animations\*.mp4` — if the motion fits your needs, one more command puts it on the mesh as GLB + FBX (menu 6, or the animate line below).

### Using your own model

Export your rigged character to GLB (Blender, Unity, Maya all export it), then run it through the rig preparer once:

```
python -m mcp_unimate rig C:\models\my_hero.glb outputs/rig/my_hero
```

It reads the bone structure, names the joints automatically and builds the asset. After that, point the sampler at `outputs/rig/my_hero` exactly like the examples.

### Writing prompts that work

Start with **"An object"** and describe **one motion**:

| Works well | Works poorly |
|---|---|
| An object walks forward. | A brave knight walks to the castle. |
| An object flaps its wings. | A golden eagle soars in the sunset. |
| An object attacks forward. | Fight me! |

Generate 3–5 variants (`--num_repetitions 5`) and pick the best take. If the model ignores your prompt, raise `--cfg` to 5–7; if motions look twitchy, lower it to 2.

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

The datasets remain governed by the licenses of their original sources: the [Mixamo](https://www.mixamo.com/) assets by Adobe's Mixamo terms of use, the [Objaverse-XL](https://objaverse.allenai.org/) assets by the license attached to each original object, and the Truebones ZOO motions by [Truebones](https://truebones.com)' commercial license. Please review and comply with the respective source licenses before using the data.

## 🤝 Acknowledgement

We thank the authors of [AnyTop](https://github.com/Anytop2025/Anytop) for open-sourcing their codebase, on which parts of this repository build. We thank [@chutch1122](https://github.com/chutch1122) for suggesting several captions per clip, which led to the normal, generic and detailed captions of UniML3D.
