"""设置对话框：语言切换等（多语言）。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                               QPushButton, QMessageBox)

from app import i18n
from app.i18n import t as tr
from app.config import APP_NAME


class SettingsDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(i18n.t("设置"))
        self.setModal(True)
        self.resize(380, 210)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        row = QHBoxLayout()
        row.setSpacing(10)
        lb = QLabel(i18n.t("语言") if i18n.t("语言") != "语言" else "界面语言 / Language")
        lb.setObjectName("fieldLabel")
        row.addWidget(lb)
        row.addStretch(1)
        self.lang_combo = QComboBox()
        for code, name in i18n.LANGUAGES.items():
            self.lang_combo.addItem(name, code)
        cur = i18n.current_lang()
        idx = self.lang_combo.findData(cur)
        if idx >= 0:
            self.lang_combo.setCurrentIndex(idx)
        self.lang_combo.currentIndexChanged.connect(self._on_lang_changed)
        row.addWidget(self.lang_combo)
        root.addLayout(row)

        hint = QLabel("切换语言后重启软件即可生效。\nRestart the app to apply language changes.")
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)
        root.addStretch(1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        ok = QPushButton(i18n.t("确定"))
        ok.setObjectName("primary")
        ok.clicked.connect(self.accept)
        btns.addWidget(ok)
        root.addLayout(btns)

    def _on_lang_changed(self, idx):
        code = self.lang_combo.itemData(idx)
        if code and code != i18n.current_lang():
            i18n.set_language(code)
            QMessageBox.information(
                self, tr(APP_NAME),
                "语言已切换，重启软件后生效。\nLanguage changed. Restart the app to apply.")
