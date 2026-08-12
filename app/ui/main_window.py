import logging
from app.i18n import t as tr, tr_format
"""主窗口：侧边栏导航 + 分组区 + 收藏/浏览两个板块 + 全局粘贴快捷键。"""
from PySide6.QtCore import Qt, QTimer

logger = logging.getLogger(__name__)
from PySide6.QtGui import (QKeySequence, QShortcut, QPainter, QPixmap,
                           QColor, QFont, QBrush, QLinearGradient)
from PySide6.QtCore import QRectF
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QStackedWidget, QButtonGroup, QLineEdit,
                               QPlainTextEdit, QTextEdit, QComboBox, QApplication,
                               QTreeWidget, QTreeWidgetItem, QMenu, QInputDialog,
                               QToolButton, QMessageBox)

from app.config import APP_NAME, VERSION
from app.ui.collect_panel import CollectPanel
from app.ui.gallery_panel import GalleryPanel
from app.ui.model_panel import ModelPanel
from app.filters import group_counts


class MainWindow(QMainWindow):
    # 后台扫描输出文件夹的超时兜底（秒）。正常 4877 图首次扫描 ~4 分钟内完成
    # （命中内存缓存秒级）；仅当扫描线程异常阻塞/死循环时触发强制清除「正在扫描」标记，
    # 避免 UI 永远卡在「正在后台扫描输出文件夹…」。测试可用短值覆盖。
    MAX_SCAN_SECONDS = 300

    # v3.9：定时增量监听输出文件夹的间隔（秒）。只 diff 不重扫（省磁盘读写、0 卡顿）；
    # 无 output dirs 时回调直接 return，不报错；全量/手动刷新后重置计时起点。
    DELTA_SCAN_SECONDS = 15

    def __init__(self, store, output_scan: bool = True):
        super().__init__()
        self.store = store
        self.output_scan = output_scan
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
        from app.ui.style import tcolor
        logo.setStyleSheet(f"font-size:16px; font-weight:700; color:{tcolor('logo_color')};")
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
        self.model_btn = self._nav_btn("◫  " + tr("模型管理"), 2)
        sv.addWidget(self.collect_btn)
        sv.addWidget(self.gallery_btn)
        sv.addWidget(self.model_btn)

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
        # 下载列表按钮（带徽标，显示活动任务数）
        self.download_btn_sidebar = QPushButton("📥  " + tr("下载列表"))
        self.download_btn_sidebar.setObjectName("sideSmall")
        self.download_btn_sidebar.clicked.connect(self._show_download_page)
        sv.addWidget(self.download_btn_sidebar)
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
        # v3.5：「刷新」按钮 → 后台扫描输出文件夹（增量扫描 + 写缓存 + done 后无条件 reload）
        self.gallery_panel.refreshRequested.connect(self._start_output_scan)
        self.model_panel = ModelPanel(self.store)

        # 全局下载管理器（必须在 DownloadListPanel 之前创建）
        from app.ui.download_manager import DownloadManager
        self.download_manager = DownloadManager(self.store, self)
        # 启动时清理 .part 残留
        self.download_manager.cleanup_partials()
        # 飞行动画请求
        self.download_manager.flyRequested.connect(self._fly_to_download)

        from app.ui.download_list_panel import DownloadListPanel
        self.download_panel = DownloadListPanel(self.store, self.download_manager)

        self.stack.addWidget(self.collect_panel)
        self.stack.addWidget(self.gallery_panel)
        self.stack.addWidget(self.model_panel)
        self.stack.addWidget(self.download_panel)
        self.collect_panel.recordsSaved.connect(self.gallery_panel.reload)
        self.collect_panel.recordsSaved.connect(self.refresh_groups)
        self.gallery_panel.groupChanged.connect(self.refresh_groups)
        self.stack.currentChanged.connect(self._on_page_changed)
        root.addWidget(self.stack, 1)

        self.collect_btn.setChecked(True)
        self.stack.setCurrentIndex(0)
        self.refresh_groups()
        # 启动徽标刷新
        self.download_manager.taskUpdated.connect(lambda *_: self._update_download_badge())
        self.download_manager.taskFinished.connect(lambda *_: self._update_download_badge())
        # 后台扫描 ComfyUI output（首次全量解析慢，延迟到窗口就绪后；selftest 跳过）
        from PySide6.QtCore import QTimer
        self._scan_thread = None
        self._thumb_thread = None
        # v4.0：缩略图线程占用中收到新请求时置位，当前线程结束后链式重启一轮——
        # 修复「增量新增图片永远不生成缩略图」（旧逻辑直接 return 跳过，运行中的
        # 线程快照不含新增文件，且无任何后续触发）。
        self._thumb_pending = False
        # 扫描超时兜底定时器（非重复）：_start_output_scan 启动，正常完成/强制清除时停止
        self._scan_timeout = QTimer(self)
        self._scan_timeout.setSingleShot(True)
        self._scan_timeout.timeout.connect(self._force_clear_scanning)
        # v3.9：定时增量监听输出文件夹（15s 一次，只 diff 不重扫，0 卡顿）。
        # 仅在配置了 output dirs 时工作；无 dirs 时回调直接 return（测试环境静默）。
        self._delta_timer = QTimer(self)
        self._delta_timer.setInterval(int(getattr(self, "DELTA_SCAN_SECONDS", 15)) * 1000)
        self._delta_timer.timeout.connect(self._on_delta_timer)
        self._delta_thread = None
        if self.output_scan:
            self._delta_timer.start()
        if self.output_scan:
            QTimer.singleShot(800, self._start_output_scan)

    def closeEvent(self, event):
        """关闭窗口时中断并等待后台扫描/缩略图线程结束（避免退出挂起）。

        v3.4：线程 done 后 finished→deleteLater 会销毁 C++ 对象，此时引用仍指向
        已删除对象，isRunning() 会抛 RuntimeError——用 try/except 防御，避免退出崩溃。
        """
        try:
            self._scan_timeout.stop()
        except Exception:
            pass
        try:
            self._delta_timer.stop()
        except Exception:
            pass
        for attr in ("_scan_thread", "_thumb_thread", "_delta_thread"):
            th = getattr(self, attr, None)
            if th is None:
                continue
            try:
                if th.isRunning():
                    th.requestInterruption()
                    th.wait(5000)
            except RuntimeError:
                pass   # 线程已完成且 C++ 对象已 deleteLater 销毁
            except Exception:
                pass
        super().closeEvent(event)

    def _open_settings(self):
        from app.ui.settings_dialog import SettingsDialog
        dlg = SettingsDialog(self.store, self)
        dlg.theme_changed.connect(self.apply_theme)
        dlg.outputDirsChanged.connect(self._on_output_dirs_changed)
        dlg.settingsApplied.connect(self._on_settings_applied)
        dlg.exec()

    def _on_settings_applied(self):
        """设置保存后：仅刷新分组 + 图库（读缓存秒级），不触发后台重扫。

        v3.9：settingsApplied 由 SettingsDialog._save 发出——改虚拟作品显示上限等
        即时生效的设置时，避免 outputDirsChanged 的全量重扫（改个数字就重扫太浪费）。
        """
        try:
            self.refresh_groups()
        except Exception:
            pass
        try:
            self.gallery_panel.reload()
        except Exception:
            pass

    def _on_output_dirs_changed(self):
        """设置保存后输出目录变化：立即刷新分组（秒级枚举）+ 图库（读缓存）+ 后台扫描写缓存。

        v3.4 修复：之前只 refresh_groups + 后台扫描，图库页不刷新，
        用户保存设置后图库看起来"没变化"。这里立即 reload 一次（读磁盘缓存，
        有缓存秒级显示；无缓存先空，后续 _on_output_scanned / 切页 reload 兜底）。
        v3.4.2 修复（缓存失配根因）：配置已变，旧磁盘/内存缓存必然失配（缓存 dirs
        集合 != 新配置），主动删除磁盘缓存并清空进程内缓存——避免 scan_output_images
        白加载 9.5MB 旧数据再丢弃全量重扫（用户实测 255s 卡顿）；删除后本次扫描
        全新写入，refresh_groups 走 quick_group_counts 兜底（秒级枚举）。
        """
        # 1) 旧缓存必然失配：删除失配的磁盘缓存文件 + 清空内存缓存（旧 key 失效）。
        #    invalidate_stale_cache 仅删「与当前配置失配」的缓存（真实配置变化时必然
        #    失配），避免 scan 白加载 9.5MB 旧数据再丢弃重扫；有效缓存保留不误删。
        try:
            from app import comfy_output as _co
            try:
                _co.invalidate_stale_cache(
                    str(self.store.root / "comfy_output_cache.json"),
                    _co.configured_output_dirs(self.store))
            except Exception:
                pass
            try:
                _co._cache.clear()
                _co.clear_memos()
            except Exception:
                pass
        except Exception:
            pass
        self.refresh_groups()
        try:
            self.gallery_panel.reload()
        except Exception:
            pass
        self._start_output_scan()

    def apply_theme(self, theme_name: str = None):
        """主题切换：重设应用级 QSS + 刷新硬编码颜色控件（即时生效）。"""
        from PySide6.QtWidgets import QApplication
        from app.ui import style as st
        t = theme_name or st.theme()
        st.set_theme(t)
        app = QApplication.instance()
        if app:
            app.setStyleSheet(st.qss(t))
        # 刷新硬编码颜色的控件
        try:
            self.collect_panel.drop.apply_theme_style()
        except Exception:
            pass
        try:
            self.gallery_panel._popup.apply_theme_style()
        except Exception:
            pass
        try:
            self.gallery_panel.sidebar._apply_theme_style()
        except Exception:
            pass
        # logo 文字颜色
        for lbl in self.findChildren(QLabel):
            if lbl.objectName() == "logoDot":
                from app.ui.style import tcolor
                lbl.setStyleSheet(f"font-size:16px; font-weight:700; color:{tcolor('logo_color')};")
                break

    def _on_page_changed(self, idx):
        """切页时刷新：模型管理页重扫 ComfyUI；图库页重载虚拟记录（走缓存，秒级）。"""
        if idx == 2:
            self.model_panel.reload()
        elif idx == 1:
            try:
                self.gallery_panel.reload()
            except Exception:
                pass

    def _start_output_scan(self):
        """后台线程扫描 ComfyUI 输出文件夹（首次全量解析较慢，不阻塞启动）。

        v3.4：开始扫描时标记 gallery 空态提示「正在后台扫描输出文件夹…」。
        v3.4.1 修复：快速重新选定输出目录时并发跑多个扫描线程、旧线程 done 干扰
        新线程状态、扫描异常阻塞时状态永远不清除 —— 这里统一处理：
          1) 启动前中断并等待旧扫描线程（最多 2 秒，超时硬覆盖，新线程照常启动）；
          2) _on_output_scanned 做线程身份校验，旧线程 done 一律忽略；
          3) set_scanning(True) 后启动非重复超时兜底定时器，异常阻塞时强制清除。
        """
        from PySide6.QtCore import QThread, Signal as QtSignal
        from app.comfy_output import configured_output_dirs
        dirs = configured_output_dirs(self.store)
        if not dirs:
            self._scan_timeout.stop()
            self.gallery_panel.set_scanning(False)
            return
        cache_file = str(self.store.root / "comfy_output_cache.json")

        # 1) 处理旧扫描线程：请求中断 + 最多等 2 秒；超时则硬覆盖（新线程照常启动）
        old = self._scan_thread
        if old is not None:
            try:
                if old.isRunning():
                    old.requestInterruption()
                    old.wait(2000)
            except RuntimeError:
                pass   # 线程已完成且 C++ 对象已 deleteLater 销毁
            except Exception:
                pass

        self.gallery_panel.set_scanning(True)

        class _ScanThread(QThread):
            done = QtSignal()

            def run(self):
                try:
                    from app.comfy_output import scan_output_images
                    scan_output_images(dirs, cache_file,
                                       cancel_cb=lambda: self.isInterruptionRequested())
                except Exception:
                    pass
                self.done.emit()

        th = _ScanThread(self)
        th.done.connect(self._on_output_scanned)
        th.finished.connect(th.deleteLater)
        self._scan_thread = th
        # 2) 超时保险：非重复定时器，异常阻塞/死循环时强制清除扫描标记；
        #    正常完成（_on_output_scanned）或下次扫描前取消/重置。
        self._scan_timeout.stop()
        self._scan_timeout.start(int(getattr(self, "MAX_SCAN_SECONDS", 300)) * 1000)
        # v3.9：全量/手动刷新后重置定时增量监听的计时起点（restart 会重新计数）
        try:
            self._delta_timer.start()
        except Exception:
            pass
        th.start()

    def _on_output_scanned(self):
        """扫描完成：刷新分组树 + 图库（无条件 reload，读缓存秒级）+ 后台生成缩略图。

        v3.4 修复：之前只在「图库当前可见」时才 reload——用户保存设置时在设置
        对话框，扫描完成时当前页不是图库 → 图库不刷新。改为无条件 reload
        （读磁盘缓存秒级不卡），并清除「扫描中」空态标记。
        v3.4.1 修复：线程身份校验——旧扫描线程（已被新线程覆盖引用）的 done 信号
        不再无条件清状态/刷新，避免干扰新扫描状态。直接调用（sender() 为 None，
        如测试/内部同步调用）仍走原逻辑，向后兼容。
        """
        sender = self.sender()
        if sender is not None and sender is not self._scan_thread:
            return   # 旧扫描线程的完成信号：忽略
        self._scan_timeout.stop()
        self.gallery_panel.set_scanning(False)
        self.refresh_groups()
        try:
            self.gallery_panel.reload()
        except Exception:
            pass
        self._start_thumb_gen()

    # ================= v3.9：定时增量监听输出文件夹 =================
    def _on_delta_timer(self):
        """定时增量监听回调：后台 diff 输出文件夹，有变化才刷新（无变化零开销）。

        - 无 output dirs / 全量或增量扫描线程占用中 → 直接 return（不报错，静默）
        - 线程身份校验沿用 _on_output_scanned 的模式（旧线程 done 忽略）
        """
        from app.comfy_output import configured_output_dirs
        dirs = configured_output_dirs(self.store)
        if not dirs:
            return
        # 全量/增量扫描线程占用中：跳过本次（避免并发读写同一磁盘缓存）
        for attr in ("_scan_thread", "_delta_thread"):
            th = getattr(self, attr, None)
            if th is None:
                continue
            try:
                if th.isRunning():
                    return
            except RuntimeError:
                pass
        cache_file = str(self.store.root / "comfy_output_cache.json")

        from PySide6.QtCore import QThread, Signal as QtSignal
        class _DeltaThread(QThread):
            done = QtSignal(object)   # dict: added/removed/changed/records

            def run(self):
                try:
                    from app.comfy_output import scan_output_images_delta
                    result = scan_output_images_delta(
                        dirs, cache_file,
                        cancel_cb=lambda: self.isInterruptionRequested())
                except Exception:
                    result = {"added": 0, "removed": 0, "changed": 0, "records": []}
                try:
                    self.done.emit(result)
                except RuntimeError:
                    pass

        th = _DeltaThread(self)
        th.done.connect(self._on_delta_scanned)
        th.finished.connect(th.deleteLater)
        self._delta_thread = th
        th.start()

    def _on_delta_scanned(self, result):
        """增量扫描完成：有变化才刷新（分组 + 图库 + 缩略图），无变化什么都不做。"""
        sender = self.sender()
        if sender is not None and sender is not self._delta_thread:
            return   # 旧增量线程的完成信号：忽略
        try:
            if not result:
                return
            n = ((result.get("added") or 0) + (result.get("removed") or 0)
                 + (result.get("changed") or 0))
            if n <= 0:
                return   # 无变化：不 reload、不刷 UI（真正 0 开销无感）
            self.refresh_groups()
            try:
                self.gallery_panel.reload()
            except Exception:
                pass
            self._start_thumb_gen()
        except Exception:
            pass

    def _force_clear_scanning(self):
        """扫描超时兜底：扫描线程异常阻塞/死循环时强制清除「正在扫描」标记。

        正常扫描（含 4877 图首次全量解析）远快于 MAX_SCAN_SECONDS；仅当线程异常
        卡住且 _on_output_scanned 永不触发时，此回调保证 UI 不会永远显示
        「正在后台扫描输出文件夹…」，同时刷新一次图库（读缓存，秒级）。
        """
        self._scan_timeout.stop()
        if self.gallery_panel._scanning:
            logger.warning("后台扫描输出文件夹超时（>%s 秒），强制清除「扫描中」标记",
                           int(getattr(self, "MAX_SCAN_SECONDS", 300)))
            self.gallery_panel.set_scanning(False)
            try:
                self.gallery_panel.reload()
            except Exception:
                pass

    def _start_thumb_gen(self):
        """后台线程为虚拟记录生成缩略图缓存（每批 60 张刷新图库）。

        v4.0：若已有缩略图线程在跑，不直接跳过——置 _thumb_pending 标记，
        当前线程结束后 _on_thumb_finished 自动再启动一轮，保证增量新增的文件
        最终一定被处理（generate_all_thumbs 幂等，只补缺失的缩略图，成本低）。
        """
        from PySide6.QtCore import QThread, Signal as QtSignal
        from app.comfy_output import configured_output_dirs
        dirs = configured_output_dirs(self.store)
        if not dirs:
            return
        # v3.9：已有缩略图线程在跑则跳过（增量监听每 15s 可能触发，避免线程堆积）
        old = getattr(self, "_thumb_thread", None)
        if old is not None:
            try:
                if old.isRunning():
                    self._thumb_pending = True
                    return
            except RuntimeError:
                pass
        try:
            from app.comfy_output import thumb_dir_for
            thumb_dir = thumb_dir_for(self.store)
        except Exception:
            return

        class _ThumbThread(QThread):
            progress = QtSignal(int, int)   # done, total

            def run(self):
                try:
                    from app.comfy_output import generate_all_thumbs
                    generate_all_thumbs(dirs, thumb_dir,
                                        cancel_cb=lambda: self.isInterruptionRequested(),
                                        batch_cb=lambda d, t: self.progress.emit(d, t))
                except Exception:
                    pass

        th = _ThumbThread(self)
        th.progress.connect(self._on_thumb_progress)
        th.finished.connect(self._on_thumb_finished)
        th.finished.connect(th.deleteLater)
        self._thumb_thread = th
        th.start()

    def _on_thumb_finished(self):
        """缩略图线程结束：若期间有新的缩略图请求（增量新增文件），链式重启一轮。"""
        if getattr(self, "_thumb_pending", False):
            self._thumb_pending = False
            self._start_thumb_gen()

    def _on_thumb_progress(self, done, total):
        """缩略图批量生成后刷新图库（仅当图库可见时）。"""
        try:
            if self.stack.currentWidget() is self.gallery_panel:
                self.gallery_panel.reload()
            # v4.0：精准重渲染仍显示占位图的虚拟记录 tile（缩略图刚生成）——
            # 不依赖 reload 指纹变化，避免占位图被 LRU 缓存导致永不更新
            self.gallery_panel._refresh_missing_thumbs()
        except Exception:
            pass

    def _show_download_page(self):
        # 下载页是独立面板（不占用 nav 高亮），直接切换
        self.stack.setCurrentIndex(3)

    def _update_download_badge(self):
        n = self.download_manager.active_count()
        suffix = f"  ({n})" if n else ""
        self.download_btn_sidebar.setText(f"📥  {tr('下载列表')}{suffix}")

    def _fly_to_download(self, src_x: int, src_y: int):
        """小动画：从 (src_x, src_y) 飞到侧栏下载列表按钮位置，模拟 macOS 下载飞入。

        动画对象必须保存引用（局部变量会被 GC 回收导致动画不执行）。
        """
        try:
            from PySide6.QtCore import QPropertyAnimation, QPoint
            from PySide6.QtWidgets import QLabel, QGraphicsOpacityEffect
        except Exception:
            return
        end_btn = self.download_btn_sidebar
        if not end_btn or not end_btn.isVisible():
            return
        from PySide6.QtCore import QPoint
        start = self.mapFromGlobal(QPoint(src_x, src_y))
        btn_center = end_btn.mapToGlobal(end_btn.rect().center())
        end = self.mapFromGlobal(QPoint(btn_center.x(), btn_center.y()))
        # 飞行小图标
        lbl = QLabel("📥", self)
        lbl.setFixedSize(38, 38)
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(
            "QLabel { background: qlineargradient(x1:0,y1:0,x2:1,y2:1,"
            "stop:0 #6d5ef0, stop:1 #4f7de0); border-radius: 19px;"
            " color: white; font-size: 20px; border: 2px solid #fff; }")
        lbl.move(start.x() - 19, start.y() - 19)
        lbl.show()
        lbl.raise_()
        op = QGraphicsOpacityEffect(lbl)
        lbl.setGraphicsEffect(op)
        # 位置动画（保存引用，防 GC）
        anim_pos = QPropertyAnimation(lbl, b"pos")
        anim_pos.setDuration(650)
        anim_pos.setStartValue(lbl.pos())
        anim_pos.setEndValue(QPoint(end.x() - 19, end.y() - 19))
        anim_op = QPropertyAnimation(op, b"opacity")
        anim_op.setDuration(650)
        anim_op.setStartValue(1.0)
        anim_op.setEndValue(0.0)
        # 持有引用直到动画结束
        if not hasattr(self, "_fly_anims"):
            self._fly_anims = []
        self._fly_anims.append(anim_pos)
        self._fly_anims.append(anim_op)

        def _cleanup():
            try:
                lbl.deleteLater()
                if anim_pos in self._fly_anims:
                    self._fly_anims.remove(anim_pos)
                if anim_op in self._fly_anims:
                    self._fly_anims.remove(anim_op)
            except Exception:
                pass

        anim_pos.finished.connect(_cleanup)
        anim_op.finished.connect(_cleanup)
        anim_pos.start()
        anim_op.start()

    # ---------- 分组 ----------
    def refresh_groups(self):
        """重建左侧分组树（全部/未分组/各自定义组 + 计数 + 「我的作品」虚拟组）。"""
        counts = group_counts(self.store.records)
        # 「我的作品」：ComfyUI 输出文件夹虚拟分组（含子目录子组，多目录按文件夹分组）
        # 优先读磁盘缓存（秒级，不枚举目录，且校验目录集合匹配）；无缓存/集合不匹配时
        # 快速统计（只枚举文件，不解析 PNG 元数据），让分组立即可见；
        # 元数据由后台线程扫描补全
        vgroups = {}
        vtotal = 0
        try:
            from app.comfy_output import (load_cached_groups, quick_group_counts,
                                          GROUP_ROOT, configured_output_dirs)
            dirs = configured_output_dirs(self.store)
            cache_f = str(self.store.root / "comfy_output_cache.json")
            vgroups = load_cached_groups(cache_f, dirs)
            if not vgroups:
                vgroups = quick_group_counts(dirs)
            vtotal = sum(vgroups.values())
        except Exception:
            vgroups = {}
        self.group_tree.blockSignals(True)
        self.group_tree.clear()
        root = QTreeWidgetItem([tr("图片分组")])
        root.setFlags(Qt.ItemIsEnabled)
        self.group_tree.addTopLevelItem(root)
        items = {}

        all_item = QTreeWidgetItem(
            [f"{tr('全部图片')}（{len(self.store.records) + vtotal}）"])
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

        # 「我的作品」虚拟组（层级：父组 + 子目录/多目录子组）
        if vgroups:
            my_item = QTreeWidgetItem([f"{tr('我的作品')}（{vtotal}）"])
            my_item.setData(0, Qt.UserRole, GROUP_ROOT)
            my_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            root.addChild(my_item)
            items[GROUP_ROOT] = my_item
            self._build_virtual_tree(my_item, items, vgroups)
            my_item.setExpanded(True)
        self._group_items = items
        root.setExpanded(self.collapse_btn.isChecked())
        self.group_tree.setCurrentItem(all_item)
        self.group_tree.blockSignals(False)

    def _build_virtual_tree(self, my_item, items, vgroups):
        """把 {group: count} 构造成「我的作品」下的层级树。

        每个分组用完整 group key 作为点击筛选值（filter_records 按前缀匹配，
        父组自动包含子组）；多目录时顶层即 my_works/<目录名>。
        """
        from app.comfy_output import GROUP_ROOT
        root_node = {"count": 0, "children": {}}
        subs = sorted({g for g in vgroups if g != GROUP_ROOT})
        for g in subs:
            segs = g[len(GROUP_ROOT) + 1:].split("/")
            acc = vgroups.get(g, 0)
            node = root_node
            for seg in segs:
                child = node["children"].setdefault(seg, {"count": 0, "children": {}})
                child["count"] += acc
                node = child

        def add(parent_item, node, prefix):
            for seg in sorted(node["children"]):
                child = node["children"][seg]
                key = f"{prefix}/{seg}" if prefix else seg
                full = f"{GROUP_ROOT}/{key}"
                ci = QTreeWidgetItem([f"{seg}（{child['count']}）"])
                ci.setData(0, Qt.UserRole, full)
                ci.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                parent_item.addChild(ci)
                items[full] = ci
                add(ci, child, key)

        add(my_item, root_node, "")

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
