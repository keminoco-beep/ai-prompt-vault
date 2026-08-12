"""设置对话框：语言切换、主题、自动导入文件夹（多目录）、ComfyUI 根目录（模型下载）、API Key、资料库位置（多语言）。"""
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
                               QPushButton, QMessageBox, QFileDialog, QLineEdit, QCheckBox,
                               QSpinBox, QWidget)

from app import i18n
from app.i18n import t as tr
from app.config import APP_NAME


class SettingsDialog(QDialog):
    theme_changed = Signal(str)        # 主题即时切换（"dark"/"light"）
    outputDirsChanged = Signal()       # 输出目录集合变化（保存后发出，主窗口触发重新扫描）
    settingsApplied = Signal()         # v3.9：设置保存后发出（主窗口仅刷新分组+图库，不触发重扫）

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

        # ---- 悬浮预览开关（列表模式悬停显示预览图） ----
        hp_row = QHBoxLayout()
        hp_row.setSpacing(10)
        self.hover_check = QCheckBox(tr("启用悬浮预览（列表模式）"))
        self.hover_check.setChecked(self.store.load_setting("hover_preview", "1") != "0")
        hp_row.addWidget(self.hover_check)
        hp_row.addStretch(1)
        root.addLayout(hp_row)

        hpint = QLabel(tr("关闭后不再显示悬停预览图，可减少资源占用；设置立即生效。"))
        hpint.setObjectName("hint")
        hpint.setWordWrap(True)
        root.addWidget(hpint)

        # ---- 限制我的作品显示数量（虚拟作品上限，v3.9 可配置，保存后立即生效） ----
        cap_row = QHBoxLayout()
        cap_row.setSpacing(10)
        self.cap_check = QCheckBox(tr("限制我的作品显示数量"))
        self.cap_check.setChecked(self.store.load_setting("virtual_cap_enabled", "1") != "0")
        cap_row.addWidget(self.cap_check)
        cap_row.addSpacing(8)
        cap_lb = QLabel(tr("我的作品最多显示"))
        cap_lb.setObjectName("fieldLabel")
        cap_row.addWidget(cap_lb)
        self.cap_spin = QSpinBox()
        self.cap_spin.setRange(50, 10000)
        try:
            self.cap_spin.setValue(int(self.store.load_setting("virtual_cap_count", "250") or "250"))
        except Exception:
            self.cap_spin.setValue(250)
        # v4.0：不再 setSuffix("张")——暗色 QSS 下 suffix 区域未渲染样式，
        # 中文单位"张"会溢出显示到输入框编辑区内；改为旁边独立 QLabel 显示单位。
        self.cap_unit = QLabel(tr("张"))
        self.cap_unit.setObjectName("fieldLabel")
        self.cap_spin.setEnabled(self.cap_check.isChecked())
        self.cap_check.toggled.connect(self.cap_spin.setEnabled)
        cap_row.addWidget(self.cap_spin)
        cap_row.addWidget(self.cap_unit)
        cap_row.addStretch(1)
        root.addLayout(cap_row)

        # ---- 自动导入文件夹（多目录，每行一个文件夹 + 浏览/删除按钮） ----
        # v4.0：从「单行 QLineEdit + 移除所选弹窗」改为「每行一个文件夹」，
        # 路径不再被截断；标题改为通用名（不再叫 ComfyUI 输出文件夹）。
        self.out_dir_title = QLabel(tr("自动导入文件夹"))
        self.out_dir_title.setObjectName("fieldLabel")
        root.addWidget(self.out_dir_title)
        dir_cont = QWidget()
        self._dir_list_layout = QVBoxLayout(dir_cont)
        self._dir_list_layout.setContentsMargins(0, 0, 0, 0)
        self._dir_list_layout.setSpacing(6)
        root.addWidget(dir_cont)
        self._dir_rows = []          # list[dict]: path/widget/edit/browse/del
        self._rebuild_dir_rows()

        dir_btns = QHBoxLayout()
        dir_btns.setSpacing(10)
        add_btn = QPushButton(tr("添加文件夹"))
        add_btn.setObjectName("ghost")
        add_btn.clicked.connect(self._add_output_dir)
        dir_btns.addWidget(add_btn)
        dir_btns.addStretch(1)
        clr_btn = QPushButton(tr("清空"))
        clr_btn.setObjectName("ghost")
        clr_btn.clicked.connect(self._clear_output_dirs)
        dir_btns.addWidget(clr_btn)
        root.addLayout(dir_btns)

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

    # ---------- 自动导入文件夹（多目录） ----------
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

    def _rebuild_dir_rows(self):
        """按 self._output_dirs 重建行 widget（增删/回显/测试直改内部列表后同步 UI）。"""
        for entry in list(self._dir_rows):
            self._dir_list_layout.removeWidget(entry["widget"])
            entry["widget"].deleteLater()
        self._dir_rows.clear()
        for d in self._output_dirs:
            self._make_dir_row(d)

    def _make_dir_row(self, d: str):
        """为单个文件夹创建一行：只读路径 + 「浏览」（系统文件管理器）+ 「×」删除。"""
        row = QWidget()
        lay = QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        edit = QLineEdit(d)
        edit.setReadOnly(True)
        lay.addWidget(edit, 1)
        browse_btn = QPushButton(tr("浏览"))
        browse_btn.setObjectName("ghost")
        browse_btn.clicked.connect(lambda _=False, p=d: self._open_dir_in_explorer(p))
        lay.addWidget(browse_btn)
        del_btn = QPushButton("×")
        del_btn.setObjectName("ghost")
        del_btn.setToolTip(tr("移除该文件夹"))
        del_btn.clicked.connect(lambda _=False, p=d: self._remove_dir_row(p))
        lay.addWidget(del_btn)
        self._dir_list_layout.addWidget(row)
        self._dir_rows.append({"path": d, "widget": row, "edit": edit,
                               "browse": browse_btn, "del": del_btn})
        return row

    @staticmethod
    def _open_dir_in_explorer(path: str):
        """在系统文件管理器中打开文件夹（测试通过 monkeypatch spy 验证）。"""
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        except Exception:
            pass

    def _remove_dir_row(self, path: str):
        """删除指定路径对应的行（找到即删；重复路径只删第一个）。"""
        for entry in list(self._dir_rows):
            if entry["path"] == path:
                self._dir_list_layout.removeWidget(entry["widget"])
                entry["widget"].deleteLater()
                self._dir_rows.remove(entry)
                break
        self._output_dirs = [e["path"] for e in self._dir_rows]

    def _add_output_dir(self):
        from pathlib import Path
        start = self._output_dirs[-1] if self._output_dirs else ""
        d = QFileDialog.getExistingDirectory(self, tr("自动导入文件夹"), start)
        if d:
            d = str(Path(d).resolve())
            if d not in self._output_dirs:
                self._output_dirs.append(d)
                self._make_dir_row(d)

    def _clear_output_dirs(self):
        for entry in list(self._dir_rows):
            self._dir_list_layout.removeWidget(entry["widget"])
            entry["widget"].deleteLater()
        self._dir_rows.clear()
        self._output_dirs = []

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
        # v4.0：行 widget 与内部列表同步（测试/外部直改 _output_dirs 后保存时回显一致）
        self._rebuild_dir_rows()
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
        # 悬浮预览开关（关闭后列表模式不显示悬停预览，省资源）
        self.store.save_setting("hover_preview", "1" if self.hover_check.isChecked() else "0")
        # 限制我的作品显示数量（虚拟作品上限，v3.9 可配置；保存后立即生效）
        self.store.save_setting("virtual_cap_enabled", "1" if self.cap_check.isChecked() else "0")
        self.store.save_setting("virtual_cap_count", str(self.cap_spin.value()))
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
        # v3.9：设置保存后即时生效（仅刷新分组 + 图库，不触发重扫）
        self.settingsApplied.emit()
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
