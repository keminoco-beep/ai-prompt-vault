"""多语言支持（i18n）。

- 轻量级翻译表：key 为中文原文，t() 按当前语言返回翻译；无翻译时返回原文。
- 语言持久化：保存在资料库 settings.json（随数据迁移）。
- 扩展：往 _LANG_TABLES 里加 "ja"/"ko" 等即可支持更多语言。
"""
import json

LANGUAGES = {
    "zh": "中文",
    "en": "English",
    "es": "Español",
    "ja": "日本語",
}

_current = "zh"
_lang_file = None

# key=中文原文，value=各语言翻译
_LANG_TABLES = {
    "en": {
        # ---- 通用 ----
        "设置": "Settings",
        "关闭": "Close",
        "确定": "OK",
        "取消": "Cancel",
        "保存": "Save",
        "打开": "Open",
        "删除": "Delete",
        "清空": "Clear",
        "复制": "Copy",
        "全部": "All",
        "其他": "Other",
        "未分组": "Ungrouped",
        "标题": "Title",
        "标签": "Tags",
        "主模型大类": "Base Model",
        "正向提示词": "Positive Prompt",
        "负向提示词": "Negative Prompt",
        "采样器": "Sampler",
        "步数": "Steps",
        "CFG": "CFG",
        "种子": "Seed",
        "模型清单": "Models",
        "模型名称": "Model Name",
        "尺寸": "Size",
        "导入时间": "Date Added",
        "未知": "Unknown",
        "未命名": "Untitled",
        "离线可用": "Offline ready",
        "删除记录": "Delete Record",

        # ---- 主窗口 ----
        "例图 · 提示词 · 模型 管理": "Reference images · Prompts · Models",
        "收藏作品": "Collect",
        "图库浏览": "Gallery",
        "图片分组": "Groups",
        "新建分组": "New Group",
        "分组名称：": "Group name:",
        "该分组已存在或名称为空": "Group already exists or name is empty",
        "重命名分组": "Rename Group",
        "新名称：": "New name:",
        "新名称已存在或无效": "New name already exists or is invalid",
        "删除分组": "Delete Group",
        "删除分组「{g}」？\n组内图片不会被删除，仅移回未分组。": "Delete group \"{g}\"?\nImages in it will not be deleted, only moved back to Ungrouped.",
        "打开资料库文件夹": "Open Library Folder",
        "折叠 / 展开分组": "Collapse / Expand groups",

        # ---- 收藏面板 ----
        "把图片拖进来或粘贴进来，填写提示词与模型后保存；粘贴 Civitai 链接可自动提取数据":
            "Drop or paste images, fill in prompts & models, then save; paste a Civitai link to auto-extract data",
        "粘贴图片": "Paste Image",
        "解析并导入": "Parse & Import",
        "全部保存": "Save All",
        "保存当前": "Save Current",
        "待保存": "Pending",
        "拖入图片 / 链接到这里": "Drop images / links here",
        "支持一次拖入多张图片，也支持拖入本地图片文件":
            "Drop multiple images at once; local image files are also supported",
        "把网页上的例图直接拖到这里\n\n或按 Ctrl+V 粘贴剪贴板里的图片\n\n也支持拖入 / 粘贴 Civitai 链接，自动提取提示词与全部模型":
            "Drag web images here\n\nor press Ctrl+V to paste from clipboard\n\nYou can also drop/paste Civitai links to auto-extract prompts & models",
        "可选，例如：赛博朋克城市夜景": "Optional, e.g. Cyberpunk city at night",
        "逗号分隔，例如：风景, 夜晚, 霓虹": "Comma separated, e.g. landscape, night, neon",
        "图片主模型所属的大类（如 Krea 2 / Flux.1 / Flux.2），导入 Civitai 链接时自动识别":
            "Base model family (e.g. Krea 2 / Flux.1 / Flux.2), auto-detected from Civitai links",
        "一键复制": "Copy",
        "一键复制到剪贴板": "Copy to clipboard",
        "正向提示词…（导入 Civitai 链接后自动填充）": "Positive prompt... (auto-filled from Civitai link)",
        "负向提示词…": "Negative prompt...",
        "模型清单（图片使用的所有模型，导入时自动列出）":
            "All models used (auto-listed on import)",
        "+ 添加模型": "+ Add Model",
        "模型名称（如 Krea2 Turbo_FP8）": "Model name (e.g. Krea2 Turbo_FP8)",
        "模型链接（Civitai 导入自动填写，可点击打开）":
            "Model link (auto-filled from Civitai, click to open)",
        "待保存列表为空，先拖入图片或导入链接": "List is empty. Drop images or import a link first",
        "剪贴板里没有可导入的图片或链接": "No image or link in clipboard",
        "该链接已在待保存列表中": "This link is already in the pending list",
        "未在输入中找到有效的 Civitai 链接": "No valid Civitai link found in input",
        "正在导入 {found} 个链接…": "Importing {found} link(s)...",
        "已加入待保存": "Added to pending",
        "已自动提取图片内嵌提示词 ✓": "Embedded prompt auto-extracted ✓",
        "已导入 Civitai 数据": "Civitai data imported",
        "已保存 {n} 条 ✓": "Saved {n} item(s) ✓",
        "已保存 ✓": "Saved ✓",
        "已复制 ✓": "Copied ✓",
        "已复制到剪贴板 ✓": "Copied to clipboard ✓",
        "已清理 {n} 个不可见字符": "Removed {n} invisible character(s)",
        "复制失败：{err}": "Copy failed: {err}",
        "没有可复制的内容": "Nothing to copy",
        "没有可保存的完整项（缺图片）": "No complete item to save (missing image)",
        "有 {n} 条仍在导入中，已跳过": "{n} item(s) still importing, skipped",
        "有 {n} 条无图片，已跳过": "{n} item(s) without an image, skipped",
        "请等待导入完成": "Please wait for the import to finish",
        "清空 {len(self.pending)} 条待保存内容？（已保存到资料库的记录不受影响）":
            "Clear {len(self.pending)} pending item(s)? (Saved records are not affected)",
        "已清空": "Cleared",
        "导入失败：": "Import failed: ",
        "确定删除这条记录吗？\n图片文件将移入资料库回收站（trash）。":
            "Delete this record?\nThe image will be moved to the library trash.",

        # ---- 图库面板 ----
        "悬停看详情，右键复制提示词/加入分组，双击打开详情；可切换显示方式与排序":
            "Hover for details, right-click to copy prompts / add to group, double-click to open",
        "搜索标题 / 标签 / 提示词 / 模型名 / 主模型大类":
            "Search title / tags / prompts / model names / base model",
        "主模型": "Base Model",
        "比例": "Ratio",
        "来源": "Source",
        "排序": "Sort",
        "显示": "View",
        "大小": "Size",
        "平铺": "Grid",
        "列表": "List",
        "复制提示词": "Copy Prompt",
        "复制正向": "Copy Pos",
        "复制负向": "Copy Neg",
        "复制正向提示词": "Copy Positive Prompt",
        "复制负向提示词": "Copy Negative Prompt",
        "复制全部提示词": "Copy All Prompts",
        "复制当前选中图片的全部提示词（含参数）": "Copy all prompts of the selected image (with params)",
        "切换升序 / 降序": "Toggle ascending / descending",
        "共 {n} 张": "{n} item(s)",
        "共 0 张": "0 items",
        "全部比例": "All Ratios",
        "全部来源": "All Sources",
        "来自Civitai": "From Civitai",
        "本地导入": "Local",
        "导入时间": "Date Added",
        "模型": "Model",
        "全部图片": "All Images",
        "查看详情 / 编辑": "View / Edit",
        "加入分组 ▸": "Add to Group ▸",
        "从当前分组移除": "Remove from Group",
        "打开主模型页面": "Open Model Page",
        "打开图片所在文件夹": "Show in Folder",
        "在浏览器打开来源链接": "Open Source Link",
        "没有符合条件的图片": "No matching images",
        "去「收藏作品」板块添加例图吧": "Add some images in the Collect panel",
        "试试调整筛选/分组条件": "Try adjusting filters / groups",
        "暂无图片": "No image",
        "暂无图片\n（右键查看来源）": "No image\n(right-click for source)",
        "（无）": "(none)",
        "未知尺寸": "Unknown size",
        "模型清单": "Models",

        # ---- 详情对话框 ----
        "作品详情": "Details",
        "标签（逗号分隔）": "Tags (comma separated)",
        "原始 baseModel": "Raw baseModel",
        "分组": "Group",
        "如 Krea 2 / Flux.1 Krea（Civitai 原始值）": "e.g. Krea 2 / Flux.1 Krea (raw Civitai value)",
        "模型链接（可选）": "Model link (optional)",
        "复制全部提示词": "Copy All",
        "保存修改": "Save Changes",
        "打开原图": "Open Image",
        "在浏览器中打开 Civitai 页面": "Open on Civitai",
        "来源链接：{src}": "Source: {src}",
        "无内容": "Nothing",

        # ---- 详情侧栏 ----
        "选择图片查看详情": "Select an image to view details",
        "（未选中）": "(not selected)",
        "（无标题）": "(no title)",
        "（无图片）": "(no image)",
        "采样参数": "Sampling",
        "复制全部": "Copy All",
        "来源：{src}": "Source: {src}",

        # ---- 数据字段映射 ----
        "大模型": "Checkpoint",
        "嵌入": "Embedding",
        "VAE": "VAE",
        "超网络": "Hypernetwork",
        "ControlNet": "ControlNet",
        "放大模型": "Upscaler",
        "工作流": "Workflow",
        "运动模块": "Motion Module",
        "文本编码器": "Text Encoder",
        "检测": "Detection",
        "姿态": "Pose",
        "CLIP视觉": "CLIP Vision",
        "美学梯度": "Aesthetic Gradient",
        "视觉语言": "Vision Language",
        "超宽": "Ultra-wide",
        "超高": "Ultra-tall",
        # ---- 补充遗漏（v2.3.1） ----
        "AI绘图资料整理": "AI Prompt Vault",
        "绘": "P",
        "＋ 新建": "＋ New",
        "待保存图片": "Pending images",
        "待保存 0 条": "0 pending",
        "待保存列表为空": "Pending list is empty",
        "导入中…": "Importing...",
        "请先粘贴 Civitai 链接": "Please paste a Civitai link first",
        "这条还没有图片，无法保存": "This item has no image yet, cannot save",
        "请先选中一张图片": "Select an image first",
        "没有内容可复制": "Nothing to copy",
        "Civitai 返回了无法解析的数据": "Civitai returned unparsable data",
        "读取 Civitai 图片信息失败：": "Failed to read Civitai image info: ",
        "读取 Civitai 图片信息失败": "Failed to read Civitai image info",
        "访问 Civitai 失败：": "Failed to access Civitai: ",
        "无图片地址": "No image URL",
        ": 页面未包含该图片数据": ": page does not contain this image data",
        "无法识别的 Civitai 链接": "Unrecognized Civitai link",
        "图片下载失败（{err}）": "Image download failed ({err})",
        "复制文件失败（{e}）": "Copy file failed ({e})",
        "导入超时（{seconds}s），请检查网络后重试": "Import timed out ({seconds}s), check your network and retry",
        "确定删除「{title}」吗？\n图片将移入资料库回收站。": "Delete \"{title}\"?\nThe image will be moved to the library trash.",
        "模型清单（所有使用的模型，可编辑，链接可点击打开）": "Models (all used models, editable, links clickable)",
        "粘贴 Civitai 链接（civitai.com / civitai.red 均可），支持多链接用空格或换行分隔": "Paste Civitai link(s) (civitai.com / civitai.red), multiple links separated by spaces or newlines",
        "待保存 {n} 条": "{n} pending",
        "提示词": "Prompt",
        "没有符合条件的图片\n": "No matching images\n",

        # ---- v2.4.0 ComfyUI 集成 ----
        "界面语言": "UI Language",
        "ComfyUI 文件夹": "ComfyUI Folder",
        "ComfyUI 根目录（用于模型下载）": "ComfyUI root folder (for model downloads)",
        "选择 ComfyUI 根目录（含 models/ 子目录）": "Select the ComfyUI root folder (contains models/)",
        "浏览…": "Browse...",
        "设置后可在图库一键下载图片使用的模型到 ComfyUI 对应类别的模型文件夹。":
            "After setting this, you can one-click download a picture's models into ComfyUI's matching model folders.",
        "下载模型": "Download Models",
        "下载当前图片使用的模型到 ComfyUI（需先在设置中选择 ComfyUI 文件夹）":
            "Download this picture's models into ComfyUI (set the ComfyUI folder in Settings first)",
        "选择模型类型": "Select Model Type",
        "模型「{name}」属于『其他』类型，请选择要保存到的 ComfyUI 模型文件夹：":
            "Model \"{name}\" is of type \"Other\". Choose the ComfyUI model folder to save to:",
        "模型类型": "Model Type",
        "正在下载：{name}": "Downloading: {name}",
        "正在下载：{name}（{mb:.0f} MB）": "Downloading: {name} ({mb:.0f} MB)",
        "取消": "Cancel",
        "模型「{name}」已存在，跳过下载。": "Model \"{name}\" already exists, skipped.",
        "模型「{name}」已下载到：\n{path}": "Model \"{name}\" downloaded to:\n{path}",
        "模型「{name}」下载失败：{err}": "Failed to download model \"{name}\": {err}",
        "模型「{name}」解析下载链接失败：{err}": "Failed to resolve download link for \"{name}\": {err}",
        "该图片没有可下载的模型（无链接）。": "No downloadable models for this picture (no links).",
        "该图片没有可下载的模型": "No downloadable models for this picture",
        "请先在「设置」中选择 ComfyUI 文件夹，再下载模型。":
            "Please select the ComfyUI folder in Settings first, then download models.",
        "下载": "Download",
        "下载到 ComfyUI 对应模型文件夹": "Download into ComfyUI's matching model folder",
        "仅用于下载模型": "For model downloads only",

        # ---- v2.4.1 模型管理面板 ----
        "模型管理": "Models",
        "管理 ComfyUI 中已安装的模型：重命名、删除、添加备注。":
            "Manage models installed in ComfyUI: rename, delete, add notes.",
        "搜索模型名…": "Search model names...",
        "类型": "Type",
        "刷新": "Refresh",
        "（根目录）": "(root)",
        "未选中模型": "No model selected",
        "备注": "Note",
        "添加备注（保存在资料库，不修改文件）…": "Add a note (saved in Library, does not modify the file)...",
        "保存备注": "Save Note",
        "重命名": "Rename",
        "复制文件名": "Copy File Name",
        "打开所在文件夹": "Show in Folder",
        "删除": "Delete",
        "尚未链接 ComfyUI。请先在「设置」中选择 ComfyUI 文件夹。":
            "ComfyUI is not linked yet. Select the ComfyUI folder in Settings first.",
        "新文件名：": "New file name:",
        "同名文件已存在": "A file with the same name already exists",
        "重命名失败：{err}": "Rename failed: {err}",
        "重命名成功 ✓": "Renamed ✓",
        "文件名已复制 ✓": "File name copied ✓",
        "确定删除模型「{name}」吗？\n此操作会直接删除文件，无法恢复。":
            "Delete model \"{name}\"?\nThis permanently deletes the file and cannot be undone.",
        "删除失败：{err}": "Delete failed: {err}",
        "已删除 ✓": "Deleted ✓",
        "备注已保存 ✓": "Note saved ✓",
        "大小": "Size",

        # ---- v2.4.3 下载列表页 ----
        "下载列表": "Downloads",
        "正在下载的模型与最近完成的历史。取消会自动清理残留缓存。":
            "Active downloads and recent history. Cancel auto-cleans up partial files.",
        "正在下载": "Downloading",
        "历史记录": "History",
        "清空历史": "Clear history",
        "暂无下载任务。从图库/详情面板点击「下载模型」即可在此查看进度。":
            "No downloads yet. Click 'Download Models' in gallery or details to track progress here.",
        "完成": "Done",
        "失败": "Failed",
        "已取消": "Cancelled",
        "暂停": "Pause",
        "继续": "Resume",
        "已暂停": "Paused",
        "该文件已不存在（可能已移动/删除）。":
            "The file no longer exists (it may have been moved or deleted).",

        # ---- v2.4.8 翻译漏洞修复 ----
        "模型链接为空": "Model URL is empty",
        "该模型暂无可下载文件": "No downloadable file for this model",
        "未知模型类型：": "Unknown model type: ",
        "返回 HTML 错误页（可能需要 Civitai API Key）":
            "Got an HTML error page (may need a Civitai API Key)",
        "下载不完整（{got}/{total}）": "Incomplete download ({got}/{total})",
        "文件过小（{got} 字节），疑似错误响应":
            "File too small ({got} bytes), likely an error response",
        "下载到的是错误页（HTML/JSON），可能需要 Civitai API Key":
            "Downloaded an error page (HTML/JSON), may need a Civitai API Key",
        "下载失败": "Download failed",
        "分": " min",
        "秒": " sec",
        "civ_...（可选，解决模型下载 403 / HTML 错误页）":
            "civ_... (optional, fixes 403 / HTML error pages)",
        "在 Civitai 用户中心（https://civitai.red/user/account → API Keys → New API Key）生成，粘贴到这里即可让模型下载携带登录凭证。":
            "Generate at civitai.red/user/account → API Keys → New API Key. Paste here so model downloads carry your login credentials.",
        "切换语言后重启软件即可生效。": "Restart the app to apply language changes.",
        "语言已切换，重启软件后生效。": "Language changed. Restart the app to apply.",
        ": 页面未包含该图片数据": ": page does not contain this image's data",
        "无图片地址": "No image URL",
        "(无图片)": "(no image)",
        "(无标题)": "(untitled)",
        "(未选中)": "(none selected)",
        "下载中": "Downloading",
        "等待": "Waiting",
        "下载模型 ▸": "Download Models ▸",
        "去设置": "Go to Settings",
        "打开模型页": "Open Model Page",
        "选择 ComfyUI 根目录": "Select the ComfyUI root folder",
        "重命名模型": "Rename Model",
        "下载失败：需要登录态（API Key）": "Download failed: login (API Key) required",
        "模型「{name}」下载失败：{err}\n\nCivitai 官方下载需要登录凭证。你可以：\n① 在「设置」填入 Civitai API Key 后重试\n② 直接打开 Civitai 模型页手动下载":
            "Model \"{name}\" failed to download: {err}\n\nCivitai downloads need a login. You can:\n① Add your Civitai API Key in Settings and retry\n② Open the Civitai model page to download manually",
        "把网页上的例图直接拖到这里\n\n或按 Ctrl+V 粘贴剪贴板里的图片\n\n也支持拖入 / 粘贴 Civitai 链接，自动提取提示词与全部模型":
            "Drop images here\n\nor press Ctrl+V to paste images from clipboard\n\nCivitai links are also supported — auto-extract prompts and models",
        # ---- v3.0 视频支持 ----
        "不是受支持的视频文件": "Unsupported video file",
        "视频": "Video",
        "全部媒体": "All media",
        "图片": "Images",
        "视频分类": "Videos",
        "播放": "Play",
        "时长": "Duration",
        "媒体": "Media",
        "视频：{t}": "Video: {t}",
        "解析中…": "Resolving...",
        "批量操作（{n} 项）▸": "Batch ({n} items) ▸",
        "批量删除": "Batch delete",
        "批量改分组 ▸": "Move to group ▸",
        "确定删除选中的 {n} 条记录吗？\n图片/视频将移入资料库回收站（trash）。":
            "Delete the {n} selected records?\nImages/videos will move to the Library trash.",
        "批量改分组": "Move to group",
        "将 {n} 条记录移动到：": "Move {n} records to:",
        "批量导出": "Export selected",
        "选择导出文件夹": "Choose export folder",
        "已导出 {n} 条记录到：{d}": "Exported {n} records to: {d}",
        "导出失败：{err}": "Export failed: {err}",
        "全部标签": "All tags",
        "查重": "Find dupes",
        "检测库中的重复图片（感知哈希）": "Find duplicate images (perceptual hash)",
        "未发现重复图片 ✓": "No duplicate images found ✓",
        "发现 {n} 组重复图片": "Found {n} groups of duplicate images",
        "以下图片哈希相同（同一张图的不同版本）。点击「清理」保留每组第一张，删除其余（移入回收站）。":
            "These images have identical hashes (different versions of the same picture). Click Clean to keep the first of each group and move the rest to trash.",
        "清理选中组": "Clean selected",
        "请先选择一组重复图片": "Select a duplicate group first",
        "已清理 {removed} 张重复图片（移入回收站）":
            "Cleaned {removed} duplicate images (moved to trash)",
        " {n} 张重复": " {n} duplicates",
        "资料库位置": "Library location",
        "更换…": "Change…",
        "更换资料库后重启软件生效。当前库：{p}":
            "Restart the app to apply the new library. Current: {p}",
        "选择资料库文件夹": "Choose library folder",
        "资料库已切换，重启软件后生效。":
            "Library changed. Restart the app to apply.",
        "界面主题": "Theme",
        "暗色": "Dark",
        "亮色": "Light",
        "界面主题即时生效。": "The theme applies immediately.",
        "启用悬浮预览（列表模式）": "Enable hover preview (list view)",
        "关闭后不再显示悬停预览图，可减少资源占用；设置立即生效。":
            "Hover preview will be disabled to save resources; applies immediately.",
        "A1111 outputs 目录": "A1111 outputs folder",
        "可选：Automatic1111 输出目录，用于一键导入生成图":
            "Optional: Automatic1111 output folder, for one-click import of generated images",
        "设置后可在图库一键把 A1111 生成的图片（含提示词等参数）导入收藏。":
            "After setting, you can one-click import A1111 generated images (with prompts) into the library.",
        "选择 A1111 outputs 目录": "Choose A1111 outputs folder",
        "从 A1111 导入": "Import from A1111",
        "把 A1111 outputs 目录的生成图（含提示词参数）一键导入收藏":
            "One-click import generated images (with prompt params) from A1111 outputs",
        "请先在「设置」中配置 A1111 outputs 目录。":
            "Please configure the A1111 outputs folder in Settings first.",
        "已导入 {imported} 张，{skipped} 张重复跳过":
            "Imported {imported} images, {skipped} duplicates skipped",
        "导入完成：{imported} 张新增，{skipped} 张重复跳过，{errors} 张失败":
            "Import finished: {imported} added, {skipped} duplicates skipped, {errors} failed",
        "空文件": "empty file",
        "疑似损坏": "possibly corrupt",
        "下载残留": "leftover download",
        "⚠ 空文件（0 字节）：下载中断或写盘失败，建议删除后重新下载。":
            "⚠ Empty file (0 bytes): download interrupted or write failed. Delete and re-download.",
        "⚠ 疑似损坏（小于 1KB）：可能是错误响应被误存，建议删除后重新下载。":
            "⚠ Possibly corrupt (<1KB): an error response may have been saved. Delete and re-download.",
        "⚠ 存在 .part 下载残留：上一次下载未完成，文件可能不完整。":
            "⚠ Leftover .part download: previous download unfinished, file may be incomplete.",
        "⚠ {n} 个模型健康异常": "⚠ {n} models with health issues",
        "全部模型正常 ✓": "All models healthy ✓",
        "视频地址为空": "Video URL is empty",
        "无视频地址": "No video URL",
        "视频下载失败（{err}）": "Video download failed ({err})",
        "视频下载失败": "Video download failed",
        "我的作品": "My Works",
        "我的作品（虚拟引用，不复制文件）":
            "My Works (virtual reference, files are not copied)",
        "共 {n} 张（虚拟作品仅显示前 {cap} 张）":
            "{n} items (only first {cap} virtual works shown)",

        # ---- v3.2 新增翻译 key（civitai 硬编码修复） ----
        "下载内容不是有效图片": "Downloaded content is not a valid image",
        "视频内容异常（{size} 字节）": "Abnormal video content ({size} bytes)",

        # ---- v3.3 多输出目录 ----
        "自动导入文件夹": "Auto-import Folders",
        "浏览": "Browse",
        "移除该文件夹": "Remove this folder",
        "添加文件夹": "Add Folder",
        "可添加多个输出文件夹，图库将按文件夹自动分组。":
            "You can add multiple output folders; the gallery will auto-group them by folder.",
        "output 目录已变更，正在后台扫描…":
            "Output folders changed. Scanning in the background...",

        # ---- v3.4 幽灵记录标记 / 扫描提示 ----
        "文件缺失": "File Missing",
        "正在后台扫描输出文件夹…": "Scanning output folders in the background...",

        # ---- v3.9 虚拟作品显示上限可配置 ----
        "限制我的作品显示数量": "Limit number of My Works shown",
        "我的作品最多显示": "Show at most",
        "张": " items",

        # ---- v4.1 自绘标题栏 ----
        "最小化": "Minimize",
        "最大化": "Maximize",
        "还原": "Restore",

        # ---- v4.2 i18n 审计补全（缺失 key / 专有名词） ----
        "重新扫描输出文件夹，立即显示新增图片（手动刷新）":
            "Rescan output folders now to show newly added images (manual refresh)",
        "Civitai API Key": "Civitai API Key",
        "AI-Prompt-Vault": "AI-Prompt-Vault",
    },

    "es": {
        # ---- 通用 ----
        "设置": "Ajustes",
        "关闭": "Cerrar",
        "确定": "Aceptar",
        "取消": "Cancelar",
        "保存": "Guardar",
        "打开": "Abrir",
        "删除": "Eliminar",
        "清空": "Vaciar",
        "复制": "Copiar",
        "全部": "Todos",
        "其他": "Otros",
        "未分组": "Sin grupo",
        "标题": "Título",
        "标签": "Etiquetas",
        "主模型大类": "Modelo base",
        "正向提示词": "Prompt positivo",
        "负向提示词": "Prompt negativo",
        "采样器": "Muestreador",
        "步数": "Pasos",
        "CFG": "CFG",
        "种子": "Semilla",
        "模型清单": "Modelos",
        "模型名称": "Nombre del modelo",
        "尺寸": "Tamaño",
        "导入时间": "Fecha de importación",
        "未知": "Desconocido",
        "未命名": "Sin título",
        "离线可用": "Disponible sin conexión",
        "删除记录": "Eliminar registro",

        # ---- 主窗口 ----
        "例图 · 提示词 · 模型 管理": "Imágenes de referencia · Prompts · Modelos",
        "收藏作品": "Colección",
        "图库浏览": "Galería",
        "图片分组": "Grupos de imágenes",
        "新建分组": "Nuevo grupo",
        "分组名称：": "Nombre del grupo:",
        "该分组已存在或名称为空": "El grupo ya existe o el nombre está vacío",
        "重命名分组": "Renombrar grupo",
        "新名称：": "Nuevo nombre:",
        "新名称已存在或无效": "El nuevo nombre ya existe o no es válido",
        "删除分组": "Eliminar grupo",
        "删除分组「{g}」？\n组内图片不会被删除，仅移回未分组。": "¿Eliminar el grupo \"{g}\"?\nLas imágenes del grupo no se eliminarán, solo volverán a Sin grupo.",
        "打开资料库文件夹": "Abrir carpeta de la biblioteca",
        "折叠 / 展开分组": "Contraer / expandir grupos",

        # ---- 收藏面板 ----
        "把图片拖进来或粘贴进来，填写提示词与模型后保存；粘贴 Civitai 链接可自动提取数据":
            "Arrastra o pega imágenes, completa prompts y modelos y guarda; pega un enlace de Civitai para extraer datos automáticamente",
        "粘贴图片": "Pegar imagen",
        "解析并导入": "Analizar e importar",
        "全部保存": "Guardar todo",
        "保存当前": "Guardar actual",
        "待保存": "Pendiente",
        "拖入图片 / 链接到这里": "Arrastra imágenes / enlaces aquí",
        "支持一次拖入多张图片，也支持拖入本地图片文件":
            "Puedes arrastrar varias imágenes a la vez; también se admiten archivos de imagen locales",
        "把网页上的例图直接拖到这里\n\n或按 Ctrl+V 粘贴剪贴板里的图片\n\n也支持拖入 / 粘贴 Civitai 链接，自动提取提示词与全部模型":
            "Arrastra imágenes de referencia de la web aquí\n\npulsa Ctrl+V para pegar desde el portapapeles\n\nTambién puedes soltar/pegar enlaces de Civitai para extraer prompts y todos los modelos automáticamente",
        "可选，例如：赛博朋克城市夜景": "Opcional, p. ej. ciudad cyberpunk de noche",
        "逗号分隔，例如：风景, 夜晚, 霓虹": "Separado por comas, p. ej. paisaje, noche, neón",
        "图片主模型所属的大类（如 Krea 2 / Flux.1 / Flux.2），导入 Civitai 链接时自动识别":
            "Familia del modelo base (p. ej. Krea 2 / Flux.1 / Flux.2), se detecta automáticamente desde enlaces de Civitai",
        "一键复制": "Copiar",
        "一键复制到剪贴板": "Copiar al portapapeles",
        "正向提示词…（导入 Civitai 链接后自动填充）": "Prompt positivo... (se rellena automáticamente desde el enlace de Civitai)",
        "负向提示词…": "Prompt negativo...",
        "模型清单（图片使用的所有模型，导入时自动列出）":
            "Todos los modelos usados (se listan automáticamente al importar)",
        "+ 添加模型": "+ Añadir modelo",
        "模型名称（如 Krea2 Turbo_FP8）": "Nombre del modelo (p. ej. Krea2 Turbo_FP8)",
        "模型链接（Civitai 导入自动填写，可点击打开）":
            "Enlace del modelo (se rellena desde Civitai, haz clic para abrir)",
        "待保存列表为空，先拖入图片或导入链接": "La lista está vacía. Arrastra imágenes o importa un enlace primero",
        "剪贴板里没有可导入的图片或链接": "No hay imagen ni enlace en el portapapeles",
        "该链接已在待保存列表中": "Este enlace ya está en la lista pendiente",
        "未在输入中找到有效的 Civitai 链接": "No se encontró un enlace de Civitai válido en la entrada",
        "正在导入 {found} 个链接…": "Importando {found} enlace(s)...",
        "已加入待保存": "Añadido a pendientes",
        "已自动提取图片内嵌提示词 ✓": "Prompt incrustado extraído automáticamente ✓",
        "已导入 Civitai 数据": "Datos de Civitai importados",
        "已保存 {n} 条 ✓": "Guardados {n} elemento(s) ✓",
        "已保存 ✓": "Guardado ✓",
        "已复制 ✓": "Copiado ✓",
        "已复制到剪贴板 ✓": "Copiado al portapapeles ✓",
        "已清理 {n} 个不可见字符": "Se eliminaron {n} carácter(es) invisible(s)",
        "复制失败：{err}": "Error al copiar: {err}",
        "没有可复制的内容": "Nada que copiar",
        "没有可保存的完整项（缺图片）": "No hay elementos completos para guardar (falta la imagen)",
        "有 {n} 条仍在导入中，已跳过": "{n} elemento(s) aún importando, omitidos",
        "有 {n} 条无图片，已跳过": "{n} elemento(s) sin imagen, omitidos",
        "请等待导入完成": "Espera a que termine la importación",
        "清空 {len(self.pending)} 条待保存内容？（已保存到资料库的记录不受影响）":
            "¿Vaciar {len(self.pending)} elemento(s) pendiente(s)? (Los registros guardados no se ven afectados)",
        "已清空": "Vaciado",
        "导入失败：": "Error de importación: ",
        "确定删除这条记录吗？\n图片文件将移入资料库回收站（trash）。":
            "¿Eliminar este registro?\nLa imagen se moverá a la papelera de la biblioteca (trash).",

        # ---- 图库面板 ----
        "悬停看详情，右键复制提示词/加入分组，双击打开详情；可切换显示方式与排序":
            "Pasa el cursor para ver detalles, clic derecho para copiar prompts / añadir a grupo, doble clic para abrir; cambia la vista y el orden",
        "搜索标题 / 标签 / 提示词 / 模型名 / 主模型大类":
            "Buscar título / etiquetas / prompts / nombres de modelos / modelo base",
        "主模型": "Modelo base",
        "比例": "Relación",
        "来源": "Origen",
        "排序": "Orden",
        "显示": "Vista",
        "大小": "Tamaño",
        "平铺": "Cuadrícula",
        "列表": "Lista",
        "复制提示词": "Copiar prompt",
        "复制正向": "Copiar pos",
        "复制负向": "Copiar neg",
        "复制正向提示词": "Copiar prompt positivo",
        "复制负向提示词": "Copiar prompt negativo",
        "复制全部提示词": "Copiar todos los prompts",
        "复制当前选中图片的全部提示词（含参数）": "Copiar todos los prompts de la imagen seleccionada (con parámetros)",
        "切换升序 / 降序": "Alternar ascendente / descendente",
        "共 {n} 张": "{n} elemento(s)",
        "共 0 张": "0 elementos",
        "全部比例": "Todas las relaciones",
        "全部来源": "Todos los orígenes",
        "来自Civitai": "De Civitai",
        "本地导入": "Local",
        "模型": "Modelo",
        "全部图片": "Todas las imágenes",
        "查看详情 / 编辑": "Ver / editar",
        "加入分组 ▸": "Añadir a grupo ▸",
        "从当前分组移除": "Quitar del grupo",
        "打开主模型页面": "Abrir página del modelo",
        "打开图片所在文件夹": "Mostrar en carpeta",
        "在浏览器打开来源链接": "Abrir enlace de origen",
        "没有符合条件的图片": "No hay imágenes que coincidan",
        "去「收藏作品」板块添加例图吧": "Añade imágenes en el panel Colección",
        "试试调整筛选/分组条件": "Prueba a ajustar filtros / grupos",
        "暂无图片": "Sin imagen",
        "暂无图片\n（右键查看来源）": "Sin imagen\n(clic derecho para ver origen)",
        "（无）": "(ninguno)",
        "未知尺寸": "Tamaño desconocido",

        # ---- 详情对话框 ----
        "作品详情": "Detalles",
        "标签（逗号分隔）": "Etiquetas (separadas por comas)",
        "原始 baseModel": "baseModel original",
        "分组": "Grupo",
        "如 Krea 2 / Flux.1 Krea（Civitai 原始值）": "p. ej. Krea 2 / Flux.1 Krea (valor original de Civitai)",
        "模型链接（可选）": "Enlace del modelo (opcional)",
        "复制全部提示词": "Copiar todos los prompts",
        "保存修改": "Guardar cambios",
        "打开原图": "Abrir imagen",
        "在浏览器中打开 Civitai 页面": "Abrir en Civitai",
        "来源链接：{src}": "Origen: {src}",
        "无内容": "Nada",

        # ---- 详情侧栏 ----
        "选择图片查看详情": "Selecciona una imagen para ver los detalles",
        "（未选中）": "(sin selección)",
        "（无标题）": "(sin título)",
        "（无图片）": "(sin imagen)",
        "采样参数": "Muestreo",
        "复制全部": "Copiar todo",
        "来源：{src}": "Origen: {src}",

        # ---- 数据字段映射 ----
        "大模型": "Checkpoint",
        "嵌入": "Embedding",
        "VAE": "VAE",
        "超网络": "Hiperred",
        "ControlNet": "ControlNet",
        "放大模型": "Upscaler",
        "工作流": "Flujo de trabajo",
        "运动模块": "Módulo de movimiento",
        "文本编码器": "Codificador de texto",
        "检测": "Detección",
        "姿态": "Pose",
        "CLIP视觉": "CLIP Vision",
        "美学梯度": "Gradiente estético",
        "视觉语言": "Lenguaje visual",
        "超宽": "Ultraancho",
        "超高": "Ultraalto",
        # ---- 补充遗漏（v2.3.1） ----
        "AI绘图资料整理": "AI Prompt Vault",
        "绘": "P",
        "＋ 新建": "＋ Nuevo",
        "待保存图片": "Imágenes pendientes",
        "待保存 0 条": "0 pendientes",
        "待保存列表为空": "La lista de pendientes está vacía",
        "导入中…": "Importando...",
        "请先粘贴 Civitai 链接": "Pega primero un enlace de Civitai",
        "这条还没有图片，无法保存": "Este elemento aún no tiene imagen, no se puede guardar",
        "请先选中一张图片": "Selecciona una imagen primero",
        "没有内容可复制": "Nada que copiar",
        "Civitai 返回了无法解析的数据": "Civitai devolvió datos no analizables",
        "读取 Civitai 图片信息失败：": "Error al leer la información de la imagen de Civitai: ",
        "读取 Civitai 图片信息失败": "Error al leer la información de la imagen de Civitai",
        "访问 Civitai 失败：": "Error al acceder a Civitai: ",
        "无图片地址": "Sin URL de imagen",
        ": 页面未包含该图片数据": ": la página no contiene los datos de esta imagen",
        "无法识别的 Civitai 链接": "Enlace de Civitai no reconocido",
        "图片下载失败（{err}）": "Error al descargar la imagen ({err})",
        "复制文件失败（{e}）": "Error al copiar el archivo ({e})",
        "导入超时（{seconds}s），请检查网络后重试": "Tiempo de importación agotado ({seconds}s), comprueba la red e inténtalo de nuevo",
        "确定删除「{title}」吗？\n图片将移入资料库回收站。": "¿Eliminar \"{title}\"?\nLa imagen se moverá a la papelera de la biblioteca.",
        "模型清单（所有使用的模型，可编辑，链接可点击打开）": "Modelos (todos los modelos usados, editables, enlaces clicables)",
        "粘贴 Civitai 链接（civitai.com / civitai.red 均可），支持多链接用空格或换行分隔": "Pega enlaces de Civitai (civitai.com / civitai.red), varios enlaces separados por espacios o saltos de línea",
        "待保存 {n} 条": "{n} pendientes",
        "提示词": "Prompt",
        "没有符合条件的图片\n": "No hay imágenes que coincidan\n",

        # ---- v2.4.0 ComfyUI 集成 ----
        "界面语言": "Idioma de la interfaz",
        "ComfyUI 文件夹": "Carpeta de ComfyUI",
        "ComfyUI 根目录（用于模型下载）": "Carpeta raíz de ComfyUI (para descargas de modelos)",
        "选择 ComfyUI 根目录（含 models/ 子目录）": "Selecciona la carpeta raíz de ComfyUI (contiene models/)",
        "浏览…": "Examinar...",
        "设置后可在图库一键下载图片使用的模型到 ComfyUI 对应类别的模型文件夹。":
            "Tras configurarlo, puedes descargar los modelos de una imagen en las carpetas de modelos de ComfyUI con un clic.",
        "下载模型": "Descargar modelos",
        "下载当前图片使用的模型到 ComfyUI（需先在设置中选择 ComfyUI 文件夹）":
            "Descargar los modelos de esta imagen a ComfyUI (configura la carpeta de ComfyUI en Ajustes primero)",
        "选择模型类型": "Seleccionar tipo de modelo",
        "模型「{name}」属于『其他』类型，请选择要保存到的 ComfyUI 模型文件夹：":
            "El modelo \"{name}\" es de tipo \"Otros\". Elige la carpeta de modelos de ComfyUI donde guardarlo:",
        "模型类型": "Tipo de modelo",
        "正在下载：{name}": "Descargando: {name}",
        "正在下载：{name}（{mb:.0f} MB）": "Descargando: {name} ({mb:.0f} MB)",
        "模型「{name}」已存在，跳过下载。": "El modelo \"{name}\" ya existe, descarga omitida.",
        "模型「{name}」已下载到：\n{path}": "Modelo \"{name}\" descargado en:\n{path}",
        "模型「{name}」下载失败：{err}": "Error al descargar el modelo \"{name}\": {err}",
        "模型「{name}」解析下载链接失败：{err}": "Error al resolver el enlace de descarga de \"{name}\": {err}",
        "该图片没有可下载的模型（无链接）。": "Esta imagen no tiene modelos descargables (sin enlaces).",
        "该图片没有可下载的模型": "Esta imagen no tiene modelos descargables",
        "请先在「设置」中选择 ComfyUI 文件夹，再下载模型。":
            "Selecciona la carpeta de ComfyUI en Ajustes antes de descargar modelos.",
        "下载": "Descargar",
        "下载到 ComfyUI 对应模型文件夹": "Descargar en la carpeta de modelos correspondiente de ComfyUI",
        "仅用于下载模型": "Solo para descargas de modelos",

        # ---- v2.4.1 模型管理面板 ----
        "模型管理": "Modelos",
        "管理 ComfyUI 中已安装的模型：重命名、删除、添加备注。":
            "Gestiona los modelos instalados en ComfyUI: renombrar, eliminar, añadir notas.",
        "搜索模型名…": "Buscar nombres de modelos...",
        "类型": "Tipo",
        "刷新": "Actualizar",
        "（根目录）": "(raíz)",
        "未选中模型": "Ningún modelo seleccionado",
        "备注": "Nota",
        "添加备注（保存在资料库，不修改文件）…": "Añadir nota (se guarda en la biblioteca, no modifica el archivo)...",
        "保存备注": "Guardar nota",
        "重命名": "Renombrar",
        "复制文件名": "Copiar nombre de archivo",
        "打开所在文件夹": "Mostrar en carpeta",
        "尚未链接 ComfyUI。请先在「设置」中选择 ComfyUI 文件夹。":
            "ComfyUI aún no está vinculado. Selecciona la carpeta de ComfyUI en Ajustes primero.",
        "新文件名：": "Nuevo nombre de archivo:",
        "同名文件已存在": "Ya existe un archivo con el mismo nombre",
        "重命名失败：{err}": "Error al renombrar: {err}",
        "重命名成功 ✓": "Renombrado ✓",
        "文件名已复制 ✓": "Nombre de archivo copiado ✓",
        "确定删除模型「{name}」吗？\n此操作会直接删除文件，无法恢复。":
            "¿Eliminar el modelo \"{name}\"?\nEsto eliminará el archivo permanentemente y no se puede deshacer.",
        "删除失败：{err}": "Error al eliminar: {err}",
        "已删除 ✓": "Eliminado ✓",
        "备注已保存 ✓": "Nota guardada ✓",

        # ---- v2.4.3 下载列表页 ----
        "下载列表": "Descargas",
        "正在下载的模型与最近完成的历史。取消会自动清理残留缓存。":
            "Descargas activas e historial reciente. Cancelar limpia automáticamente los archivos parciales.",
        "正在下载": "Descargando",
        "历史记录": "Historial",
        "清空历史": "Vaciar historial",
        "暂无下载任务。从图库/详情面板点击「下载模型」即可在此查看进度。":
            "Aún no hay descargas. Haz clic en \"Descargar modelos\" en la galería o en los detalles para ver el progreso aquí.",
        "完成": "Hecho",
        "失败": "Fallido",
        "已取消": "Cancelado",
        "暂停": "Pausar",
        "继续": "Reanudar",
        "已暂停": "En pausa",
        "该文件已不存在（可能已移动/删除）。":
            "El archivo ya no existe (puede haberse movido o eliminado).",

        # ---- v2.4.8 翻译漏洞修复 ----
        "模型链接为空": "La URL del modelo está vacía",
        "该模型暂无可下载文件": "No hay archivos descargables para este modelo",
        "未知模型类型：": "Tipo de modelo desconocido: ",
        "返回 HTML 错误页（可能需要 Civitai API Key）":
            "Se obtuvo una página de error HTML (puede que necesites una API Key de Civitai)",
        "下载不完整（{got}/{total}）": "Descarga incompleta ({got}/{total})",
        "文件过小（{got} 字节），疑似错误响应":
            "Archivo demasiado pequeño ({got} bytes), posible respuesta de error",
        "下载到的是错误页（HTML/JSON），可能需要 Civitai API Key":
            "Se descargó una página de error (HTML/JSON), puede que necesites una API Key de Civitai",
        "下载失败": "Error de descarga",
        "分": " min",
        "秒": " s",
        "civ_...（可选，解决模型下载 403 / HTML 错误页）":
            "civ_... (opcional, soluciona errores 403 / páginas HTML)",
        "在 Civitai 用户中心（https://civitai.red/user/account → API Keys → New API Key）生成，粘贴到这里即可让模型下载携带登录凭证。":
            "Genérala en civitai.red/user/account → API Keys → New API Key. Pégala aquí para que las descargas de modelos lleven tus credenciales de inicio de sesión.",
        "切换语言后重启软件即可生效。": "Reinicia la aplicación para aplicar el cambio de idioma.",
        "语言已切换，重启软件后生效。": "Idioma cambiado. Reinicia la aplicación para aplicarlo.",
        ": 页面未包含该图片数据": ": la página no contiene los datos de esta imagen",
        "无图片地址": "Sin URL de imagen",
        "(无图片)": "(sin imagen)",
        "(无标题)": "(sin título)",
        "(未选中)": "(sin selección)",
        "下载中": "Descargando",
        "等待": "En espera",
        "下载模型 ▸": "Descargar modelos ▸",
        "去设置": "Ir a Ajustes",
        "打开模型页": "Abrir página del modelo",
        "选择 ComfyUI 根目录": "Seleccionar la carpeta raíz de ComfyUI",
        "重命名模型": "Renombrar modelo",
        "下载失败：需要登录态（API Key）": "Error de descarga: se requiere inicio de sesión (API Key)",
        "模型「{name}」下载失败：{err}\n\nCivitai 官方下载需要登录凭证。你可以：\n① 在「设置」填入 Civitai API Key 后重试\n② 直接打开 Civitai 模型页手动下载":
            "El modelo \"{name}\" no se pudo descargar: {err}\n\nLas descargas de Civitai requieren inicio de sesión. Puedes:\n① Añadir tu API Key de Civitai en Ajustes y reintentar\n② Abrir la página del modelo en Civitai para descargar manualmente",
        "把网页上的例图直接拖到这里\n\n或按 Ctrl+V 粘贴剪贴板里的图片\n\n也支持拖入 / 粘贴 Civitai 链接，自动提取提示词与全部模型":
            "Arrastra imágenes de referencia de la web aquí\n\npulsa Ctrl+V para pegar desde el portapapeles\n\nTambién puedes pegar enlaces de Civitai para extraer el prompt y todos los modelos automáticamente",
        # ---- v3.0 视频支持 ----
        "不是受支持的视频文件": "Archivo de vídeo no compatible",
        "视频": "Vídeo",
        "全部媒体": "Todos los medios",
        "图片": "Imágenes",
        "视频分类": "Vídeos",
        "播放": "Reproducir",
        "时长": "Duración",
        "媒体": "Medio",
        "视频：{t}": "Vídeo: {t}",
        "解析中…": "Analizando...",
        "批量操作（{n} 项）▸": "Lote ({n} elementos) ▸",
        "批量删除": "Eliminación en lote",
        "批量改分组 ▸": "Mover a grupo ▸",
        "确定删除选中的 {n} 条记录吗？\n图片/视频将移入资料库回收站（trash）。":
            "¿Eliminar los {n} registros seleccionados?\nLas imágenes/vídeos se moverán a la papelera de la biblioteca (trash).",
        "批量改分组": "Mover a grupo",
        "将 {n} 条记录移动到：": "Mover {n} registros a:",
        "批量导出": "Exportar seleccionados",
        "选择导出文件夹": "Elegir carpeta de exportación",
        "已导出 {n} 条记录到：{d}": "Exportados {n} registros a: {d}",
        "导出失败：{err}": "Error de exportación: {err}",
        "全部标签": "Todas las etiquetas",
        "查重": "Buscar duplicados",
        "检测库中的重复图片（感知哈希）": "Buscar imágenes duplicadas (hash perceptual)",
        "未发现重复图片 ✓": "No se encontraron imágenes duplicadas ✓",
        "发现 {n} 组重复图片": "Se encontraron {n} grupos de imágenes duplicadas",
        "以下图片哈希相同（同一张图的不同版本）。点击「清理」保留每组第一张，删除其余（移入回收站）。":
            "Estas imágenes tienen hashes idénticos (versiones diferentes de la misma imagen). Haz clic en Limpiar para conservar la primera de cada grupo y mover el resto a la papelera.",
        "清理选中组": "Limpiar seleccionadas",
        "请先选择一组重复图片": "Selecciona primero un grupo de imágenes duplicadas",
        "已清理 {removed} 张重复图片（移入回收站）":
            "Se limpiaron {removed} imágenes duplicadas (movidas a la papelera)",
        " {n} 张重复": " {n} duplicados",
        "资料库位置": "Ubicación de la biblioteca",
        "更换…": "Cambiar...",
        "更换资料库后重启软件生效。当前库：{p}":
            "Reinicia la aplicación para aplicar la nueva biblioteca. Actual: {p}",
        "选择资料库文件夹": "Elegir carpeta de la biblioteca",
        "资料库已切换，重启软件后生效。":
            "Biblioteca cambiada. Reinicia la aplicación para aplicarlo.",
        "界面主题": "Tema",
        "暗色": "Oscuro",
        "亮色": "Claro",
        "界面主题即时生效。": "El tema se aplica inmediatamente.",
        "启用悬浮预览（列表模式）": "Habilitar vista previa al pasar el cursor (vista de lista)",
        "关闭后不再显示悬停预览图，可减少资源占用；设置立即生效。":
            "La vista previa se desactivará para ahorrar recursos; se aplica de inmediato.",
        "A1111 outputs 目录": "Carpeta de outputs de A1111",
        "可选：Automatic1111 输出目录，用于一键导入生成图":
            "Opcional: carpeta de salida de Automatic1111, para importar imágenes generadas con un clic",
        "设置后可在图库一键把 A1111 生成的图片（含提示词等参数）导入收藏。":
            "Tras configurarlo, puedes importar las imágenes generadas por A1111 (con prompts) a la biblioteca con un clic.",
        "选择 A1111 outputs 目录": "Elegir la carpeta de outputs de A1111",
        "从 A1111 导入": "Importar desde A1111",
        "把 A1111 outputs 目录的生成图（含提示词参数）一键导入收藏":
            "Importa con un clic las imágenes generadas (con parámetros de prompt) desde la carpeta de outputs de A1111",
        "请先在「设置」中配置 A1111 outputs 目录。":
            "Configura primero la carpeta de outputs de A1111 en Ajustes.",
        "已导入 {imported} 张，{skipped} 张重复跳过":
            "Importadas {imported} imágenes, {skipped} duplicadas omitidas",
        "导入完成：{imported} 张新增，{skipped} 张重复跳过，{errors} 张失败":
            "Importación finalizada: {imported} añadidas, {skipped} duplicadas omitidas, {errors} fallidas",
        "空文件": "archivo vacío",
        "疑似损坏": "posiblemente corrupto",
        "下载残留": "descarga residual",
        "⚠ 空文件（0 字节）：下载中断或写盘失败，建议删除后重新下载。":
            "⚠ Archivo vacío (0 bytes): descarga interrumpida o error de escritura. Elimínalo y vuelve a descargar.",
        "⚠ 疑似损坏（小于 1KB）：可能是错误响应被误存，建议删除后重新下载。":
            "⚠ Posiblemente corrupto (<1KB): puede haberse guardado una respuesta de error. Elimínalo y vuelve a descargar.",
        "⚠ 存在 .part 下载残留：上一次下载未完成，文件可能不完整。":
            "⚠ Queda una descarga residual .part: la descarga anterior no terminó, el archivo puede estar incompleto.",
        "⚠ {n} 个模型健康异常": "⚠ {n} modelos con problemas",
        "全部模型正常 ✓": "Todos los modelos en buen estado ✓",
        "视频地址为空": "La URL del vídeo está vacía",
        "无视频地址": "Sin URL de vídeo",
        "视频下载失败（{err}）": "Error al descargar el vídeo ({err})",
        "视频下载失败": "Error al descargar el vídeo",
        "我的作品": "Mis Obras",
        "我的作品（虚拟引用，不复制文件）":
            "Mis Obras (referencia virtual, los archivos no se copian)",
        "共 {n} 张（虚拟作品仅显示前 {cap} 张）":
            "{n} elementos (solo se muestran los primeros {cap} de las obras virtuales)",

        # ---- v3.2 新增翻译 key（civitai 硬编码修复） ----
        "下载内容不是有效图片": "El contenido descargado no es una imagen válida",
        "视频内容异常（{size} 字节）": "Contenido de vídeo anómalo ({size} bytes)",

        # ---- v3.3 多输出目录 ----
        "自动导入文件夹": "Carpetas de importación automática",
        "浏览": "Examinar",
        "移除该文件夹": "Eliminar esta carpeta",
        "添加文件夹": "Añadir carpeta",
        "可添加多个输出文件夹，图库将按文件夹自动分组。":
            "Puedes añadir varias carpetas de salida; la galería las agrupará automáticamente por carpeta.",
        "output 目录已变更，正在后台扫描…":
            "Las carpetas de salida han cambiado. Escaneando en segundo plano...",

        # ---- v3.4 幽灵记录标记 / 扫描提示 ----
        "文件缺失": "Archivo faltante",
        "正在后台扫描输出文件夹…": "Escaneando las carpetas de salida en segundo plano...",

        # ---- v3.9 虚拟作品显示上限可配置 ----
        "限制我的作品显示数量": "Limitar el número de Mis Obras mostradas",
        "我的作品最多显示": "Mostrar como máximo",
        "张": " uds.",

        # ---- v4.1 自绘标题栏 ----
        "最小化": "Minimizar",
        "最大化": "Maximizar",
        "还原": "Restaurar",

        # ---- v4.2 i18n 审计补全（缺失 key / 专有名词） ----
        "重新扫描输出文件夹，立即显示新增图片（手动刷新）":
            "Vuelve a escanear las carpetas de salida para mostrar las imágenes nuevas (refresco manual)",
        "Civitai API Key": "Clave de API de Civitai",
        "AI-Prompt-Vault": "AI-Prompt-Vault",
    },

    "ja": {
        # ---- 通用 ----
        "设置": "設定",
        "关闭": "閉じる",
        "确定": "OK",
        "取消": "キャンセル",
        "保存": "保存",
        "打开": "開く",
        "删除": "削除",
        "清空": "クリア",
        "复制": "コピー",
        "全部": "すべて",
        "其他": "その他",
        "未分组": "未分類",
        "标题": "タイトル",
        "标签": "タグ",
        "主模型大类": "ベースモデル",
        "正向提示词": "プロンプト（Positive）",
        "负向提示词": "プロンプト（Negative）",
        "采样器": "サンプラー",
        "步数": "ステップ数",
        "CFG": "CFG",
        "种子": "シード",
        "模型清单": "モデル一覧",
        "模型名称": "モデル名",
        "尺寸": "サイズ",
        "导入时间": "インポート日時",
        "未知": "不明",
        "未命名": "無題",
        "离线可用": "オフライン利用可",
        "删除记录": "レコード削除",

        # ---- 主窗口 ----
        "例图 · 提示词 · 模型 管理": "参考画像 · プロンプト · モデル管理",
        "收藏作品": "コレクション",
        "图库浏览": "ギャラリー",
        "图片分组": "画像グループ",
        "新建分组": "新規グループ",
        "分组名称：": "グループ名：",
        "该分组已存在或名称为空": "グループは既に存在するか、名前が空です",
        "重命名分组": "グループ名を変更",
        "新名称：": "新しい名前：",
        "新名称已存在或无效": "新しい名前は既に存在するか、無効です",
        "删除分组": "グループを削除",
        "删除分组「{g}」？\n组内图片不会被删除，仅移回未分组。": "グループ「{g}」を削除しますか？\nグループ内の画像は削除されず、未分類に戻るだけです。",
        "打开资料库文件夹": "ライブラリフォルダを開く",
        "折叠 / 展开分组": "グループを折りたたむ / 展開",

        # ---- 收藏面板 ----
        "把图片拖进来或粘贴进来，填写提示词与模型后保存；粘贴 Civitai 链接可自动提取数据":
            "画像をドラッグまたは貼り付け、プロンプトとモデルを入力して保存します。Civitaiリンクを貼り付けると自動でデータを抽出できます",
        "粘贴图片": "画像を貼り付け",
        "解析并导入": "解析してインポート",
        "全部保存": "すべて保存",
        "保存当前": "現在を保存",
        "待保存": "未保存",
        "拖入图片 / 链接到这里": "画像 / リンクをここにドロップ",
        "支持一次拖入多张图片，也支持拖入本地图片文件":
            "複数の画像を一度にドラッグできます。ローカルの画像ファイルにも対応",
        "把网页上的例图直接拖到这里\n\n或按 Ctrl+V 粘贴剪贴板里的图片\n\n也支持拖入 / 粘贴 Civitai 链接，自动提取提示词与全部模型":
            "Webの参考画像をここに直接ドラッグ\n\nまたは Ctrl+V でクリップボードの画像を貼り付け\n\nCivitaiリンクのドロップ / 貼り付けにも対応し、プロンプトと全モデルを自動抽出",
        "可选，例如：赛博朋克城市夜景": "任意。例：サイバーパンクな都市の夜景",
        "逗号分隔，例如：风景, 夜晚, 霓虹": "カンマ区切り。例：風景, 夜景, ネオン",
        "图片主模型所属的大类（如 Krea 2 / Flux.1 / Flux.2），导入 Civitai 链接时自动识别":
            "画像のベースモデルの分類（例：Krea 2 / Flux.1 / Flux.2）。Civitaiリンクのインポート時に自動判定",
        "一键复制": "コピー",
        "一键复制到剪贴板": "クリップボードにコピー",
        "正向提示词…（导入 Civitai 链接后自动填充）": "プロンプト（Positive）...（Civitaiリンクのインポート後に自動入力）",
        "负向提示词…": "プロンプト（Negative）...",
        "模型清单（图片使用的所有模型，导入时自动列出）":
            "使用した全モデル（インポート時に自動一覧表示）",
        "+ 添加模型": "+ モデル追加",
        "模型名称（如 Krea2 Turbo_FP8）": "モデル名（例：Krea2 Turbo_FP8）",
        "模型链接（Civitai 导入自动填写，可点击打开）":
            "モデルリンク（Civitaiから自動入力、クリックで開く）",
        "待保存列表为空，先拖入图片或导入链接": "リストが空です。先に画像をドロップするかリンクをインポートしてください",
        "剪贴板里没有可导入的图片或链接": "クリップボードにインポートできる画像やリンクがありません",
        "该链接已在待保存列表中": "このリンクは既に未保存リストにあります",
        "未在输入中找到有效的 Civitai 链接": "入力に有効なCivitaiリンクが見つかりません",
        "正在导入 {found} 个链接…": "{found} 件のリンクをインポート中...",
        "已加入待保存": "未保存に追加しました",
        "已自动提取图片内嵌提示词 ✓": "画像内のプロンプトを自動抽出しました ✓",
        "已导入 Civitai 数据": "Civitaiデータをインポートしました",
        "已保存 {n} 条 ✓": "{n} 件保存しました ✓",
        "已保存 ✓": "保存しました ✓",
        "已复制 ✓": "コピーしました ✓",
        "已复制到剪贴板 ✓": "クリップボードにコピーしました ✓",
        "已清理 {n} 个不可见字符": "不可視文字を {n} 個削除しました",
        "复制失败：{err}": "コピーに失敗しました：{err}",
        "没有可复制的内容": "コピーする内容がありません",
        "没有可保存的完整项（缺图片）": "保存できる完全な項目がありません（画像がありません）",
        "有 {n} 条仍在导入中，已跳过": "{n} 件はまだインポート中のためスキップしました",
        "有 {n} 条无图片，已跳过": "{n} 件は画像がないためスキップしました",
        "请等待导入完成": "インポートが完了するまでお待ちください",
        "清空 {len(self.pending)} 条待保存内容？（已保存到资料库的记录不受影响）":
            "未保存の {len(self.pending)} 件をクリアしますか？（保存済みのレコードには影響しません）",
        "已清空": "クリアしました",
        "导入失败：": "インポート失敗： ",
        "确定删除这条记录吗？\n图片文件将移入资料库回收站（trash）。":
            "このレコードを削除しますか？\n画像はライブラリのゴミ箱（trash）に移動します。",

        # ---- 图库面板 ----
        "悬停看详情，右键复制提示词/加入分组，双击打开详情；可切换显示方式与排序":
            "ホバーで詳細表示、右クリックでプロンプトのコピー / グループ追加、ダブルクリックで詳細を開きます。表示方法と並び順も切り替え可能",
        "搜索标题 / 标签 / 提示词 / 模型名 / 主模型大类":
            "タイトル / タグ / プロンプト / モデル名 / ベースモデルを検索",
        "主模型": "ベースモデル",
        "比例": "比率",
        "来源": "ソース",
        "排序": "並び順",
        "显示": "表示",
        "大小": "サイズ",
        "平铺": "グリッド",
        "列表": "リスト",
        "复制提示词": "プロンプトをコピー",
        "复制正向": "Positiveをコピー",
        "复制负向": "Negativeをコピー",
        "复制正向提示词": "プロンプト（Positive）をコピー",
        "复制负向提示词": "プロンプト（Negative）をコピー",
        "复制全部提示词": "全プロンプトをコピー",
        "复制当前选中图片的全部提示词（含参数）": "選択中の画像の全プロンプトをコピー（パラメータ含む）",
        "切换升序 / 降序": "昇順 / 降順を切り替え",
        "共 {n} 张": "全 {n} 件",
        "共 0 张": "0 件",
        "全部比例": "すべての比率",
        "全部来源": "すべてのソース",
        "来自Civitai": "Civitaiから",
        "本地导入": "ローカル",
        "模型": "モデル",
        "全部图片": "すべての画像",
        "查看详情 / 编辑": "詳細表示 / 編集",
        "加入分组 ▸": "グループに追加 ▸",
        "从当前分组移除": "現在のグループから削除",
        "打开主模型页面": "ベースモデルのページを開く",
        "打开图片所在文件夹": "フォルダを開く",
        "在浏览器打开来源链接": "ソースリンクをブラウザで開く",
        "没有符合条件的图片": "条件に一致する画像がありません",
        "去「收藏作品」板块添加例图吧": "「コレクション」パネルで参考画像を追加しましょう",
        "试试调整筛选/分组条件": "フィルター / グループ条件を調整してみてください",
        "暂无图片": "画像がありません",
        "暂无图片\n（右键查看来源）": "画像がありません\n（右クリックでソースを表示）",
        "（无）": "（なし）",
        "未知尺寸": "サイズ不明",

        # ---- 详情对话框 ----
        "作品详情": "作品詳細",
        "标签（逗号分隔）": "タグ（カンマ区切り）",
        "原始 baseModel": "元の baseModel",
        "分组": "グループ",
        "如 Krea 2 / Flux.1 Krea（Civitai 原始值）": "例：Krea 2 / Flux.1 Krea（Civitaiの生の値）",
        "模型链接（可选）": "モデルリンク（任意）",
        "复制全部提示词": "全プロンプトをコピー",
        "保存修改": "変更を保存",
        "打开原图": "元画像を開く",
        "在浏览器中打开 Civitai 页面": "Civitaiで開く",
        "来源链接：{src}": "ソース：{src}",
        "无内容": "なし",

        # ---- 详情侧栏 ----
        "选择图片查看详情": "画像を選択して詳細を表示",
        "（未选中）": "（未選択）",
        "（无标题）": "（タイトルなし）",
        "（无图片）": "（画像なし）",
        "采样参数": "サンプリング設定",
        "复制全部": "すべてコピー",
        "来源：{src}": "ソース：{src}",

        # ---- 数据字段映射 ----
        "大模型": "Checkpoint",
        "嵌入": "Embedding",
        "VAE": "VAE",
        "超网络": "Hypernetwork",
        "ControlNet": "ControlNet",
        "放大模型": "Upscaler",
        "工作流": "Workflow",
        "运动模块": "Motion Module",
        "文本编码器": "Text Encoder",
        "检测": "Detection",
        "姿态": "Pose",
        "CLIP视觉": "CLIP Vision",
        "美学梯度": "Aesthetic Gradient",
        "视觉语言": "Vision Language",
        "超宽": "超ワイド",
        "超高": "超縦長",
        # ---- 补充遗漏（v2.3.1） ----
        "AI绘图资料整理": "AI Prompt Vault",
        "绘": "P",
        "＋ 新建": "＋ 新規",
        "待保存图片": "未保存の画像",
        "待保存 0 条": "未保存 0 件",
        "待保存列表为空": "未保存リストは空です",
        "导入中…": "インポート中...",
        "请先粘贴 Civitai 链接": "先にCivitaiリンクを貼り付けてください",
        "这条还没有图片，无法保存": "この項目にはまだ画像がないため保存できません",
        "请先选中一张图片": "先に画像を選択してください",
        "没有内容可复制": "コピーする内容がありません",
        "Civitai 返回了无法解析的数据": "Civitaiが解析できないデータを返しました",
        "读取 Civitai 图片信息失败：": "Civitai画像情報の読み取りに失敗： ",
        "读取 Civitai 图片信息失败": "Civitai画像情報の読み取りに失敗しました",
        "访问 Civitai 失败：": "Civitaiへのアクセスに失敗： ",
        "无图片地址": "画像URLがありません",
        ": 页面未包含该图片数据": ": ページにこの画像のデータが含まれていません",
        "无法识别的 Civitai 链接": "認識できないCivitaiリンクです",
        "图片下载失败（{err}）": "画像のダウンロードに失敗（{err}）",
        "复制文件失败（{e}）": "ファイルのコピーに失敗（{e}）",
        "导入超时（{seconds}s），请检查网络后重试": "インポートがタイムアウトしました（{seconds}秒）。ネットワークを確認して再試行してください",
        "确定删除「{title}」吗？\n图片将移入资料库回收站。": "「{title}」を削除しますか？\n画像はライブラリのゴミ箱に移動します。",
        "模型清单（所有使用的模型，可编辑，链接可点击打开）": "モデル一覧（使用した全モデル、編集可能、リンクはクリックで開く）",
        "粘贴 Civitai 链接（civitai.com / civitai.red 均可），支持多链接用空格或换行分隔": "Civitaiリンクを貼り付け（civitai.com / civitai.red 対応）。複数のリンクはスペースまたは改行で区切れます",
        "待保存 {n} 条": "未保存 {n} 件",
        "提示词": "プロンプト",
        "没有符合条件的图片\n": "条件に一致する画像がありません\n",

        # ---- v2.4.0 ComfyUI 集成 ----
        "界面语言": "表示言語",
        "ComfyUI 文件夹": "ComfyUIフォルダ",
        "ComfyUI 根目录（用于模型下载）": "ComfyUIルートフォルダ（モデルダウンロード用）",
        "选择 ComfyUI 根目录（含 models/ 子目录）": "ComfyUIのルートフォルダを選択（models/ サブディレクトリを含む）",
        "浏览…": "参照...",
        "设置后可在图库一键下载图片使用的模型到 ComfyUI 对应类别的模型文件夹。":
            "設定すると、ギャラリーで画像のモデルをワンクリックでComfyUIの対応モデルフォルダにダウンロードできます。",
        "下载模型": "モデルをダウンロード",
        "下载当前图片使用的模型到 ComfyUI（需先在设置中选择 ComfyUI 文件夹）":
            "この画像のモデルをComfyUIにダウンロード（先に設定でComfyUIフォルダを選択してください）",
        "选择模型类型": "モデルタイプを選択",
        "模型「{name}」属于『其他』类型，请选择要保存到的 ComfyUI 模型文件夹：":
            "モデル「{name}」は「その他」タイプです。保存先のComfyUIモデルフォルダを選択してください：",
        "模型类型": "モデルタイプ",
        "正在下载：{name}": "ダウンロード中：{name}",
        "正在下载：{name}（{mb:.0f} MB）": "ダウンロード中：{name}（{mb:.0f} MB）",
        "模型「{name}」已存在，跳过下载。": "モデル「{name}」は既に存在するため、ダウンロードをスキップしました。",
        "模型「{name}」已下载到：\n{path}": "モデル「{name}」をダウンロードしました：\n{path}",
        "模型「{name}」下载失败：{err}": "モデル「{name}」のダウンロードに失敗：{err}",
        "模型「{name}」解析下载链接失败：{err}": "モデル「{name}」のダウンロードリンクの解析に失敗：{err}",
        "该图片没有可下载的模型（无链接）。": "この画像にはダウンロードできるモデルがありません（リンクなし）。",
        "该图片没有可下载的模型": "この画像にはダウンロードできるモデルがありません",
        "请先在「设置」中选择 ComfyUI 文件夹，再下载模型。":
            "先に「設定」でComfyUIフォルダを選択してからモデルをダウンロードしてください。",
        "下载": "ダウンロード",
        "下载到 ComfyUI 对应模型文件夹": "ComfyUIの対応モデルフォルダにダウンロード",
        "仅用于下载模型": "モデルのダウンロードのみに使用",

        # ---- v2.4.1 模型管理面板 ----
        "模型管理": "モデル管理",
        "管理 ComfyUI 中已安装的模型：重命名、删除、添加备注。":
            "ComfyUIにインストール済みのモデルを管理：名前変更、削除、メモ追加。",
        "搜索模型名…": "モデル名を検索...",
        "类型": "タイプ",
        "刷新": "更新",
        "（根目录）": "（ルート）",
        "未选中模型": "モデル未選択",
        "备注": "メモ",
        "添加备注（保存在资料库，不修改文件）…": "メモを追加（ライブラリに保存、ファイルは変更しません）...",
        "保存备注": "メモを保存",
        "重命名": "名前を変更",
        "复制文件名": "ファイル名をコピー",
        "打开所在文件夹": "フォルダを開く",
        "尚未链接 ComfyUI。请先在「设置」中选择 ComfyUI 文件夹。":
            "ComfyUIが未リンクです。先に「設定」でComfyUIフォルダを選択してください。",
        "新文件名：": "新しいファイル名：",
        "同名文件已存在": "同名のファイルが既に存在します",
        "重命名失败：{err}": "名前の変更に失敗：{err}",
        "重命名成功 ✓": "名前を変更しました ✓",
        "文件名已复制 ✓": "ファイル名をコピーしました ✓",
        "确定删除模型「{name}」吗？\n此操作会直接删除文件，无法恢复。":
            "モデル「{name}」を削除しますか？\nこの操作はファイルを直接削除し、元に戻せません。",
        "删除失败：{err}": "削除に失敗：{err}",
        "已删除 ✓": "削除しました ✓",
        "备注已保存 ✓": "メモを保存しました ✓",

        # ---- v2.4.3 下载列表页 ----
        "下载列表": "ダウンロード一覧",
        "正在下载的模型与最近完成的历史。取消会自动清理残留缓存。":
            "ダウンロード中のモデルと最近完了した履歴。キャンセルすると不完全なファイルを自動でクリーンアップします。",
        "正在下载": "ダウンロード中",
        "历史记录": "履歴",
        "清空历史": "履歴をクリア",
        "暂无下载任务。从图库/详情面板点击「下载模型」即可在此查看进度。":
            "ダウンロードはまだありません。ギャラリー / 詳細パネルで「モデルをダウンロード」をクリックすると、ここで進捗を確認できます。",
        "完成": "完了",
        "失败": "失敗",
        "已取消": "キャンセル済み",
        "暂停": "一時停止",
        "继续": "再開",
        "已暂停": "一時停止中",
        "该文件已不存在（可能已移动/删除）。":
            "ファイルは既に存在しません（移動または削除された可能性があります）。",

        # ---- v2.4.8 翻译漏洞修复 ----
        "模型链接为空": "モデルURLが空です",
        "该模型暂无可下载文件": "このモデルにはダウンロード可能なファイルがありません",
        "未知模型类型：": "不明なモデルタイプ： ",
        "返回 HTML 错误页（可能需要 Civitai API Key）":
            "HTMLエラーページが返されました（Civitai API Key が必要かもしれません）",
        "下载不完整（{got}/{total}）": "不完全なダウンロード（{got}/{total}）",
        "文件过小（{got} 字节），疑似错误响应":
            "ファイルが小さすぎます（{got} バイト）、エラー応答の可能性があります",
        "下载到的是错误页（HTML/JSON），可能需要 Civitai API Key":
            "エラーページ（HTML/JSON）をダウンロードしました。Civitai API Key が必要かもしれません",
        "下载失败": "ダウンロード失敗",
        "分": "分",
        "秒": "秒",
        "civ_...（可选，解决模型下载 403 / HTML 错误页）":
            "civ_...（任意、モデルダウンロードの403 / HTMLエラーページを解決）",
        "在 Civitai 用户中心（https://civitai.red/user/account → API Keys → New API Key）生成，粘贴到这里即可让模型下载携带登录凭证。":
            "civitai.red/user/account → API Keys → New API Key で生成し、ここに貼り付けるとモデルダウンロードがログイン認証情報を利用できます。",
        "切换语言后重启软件即可生效。": "言語を切り替えたらアプリを再起動すると反映されます。",
        "语言已切换，重启软件后生效。": "言語を切り替えました。再起動後に反映されます。",
        ": 页面未包含该图片数据": ": ページにこの画像のデータが含まれていません",
        "无图片地址": "画像URLがありません",
        "(无图片)": "（画像なし）",
        "(无标题)": "（タイトルなし）",
        "(未选中)": "（未選択）",
        "下载中": "ダウンロード中",
        "等待": "待機中",
        "下载模型 ▸": "モデルをダウンロード ▸",
        "去设置": "設定へ",
        "打开模型页": "モデルページを開く",
        "选择 ComfyUI 根目录": "ComfyUIのルートフォルダを選択",
        "重命名模型": "モデル名を変更",
        "下载失败：需要登录态（API Key）": "ダウンロード失敗：ログイン（API Key）が必要です",
        "模型「{name}」下载失败：{err}\n\nCivitai 官方下载需要登录凭证。你可以：\n① 在「设置」填入 Civitai API Key 后重试\n② 直接打开 Civitai 模型页手动下载":
            "モデル「{name}」のダウンロードに失敗：{err}\n\nCivitaiのダウンロードにはログイン認証が必要です。次のいずれかを行ってください：\n① 「設定」でCivitai API Keyを入力して再試行\n② Civitaiのモデルページを開いて手動でダウンロード",
        "把网页上的例图直接拖到这里\n\n或按 Ctrl+V 粘贴剪贴板里的图片\n\n也支持拖入 / 粘贴 Civitai 链接，自动提取提示词与全部模型":
            "Webの参考画像をここに直接ドラッグ\n\nまたは Ctrl+V でクリップボードから貼り付け\n\nCivitaiリンクの貼り付けにも対応し、プロンプトと全モデルを自動抽出",
        # ---- v3.0 视频支持 ----
        "不是受支持的视频文件": "サポートされていない動画ファイルです",
        "视频": "動画",
        "全部媒体": "すべてのメディア",
        "图片": "画像",
        "视频分类": "動画",
        "播放": "再生",
        "时长": "再生時間",
        "媒体": "メディア",
        "视频：{t}": "動画：{t}",
        "解析中…": "解析中...",
        "批量操作（{n} 项）▸": "一括操作（{n} 件）▸",
        "批量删除": "一括削除",
        "批量改分组 ▸": "グループへ移動 ▸",
        "确定删除选中的 {n} 条记录吗？\n图片/视频将移入资料库回收站（trash）。":
            "選択した {n} 件のレコードを削除しますか？\n画像 / 動画はライブラリのゴミ箱（trash）に移動します。",
        "批量改分组": "グループへ移動",
        "将 {n} 条记录移动到：": "{n} 件のレコードを移動先：",
        "批量导出": "選択をエクスポート",
        "选择导出文件夹": "エクスポート先フォルダを選択",
        "已导出 {n} 条记录到：{d}": "{n} 件のレコードをエクスポートしました：{d}",
        "导出失败：{err}": "エクスポートに失敗：{err}",
        "全部标签": "すべてのタグ",
        "查重": "重複検索",
        "检测库中的重复图片（感知哈希）": "ライブラリ内の重複画像を検出（知覚ハッシュ）",
        "未发现重复图片 ✓": "重複画像は見つかりませんでした ✓",
        "发现 {n} 组重复图片": "重複画像が {n} グループ見つかりました",
        "以下图片哈希相同（同一张图的不同版本）。点击「清理」保留每组第一张，删除其余（移入回收站）。":
            "以下の画像はハッシュが同一です（同じ画像の別バージョン）。「クリーンアップ」をクリックすると各グループの1枚目を残し、残りを削除します（ゴミ箱へ移動）。",
        "清理选中组": "選択をクリーンアップ",
        "请先选择一组重复图片": "先に重複画像のグループを選択してください",
        "已清理 {removed} 张重复图片（移入回收站）":
            "重複画像 {removed} 枚をクリーンアップしました（ゴミ箱へ移動）",
        " {n} 张重复": " {n} 枚の重複",
        "资料库位置": "ライブラリの場所",
        "更换…": "変更...",
        "更换资料库后重启软件生效。当前库：{p}":
            "ライブラリを変更したら再起動で反映されます。現在のライブラリ：{p}",
        "选择资料库文件夹": "ライブラリフォルダを選択",
        "资料库已切换，重启软件后生效。":
            "ライブラリを変更しました。再起動後に反映されます。",
        "界面主题": "テーマ",
        "暗色": "ダーク",
        "亮色": "ライト",
        "界面主题即时生效。": "テーマはすぐに反映されます。",
        "启用悬浮预览（列表模式）": "ホバープレビューを有効にする（リスト表示）",
        "关闭后不再显示悬停预览图，可减少资源占用；设置立即生效。":
            "プレビューを無効にしてリソースを節約します。すぐに反映されます。",
        "A1111 outputs 目录": "A1111 outputs フォルダ",
        "可选：Automatic1111 输出目录，用于一键导入生成图":
            "任意：Automatic1111 の出力フォルダ。生成画像のワンクリックインポート用",
        "设置后可在图库一键把 A1111 生成的图片（含提示词等参数）导入收藏。":
            "設定すると、ギャラリーでA1111が生成した画像（プロンプト等のパラメータ含む）をワンクリックでライブラリにインポートできます。",
        "选择 A1111 outputs 目录": "A1111 outputs フォルダを選択",
        "从 A1111 导入": "A1111からインポート",
        "把 A1111 outputs 目录的生成图（含提示词参数）一键导入收藏":
            "A1111 outputs フォルダの生成画像（プロンプトパラメータ含む）をワンクリックでインポート",
        "请先在「设置」中配置 A1111 outputs 目录。":
            "先に「設定」でA1111 outputs フォルダを設定してください。",
        "已导入 {imported} 张，{skipped} 张重复跳过":
            "{imported} 枚をインポート、{skipped} 枚は重複のためスキップ",
        "导入完成：{imported} 张新增，{skipped} 张重复跳过，{errors} 张失败":
            "インポート完了：{imported} 枚追加、{skipped} 枚は重複スキップ、{errors} 枚失敗",
        "空文件": "空ファイル",
        "疑似损坏": "破損の可能性",
        "下载残留": "ダウンロード残骸",
        "⚠ 空文件（0 字节）：下载中断或写盘失败，建议删除后重新下载。":
            "⚠ 空ファイル（0バイト）：ダウンロードが中断されたか書き込みに失敗しました。削除して再ダウンロードしてください。",
        "⚠ 疑似损坏（小于 1KB）：可能是错误响应被误存，建议删除后重新下载。":
            "⚠ 破損の可能性（1KB未満）：エラー応答が保存された可能性があります。削除して再ダウンロードしてください。",
        "⚠ 存在 .part 下载残留：上一次下载未完成，文件可能不完整。":
            "⚠ .part のダウンロード残骸があります：前回のダウンロードが未完了で、ファイルが不完全な可能性があります。",
        "⚠ {n} 个模型健康异常": "⚠ {n} 個のモデルに異常があります",
        "全部模型正常 ✓": "すべてのモデルは正常です ✓",
        "视频地址为空": "動画URLが空です",
        "无视频地址": "動画URLがありません",
        "视频下载失败（{err}）": "動画のダウンロードに失敗（{err}）",
        "视频下载失败": "動画のダウンロードに失敗",
        "我的作品": "マイ作品",
        "我的作品（虚拟引用，不复制文件）":
            "マイ作品（仮想参照、ファイルはコピーしません）",
        "共 {n} 张（虚拟作品仅显示前 {cap} 张）":
            "全 {n} 件（仮想作品は先頭 {cap} 件のみ表示）",

        # ---- v3.2 新增翻译 key（civitai 硬编码修复） ----
        "下载内容不是有效图片": "ダウンロードしたコンテンツは有効な画像ではありません",
        "视频内容异常（{size} 字节）": "動画コンテンツが異常です（{size} バイト）",

        # ---- v3.3 多输出目录 ----
        "自动导入文件夹": "自動インポートフォルダー",
        "浏览": "参照",
        "移除该文件夹": "このフォルダを削除",
        "添加文件夹": "フォルダを追加",
        "可添加多个输出文件夹，图库将按文件夹自动分组。":
            "出力フォルダは複数追加できます。ギャラリーはフォルダごとに自動でグループ化します。",
        "output 目录已变更，正在后台扫描…":
            "出力フォルダが変更されました。バックグラウンドでスキャン中...",

        # ---- v3.4 幽灵记录标记 / 扫描提示 ----
        "文件缺失": "ファイル欠落",
        "正在后台扫描输出文件夹…": "出力フォルダをバックグラウンドでスキャン中...",

        # ---- v3.9 虚拟作品显示上限可配置 ----
        "限制我的作品显示数量": "マイ作品の表示数を制限",
        "我的作品最多显示": "マイ作品の最大表示",
        "张": " 枚",

        # ---- v4.1 自绘标题栏 ----
        "最小化": "最小化する",
        "最大化": "最大化する",
        "还原": "元に戻す",

        # ---- v4.2 i18n 审计补全（缺失 key / 专有名词） ----
        "重新扫描输出文件夹，立即显示新增图片（手动刷新）":
            "出力フォルダを再スキャンして、新しく追加された画像をすぐに表示（手動更新）",
        "Civitai API Key": "Civitai API キー",
        "AI-Prompt-Vault": "AI-Prompt-Vault",
    },
}


def init(lang_file, lang: str = "zh"):
    """初始化：设置语言文件路径与当前语言。"""
    global _lang_file, _current
    _lang_file = lang_file
    _current = lang if lang in LANGUAGES else "zh"


def current_lang() -> str:
    return _current


def set_language(lang: str) -> bool:
    """切换语言并持久化到 settings.json。"""
    global _current
    if lang not in LANGUAGES:
        return False
    _current = lang
    if _lang_file:
        try:
            data = {}
            if _lang_file.exists():
                data = json.loads(_lang_file.read_text(encoding="utf-8"))
            data["language"] = lang
            _lang_file.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        except Exception:
            pass
    return True


def t(text: str) -> str:
    """按当前语言翻译；中文或无翻译时返回原文。"""
    # 中文别名：把口语化术语替换为更准确的称呼（存储 key 保持不变）
    if _current == "zh":
        return _ZH_ALIASES.get(text, text)
    return _LANG_TABLES.get(_current, {}).get(text, text)


# 中文界面别名：让 UI 文本更专业，但存储 key 仍是"大模型"等保证向后兼容
_ZH_ALIASES = {
    "大模型": "基础模型",  # Checkpoint / Base Model
}


def rev(text: str) -> str:
    """反向查找：把当前语言显示的文本映射回中文 key（用于下拉/筛选反查）。"""
    if _current == "zh" or not text:
        return text
    table = _LANG_TABLES.get(_current, {})
    for k, v in table.items():
        if v == text:
            return k
    return text


def tr_format(text: str, **kw) -> str:
    """翻译后格式化（先翻译，再 .format）。"""
    try:
        return t(text).format(**kw)
    except Exception:
        return text
