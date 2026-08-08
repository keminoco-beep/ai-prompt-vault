"""M3.4 多资料库：resolve_library_dir + 设置保存 + 设置对话框 UI。"""
import os, sys, tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)

from app import i18n
from app.config import resolve_library_dir, library_dir
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.settings_dialog import SettingsDialog

app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)
td = Path(tempfile.mkdtemp())

ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {name}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        ok = False

# ---- T1: resolve_library_dir 默认库 ----
d1 = resolve_library_dir("")
check("T1 默认库路径存在", d1.is_dir())
check("T1 默认库名为 Library", d1.name == "Library")

# ---- T2: 自定义库 ----
custom = td / "MyVault"
d2 = resolve_library_dir(str(custom))
check("T2 自定义库路径", d2 == custom.resolve() and d2.is_dir())
# 根目录由 resolve 创建；子目录（images/…）由 DataStore 构造时创建
s2 = DataStore(d2)
check("T2 DataStore 创建子目录", (d2 / "images").exists() and (d2 / "thumbs").exists())

# ---- T3: 设置保存到默认库 + 设置对话框 UI ----
import app.config as _cfg_mod
_orig_library_dir = _cfg_mod.library_dir
fake_default_root = td / "_default_lib"      # 模拟的默认库根目录（monkeypatch 隔离，绝不碰真实项目 Library）
_cfg_mod.library_dir = lambda: fake_default_root

store = DataStore(d2)
i18n.init(store.settings_path(), "zh")
dlg = SettingsDialog(store)
# lib_edit 显示当前库
check("T3 对话框显示当前库", dlg.lib_edit.text() == str(d2))
# 模拟 _save：换到新路径 → 写入（被 monkeypatch 的）默认库设置
new_lib = td / "AnotherVault"
dlg.lib_edit.setText(str(new_lib))
dlg._save()
saved = DataStore(fake_default_root).load_setting("library_dir_custom", "")
check("T3 换库写入默认库设置", Path(saved).resolve() == new_lib.resolve(), repr(saved))
# 恢复真实 library_dir
_cfg_mod.library_dir = _orig_library_dir
# 真实默认库必须未被污染
from app.config import library_dir as _ld
real_settings = Path(_ld()) / "settings.json"
real_custom = ""
if real_settings.exists():
    import json as _json
    try:
        real_custom = _json.loads(real_settings.read_text(encoding="utf-8")).get("library_dir_custom", "")
    except Exception:
        pass
check("T3 未污染真实项目默认库", real_custom == "", repr(real_custom))
# 设置对话框 _save 不动 comfyui_dir
check("T3 comfyui_dir 保留", store.load_setting("comfyui_dir", "") == "")

# ---- T4: 数据隔离（不同库互不影响） ----
libA = DataStore(td / "LibA")
libB = DataStore(td / "LibB")
libA.add({"id": "a1", "title": "AAA", "models": []})
check("T4 A 库有 1 条", len(libA.records) == 1)
check("T4 B 库为空", len(libB.records) == 0)
libB.add({"id": "b1", "title": "BBB", "models": []})
check("T4 B 库有 1 条", len(libB.records) == 1)
check("T4 重新打开 A 库仍 1 条", len(DataStore(td / "LibA").records) == 1)

print()
print("M3.4 多资料库", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
