══════════════════════════════════════════════════════════
      AI Prompt Vault  v3.2.1
      Organize your AI art (reference images + prompts + models)
      UI available in 中文 / English / Español / 日本語
══════════════════════════════════════════════════════════

【Introduction】
A fully offline, standalone Windows tool for collecting and
organizing AI-generated art: save reference images, auto-extract
prompts, annotate every model, filter by base model family,
manage custom groups, and browse your ComfyUI output directly
in the gallery. The UI supports four languages — Chinese,
English, Español and 日本語 — switchable at any time.

──────────────────────────────────────────────
★ Features
──────────────────────────────────────────────
· Collect: drag & drop web images, paste with Ctrl+V, or paste
  a Civitai image / model / video share link for one-click
  import — prompts, model lists and sampling parameters are
  extracted automatically, and originals are downloaded
· Gallery: grid / list views with sorting, multi-filter and
  keyword search; large hover preview in List view; imported
  videos show their real resolution
· My Works: point the app at Auto-Import Folders (e.g. your
  ComfyUI output) and new images appear in the gallery
  automatically — no manual refresh; auto-grouped by folder;
  display cap adjustable in Settings
· Models: one-click health check of your model folders
  (corrupt / 0-byte / leftover files flagged), and one-click
  download of a picture's models straight into ComfyUI's
  folders
· Groups: custom groups plus the auto-generated "My Works"
  group tree — organize by theme with ease
· Duplicate detection: finds visually duplicated images in one
  click, keeps the sharpest
· Batch export: export multiple records to CSV / Markdown
  (prompts-only option)
· Multiple libraries: switch or create library folders
  independently
· Light / Dark theme: instant switch
· 4 languages: 中文 / English / Español / 日本語, switch
  anytime

──────────────────────────────────────────────
1. System Requirements & Installation
──────────────────────────────────────────────
· Windows 10 / Windows 11 (64-bit)
· No runtime or environment needed — portable single .exe,
  just double-click to run
· Fully offline (only Civitai link import and model downloads
  require an Internet connection)

【SmartScreen notice on first run】
Because the app is not code-signing certified, Windows may show
"Windows protected your PC" on first launch. This is normal —
click:
    More info → Run anyway
The app will open normally. (Only needed the first time.)

【Switching the UI language】
Settings → UI Language, choose 中文 / English / Español / 日本語.
Restart the app to apply; your preference is saved automatically.
(The language preference is stored in the Library and migrates
with your data.)

──────────────────────────────────────────────
2. Feature Guide
──────────────────────────────────────────────

【Collecting works (how to add images)】
· Drag & drop images: drag reference images from the web
  straight into the dashed area (multiple at once); local image
  files work too
· Paste images: press Ctrl+V anywhere, or click the "Paste
  Image" button
· Local videos: import local video files (a first-frame
  thumbnail is extracted automatically)
· Civitai link import: paste a civitai.com or civitai.red
  image / model / video share link → "Parse & Import",
  which automatically extracts:
  - Positive / negative prompts
  - Base model family (Krea 2 / Flux.1 / Flux.2 / SDXL / Pony /
    Illustrious / NoobAI / SD 1.5 / SD 3.5, etc.)
  - The full model list (Checkpoint / LoRA / Embedding / VAE,
    etc.), each with a clickable Civitai page link — click
    "Open" to jump straight to it
  - Sampler, steps, CFG, seed, image size
  - Automatic download of the original image; for video links
    the video file is downloaded and a first-frame thumbnail is
    generated for the gallery
  Tip: multiple links can be pasted at once (separated by
  spaces or newlines).

【Automatic local PNG parameter extraction (important)】
PNG images exported from SD WebUI (A1111), ComfyUI, or NovelAI
embed their generation parameters. When you drop or paste such
an image, the app auto-fills: positive/negative prompts, sampler,
steps, CFG, seed, model name and LoRA (the status bar shows
"Embedded prompt auto-extracted ✓").

【My Works (auto-import gallery)】
In Settings you can add one or more "Auto-Import Folders"
(multiple folders supported, such as your ComfyUI output
directory, including all subfolders). Changes apply immediately
after saving; the app scans these folders in the background and
adds the generated images to the gallery as "virtual
references" — no file copying, no extra disk usage:
· A "My Works" group appears in the group tree; with multiple
  folders, works are auto-grouped as
  My Works / <folder name> / <subfolder>
· Generation parameters are auto-extracted for every work
  (prompt / sampler / model / LoRA, etc.)
· Real-time updates: new / deleted / moved images in your
  folders sync to the gallery automatically — no manual
  refresh; you can also click the "Refresh" button on the
  gallery toolbar to check immediately
· Adjustable display cap: limit how many "My Works" items are
  shown (default 250, adjustable 50–10000, or unlimited)
· "File Missing" badge: works whose source file has been moved
  or deleted are clearly marked in the gallery
· Double-click a virtual work to view details; it is never
  copied into the Library (avoids doubling disk usage)

【Gallery browsing】
· Two view modes:
  - Grid: large-image thumbnails; drag the "Size" slider to
    scale tiles
  - List: a detailed file-manager-like table (thumbnail / title /
    base model / models / prompt / size / date added); click
    column headers to sort, drag column separators to resize
· Sort by: date added / title / base model / model / size,
  ascending or descending (clicking headers in List mode works
  too)
· Filters: base model family, image ratio, LoRA used, source,
  and keyword search (searches model names / base model family)
· Hover over an image: a clean large preview popup appears
· Select an image: the right-side panel shows full details
  (large image, prompts, sampling parameters, model links,
  group) with one-click copy of all / positive / negative
· Right-click an image: copy prompt, add to group, open base
  model page, show in folder, delete record
· Double-click an image: opens the details/edit dialog to
  modify info, copy, or delete

【Manual grouping】
In the "Groups" area below the left sidebar:
· Click "＋ New" to create a custom group (rename / delete
  anytime)
· Right-click an image → "Add to Group ▸" to pick a group, or
  "Remove from Group"
· Click a group name to view only that group's images (with a
  count badge)
· Group data is stored in the Library and survives machine
  migration

【Batch operations / Export】
With multiple images selected you can:
· Batch move to a group / batch delete (moved to trash)
· Batch export: CSV or Markdown, full records or prompts only
· Exported content includes: title, prompt, model list,
  parameters, source link, etc.

【Duplicate detection】
· One click finds visually duplicated images; compare the
  previews and keep the sharpest one — the rest are moved to
  trash

【Multiple libraries】
· Settings → Library location → Change, to point to a new
  library directory; restart to apply, old data stays intact
· Libraries are independent of each other — great for keeping
  different subjects separate

【Light / Dark theme】
· Settings → Theme: switch between Dark / Light, applies
  immediately

【Model health check】
The Models page scans your ComfyUI model folders (including
subfolders) and checks file health (corrupt / 0-byte / leftover
.part). Problem models are marked with a red ⚠ and the toolbar
shows the total count. (.txt description files are
ignored automatically.)

【Downloading models to ComfyUI】
· Settings → ComfyUI root folder (a separate setting,
  used only for model downloads — it does not interfere
  with the Auto-Import Folders)
· Click "Download Models" in the gallery / details panel to
  download a picture's models straight into ComfyUI's matching
  model folders
· The "Downloads" page shows progress, pause / resume, and
  history
· If a download hits 403 / HTML error pages, add a Civitai API
  Key in Settings (generated at civitai.red user center) and
  retry

──────────────────────────────────────────────
3. Data Management
──────────────────────────────────────────────
All data is stored automatically in the Library subfolder next
to the exe (created on first run; an old Chinese-named
"资料库" folder is auto-migrated):

    Library/
    ├── library.db                # SQLite database (records/groups/settings)
    ├── settings.json             # Settings (language, theme, paths, etc.)
    ├── images/                   # Original images
    ├── videos/                   # Imported videos
    ├── thumbs/                   # Thumbnails (faster browsing)
    ├── comfy_output_cache.json   # "My Works" scan cache
    ├── comfy_output_thumbs/      # "My Works" thumbnails
    └── trash/                    # Trash (deleted records go here)

· The "Open Library Folder" button in the sidebar opens it
  directly
· Copy the whole Library folder to back up / migrate everything
· Deleted records move to trash, never physically deleted
  immediately
· Multiple libraries: point Settings at a new library directory
  (restart to apply; old library data is untouched)
· Theme: switch Dark / Light in Settings (applies immediately)

──────────────────────────────────────────────
4. FAQ
──────────────────────────────────────────────
· Civitai import sometimes fails: network access to Civitai can
  be unstable; the app auto-switches between civitai.com and
  civitai.red and retries — just try again later
· Dragging images from the web fails: if hotlink protection is
  in place, save the image first, then drag in the local file
· Changing computers: copy the whole Library folder over and
  open the app — everything is there
· "My Works" is not showing: make sure the "Auto-Import
  Folders" in Settings are correct; the first scan runs in the
  background, so wait a moment — or click the "Refresh" button
  on the gallery toolbar to check immediately
· "My Works" marked "File Missing": the source file was moved
  or deleted — the gallery only references the original path,
  so check your Auto-Import Folders
· Does the first scan of a large folder take long? The scan
  runs in the background and the UI stays responsive; after the
  first scan, new images are synced automatically with no
  manual refresh needed
· Model download shows 403 / HTML error page: add a Civitai API
  Key in Settings (civitai.red user center → API Keys) and retry

──────────────────────────────────────────────
5. Version History
──────────────────────────────────────────────
v3.2.1  (this release)
        · New look: frameless rounded window with a custom
          title bar (drag to move, double-click to maximize /
          restore, resize from any edge)
        · Brand-new AI-art app icon
        · Improved text contrast in dark theme — clearer and
          easier to read
        · Fixed leftover Chinese text in the English UI
        · Fixed flicker while resizing the window, plus other
          polish
v3.2.0  (previous release — all fixes & improvements since
        v3.1.0)
        · Enlarged hover preview (360px in the detail sidebar,
          toggleable; off in Grid view)
        · Video resolution (imported videos show their real
          size — no more "Unknown")
        · Collect batch-save fix (each image keeps its own
          prompt/model; skips importing/no-image items with a
          notice)
        · Configurable "My Works" display cap (default 250,
          50–10000, or unlimited)
        · Real-time updates (new/deleted/moved images in your
          Auto-Import Folders sync automatically — no manual
          refresh)
        · No flicker on refresh (scroll & selection preserved)
        · Missing thumbnails auto-fill (real thumbnails swap in
          as soon as they are ready)
        · Settings redesign (one Auto-Import Folder per row
          with open/remove buttons)
        · Smoother mouse-wheel (per-pixel grid scrolling)
v3.1.0  (previous release — every improvement since v3.0)
        · Civitai video link import (download video + extract
          parameters + first-frame thumbnail)
        · Spanish / Japanese UI (four languages)
        · ComfyUI output gallery "My Works" (virtual references —
          no file copying; automatic grouping across multiple
          output folders; disk cache for second-level startup;
          ~6.5× faster scanning)
        · Settings: multiple "ComfyUI Output Folders" + a
          dedicated "ComfyUI root folder" row
        · Fixes: deleted duplicates no longer resurrect after
          restart, gallery refreshes after saving, no frozen
          scans, and a mismatched cache directory no longer
          triggers a full rescan on every startup
        · Chunked gallery rendering (large galleries stay
          responsive, images appear batch by batch) + "Refresh"
          button
v3.0    Rewrite: SQLite database, multiple libraries, batch
        operations & export (CSV/Markdown), tag system,
        duplicate image detection, A1111 output one-click
        import, light/dark themes
v2.2.1  Fixes: import stuck at "Importing...", wrong sort order,
        thumbnail column text, clipped button text; two-row
        toolbar layout
v2.2.0  New: automatic generation parameter extraction from
        local images (A1111/ComfyUI/NovelAI); full Apple-style
        UI redesign; improved group sidebar
v2.1.x  New: list view, sorting, manual groups, one-click copy,
        right-side details panel
v2.0    Model taxonomy: base model family + full model list +
        per-model Civitai hyperlinks
v1.0.3  Basics: collect / browse / filter / import-export

══════════════════════════════════════════════════════════
  Enjoy! Feedback is always welcome.
══════════════════════════════════════════════════════════
