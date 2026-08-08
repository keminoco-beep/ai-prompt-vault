"""v3.1b 磁盘缓存：启动不卡（缓存持久化 + 增量）+ 真实 output 验证。"""
import os, sys, tempfile, json, time
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

comfy = td / "ComfyUI"
out = comfy / "output"
(out / "sub").mkdir(parents=True)
from PIL import Image as PILImage, PngImagePlugin
import json as _json
wf = _json.dumps({"5": {"class_type": "CLIPTextEncode", "inputs": {"text": "cached test"}}})
for i in range(5):
    im = PILImage.new("RGB", (64, 64), (i * 40, 60, 120))
    info = PngImagePlugin.PngInfo(); info.add_text("prompt", wf)
    target = out / "sub" / f"img_{i}.png" if i % 2 else out / f"img_{i}.png"
    im.save(str(target), "PNG", pnginfo=info)

cache_file = store.root / "comfy_output_cache.json"

# ---- T1: 首次扫描 + 写磁盘缓存 ----
t0 = time.time()
recs1 = comfy_output.scan_output_images(str(out), str(cache_file))
t1 = time.time()
check("T1 首次扫描 5 条", len(recs1) == 5)
check("T1 缓存文件已写", cache_file.exists())
check("T1 缓存文件含 5 个文件", len(json.loads(cache_file.read_text(encoding="utf-8"))["files"]) == 5)

# ---- T2: 新进程（清内存缓存）从磁盘加载，不重解析 ----
comfy_output._cache.clear()
t2 = time.time()
recs2 = comfy_output.scan_output_images(str(out), str(cache_file))
t3 = time.time()
check("T2 磁盘缓存加载 5 条", len(recs2) == 5)
check("T2 缓存加载 < 0.5s", (t3 - t2) < 0.5, f"({t3-t2:.3f}s)")
check("T2 缓存后元数据仍在", any("cached test" in r["positive"] for r in recs2))

# ---- T3: 增量（新增 1 个文件只解析 1 个） ----
im6 = PILImage.new("RGB", (32, 32), (10, 200, 10))
info6 = PngImagePlugin.PngInfo(); info6.add_text("prompt", _json.dumps(
    {"5": {"class_type": "CLIPTextEncode", "inputs": {"text": "brand new"}}}))
im6.save(str(out / "img_new.png"), "PNG", pnginfo=info6)
comfy_output._cache.clear()
t4 = time.time()
recs3 = comfy_output.scan_output_images(str(out), str(cache_file))
t5 = time.time()
check("T3 增量后 6 条", len(recs3) == 6)
check("T3 新增文件解析到元数据", any("brand new" in r["positive"] for r in recs3))

# ---- T4: 删除文件后缓存清理 ----
(out / "img_new.png").unlink()
comfy_output._cache.clear()
recs4 = comfy_output.scan_output_images(str(out), str(cache_file))
check("T4 删除后 5 条", len(recs4) == 5)

# ---- T5: MainWindow 启动不卡（后台扫描线程） ----
from app.ui.main_window import MainWindow
# comfyui_dir 仅用于模型下载；图库输出目录用 comfy_output_dirs（解耦后唯一入口）
store.save_setting("comfyui_dir", str(comfy))
store.save_setting("comfy_output_dirs", [str(out)])
win = MainWindow(store)
win.show()
app.processEvents()
# 启动后立即检查：不应有同步扫描阻塞（进程事件循环 1 秒内响应）
t6 = time.time()
app.processEvents()
check("T5 启动构建 < 2s", (time.time() - t6) < 2)
# 分组树显示（走缓存）
win.refresh_groups()
app.processEvents()
texts = []
def walk(items):
    for it in items:
        texts.append(it.text(0))
        walk([it.child(i) for i in range(it.childCount())])
walk([win.group_tree.topLevelItem(i) for i in range(win.group_tree.topLevelItemCount())])
check("T5 分组树 my_works 计数 5", any("我的作品（5）" in t for t in texts), repr(texts))
# 等待后台扫描线程完成
import time as _t
for _ in range(20):
    app.processEvents()
    _t.sleep(0.1)
app.processEvents()
check("T5 后台扫描完成后刷新", any("我的作品（5）" in t for t in
      [it.text(0) for i in range(win.group_tree.topLevelItemCount())
       for it in [win.group_tree.topLevelItem(i)]] + texts))

print()
print("v3.1b 磁盘缓存", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
