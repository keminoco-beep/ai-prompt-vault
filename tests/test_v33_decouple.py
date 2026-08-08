"""v3.3 解耦测试：comfyui_dir 与「我的作品」图库输出目录完全解耦。

需求：comfyui_dir（ComfyUI 根目录）只保留模型下载用途；
「我的作品」图库只认独立的 comfy_output_dirs（output 文件夹多选配置），
不再从 comfyui_dir 回退推导 output 目录（防止两个设置重复导入）。

断言：
- 只设 comfyui_dir（含 output 子目录）→ configured_output_dirs 返回 []（不再自动导入）
- 只设 comfy_output_dirs=[A] → 返回 [A]；两者并存 → 只返回新键
- settings_dialog._load_output_dirs() 同步解耦：只设 comfyui_dir → 空
- 模型下载不受影响：download_manager / model_panel 仍读 comfyui_dir
"""
import os, sys, tempfile, json
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app import comfy_output
from app.ui.settings_dialog import SettingsDialog
from app.ui.download_manager import DownloadManager

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

def make_png(path, text=None, size=(64, 64), color=(100, 150, 200)):
    """生成 PNG；text 非空时写入 ComfyUI 风格 prompt 元数据。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    from PIL import Image as PILImage, PngImagePlugin
    im = PILImage.new("RGB", size, color)
    if text is not None:
        wf = json.dumps({"5": {"class_type": "CLIPTextEncode", "inputs": {"text": text}}})
        info = PngImagePlugin.PngInfo()
        info.add_text("prompt", wf)
        im.save(str(path), "PNG", pnginfo=info)
    else:
        im.save(str(path), "PNG")

# ---- 目录结构：A（2 张） + comfy 根（含 output 子目录，1 张） ----
dirA = td / "outA"
dirA.mkdir(parents=True, exist_ok=True)
make_png(dirA / "a1.png", text="alpha prompt")
make_png(dirA / "a2.png")
comfy = td / "ComfyUI"
legacy_out = comfy / "output"
make_png(legacy_out / "leg.png", text="legacy prompt")

# ---- T1: 只设 comfyui_dir（含 output 子目录）→ 返回 [] ----
store.save_setting("comfy_output_dirs", None)
store.save_setting("comfyui_dir", str(comfy))
dirs = comfy_output.configured_output_dirs(store)
check("T1 只设 comfyui_dir → []", dirs == [], repr(dirs))
recs = comfy_output.scan_output_images(dirs)
check("T1 空目录配置扫描 0 条", recs == [], f"({len(recs)})")

# ---- T2: 只设 comfy_output_dirs=[A] → 返回 [A] ----
store.save_setting("comfy_output_dirs", [str(dirA)])
dirs2 = comfy_output.configured_output_dirs(store)
check("T2 只设 comfy_output_dirs → [A]", len(dirs2) == 1 and Path(dirs2[0]).name == "outA",
      repr(dirs2))

# ---- T3: 两者并存 → 只返回新键（不重复导入） ----
store.save_setting("comfyui_dir", str(comfy))
dirs3 = comfy_output.configured_output_dirs(store)
check("T3 并存只返回新键 [A]", len(dirs3) == 1 and Path(dirs3[0]).name == "outA", repr(dirs3))
recs3 = comfy_output.scan_output_images(dirs3)
check("T3 扫描仅 A 的 2 条（不含 legacy）", len(recs3) == 2
      and all("leg" not in (r.get("virtual_path") or "") for r in recs3), f"({len(recs3)})")

# ---- T4: settings_dialog._load_output_dirs() 同步解耦 ----
store.save_setting("comfy_output_dirs", None)
store.save_setting("comfyui_dir", str(comfy))
dlg = SettingsDialog(store)
check("T4 只设 comfyui_dir → 对话框基线为空", dlg._output_dirs == [], repr(dlg._output_dirs))
store.save_setting("comfy_output_dirs", [str(dirA)])
dlg2 = SettingsDialog(store)
check("T4 只设 comfy_output_dirs → 对话框基线=[A]",
      len(dlg2._output_dirs) == 1 and Path(dlg2._output_dirs[0]).name == "outA",
      repr(dlg2._output_dirs))

# ---- T5: 模型下载不受影响（download_manager 仍读 comfyui_dir） ----
store.save_setting("comfyui_dir", str(comfy))
dm = DownloadManager(store)
check("T5 DownloadManager 读 comfyui_dir", dm.comfy_dir() == str(comfy),
      repr(dm.comfy_dir()))
check("T5 store 中 comfyui_dir 未被图库逻辑改动",
      store.load_setting("comfyui_dir", "") == str(comfy),
      repr(store.load_setting("comfyui_dir", "")))

# ---- T6: normalize_output_dirs 不再自动落 output 子目录 ----
# 传 comfy 根路径字符串时按根目录本身处理（不再落到 output/）
store.save_setting("comfy_output_dirs", [str(comfy)])
dirs6 = comfy_output.configured_output_dirs(store)
check("T6 新键=comfy 根 → 按根本身（不再落 output）", len(dirs6) == 1 and Path(dirs6[0]).name == "ComfyUI",
      repr(dirs6))

print()
print("v3.3 comfyui_dir 解耦", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
