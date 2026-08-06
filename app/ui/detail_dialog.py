from app.i18n import t as tr, tr_format, rev
"""详情/编辑对话框：查看大图与完整信息，复制提示词，编辑或删除记录。"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
                               QPlainTextEdit, QPushButton, QScrollArea, QWidget,
                               QComboBox, QApplication, QFrame, QMessageBox)

from app.config import APP_NAME
from app.thumbs import load_pixmap
from app.filters import ratio_text
from app.civitai import BASE_MODEL_GROUPS

MODEL_TYPE_CHOICES = [tr("大模型"), "LoRA", tr("嵌入"), tr("VAE"), tr("超网络"), tr("ControlNet"),
                      tr("放大模型"), tr("工作流"), tr("运动模块"), tr("文本编码器"), tr("其他")]


def copy_text(text: str) -> bool:
    if not text:
        return False
    QApplication.clipboard().setText(text)
    return True


class DetailDialog(QDialog):
    def __init__(self, record: dict, image_path: str, parent=None):
        super().__init__(parent)
        self.record = dict(record)
        self.image_path = image_path
        self.setWindowTitle(tr("作品详情"))
        self.setModal(True)
        self.resize(880, 620)
        self.setMinimumSize(760, 520)
        self._build()

    # ---------- UI ----------
    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(10)
        # 显式深色背景：QScrollArea 与内嵌 QWidget 默认浅色，需强制覆盖
        self.setStyleSheet(
            "QDialog { background-color: #16161f; color: #f2f2f8; }"
            " QScrollArea { background: #16161f; border: none; }"
            " QScrollArea > QWidget > QWidget { background: #16161f; }"
        )

        body = QHBoxLayout()
        body.setSpacing(14)
        root.addLayout(body, 1)

        # 左：大图
        left = QVBoxLayout()
        left.setSpacing(8)
        self.img_label = QLabel()
        self.img_label.setAlignment(Qt.AlignCenter)
        self.img_label.setMinimumSize(380, 380)
        self.img_label.setStyleSheet(
            "background:#16161f; border:1px solid #26263a; border-radius:14px;")
        self.img_label.setScaledContents(False)
        left.addWidget(self.img_label, 1)
        self.open_btn = QPushButton(tr("打开原图"))
        self.open_btn.setObjectName("ghost")
        self.open_btn.clicked.connect(self._open_image)
        left.addWidget(self.open_btn, 0, Qt.AlignHCenter)
        body.addLayout(left, 3)

        # 右：信息
        right = QScrollArea()
        right.setWidgetResizable(True)
        right.setFrameShape(QFrame.NoFrame)
        right.setStyleSheet("QScrollArea { background: transparent; }")
        inner = QWidget()
        form = QVBoxLayout(inner)
        form.setContentsMargins(2, 0, 6, 0)
        form.setSpacing(8)

        def field_label(t):
            lb = QLabel(t)
            lb.setObjectName("fieldLabel")
            return lb

        form.addWidget(field_label(tr("标题")))
        self.title_edit = QLineEdit(self.record.get("title") or "")
        form.addWidget(self.title_edit)

        form.addWidget(field_label(tr("标签（逗号分隔）")))
        self.tags_edit = QLineEdit(", ".join(self.record.get("tags") or []))
        form.addWidget(self.tags_edit)

        row = QHBoxLayout()
        row.setSpacing(8)
        col_m = QVBoxLayout()
        col_m.setSpacing(4)
        col_m.addWidget(field_label(tr("主模型大类")))
        self.base_combo = QComboBox()
        self.base_combo.addItems(list(BASE_MODEL_GROUPS))
        bm = self.record.get("base_model") or "其他"
        self.base_combo.setCurrentText(bm if bm in BASE_MODEL_GROUPS else tr("其他"))
        col_m.addWidget(self.base_combo)
        col_t = QVBoxLayout()
        col_t.setSpacing(4)
        col_t.addWidget(field_label(tr("原始 baseModel")))
        self.bm_raw_edit = QLineEdit(self.record.get("base_model_raw") or "")
        self.bm_raw_edit.setPlaceholderText(tr("如 Krea 2 / Flux.1 Krea（Civitai 原始值）"))
        col_t.addWidget(self.bm_raw_edit)
        col_g = QVBoxLayout()
        col_g.setSpacing(4)
        col_g.addWidget(field_label(tr("分组")))
        self.group_combo = QComboBox()
        self.group_combo.addItem(tr("未分组"), "")
        store = getattr(self.parent(), "store", None) if self.parent() else None
        if store is not None:
            for g in store.groups:
                self.group_combo.addItem(g, g)
        cur_g = self.record.get("group") or ""
        idx = self.group_combo.findData(cur_g)
        if idx >= 0:
            self.group_combo.setCurrentIndex(idx)
        col_g.addWidget(self.group_combo)
        row.addLayout(col_m, 3)
        row.addLayout(col_t, 3)
        row.addLayout(col_g, 2)
        form.addLayout(row)

        form.addWidget(field_label(tr("正向提示词")))
        self.pos_edit = QPlainTextEdit(self.record.get("positive") or "")
        self.pos_edit.setMinimumHeight(96)
        form.addWidget(self.pos_edit)

        form.addWidget(field_label(tr("负向提示词")))
        self.neg_edit = QPlainTextEdit(self.record.get("negative") or "")
        self.neg_edit.setMinimumHeight(64)
        form.addWidget(self.neg_edit)

        pr = QHBoxLayout()
        pr.setSpacing(8)
        for key, label in (("sampler", tr("采样器")), ("steps", tr("步数")), ("cfg", tr("CFG")), ("seed", tr("种子"))):
            box = QVBoxLayout()
            box.setSpacing(4)
            box.addWidget(field_label(label))
            e = QLineEdit(str(self.record.get(key) or ""))
            setattr(self, f"{key}_edit", e)
            box.addWidget(e)
            pr.addLayout(box)
        form.addLayout(pr)

        # 模型清单（可编辑 + 超链接）
        mh = QHBoxLayout()
        mh.setSpacing(8)
        mt = QLabel(tr("模型清单（所有使用的模型，可编辑，链接可点击打开）"))
        mt.setObjectName("fieldLabel")
        mh.addWidget(mt)
        mh.addStretch(1)
        add_btn = QPushButton(tr("+ 添加模型"))
        add_btn.setObjectName("ghost")
        add_btn.clicked.connect(lambda: self._add_model_row())
        mh.addWidget(add_btn)
        form.addLayout(mh)
        self.models_box = QVBoxLayout()
        self.models_box.setSpacing(4)
        self.model_rows = []
        form.addLayout(self.models_box)
        models = self.record.get("models") or []
        if not models and self.record.get("model_name"):
            models = [{"name": self.record.get("model_name"), "type": tr(self.record.get("model_type") or "大模型"), "url": ""}]
        for m in models:
            self._add_model_row(m.get("name") or "", tr(m.get("type") or "大模型"), m.get("url") or "")

        src = self.record.get("source_url") or ""
        if src:
            src_lb = QLabel(tr_format("来源链接：{src}", src=src))
            src_lb.setObjectName("hint")
            src_lb.setWordWrap(True)
            src_lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
            form.addWidget(src_lb)
            go = QPushButton(tr("在浏览器中打开 Civitai 页面"))
            go.setObjectName("ghost")
            go.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(src)))
            form.addWidget(go)

        right.setWidget(inner)
        body.addWidget(right, 4)

        # 底部按钮
        btns = QHBoxLayout()
        btns.setSpacing(8)
        self.copy_all = QPushButton(tr("复制全部提示词"))
        self.copy_all.setObjectName("primary")
        self.copy_all.clicked.connect(lambda: self._copy_all(True))
        btns.addWidget(self.copy_all)
        self.copy_pos = QPushButton(tr("复制正向"))
        self.copy_pos.setObjectName("ghost")
        self.copy_pos.clicked.connect(lambda: self._copy_all(False))
        btns.addWidget(self.copy_pos)
        self.copy_neg = QPushButton(tr("复制负向"))
        self.copy_neg.setObjectName("ghost")
        self.copy_neg.clicked.connect(lambda: copy_text(self.record.get("negative") or ""))
        btns.addWidget(self.copy_neg)
        btns.addStretch(1)
        self.save_btn = QPushButton(tr("保存修改"))
        self.save_btn.setObjectName("primary")
        self.save_btn.clicked.connect(self._save)
        btns.addWidget(self.save_btn)
        self.del_btn = QPushButton(tr("删除记录"))
        self.del_btn.setObjectName("danger")
        self.del_btn.clicked.connect(self._delete)
        btns.addWidget(self.del_btn)
        self.close_btn = QPushButton(tr("关闭"))
        self.close_btn.setObjectName("ghost")
        self.close_btn.clicked.connect(self.accept)
        btns.addWidget(self.close_btn)
        root.addLayout(btns)

        self._load_image()

    def _load_image(self):
        if self.image_path:
            pm = load_pixmap(self.image_path, 560)
            if not pm.isNull():
                self.img_label.setPixmap(pm)

    def _open_image(self):
        if self.image_path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.image_path))

    # ---------- 动作 ----------
    def _add_model_row(self, name: str = "", mtype: str = tr("大模型"), url: str = ""):
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        name_edit = QLineEdit(name)
        name_edit.setPlaceholderText(tr("模型名称"))
        type_combo = QComboBox()
        type_combo.addItems([tr(c) for c in MODEL_TYPE_CHOICES])
        type_combo.setCurrentText(mtype if mtype in MODEL_TYPE_CHOICES else tr("其他"))
        url_edit = QLineEdit(url)
        url_edit.setPlaceholderText(tr("模型链接（可选）"))
        open_btn = QPushButton(tr("打开"))
        open_btn.setObjectName("ghost")
        open_btn.setFixedWidth(52)
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url_edit.text().strip())))
        del_btn = QPushButton("×")
        del_btn.setObjectName("ghost")
        del_btn.setFixedWidth(30)
        del_btn.clicked.connect(lambda: self._remove_model_row(row))
        h.addWidget(name_edit, 3)
        h.addWidget(type_combo, 1)
        h.addWidget(url_edit, 3)
        h.addWidget(open_btn)
        h.addWidget(del_btn)
        self.models_box.addWidget(row)
        self.model_rows.append({"row": row, "name": name_edit, "type": type_combo, "url": url_edit})

    def _remove_model_row(self, row):
        for i, r in enumerate(self.model_rows):
            if r["row"] is row:
                self.models_box.removeWidget(row)
                row.deleteLater()
                del self.model_rows[i]
                break

    def _collect(self) -> dict:
        models = []
        for r in self.model_rows:
            name = r["name"].text().strip()
            if not name:
                continue
            models.append({"name": name, "type": rev(r["type"].currentText()),
                           "url": r["url"].text().strip()})
        return {
            "title": self.title_edit.text().strip(),
            "tags": [t.strip() for t in self.tags_edit.text().replace("，", ",").split(",") if t.strip()],
            "positive": self.pos_edit.toPlainText().strip(),
            "negative": self.neg_edit.toPlainText().strip(),
            "base_model": self.base_combo.currentText(),
            "base_model_raw": self.bm_raw_edit.text().strip(),
            "group": self.group_combo.currentData() or "",
            "models": models,
            "sampler": self._first_line("sampler"),
            "steps": self._first_line("steps"),
            "cfg": self._first_line("cfg"),
            "seed": self._first_line("seed"),
        }

    def _first_line(self, key):
        e = getattr(self, f"{key}_edit", None)
        return (e.text().strip() if e else "")

    def _copy_all(self, with_meta: bool):
        r = self._collect()
        parts = [r["positive"]]
        if r["negative"]:
            parts.append(f"Negative prompt: {r['negative']}")
        if with_meta:
            meta = []
            if r["steps"]:
                meta.append(f"Steps: {r['steps']}")
            if r["sampler"]:
                meta.append(f"Sampler: {r['sampler']}")
            if r["cfg"]:
                meta.append(f"CFG scale: {r['cfg']}")
            if r["seed"]:
                meta.append(f"Seed: {r['seed']}")
            main_models = [m for m in r["models"] if m.get("type") == tr("大模型")]
            if main_models:
                meta.append(f"Model: {main_models[0]['name']}")
            if r["base_model"] and r["base_model"] != tr("其他"):
                meta.append(f"Base model: {r['base_model_raw'] or r['base_model']}")
            if meta:
                parts.append(" ".join(meta))
        text = "\n".join(parts).strip()
        if text:
            QApplication.clipboard().setText(text)
            self._flash(self.copy_all if with_meta else self.copy_pos, tr("已复制 ✓"))
        else:
            self._flash(self.copy_all if with_meta else self.copy_pos, tr("无内容"))

    def _flash(self, btn: QPushButton, text: str):
        old = btn.text()
        btn.setText(text)
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1200, lambda: btn.setText(old))

    def _save(self):
        self.record.update(self._collect())
        self.accept()

    def _delete(self):
        ret = QMessageBox.question(
            self, tr(APP_NAME),
            tr("确定删除这条记录吗？\n图片文件将移入资料库回收站（trash）。"),
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if ret == QMessageBox.Yes:
            self.record["_deleted"] = True
            self.accept()
