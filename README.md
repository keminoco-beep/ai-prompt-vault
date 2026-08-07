# AI Prompt Vault (AI绘图资料整理)

> A fully offline, single-exe desktop tool for collecting and organizing AI-generated images:
> save reference images, auto-extract prompts, keep a full model list, filter by base model
> family, and group images manually. Clean macOS-style dark UI, Chinese + English UI.

一个完全离线、独立 exe 的本地小工具，用于收集和整理 AI 绘画作品：保存例图、
自动提取提示词、记录全部模型、按主模型大类筛选、手动分组管理。

---

## Features

- **Collect images** — drag & drop from web pages, paste from clipboard (Ctrl+V),
  import **Civitai links** (auto-extracts prompts, all models with clickable links,
  sampler / steps / CFG / seed / size, and downloads the original image)
- **Auto-extract embedded prompts** — PNGs exported from **A1111 / ComfyUI / NovelAI**
  carry generation params; drop or paste them and the form is auto-filled
  (positive / negative prompts, sampler, steps, CFG, seed, model, LoRA)
- **Gallery** — Grid / List views, sort (date, title, base model, model, size),
  filter (base model, ratio, LoRA, source, keyword), hover image preview,
  right-side detail panel, one-click copy (all / positive / negative)
- **Manual groups** — create / rename / delete groups, right-click to assign,
  counts always in sync
- **Fully offline** — all data lives in a `Library` folder next to the exe
  (index JSON + images + thumbs + trash); no account, no telemetry
- **Bilingual UI** — Chinese / English, switch anytime in Settings
  (restart to apply; language saved in `Library/settings.json`)

## Screenshots

*(Add screenshots here before publishing, e.g.)*

```
![Gallery](docs/screenshots/gallery.png)
![Collect](docs/screenshots/collect.png)
```

## Download

Prebuilt Windows exe: see **Releases**. The exe is a single portable file —
copy it anywhere, run it, done. SmartScreen may warn (unsigned); click
*More info → Run anyway* the first time.

## Run from source

```bash
# Python 3.10+ (tested on 3.13)
pip install -r requirements.txt
python main.py
```

Optional self-test: `python main.py --selftest` (auto-quits after 2.5 s).

## Build the exe (Windows)

```bash
pip install pyinstaller
python build.py
# output: dist/AI绘图资料整理.exe
```

Or via GitHub Actions: push to `main` and the workflow
(`.github/workflows/build.yml`) builds the exe and uploads it as an artifact.

## Run tests

```bash
python tests/test_core.py          # data / filters / civitai logic
python tests/test_image_meta.py    # embedded PNG metadata parsing
python tests/gui_smoke.py          # offscreen GUI smoke test (QT_QPA_PLATFORM=offscreen)
```

## Project layout

```
ai-prompt-vault/
├── main.py              # entry point
├── app/
│   ├── config.py        # paths, library folder (auto-migrates old "资料库")
│   ├── data_store.py    # Library/ data.json + images + thumbs + trash
│   ├── civitai.py       # Civitai scraping / API (dual-domain fallback)
│   ├── image_meta.py    # PNG tEXt/zTXt/iTXt → A1111/NovelAI/ComfyUI params
│   ├── filters.py       # filtering, ratio buckets, LoRA merge
│   ├── i18n.py          # lightweight zh/en translation
│   ├── thumbs.py        # thumbnail / rounded tile generation
│   ├── workers.py       # background copy/download workers
│   └── ui/              # PySide6 widgets (dark macOS-style QSS)
├── tests/               # unit + offscreen GUI smoke tests
├── build.py             # one-command PyInstaller build
└── requirements.txt
```

## Data folder

Everything is stored in a **`Library`** folder next to the exe (auto-created):

```
Library/
├── data.json    # record index (prompts / models / params / groups)
├── images/      # original images
├── thumbs/      # thumbnails
├── trash/       # deleted records (soft delete)
└── settings.json# language preference
```

> **Migration**: versions ≤ 2.2.1 used a Chinese folder name `资料库`.
> The app renames it to `Library` automatically on first launch — data is preserved.

## Tech

- Python + PySide6 (Qt) + QSS dark theme, single-file PyInstaller build
- Zero runtime dependencies beyond PySide6 + requests
- No account, no network calls except Civitai imports (which you initiate)

## License

[MIT](LICENSE)

## Changelog
### v2.4.7 (2026-08-08)
- Download list: incremental refresh (no longer rebuilds rows on every update,
  so pause/delete buttons stay clickable)
- Delete works on paused downloads (cleans up .part file)
- Button label: Cancel → Delete
- ComfyUI model download: pause/resume with HTTP Range resume, HTML error-page
  detection, Civitai API Key auth (optional), speed display, throttled refresh

### v2.4.6 (2026-08-08)
- Pause/resume downloads with breakpoint continuation (HTTP Range)
- Long file names elided in detail sidebar (middle-truncated with tooltip)
- API-key guide dialog shown at most once per session

### v2.4.5 (2026-08-08)
- Negative Content-Length guard; lower-resolution friendly sidebar
- API Key guide at civitai.red/user/account; cancel buttons; throttled UI refresh

### v2.3.2 (2026-08-07)
- Bug fixes: Civitai import NameError; auto-extracted prompts lost on save; copy feedback.
