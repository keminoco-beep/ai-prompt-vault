"""v3.1 真实环境自检：完整 MainWindow + 分组树层级 + 图库虚拟记录 + 英文翻译 + 不污染真实库。"""
import os, sys, tempfile, json
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS, set_theme
from app.ui.main_window import MainWindow

app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)
set_theme("dark")
td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")

ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {name}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        ok = False

# 模拟 ComfyUI output：根目录 + 子目录 + 带元数据的 PNG
comfy = td / "ComfyUI"
out = comfy / "output"
(out / "batch_01").mkdir(parents=True)
from PIL import Image as PILImage, PngImagePlugin
wf = json.dumps({
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux.safetensors"}},
    "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "cyberpunk city, night"}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry"}},
})
im = PILImage.new("RGB", (768, 512), (40, 80, 160))
info = PngImagePlugin.PngInfo(); info.add_text("prompt", wf)
im.save(str(out / "batch_01" / "a.png"), "PNG", pnginfo=info)
im2 = PILImage.new("RGB", (400, 300), (200, 120, 40))
im2.save(str(out / "root_pic.png"), "PNG")
store.save_setting("comfyui_dir", str(comfy))           # 模型下载仍读（本测试未用，语义保留）
store.save_setting("comfy_output_dirs", [str(out)])      # 图库输出目录（解耦后唯一入口）
store.add({"id": "r1", "title": "手动收藏", "positive": "x", "models": [], "source": "local"})

win = MainWindow(store)
win.show()
app.processEvents()

# ---- T1: 分组树层级 ----
win.refresh_groups()
app.processEvents()
texts = []
def walk(items):
    for it in items:
        texts.append((it.data(0, 0x0100), it.text(0)))
        walk([it.child(i) for i in range(it.childCount())])
walk([win.group_tree.topLevelItem(i) for i in range(win.group_tree.topLevelItemCount())])
roles = {d for d, _ in texts}
check("T1 分组树含 my_works", "my_works" in roles, repr(sorted([r for r in roles if r])))
check("T1 分组树含子组", any(d == "my_works/batch_01" for d, _ in texts))
check("T1 分组树含 我的作品 文案", any("我的作品" in t for _, t in texts))
check("T1 全部图片计数含虚拟", any("全部图片（3）" in t for _, t in texts), repr(texts[:3]))

# ---- T2: 图库合并虚拟记录 + 分组筛选 ----
# 模拟后台线程扫描写缓存（产品中 scan_output_images 由后台线程调用），
# 完成后 gallery reload 读缓存合并显示
from app.comfy_output import scan_output_images
scan_output_images(str(out), str(store.root / "comfy_output_cache.json"))
gp = win.gallery_panel
gp.reload()
app.processEvents()
vrecs = [r for r in gp._records if r.get("is_virtual")]
check("T2 图库含 2 条虚拟记录", len(vrecs) == 2, f"({len(vrecs)})")
check("T2 虚拟记录元数据提取", any("cyberpunk" in r.get("positive", "") for r in vrecs))
# 点「我的作品」分组筛选
gp.set_group("my_works")
app.processEvents()
shown = [gp.gallery.item(i).data(0x0100) for i in range(gp.gallery.count())]
check("T2 my_works 筛选显示 2 条", len(shown) == 2, f"({len(shown)})")
# 点子组
gp.set_group("my_works/batch_01")
app.processEvents()
shown2 = [gp.gallery.item(i).data(0x0100) for i in range(gp.gallery.count())]
check("T2 子组筛选显示 1 条", len(shown2) == 1)
# 回全部
gp.set_group("全部")
app.processEvents()

# ---- T3: 详情侧栏虚拟记录 ----
rec = next(r for r in gp._records if r.get("is_virtual") and r.get("virtual_path"))
gp.sidebar.set_record(rec)
app.processEvents()
check("T3 侧栏标题", "root_pic.png" in gp.sidebar.title_label.text() or
      "cyberpunk" in gp.sidebar.title_label.text())

# ---- T4: 英文模式翻译 ----
i18n.init(store.settings_path(), "en")
win.refresh_groups()
app.processEvents()
texts2 = []
def walk2(items):
    for it in items:
        texts2.append(it.text(0))
        walk2([it.child(i) for i in range(it.childCount())])
walk2([win.group_tree.topLevelItem(i) for i in range(win.group_tree.topLevelItemCount())])
check("T4 英文 我的作品→My Works", any("My Works" in t for t in texts2), repr(texts2))
i18n.init(store.settings_path(), "zh")

# ---- T5: 真实默认库未被污染 ----
from app.config import library_dir as _ld
real_s = Path(_ld()) / "settings.json"
real_custom = ""
if real_s.exists():
    try:
        real_custom = json.loads(real_s.read_text(encoding="utf-8")).get("library_dir_custom", "")
    except Exception:
        pass
check("T5 真实默认库未被污染", real_custom == "", repr(real_custom))

print()
print("v3.1 真实环境自检", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
