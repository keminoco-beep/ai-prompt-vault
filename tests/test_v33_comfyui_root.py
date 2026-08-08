"""v3.3.1 回归：设置对话框「ComfyUI 根目录」行加回。

背景：v3.3 改造把设置页的 ComfyUI 根目录行替换成了「ComfyUI 输出文件夹」多选行，
新用户无法在设置里配置模型下载路径（下载模型功能仍读 comfyui_dir 定位 models/）。
本测试验证：
- 新行回显：store 预置 comfyui_dir=X → 打开对话框 comfy_edit.text()==X
- _save 写入：改 comfy_edit 文本 → _save() → store 中 comfyui_dir 更新
- 互不干扰：只改 comfyui_dir 行 → comfy_output_dirs 不变且 outputDirsChanged 不 emit；
  只改输出文件夹行 → comfyui_dir 不变
- 旧行为回归：保存空 comfyui_dir 不崩
"""
import os, sys, tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.settings_dialog import SettingsDialog

app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)
td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")

ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {name}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        ok = False

# 预置输出目录（必须真实存在，normalize_output_dirs 对不存在目录返回空）
dirB = td / "outB"
dirC = td / "outC"
dirB.mkdir(parents=True, exist_ok=True)
dirC.mkdir(parents=True, exist_ok=True)

comfyX = td / "ComfyUI_X"
comfyY = td / "ComfyUI_Y"
comfyX.mkdir(parents=True, exist_ok=True)
comfyY.mkdir(parents=True, exist_ok=True)

def make_dialog():
    """新建对话框并挂 emit 计数器（不弹 QFileDialog，直接操作控件/_output_dirs）。"""
    dlg = SettingsDialog(store)
    dlg._emit_count = [0]
    dlg.outputDirsChanged.connect(lambda: dlg._emit_count.__setitem__(0, dlg._emit_count[0] + 1))
    return dlg

# ---- T1: 新行回显 ----
store.save_setting("comfy_output_dirs", [str(dirB)])
store.save_setting("comfyui_dir", str(comfyX))
dlg = make_dialog()
check("T1 comfy_edit 回显 comfyui_dir", dlg.comfy_edit.text() == str(comfyX),
      repr(dlg.comfy_edit.text()))

# ---- T2: _save 写入 ----
dlg.comfy_edit.setText(str(comfyY))
dlg._save()
check("T2 _save 写入 comfyui_dir", store.load_setting("comfyui_dir", "") == str(comfyY),
      repr(store.load_setting("comfyui_dir", "")))

# ---- T3a: 只改 comfyui_dir 行 → comfy_output_dirs 不变、outputDirsChanged 不 emit ----
store.save_setting("comfy_output_dirs", [str(dirB)])
store.save_setting("comfyui_dir", str(comfyX))
dlg = make_dialog()
check("T3a 基线输出目录=outB", dlg._output_dirs == [str(dirB)], repr(dlg._output_dirs))
check("T3a 基线 comfy_edit=comfyX", dlg.comfy_edit.text() == str(comfyX))
dlg.comfy_edit.setText(str(comfyY))     # 只改根目录行
dlg._save()
check("T3a 输出目录集合不变", store.load_setting("comfy_output_dirs") == [str(dirB)],
      repr(store.load_setting("comfy_output_dirs")))
check("T3a 根目录已更新", store.load_setting("comfyui_dir", "") == str(comfyY),
      repr(store.load_setting("comfyui_dir", "")))
check("T3a 仅改根目录 emit=0", dlg._emit_count[0] == 0, f"({dlg._emit_count[0]})")

# ---- T3b: 只改输出文件夹行 → comfyui_dir 不变 ----
store.save_setting("comfy_output_dirs", [str(dirB)])
store.save_setting("comfyui_dir", str(comfyX))
dlg = make_dialog()
check("T3b 基线 comfy_edit=comfyX", dlg.comfy_edit.text() == str(comfyX),
      repr(dlg.comfy_edit.text()))
dlg._output_dirs = [str(dirC)]          # 只改输出文件夹集合
dlg._save()
check("T3b 根目录不变", store.load_setting("comfyui_dir", "") == str(comfyX),
      repr(store.load_setting("comfyui_dir", "")))
check("T3b 输出目录已更新", store.load_setting("comfy_output_dirs") == [str(dirC)],
      repr(store.load_setting("comfy_output_dirs")))

# ---- T4: 旧行为回归：保存空 comfyui_dir 不崩 ----
store.save_setting("comfyui_dir", str(comfyX))
dlg = make_dialog()
check("T4 基线 comfy_edit=comfyX", dlg.comfy_edit.text() == str(comfyX))
dlg.comfy_edit.setText("")              # 清空根目录
try:
    dlg._save()
    check("T4 保存空 comfyui_dir 不崩", True)
    check("T4 comfyui_dir 为空串", store.load_setting("comfyui_dir", "") == "",
          repr(store.load_setting("comfyui_dir", "")))
except Exception as e:
    check("T4 保存空 comfyui_dir 不崩", False, repr(e))

print()
print("v3.3.1 ComfyUI 根目录设置行", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
