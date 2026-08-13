"""自绘标题栏：无边框主窗口的标题区（拖动 / 双击最大化 / 窗口控制按钮）。

v4.1 无边框窗口的一部分：Windows 上用自绘标题栏替换系统标题栏，风格与软件
UI 一致（暗色 #16161f / 紫强调、圆角、几何字符，不用 emoji，低开销）。

v4.2（本次）：
  - 右侧三按钮由几何字符（─ □ ✕）改为 QPainter 自绘 16×16 图标
    （横线 / 方框 / 双层方框 / ×），跨字体居中精确、暗色下清晰；
    颜色随主题（暗 #e8e8f2 / 亮 #2a2a3d），apply_theme() 即时刷新。
  - 左侧 logo 外框改为 30×30（28 图标 + 2px 描边），配合 QSS
    #appLogo 的细描边 + 底色，暗色 shell 下边界清晰。

v4.3（本次）：
  - Bug 1：亮色主题按钮图标由 #4a4a62 加深为 #2a2a3d，与亮色标题栏
    #f4f4fa 对比度由 ≈4.7:1 提升至 ≈12.8:1，右上角 ─ □ ✕ 清晰可见。
  - Bug 2：移除 v4.2 在 logo PNG 上合成的 #b0b0c8 描边环（与中间 A 在
    暗色下混在一起）；logo 容器 #appLogo 的 QSS 改为暗/亮主题都固定
    深色底 #2a2a3e，为 PNG 内 A 提供稳定深色衬底。

v4.3.1（短暂）：
  - 曾尝试用 QPainterPath + 贝塞尔曲线在 PNG 上叠加"艺术 A"，还原原 PNG
    笔触设计。已废弃（见 v4.3.2）。

v4.3.2（本次）：
  - 彻底移除所有 QPainter 覆盖绘制（v4.3 描边环、v4.3.1 艺术 A）。
    用户明确要求"不要画新的，直接显示 AI 生成的 logo 原图"。
  - 标题栏 logo 现在直接显示 app/app_icon.png 原图，无任何 QPainter
    覆盖（无描边环、无 A 重绘、无着色）。
  - 对比度仍靠 #appLogo 容器的固定深色底 #2a2a3e + 边框
    （暗 #3a3a58 / 亮 #c8c8e0）提供，PNG 边缘在两主题下都清晰。

v4.3.3（本次）：
  - LOGO_SIZE 由 28 → 36（小尺寸抗锯齿优化）：新 AI 设计的圆角方形 logo
    笔画较粗（艺术 A + sparkle 点），36×36 显示时 PNG 缩放损失更小、
    A 笔画保留更多细节；LOGO_BOX 同步 30 → 38。
  - 标题栏总高 44px 不变，logo 占比 ≈80%（视觉协调，不影响布局）；
    仍只加载 app/app_icon.png 原图，不做任何 QPainter 重画/描边/覆盖。
  - 仅调整两个常量，QSS #appLogo 容器深色底 #2a2a3e 不变（对比度方案复用）。

布局：
  左侧  AI 设计 logo（从 app/app_icon.png 加载的 QPixmap）+ 应用名（#brandName）+ 版本号（#brandSub）
  右侧  最小化 ─ / 最大化 □·❐ / 关闭 ✕（QToolButton + 自绘 QIcon，objectName tbMin/tbMax/tbClose）

行为：
  - 空白区按住拖动窗口（mousePress 记录偏移 + mouseMove move）
  - 空白区双击切换最大化/还原（按钮区域不响应）
  - 最大化/还原状态变化（按钮、双击、系统边缘拖拽缩放、快捷键）时同步按钮图标
    （changeEvent 监听 WindowStateChange；MainWindow.changeEvent 也会兜底调用）

注：macOS 不使用本组件（保持原生边框，保证可编译可运行）。
"""
from pathlib import Path

from PySide6.QtCore import Qt, QEvent, QPoint, QSize, QRectF, QPointF
from PySide6.QtGui import QPixmap, QIcon, QPainter, QPen, QColor
from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QToolButton

from app.config import APP_NAME, VERSION, app_icon_png_path
from app.i18n import t as tr


class TitleBar(QWidget):
    """自绘标题栏（高 44px）。

    依赖全局 QSS 中的 #titleBar / #brandName / #brandSub /
    QToolButton#tbMin / #tbMax / #tbClose 规则完成外观；仅在此处处理交互。
    """

    HEIGHT = 44
    # v4.3.3：标题栏左侧 logo 显示尺寸（来自 app/app_icon.png 的 36x36 缩略图）
    # 原 v4.1 LOGO_SIZE=28（旧版 icon 笔画细、28px 抗锯齿损失可接受）。
    # 新版 icon 为「粗笔画艺术 A + sparkle」设计，36×36 显示时笔画细节保留更好。
    LOGO_SIZE = 36
    # v4.3.3：logo 外框尺寸（36 图标 + 左右各 1px QSS 描边）
    LOGO_BOX = LOGO_SIZE + 2

    def __init__(self, parent: QWidget = None):
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(self.HEIGHT)
        # v4.2：窗口按钮图标颜色（随主题），暗色默认
        self._icon_color = "#e8e8f2"
        # 拖动窗口时：全局鼠标坐标 - 窗口左上角（记录一次，随后按差值移动）
        self._drag_offset: QPoint = None
        self._build()
        self._update_max_icon()

    # ================= UI =================
    def _build(self):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 0, 0)
        lay.setSpacing(10)

        # 左侧 logo：v4.1 改用 PNG 加载（app/app_icon.png，AI 设计圆角方形图标），
        # 不再用 QSS 渐变 + "绘" 字符。objectName 改为 "appLogo" 避免与已删除的
        # 侧栏 #logoDot 混淆；pixmap 不随主题变色，apply_theme 无需处理。
        # v4.2：label 尺寸 30×30，QSS #appLogo 画 1px 描边 + 底色，图标 28×28。
        # v4.3.3：label 尺寸 38×38，图标 36×36（新粗笔画 A 抗锯齿优化）。
        self.logo_label = QLabel()
        self.logo_label.setObjectName("appLogo")
        self.logo_label.setFixedSize(self.LOGO_BOX, self.LOGO_BOX)
        self.logo_label.setAlignment(Qt.AlignCenter)
        self._load_logo_pixmap(self.LOGO_SIZE)
        lay.addWidget(self.logo_label)

        # 应用名 + 版本号（复用侧栏 brandName/brandSub 样式，保证视觉一致）
        name = QLabel(tr(APP_NAME))
        name.setObjectName("brandName")
        lay.addWidget(name)

        sub = QLabel(f"v{VERSION}")
        sub.setObjectName("brandSub")
        lay.addWidget(sub)

        lay.addStretch(1)

        # 右侧窗口按钮（v4.2：自绘 QIcon，不再用几何字符，居中精确）
        self.btn_min = self._make_button("tbMin", "min", tr("最小化"))
        self.btn_min.clicked.connect(self._on_minimize)
        lay.addWidget(self.btn_min)

        self.btn_max = self._make_button("tbMax", "max", tr("最大化"))
        self.btn_max.clicked.connect(self._on_toggle_max)
        lay.addWidget(self.btn_max)

        self.btn_close = self._make_button("tbClose", "close", tr("关闭"))
        self.btn_close.clicked.connect(self._on_close)
        lay.addWidget(self.btn_close)

    def _load_logo_pixmap(self, size: int) -> None:
        """从 app/app_icon.png 直接加载标题栏 logo，不做任何 QPainter 覆盖。

        资源定位走 app_icon_png_path()：开发模式用项目根的 app/app_icon.png，
        打包模式（PyInstaller）走 sys._MEIPASS/app/app_icon.png。

        v4.3.2：彻底移除所有 QPainter 覆盖绘制（v4.3 描边环 + v4.3.1 艺术 A），
        用户明确要求"直接显示 AI 生成的 logo 原图，不要画新的"。
        加载流程仅做：读取 PNG → smooth 缩放到 size×size → setPixmap，
        无任何像素级修改。

        对比度由 #appLogo 容器的固定深色底 #2a2a3e + 边框
        （暗 #3a3a58 / 亮 #c8c8e0）保证 PNG 边界在两主题下都清晰。
        """
        try:
            png = app_icon_png_path()
            if png.is_file():
                pm = QPixmap(str(png))
                if not pm.isNull():
                    pm = pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    self.logo_label.setPixmap(pm)
        except Exception:
            # 加载失败（文件缺失/损坏）时保持空白 pixmap，不抛异常阻塞 UI 启动
            pass

    # ================= 窗口按钮图标（v4.2 自绘） =================
    def apply_theme(self, theme_name: str = "dark"):
        """主题切换时刷新按钮图标颜色（暗 #e8e8f2 / 亮 #2a2a3d）。

        v4.3：亮色图标由 #4a4a62 加深为 #2a2a3d，与亮色标题栏 #f4f4fa 的
        对比度由 ≈4.7:1 提升至 ≈12.8:1（≥12:1），右上角 ─ □ ✕ 醒目清晰。
        """
        self._icon_color = "#e8e8f2" if theme_name != "light" else "#2a2a3d"
        self._refresh_button_icons()

    def _refresh_button_icons(self):
        for b, kind in ((self.btn_min, "min"),
                        (self.btn_max, "restore" if self._is_maximized() else "max"),
                        (self.btn_close, "close")):
            b.setIcon(QIcon(self._paint_icon(kind, self._icon_color)))

    def _paint_icon(self, kind: str, color: str) -> QPixmap:
        """自绘 16×16 窗口图标（横线 / 方框 / 双层方框 / ×），跨字体居中精确。"""
        pm = QPixmap(16, 16)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        pen = QPen(QColor(color))
        pen.setWidthF(1.6)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        if kind == "min":
            p.drawLine(QPointF(3.0, 8.0), QPointF(13.0, 8.0))
        elif kind == "max":
            p.drawRoundedRect(QRectF(3.5, 3.5, 9.0, 9.0), 1.5, 1.5)
        elif kind == "restore":
            # 双层方框：小框（左上方）叠大框（右下方），与原生「还原」图标一致
            p.drawRoundedRect(QRectF(3.5, 3.5, 8.0, 8.0), 1.5, 1.5)
            p.drawRoundedRect(QRectF(6.5, 6.5, 8.0, 8.0), 1.5, 1.5)
        elif kind == "close":
            p.drawLine(QPointF(4.5, 4.5), QPointF(11.5, 11.5))
            p.drawLine(QPointF(11.5, 4.5), QPointF(4.5, 11.5))
        p.end()
        return pm

    def _make_button(self, object_name: str, kind: str, tooltip: str) -> QToolButton:
        b = QToolButton()
        b.setObjectName(object_name)
        b.setIcon(QIcon(self._paint_icon(kind, self._icon_color)))
        b.setIconSize(QSize(14, 14))
        b.setToolTip(tooltip)
        b.setCursor(Qt.PointingHandCursor)
        b.setFixedSize(46, 32)
        b.setFocusPolicy(Qt.NoFocus)
        return b

    # ================= 窗口控制 =================
    def _on_minimize(self):
        w = self.window()
        if w is not None:
            w.showMinimized()

    def _on_toggle_max(self):
        w = self.window()
        if w is None:
            return
        if w.isMaximized():
            w.showNormal()
        else:
            w.showMaximized()
        self._update_max_icon()

    def _on_close(self):
        w = self.window()
        if w is not None:
            w.close()

    def _is_maximized(self) -> bool:
        w = self.window()
        return w is not None and w.isMaximized()

    def _update_max_icon(self):
        """同步最大化/还原按钮图标与 tooltip。"""
        maximized = self._is_maximized()
        self.btn_max.setIcon(
            QIcon(self._paint_icon("restore" if maximized else "max", self._icon_color)))
        self.btn_max.setToolTip(tr("还原") if maximized else tr("最大化"))

    def changeEvent(self, event):
        """窗口最大化/还原状态变化（按钮、双击、系统边缘拖拽缩放、快捷键）时同步按钮图标。

        注：WindowStateChange 主要发给顶层窗口；MainWindow.changeEvent 也会调用
        _update_max_icon 兜底，这里保留是双保险且符合自绘标题栏职责。
        """
        if event.type() == QEvent.WindowStateChange:
            self._update_max_icon()
        super().changeEvent(event)

    # ================= 拖动 / 双击 =================
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            w = self.window()
            if w is not None and not w.isMaximized():
                # 记录「全局鼠标 - 窗口左上角」偏移；随后 mouseMove 按差值整体平移
                self._drag_offset = event.globalPosition().toPoint() - w.frameGeometry().topLeft()
            else:
                self._drag_offset = None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (self._drag_offset is not None
                and event.buttons() & Qt.LeftButton):
            w = self.window()
            if w is not None and not w.isMaximized():
                w.move(event.globalPosition().toPoint() - self._drag_offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_offset = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        # 只在标题栏空白区（不在任何窗口按钮上）双击才切换最大化/还原
        if event.button() == Qt.LeftButton and not self._hit_button(event.position().toPoint()):
            self._on_toggle_max()
        super().mouseDoubleClickEvent(event)

    def _hit_button(self, pos: QPoint) -> bool:
        """判断某点（标题栏坐标系）是否落在窗口按钮上。"""
        for b in (self.btn_min, self.btn_max, self.btn_close):
            if b.geometry().contains(pos):
                return True
        return False
