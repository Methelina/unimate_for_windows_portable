# UniML3D Data Pipeline (RU)

Русская версия: [`README.md`](README.md) — полная каноническая документация пайплайна. Здесь — выжимка для Windows-сборки.

## Суть

Пайплайн превращает риггед-ассеты (FBX Truebones, FBX Mixamo, GLB Objaverse или свои) в **[UniML3D](https://huggingface.co/datasets/Linzhan/UniML3D)**: текстово-парные клипы с разметкой топологии для тренировки UniMate, а также готовит одиночный риггед-ассет для обученной модели ([rig_preprocess](rig_preprocess/README.ru.md)).

## Windows-специфика

Все bash-обёртки `data_process/scripts/*.sh` удалены. Каждая стадия вызывается напрямую как модуль — соответствие «обёртка → модуль» один-в-один, аргументы те же (см. `--help` каждого модуля). Переменные окружения, которые читали обёртки, модулями не поддерживаются — передавайте опции флагами.

| Стадия | Команда (Windows) |
|---|---|
| 0. Загрузка | `python tools/_hf_pycurl_download.py <repo> dataset/raw/<ds> --include ...` |
| 1. Экспорт | `python -m data_process.motion_export.export_mixamo` / `export_objaverse` / `export_truebones` / `export_general` |
| 2. Рендеринг | `python -m data_process.motion_rendering.render_tpose` / `render_mixamo` / `render_objaverse` / `render_truebones` / `render_general` |
| 2a-b. Капшены | `python -m data_process.vlm_caption.caption_motion` / `classify_category` |
| 3. Суставы | `python -m data_process.joint_annotation.names_clean_llm` / `face_select_llm` / `names_correct_llm` / `face_correct_llm` / `names_clean_rule` / `face_select_rule` |
| 3-vis | `python -m data_process.tools.vis_tpose` / `vis_tpose_facing` |
| 4. Признаки | `python -m data_process.feature_extraction.extract_features` |
| 5. Анимация | `python -m data_process.mesh_animation.sample_manifest <dir> --skip_invalid`; точечно: `animate_motion` / `animate_npz` / `animate_lbs` / `animate_fbx` / `animate_mixamo` |
| rig_preprocess | `python -m data_process.rig_preprocess run ...` или `python -m mcp_unimate rig <in> <out>` |

Изоляция среды, выбор GPU и `PYTHONIOENCODING=utf-8` обеспечивает `run_unimate.ps1` / MCP-мост.

## Важно для инференс-сценария

Эта сборка — инференс-ориентированная: этапы 0–4 нужны только тем, кто строит датасет или тренирует модель. Для анимации собственного ассета достаточно [rig_preprocess](rig_preprocess/README.ru.md); тренировочные клипы этапа 4 публикуются готовыми на HF Hub.

Детальное описание стадий, форматы данных, конфигурация — в [`README.md`](README.md).
