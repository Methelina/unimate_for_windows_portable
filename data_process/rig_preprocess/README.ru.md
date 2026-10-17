# rig_preprocess: собственный риггед-ассет (RU)

Русская версия: [`README.md`](README.md) (полная, каноническая документация). Здесь — выжимка для Windows-сборки.

## Что это

`rig_preprocess` превращает один риггед 3D-ассет (GLB, glTF или FBX, анимированный или нет) в **каталог-ассет**, который обученная модель UniMate анимирует по тексту: скелетное условие (`cond.npy`), rest-pose меш в канонической системе модели (`<name>.glb`) и превью. Используются те же этапы экспорта, разметки суставов, извлечения признаков и канонической запечки, что и при построении UniML3D — невиденный модели ассет готовится ровно как тренировочные данные.

## Windows-специфика

bash-обёртка `run_rig_preprocess.sh` удалена. Эквиваленты:

```bash
# интерактивный путь (метки суставов -> пауза на ревью -> сборка):
python -m data_process.rig_preprocess run --input robot.glb --output_dir outputs/rig/robot
# прочитать outputs/rig/robot/REVIEW.md, поправить annotation.json, затем:
python -m data_process.rig_preprocess run --input robot.glb --output_dir outputs/rig/robot --annotation outputs/rig/robot/annotation.json

# без интерактива (сборка сразу на автоматической rule-based разметке):
python -m data_process.rig_preprocess run --input robot.glb --output_dir outputs/rig/robot --no_review
```

или через MCP/CLI мост (`mcp_unimate`):

```powershell
python -m mcp_unimate rig robot.glb outputs/rig/robot            # REVIEW=0, сборка сразу
python -m mcp_unimate rig robot.glb outputs/rig/robot --face-r R_Thigh --face-l L_Thigh
```

Переменные окружения старой обёртки (INPUT/OUTPUT_DIR/REVIEW/...) модулем **не читаются** — передавайте флаги явно (полная таблица соответствия — в английской версии, раздел «Wrapper and Python API»).

## Быстрый цикл использования

```bash
python -m data_process.rig_preprocess run --input robot.glb --output_dir outputs/rig/robot --no_review
python -m unimate.inference.sample --exp_dir outputs/unimate_uniml3d_f60_v3 --asset outputs/rig/robot --prompt "An object walks forward." --num_repetitions 3
python -m data_process.mesh_animation.sample_manifest outputs/samples/custom --skip_invalid   # прогон меша анимацией
```

## Проверено

На этой сборке путь проверен end-to-end на встроенном ассете `assets/examples/eagle/Eagle.glb` (glTF-импорт, каноническая запечка, `cond.npy`, консистентность метаданных — OK). Предупреждение «Draco mesh compression is not available» при экспорте — косметическое (в pip-bpy 4.0 нет extern_draco.dll), на результат не влияет.

Подробности (входные форматы, разметка и facing, ревью, опции команд, точность, ограничения, troubleshooting) — в [`README.md`](README.md).
