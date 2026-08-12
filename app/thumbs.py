"""图片工具：缩略图生成、圆角贴图、尺寸读取。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap, QPainter, QPainterPath
from PySide6.QtCore import QRectF


def load_pixmap(path: str, max_side: int = 0) -> QPixmap:
    pm = QPixmap(path)
    if pm.isNull():
        return pm
    if max_side > 0 and (pm.width() > max_side or pm.height() > max_side):
        pm = pm.scaled(max_side, max_side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return pm


def make_thumbnail(src: str, dst: str, max_side: int = 360) -> bool:
    """从原图生成缩略图（PNG，保留透明）。"""
    img = QImage(src)
    if img.isNull():
        return False
    if img.width() > max_side or img.height() > max_side:
        img = img.scaled(max_side, max_side, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    return img.save(dst, "PNG")


def rounded_pixmap(path: str, size: int, radius: int = 14) -> QPixmap:
    """按缩略图生成指定尺寸的圆角方形贴图（居中留白）。"""
    src = QPixmap(path)
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    if not src.isNull():
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        # 目标绘制区域（带内边距）
        pad = max(2, int(size * 0.02))
        target = QRectF(pad, pad, size - 2 * pad, size - 2 * pad)
        # 取景：按目标比例居中裁剪原图
        sx = target.width() / src.width()
        sy = target.height() / src.height()
        scale = max(sx, sy)
        src_rect = QRectF(0, 0, target.width() / scale, target.height() / scale)
        src_rect.moveCenter(src.rect().center())
        clip = QPainterPath()
        clip.addRoundedRect(target, radius, radius)
        p.setClipPath(clip)
        p.drawPixmap(target, src, src_rect)
        p.end()
    return out


def image_size(path: str) -> tuple:
    """读取图片尺寸（宽, 高）。

    v3.6：改用 QImageReader.size() 只读文件头（实测 ~1ms，不再全解码大图），
    失败时回退 QImage 全解码（与旧行为一致，返回 (0,0) 表示无法读取）。
    调用方行为不变：始终返回 (int, int)。
    """
    try:
        from PySide6.QtGui import QImageReader
        reader = QImageReader(path)
        size = reader.size()
        if size.isValid():
            return (size.width(), size.height())
    except Exception:
        pass
    img = QImage(path)
    if img.isNull():
        return (0, 0)
    return (img.width(), img.height())
