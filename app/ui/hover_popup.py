"""图片预览浮窗：鼠标悬停时仅显示图片（无文字信息），轻量流畅。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel

MAX_W = 380
MAX_H = 380


class HoverPopup(QWidget):
    """无边框置顶图片预览浮窗，跟随鼠标，不拦截鼠标事件。"""

    def __init__(self):
        super().__init__(None,
                         Qt.FramelessWindowHint | Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.img_label = QLabel()
        self.img_label.setStyleSheet(
            "background:#0e0e16; border:1px solid #33334c; border-radius:12px;")
        lay.addWidget(self.img_label)

    def show_image(self, pixmap: QPixmap, global_pos, screen_rect):
        """显示已缩放的图片（pixmap 由调用方缓存，避免磁盘 IO 与重复缩放卡顿）。"""
        if pixmap is None or pixmap.isNull():
            self.hide()
            return
        self.img_label.setPixmap(pixmap)
        self.adjustSize()
        self._place(global_pos, screen_rect)
        self.show()
        self.raise_()

    def reposition(self, global_pos, screen_rect):
        """鼠标同图片内移动时仅更新位置（无重绘开销）。"""
        self._place(global_pos, screen_rect)

    def _place(self, global_pos, screen_rect):
        size = self.sizeHint()
        x = global_pos.x() + 24
        y = global_pos.y() + 24
        if x + size.width() > screen_rect.right():
            x = global_pos.x() - size.width() - 24
        if y + size.height() > screen_rect.bottom():
            y = global_pos.y() - size.height() - 24
        x = max(screen_rect.left(), min(x, screen_rect.right() - size.width()))
        y = max(screen_rect.top(), min(y, screen_rect.bottom() - size.height()))
        if x != self.x() or y != self.y():
            self.move(x, y)
