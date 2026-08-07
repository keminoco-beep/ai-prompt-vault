from app.i18n import t as tr, rev, tr_format
"""浏览面板：平铺大图 / 详细信息列表两种显示模式，排序、筛选、悬浮详情、复制、分组。"""
from PySide6.QtCore import Qt, QEvent, QTimer, QPoint, QSize, Signal, QSortFilterProxyModel
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QCursor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QComboBox, QSlider, QPushButton, QListWidget,
                               QListWidgetItem, QTableWidget, QTableWidgetItem, QMenu,
                               QApplication, QStackedLayout, QSplitter, QMessageBox,
                               QToolTip, QHeaderView, QAbstractItemView)

from app.filters import filter_records, unique_loras, ratio_bucket, ratio_text, group_counts
from app.civitai import BASE_MODEL_GROUPS
from app.thumbs import load_pixmap, rounded_pixmap
from app.ui.hover_popup import HoverPopup, MAX_W as HOVER_MAX_W, MAX_H as HOVER_MAX_H
from app.ui.detail_dialog import DetailDialog, copy_text
from app.ui.detail_sidebar import DetailSidebar

SOURCES = ["全部来源", "来自Civitai", "本地导入"]
SORT_KEYS = [("time", tr("导入时间")), ("title", tr("标题")), ("base_model", tr("主模型大类")),
             ("models", tr("模型")), ("size", tr("尺寸"))]


def _no_image_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#1e1e2e"))
    p.setPen(QColor("#3a3a5c"))
    p.drawRoundedRect(3, 3, size - 6, size - 6, 14, 14)
    p.setPen(QColor("#8f8faa"))
    f = QFont()
    f.setPointSize(10)
    p.setFont(f)
    p.drawText(pm.rect().adjusted(10, 0, -10, 0), Qt.AlignCenter | Qt.TextWordWrap,
               "暂无图片\n（右键查看来源）")
    p.end()
    return pm


class GalleryPanel(QWidget):
    groupChanged = Signal()   # 记录加入/移除分组时发出，主窗口连接刷新侧栏计数

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._records = []
        self._by_uid = {}
        self._popup_index = -1
        self._pending_show = None
        self._current_group = "全部"   # 固定 key（"全部"/"未分组"/组名），不随语言翻译
        self._sort_key = "time"
        self._sort_desc = True
        self._view_mode = "grid"       # grid | table
        self._pm_cache = {}            # uid -> QPixmap（悬停/缩略图缓存，避免磁盘 IO 卡顿）
        self._build()
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(120)
        self._hover_timer.timeout.connect(self._show_pending_popup)
        self._popup = HoverPopup()
        self.reload()

    # ================= UI =================
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(10)

        head = QVBoxLayout()
        head.setSpacing(2)
        t = QLabel(tr("图库浏览"))
        t.setObjectName("pageTitle")
        head.addWidget(t)
        s = QLabel(tr("悬停看详情，右键复制提示词/加入分组，双击打开详情；可切换显示方式与排序"))
        s.setObjectName("pageSub")
        head.addWidget(s)
        root.addLayout(head)

        # 工具栏
        # 工具栏两行布局：第一行筛选，第二行排序/显示/复制/缩放
        bar = QHBoxLayout()
        bar.setSpacing(6)

        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("搜索标题 / 标签 / 提示词 / 模型名 / 主模型大类"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply)
        bar.addWidget(self.search, 1)

        bar.addWidget(self._tool_label(tr("主模型")))
        self.base_combo = QComboBox()
        self.base_combo.currentTextChanged.connect(self._apply)
        bar.addWidget(self.base_combo)

        bar.addWidget(self._tool_label(tr("比例")))
        self.ratio_combo = QComboBox()
        self.ratio_combo.addItems([tr("全部比例"), "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", tr("超宽"), tr("超高"), tr("其他")])
        self.ratio_combo.currentTextChanged.connect(self._apply)
        bar.addWidget(self.ratio_combo)

        bar.addWidget(self._tool_label("LoRA"))
        self.lora_combo = QComboBox()
        self.lora_combo.addItem(tr("全部"))
        self.lora_combo.currentTextChanged.connect(self._apply)
        bar.addWidget(self.lora_combo)

        bar.addWidget(self._tool_label(tr("来源")))
        self.source_combo = QComboBox()
        self.source_combo.addItems([tr(s) for s in SOURCES])
        self.source_combo.currentTextChanged.connect(self._apply)
        bar.addWidget(self.source_combo)
        root.addLayout(bar)

        bar2 = QHBoxLayout()
        bar2.setSpacing(6)

        bar2.addWidget(self._tool_label(tr("排序")))
        self.sort_combo = QComboBox()
        for _k, label in SORT_KEYS:
            self.sort_combo.addItem(tr(label))
        self.sort_combo.currentIndexChanged.connect(self._on_sort_combo)
        bar2.addWidget(self.sort_combo)
        self.sort_dir_btn = QPushButton("↓")
        self.sort_dir_btn.setObjectName("ghost")
        self.sort_dir_btn.setToolTip(tr("切换升序 / 降序"))
        self.sort_dir_btn.setCursor(Qt.PointingHandCursor)
        self.sort_dir_btn.clicked.connect(self._toggle_sort_dir)
        bar2.addWidget(self.sort_dir_btn)

        bar2.addSpacing(6)
        bar2.addWidget(self._tool_label(tr("显示")))
        self.view_grid_btn = QPushButton(tr("平铺"))
        self.view_grid_btn.setCheckable(True)
        self.view_grid_btn.setChecked(True)
        self.view_grid_btn.clicked.connect(lambda: self._set_view_mode("grid"))
        bar2.addWidget(self.view_grid_btn)
        self.view_table_btn = QPushButton(tr("列表"))
        self.view_table_btn.setCheckable(True)
        self.view_table_btn.clicked.connect(lambda: self._set_view_mode("table"))
        bar2.addWidget(self.view_table_btn)

        bar2.addSpacing(6)
        copy_btn = QPushButton(tr("复制提示词"))
        copy_btn.setObjectName("primary")
        copy_btn.setToolTip(tr("复制当前选中图片的全部提示词（含参数）"))
        copy_btn.clicked.connect(lambda: self._copy_current("all"))
        bar2.addWidget(copy_btn)
        copy_p_btn = QPushButton(tr("复制正向"))
        copy_p_btn.setObjectName("ghost")
        copy_p_btn.setToolTip(tr("复制正向提示词"))
        copy_p_btn.setCursor(Qt.PointingHandCursor)
        copy_p_btn.clicked.connect(lambda: self._copy_current("positive"))
        bar2.addWidget(copy_p_btn)
        copy_n_btn = QPushButton(tr("复制负向"))
        copy_n_btn.setObjectName("ghost")
        copy_n_btn.setToolTip(tr("复制负向提示词"))
        copy_n_btn.setCursor(Qt.PointingHandCursor)
        copy_n_btn.clicked.connect(lambda: self._copy_current("negative"))
        bar2.addWidget(copy_n_btn)

        bar2.addSpacing(6)
        self.dl_models_btn = QPushButton(tr("下载模型"))
        self.dl_models_btn.setObjectName("ghost")
        self.dl_models_btn.setToolTip(tr("下载当前图片使用的模型到 ComfyUI（需先在设置中选择 ComfyUI 文件夹）"))
        self.dl_models_btn.setCursor(Qt.PointingHandCursor)
        self.dl_models_btn.clicked.connect(self._download_current_models)
        bar2.addWidget(self.dl_models_btn)

        bar2.addSpacing(6)
        bar2.addWidget(self._tool_label(tr("大小")))
        self.zoom = QSlider(Qt.Horizontal)
        self.zoom.setRange(150, 420)
        self.zoom.setValue(220)
        self.zoom.setFixedWidth(110)
        self.zoom.valueChanged.connect(self._apply)
        bar2.addWidget(self.zoom)
        self.count_label = QLabel(tr("共 0 张"))
        self.count_label.setObjectName("countLabel")
        bar2.addWidget(self.count_label)
        bar2.addStretch(1)
        root.addLayout(bar2)

        # 内容区（平铺 / 列表 / 空状态）
        self.stack = QStackedLayout()
        # 平铺
        self.gallery = QListWidget()
        self.gallery.setObjectName("galleryList")
        self.gallery.setViewMode(QListWidget.IconMode)
        self.gallery.setResizeMode(QListWidget.Adjust)
        self.gallery.setMovement(QListWidget.Static)
        self.gallery.setUniformItemSizes(True)
        self.gallery.setSpacing(14)
        self.gallery.setWordWrap(True)
        self.gallery.setContextMenuPolicy(Qt.CustomContextMenu)
        self.gallery.customContextMenuRequested.connect(lambda pos: self._context_menu(pos, "grid"))
        self.gallery.itemDoubleClicked.connect(
            lambda li: self._open_detail(self._by_uid.get(li.data(Qt.UserRole)) if li else None))
        self.gallery.viewport().setMouseTracking(True)
        self.gallery.viewport().installEventFilter(self)
        self.stack.addWidget(self.gallery)

        # 详细列表
        self.detail = QTableWidget()
        self.detail.setObjectName("detailTable")
        self.detail.setColumnCount(7)
        self.detail.setHorizontalHeaderLabels(
            ["", tr("标题"), tr("主模型"), tr("模型清单"), tr("提示词"), tr("尺寸"), tr("导入时间")])
        self.detail.verticalHeader().setVisible(False)
        self.detail.setShowGrid(False)
        self.detail.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.detail.setSelectionMode(QAbstractItemView.SingleSelection)
        self.detail.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.detail.setRowHeight(0, 60)
        # 所有列允许用户拖动调节宽度（Interactive），并给出合理初始宽度
        self.detail.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        for c in range(1, 7):
            self.detail.horizontalHeader().setSectionResizeMode(c, QHeaderView.Interactive)
        self.detail.setColumnWidth(0, 68)
        self.detail.setColumnWidth(1, 140)   # 标题
        self.detail.setColumnWidth(2, 90)    # 主模型
        self.detail.setColumnWidth(3, 180)   # 模型清单
        self.detail.setColumnWidth(4, 160)   # 提示词
        self.detail.setColumnWidth(5, 90)    # 尺寸
        self.detail.setColumnWidth(6, 150)   # 导入时间
        self.detail.horizontalHeader().setStretchLastSection(False)
        # 不用 Qt 自带排序（避免与工具栏排序冲突），改为表头点击自定义排序
        self.detail.setSortingEnabled(False)
        self.detail.horizontalHeader().sectionClicked.connect(self._on_header_clicked)
        self.detail.setContextMenuPolicy(Qt.CustomContextMenu)
        self.detail.customContextMenuRequested.connect(lambda pos: self._context_menu(pos, "table"))
        self.detail.cellDoubleClicked.connect(self._table_double_click)
        self.detail.viewport().setMouseTracking(True)
        self.detail.viewport().installEventFilter(self)
        self.stack.addWidget(self.detail)

        self.empty_widget = QWidget()
        ev = QVBoxLayout(self.empty_widget)
        ev.addStretch(1)
        self.empty_label = QLabel("")
        self.empty_label.setObjectName("emptyHint")
        self.empty_label.setAlignment(Qt.AlignCenter)
        ev.addWidget(self.empty_label)
        ev.addStretch(1)
        self.stack.addWidget(self.empty_widget)
        self.stack.setCurrentIndex(0)

        # 右侧详情面板（选中图片时显示完整详情）
        self.sidebar = DetailSidebar(self.store, self)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(6)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self._wrap_stack())
        self.splitter.addWidget(self.sidebar)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([820, 360])
        root.addWidget(self.splitter, 1)

        # 选中变化同步到右侧详情
        self.gallery.currentItemChanged.connect(
            lambda cur, prev: self._on_selection_changed(
                self._by_uid.get(cur.data(Qt.UserRole)) if cur else None))
        self.detail.itemSelectionChanged.connect(self._on_table_selection)

    @staticmethod
    def _tool_label(text):
        lb = QLabel(text)
        lb.setObjectName("fieldLabel")
        return lb

    # ================= 显示模式 / 排序 =================
    def _set_view_mode(self, mode: str):
        self._view_mode = mode
        self.view_grid_btn.setChecked(mode == "grid")
        self.view_table_btn.setChecked(mode == "table")
        self._apply()

    def _on_sort_combo(self, idx):
        if 0 <= idx < len(SORT_KEYS):
            self._sort_key = SORT_KEYS[idx][0]
            self._apply()

    # 列表模式表头点击 → 同步工具栏排序（与平铺模式一致）
    _HEADER_SORT = {1: "title", 2: "base_model", 3: "models", 5: "size", 6: "time"}

    def _on_header_clicked(self, col):
        key = self._HEADER_SORT.get(col)
        if not key:
            return
        if self._sort_key == key:
            self._toggle_sort_dir()
        else:
            self._sort_key = key
            self._sort_desc = True
            self.sort_dir_btn.setText("↓")
            keys = [k for k, _ in SORT_KEYS]
            idx = keys.index(key) if key in keys else 0
            self.sort_combo.blockSignals(True)
            self.sort_combo.setCurrentIndex(idx)
            self.sort_combo.blockSignals(False)
            self._apply()

    def _toggle_sort_dir(self):
        self._sort_desc = not self._sort_desc
        self.sort_dir_btn.setText("↓" if self._sort_desc else "↑")
        self._apply()

    def set_group(self, group: str):
        self._current_group = group
        self._apply()

    def _sorted(self, records: list) -> list:
        def keyof(r):
            k = self._sort_key
            if k == "time":
                return r.get("created_at") or ""
            if k == "title":
                return (r.get("title") or "").lower()
            if k == "base_model":
                return (r.get("base_model") or "其他")
            if k == "models":
                ms = r.get("models") or []
                return (ms[0].get("name") or "") if ms else (r.get("model_name") or "")
            if k == "size":
                return int(r.get("width") or 0) * int(r.get("height") or 0)
            return ""
        try:
            return sorted(records, key=keyof, reverse=self._sort_desc)
        except Exception:
            return records

    # ================= 数据 =================
    def reload(self):
        self._records = list(self.store.records)
        self._pm_cache.clear()
        types_present = {(r.get("base_model") or "其他") for r in self._records}
        cur_base = self.base_combo.currentText()
        self.base_combo.blockSignals(True)
        self.base_combo.clear()
        self.base_combo.addItem(tr("全部"))
        for g in BASE_MODEL_GROUPS:
            if g != "其他" and g in types_present:
                self.base_combo.addItem(g)
        if "其他" in types_present:
            self.base_combo.addItem(tr("其他"))
        if cur_base in [self.base_combo.itemText(i) for i in range(self.base_combo.count())]:
            self.base_combo.setCurrentText(cur_base)
        self.base_combo.blockSignals(False)

        cur_lora = self.lora_combo.currentText()
        loras = unique_loras(self._records)
        self.lora_combo.blockSignals(True)
        self.lora_combo.clear()
        self.lora_combo.addItem(tr("全部"))
        for lo in loras:
            self.lora_combo.addItem(lo)
        if cur_lora in loras:
            self.lora_combo.setCurrentText(cur_lora)
        self.lora_combo.blockSignals(False)
        self._apply()

    def _filtered(self) -> list:
        # 下拉显示的是当前语言，反查回中文 key 再筛选
        return filter_records(
            self._records,
            base_model=rev(self.base_combo.currentText()),
            ratio=rev(self.ratio_combo.currentText()),
            lora=rev(self.lora_combo.currentText()),
            source=rev(self.source_combo.currentText()),
            search=self.search.text(),
            group=self._current_group,
        )

    def _apply(self):
        self._hide_popup()
        records = self._sorted(self._filtered())
        size = self.zoom.value()
        n = len(records)
        self.count_label.setText(tr_format("共 {n} 张", n=n))
        if n == 0:
            self.gallery.clear()
            self.detail.clearContents()
            self.detail.setRowCount(0)
            self.stack.setCurrentIndex(2)
            self.empty_label.setText(
                "没有符合条件的图片\n" +
                (tr("去「收藏作品」板块添加例图吧") if not self._records else tr("试试调整筛选/分组条件")))
            return
        if self._view_mode == "table":
            self.stack.setCurrentIndex(1)
            self._fill_table(records)
        else:
            self.stack.setCurrentIndex(0)
            self._fill_grid(records, size)

    def _fill_grid(self, records: list, size: int):
        self.gallery.clear()
        self._by_uid = {}
        grid = size + 26
        self.gallery.setIconSize(QSize(size - 6, size - 6))
        self.gallery.setGridSize(QSize(grid, grid + 22))
        for r in records:
            uid = r["id"]
            self._by_uid[uid] = r
            li = QListWidgetItem()
            li.setData(Qt.UserRole, uid)
            li.setText(r.get("title") or "")
            li.setTextAlignment(Qt.AlignHCenter)
            li.setIcon(self._tile_pixmap(r, size - 6))
            self.gallery.addItem(li)

    def _fill_table(self, records: list):
        self._by_uid = {}
        self.detail.setSortingEnabled(False)
        self.detail.setRowCount(len(records))
        for row, r in enumerate(records):
            uid = r["id"]
            self._by_uid[uid] = r
            # 缩略图列：仅显示缩略图，不携带任何文本（setData 会覆盖显示文本）
            thumb = QTableWidgetItem()
            thumb.setData(Qt.UserRole, uid)
            pm = self._tile_pixmap(r, 52)
            thumb.setIcon(pm)
            thumb.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            self.detail.setItem(row, 0, thumb)
            # 标题
            ti = QTableWidgetItem(r.get("title") or "")
            ti.setData(Qt.UserRole, uid)
            self.detail.setItem(row, 1, ti)
            # 主模型大类
            bi = QTableWidgetItem(tr(r.get("base_model") or "其他"))
            bi.setData(Qt.UserRole, uid)
            self.detail.setItem(row, 2, bi)
            # 模型清单
            ms = r.get("models") or []
            if not ms and r.get("model_name"):
                ms = [{"name": r["model_name"], "type": tr(r.get("model_type") or "大模型")}]
            mi = QTableWidgetItem(self._models_brief(ms, r.get("loras") or []))
            mi.setData(Qt.UserRole, uid)
            self.detail.setItem(row, 3, mi)
            # 提示词（短截断，避免占用过多横向空间；详情面板右侧有完整版）
            pos = (r.get("positive") or "").strip()
            pt = pos[:50] + ("…" if len(pos) > 50 else "") if pos else tr("（无）")
            pi = QTableWidgetItem(pt)
            pi.setData(Qt.UserRole, uid)
            self.detail.setItem(row, 4, pi)
            # 尺寸（文本保持 "WxH" 格式）
            w, h = r.get("width") or 0, r.get("height") or 0
            si = QTableWidgetItem(f"{w}×{h}" if w else tr("未知"))
            si.setData(Qt.UserRole, uid)
            self.detail.setItem(row, 5, si)
            # 导入时间
            ci = QTableWidgetItem(r.get("created_at") or "")
            ci.setData(Qt.UserRole, uid)
            self.detail.setItem(row, 6, ci)

    @staticmethod
    def _models_brief(models: list, loras: list) -> str:
        parts = []
        main = next((m for m in models if m.get("type") == "大模型"), None)
        if main:
            parts.append(main.get("name") or "")
        lora_names = [m.get("name") for m in models if m.get("type") == "LoRA" and m.get("name")]
        for lo in loras:
            if lo not in lora_names:
                lora_names.append(lo)
        for lo in lora_names[:2]:
            parts.append(f"LoRA:{lo}")
        if len(lora_names) > 2:
            parts.append(f"+{len(lora_names)-2} LoRA")
        others = [m.get("name") for m in models
                  if m.get("type") not in ("大模型", "LoRA") and m.get("name")]
        if others:
            parts.append("、".join(others[:2]))
        return " · ".join(parts) if parts else "—"

    def _tile_pixmap(self, r: dict, size: int) -> QPixmap:
        """缩略图/平铺图（带缓存，避免反复磁盘 IO 与解码造成的卡顿）。"""
        uid = r.get("id")
        key = f"{uid}@{size}"
        if key in self._pm_cache:
            return self._pm_cache[key]
        if r.get("thumb_file"):
            path = str(self.store.thumbs_dir / r["thumb_file"])
            pm = rounded_pixmap(path, size)
        elif r.get("image_file"):
            path = str(self.store.images_dir / r["image_file"])
            pm = rounded_pixmap(path, size)
        else:
            pm = _no_image_pixmap(size)
        if len(self._pm_cache) > 500:   # 防止无限增长
            self._pm_cache.clear()
        self._pm_cache[key] = pm
        return pm

    def _hover_pixmap(self, r: dict) -> QPixmap:
        """悬停预览图：一次缩放到位并缓存，避免每次 hover 的磁盘 IO + 缩放开销。"""
        uid = r.get("id")
        key = f"hover:{uid}"
        if key in self._pm_cache and not self._pm_cache[key].isNull():
            return self._pm_cache[key]
        pm = None
        if r.get("thumb_file"):
            pm = load_pixmap(str(self.store.thumbs_dir / r["thumb_file"]), 480)
        if (pm is None or pm.isNull()) and r.get("image_file"):
            pm = load_pixmap(str(self.store.images_dir / r["image_file"]), 480)
        if pm is None or pm.isNull():
            pm = _no_image_pixmap(120)
        # 预缩放为悬浮窗所需尺寸（380 内等比），show_image 直接 setPixmap 零开销
        scaled = pm.scaled(HOVER_MAX_W, HOVER_MAX_H, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        if len(self._pm_cache) > 500:
            self._pm_cache.clear()
        self._pm_cache[key] = scaled
        return scaled

    def _wrap_stack(self) -> QWidget:
        """把 stack 装入 QWidget 以便放进 QSplitter。"""
        w = QWidget()
        lay = QStackedLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        # 将 self.stack 的 3 个页迁移过来（避免双倍布局）
        for i in range(self.stack.count()):
            lay.addWidget(self.stack.widget(i))
        self.stack = lay
        return w

    def _on_table_selection(self):
        rec = None
        for item in self.detail.selectedItems():
            uid = item.data(Qt.UserRole)
            rec = self._by_uid.get(uid)
            if rec:
                break
        self._on_selection_changed(rec)

    def _on_selection_changed(self, rec):
        self.sidebar.set_record(rec)

    def _table_double_click(self, row, col):
        item = self.detail.item(row, 0)
        if item:
            rec = self._by_uid.get(item.data(Qt.UserRole))
            if rec:
                self._open_detail(rec)

    # ================= 悬浮详情 =================
    def eventFilter(self, obj, event):
        # _build 期间 detail 可能尚未创建，需防御
        detail = getattr(self, "detail", None)
        gview = self.gallery.viewport() if hasattr(self, "gallery") else None
        if obj is not gview and (detail is None or obj is not detail.viewport()):
            return super().eventFilter(obj, event)
        et = event.type()
        if et == QEvent.MouseMove:
            if self._view_mode == "grid":
                idx = self.gallery.indexAt(event.position().toPoint())
                row = idx.row()
            else:
                # viewport 坐标直接用于 rowAt（视口顶部即第一行，不要与表头高度比较）
                row = self.detail.rowAt(event.position().toPoint().y())
            gpos = event.globalPosition().toPoint()
            if self._popup.isVisible() and row == self._popup_index:
                self._reposition_popup(gpos)
            else:
                self._pending_show = (row, gpos)
                self._hover_timer.start()
        elif et in (QEvent.Leave, QEvent.MouseButtonPress, QEvent.Wheel, QEvent.MouseButtonDblClick):
            self._hide_popup()
        return super().eventFilter(obj, event)

    def _show_pending_popup(self):
        if self._pending_show is None:
            return
        row, gpos = self._pending_show
        self._pending_show = None
        if row < 0:
            return
        rec = None
        if self._view_mode == "grid":
            li = self.gallery.item(row)
            rec = self._by_uid.get(li.data(Qt.UserRole)) if li else None
        else:
            item = self.detail.item(row, 0)
            rec = self._by_uid.get(item.data(Qt.UserRole)) if item else None
        if not rec:
            return
        self._popup_index = row
        screen = self.gallery.screen() or self.gallery.window().screen()
        rect = screen.availableGeometry() if screen else self.gallery.rect()
        # 纯图片预览：直接用缓存的 pixmap，避免磁盘 IO
        self._popup.show_image(self._hover_pixmap(rec), gpos, rect)

    def _reposition_popup(self, gpos):
        rect = self.gallery.screen().availableGeometry()
        self._popup.reposition(gpos, rect)

    def _hide_popup(self):
        self._hover_timer.stop()
        self._pending_show = None
        self._popup_index = -1
        self._popup.hide()

    # ================= 右键菜单 =================
    def _record_at(self, pos: QPoint, mode: str) -> dict:
        if mode == "grid":
            li = self.gallery.itemAt(pos)
            return self._by_uid.get(li.data(Qt.UserRole)) if li else None
        item = self.detail.itemAt(pos.x(), pos.y())
        if item is None:
            return None
        item = self.detail.item(item.row(), 0) or item
        return self._by_uid.get(item.data(Qt.UserRole))

    def _context_menu(self, pos: QPoint, mode: str):
        rec = self._record_at(pos, mode)
        if not rec:
            return
        menu = QMenu(self)
        menu.addAction(tr("复制正向提示词"), lambda: self._copy(rec, "positive"))
        menu.addAction(tr("复制负向提示词"), lambda: self._copy(rec, "negative"))
        menu.addAction(tr("复制全部提示词"), lambda: self._copy(rec, "all"))
        menu.addSeparator()
        menu.addAction(tr("查看详情 / 编辑"), lambda: self._open_detail(rec))
        # 分组子菜单
        gmenu = menu.addMenu(tr("加入分组 ▸"))
        gmenu.addAction(tr("未分组"), lambda: self._set_group_of(rec, ""))
        for g in self.store.groups:
            gmenu.addAction(g, lambda gg=g: self._set_group_of(rec, gg))
        menu.addAction(tr("从当前分组移除"), lambda: self._set_group_of(rec, ""))
        # 下载模型子菜单
        dmenu = menu.addMenu(tr("下载模型 ▸"))
        dl_ms = [m for m in (rec.get("models") or []) if (m.get("url") or "").strip()]
        if dl_ms:
            for m in dl_ms:
                lbl = f"{tr(m.get('type') or '其他')}: {m.get('name') or ''}"
                dmenu.addAction(lbl, lambda mm=m: self._download_models_for(rec, [mm]))
        else:
            dmenu.addAction(tr("该图片没有可下载的模型"), lambda: None)
            dmenu.setEnabled(False)
        # 主模型链接
        main_url = ""
        for m in (rec.get("models") or []):
            if m.get("type") == "大模型" and m.get("url"):
                main_url = m["url"]
                break
        if not main_url:
            main_url = rec.get("source_url") or ""
        if main_url and "civitai" in main_url:
            menu.addAction(tr("打开主模型页面"), lambda: self._open_url(main_url))
        if rec.get("image_file"):
            menu.addAction(tr("打开图片所在文件夹"), lambda: self._reveal(rec))
        if rec.get("source_url"):
            menu.addAction(tr("在浏览器打开来源链接"), lambda: self._open_source(rec))
        menu.addSeparator()
        menu.addAction(tr("删除记录"), lambda: self._delete(rec))
        menu.exec(self.gallery.viewport().mapToGlobal(pos))

    def _set_group_of(self, rec, group: str):
        self.store.set_record_group(rec["id"], group)
        self.groupChanged.emit()
        self.reload()

    # ---------- 模型下载（ComfyUI） ----------
    def _download_current_models(self):
        """工具栏按钮：下载当前选中图片的全部模型。"""
        rec = self._current_record()
        if not rec:
            QToolTip.showText(QCursor.pos(), tr("请先选中一张图片"))
            return
        ms = [m for m in (rec.get("models") or []) if (m.get("url") or "").strip()]
        if not ms:
            QMessageBox.information(self, tr("AI-Prompt-Vault"),
                                    tr("该图片没有可下载的模型（无链接）。"))
            return
        self._download_models_for(rec, ms)

    def _download_models_for(self, rec, models: list):
        """下载指定模型列表到 ComfyUI（由 DownloadManager 调度，独立列表页查看进度）。"""
        from PySide6.QtGui import QCursor
        from app.ui.download_manager import DownloadManager
        win = self.window()
        mgr: DownloadManager = getattr(win, "download_manager", None)
        if mgr is None:
            return
        for m in models:
            mgr.start(m, parent_widget=self, src_pos=QCursor.pos())

    def _current_record(self):
        if self._view_mode == "table":
            row = self.detail.currentRow()
            if row >= 0:
                item = self.detail.item(row, 0)
                return self._by_uid.get(item.data(Qt.UserRole)) if item else None
        li = self.gallery.currentItem()
        return self._by_uid.get(li.data(Qt.UserRole)) if li else None


    def _copy(self, rec, which):
        pos = rec.get("positive") or ""
        neg = rec.get("negative") or ""
        if which == "positive":
            ok = copy_text(pos)
        elif which == "negative":
            ok = copy_text(neg)
        else:
            parts = [pos]
            if neg:
                parts.append(f"Negative prompt: {neg}")
            ms = rec.get("models") or []
            mains = [m for m in ms if m.get("type") == "大模型"]
            meta = []
            if rec.get("steps"):
                meta.append(f"Steps: {rec['steps']}")
            if rec.get("sampler"):
                meta.append(f"Sampler: {rec['sampler']}")
            if rec.get("cfg"):
                meta.append(f"CFG scale: {rec['cfg']}")
            if rec.get("seed"):
                meta.append(f"Seed: {rec['seed']}")
            if mains:
                meta.append(f"Model: {mains[0]['name']}")
            elif rec.get("model_name"):
                meta.append(f"Model: {rec['model_name']}")
            if rec.get("base_model") and rec.get("base_model") != tr("其他"):
                meta.append(f"Base model: {rec.get('base_model_raw') or rec['base_model']}")
            if meta:
                parts.append(" ".join(meta))
            ok = copy_text("\n".join(parts).strip())
        QToolTip.showText(QCursor.pos(), tr("已复制到剪贴板 ✓") if ok else tr("没有内容可复制"))

    def _copy_current(self, which):
        rec = None
        if self._view_mode == "table":
            row = self.detail.currentRow()
            if row >= 0:
                item = self.detail.item(row, 0)
                rec = self._by_uid.get(item.data(Qt.UserRole)) if item else None
        else:
            li = self.gallery.currentItem()
            rec = self._by_uid.get(li.data(Qt.UserRole)) if li else None
        if rec:
            self._copy(rec, which)
        else:
            QToolTip.showText(QCursor.pos(), tr("请先选中一张图片"))

    def _open_detail(self, rec):
        img_path = ""
        if rec.get("image_file"):
            img_path = str(self.store.images_dir / rec["image_file"])
        dlg = DetailDialog(rec, img_path, self)
        if dlg.exec():
            if dlg.record.get("_deleted"):
                self.store.remove(rec["id"])
                self.reload()
            else:
                self.store.update(rec["id"], dlg.record)
                self.reload()

    def _reveal(self, rec):
        if rec.get("image_file"):
            self.store.reveal_in_explorer(str(self.store.images_dir / rec["image_file"]))

    def _open_url(self, url):
        from PySide6.QtGui import QDesktopServices
        from PySide6.QtCore import QUrl
        if url:
            QDesktopServices.openUrl(QUrl(url))

    def _open_source(self, rec):
        self._open_url(rec.get("source_url") or "")

    def _delete(self, rec):
        ret = QMessageBox.question(
            self, tr("AI-Prompt-Vault"),
            tr_format("确定删除「{title}」吗？\n图片将移入资料库回收站。",
                      title=rec.get("title") or rec["id"]),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret == QMessageBox.Yes:
            self.store.remove(rec["id"])
            self.reload()
