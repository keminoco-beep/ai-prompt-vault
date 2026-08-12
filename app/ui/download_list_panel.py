"""下载列表页：正在下载任务 + 已完成历史。

每个任务用自定义 QWidget 显示（紧凑布局、取消按钮）。
修复：选中闪烁 / 无按钮 / UI 高度过高。
"""
import time

from PySide6.QtCore import Qt, QUrl, QSize
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QProgressBar, QListWidget, QListWidgetItem, QFrame)

from app.i18n import t as tr


def _fmt_size(n: int) -> str:
    n = max(int(n or 0), 0)
    if n >= 1073741824:
        return f"{n / 1073741824:.2f} GB"
    if n >= 1048576:
        return f"{n / 1048576:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def _fmt_speed(bps: float) -> str:
    bps = max(float(bps or 0), 0)
    if bps >= 1048576:
        return f"{bps / 1048576:.1f} MB/s"
    if bps >= 1024:
        return f"{bps / 1024:.0f} KB/s"
    return f"{bps:.0f} B/s"


# 状态文本
_STATUS_LABELS = {
    "pending": lambda: tr("等待"),
    "downloading": lambda: tr("下载中"),
    "paused": lambda: tr("已暂停"),
    "done": lambda: tr("完成"),
    "failed": lambda: tr("失败"),
    "cancelled": lambda: tr("已取消"),
}


class _TaskItemWidget(QFrame):
    """单个下载任务的紧凑 item（54px 高）。"""

    def __init__(self, manager, task, is_history: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("downloadItem")
        self.setFrameShape(QFrame.NoFrame)
        self.task = task
        self.manager = manager
        self._build(is_history)
        # 历史项单击双击无副作用（已通过取消按钮支持交互）

    def _build(self, is_history: bool):
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 6, 8, 6)
        lay.setSpacing(8)

        # 左：图标
        icon_lb = QLabel(self._icon_for_status())
        icon_lb.setObjectName("popupText")
        icon_lb.setFixedWidth(18)
        icon_lb.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon_lb)

        # 中：名称 + 进度条 + 详情
        mid = QVBoxLayout()
        mid.setSpacing(1)
        mid.setContentsMargins(0, 0, 0, 0)
        self.name_lb = QLabel(self.task.name)
        self.name_lb.setObjectName("popupText")
        self.name_lb.setMinimumWidth(0)
        from PySide6.QtWidgets import QSizePolicy
        self.name_lb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        mid.addWidget(self.name_lb)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(4)
        mid.addWidget(self.bar)

        self.meta_lb = QLabel("")
        self.meta_lb.setObjectName("hint")
        self.meta_lb.setMinimumWidth(0)
        self.meta_lb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        mid.addWidget(self.meta_lb)
        lay.addLayout(mid, 1)

        # 右：暂停/继续 + 取消按钮（仅活动项）
        self.pause_btn = QPushButton(tr("暂停"))
        self.pause_btn.setObjectName("ghost")
        self.pause_btn.setCursor(Qt.PointingHandCursor)
        self.pause_btn.clicked.connect(self._on_pause)
        lay.addWidget(self.pause_btn, 0, Qt.AlignVCenter)

        self.cancel_btn = QPushButton(tr("删除"))
        self.cancel_btn.setObjectName("ghost")
        self.cancel_btn.setCursor(Qt.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._on_cancel)
        lay.addWidget(self.cancel_btn, 0, Qt.AlignVCenter)

        self.refresh()

    def _icon_for_status(self) -> str:
        return {"done": "✓", "failed": "✕", "cancelled": "⊘",
                "downloading": "↓", "pending": "·", "paused": "Ⅱ"}.get(self.task.status, "•")

    def _on_cancel(self):
        self.manager.cancel(self.task.id)

    def _on_pause(self):
        if self.task.status == "paused":
            self.manager.resume(self.task.id)
        else:
            self.manager.pause(self.task.id)

    def refresh(self):
        t = self.task
        is_active = t.status in ("pending", "downloading", "paused")
        # 进度条
        ratio = t.progress_ratio() if t.total > 0 else 0
        self.bar.setValue(int(ratio * 100))
        # meta
        if t.status in ("downloading", "paused"):
            got_s = _fmt_size(t.got)
            total_s = _fmt_size(t.total) if t.total > 0 else "—"
            spd_s = _fmt_speed(t.speed) if t.status == "downloading" else tr("已暂停")
            self.meta_lb.setText(f"{got_s} / {total_s}   ·   {spd_s}")
        else:
            size_s = _fmt_size(t.total or t.got)
            label = _STATUS_LABELS.get(t.status, lambda: t.status)()
            when = ""
            if t.end_time:
                when = time.strftime("%H:%M:%S", time.localtime(t.end_time))
            self.meta_lb.setText(f"{size_s}   ·   {label}{('   ·   ' + when) if when else ''}")
        # 按钮可见性
        self.pause_btn.setVisible(is_active)
        self.cancel_btn.setVisible(is_active)
        if t.status == "paused":
            self.pause_btn.setText(tr("继续"))
        else:
            self.pause_btn.setText(tr("暂停"))
        self.name_lb.setText(t.name)

    def sizeHint(self) -> QSize:
        return QSize(0, 54)


class DownloadListPanel(QWidget):
    """下载列表页。"""

    def __init__(self, store, manager, parent=None):
        super().__init__(parent)
        self.store = store
        self.manager = manager
        self.setSelectionMode_(None)
        self._build()
        manager.taskAdded.connect(self._refresh_all)
        manager.taskUpdated.connect(lambda *_: self._refresh_all())
        manager.taskFinished.connect(self._refresh_all)
        self._refresh_all()

    def setSelectionMode_(self, _):
        pass  # 占位防止误调用

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 14, 18, 14)
        root.setSpacing(8)

        title = QLabel(tr("下载列表"))
        title.setObjectName("pageTitle")
        root.addWidget(title)
        sub = QLabel(tr("正在下载的模型与最近完成的历史。取消会自动清理残留缓存。"))
        sub.setObjectName("pageSub")
        sub.setWordWrap(True)
        root.addWidget(sub)

        sec = QLabel(tr("正在下载"))
        sec.setObjectName("popupSection")
        root.addWidget(sec)
        self.active_list = QListWidget()
        self.active_list.setObjectName("downloadList")
        # 修复选中闪烁：禁用 selection + 焦点，避免 item 被误点击选中又取消
        self.active_list.setSelectionMode(QListWidget.NoSelection)
        self.active_list.setFocusPolicy(Qt.NoFocus)
        self.active_list.setSpacing(2)
        self.active_list.setUniformItemSizes(True)
        root.addWidget(self.active_list, 1)

        hist = QHBoxLayout()
        hist.setSpacing(6)
        h_lb = QLabel(tr("历史记录"))
        h_lb.setObjectName("popupSection")
        hist.addWidget(h_lb)
        hist.addStretch(1)
        clear_btn = QPushButton(tr("清空历史"))
        clear_btn.setObjectName("ghost")
        clear_btn.setCursor(Qt.PointingHandCursor)
        clear_btn.clicked.connect(self._clear_history)
        hist.addWidget(clear_btn)
        root.addLayout(hist)

        self.history_list = QListWidget()
        self.history_list.setObjectName("downloadList")
        self.history_list.setSelectionMode(QListWidget.NoSelection)
        self.history_list.setFocusPolicy(Qt.NoFocus)
        self.history_list.setSpacing(1)
        self.history_list.setUniformItemSizes(True)
        self.history_list.itemDoubleClicked.connect(self._open_history_item)
        root.addWidget(self.history_list, 0)

        self.empty_lb = QLabel(tr("暂无下载任务。从图库/详情面板点击「下载模型」即可在此查看进度。"))
        self.empty_lb.setObjectName("emptyHint")
        self.empty_lb.setWordWrap(True)
        self.empty_lb.setAlignment(Qt.AlignCenter)
        root.addWidget(self.empty_lb)
        root.addStretch(1)

    def _refresh_all(self):
        actives, history = self.manager.all_tasks()
        active_ids = {t.id for t in actives}
        # ---- 活动列表：增量更新（不 clear 重建，避免打断用户点击/选中）----
        # 1. 移除已不在活动集合的 item（完成/失败/取消已移入历史）
        for i in range(self.active_list.count() - 1, -1, -1):
            item = self.active_list.item(i)
            if item.data(Qt.UserRole) not in active_ids:
                w = self.active_list.itemWidget(item)
                self.active_list.takeItem(i)
                if w:
                    w.deleteLater()
        # 2. 更新已有 item 的内容（复用 widget，不重建）
        by_id = {t.id: t for t in actives}
        for i in range(self.active_list.count()):
            item = self.active_list.item(i)
            w = self.active_list.itemWidget(item)
            t = by_id.get(item.data(Qt.UserRole))
            if t is not None and w is not None:
                w.task = t
                w.refresh()
        # 3. 添加新出现的任务
        existing = {self.active_list.item(i).data(Qt.UserRole)
                    for i in range(self.active_list.count())}
        for t in actives:
            if t.id not in existing:
                item = QListWidgetItem(self.active_list)
                item.setData(Qt.UserRole, t.id)
                item.setSizeHint(QSize(0, 54))
                w = _TaskItemWidget(self.manager, t, is_history=False)
                self.active_list.addItem(item)
                self.active_list.setItemWidget(item, w)

        # ---- 历史列表：变化频率低，清空重建可接受 ----
        self.history_list.clear()
        for t in history:
            item = QListWidgetItem(self.history_list)
            item.setData(Qt.UserRole, t.id)
            item.setData(Qt.UserRole + 1, "history")
            item.setSizeHint(QSize(0, 54))
            w = _TaskItemWidget(self.manager, t, is_history=True)
            self.history_list.addItem(item)
            self.history_list.setItemWidget(item, w)
        no_active = self.active_list.count() == 0
        no_hist = self.history_list.count() == 0
        self.empty_lb.setVisible(no_active and no_hist)

    def _clear_history(self):
        self.manager.clear_history()

    def _open_history_item(self, item: QListWidgetItem):
        tid = item.data(Qt.UserRole)
        for t in self.manager.history:
            if t.id == tid and t.final_dest and t.final_dest.exists():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(t.final_dest)))
                return
        from PySide6.QtWidgets import QMessageBox
        from app.config import APP_NAME
        QMessageBox.information(self, tr(APP_NAME), tr("该文件已不存在（可能已移动/删除）。"))