from app.i18n import t as tr, tr_format
"""主窗口：侧边栏导航 + 分组区 + 收藏/浏览两个板块 + 全局粘贴快捷键。"""
from PySide6.QtCore import Qt, QEvent, QTimer, QSize
from PySide6.QtGui import (QKeySequence, QShortcut, QDesktopServices, QPainter, QPixmap,
                           QColor, QFont, QBrush, QLinearGradient)
from PySide6.QtCore import QRectF, QUrl
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QStackedWidget, QButtonGroup, QLineEdit,
                               QPlainTextEdit, QTextEdit, QComboBox, QApplication,
                               QTreeWidget, QTreeWidgetItem, QMenu, QInputDialog,
                               QToolButton, QMessageBox)

from app.config import APP_NAME, VERSION
from app.ui.collect_panel import CollectPanel
from app.ui.gallery_panel import GalleryPanel
from app.filters import group_counts


class MainWindow(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.setWindowTitle(tr(APP_NAME))
        self.resize(1240, 780)
        self.setMinimumSize(1020, 640)
        self.setWindowIcon(self._make_icon())
        self._build()
        # 全局 Ctrl+V：焦点不在文本输入框时，把剪贴板图片/链接交给收藏面板
        self.paste_shortcut = QShortcut(QKeySequence("Ctrl+V"), self)
        self.paste_shortcut.setContext(Qt.ApplicationShortcut)
        self.paste_shortcut.activated.connect(self._global_paste)

    # ================= UI =================
    def _build(self):
        central = QWidget()
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.setCentralWidget(central)

        # -------- 侧边栏 --------
        side = QWidget()
        side.setObjectName("sidebar")
        side.setFixedWidth(206)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(14, 18, 14, 12)
        sv.setSpacing(8)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        logo = QLabel()
        logo.setObjectName("logoDot")
        logo.setFixedSize(36, 36)
        logo.setAlignment(Qt.AlignCenter)
        logo.setText(tr("绘"))
        logo.setStyleSheet("font-size:16px; font-weight:700; color:#fff;")
        brand.addWidget(logo)
        bt = QVBoxLayout()
        bt.setSpacing(0)
        bn = QLabel(tr(APP_NAME))
        bn.setObjectName("brandName")
        bs = QLabel(tr("例图 · 提示词 · 模型 管理"))
        bs.setObjectName("brandSub")
        bt.addWidget(bn)
        bt.addWidget(bs)
        brand.addLayout(bt)
        brand.addStretch(1)
        sv.addLayout(brand)
        sv.addSpacing(8)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)
        self.collect_btn = self._nav_btn("◈  " + tr("收藏作品"), 0)
        self.gallery_btn = self._nav_btn("▦  " + tr("图库浏览"), 1)
        sv.addWidget(self.collect_btn)
        sv.addWidget(self.gallery_btn)
        sv.addStretch(1)

        # -------- 分组区（折叠） --------
        gh = QHBoxLayout()
        gh.setSpacing(4)
        gt = QLabel(tr("图片分组"))
        gt.setObjectName("groupTitle")
        gh.addWidget(gt)
        gh.addStretch(1)
        self.collapse_btn = QToolButton()
        self.collapse_btn.setObjectName("collapseBtn")
        self.collapse_btn.setText("▼")
        self.collapse_btn.setToolTip(tr("折叠 / 展开分组"))
        self.collapse_btn.setCheckable(True)
        self.collapse_btn.setChecked(True)
        self.collapse_btn.toggled.connect(self._toggle_groups)
        gh.addWidget(self.collapse_btn)
        addg_btn = QToolButton()
        addg_btn.setObjectName("collapseBtn")
        addg_btn.setText(tr("＋ 新建"))
        addg_btn.setToolTip(tr("新建分组"))
        addg_btn.clicked.connect(self._add_group_dialog)
        gh.addWidget(addg_btn)
        sv.addLayout(gh)

        self.group_tree = QTreeWidget()
        self.group_tree.setObjectName("groupTree")
        self.group_tree.setHeaderHidden(True)
        self.group_tree.setIndentation(16)
        self.group_tree.setRootIsDecorated(False)   # 去掉 branch 箭头/色块，仅保留文本
        self.group_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.group_tree.customContextMenuRequested.connect(self._group_menu)
        self.group_tree.itemClicked.connect(self._group_clicked)
        sv.addWidget(self.group_tree, 0)

        open_btn = QPushButton(tr("打开资料库文件夹"))
        open_btn.setObjectName("sideSmall")
        open_btn.clicked.connect(lambda: self.store.open_folder(str(self.store.root)))
        sv.addWidget(open_btn)
        settings_btn = QPushButton("⚙  " + tr("设置"))
        settings_btn.setObjectName("sideSmall")
        settings_btn.clicked.connect(self._open_settings)
        sv.addWidget(settings_btn)
        ver = QLabel(f"v{VERSION} · {tr('离线可用')}")
        ver.setObjectName("brandSub")
        ver.setAlignment(Qt.AlignCenter)
        sv.addWidget(ver)

        root.addWidget(side)

        # -------- 内容区 --------
        self.stack = QStackedWidget()
        self.collect_panel = CollectPanel(self.store)
        self.gallery_panel = GalleryPanel(self.store)
        self.stack.addWidget(self.collect_panel)
        self.stack.addWidget(self.gallery_panel)
        self.collect_panel.recordsSaved.connect(self.gallery_panel.reload)
        self.collect_panel.recordsSaved.connect(self.refresh_groups)
        self.gallery_panel.groupChanged.connect(self.refresh_groups)
        root.addWidget(self.stack, 1)

        self.collect_btn.setChecked(True)
        self.stack.setCurrentIndex(0)
        self.refresh_groups()

    def _open_settings(self):
        from app.ui.settings_dialog import SettingsDialog
        SettingsDialog(self.store, self).exec()

    # ---------- 分组 ----------
    def refresh_groups(self):
        """重建左侧分组树（全部/未分组/各自定义组 + 计数）。"""
        counts = group_counts(self.store.records)
        self.group_tree.blockSignals(True)
        self.group_tree.clear()
        root = QTreeWidgetItem([tr("图片分组")])
        root.setFlags(Qt.ItemIsEnabled)
        self.group_tree.addTopLevelItem(root)
        items = {}

        all_item = QTreeWidgetItem([f"{tr('全部图片')}（{len(self.store.records)}）"])
        all_item.setData(0, Qt.UserRole, "全部")   # 固定 key，不随语言变化（筛选逻辑用）
        all_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        root.addChild(all_item)
        items["全部"] = all_item

        un_item = QTreeWidgetItem([f"{tr('未分组')}（{counts.get('', 0)}）"])
        un_item.setData(0, Qt.UserRole, "未分组")
        un_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        root.addChild(un_item)
        items["未分组"] = un_item

        for g in self.store.groups:
            gi = QTreeWidgetItem([f"{g}（{counts.get(g, 0)}）"])
            gi.setData(0, Qt.UserRole, g)
            gi.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            root.addChild(gi)
            items[g] = gi
        self._group_items = items
        root.setExpanded(self.collapse_btn.isChecked())
        self.group_tree.setCurrentItem(all_item)
        self.group_tree.blockSignals(False)

    def _toggle_groups(self, checked: bool):
        self.collapse_btn.setText("▼" if checked else "▶")
        top = self.group_tree.topLevelItem(0)
        if top:
            top.setExpanded(checked)

    def _group_clicked(self, item, col):
        g = item.data(0, Qt.UserRole)
        if not g:
            return
        self.gallery_panel.set_group(g)
        if self.stack.currentIndex() != 1:
            self.stack.setCurrentIndex(1)
            self.gallery_btn.setChecked(True)

    def _add_group_dialog(self):
        name, ok = QInputDialog.getText(self, tr("新建分组"), tr("分组名称："))
        if ok and name.strip():
            if not self.store.add_group(name.strip()):
                QMessageBox.information(self, tr(APP_NAME), tr("该分组已存在或名称为空"))
            self.refresh_groups()

    def _group_menu(self, pos):
        item = self.group_tree.itemAt(pos)
        if not item:
            return
        g = item.data(0, Qt.UserRole)
        if not g or g in ("全部", "未分组"):
            return
        menu = QMenu(self)
        menu.addAction(tr("重命名分组"), lambda: self._rename_group_dialog(g))
        menu.addAction(tr("删除分组"), lambda: self._delete_group_confirm(g))
        menu.exec(self.group_tree.viewport().mapToGlobal(pos))

    def _rename_group_dialog(self, old):
        name, ok = QInputDialog.getText(self, tr("重命名分组"), tr("新名称："), text=old)
        if ok and name.strip():
            if not self.store.rename_group(old, name.strip()):
                QMessageBox.information(self, tr(APP_NAME), tr("新名称已存在或无效"))
            self.refresh_groups()

    def _delete_group_confirm(self, g):
        ret = QMessageBox.question(self, tr(APP_NAME),
                                   tr_format("删除分组「{g}」？\n组内图片不会被删除，仅移回未分组。", g=g),
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret == QMessageBox.Yes:
            self.store.remove_group(g)
            self.refresh_groups()

    def _nav_btn(self, text, idx):
        b = QPushButton(text)
        b.setObjectName("navBtn")
        b.setCheckable(True)
        b.setCursor(Qt.PointingHandCursor)
        self.nav_group.addButton(b, idx)
        b.clicked.connect(lambda: self.stack.setCurrentIndex(idx))
        return b

    # ================= 全局粘贴 =================
    def _global_paste(self):
        w = QApplication.focusWidget()
        if isinstance(w, (QLineEdit, QPlainTextEdit, QTextEdit, QComboBox)):
            return  # 文本输入场景交给控件自身的粘贴
        self.collect_panel.add_from_clipboard()

    # ================= 图标 =================
    @staticmethod
    def _make_icon() -> QPixmap:
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        g = QLinearGradient(0, 0, 64, 64)
        g.setColorAt(0, QColor("#8b7bff"))
        g.setColorAt(0.5, QColor("#6d9bff"))
        g.setColorAt(1, QColor("#5ee0c8"))
        p.setBrush(QBrush(g))
        p.setPen(Qt.NoPen)
        p.drawRoundedRect(QRectF(2, 2, 60, 60), 15, 15)
        p.setPen(QColor("white"))
        f = QFont("Microsoft YaHei UI", 24, QFont.Bold)
        p.setFont(f)
        p.drawText(pm.rect(), Qt.AlignCenter, tr("绘"))
        p.end()
        return pm


def make_app_icon_file(path: str):
    """生成应用图标 .ico（含 32px PNG 的 ICO）。"""
    import os
    import tempfile
    from PySide6.QtGui import QImage
    icon = MainWindow._make_icon()
    img = icon.toImage().convertToFormat(QImage.Format_ARGB32)
    png_path = os.path.join(tempfile.gettempdir(), "app_icon_tmp.png")
    img.save(png_path, "PNG")
    try:
        with open(png_path, "rb") as f:
            data = f.read()
    finally:
        try:
            os.remove(png_path)
        except Exception:
            pass
    header = b"\x00\x00\x01\x00\x01\x00"
    entry = bytes([32, 32, 0, 0, 1, 0]) + (32).to_bytes(2, "little") + (len(data)).to_bytes(4, "little") + (22).to_bytes(4, "little")
    with open(path, "wb") as f:
        f.write(header + entry + data)
