"""图片重复检测：dHash 感知哈希 + 分组找重复。

AI 绘画收集的重复图通常是同一张的不同尺寸/压缩版本，
dHash 对缩放/轻微压缩鲁棒，适合此场景。
"""
from PySide6.QtGui import QImage, QColor
from PySide6.QtCore import Qt


def image_dhash(path: str, size: int = 16) -> str:
    """返回图片的 dHash（hex 字符串）；无效图片返回 ''。"""
    try:
        img = QImage(path)
        if img.isNull():
            return ""
        img = img.scaled(size + 1, size, Qt.IgnoreAspectRatio,
                         Qt.SmoothTransformation)
        img = img.convertToFormat(QImage.Format_Grayscale8)
        bits = []
        for y in range(size):
            for x in range(size):
                a = img.pixelColor(x, y).value()
                b = img.pixelColor(x + 1, y).value()
                bits.append(1 if b > a else 0)
        # 打包为 hex
        h = 0
        for i, b in enumerate(bits):
            h = (h << 1) | b
        return format(h, 'x')
    except Exception:
        return ""


def hamming(a: str, b: str) -> int:
    """两个 hex 哈希的汉明距离（位数差）。"""
    ia, ib = int(a, 16), int(b, 16)
    return bin(ia ^ ib).count("1")


def find_duplicate_groups(records: list, thumb_resolver) -> list:
    """按缩略图 dHash 分组找重复。

    - thumb_resolver(rec) -> 缩略图路径（无则 ''）
    - 返回重复组列表：[[rec, rec, ...], ...]（每组 ≥2 条，按哈希一致分组）
    """
    groups = {}
    for r in records:
        p = thumb_resolver(r)
        if not p:
            continue
        h = image_dhash(str(p))
        if not h:
            continue
        groups.setdefault(h, []).append(r)
    return [g for g in groups.values() if len(g) >= 2]