from app.i18n import t as tr, rev, tr_format
"""浏览面板：平铺大图 / 详细信息列表两种显示模式，排序、筛选、悬浮详情、复制、分组。"""
from pathlib import Path
from PySide6.QtCore import Qt, QEvent, QTimer, QPoint, QSize, Signal, QSortFilterProxyModel
from PySide6.QtGui import QPixmap, QPainter, QColor, QFont, QCursor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QComboBox, QSlider, QPushButton, QListWidget,
                               QListWidgetItem, QTableWidget, QTableWidgetItem, QMenu,
                               QApplication, QStackedLayout, QSplitter, QMessageBox,
                               QToolTip, QHeaderView, QAbstractItemView)

from app.filters import filter_records, unique_loras, unique_tags, ratio_bucket, ratio_text, group_counts
from app.civitai import BASE_MODEL_GROUPS
from app.thumbs import load_pixmap, rounded_pixmap
from app.ui.hover_popup import HoverPopup, MAX_W as HOVER_MAX_W, MAX_H as HOVER_MAX_H
from app.ui.detail_dialog import DetailDialog, copy_text
from app.ui.detail_sidebar import DetailSidebar

SOURCES = ["全部来源", "来自Civitai", "本地导入"]
# (显示标签, 存储值)：media_type 筛选用英文存储 key
MEDIA_CHOICES = [("全部媒体", "全部媒体"), ("图片", "image"), ("视频", "video")]
SORT_KEYS = [("time", tr("导入时间")), ("title", tr("标题")), ("base_model", tr("主模型大类")),
             ("models", tr("模型")), ("size", tr("尺寸"))]


_NO_IMG_CACHE = {}   # size -> QPixmap（复用，避免 frozen 环境反复创建 QPixmap/QPainter 卡顿）

# v3.5 分片渲染：大数据量平铺时每批渲染的 item 数与批次间隔（ms）。
# 根因：真实窗口下 _fill_grid 同步循环为每个 item setIcon（250+ tile 的磁盘 IO +
# GDI 绘制 → 几十秒卡死）；分批 QTimer 让事件循环在批次间处理绘制/输入，窗口保持可用。
GRID_CHUNK = 40       # 每批渲染的平铺 item 数
GRID_CHUNK_MS = 16    # 批次间隔（ms）


def _no_image_pixmap(size: int) -> QPixmap:
    cached = _NO_IMG_CACHE.get(size)
    if cached is not None and not cached.isNull():
        return cached
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
               tr("暂无图片\n（右键查看来源）"))
    p.end()
    if len(_NO_IMG_CACHE) > 8:
        _NO_IMG_CACHE.clear()
    _NO_IMG_CACHE[size] = pm
    return pm


class GalleryPanel(QWidget):
    groupChanged = Signal()   # 记录加入/移除分组时发出，主窗口连接刷新侧栏计数
    refreshRequested = Signal()   # v3.5：点击「刷新」→ MainWindow 启动后台输出扫描

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
        self._scanning = False         # v3.4：后台扫描输出文件夹中（空态提示用）
        # v3.5：平铺分片渲染（大数据量分批 QTimer，批次间事件循环处理绘制/输入）
        self._chunk_timer = QTimer(self)
        self._chunk_timer.setInterval(GRID_CHUNK_MS)
        self._chunk_timer.timeout.connect(self._render_grid_chunk)
        self._chunk_records = None     # 分片渲染中的 records（None = 未在分片）
        self._chunk_size = 0
        self._chunk_pos = 0
        self._build()
        self._hover_timer = QTimer(self)
        self._hover_timer.setSingleShot(True)
        self._hover_timer.setInterval(120)
        self._hover_timer.timeout.connect(self._show_pending_popup)
        self._popup = HoverPopup()
        self.reload()

    def set_scanning(self, scanning: bool):
        """v3.4：标记后台输出文件夹扫描中（空态显示「正在后台扫描…」提示）。

        由 main_window 在 _start_output_scan / _on_output_scanned 中调用。
        仅影响空态文案，不影响数据。
        """
        self._scanning = bool(scanning)

    # ================= v3.5：手动刷新 =================
    def _on_refresh_clicked(self):
        """「刷新」按钮：请求后台重新扫描输出文件夹（增量扫描 + 写缓存）。

        明确不做实时监听（QFileSystemWatcher 等）——手动刷新即可，避免性能开销。
        - 有 MainWindow：发 refreshRequested 信号 → MainWindow._start_output_scan
          （后台线程扫描，done 后 _on_output_scanned 无条件 reload），并给状态反馈
        - 独立使用（无 MainWindow，如测试/单面板）：直接重读磁盘缓存兜底
        """
        win = self.window()
        has_scan = (win is not None and hasattr(win, "_start_output_scan")
                    and callable(getattr(win, "_start_output_scan", None)))
        self.refreshRequested.emit()
        if not has_scan:
            self.reload()
        else:
            # 状态反馈：扫描中标记由 _start_output_scan 设置（空态显示扫描文案）；
            # 这里再给一个即时 tooltip，图库非空时也能看到反馈
            try:
                QToolTip.showText(QCursor.pos(), tr("正在后台扫描输出文件夹…"))
            except Exception:
                pass

    # ================= 文件缺失标记（幽灵记录提示） =================
    def _missing_files(self, rec: dict) -> list:
        """真实记录的文件缺失检查：image_file/thumb_file/video_file 声明了但文件不存在。

        - 虚拟记录（is_virtual）不检查：文件在 ComfyUI 输出目录，不属于资料库
        - 仅提示不自动删记录：用户可能外部移动文件但想保留记录
        """
        if not rec or rec.get("is_virtual"):
            return []
        miss = []
        if rec.get("image_file") and not (self.store.images_dir / rec["image_file"]).exists():
            miss.append("image_file")
        if rec.get("thumb_file") and not (self.store.thumbs_dir / rec["thumb_file"]).exists():
            miss.append("thumb_file")
        if rec.get("video_file") and not (self.store.videos_dir / rec["video_file"]).exists():
            miss.append("video_file")
        return miss

    def _missing_marker(self, rec: dict) -> str:
        """标题旁的文件缺失标记（如 "  ⚠ 文件缺失"）；文件齐全返回空串。"""
        if self._missing_files(rec):
            return "  ⚠ " + tr("文件缺失")
        return ""

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

        bar.addWidget(self._tool_label(tr("媒体")))
        self.media_combo = QComboBox()
        for label, key in MEDIA_CHOICES:
            self.media_combo.addItem(tr(label), key)
        self.media_combo.currentTextChanged.connect(self._apply)
        bar.addWidget(self.media_combo)

        bar.addWidget(self._tool_label(tr("标签")))
        self.tag_combo = QComboBox()
        self.tag_combo.addItem(tr("全部标签"))
        self.tag_combo.currentTextChanged.connect(self._apply)
        bar.addWidget(self.tag_combo)
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

        dupe_btn = QPushButton(tr("查重"))
        dupe_btn.setObjectName("ghost")
        dupe_btn.setToolTip(tr("检测库中的重复图片（感知哈希）"))
        dupe_btn.setCursor(Qt.PointingHandCursor)
        dupe_btn.clicked.connect(self._find_duplicates)
        bar2.addWidget(dupe_btn)

        # v3.5：手动刷新（不实时监听 QFileSystemWatcher——太耗性能）。
        # 点击 → refreshRequested → MainWindow._start_output_scan（后台线程增量扫描
        # 输出目录 + 写缓存，done 后无条件 reload），新图片立即可见。
        refresh_btn = QPushButton(tr("刷新"))
        refresh_btn.setObjectName("ghost")
        refresh_btn.setToolTip(tr("重新扫描输出文件夹，立即显示新增图片（手动刷新）"))
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self._on_refresh_clicked)
        bar2.addWidget(refresh_btn)

        a1111_btn = QPushButton(tr("从 A1111 导入"))
        a1111_btn.setObjectName("ghost")
        a1111_btn.setToolTip(tr("把 A1111 outputs 目录的生成图（含提示词参数）一键导入收藏"))
        a1111_btn.setCursor(Qt.PointingHandCursor)
        a1111_btn.clicked.connect(self._import_from_a1111)
        bar2.addWidget(a1111_btn)

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
        # v3.0：支持多选（Ctrl/Shift），右键批量操作
        self.gallery.setSelectionMode(QListWidget.ExtendedSelection)
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
        # v3.1+：合并 ComfyUI 输出文件夹虚拟记录（「我的作品」分组，不复制文件）
        # 启动时只读磁盘缓存（秒级，不枚举目录，校验目录集合匹配）；
        # 后台线程增量扫描后由 main_window 刷新
        try:
            from app.comfy_output import load_cached_records, configured_output_dirs
            vout = load_cached_records(
                str(self.store.root / "comfy_output_cache.json"),
                configured_output_dirs(self.store))
            self._records.extend(vout)
        except Exception:
            pass
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

        # v3.0：标签筛选下拉（从全部记录收集）
        cur_tag = self.tag_combo.currentText()
        tags = unique_tags(self._records)
        self.tag_combo.blockSignals(True)
        self.tag_combo.clear()
        self.tag_combo.addItem(tr("全部标签"))
        for t in tags:
            self.tag_combo.addItem(t)
        if cur_tag in [self.tag_combo.itemText(i) for i in range(self.tag_combo.count())]:
            self.tag_combo.setCurrentText(cur_tag)
        self.tag_combo.blockSignals(False)
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
            media_type=self.media_combo.currentData(),
            tag=self.tag_combo.currentText() if self.tag_combo.currentText() != tr("全部标签") else "全部",
        )

    def _apply(self):
        self._hide_popup()
        # v3.5：每次 _apply 先停旧分片渲染（防堆积/交错）——筛选/排序/刷新/切页
        # 触发的新渲染必须取消进行中的分片，避免旧定时器继续往新列表里加 item
        self._cancel_chunk_render()
        records = self._sorted(self._filtered())
        # 虚拟记录上限：Windows GDI 对象限制，一次渲染过多 QPixmap 会卡死/崩溃
        VIRT_CAP = 250
        virt = [r for r in records if r.get("is_virtual")]
        real = [r for r in records if not r.get("is_virtual")]
        capped = len(virt) > VIRT_CAP
        if capped:
            virt = virt[:VIRT_CAP]
        records = real + virt
        size = self.zoom.value()
        n = len(records)
        if capped:
            self.count_label.setText(
                tr_format("共 {n} 张（虚拟作品仅显示前 {cap} 张）", n=n, cap=VIRT_CAP))
        else:
            self.count_label.setText(tr_format("共 {n} 张", n=n))
        if n == 0:
            self.gallery.clear()
            self.detail.clearContents()
            self.detail.setRowCount(0)
            self.stack.setCurrentIndex(2)
            if self._scanning:
                self.empty_label.setText(tr("正在后台扫描输出文件夹…"))
            else:
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
        """平铺渲染。v3.5：大数据量改为分片渲染，窗口保持可交互。

        旧实现：同步 for 循环为每个 item setIcon（真实窗口 250+ tile 的磁盘 IO +
        GDI 绘制 → 几十秒卡死；offscreen 不绘制所以测不出）。新实现：
        - 小数据集（<= GRID_CHUNK）：单批同步渲染（瞬间完成，零延迟）
        - 大数据集：先清空 + 预填 _by_uid + 设尺寸，再启动分片定时器逐批添加
          （每批 GRID_CHUNK 个，间隔 GRID_CHUNK_MS，批次间事件循环可滚动/点击）
        """
        self._cancel_chunk_render()
        self.gallery.clear()
        self._by_uid = {}
        for r in records:
            self._by_uid[r["id"]] = r
        grid = size + 26
        self.gallery.setIconSize(QSize(size - 6, size - 6))
        self.gallery.setGridSize(QSize(grid, grid + 22))
        if len(records) <= GRID_CHUNK:
            # 小数据集：同步单批渲染（保持既有行为/测试确定性）
            self._render_grid_batch(records, size, 0, len(records))
            return
        self._chunk_records = records
        self._chunk_size = size
        self._chunk_pos = 0
        self._chunk_timer.start(GRID_CHUNK_MS)

    def _render_grid_batch(self, records: list, size: int, start: int, end: int):
        """渲染 records[start:end] 的一批平铺 item（setIcon + setText + addItem）。

        _by_uid 已在 _fill_grid 预填全部记录，本方法只创建列表项；
        悬停/右键查询不依赖 item 是否已创建。
        """
        for r in records[start:end]:
            uid = r["id"]
            li = QListWidgetItem()
            li.setData(Qt.UserRole, uid)
            is_video = (r.get("media_type") == "video")
            title = r.get("title") or ""
            li.setText(("▶ " if is_video else "") + title + self._missing_marker(r))
            li.setTextAlignment(Qt.AlignHCenter)
            li.setIcon(self._tile_pixmap(r, size - 6))
            if is_video:
                li.setToolTip(tr_format("视频：{t}", t=title or tr("视频")))
            self.gallery.addItem(li)

    def _render_grid_chunk(self):
        """分片定时器回调：渲染下一批；全部完成后停定时器、恢复状态。"""
        records = self._chunk_records
        if not records:
            self._chunk_timer.stop()
            return
        size = self._chunk_size
        end = min(self._chunk_pos + GRID_CHUNK, len(records))
        self._render_grid_batch(records, size, self._chunk_pos, end)
        self._chunk_pos = end
        if self._chunk_pos >= len(records):
            self._chunk_timer.stop()
            self._chunk_records = None
            self._chunk_size = 0
            self._chunk_pos = 0

    def _cancel_chunk_render(self):
        """停止进行中的分片渲染并清空状态（_apply 开头调用，防堆积/交错）。"""
        try:
            self._chunk_timer.stop()
        except RuntimeError:
            pass
        self._chunk_records = None
        self._chunk_size = 0
        self._chunk_pos = 0

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
            is_video = (r.get("media_type") == "video")
            ti = QTableWidgetItem(("▶ " if is_video else "") + (r.get("title") or "") + self._missing_marker(r))
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
            pm = rounded_pixmap(path, size) if Path(path).exists() else _no_image_pixmap(size)
        elif r.get("image_file"):
            path = str(self.store.images_dir / r["image_file"])
            pm = rounded_pixmap(path, size) if Path(path).exists() else _no_image_pixmap(size)
        elif r.get("is_virtual") and r.get("virtual_path"):
            # 虚拟记录：用缩略图缓存（后台线程生成）；无缓存时显示占位图，避免读原图卡顿
            try:
                from app.comfy_output import thumb_path_for_rec
                tp = thumb_path_for_rec(self.store, r)
                if tp.exists() and tp.stat().st_size >= 100:
                    pm = rounded_pixmap(str(tp), size)
                else:
                    pm = _no_image_pixmap(size)
            except Exception:
                pm = _no_image_pixmap(size)
        elif r.get("virtual_path") and Path(r["virtual_path"]).exists():
            pm = rounded_pixmap(str(r["virtual_path"]), size)
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
        if (pm is None or pm.isNull()) and r.get("virtual_path"):
            pm = load_pixmap(str(r["virtual_path"]), 480)
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

        # v3.0：多选时的批量操作
        sel = self._selected_records()
        if len(sel) > 1:
            menu.addSeparator()
            bmenu = menu.addMenu(tr_format("批量操作（{n} 项）▸", n=len(sel)))
            bmenu.addAction(tr("批量删除"), lambda: self._batch_delete(sel))
            bmenu.addAction(tr("批量改分组 ▸"), lambda: self._batch_set_group(sel))
            bmenu.addAction(tr("批量导出"), lambda: self._batch_export(sel))
        menu.exec(self.gallery.viewport().mapToGlobal(pos))

    def _selected_records(self) -> list:
        """当前网格多选的记录列表（去重保序）。"""
        out = []
        for li in self.gallery.selectedItems():
            r = self._by_uid.get(li.data(Qt.UserRole))
            if r and r not in out:
                out.append(r)
        return out

    def _batch_delete(self, recs: list):
        from PySide6.QtWidgets import QMessageBox
        ret = QMessageBox.question(
            self, tr("AI-Prompt-Vault"),
            tr_format("确定删除选中的 {n} 条记录吗？\n图片/视频将移入资料库回收站（trash）。",
                      n=len(recs)))
        if ret != QMessageBox.Yes:
            return
        for r in recs:
            self.store.remove(r["id"])
        self.reload()

    def _batch_set_group(self, recs: list):
        from PySide6.QtWidgets import QInputDialog, QMessageBox
        choices = [tr("未分组")] + list(self.store.groups)
        g, ok = QInputDialog.getItem(self, tr("批量改分组"),
                                     tr_format("将 {n} 条记录移动到：", n=len(recs)),
                                     choices, 0, False)
        if not ok:
            return
        group = "" if g == tr("未分组") else g
        for r in recs:
            self.store.set_record_group(r["id"], group)
        self.reload()

    def _batch_export(self, recs: list):
        from app.export_util import export_records
        from PySide6.QtWidgets import QFileDialog, QMessageBox
        from app.config import APP_NAME
        d = QFileDialog.getExistingDirectory(self, tr("选择导出文件夹"))
        if not d:
            return
        n, err = export_records(self.store, recs, d)
        if n:
            QMessageBox.information(self, tr(APP_NAME),
                                    tr_format("已导出 {n} 条记录到：{d}", n=n, d=d))
        else:
            QMessageBox.warning(self, tr(APP_NAME), tr_format("导出失败：{err}", err=err or "?"))

    def _import_from_a1111(self):
        """从 A1111 outputs 目录一键导入生成图（后台线程，不卡 UI）。"""
        from PySide6.QtCore import QThread, Signal as QtSignal
        from PySide6.QtWidgets import QMessageBox
        from app.config import APP_NAME

        out_dir = self.store.load_setting("a1111_dir", "").strip()
        if not out_dir:
            QMessageBox.information(
                self, tr(APP_NAME),
                tr("请先在「设置」中配置 A1111 outputs 目录。"))
            return

        class _ImportThread(QThread):
            done = QtSignal(int, int, int)   # imported, skipped, errors

            def __init__(self, store, out_dir):
                super().__init__()
                self.store = store
                self.out_dir = out_dir

            def run(self):
                from app.a1111 import import_from_outputs
                imported, skipped, errors = import_from_outputs(self.store, self.out_dir)
                self.done.emit(imported, skipped, errors)

        btn = self.sender() if hasattr(self, "sender") else None
        if btn is not None:
            btn.setEnabled(False)
        th = _ImportThread(self.store, out_dir)

        def _on_done(imported, skipped, errors):
            if btn is not None:
                btn.setEnabled(True)
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self.reload())
            if errors:
                QMessageBox.warning(
                    self, tr(APP_NAME),
                    tr_format("导入完成：{imported} 张新增，{skipped} 张重复跳过，{errors} 张失败",
                              imported=imported, skipped=skipped, errors=errors))
            else:
                QMessageBox.information(
                    self, tr(APP_NAME),
                    tr_format("已导入 {imported} 张，{skipped} 张重复跳过",
                              imported=imported, skipped=skipped))

        th.done.connect(_on_done)
        th.finished.connect(th.deleteLater)
        th.start()

    def _find_duplicates(self):
        """检测库中重复图片（感知哈希），列出重复组供选择删除。

        v3.4：只对真实记录查重——虚拟记录（ComfyUI 输出引用，id 不在 store 里）
        不参与查重清理，避免用户对虚拟记录点清理时静默失败。
        """
        from app.dupe_util import find_duplicate_groups
        from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                                       QListWidget, QListWidgetItem, QPushButton,
                                       QMessageBox)
        from app.config import APP_NAME
        import time as _t

        def thumb_of(r):
            if r.get("thumb_file"):
                p = self.store.thumbs_dir / r["thumb_file"]
                if p.exists():
                    return p
            if r.get("image_file"):
                p = self.store.images_dir / r["image_file"]
                if p.exists():
                    return p
            return ""

        records = self.real_records(self._records)   # 排除虚拟记录
        groups = find_duplicate_groups(records, thumb_of)
        if not groups:
            QMessageBox.information(self, tr(APP_NAME), tr("未发现重复图片 ✓"))
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(tr_format("发现 {n} 组重复图片", n=len(groups)))
        dlg.resize(520, 480)
        lay = QVBoxLayout(dlg)
        tip = QLabel(tr("以下图片哈希相同（同一张图的不同版本）。点击「清理」保留每组第一张，删除其余（移入回收站）。"))
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        lst = QListWidget()
        lst.setObjectName("dupeList")
        for g in groups:
            title = (g[0].get("title") or tr("未命名"))[:30]
            item = QListWidgetItem(f"{title}  ·  {tr_format(' {n} 张重复', n=len(g))}")
            item.setData(Qt.UserRole, [r["id"] for r in g])
            lst.addItem(item)
        lay.addWidget(lst, 1)
        btns = QHBoxLayout()
        btns.addStretch(1)
        close_btn = QPushButton(tr("关闭"))
        close_btn.setObjectName("ghost")
        close_btn.clicked.connect(dlg.accept)
        btns.addWidget(close_btn)
        clean_btn = QPushButton(tr("清理选中组"))
        clean_btn.setObjectName("primary")
        clean_btn.clicked.connect(lambda: self._cleanup_dupe_group(dlg, lst))
        btns.addWidget(clean_btn)
        lay.addLayout(btns)
        dlg.exec()

    @staticmethod
    def real_records(records: list) -> list:
        """过滤虚拟记录（ComfyUI 输出引用），只保留真实资料库记录。

        v3.4：查重清理只应作用于真实记录；虚拟记录 id（vout:...）不在 store 中，
        store.remove() 会静默返回 None。同时作为可测试的纯函数入口。
        """
        return [r for r in records if not r.get("is_virtual")]

    def _cleanup_dupe_group(self, dlg, lst):
        """清理选中的重复组：保留第一张，删除其余（进回收站）。"""
        from PySide6.QtWidgets import QMessageBox
        from app.config import APP_NAME
        cur = lst.currentItem()
        if not cur:
            QMessageBox.information(self, tr(APP_NAME), tr("请先选择一组重复图片"))
            return
        ids = cur.data(Qt.UserRole)
        removed = 0
        for rid in ids[1:]:
            # v3.4 防御：虚拟记录 id 不在 store 中，跳过（正常流程已过滤，此处兜底）
            if str(rid).startswith("vout:") or str(rid).startswith("my_works"):
                continue
            if self.store.remove(rid):
                removed += 1
        QMessageBox.information(self, tr(APP_NAME),
                                tr_format("已清理 {removed} 张重复图片（移入回收站）", removed=removed))
        self.reload()
        dlg.accept()

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
        # 视频：双击直接用系统默认播放器打开（不走图片详情编辑）
        if rec.get("media_type") == "video" and rec.get("video_file"):
            from PySide6.QtGui import QDesktopServices
            from PySide6.QtCore import QUrl
            p = self.store.videos_dir / rec["video_file"]
            if p.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
                return
        img_path = ""
        if rec.get("image_file"):
            img_path = str(self.store.images_dir / rec["image_file"])
        elif rec.get("virtual_path") and Path(rec["virtual_path"]).exists():
            img_path = str(rec["virtual_path"])
        dlg = DetailDialog(rec, img_path, self)
        # 虚拟记录（ComfyUI output 引用）：只读，保存/删除无效化
        if rec.get("is_virtual"):
            dlg.setWindowTitle(tr("作品详情") + "  ·  " + tr("我的作品（虚拟引用，不复制文件）"))
            dlg._readonly_virtual = True
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
