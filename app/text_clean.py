"""剪贴板文本清理工具：复制到下游工具（SD WebUI / ComfyUI 等）前的安全化处理。

背景：部分导入的提示词/文件名可能含 NULL(\\x00) 等 ASCII 控制字符（例如从网页
复制文本时带入）。这类字符在剪贴板层面能正常往返（QClipboard.setText 对任意
unicode 均可 round-trip），但粘贴到下游工具时会被拒绝、截断，或在字体替换下
显示为豆腐块(□)。本模块在复制前统一移除这些无效控制字符，同时保留所有可见
字符（中文、emoji、私用区 \\uE000-\\uF8FF、非 BMP 字符、换行 \\n、回车 \\r、
制表 \\t、空格），保证 prompt 语义不被破坏。

不替换/不截断/不转义——只移除 ASCII 控制字符，避免改动用户可见内容。
"""
from __future__ import annotations

# 需要移除的 ASCII 控制字符：C0 区 0x00-0x1F（保留 \t=0x09、\n=0x0A、\r=0x0D）
# + DEL 0x7F。这些字符在下游工具中无意义且常导致拒绝/截断/乱码。
_INVALID_CONTROL_CHARS = frozenset(
    chr(c) for c in range(0x00, 0x20) if c not in (0x09, 0x0A, 0x0D)
) | frozenset("\x7f")


def sanitize_for_clipboard(text: str) -> tuple[str, int]:
    """移除文本中的无效 ASCII 控制字符，返回 (清理后文本, 移除字符数)。

    Args:
        text: 原始文本；None/空串原样返回空串。

    Returns:
        (cleaned, removed_count)：
        - cleaned: 移除 NULL(0x00)、其他 C0 控制字符(0x01-0x08/0x0B/0x0C/0x0E-0x1F)
          与 DEL(0x7F) 后的文本；保留 \\t \\n \\r 及全部可见 unicode（中文、
          emoji、私用区、非 BMP 字符等）。
        - removed_count: 移除的字符数；为 0 时 cleaned 与输入是同一对象。
    """
    if not text:
        return "", 0
    removed = 0
    cleaned = []
    for ch in text:
        if ch in _INVALID_CONTROL_CHARS:
            removed += 1
        else:
            cleaned.append(ch)
    if removed == 0:
        return text, 0
    return "".join(cleaned), removed


def safe_copy_to_clipboard(text: str) -> tuple[bool, int]:
    """清理控制字符后写入系统剪贴板。

    Args:
        text: 原始文本。

    Returns:
        (ok, removed_count)：
        - ok: True=写入成功；False=文本无可复制内容（清理后为空）或剪贴板写入异常。
        - removed_count: 清理掉的无效控制字符数；失败时可结合原始文本判断是
          「无可见内容」（removed>0 且清理后为空）还是「写入异常」。
    """
    cleaned, removed = sanitize_for_clipboard(text)
    if not cleaned:
        return False, removed
    try:
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(cleaned)
        return True, removed
    except Exception:
        return False, removed
