"""下载相关对话框：类型选择对话框（其他模型）。"""
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                               QPushButton)

from app import comfy
from app.i18n import t as tr, tr_format


class TypePickDialog(QDialog):
    """"其他"等无标准目录的模型类型：让用户选择 ComfyUI 子目录。"""

    def __init__(self, model_name: str, comfy_dir, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("选择模型类型"))
        self.setModal(True)
        self.resize(440, 170)
        self.picked = ""
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        tip = QLabel(tr_format("模型「{name}」属于『其他』类型，请选择要保存到的 ComfyUI 模型文件夹：",
                               name=model_name[:40]))
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        root.addWidget(tip)

        row = QHBoxLayout()
        lb = QLabel(tr("模型类型"))
        lb.setObjectName("fieldLabel")
        row.addWidget(lb)
        self.combo = QComboBox()
        known = [k for k in comfy.COMIFY_MODEL_DIRS]
        subs = comfy.available_subdirs(comfy_dir)
        seen, final = set(), []
        for o in known + subs:
            if o not in seen:
                seen.add(o)
                final.append(o)
        self.combo.addItems(final)
        row.addWidget(self.combo, 1)
        root.addLayout(row)

        btns = QHBoxLayout()
        btns.addStretch(1)
        ok = QPushButton(tr("确定"))
        ok.setObjectName("primary")
        ok.clicked.connect(self._ok)
        btns.addWidget(ok)
        root.addLayout(btns)

    def _ok(self):
        self.picked = self.combo.currentText()
        self.accept()