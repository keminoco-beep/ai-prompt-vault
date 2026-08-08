"""v3.1 测试：ComfyUI output 虚拟图库 + 健康检查忽略 txt。"""
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
from app.filters import filter_records
from app.ui.model_panel import ModelPanel
from app.ui.gallery_panel import GalleryPanel

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

# ============ 任务 2：ComfyUI output 虚拟图库 ============
comfy = td / "ComfyUI"
out = comfy / "output"
(out / "2026-08-08" / "batch1").mkdir(parents=True)

# 带 ComfyUI 工作流元数据的 PNG（根目录）
from PySide6.QtGui import QImage, QColor
img = QImage(640, 480, QImage.Format_RGB32)
img.fill(QColor(60, 100, 180))
img.save(str(out / "root_work.png"), "PNG")

from PIL import Image as PILImage, PngImagePlugin
wf = json.dumps({
    "3": {"class_type": "KSampler", "inputs": {}},
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd15_model.safetensors"}},
    "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "masterpiece, a fox in forest"}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry, low quality"}},
    "7": {"class_type": "LoraLoader", "inputs": {"lora_name": "detail_enhancer.safetensors"}},
})
im = PILImage.new("RGB", (512, 512), (120, 60, 200))
info = PngImagePlugin.PngInfo()
info.add_text("prompt", wf)
info.add_text("workflow", wf)
sub_png = out / "2026-08-08" / "batch1" / "sub_work.png"
im.save(str(sub_png), "PNG", pnginfo=info)
# 无元数据的普通 PNG（子目录）
im2 = PILImage.new("RGB", (300, 200), (200, 160, 60))
im2.save(str(out / "2026-08-08" / "plain.png"), "PNG")
# 忽略非图片文件
(out / "readme.txt").write_text("note", encoding="utf-8")

# comfyui_dir 仅用于模型下载（T6 健康检查）；图库输出目录用 comfy_output_dirs
store.save_setting("comfyui_dir", str(comfy))
store.save_setting("comfy_output_dirs", [str(out)])

# ---- T1: scan_output_images（直接传 output 文件夹路径） ----
vrecs = comfy_output.scan_output_images(str(out))
check("T1 扫描到 3 个虚拟记录", len(vrecs) == 3, f"({len(vrecs)})")
check("T1 txt 被忽略", all("txt" not in (r.get("virtual_path") or "") for r in vrecs))
by_name = {Path(r["virtual_path"]).name: r for r in vrecs}

# 根目录图片 → my_works
r1 = by_name.get("root_work.png")
check("T1 根目录组=my_works", r1 and r1["group"] == comfy_output.GROUP_ROOT)
# 子目录图片 → my_works/2026-08-08/batch1
r2 = by_name.get("sub_work.png")
check("T1 子目录组=my_works/子目录", r2 and r2["group"] == "my_works/2026-08-08/batch1",
      repr(r2.get("group") if r2 else None))
# 元数据提取
check("T1 提取正向提示词", r2 and "fox in forest" in r2["positive"], repr(r2.get("positive") if r2 else ""))
check("T1 提取负向提示词", r2 and "blurry" in r2["negative"])
check("T1 提取模型", r2 and len(r2["models"]) == 1 and r2["models"][0]["name"] == "sd15_model.safetensors")
check("T1 提取 LoRA", r2 and any("detail_enhancer" in lo for lo in (r2["loras"] or [])),
      repr(r2.get("loras") if r2 else None))
check("T1 虚拟标志", r2 and r2.get("is_virtual") is True)
check("T1 尺寸", r2 and r2["width"] == 512 and r2["height"] == 512)

# ---- T2: 增量缓存（第二次扫描不重新解析，结果一致） ----
vrecs2 = comfy_output.scan_output_images(str(out))
check("T2 二次扫描一致", len(vrecs2) == 3)
r2b = next(r for r in vrecs2 if Path(r["virtual_path"]).name == "sub_work.png")
check("T2 缓存后字段相同", r2b["positive"] == r2["positive"])

# ---- T3: virtual_groups 统计 ----
# plain.png 在 2026-08-08（1 个），sub_work.png 在 2026-08-08/batch1（1 个），root_work 在根（1 个）
vg = comfy_output.virtual_groups(str(out))
check("T3 分组统计", vg.get("my_works") == 1 and vg.get("my_works/2026-08-08") == 1
      and vg.get("my_works/2026-08-08/batch1") == 1, repr(vg))

# ---- T4: filter 父组前缀匹配 ----
f_all = filter_records(vrecs, group="my_works")
check("T4 my_works 父组匹配全部虚拟", len(f_all) == 3)
f_sub = filter_records(vrecs, group="my_works/2026-08-08")
check("T4 子组匹配 2 条", len(f_sub) == 2)

# ---- T5: gallery 合并显示 ----
# 产品行为：后台线程先扫描写磁盘缓存，gallery reload 读缓存合并。
# 这里模拟后台扫描生成缓存后 reload。
gp = GalleryPanel(store)
cache_f = str(store.root / "comfy_output_cache.json")
comfy_output._cache.clear()          # 清内存缓存，模拟新进程首次扫描
comfy_output.scan_output_images(str(out), cache_f)   # 扫描并写磁盘缓存
gp.reload()
app.processEvents()
check("T5 gallery 记录含虚拟", any(r.get("is_virtual") for r in gp._records),
      f"(总数 {len(gp._records)})")
check("T5 虚拟记录缩略图可加载",
      not gp._tile_pixmap(
          next(r for r in gp._records if r.get("is_virtual")), 80).isNull())

# ============ 任务 3：健康检查忽略 txt ============
(comfy / "models" / "checkpoints").mkdir(parents=True)
(comfy / "models" / "loras").mkdir(parents=True)
(comfy / "models" / "checkpoints" / "good.safetensors").write_bytes(b"G" * 2_000_000)
# 空 txt（ComfyUI 指引文件）
(comfy / "models" / "loras" / "README.txt").write_bytes(b"")
# 正常 txt
(comfy / "models" / "checkpoints" / "model_info.txt").write_bytes(b"guide text")
# 真异常：空 safetensors
(comfy / "models" / "loras" / "broken.safetensors").write_bytes(b"")

panel = ModelPanel(store)
panel.reload()
app.processEvents()
rels = [m["rel"] for m in panel._models]
check("T6 健康检查忽略 txt", all("txt" not in r for r in rels), repr(rels))
check("T6 仍检测真异常", any("broken" in r for r in rels))
check("T6 异常数=1", panel.health_label.text() == "⚠ 1 个模型健康异常",
      repr(panel.health_label.text()))

print()
print("ComfyUI 输出图库 + txt 忽略", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
