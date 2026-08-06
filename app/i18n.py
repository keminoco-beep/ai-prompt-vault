"""多语言支持（i18n）。

- 轻量级翻译表：key 为中文原文，t() 按当前语言返回翻译；无翻译时返回原文。
- 语言持久化：保存在资料库 settings.json（随数据迁移）。
- 扩展：往 _LANG_TABLES 里加 "ja"/"ko" 等即可支持更多语言。
"""
import json

LANGUAGES = {
    "zh": "中文",
    "en": "English",
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
        "没有可复制的内容": "Nothing to copy",
        "没有可保存的完整项（缺图片）": "No complete item to save (missing image)",
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
    if _current == "zh" or not text:
        return text
    return _LANG_TABLES.get(_current, {}).get(text, text)


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
