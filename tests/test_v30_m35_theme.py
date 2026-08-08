"""M3.5 亮暗主题：QSS 完整性 + 即时切换 + 硬编码控件刷新。"""
import os, sys, tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

from app import i18n
from app.data_store import DataStore
from app.ui import style as st
from app.ui.main_window import MainWindow

app = QApplication(sys.argv)
app.setStyleSheet(st.APP_QSS)
td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")

ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {name}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        ok = False

# ---- T1: 两套 QSS 完整 ----
check("T1 暗色 QSS 长度", len(st.APP_QSS) > 3000)
check("T1 亮色 QSS 长度", len(st.LIGHT_QSS) > 3000)
check("T1 关键控件覆盖", all(k in st.LIGHT_QSS for k in
      ("#sidebar", "#navBtn", "QPushButton#primary", "QMenu", "QListWidget#downloadList",
       "#modelTree", "#keyNote", "QMessageBox")))
check("T1 主题表含两套", set(st.QSS_BY_THEME) == {"dark", "light"})

# ---- T2: 色板两套齐全 ----
for key in ("img_bg", "dialog_bg", "panel_bg", "panel_border", "drop_border",
            "drop_text", "drop_sub", "logo_color", "status_ok", "status_fail"):
    dk = st._THEME_COLORS["dark"].get(key)
    lt = st._THEME_COLORS["light"].get(key)
    check(f"T2 色板 {key} 双主题", bool(dk) and bool(lt) and dk != lt)

# ---- T3: 即时切换生效 ----
win = MainWindow(store)
win.show()
app.processEvents()
st.set_theme("dark")
win.apply_theme("light")
app.processEvents()
check("T3 当前主题=light", st.theme() == "light")
check("T3 应用 QSS 已换", app.styleSheet() == st.LIGHT_QSS)
# 硬编码控件刷新
check("T3 sidebar img_label 亮色", "e8e8f4" in win.gallery_panel.sidebar.img_label.styleSheet())
check("T3 drop zone 亮色", "qlineargradient" in win.collect_panel.drop.styleSheet() and
      "#ffffff" in win.collect_panel.drop.styleSheet())
check("T3 hover popup 亮色", "e8e8f4" in win.gallery_panel._popup.img_label.styleSheet())
# 切回暗色
win.apply_theme("dark")
app.processEvents()
check("T3 切回暗色", st.theme() == "dark" and app.styleSheet() == st.APP_QSS)
check("T3 sidebar img_label 暗色", "0e0e16" in win.gallery_panel.sidebar.img_label.styleSheet())

# ---- T4: 设置对话框主题下拉 + 保存 ----
from app.ui.settings_dialog import SettingsDialog
dlg = SettingsDialog(store, win)
check("T4 主题下拉 2 项", dlg.theme_combo.count() == 2)
check("T4 默认选中暗色", dlg.theme_combo.currentData() == "dark")
dlg.theme_combo.setCurrentIndex(dlg.theme_combo.findData("light"))
dlg._save()
check("T4 保存 theme=light", store.load_setting("theme", "") == "light")

print()
print("M3.5 亮暗主题", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
