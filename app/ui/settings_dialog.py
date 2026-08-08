"""设置对话框：语言切换、主题、ComfyUI 输出文件夹（多目录）、ComfyUI 根目录（模型下载）、API Key、资料库位置（多语言）。"""
from pathlib import Path
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                               QPushButton, QMessageBox, QFileDialog, QLineEdit)

from app import i18n
from app.i18n import t as tr
from app.config import APP_NAME


class SettingsDialog(QDialog):
    theme_changed = Signal(str)        # 主题即时切换（"dark"/"light"）
    outputDirsChanged = Signal()       # 输出目录集合变化（保存后发出，主窗口触发重新扫描）

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle(tr("设置"))
        self.setModal(True)
        self.resize(480, 380)
        self._output_dirs = self._load_output_dirs()
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

        hint = QLabel(tr("切换语言后重启软件即可生效。"))
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

        # ---- 界面主题（即时生效） ----
        th_row = QHBoxLayout()
        th_row.setSpacing(10)
        thlb = QLabel(tr("界面主题"))
        thlb.setObjectName("fieldLabel")
        th_row.addWidget(thlb)
        th_row.addStretch(1)
        self.theme_combo = QComboBox()
        from app.ui import style as st
        for code, name in (("dark", tr("暗色")), ("light", tr("亮色"))):
            self.theme_combo.addItem(name, code)
        cur_theme = st.theme()
        idx = self.theme_combo.findData(cur_theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        th_row.addWidget(self.theme_combo)
        root.addLayout(th_row)

        thint = QLabel(tr("界面主题即时生效。"))
        thint.setObjectName("hint")
        thint.setWordWrap(True)
        root.addWidget(thint)

        # ---- ComfyUI 输出文件夹（多目录，直接填写 output 文件夹路径） ----
        out_row = QHBoxLayout()
        out_row.setSpacing(10)
        olb = QLabel(tr("ComfyUI 输出文件夹"))
        olb.setObjectName("fieldLabel")
        out_row.addWidget(olb)
        self.output_edit = QLineEdit()
        self.output_edit.setReadOnly(True)
        self.output_edit.setPlaceholderText(tr("选择 ComfyUI 输出文件夹"))
        self._update_output_edit()
        out_row.addWidget(self.output_edit, 1)
        add_btn = QPushButton(tr("添加文件夹"))
        add_btn.setObjectName("ghost")
        add_btn.clicked.connect(self._add_output_dir)
        out_row.addWidget(add_btn)
        root.addLayout(out_row)

        out_btns = QHBoxLayout()
        out_btns.addStretch(1)
        rm_btn = QPushButton(tr("移除所选"))
        rm_btn.setObjectName("ghost")
        rm_btn.clicked.connect(self._remove_output_dir)
        out_btns.addWidget(rm_btn)
        clr_btn = QPushButton(tr("清空"))
        clr_btn.setObjectName("ghost")
        clr_btn.clicked.connect(self._clear_output_dirs)
        out_btns.addWidget(clr_btn)
        root.addLayout(out_btns)

        ohint = QLabel(tr("可添加多个输出文件夹，图库将按文件夹自动分组。"))
        ohint.setObjectName("hint")
        ohint.setWordWrap(True)
        root.addWidget(ohint)

        # ---- ComfyUI 根目录（用于模型下载，与输出文件夹独立） ----
        comfy_row = QHBoxLayout()
        comfy_row.setSpacing(10)
        clb = QLabel(tr("ComfyUI 根目录（用于模型下载）"))
        clb.setObjectName("fieldLabel")
        comfy_row.addWidget(clb)
        self.comfy_edit = QLineEdit()
        self.comfy_edit.setPlaceholderText(tr("选择 ComfyUI 根目录（含 models/ 子目录）"))
        self.comfy_edit.setText(self.store.load_setting("comfyui_dir", ""))
        comfy_row.addWidget(self.comfy_edit, 1)
        comfy_btn = QPushButton(tr("浏览…"))
        comfy_btn.setObjectName("ghost")
        comfy_btn.clicked.connect(self._pick_comfy_dir)
        comfy_row.addWidget(comfy_btn)
        root.addLayout(comfy_row)

        # ---- A1111 / WebUI outputs 目录（可选） ----
        a11_row = QHBoxLayout()
        a11_row.setSpacing(10)
        alb = QLabel(tr("A1111 outputs 目录"))
        alb.setObjectName("fieldLabel")
        a11_row.addWidget(alb)
        self.a1111_edit = QLineEdit()
        self.a1111_edit.setPlaceholderText(tr("可选：Automatic1111 输出目录，用于一键导入生成图"))
        self.a1111_edit.setText(self.store.load_setting("a1111_dir", ""))
        a11_row.addWidget(self.a1111_edit, 1)
        a11b = QPushButton(tr("浏览…"))
        a11b.setObjectName("ghost")
        a11b.clicked.connect(self._pick_a1111_dir)
        a11_row.addWidget(a11b)
        root.addLayout(a11_row)

        ahint = QLabel(tr("设置后可在图库一键把 A1111 生成的图片（含提示词等参数）导入收藏。"))
        ahint.setObjectName("hint")
        ahint.setWordWrap(True)
        root.addWidget(ahint)

        # ---- Civitai API Key（下载鉴权） ----
        key_row = QHBoxLayout()
        key_row.setSpacing(10)
        klb = QLabel(tr("Civitai API Key"))
        klb.setObjectName("fieldLabel")
        key_row.addWidget(klb)
        # 标注：API 仅用于下载模型（不上传任何数据）
        key_note = QLabel(tr("仅用于下载模型"))
        key_note.setObjectName("keyNote")
        key_note.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        key_row.addWidget(key_note)
        self.key_edit = QLineEdit()
        self.key_edit.setPlaceholderText(tr("civ_...（可选，解决模型下载 403 / HTML 错误页）"))
        self.key_edit.setText(self.store.load_setting("civitai_api_key", ""))
        key_row.addWidget(self.key_edit, 1)
        root.addLayout(key_row)

        khint = QLabel(
            tr("在 Civitai 用户中心（https://civitai.red/user/account → API Keys → New API Key）生成，粘贴到这里即可让模型下载携带登录凭证。"))
        khint.setObjectName("hint")
        khint.setWordWrap(True)
        root.addWidget(khint)

        # ---- 资料库位置（多资料库） ----
        lib_row = QHBoxLayout()
        lib_row.setSpacing(10)
        llb = QLabel(tr("资料库位置"))
        llb.setObjectName("fieldLabel")
        lib_row.addWidget(llb)
        self.lib_edit = QLineEdit()
        self.lib_edit.setReadOnly(True)
        self.lib_edit.setText(str(self.store.root))
        lib_row.addWidget(self.lib_edit, 1)
        lib_btn = QPushButton(tr("更换…"))
        lib_btn.setObjectName("ghost")
        lib_btn.clicked.connect(self._pick_library_dir)
        lib_row.addWidget(lib_btn)
        root.addLayout(lib_row)

        libhint = QLabel(tr("更换资料库后重启软件生效。当前库：{p}").format(p=str(self.store.root)))
        libhint.setObjectName("hint")
        libhint.setWordWrap(True)
        root.addWidget(libhint)

        root.addStretch(1)

        btns = QHBoxLayout()
        btns.addStretch(1)
        ok = QPushButton(tr("确定"))
        ok.setObjectName("primary")
        ok.clicked.connect(self._save)
        btns.addWidget(ok)
        root.addLayout(btns)

    # ---------- ComfyUI 输出文件夹（多目录） ----------
    def _load_output_dirs(self) -> list:
        """读取当前输出目录配置（只读 comfy_output_dirs，不再回退 comfyui_dir）。

        comfyui_dir 仅用于模型下载；「我的作品」图库只认 comfy_output_dirs，
        避免两个设置重复导入。
        """
        from app.comfy_output import normalize_output_dirs
        dirs = self.store.load_setting("comfy_output_dirs", None)
        if dirs is None or not dirs:
            return []
        return normalize_output_dirs(dirs)

    def _update_output_edit(self):
        self.output_edit.setText("；".join(self._output_dirs))

    def _add_output_dir(self):
        from pathlib import Path
        start = self._output_dirs[-1] if self._output_dirs else ""
        d = QFileDialog.getExistingDirectory(self, tr("选择 ComfyUI 输出文件夹"), start)
        if d:
            d = str(Path(d).resolve())
            if d not in self._output_dirs:
                self._output_dirs.append(d)
                self._update_output_edit()

    def _remove_output_dir(self):
        if not self._output_dirs:
            QMessageBox.information(self, tr(APP_NAME), tr("请先添加输出文件夹"))
            return
        from PySide6.QtWidgets import QInputDialog
        cur, ok = QInputDialog.getItem(
            self, tr("移除所选"), tr("选择要移除的输出文件夹："),
            self._output_dirs, 0, False)
        if ok and cur:
            self._output_dirs = [d for d in self._output_dirs if d != cur]
            self._update_output_edit()

    def _clear_output_dirs(self):
        self._output_dirs = []
        self._update_output_edit()

    def _pick_library_dir(self):
        from pathlib import Path
        from app.config import library_dir
        cur = str(self.store.root)
        start = cur if Path(cur).is_dir() else str(library_dir())
        d = QFileDialog.getExistingDirectory(self, tr("选择资料库文件夹"), start)
        if d:
            self.lib_edit.setText(d)
            QMessageBox.information(
                self, tr(APP_NAME),
                tr("资料库已切换，重启软件后生效。"))

    def _pick_comfy_dir(self):
        from pathlib import Path
        cur = self.comfy_edit.text().strip()
        start = cur if Path(cur).is_dir() else ""
        d = QFileDialog.getExistingDirectory(self, tr("选择 ComfyUI 根目录"), start)
        if d:
            self.comfy_edit.setText(d)

    def _pick_a1111_dir(self):
        from pathlib import Path
        cur = self.a1111_edit.text().strip()
        start = cur if Path(cur).is_dir() else ""
        d = QFileDialog.getExistingDirectory(self, tr("选择 A1111 outputs 目录"), start)
        if d:
            self.a1111_edit.setText(d)

    def _save(self):
        from app.comfy_output import normalize_output_dirs
        # 基线 = store 中**已持久化**的配置（保存前读取，尚未被本次写入覆盖；
        # 只读 comfy_output_dirs，不再含 comfyui_dir 回退），与本次编辑后的 new_dirs
        # 比较，集合不同才 emit。
        # 不能用 self._output_dirs 当基线——它已含用户本次编辑，比较恒等导致信号永不触发。
        old_dirs = self._load_output_dirs()
        new_dirs = normalize_output_dirs(self._output_dirs)
        self.store.save_setting("comfy_output_dirs", new_dirs)
        # ComfyUI 根目录（用于模型下载）：独立保存，不影响输出目录集合
        self.store.save_setting("comfyui_dir", self.comfy_edit.text().strip())
        api_key = self.key_edit.text().strip()
        self.store.save_setting("civitai_api_key", api_key)
        self.store.save_setting("a1111_dir", self.a1111_edit.text().strip())
        self.store.save_setting("theme", self.theme_combo.currentData() or "dark")
        # 多资料库：library_dir_custom 必须写到默认库的 settings.json（main 启动时从默认库读取）
        new_lib = self.lib_edit.text().strip()
        if new_lib and str(Path(new_lib).resolve()) != str(self.store.root.resolve()):
            try:
                from app.config import library_dir
                default_store = __import__("app.data_store", fromlist=["DataStore"]).DataStore(library_dir())
                default_store.save_setting("library_dir_custom", new_lib)
            except Exception:
                pass
        # 输出目录集合变化 → 通知主窗口立即后台重扫
        if new_dirs != old_dirs:
            self.outputDirsChanged.emit()
            QMessageBox.information(
                self, tr(APP_NAME),
                tr("output 目录已变更，正在后台扫描…"))
        self.accept()

    def _on_lang_changed(self, idx):
        code = self.lang_combo.itemData(idx)
        if code and code != i18n.current_lang():
            i18n.set_language(code)
            QMessageBox.information(
                self, tr(APP_NAME),
                tr("语言已切换，重启软件后生效。"))

    def _on_theme_changed(self, idx):
        code = self.theme_combo.itemData(idx)
        if code:
            self.theme_changed.emit(code)
