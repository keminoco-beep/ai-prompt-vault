"""设置对话框：语言切换、ComfyUI 文件夹（多语言）。"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                               QPushButton, QMessageBox, QFileDialog, QLineEdit)

from app import i18n
from app.i18n import t as tr
from app.config import APP_NAME


class SettingsDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(tr("设置"))
        self.setModal(True)
        self.resize(460, 260)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 18)
        root.setSpacing(12)

        # ---- 语言 ----
        row = QHBoxLayout()
        row.setSpacing(10)
        lb = QLabel(tr("界面语言"))
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

        # ---- ComfyUI 文件夹 ----
        comfy_row = QHBoxLayout()
        comfy_row.setSpacing(10)
        clb = QLabel(tr("ComfyUI 文件夹"))
        clb.setObjectName("fieldLabel")
        comfy_row.addWidget(clb)
        self.comfy_edit = QLineEdit()
        self.comfy_edit.setPlaceholderText(tr("选择 ComfyUI 根目录（含 models/ 子目录）"))
        self.comfy_edit.setText(self.store.load_setting("comfyui_dir", ""))
        comfy_row.addWidget(self.comfy_edit, 1)
        browse = QPushButton(tr("浏览…"))
        browse.setObjectName("ghost")
        browse.clicked.connect(self._pick_comfy_dir)
        comfy_row.addWidget(browse)
        root.addLayout(comfy_row)

        chint = QLabel(tr("设置后可在图库一键下载图片使用的模型到 ComfyUI 对应类别的模型文件夹。"))
        chint.setObjectName("hint")
        chint.setWordWrap(True)
        root.addWidget(chint)

        # ---- Civitai API Key（下载鉴权） ----
        key_row = QHBoxLayout()
        key_row.setSpacing(10)
        klb = QLabel(tr("Civitai API Key"))
        klb.setObjectName("fieldLabel")
        key_row.addWidget(klb)
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText("civ_...（可选，解决模型下载 403 / HTML 错误页）")
        self.key_edit.setText(self.store.load_setting("civitai_api_key", ""))
        key_row.addWidget(self.key_edit, 1)
        root.addLayout(key_row)

        khint = QLabel(
            "在 Civitai 用户中心（https://civitai.red/user/account → API Keys → New API Key）生成，"
            "粘贴到这里即可让模型下载携带登录凭证。\n"
            "Generate at civitai.red/user/account → API Keys. Needed to download models without 403.")
        khint.setObjectName("hint")
        khint.setWordWrap(True)
        root.addWidget(khint)

        root.addStretch(1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        ok = QPushButton(tr("确定"))
        ok.setObjectName("primary")
        ok.clicked.connect(self._save)
        btns.addWidget(ok)
        root.addLayout(btns)

    def _pick_comfy_dir(self):
        from pathlib import Path
        cur = self.comfy_edit.text().strip()
        start = cur if Path(cur).is_dir() else ""
        d = QFileDialog.getExistingDirectory(self, tr("选择 ComfyUI 根目录"), start)
        if d:
            self.comfy_edit.setText(d)

    def _save(self):
        path = self.comfy_edit.text().strip()
        self.store.save_setting("comfyui_dir", path)
        api_key = self.key_edit.text().strip()
        self.store.save_setting("civitai_api_key", api_key)
        self.accept()

    def _on_lang_changed(self, idx):
        code = self.lang_combo.itemData(idx)
        if code and code != i18n.current_lang():
            i18n.set_language(code)
            QMessageBox.information(
                self, tr(APP_NAME),
                "语言已切换，重启软件后生效。\nLanguage changed. Restart the app to apply.")
