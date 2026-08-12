from app.i18n import t as tr, tr_format
"""图库右侧详情侧栏：显示当前选中图片的完整详情，可读、可复制、可跳转。"""
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtGui import QPixmap, QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
                               QPushButton, QSizePolicy, QTextEdit, QScrollArea)

from app.filters import ratio_text
from app.thumbs import load_pixmap
from app.text_clean import safe_copy_to_clipboard


def elide_middle(text: str, width: int, fm) -> str:
    """长文本中间截断显示（如 M8FZGN3...N0?sig=...），保留开头结尾。"""
    if not text or fm.horizontalAdvance(text) <= width:
        return text
    return fm.elidedText(text, Qt.ElideMiddle, max(width, 40))


def _copy(text: str) -> tuple[bool, int]:
    """复制文本到剪贴板（自动清理无效控制字符）。

    Returns:
        (ok, removed_count)：ok=是否写入成功；removed_count=清理掉的
        无效控制字符数（>0 时用于提示用户）。
    """
    if not text:
        return False, 0
    return safe_copy_to_clipboard(text)


class DetailSidebar(QWidget):
    """图库右侧详情面板。"""

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self._record = None
        self.scroll = None
        self.img_label = None
        self.setMinimumWidth(280)
        self.setMaximumWidth(440)
        self._build()

    def _apply_theme_style(self):
        """按当前主题刷新硬编码颜色（主题切换时调用）。"""
        from app.ui.style import tcolor
        bg = tcolor("panel_bg")
        self.setStyleSheet(
            f"QWidget#detailSidebar {{ background-color: {bg}; color: #ececf6; }}"
            f" QWidget#detailSidebar QScrollArea {{ background: {bg}; border: none; }}"
            f" QWidget#detailSidebar QScrollArea > QWidget > QWidget {{ background: {bg}; }}"
        )
        if self.scroll:
            self.scroll.setStyleSheet(f"QScrollArea {{ background: {bg}; border: none; }}")
        if self.img_label:
            self.img_label.setStyleSheet(
                f"background:{tcolor('img_bg')}; border:1px solid {tcolor('img_border')};"
                f" border-radius:10px; color:{tcolor('img_placeholder')};")

    def _build(self):
        # 深色背景（仅作用于本组件容器，避免 QWidget 通配覆盖按钮/输入框的全局样式，
        # 否则按钮会失去 hover/pressed 反馈）
        self.setObjectName("detailSidebar")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("detailScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        self.scroll = scroll
        outer.addWidget(scroll)

        inner = QWidget()
        self.lay = QVBoxLayout(inner)
        self.lay.setContentsMargins(10, 10, 10, 10)
        self.lay.setSpacing(6)
        scroll.setWidget(inner)

        # 大图预览：高度自适应（宽 360，高 140~420），水平 Ignored 保证图片缩放不撑破布局
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setMinimumHeight(140)
        self.img_label.setMaximumHeight(420)
        self.img_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.img_label.setText(tr("选择图片查看详情"))
        self.lay.addWidget(self.img_label)
        self._apply_theme_style()

        self.title_label = QLabel(tr("(未选中)"))
        self.title_label.setObjectName("popupTitle")
        self.title_label.setWordWrap(True)
        self.title_label.setMinimumWidth(0)
        self.title_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.lay.addWidget(self.title_label)

        self.chip_row = QHBoxLayout()
        self.chip_row.setSpacing(4)
        self.lay.addLayout(self.chip_row)

        # 模型清单
        self.models_section = QLabel(tr("模型清单"))
        self.models_section.setObjectName("popupSection")
        self.lay.addWidget(self.models_section)
        self.models_box = QVBoxLayout()
        self.models_box.setSpacing(4)
        self.lay.addLayout(self.models_box)

        # 提示词：限高更紧凑（默认折叠为点击展开）
        self.pos_label = QLabel(tr("正向提示词"))
        self.pos_label.setObjectName("popupSection")
        self.lay.addWidget(self.pos_label)
        self.pos_text = QTextEdit()
        self.pos_text.setReadOnly(True)
        self.pos_text.setMinimumHeight(60)
        self.pos_text.setMaximumHeight(120)
        self.lay.addWidget(self.pos_text)

        self.neg_label = QLabel(tr("负向提示词"))
        self.neg_label.setObjectName("popupSection")
        self.lay.addWidget(self.neg_label)
        self.neg_text = QTextEdit()
        self.neg_text.setReadOnly(True)
        self.neg_text.setMinimumHeight(40)
        self.neg_text.setMaximumHeight(80)
        self.lay.addWidget(self.neg_text)

        # 参数
        self.params_label = QLabel(tr("采样参数"))
        self.params_label.setObjectName("popupSection")
        self.lay.addWidget(self.params_label)
        self.params_layout = QVBoxLayout()
        self.params_layout.setSpacing(3)
        self.lay.addLayout(self.params_layout)
        self._param_labels = {}

        # 分组
        self.group_label = QLabel(tr("分组"))
        self.group_label.setObjectName("popupSection")
        self.lay.addWidget(self.group_label)
        self.group_chip = QLabel(tr("未分组"))
        self.group_chip.setObjectName("chip")
        self.lay.addWidget(self.group_chip)

        # 复制按钮组
        btns = QHBoxLayout()
        btns.setSpacing(6)
        b_all = QPushButton(tr("复制全部"))
        b_all.setObjectName("primary")
        b_all.clicked.connect(lambda: self._copy_record("all"))
        btns.addWidget(b_all)
        b_pos = QPushButton(tr("复制正向"))
        b_pos.setObjectName("ghost")
        b_pos.clicked.connect(lambda: self._copy_record("positive"))
        btns.addWidget(b_pos)
        b_neg = QPushButton(tr("复制负向"))
        b_neg.setObjectName("ghost")
        b_neg.clicked.connect(lambda: self._copy_record("negative"))
        btns.addWidget(b_neg)
        self.lay.addLayout(btns)

        # 复制反馈（成功/失败提示，2 秒后自动隐藏）
        self.copy_status = QLabel("")
        self.copy_status.setObjectName("hint")
        self.copy_status.setAlignment(Qt.AlignCenter)
        self.copy_status.setVisible(False)
        self.lay.addWidget(self.copy_status)

        # 来源链接
        self.src_label = QLabel("")
        self.src_label.setObjectName("hint")
        self.src_label.setWordWrap(True)
        self.src_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.src_label.setVisible(False)
        self.lay.addWidget(self.src_label)
        self.src_btn = QPushButton(tr("在浏览器打开来源链接"))
        self.src_btn.setObjectName("ghost")
        self.src_btn.setVisible(False)
        self.src_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self._record.get("source_url", ""))) if self._record else None)
        self.lay.addWidget(self.src_btn)

        self.lay.addStretch(1)

    # ---------- 公共 ----------
    def set_record(self, rec):
        """显示记录详情。无 rec 时清空并显示占位。"""
        # 清旧
        while self.chip_row.count():
            item = self.chip_row.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        while self.models_box.count():
            item = self.models_box.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        for k, lab in list(self._param_labels.items()):
            lab.deleteLater()
        self._param_labels.clear()

        if not rec:
            self._record = None
            self._set_img(None, placeholder=tr("选择图片查看详情"))
            self.title_label.setText(tr("(未选中)"))
            return

        self._record = rec
        self._set_img(rec)

        title = rec.get("title") or tr("(无标题)")
        # 超长文件名中间截断显示，悬停显示完整
        self.title_label.setText(elide_middle(title, self.title_label.width() or 300,
                                              self.title_label.fontMetrics()))
        self.title_label.setToolTip(title)

        # 大类 / 原始大类 chip
        bm = rec.get("base_model") or "其他"
        self._add_chip(bm, accent=True)
        bm_raw = rec.get("base_model_raw") or ""
        if bm_raw and bm_raw != bm:
            self._add_chip(bm_raw[:24])
        w, h = rec.get("width") or 0, rec.get("height") or 0
        self._add_chip(f"{tr(ratio_text(w, h))} {w}×{h}" if w else tr("未知尺寸"))
        grp = rec.get("group") or ""
        if grp:
            self._add_chip(f"📁 {grp}")

        # 模型清单
        models = rec.get("models") or []
        if not models and rec.get("model_name"):
            models = [{"name": rec["model_name"], "type": tr(rec.get("model_type") or "大模型")}]
        if not models:
            self.models_section.setVisible(False)
        else:
            self.models_section.setVisible(True)
            for m in models:
                self._add_model_row(m)

        # 提示词
        self.pos_text.setPlainText(rec.get("positive") or "")
        self.neg_text.setPlainText(rec.get("negative") or "")

        # 参数
        for key, label in (("sampler", tr("采样器")), ("steps", tr("步数")), ("cfg", tr("CFG")), ("seed", tr("种子"))):
            v = str(rec.get(key) or "").strip()
            if v:
                row = QLabel(f"{label}: {v}")
                row.setObjectName("popupText")
                self.params_layout.addWidget(row)
                self._param_labels[key] = row

        # 分组
        self.group_chip.setText(grp or tr("未分组"))

        # 来源
        src = rec.get("source_url") or ""
        if src:
            self.src_label.setText(tr_format("来源：{src}", src=src))
            self.src_label.setVisible(True)
            self.src_btn.setVisible(True)
            try:
                self.src_btn.clicked.disconnect()
            except RuntimeError:
                pass
            self.src_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(src)))
        else:
            self.src_label.setVisible(False)
            self.src_btn.setVisible(False)

    # ---------- 悬停预览 ----------
    def set_preview(self, rec):
        """仅更新大图预览（列表模式悬停表格行时调用），不改动任何详情文本/控件。

        与 set_record 区分：set_record 更新全部详情；set_preview 只切换 img_label，
        已有选中记录（self._record）保持不变，clear_preview 时恢复其大图。
        """
        self._set_img(rec)

    def clear_preview(self):
        """清除预览态：恢复显示当前选中记录的大图；无选中记录时恢复占位。"""
        if self._record is not None:
            self._set_img(self._record)
        else:
            self._set_img(None, placeholder=tr("选择图片查看详情"))

    def _set_img(self, rec, placeholder=None):
        """加载并显示 rec 的大图预览（等比缩放：宽上限 360、高上限 1000，靠控件最大高度约束）。

        取图顺序：thumb_file → image_file → virtual_path/thumb_path_for_rec 兜底。
        加载失败或 rec 为 None 时显示 placeholder（默认 tr("暂无图片")）。
        """
        if placeholder is None:
            placeholder = tr("暂无图片")
        pm = None
        if rec:
            if rec.get("thumb_file"):
                pm = load_pixmap(str(self.store.thumbs_dir / rec["thumb_file"]), 360)
            if (pm is None or pm.isNull()) and rec.get("image_file"):
                pm = load_pixmap(str(self.store.images_dir / rec["image_file"]), 360)
            if (pm is None or pm.isNull()) and rec.get("virtual_path"):
                tp = None
                try:
                    from app.comfy_output import thumb_path_for_rec
                    tp = thumb_path_for_rec(self.store, rec)
                except Exception:
                    tp = None
                if tp and tp.exists() and tp.stat().st_size >= 100:
                    pm = load_pixmap(str(tp), 360)
                if pm is None or pm.isNull():
                    pm = load_pixmap(str(rec["virtual_path"]), 360)
        if pm and not pm.isNull():
            scaled = pm.scaled(360, 1000, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.img_label.setPixmap(scaled)
            self.img_label.setText("")
        else:
            self.img_label.setPixmap(QPixmap())
            self.img_label.setText(placeholder)

    # ---------- 内部 ----------
    def _add_chip(self, text, accent=False):
        lb = QLabel(text)
        lb.setObjectName("chipAccent" if accent else "chip")
        self.chip_row.addWidget(lb)

    def _add_model_row(self, m):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        name_text = m.get("name") or ""
        name = QLabel(name_text)
        name.setObjectName("popupText")
        name.setWordWrap(True)
        # 超长文件名不允许撑破布局：水平方向尺寸交给布局分配 + 中间截断显示
        name.setMinimumWidth(0)
        name.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        name.setText(elide_middle(name_text, 260, name.fontMetrics()))
        name.setToolTip(name_text)
        h.addWidget(name, 1)
        type_lb = QLabel(tr(m.get("type") or "其他"))
        type_lb.setObjectName("chip")
        type_lb.setMinimumWidth(0)
        h.addWidget(type_lb)
        url = m.get("url") or ""
        if url and ("civitai.com" in url or url.startswith("http")):
            dl_btn = QPushButton(tr("下载"))
            dl_btn.setObjectName("ghost")
            dl_btn.setCursor(Qt.PointingHandCursor)
            dl_btn.setToolTip(tr("下载到 ComfyUI 对应模型文件夹"))
            dl_btn.clicked.connect(lambda checked=False, mm=m: self._download_model(mm))
            h.addWidget(dl_btn)
            open_btn = QPushButton(tr("打开"))
            open_btn.setObjectName("ghost")
            open_btn.setCursor(Qt.PointingHandCursor)
            u = url
            open_btn.clicked.connect(lambda checked=False, uu=u: QDesktopServices.openUrl(QUrl(uu)))
            h.addWidget(open_btn)
        self.models_box.addWidget(row)

    def _download_model(self, m):
        from PySide6.QtGui import QCursor
        from app.ui.download_manager import DownloadManager
        win = self.window()
        mgr: DownloadManager = getattr(win, "download_manager", None)
        if mgr is None:
            return
        mgr.start(m, parent_widget=self, src_pos=QCursor.pos())

    def _copy_record(self, which):
        rec = self._record
        if not rec:
            self._flash(tr("请先选中一张图片"))
            return
        pos = rec.get("positive") or ""
        if which == "positive":
            self._flash(self._copy_feedback(_copy(pos), bool(pos)))
            return
        if which == "negative":
            neg = rec.get("negative") or ""
            self._flash(self._copy_feedback(_copy(neg), bool(neg)))
            return
        parts = [pos]
        neg = rec.get("negative") or ""
        if neg:
            parts.append(f"Negative prompt: {neg}")
        meta = []
        if rec.get("steps"):
            meta.append(f"Steps: {rec['steps']}")
        if rec.get("sampler"):
            meta.append(f"Sampler: {rec['sampler']}")
        if rec.get("cfg"):
            meta.append(f"CFG scale: {rec['cfg']}")
        if rec.get("seed"):
            meta.append(f"Seed: {rec['seed']}")
        ms = rec.get("models") or []
        main = next((mm for mm in ms if mm.get("type") == "大模型"), None)
        if main:
            meta.append(f"Model: {main['name']}")
        if rec.get("base_model") and rec["base_model"] != tr("其他"):
            meta.append(f"Base model: {rec.get('base_model_raw') or rec['base_model']}")
        if meta:
            parts.append(" ".join(meta))
        text = "\n".join(parts).strip()
        self._flash(self._copy_feedback(_copy(text), bool(text)))

    def _copy_feedback(self, result: tuple[bool, int], has_content: bool) -> str:
        """根据复制结果构造用户反馈文案。

        - 成功：显示「已复制 ✓」，若清理过控制字符则追加「已清理 N 个不可见字符」。
        - 失败：无可见内容提示「没有内容可复制」；有内容但写入失败时提示
          「复制失败：{err}」（底层 safe_copy_to_clipboard 已捕获剪贴板异常，
          无法透传具体 err，此处给出通用失败信息，正常流程不会走到）。
        """
        ok, removed = result
        if ok:
            msg = tr("已复制 ✓")
            if removed:
                msg = f"{msg} {tr_format('已清理 {n} 个不可见字符', n=removed)}"
            return msg
        if not has_content:
            return tr("没有内容可复制")
        return tr_format("复制失败：{err}", err="write failed")

    def _flash(self, msg: str):
        """在状态条显示反馈，2 秒后自动隐藏。"""
        self.copy_status.setText(msg)
        self.copy_status.setVisible(True)
        QTimer.singleShot(2000, lambda: self.copy_status.setVisible(False))