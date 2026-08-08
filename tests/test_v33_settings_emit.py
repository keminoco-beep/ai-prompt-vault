"""v3.3 设置对话框 outputDirsChanged 触发回归测试。

QA 复现 bug：_save() 用对话框当前内存列表当基线，与规范化后的同一列表比较
恒等 → emit 永不触发。修复后基线改为 store 中已持久化配置（只读 comfy_output_dirs，
不再含 comfyui_dir 回退——comfyui_dir 与图库输出目录已解耦）。
断言：新增/更换/清空 → emit=1；不变 → emit=0。
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

dirA = td / "outA"
dirB = td / "outB"
dirA.mkdir(parents=True, exist_ok=True)
dirB.mkdir(parents=True, exist_ok=True)

def make_dialog():
    """新建对话框并挂 emit 计数器（不弹 QFileDialog，直接操作 _output_dirs）。"""
    dlg = SettingsDialog(store)
    dlg._emit_count = [0]
    dlg.outputDirsChanged.connect(lambda: dlg._emit_count.__setitem__(0, dlg._emit_count[0] + 1))
    return dlg

# ---- T1: 新增目录 → emit=1 ----
dlg = make_dialog()
check("T1 初始无配置基线为空", dlg._output_dirs == [], repr(dlg._output_dirs))
dlg._output_dirs = [str(dirA)]     # 模拟用户本次「添加文件夹」
dlg._save()
check("T1 新增目录 emit=1", dlg._emit_count[0] == 1, f"({dlg._emit_count[0]})")
check("T1 配置已保存", store.load_setting("comfy_output_dirs") == [str(dirA)],
      repr(store.load_setting("comfy_output_dirs")))

# ---- T2: 更换目录（outA → outB）→ emit=1 ----
dlg = make_dialog()                # 重新打开：基线读 store（outA）
check("T2 重新打开基线=outA", dlg._output_dirs == [str(dirA)], repr(dlg._output_dirs))
dlg._output_dirs = [str(dirB)]     # 模拟用户本次「移除 outA + 添加 outB」
dlg._save()
check("T2 更换目录 emit=1", dlg._emit_count[0] == 1, f"({dlg._emit_count[0]})")

# ---- T3: 清空 → emit=1 ----
dlg = make_dialog()
check("T3 重新打开基线=outB", dlg._output_dirs == [str(dirB)], repr(dlg._output_dirs))
dlg._output_dirs = []              # 模拟用户本次「清空」
dlg._save()
check("T3 清空 emit=1", dlg._emit_count[0] == 1, f"({dlg._emit_count[0]})")

# ---- T4: 不变 → emit=0 ----
dlg = make_dialog()
check("T4 重新打开基线为空", dlg._output_dirs == [], repr(dlg._output_dirs))
dlg._save()
check("T4 不变 emit=0", dlg._emit_count[0] == 0, f"({dlg._emit_count[0]})")

# ---- T5: 只设 comfyui_dir 不再回退（解耦） ----
store.save_setting("comfy_output_dirs", None)
store.save_setting("comfyui_dir", str(td / "ComfyUI_legacy"))
legacy_out = td / "ComfyUI_legacy" / "output"
legacy_out.mkdir(parents=True, exist_ok=True)
dlg = make_dialog()
check("T5 只设 comfyui_dir 基线为空（不再回退）", dlg._output_dirs == [], repr(dlg._output_dirs))
# 用户不修改直接保存：基线([]) == 新值([]) → emit=0
dlg._save()
check("T5 空配置不变 emit=0", dlg._emit_count[0] == 0, f"({dlg._emit_count[0]})")
# 用户改为 outB → emit=1（空基线 [] vs 新 [outB]）
dlg2 = make_dialog()
dlg2._output_dirs = [str(dirB)]
dlg2._save()
check("T5 空配置下更换 emit=1", dlg2._emit_count[0] == 1, f"({dlg2._emit_count[0]})")

print()
print("v3.3 设置 emit 回归", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
