<h1 align="center">UniMate (Windows Portable Fork)</h1>

<p align="center"><b>Единая модель для анимации произвольных скелетов — портативная сборка под Windows</b></p>

<p align="center">Русская версия оригинального README: <a href="README.md">README.md (English)</a></p>

Автор сопровождения порта: Soror L.'.L.'.
Updated: 2026-10-18

---

## 🪟 Портативная установка (Windows, без conda)

Вся среда живёт внутри папки проекта и переносится на любой диск целиком: в `C:\Users\...` и `%LOCALAPPDATA%` ничего не пишется — все кэши (uv, HuggingFace, matplotlib, временные файлы) лежат в `.cache\` проекта.

Установка и запуск:

```powershell
pwsh -File install_unimate.ps1   # один раз: uv-venv unimate_env (Python 3.10), PyTorch 2.5.1+cu124, bpy 4.0.0, requirements
pwsh -File run_unimate.ps1       # лаунчер с меню
```

Установщик: скачивает `uv` локально, ставит uv-managed Python 3.10, пиннит `setuptools<81` (требуется для сборки git-пакета `Motion` с `--no-build-isolation`), ставит torch/torchvision cu124 с PyTorch-индекса и `bpy==4.0.0` с индекса Blender (на PyPI cp310-колёс нет), затем ставит `requirements.txt`. Установка идемпотентна: готовый валидный venv не пересоздаётся.

Лаунчер `run_unimate.ps1` (меню): сэмплинг по ассету и промпту, сэмплинг по `test_cases_json`, тренировка через accelerate, скачивание чекпоинта, предвычисление текстовых эмбеддингов, анимация мешей по манифесту, портативный python-shell. Перед запуском задаёт полную изоляцию переменных среды и автоматически выбирает GPU с максимумом свободной памяти.

Конфигурация установщика — `settings_unimate.yaml` (имена env, версии torch/bpy/uv, индексы).

## 🤖 FastMCP + CLI (`mcp_unimate/`)

UniMate доступен как MCP-сервер и как CLI с одними и теми же операциями. Каждый вызов выполняется в изолированном subprocess портативного python — падение инструмента не влияет на сервер.

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

Инструменты MCP: `list_examples` (встроенные ассеты eagle/shark/unitree_go2), `list_checkpoints`, `sample_animation` (текст→анимация на скелете любого рига: имя примера, выход `rig_preprocess`, каталог с `cond.npy` или `<dataset>:<object_type>`; параметры reps/cfg_scale/seed), `get_manifest`, `animate_manifest`, `animate_motion` (прогон моушена `.npy` по GLB-мешу → анимированные GLB+FBX через pip bpy), `preprocess_rig` (подготовка произвольного rigged GLB/glTF/FBX без интерактива), `download_checkpoint` (устойчивая докачиваемая загрузка через pycurl с glob-фильтрами).

CLI: `python -m mcp_unimate serve | examples | checkpoints | sample <asset> "промпт" [--reps N --cfg X --seed S] | manifest <dir> | jobs <dir> | animate <anim.npy> [--char dir] | rig <input.glb> <out_dir> | download`.

## ⬇️ Скачивание чекпоинтов (только нужное)

Вместо нестабильного `hf.exe` — pycurl-загрузчик `scripts/_hf_pycurl_download.py`: список файлов из tree-API Hub'а, докачка `.part` через Range, повтор при обрыве, прогресс через tqdm (по-файловый бар + общий). Фильтры `--include`/`--exclude` позволяют качать ровно то, что нужно для инференса — например, один чекпоинт вместо всех:

```powershell
.\unimate_env\Scripts\python.exe scripts\_hf_pycurl_download.py Linzhan/UniMate outputs `
  --include "unimate_uniml3d_f60_v3/config.json" `
  --include "unimate_uniml3d_f60_v3/dataset_stats.npy" `
  --include "unimate_uniml3d_f60_v3/checkpoints/checkpoint_step_150000.pt"
```

Для инференса на собственных ассетах датасет UniML3D (~88 ГБ) не нужен.

## 🎬 Быстрый старт (инференс)

```powershell
python -m unimate.inference.sample --exp_dir outputs/unimate_uniml3d_f60_v3 `
  --asset assets/examples/eagle --prompt "An object flaps its wings." `
  --num_repetitions 3 --output_dir outputs/samples_eagle
```

Результат: `outputs/samples_eagle/animations/*.mp4` (превью-рендеры), `motions/*.npy` (моушены), `manifest.json`. Промпты пишутся в стиле обучающих подписей: начинать с «An object» и описывать одно движение, а не персонажа.

Проверено на этой сборке: сэмплинг по встроенным ассетам (орёл — «An object flaps its wings.», акула — «An object swims and turns around.»), CUDA на torch 2.5.1+cu124, bpy 4.0.0 импортируется, оба smoke-теста entry points зелёные.

## 🛠️ Среда (оригинальный способ, Linux/conda)

Все компоненты используют одно conda-окружение из [`requirements.txt`](requirements.txt):

```bash
conda create -n unimate python=3.10 -y
conda activate unimate
pip install "setuptools<81"
pip install -r requirements.txt --no-build-isolation
```

## 📦 Данные и тренировка (вне рамок форка)

Эта сборка — только инференс: чекпоинт + собственный риг. Датасет UniML3D (~88 ГБ), пайплайн его построения и тренировка в неё не входят. Для исследования этих частей см. [`data_process/README.md`](data_process/README.md) (пайплайн: загрузка → экспорт → рендеринг → подписи → разметка суставов → извлечение признаков → анимация) и код `unimate/training/` (запуск: `accelerate launch -m unimate.training.train --config <config>`; конфиги в [`configs/`](configs/)). Предвычисление текстовых эмбеддингов для тренировочных прогонов: `python -m unimate.tools.precompute_text_emb --config <config>`.

## 📌 Примечания

Релизованный UniML3D прошёл повторную обработку подписей — они могут не совпадать с показанными на проектной странице. UniMate — ранний шаг к text-to-animation для произвольных скелетов: многие движения и скелеты всё ещё не удаются; случаи отказов помогают улучшению (issues/контакты авторов оригинала).

## 🎬 Приложения (те же веса, три задачи)

Та же обученная модель без дополнительного обучения решает ещё три задачи — замещающий сэмплинг: часть движения зафиксирована на известном сигнале, flow ODE дорисовывает остальное на каждом шаге.

- **Motion in-betweening** — удержание выбранных ключевых кадров, генерация переходов между ними: `--inbetween`, кадры задаются индексами (`"0,-1"` — всё между первой и последней позой).
- **Text-guided motion editing** — удержание выбранных суставов на их ground-truth движении, перегенерация остального под новым промптом: `--motion_edit --keep_joints "Neck,Head"`.
- **Motion expansion** — сшивка нескольких промптов в одно длинное движение: `--motion_expand`, перекрытие сегментов задаёт `--expand_overlap`.

Каждый режим пишет в свой подкаталог `--output_dir` (`inbetween/`, `motion_edit/`, `motion_expand/`) рядом с JSON-описанием наложенного ограничения; для редактирования и in-betweening ключи тест-кейсов должны называть реальные клипы (`<object_type>-<clip_id>`), а все три режима требуют `--cfg_scale > 1.0` и взаимоисключимы.

## 📝 Цитирование

```bibtex
@article{mou2026unimate,
  title   = {UniMate: One Unified Model to Animate Diverse Skeletons},
  author  = {Mou, Linzhan and Lei, Jiahui and Dou, Zhiyang and Cai, Chenyue and Song, Chaoyue and Finkelstein, Adam and Rusinkiewicz, Szymon},
  journal = {arXiv preprint arXiv:2609.05415},
  year    = {2026}
}
```

## ⚖️ Лицензия

Код репозитория — MIT License ([LICENSE](LICENSE)); релизные чекпоинты — CC BY-NC 4.0 (см. карточку модели). Датасеты подчиняются лицензиям исходных источников: ассеты Mixamo — условия Adobe Mixamo, объекты Objaverse-XL — лицензия каждого исходного объекта, движения Truebones ZOO — коммерческая лицензия truebones.com. Перед использованием данных проверьте и соблюдайте соответствующие лицензии.

## 🤝 Благодарности

Авторы [AnyTop](https://github.com/Anytop2025/Anytop) за открытую кодовую базу, на которой частично построен этот репозиторий, и @chutch1122 за идею нескольких подписей на клип (обычная, общая и детальная подписи UniML3D).
