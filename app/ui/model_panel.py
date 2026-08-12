"""模型管理面板：链接 ComfyUI 后浏览/重命名/删除/备注全部已装模型。

功能：
- 按 ComfyUI models/ 子目录分组浏览所有模型文件（扩展名白名单）
- 搜索 / 类型筛选 / 刷新
- 选中模型：查看大小、修改时间、路径；编辑备注（持久化到 Library/model_notes.json）
- 操作：重命名、删除（确认）、复制文件名、打开所在文件夹
"""
import json
import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QColor
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QLineEdit, QComboBox, QTreeWidget, QTreeWidgetItem,
                               QInputDialog, QMessageBox, QSplitter, QFrame, QSizePolicy)

from app import comfy
from app.i18n import t as tr, tr_format
from app.config import APP_NAME

_NOTES_FILENAME = "model_notes.json"

# 模型健康状态 → 树节点后缀标记（运行时调用 tr，避免 i18n 未初始化）
def _badge(status: str) -> str:
    return {
        "ok": "",
        "zero": "  ⚠ " + tr("空文件"),
        "tiny": "  ⚠ " + tr("疑似损坏"),
        "part": "  ⚠ " + tr("下载残留"),
    }.get(status, "")


def _status_detail(status: str) -> str:
    return {
        "ok": "",
        "zero": tr("⚠ 空文件（0 字节）：下载中断或写盘失败，建议删除后重新下载。"),
        "tiny": tr("⚠ 疑似损坏（小于 1KB）：可能是错误响应被误存，建议删除后重新下载。"),
        "part": tr("⚠ 存在 .part 下载残留：上一次下载未完成，文件可能不完整。"),
    }.get(status, "")


def _fmt_size(n: int) -> str:
    n = int(n or 0)
    if n >= 1073741824:
        return f"{n / 1073741824:.2f} GB"
    if n >= 1048576:
        return f"{n / 1048576:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


class ModelPanel(QWidget):
    """模型管理（ComfyUI 已装模型）。"""

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._notes = {}
        self._models = []          # [{rel, abs, size, mtime, subdir}]
        self._comfy_dir = ""
        self._load_notes()
        self._build()

    # ---------- 构建 ----------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        title = QLabel(tr("模型管理"))
        title.setObjectName("pageTitle")
        root.addWidget(title)
        sub = QLabel(tr("管理 ComfyUI 中已安装的模型：重命名、删除、添加备注。"))
        sub.setObjectName("pageSub")
        root.addWidget(sub)

        # 工具栏
        bar = QHBoxLayout()
        bar.setSpacing(6)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("搜索模型名…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        bar.addWidget(self.search, 1)
        bar.addWidget(self._tool_label(tr("类型")))
        self.type_combo = QComboBox()
        self.type_combo.addItem(tr("全部"))
        self.type_combo.currentTextChanged.connect(self._apply_filter)
        bar.addWidget(self.type_combo)
        refresh_btn = QPushButton(tr("刷新"))
        refresh_btn.setObjectName("ghost")
        refresh_btn.setCursor(Qt.PointingHandCursor)
        refresh_btn.clicked.connect(self.reload)
        bar.addWidget(refresh_btn)
        self.health_label = QLabel("")
        self.health_label.setObjectName("hint")
        bar.addWidget(self.health_label)
        root.addLayout(bar)

        # 主区：左列表 + 右详情
        split = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setObjectName("modelTree")
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.itemSelectionChanged.connect(self._on_select)
        split.addWidget(self.tree)

        right = QFrame()
        right.setObjectName("modelDetail")
        rl = QVBoxLayout(right)
        rl.setContentsMargins(12, 12, 12, 12)
        rl.setSpacing(8)

        self.info_name = QLabel(tr("未选中模型"))
        self.info_name.setObjectName("popupTitle")
        self.info_name.setWordWrap(True)
        self.info_name.setMinimumWidth(0)
        self.info_name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        rl.addWidget(self.info_name)

        self.info_meta = QLabel("")
        self.info_meta.setObjectName("hint")
        self.info_meta.setWordWrap(True)
        rl.addWidget(self.info_meta)

        # 健康状态（红字说明）
        self.info_health = QLabel("")
        self.info_health.setObjectName("hint")
        self.info_health.setWordWrap(True)
        rl.addWidget(self.info_health)

        note_lb = QLabel(tr("备注"))
        note_lb.setObjectName("popupSection")
        rl.addWidget(note_lb)
        self.note_edit = QLineEdit()
        self.note_edit.setPlaceholderText(tr("添加备注（保存在资料库，不修改文件）…"))
        rl.addWidget(self.note_edit)
        note_save = QPushButton(tr("保存备注"))
        note_save.setObjectName("ghost")
        note_save.setCursor(Qt.PointingHandCursor)
        note_save.clicked.connect(self._save_note)
        rl.addWidget(note_save)

        btns = QHBoxLayout()
        btns.setSpacing(6)
        rename_btn = QPushButton(tr("重命名"))
        rename_btn.setObjectName("ghost")
        rename_btn.setCursor(Qt.PointingHandCursor)
        rename_btn.clicked.connect(self._rename)
        btns.addWidget(rename_btn)
        copy_btn = QPushButton(tr("复制文件名"))
        copy_btn.setObjectName("ghost")
        copy_btn.setCursor(Qt.PointingHandCursor)
        copy_btn.clicked.connect(self._copy_name)
        btns.addWidget(copy_btn)
        reveal_btn = QPushButton(tr("打开所在文件夹"))
        reveal_btn.setObjectName("ghost")
        reveal_btn.setCursor(Qt.PointingHandCursor)
        reveal_btn.clicked.connect(self._reveal)
        btns.addWidget(reveal_btn)
        del_btn = QPushButton(tr("删除"))
        del_btn.setObjectName("ghost")
        del_btn.setCursor(Qt.PointingHandCursor)
        del_btn.clicked.connect(self._delete)
        btns.addWidget(del_btn)
        rl.addLayout(btns)
        rl.addStretch(1)
        split.addWidget(right)
        split.setSizes([340, 360])
        root.addWidget(split, 1)

        # 空状态提示（未设置 ComfyUI）
        self.empty_label = QLabel(tr("尚未链接 ComfyUI。请先在「设置」中选择 ComfyUI 文件夹。"))
        self.empty_label.setObjectName("emptyHint")
        self.empty_label.setAlignment(Qt.AlignCenter)
        self.empty_label.setVisible(False)
        root.addWidget(self.empty_label)

        self._current = None

    @staticmethod
    def _tool_label(text: str) -> QLabel:
        lb = QLabel(text)
        lb.setObjectName("toolLabel")
        return lb

    # ---------- 备注 ----------
    def _notes_path(self) -> Path:
        return self.store.root / _NOTES_FILENAME

    def _load_notes(self):
        try:
            p = self._notes_path()
            if p.exists():
                self._notes = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            self._notes = {}

    def _save_notes_file(self):
        try:
            self._notes_path().write_text(
                json.dumps(self._notes, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ---------- 扫描 ----------
    def reload(self):
        self._comfy_dir = self.store.load_setting("comfyui_dir", "") or ""
        self._models = []
        self.tree.clear()
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        self.type_combo.addItem(tr("全部"))
        if not self._comfy_dir or not Path(self._comfy_dir).is_dir():
            self.tree.setVisible(False)
            self.empty_label.setVisible(True)
            self.type_combo.blockSignals(False)
            return
        self.tree.setVisible(True)
        self.empty_label.setVisible(False)

        root = Path(self._comfy_dir) / "models"
        if not root.is_dir():
            root = Path(self._comfy_dir)
        exts = set(comfy.MODEL_EXTENSIONS)
        for p in root.rglob("*"):
            if not p.is_file() or p.name.endswith(".part"):
                continue
            suf = p.suffix.lower()
            if suf not in exts or suf == ".txt":
                # .txt 是 ComfyUI 里的指引/说明文件，不是模型，健康检查忽略
                continue
            rel = p.relative_to(root).as_posix()
            sub = str(p.parent.relative_to(root)) if p.parent != root else ""
            st = p.stat()
            status = "ok"
            if st.st_size == 0:
                status = "zero"          # 空文件
            elif st.st_size < 1024:
                status = "tiny"          # 疑似损坏（<1KB，可能是错误响应）
            if Path(str(p) + ".part").exists():
                status = "part"          # 存在下载残留 .part
            self._models.append({
                "rel": rel, "abs": str(p), "subdir": sub,
                "size": st.st_size, "mtime": st.st_mtime,
                "status": status,
            })
        for sub in sorted({m["subdir"] for m in self._models}):
            self.type_combo.addItem(sub or tr("（根目录）"))
        self.type_combo.blockSignals(False)
        # 健康摘要
        bad = [m for m in self._models if m.get("status", "ok") != "ok"]
        if bad:
            self.health_label.setText(
                tr_format("⚠ {n} 个模型健康异常", n=len(bad)))
            self.health_label.setStyleSheet("color: #ff9aa5;")
        else:
            self.health_label.setText(tr("全部模型正常 ✓"))
            self.health_label.setStyleSheet("")
        self._apply_filter()
        self._current = None
        self._show_none()

    def _apply_filter(self):
        kw = self.search.text().strip().lower()
        typ = self.type_combo.currentText()
        if typ == tr("全部"):
            typ = ""
        elif typ == tr("（根目录）"):
            typ = "\x00root"
        self.tree.blockSignals(True)
        self.tree.clear()
        groups = {}
        for m in self._models:
            if kw and kw not in m["rel"].lower():
                continue
            if typ == "\x00root":
                if m["subdir"]:
                    continue
            elif typ and m["subdir"] != typ:
                continue
            groups.setdefault(m["subdir"], []).append(m)
        for sub in sorted(groups):
            gitem = QTreeWidgetItem([sub or tr("（根目录）")])
            gitem.setFlags(Qt.ItemIsEnabled)
            self.tree.addTopLevelItem(gitem)
            for m in sorted(groups[sub], key=lambda x: x["rel"].lower()):
                note = self._notes.get(m["rel"], "")
                badge = _badge(m.get("status", "ok"))
                item = QTreeWidgetItem(
                    [m["rel"].split("/")[-1] + badge + (f"  · {note}" if note else "")])
                item.setData(0, Qt.UserRole, m["rel"])
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if m.get("status", "ok") != "ok":
                    item.setForeground(0, QColor("#ff9aa5"))
                gitem.addChild(item)
            gitem.setExpanded(True)
        self.tree.blockSignals(False)

    # ---------- 选择 ----------
    def _selected_model(self):
        items = self.tree.selectedItems()
        if not items:
            return None
        rel = items[0].data(0, Qt.UserRole)
        if not rel:
            return None
        return next((m for m in self._models if m["rel"] == rel), None)

    def _on_select(self):
        m = self._selected_model()
        self._current = m
        if not m:
            self._show_none()
            return
        name = m["rel"].split("/")[-1]
        self.info_name.setText(name)
        self.info_name.setToolTip(m["rel"])
        mtime = datetime.fromtimestamp(m["mtime"]).strftime("%Y-%m-%d %H:%M")
        self.info_meta.setText(
            f"{tr('类型')}: {m['subdir'] or tr('（根目录）')}    "
            f"{tr('大小')}: {_fmt_size(m['size'])}    {mtime}\n{m['abs']}")
        detail = _status_detail(m.get("status", "ok"))
        self.info_health.setText(detail)
        self.info_health.setStyleSheet("color: #ff9aa5;" if detail else "")
        self.note_edit.setText(self._notes.get(m["rel"], ""))

    def _show_none(self):
        self._current = None
        self.info_name.setText(tr("未选中模型"))
        self.info_meta.setText("")
        self.info_health.setText("")
        self.info_health.setStyleSheet("")
        self.note_edit.setText("")

    # ---------- 操作 ----------
    def _save_note(self):
        if not self._current:
            return
        self._notes[self._current["rel"]] = self.note_edit.text().strip()
        self._save_notes_file()
        self._apply_filter()
        QMessageBox.information(self, tr(APP_NAME), tr("备注已保存 ✓"))

    def _rename(self):
        m = self._current
        if not m:
            return
        old = m["rel"].split("/")[-1]
        name, ok = QInputDialog.getText(self, tr("重命名模型"), tr("新文件名："), text=old)
        if not ok or not name.strip():
            return
        name = comfy.safe_filename(name.strip(), Path(old).suffix)
        src = Path(m["abs"])
        dst = src.with_name(name)
        if dst.exists():
            QMessageBox.warning(self, tr(APP_NAME), tr("同名文件已存在"))
            return
        try:
            src.rename(dst)
        except Exception as e:
            QMessageBox.warning(self, tr(APP_NAME), tr_format("重命名失败：{err}", err=e))
            return
        old_rel, new_rel = m["rel"], dst.relative_to(Path(self._comfy_dir) / "models").as_posix() \
            if (Path(self._comfy_dir) / "models").exists() else dst.relative_to(Path(self._comfy_dir)).as_posix()
        if old_rel in self._notes:
            self._notes[new_rel] = self._notes.pop(old_rel)
            self._save_notes_file()
        self.reload()
        QMessageBox.information(self, tr(APP_NAME), tr("重命名成功 ✓"))

    def _copy_name(self):
        m = self._current
        if not m:
            return
        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(m["rel"].split("/")[-1])
        QMessageBox.information(self, tr(APP_NAME), tr("文件名已复制 ✓"))

    def _reveal(self):
        m = self._current
        if not m:
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(m["abs"]).parent)))

    def _delete(self):
        m = self._current
        if not m:
            return
        name = m["rel"].split("/")[-1]
        ret = QMessageBox.question(
            self, tr(APP_NAME),
            tr_format("确定删除模型「{name}」吗？\n此操作会直接删除文件，无法恢复。", name=name),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        try:
            os.remove(m["abs"])
        except Exception as e:
            QMessageBox.warning(self, tr(APP_NAME), tr_format("删除失败：{err}", err=e))
            return
        self._notes.pop(m["rel"], None)
        self._save_notes_file()
        self.reload()
        QMessageBox.information(self, tr(APP_NAME), tr("已删除 ✓"))
