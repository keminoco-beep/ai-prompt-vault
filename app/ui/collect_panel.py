from app.i18n import t as tr, tr_format, rev
"""收藏面板：拖拽/粘贴图片、Civitai 链接导入、提示词与模型表单。"""
import re
import uuid

from PySide6.QtCore import Qt, QBuffer, QIODevice, QThreadPool, QTimer, QSize, QUrl, Signal
from PySide6.QtGui import QPixmap, QImage, QPainter, QColor, QFont, QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel,
                               QFrame, QLineEdit, QPlainTextEdit, QComboBox, QPushButton,
                               QListWidget, QListWidgetItem, QApplication)

from app.civitai import parse_link, BASE_MODEL_GROUPS
from app.filters import merge_loras
from app.thumbs import image_size, load_pixmap, rounded_pixmap, make_thumbnail
from app.workers import Worker, WorkerSignals

# 模型清单中每行可选的类型（含 Civitai 常见类型的中文标签）
MODEL_TYPE_CHOICES = [tr("大模型"), "LoRA", tr("嵌入"), tr("VAE"), tr("超网络"), tr("ControlNet"),
                      tr("放大模型"), tr("工作流"), tr("运动模块"), tr("文本编码器"), tr("其他")]
PLACEHOLDER_TEXT = tr("把网页上的例图直接拖到这里\n\n或按 Ctrl+V 粘贴剪贴板里的图片\n\n也支持拖入 / 粘贴 Civitai 链接，自动提取提示词与全部模型")


def _placeholder_pixmap(size: int) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor("#22223a"))
    p.setPen(QColor("#3a3a56"))
    p.drawRoundedRect(2, 2, size - 4, size - 4, 12, 12)
    p.setPen(QColor("#7d7d95"))
    f = QFont()
    f.setPointSize(18)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "…")
    p.end()
    return pm


class DropZone(QFrame):
    dropped = Signal(object)

    def apply_theme_style(self):
        """按当前主题设置拖放区样式（主题切换时调用刷新）。"""
        from app.ui.style import tcolor
        self.setStyleSheet(f"""
            QFrame#dropZone {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {tcolor("drop_bg_a")}, stop:1 {tcolor("drop_bg_b")});
                border: 2px dashed {tcolor("drop_border")}; border-radius: 14px;
            }}
            QFrame#dropZone[active="true"] {{
                border: 2px dashed {tcolor("drop_active_border")};
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {tcolor("drop_active_bg_a")}, stop:1 {tcolor("drop_active_bg_b")});
            }}
            QLabel#dzText {{ color: {tcolor("drop_text")}; font-size: 15px; }}
            QLabel#dzSub {{ color: {tcolor("drop_sub")}; font-size: 12px; }}
        """)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(150)
        self.setObjectName("dropZone")
        self.apply_theme_style()
        lay = QVBoxLayout(self)
        lay.setSpacing(4)
        self.text = QLabel(PLACEHOLDER_TEXT)
        self.text.setObjectName("dzText")
        self.text.setAlignment(Qt.AlignCenter)
        lay.addStretch(1)
        lay.addWidget(self.text)
        self.sub = QLabel(tr("支持一次拖入多张图片，也支持拖入本地图片文件"))
        self.sub.setObjectName("dzSub")
        self.sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.sub)
        lay.addStretch(1)

    def _active(self, on: bool):
        self.setProperty("active", "true" if on else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e):
        if self._has_images(e.mimeData()):
            self._active(True)
            e.acceptProposedAction()
        else:
            e.ignore()

    def dragLeaveEvent(self, e):
        self._active(False)

    def dropEvent(self, e):
        self._active(False)
        if self._has_images(e.mimeData()):
            self.dropped.emit(e.mimeData())
            e.acceptProposedAction()

    @staticmethod
    def _has_images(mime) -> bool:
        return (mime.hasUrls() or mime.hasImage() or mime.hasText()
                or (mime.hasHtml() and "<img" in mime.html()))


class CollectPanel(QWidget):
    recordsSaved = Signal()

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.pool = QThreadPool.globalInstance()
        self.pool.setMaxThreadCount(2)  # 导入并发上限 2（视频首帧提取较吃 CPU）
        # 当前所有 pending 项的导入看门狗（uid -> QTimer）
        self._watchdogs = {}
        self.pending = {}      # uid -> item dict
        self._build()
        self._status("")

    # ================= UI =================
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 18, 22, 18)
        root.setSpacing(12)

        head = QVBoxLayout()
        head.setSpacing(2)
        t = QLabel(tr("收藏作品"))
        t.setObjectName("pageTitle")
        head.addWidget(t)
        s = QLabel(tr("把图片拖进来或粘贴进来，填写提示词与模型后保存；粘贴 Civitai 链接可自动提取数据"))
        s.setObjectName("pageSub")
        head.addWidget(s)
        root.addLayout(head)

        self.drop = DropZone()
        self.drop.dropped.connect(self._on_dropped)
        root.addWidget(self.drop)

        body = QHBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, 1)

        # -------- 左：待保存列表 --------
        left = QVBoxLayout()
        left.setSpacing(8)
        lh = QHBoxLayout()
        self.count_label = QLabel(tr("待保存 0 条"))
        self.count_label.setObjectName("countLabel")
        lh.addWidget(self.count_label)
        lh.addStretch(1)
        paste_btn = QPushButton(tr("粘贴图片"))
        paste_btn.setObjectName("ghost")
        paste_btn.clicked.connect(self.add_from_clipboard)
        lh.addWidget(paste_btn)
        clear_btn = QPushButton(tr("清空"))
        clear_btn.setObjectName("ghost")
        clear_btn.clicked.connect(self._clear_all)
        lh.addWidget(clear_btn)
        left.addLayout(lh)

        self.pending_list = QListWidget()
        self.pending_list.setObjectName("pendingList")
        self.pending_list.setViewMode(QListWidget.IconMode)
        self.pending_list.setResizeMode(QListWidget.Adjust)
        self.pending_list.setMovement(QListWidget.Static)
        self.pending_list.setIconSize(QSize(88, 88))
        self.pending_list.setGridSize(QSize(100, 104))
        self.pending_list.setSpacing(6)
        self.pending_list.setUniformItemSizes(True)
        self.pending_list.setMinimumWidth(220)
        self.pending_list.setMaximumWidth(260)
        self.pending_list.setWordWrap(True)
        self.pending_list.currentItemChanged.connect(self._on_select)
        self.pending_list.setContextMenuPolicy(Qt.CustomContextMenu)
        left.addWidget(self.pending_list, 1)
        body.addLayout(left)

        # -------- 右：Civitai 导入 + 表单 --------
        right = QVBoxLayout()
        right.setSpacing(8)

        link_row = QHBoxLayout()
        link_row.setSpacing(8)
        self.link_edit = QLineEdit()
        self.link_edit.setPlaceholderText(tr("粘贴 Civitai 链接（civitai.com / civitai.red 均可），支持多链接用空格或换行分隔"))
        self.link_edit.returnPressed.connect(self._import_links)
        link_row.addWidget(self.link_edit, 1)
        imp_btn = QPushButton(tr("解析并导入"))
        imp_btn.setObjectName("primary")
        imp_btn.clicked.connect(self._import_links)
        link_row.addWidget(imp_btn)
        right.addLayout(link_row)

        form = QGridLayout()
        form.setHorizontalSpacing(10)
        form.setVerticalSpacing(7)

        def fl(text):
            lb = QLabel(text)
            lb.setObjectName("fieldLabel")
            return lb

        form.addWidget(fl(tr("标题")), 0, 0)
        self.title_edit = QLineEdit()
        self.title_edit.setPlaceholderText(tr("可选，例如：赛博朋克城市夜景"))
        form.addWidget(self.title_edit, 0, 1)

        form.addWidget(fl(tr("标签")), 1, 0)
        self.tags_edit = QLineEdit()
        self.tags_edit.setPlaceholderText(tr("逗号分隔，例如：风景, 夜晚, 霓虹"))
        form.addWidget(self.tags_edit, 1, 1)

        form.addWidget(fl(tr("主模型大类")), 2, 0)
        self.base_combo = QComboBox()
        self.base_combo.addItems(list(BASE_MODEL_GROUPS))
        self.base_combo.setToolTip(tr("图片主模型所属的大类（如 Krea 2 / Flux.1 / Flux.2），导入 Civitai 链接时自动识别"))
        form.addWidget(self.base_combo, 2, 1)

        # col1 顶部放一键复制按钮，编辑框放其下；不再在 col0 塞按钮以免挤压标签宽度
        def edit_with_copy(placeholder, min_h):
            col = QVBoxLayout()
            col.setSpacing(4)
            btn_row = QHBoxLayout()
            btn_row.addStretch(1)
            edit = QPlainTextEdit()
            edit.setPlaceholderText(placeholder)
            edit.setMinimumHeight(min_h)
            col.addWidget(edit)
            copy_btn = QPushButton(tr("一键复制"))
            copy_btn.setObjectName("ghost")
            copy_btn.setCursor(Qt.PointingHandCursor)
            copy_btn.setToolTip(tr("一键复制到剪贴板"))
            btn_row.addWidget(copy_btn)
            col.addLayout(btn_row)
            return col, edit, copy_btn

        form.addWidget(fl(tr("正向提示词")), 3, 0)
        pos_col, self.pos_edit, self.pos_copy_btn = edit_with_copy(
            tr("正向提示词…（导入 Civitai 链接后自动填充）"), 88)
        self.pos_copy_btn.clicked.connect(lambda: self._copy_text(self.pos_edit.toPlainText()))
        form.addLayout(pos_col, 3, 1)

        form.addWidget(fl(tr("负向提示词")), 4, 0)
        neg_col, self.neg_edit, self.neg_copy_btn = edit_with_copy(tr("负向提示词…"), 60)
        self.neg_copy_btn.clicked.connect(lambda: self._copy_text(self.neg_edit.toPlainText()))
        form.addLayout(neg_col, 4, 1)

        param_row = QHBoxLayout()
        param_row.setSpacing(8)
        self.param_edits = {}
        for key, label in (("sampler", tr("采样器")), ("steps", tr("步数")), ("cfg", tr("CFG")), ("seed", tr("种子"))):
            box = QVBoxLayout()
            box.setSpacing(3)
            lb = QLabel(label)
            lb.setObjectName("fieldLabel")
            e = QLineEdit()
            e.setPlaceholderText("—")
            box.addWidget(lb)
            box.addWidget(e)
            param_row.addLayout(box)
            self.param_edits[key] = e
        form.addLayout(param_row, 5, 0, 1, 2)

        self.lora_label = QLabel("")
        self.lora_label.setObjectName("hint")
        self.lora_label.setWordWrap(True)
        form.addWidget(self.lora_label, 6, 0, 1, 2)

        right.addLayout(form)

        # -------- 模型清单编辑器 --------
        ms_head = QHBoxLayout()
        ms_head.setSpacing(8)
        ms_t = QLabel(tr("模型清单（图片使用的所有模型，导入时自动列出）"))
        ms_t.setObjectName("fieldLabel")
        ms_head.addWidget(ms_t)
        ms_head.addStretch(1)
        add_model_btn = QPushButton(tr("+ 添加模型"))
        add_model_btn.setObjectName("ghost")
        add_model_btn.clicked.connect(lambda: self._add_model_row())
        ms_head.addWidget(add_model_btn)
        right.addLayout(ms_head)

        self.models_box = QVBoxLayout()
        self.models_box.setSpacing(4)
        self.model_rows = []          # list of dict(row, name, type, url)
        right.addLayout(self.models_box)

        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.save_btn = QPushButton(tr("保存当前"))
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self.save_current)
        btns.addWidget(self.save_btn)
        self.save_all_btn = QPushButton(tr("全部保存"))
        self.save_all_btn.setObjectName("primary")
        self.save_all_btn.clicked.connect(self.save_all)
        btns.addWidget(self.save_all_btn)
        self.status_label = QLabel("")
        self.status_label.setObjectName("hint")
        btns.addWidget(self.status_label, 1)
        btns.addStretch(1)
        right.addLayout(btns)

        right.addStretch(1)
        body.addLayout(right, 1)

    # ================= 工具 =================
    def _status(self, text: str, ok: bool = True):
        self.status_label.setText(text)
        from app.ui.style import tcolor
        self.status_label.setStyleSheet(
            f"color: {tcolor('status_ok')};" if ok else f"color: {tcolor('status_fail')};")

    def _copy_text(self, text: str):
        if not text:
            self._status(tr("没有可复制的内容"), ok=False)
            return
        from PySide6.QtWidgets import QToolTip
        from PySide6.QtGui import QCursor
        from app.text_clean import safe_copy_to_clipboard
        ok, removed = safe_copy_to_clipboard(text)
        if ok:
            msg = tr("已复制 ✓")
            if removed:
                msg = f"{msg} {tr_format('已清理 {n} 个不可见字符', n=removed)}"
            self._status(msg)
            QToolTip.showText(QCursor.pos(), tr("已复制到剪贴板 ✓"))
        else:
            self._status(tr("没有可复制的内容"), ok=False)

    # ---------- 模型清单编辑器 ----------
    def _add_model_row(self, name: str = "", mtype: str = tr("大模型"), url: str = ""):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)

        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText(tr("模型名称（如 Krea2 Turbo_FP8）"))
        type_combo = QComboBox()
        type_combo.addItems([tr(c) for c in MODEL_TYPE_CHOICES])
        if mtype in MODEL_TYPE_CHOICES:
            type_combo.setCurrentText(mtype)
        else:
            type_combo.setCurrentText(tr("其他"))
        url_edit = QLineEdit(url)
        url_edit.setPlaceholderText(tr("模型链接（Civitai 导入自动填写，可点击打开）"))
        open_btn = QPushButton(tr("打开"))
        open_btn.setObjectName("ghost")
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url_edit.text().strip())))
        del_btn = QPushButton("×")
        del_btn.setObjectName("ghost")
        del_btn.clicked.connect(lambda: self._remove_model_row(row))

        h.addWidget(name_edit, 3)
        h.addWidget(type_combo, 1)
        h.addWidget(url_edit, 3)
        h.addWidget(open_btn)
        h.addWidget(del_btn)
        self.models_box.addWidget(row)
        self.model_rows.append({"row": row, "name": name_edit, "type": type_combo, "url": url_edit})
        return row

    def _remove_model_row(self, row):
        for i, r in enumerate(self.model_rows):
            if r["row"] is row:
                self.models_box.removeWidget(row)
                row.deleteLater()
                del self.model_rows[i]
                break

    def _clear_model_rows(self):
        for r in list(self.model_rows):
            self.models_box.removeWidget(r["row"])
            r["row"].deleteLater()
        self.model_rows = []

    def _read_models(self) -> list:
        models = []
        for r in self.model_rows:
            name = r["name"].text().strip()
            if not name:
                continue
            models.append({
                "name": name,
                "type": rev(r["type"].currentText()),
                "url": r["url"].text().strip(),
            })
        return models

    def _refresh_pending_count(self):
        n = len(self.pending)
        self.count_label.setText(tr_format("待保存 {n} 条", n=n))
        self.save_all_btn.setEnabled(n > 0)

    # ================= 导入入口 =================
    def _on_dropped(self, mime):
        items = self._collect_mime(mime)
        self._enqueue(items)

    def add_from_clipboard(self):
        mime = QApplication.clipboard().mimeData()
        items = self._collect_mime(mime)
        if items:
            self._enqueue(items)
        else:
            self._status(tr("剪贴板里没有可导入的图片或链接"), ok=False)

    def _collect_mime(self, mime) -> list:
        items = []
        if mime.hasUrls():
            for u in mime.urls():
                url = u.toString()
                if url.startswith("file://"):
                    items.append({"kind": "file", "path": u.toLocalFile()})
                elif url.startswith(("http://", "https://")):
                    items.append({"kind": "url", "url": url})
        if not items and mime.hasText():
            t = mime.text().strip()
            if t.startswith(("http://", "https://")):
                items.append({"kind": "url", "url": t})
        if not items and mime.hasHtml():
            for src in re.findall(r'<img[^>]+src=["\']([^"\']+)["\']', mime.html()):
                if src.startswith(("http://", "https://")):
                    items.append({"kind": "url", "url": src})
        if not items and mime.hasImage():
            img = mime.imageData()
            if isinstance(img, QImage):
                items.append({"kind": "image", "qimage": img})
            elif isinstance(img, QPixmap):
                items.append({"kind": "image", "qimage": img.toImage()})
        return items

    def _enqueue(self, items: list):
        if not items:
            return
        for it in items:
            parsed = parse_link(it.get("url") or it.get("path") or "")
            if parsed:
                self._start_civitai_import(parsed)
            elif it["kind"] == "file":
                self._start_local_copy(it["path"])
            elif it["kind"] == "url":
                self._start_web_download(it["url"])
            elif it["kind"] == "image":
                self._start_pasted_image(it["qimage"])

    # ================= 各类导入 =================
    def _make_pending(self, fields: dict, image_file=None, uid=None) -> str:
        uid = uid or uuid.uuid4().hex[:8]
        item = {"uid": uid, "record": fields, "image_file": image_file, "state": "ready"}
        self.pending[uid] = item
        if image_file:
            item["record"]["width"], item["record"]["height"] = image_size(
                str(self.store.images_dir / image_file))
        self._add_pending_item(item)
        return uid

    def _add_pending_item(self, item: dict):
        li = QListWidgetItem()
        li.setData(Qt.UserRole, item["uid"])
        li.setTextAlignment(Qt.AlignHCenter)
        li.setToolTip((item["record"].get("title") or tr("待保存图片"))[:40])
        self.pending_list.addItem(li)
        self._update_item_visual(li, item)
        self._refresh_pending_count()

    def _update_item_visual(self, li, item: dict):
        pm = None
        if item.get("video_file"):
            # 视频项：用首帧缩略图，加 ▶ 标记
            t = item.get("thumb_file")
            if t:
                pm = load_pixmap(str(self.store.thumbs_dir / t), 320)
            if pm and not pm.isNull():
                li.setIcon(rounded_pixmap(str(self.store.thumbs_dir / t), 84))
            else:
                li.setIcon(_placeholder_pixmap(84))
        elif item["image_file"]:
            pm = load_pixmap(str(self.store.images_dir / item["image_file"]), 320)
            if pm and not pm.isNull():
                li.setIcon(rounded_pixmap(str(self.store.images_dir / item["image_file"]), 84))
            else:
                li.setIcon(_placeholder_pixmap(84))
        else:
            li.setIcon(_placeholder_pixmap(84))
        if item["state"] == "importing":
            li.setText(tr("导入中…"))
        elif item["record"].get("title"):
            li.setText(item["record"]["title"][:8])
        elif item.get("video_file"):
            li.setText("▶")
        else:
            li.setText(tr("待保存"))

    def _on_select(self, cur, prev):
        if not cur:
            return
        uid = cur.data(Qt.UserRole)
        item = self.pending.get(uid)
        if item:
            self._apply_form(item)

    def _apply_form(self, item: dict):
        r = item["record"]
        self.title_edit.setText(r.get("title") or "")
        self.tags_edit.setText(", ".join(r.get("tags") or []))
        bm = r.get("base_model") or "其他"
        self.base_combo.setCurrentText(bm if bm in BASE_MODEL_GROUPS else tr("其他"))
        self.pos_edit.setPlainText(r.get("positive") or "")
        self.neg_edit.setPlainText(r.get("negative") or "")
        for key, e in self.param_edits.items():
            e.setText(str(r.get(key) or ""))
        # 模型清单
        self._clear_model_rows()
        models = r.get("models") or []
        if not models and (r.get("model_name") or r.get("loras")):
            if r.get("model_name"):
                models.append({"name": r["model_name"], "type": r.get("model_type") or "大模型", "url": ""})
            for lo in (r.get("loras") or []):
                models.append({"name": lo, "type": "LoRA", "url": ""})
        for m in models:
            self._add_model_row(m.get("name") or "", tr(m.get("type") or "大模型"), m.get("url") or "")
        loras = [m["name"] for m in (models or []) if m.get("type") == "LoRA" and m.get("name")]
        if loras:
            self.lora_label.setText("LoRA：" + "、".join(loras))
        else:
            self.lora_label.setText("")

    def _read_form(self) -> dict:
        tags = [t.strip() for t in self.tags_edit.text().replace("，", ",").split(",") if t.strip()]
        models = self._read_models()
        # 主模型大类：显示值反查回中文 key；"全部/All" 视为未选择（不覆盖已提取值）
        bm = rev(self.base_combo.currentText())
        if bm in ("全部",):
            bm = ""
        return {
            "title": self.title_edit.text().strip(),
            "tags": tags,
            "positive": self.pos_edit.toPlainText().strip(),
            "negative": self.neg_edit.toPlainText().strip(),
            "base_model": bm,
            "models": models,
            "sampler": self.param_edits["sampler"].text().strip(),
            "steps": self.param_edits["steps"].text().strip(),
            "cfg": self.param_edits["cfg"].text().strip(),
            "seed": self.param_edits["seed"].text().strip(),
        }

    # ---------- 各来源任务 ----------
    def _install_watchdog(self, uid: str, seconds: int):
        """启动一个超时看门狗：若 seconds 内任务仍未结束，强制标记为失败。"""
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.setInterval(seconds * 1000)

        def on_timeout():
            self._watchdogs.pop(uid, None)
            item = self.pending.get(uid)
            if item and item.get("state") == "importing":
                item["state"] = "error"
                li = self._li_of(uid)
                if li is not None:
                    self._update_item_visual(li, item)
                self._status(tr_format("导入超时（{seconds}s），请检查网络后重试", seconds=seconds), ok=False)

        timer.timeout.connect(on_timeout)
        timer.start()
        self._watchdogs[uid] = timer

    def _clear_watchdog(self, uid: str):
        t = self._watchdogs.pop(uid, None)
        if t is not None:
            t.stop()
            t.deleteLater()

    def _run_task(self, uid: str, fn, *args, timeout_sec: int = 90, **kwargs):
        """公共后台任务封装：parented signals + 看门狗。"""
        signals = WorkerSignals(self)
        signals.done.connect(lambda res, u=uid: self._on_task_done(u, res))
        signals.failed.connect(lambda err, u=uid: self._on_task_fail(u, err))
        task = Worker(signals, fn, *args, **kwargs)
        self._install_watchdog(uid, timeout_sec)
        self.pool.start(task)

    def _start_pasted_image(self, qimage: QImage):
        uid = uuid.uuid4().hex[:8]
        fields = {"source": "local", "source_url": "", "width": qimage.width(), "height": qimage.height()}
        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        qimage.save(buf, "PNG")
        name = self.store.save_uploaded_bytes(bytes(buf.data()), "png")
        self._make_pending(fields, image_file=name, uid=uid)
        # 剪贴板图片若自带 PNG 生成参数，自动填充表单
        if self._fill_from_image_meta(uid):
            self._apply_form(self.pending[uid])
            self._status(tr("已自动提取图片内嵌提示词 ✓"))
        self._select_uid(uid)
        self._status(tr("已加入待保存"))

    def _start_local_copy(self, path: str):
        # 视频文件走视频导入链路（复制到 videos/ + 首帧缩略图）
        from app.video_meta import is_video_path
        if is_video_path(path):
            self._start_local_video(path)
            return
        from app.workers import copy_local_file
        uid = uuid.uuid4().hex[:8]
        fields = {"source": "local", "source_url": ""}
        self.pending[uid] = {"uid": uid, "record": fields, "image_file": None, "state": "importing"}
        self._add_pending_item(self.pending[uid])
        self._run_task(uid, copy_local_file, self.store, path, timeout_sec=30)

    def _start_local_video(self, path: str):
        """导入本地视频：后台复制 + 首帧缩略图，不阻塞 UI。"""
        from app.workers import import_local_video
        uid = uuid.uuid4().hex[:8]
        fields = {"source": "local", "source_url": "", "media_type": "video"}
        self.pending[uid] = {"uid": uid, "record": fields,
                             "image_file": None, "state": "importing"}
        self._add_pending_item(self.pending[uid])
        self._select_uid(uid)
        self._run_task(uid, import_local_video, self.store, path, timeout_sec=120)

    def _start_web_download(self, url: str):
        from app.workers import download_web_image
        uid = uuid.uuid4().hex[:8]
        fields = {"source": "local", "source_url": url}
        self.pending[uid] = {"uid": uid, "record": fields, "image_file": None, "state": "importing"}
        self._add_pending_item(self.pending[uid])
        self._run_task(uid, download_web_image, self.store, url, timeout_sec=90)

    def _start_civitai_import(self, parsed: dict):
        from app.workers import import_civitai
        url = f"https://civitai.com/{'images' if parsed['kind']=='image' else ('models' if parsed['kind']=='model' else 'api/v1/model-versions')}/{parsed['id']}"
        for uid, item in self.pending.items():
            if item["record"].get("source_url") and parsed["id"] == _id_of(item["record"]["source_url"]):
                self._select_uid(uid)
                self._status(tr("该链接已在待保存列表中"))
                return
        uid = uuid.uuid4().hex[:8]
        fields = {"source": "civitai", "source_url": url}
        self.pending[uid] = {"uid": uid, "record": fields, "image_file": None, "state": "importing"}
        self._add_pending_item(self.pending[uid])
        self._select_uid(uid)
        # 给 Civitai 任务单独用更长的看门狗（含重试与图片下载，最坏情况 ~120s）
        signals = WorkerSignals(self)
        signals.done.connect(lambda res, u=uid: self._on_civitai_done(u, res))
        signals.failed.connect(lambda err, u=uid: self._on_task_fail(u, err))
        task = Worker(signals, import_civitai, self.store, url)
        self._install_watchdog(uid, 120)
        self.pool.start(task)

    def _import_links(self):
        text = self.link_edit.text().strip()
        if not text:
            self._status(tr("请先粘贴 Civitai 链接"), ok=False)
            return
        found = 0
        for m in re.finditer(r"https?://civitai\.(?:com|red)/[^\s,，;；]+", text, re.I):
            # 剥离 URL 尾部被误吞的中文标点（如 。，、）等），避免污染 parse_link 结果
            p = parse_link(_strip_url_trailing(m.group(0)))
            if p:
                self._start_civitai_import(p)
                found += 1
        if found == 0:
            self._status(tr("未在输入中找到有效的 Civitai 链接"), ok=False)
        else:
            self._status(tr_format("正在导入 {found} 个链接…", found=found))

    # ---------- 任务回调 ----------
    def _fill_from_image_meta(self, uid: str) -> bool:
        """从待保存项的图片文件提取内嵌生成参数（A1111/NovelAI/ComfyUI）。

        合并到 record，并同步到表单控件（当前选中项），保证保存时不会因空表单
        覆盖提取到的数据（与 Civitai 导入路径行为一致）。
        返回 True 表示提取到数据。
        """
        item = self.pending.get(uid)
        if not item or not item.get("image_file"):
            return False
        try:
            from app.image_meta import extract_image_meta
            meta = extract_image_meta(str(self.store.images_dir / item["image_file"]))
        except Exception:
            return False
        if not meta.get("positive"):
            return False
        fields = {k: v for k, v in meta.items() if v}
        mn = fields.pop("model_name", "")
        if mn and not item["record"].get("models"):
            # 模型类型用固定中文 key 存储（不随语言翻译，否则后续比较全部失效）
            fields["models"] = [{"name": mn, "type": "大模型", "url": "", "base_model": ""}]
        item["record"].update(fields)
        # 同步表单（仅当前选中项），保存时表单与 record 一致
        if self._li_of(uid) == self.pending_list.currentItem():
            self._apply_form(item)
        return True

    def _on_task_done(self, uid, res, is_import=False):
        self._clear_watchdog(uid)
        item = self.pending.get(uid)
        if not item:
            return
        item["state"] = "ready"
        auto_filled = False
        if res.get("image_file"):
            item["image_file"] = res["image_file"]
            item["record"]["width"], item["record"]["height"] = image_size(
                str(self.store.images_dir / res["image_file"]))
            # 本地图片自带生成参数时自动填充（不提前 return，保证 visual 一定更新）
            if not item["record"].get("source_url") or not is_import:
                auto_filled = self._fill_from_image_meta(uid)
        if res.get("video_file"):
            # 视频导入结果：media_type=video + 首帧缩略图 + 时长 + 分辨率
            item["video_file"] = res["video_file"]
            item["record"]["media_type"] = "video"
            item["thumb_file"] = res.get("thumb_file") or ""
            if res.get("duration"):
                item["record"]["duration"] = res["duration"]
            if res.get("width"):
                item["record"]["width"] = res["width"]
            if res.get("height"):
                item["record"]["height"] = res["height"]
        self._update_item_visual(self._li_of(uid), item)
        if self._li_of(uid) == self.pending_list.currentItem():
            self._apply_form(item)
        self._status(tr("已自动提取图片内嵌提示词 ✓") if auto_filled else tr("已加入待保存"))

    def _on_civitai_done(self, uid, res):
        self._clear_watchdog(uid)
        item = self.pending.get(uid)
        if not item:
            return
        item["state"] = "ready"
        fields = res.get("fields") or {}
        if fields:
            item["record"].update({k: v for k, v in fields.items() if k not in ("width", "height")})
            if res.get("image_file"):
                item["record"]["width"], item["record"]["height"] = image_size(
                    str(self.store.images_dir / res["image_file"]))
        if res.get("image_file"):
            item["image_file"] = res["image_file"]
        if res.get("video_file"):
            # Civitai 视频：media_type=video + 首帧缩略图 + 时长 + 分辨率
            item["video_file"] = res["video_file"]
            item["record"]["media_type"] = "video"
            if res.get("thumb_file"):
                item["thumb_file"] = res["thumb_file"]
            if res.get("duration"):
                item["record"]["duration"] = res["duration"]
            if fields.get("width"):
                item["record"]["width"] = fields["width"]
            if fields.get("height"):
                item["record"]["height"] = fields["height"]
        err = res.get("error") or ""
        if err:
            self._status(err, ok=False)
        else:
            self._status(tr("已导入 Civitai 数据"))
        self._update_item_visual(self._li_of(uid), item)
        if self._li_of(uid) == self.pending_list.currentItem():
            self._apply_form(item)

    def _on_task_fail(self, uid, err):
        self._clear_watchdog(uid)
        item = self.pending.get(uid)
        if item:
            item["state"] = "error"
            li = self._li_of(uid)
            if li is not None:
                self._update_item_visual(li, item)
        self._status(tr("导入失败：") + err, ok=False)

    # ---------- 保存 ----------
    def _build_record(self, item: dict, merge_form: bool = True) -> dict:
        """把待保存项构造成完整记录。

        merge_form=True：把右侧表单最新内容合并进 record（**空值不覆盖**已提取的数据，
        用户手动填写的值优先），用于「保存当前」或「全部保存」中的当前选中项
        （用户正在表单里编辑该项，编辑必须生效）。
        merge_form=False：直接用 item["record"] 已有数据（多链接导入时其余项保留
        各自独立提取的提示词/模型，避免被共享表单污染）。
        注意：合并在 record 的副本上进行，不修改 item["record"]（保存中断也不污染待保存项）。
        """
        r = dict(item["record"])
        if merge_form:
            form = self._read_form()
            r.update({k: v for k, v in form.items() if v})
        models = r.get("models") or []
        loras = merge_loras(
            [m["name"] for m in models if m.get("type") == "LoRA" and m.get("name")],
            r.get("positive") or "")
        rec = {
            "title": r.get("title") or "",
            "tags": r.get("tags") or [],
            "positive": r.get("positive") or "",
            "negative": r.get("negative") or "",
            "base_model": r.get("base_model") or "其他",
            "base_model_raw": r.get("base_model_raw") or "",
            "models": models,
            "loras": loras,
            "sampler": r.get("sampler") or "",
            "steps": r.get("steps") or "",
            "cfg": r.get("cfg") or "",
            "seed": r.get("seed") or "",
            "width": r.get("width") or 0,
            "height": r.get("height") or 0,
            "source": r.get("source") or "local",
            "source_url": r.get("source_url") or "",
            "image_file": item.get("image_file") or "",
            "thumb_file": "",
            "media_type": r.get("media_type") or "image",
            "video_file": item.get("video_file") or "",
        }
        if rec["media_type"] == "video" and rec["video_file"]:
            # 视频：缩略图来自首帧提取（导入时生成），无则占位
            rec["thumb_file"] = item.get("thumb_file") or ""
            rec["duration"] = r.get("duration") or 0
        elif rec["image_file"]:
            src = str(self.store.images_dir / rec["image_file"])
            tname = rec["image_file"].rsplit(".", 1)[0] + ".png"
            if make_thumbnail(src, str(self.store.thumbs_dir / tname), 400):
                rec["thumb_file"] = tname
        if not rec["title"]:
            rec["title"] = rec["video_file"] or rec["image_file"] or "未命名"
        return rec

    def save_current(self):
        li = self.pending_list.currentItem()
        if not li:
            self._status(tr("待保存列表为空，先拖入图片或导入链接"), ok=False)
            return
        uid = li.data(Qt.UserRole)
        item = self.pending.get(uid)
        if not item:
            return
        if item.get("state") == "importing":
            # Civitai/本地文件还在后台提取/下载，record 尚未填充完整，禁止保存
            self._status(tr("请等待导入完成"), ok=False)
            return
        if not item["image_file"] and not item.get("video_file"):
            self._status(tr("这条还没有图片，无法保存"), ok=False)
            return
        rec = self._build_record(item)
        self.store.add(rec)
        self._remove_pending(uid)
        self._status(tr("已保存 ✓"))
        self.recordsSaved.emit()

    def save_all(self):
        if not self.pending:
            self._status(tr("待保存列表为空"), ok=False)
            return
        # 仅当前选中项合并表单（用户正在编辑它）；其余项保留各自导入数据，
        # 避免多链接导入时所有项被“当前选中项的表单”污染成同一份提示词
        cur_li = self.pending_list.currentItem()
        cur_uid = cur_li.data(Qt.UserRole) if cur_li is not None else None
        n = 0
        skipped_importing = 0
        skipped_no_image = 0
        for uid in list(self.pending.keys()):
            item = self.pending[uid]
            if item.get("state") == "importing":
                skipped_importing += 1
                continue
            if not item["image_file"] and not item.get("video_file"):
                skipped_no_image += 1
                continue
            rec = self._build_record(item, merge_form=(uid == cur_uid))
            self.store.add(rec)
            self._remove_pending(uid)
            n += 1
        msgs = []
        if n:
            msgs.append(tr_format("已保存 {n} 条 ✓", n=n))
        if skipped_importing:
            msgs.append(tr_format("有 {n} 条仍在导入中，已跳过", n=skipped_importing))
        if skipped_no_image:
            msgs.append(tr_format("有 {n} 条无图片，已跳过", n=skipped_no_image))
        if n:
            self._status("；".join(msgs))
            self.recordsSaved.emit()
        elif msgs:
            self._status("；".join(msgs), ok=False)
        else:
            self._status(tr("没有可保存的完整项（缺图片）"), ok=False)

    def _clear_all(self):
        if not self.pending:
            return
        from PySide6.QtWidgets import QMessageBox
        ret = QMessageBox.question(self, tr("AI-Prompt-Vault"),
                                   tr_format("清空 {len(self.pending)} 条待保存内容？（已保存到资料库的记录不受影响）"),
                                   QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret != QMessageBox.Yes:
            return
        for uid in list(self.pending.keys()):
            self._remove_pending(uid, to_trash=True)
        self._status(tr("已清空"))

    def _remove_pending(self, uid, to_trash=False):
        item = self.pending.pop(uid, None)
        if item and to_trash and item.get("image_file"):
            try:
                import shutil
                f = self.store.images_dir / item["image_file"]
                if f.exists():
                    shutil.move(str(f), str(self.store.trash_dir / f.name))
            except Exception:
                pass
        for i in range(self.pending_list.count()):
            li = self.pending_list.item(i)
            if li.data(Qt.UserRole) == uid:
                self.pending_list.takeItem(i)
                li = None
                break
        self._refresh_pending_count()

    def _li_of(self, uid):
        for i in range(self.pending_list.count()):
            li = self.pending_list.item(i)
            if li.data(Qt.UserRole) == uid:
                return li
        return None

    def _select_uid(self, uid):
        li = self._li_of(uid)
        if li:
            self.pending_list.setCurrentItem(li)


def _id_of(source_url: str):
    m = re.search(r"/(?:images?|models?|model-versions?)/(\d+)", source_url)
    return int(m.group(1)) if m else None


# URL 尾部可保留的合法字符（Civitai 页面/图片链接的路径与查询字符集）
_URL_TRAIL_OK = r"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_\-./?&=:#%+~"


def _strip_url_trailing(url: str) -> str:
    """剥离 URL 尾部被误吞的中文标点（如 。，、！？）等）。

    多链接粘贴时中文标点常紧跟在链接后，原正则 [^\\s,，;；]+ 会把它们吞进匹配，
    导致 URL 尾部带标点；此函数统一剔除尾部非 URL 合法字符。
    """
    return re.sub(rf"[^{_URL_TRAIL_OK}]+$", "", url or "")