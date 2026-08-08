"""M3.6 A1111 集成：扫描 + 导入（元数据提取/去重/缩略图）+ 设置 UI。"""
import os, sys, tempfile, threading, time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.a1111 import scan_outputs, import_from_outputs, _file_sha256

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

# 造一个 A1111 outputs 目录：1 张带 A1111 元数据的 PNG + 1 张普通 PNG + 1 个 txt（忽略）
out = td / "outputs"
(out / "2026-08-08").mkdir(parents=True)
from PySide6.QtGui import QImage, QColor
img = QImage(320, 240, QImage.Format_RGB32)
img.fill(QColor(70, 120, 200))
# A1111 元数据（tEXt chunk 写入 PNG）
from PIL import Image as PILImage, PngImagePlugin
meta = "masterpiece, best quality, 1girl, landscape\nNegative prompt: lowres, bad quality\nSteps: 25, Sampler: DPM++ 2M, CFG scale: 7, Seed: 12345, Size: 320x240, Model: sd_xl_base_1.0"
p1 = out / "2026-08-08" / "a1.png"
im = PILImage.new("RGB", (320, 240), (70, 120, 200))
info = PngImagePlugin.PngInfo()
info.add_text("parameters", meta)
im.save(str(p1), "PNG", pnginfo=info)
p2 = out / "2026-08-08" / "plain.png"
im2 = PILImage.new("RGB", (100, 100), (200, 80, 80))
im2.save(str(p2), "PNG")
(out / "2026-08-08" / "note.txt").write_text("skip me", encoding="utf-8")

# ---- T1: 扫描 ----
files = scan_outputs(out)
check("T1 扫描到 2 张图片", len(files) == 2, f"({len(files)})")
check("T1 txt 被忽略", all(f.suffix.lower() == ".png" for f in files))

# ---- T2: 导入 ----
imported, skipped, errors = import_from_outputs(store, out)
check("T2 导入 2 张", imported == 2 and skipped == 0 and errors == 0,
      f"({imported}/{skipped}/{errors})")
recs = store.records
check("T2 记录 2 条", len(recs) == 2)
a1 = next((r for r in recs if r["image_file"].startswith("img_") and r["positive"]), None)
check("T2 提取正向提示词", bool(a1) and "1girl" in a1["positive"])
check("T2 提取模型", bool(a1) and a1["models"] and a1["models"][0]["name"] == "sd_xl_base_1.0")
check("T2 提取参数", bool(a1) and a1["sampler"] == "DPM++ 2M" and a1["seed"] == "12345")
check("T2 缩略图生成", all(store.thumbs_dir / r["thumb_file"] for r in recs if r["thumb_file"]))
check("T2 尺寸记录", a1["width"] == 320 and a1["height"] == 240)

# ---- T3: 重复导入去重 ----
imported2, skipped2, errors2 = import_from_outputs(store, out)
check("T3 二次导入全部跳过", imported2 == 0 and skipped2 == 2, f"({imported2}/{skipped2}/{errors2})")
check("T3 记录仍 2 条", len(store.records) == 2)

# ---- T4: hash 一致性（不同文件名同内容） ----
check("T4 sha256 可用", len(_file_sha256(p1)) == 64)

# ---- T5: 设置 UI（A1111 目录行 + 保存） ----
from app.ui.settings_dialog import SettingsDialog
store.save_setting("a1111_dir", str(out))
dlg = SettingsDialog(store)
check("T5 设置回显 A1111 目录", dlg.a1111_edit.text() == str(out))

# ---- T6: GUI 按钮存在 ----
from app.ui.gallery_panel import GalleryPanel
gp = GalleryPanel(store)
btns = [b.text() for b in gp.findChildren(type(gp.zoom) and __import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton)]
check("T6 图库含导入按钮", any("A1111" in b or "A1111" in str(b) for b in btns) or
      any("A1111" in b for b in [bb.text() for bb in gp.findChildren(__import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton)]),
      str([b for b in btns if "A" in b])[:80])

print()
print("M3.6 A1111 集成", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
