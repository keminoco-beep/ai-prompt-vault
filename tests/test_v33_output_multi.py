"""v3.3 测试：ComfyUI 输出文件夹多目录扫描 + 按文件夹分组 + 缓存失效 + comfyui_dir 解耦。"""
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

# ---- 目录结构：outA（3 张）、outB（2 张） ----
dirA = td / "outA"
dirB = td / "outB"
make_png(dirA / "a_root.png", text="alpha root prompt")
make_png(dirA / "subA" / "a_sub.png", text="alpha sub prompt")
make_png(dirA / "subA" / "plain.png")          # 无元数据
make_png(dirB / "b_root.png", text="beta root prompt")
make_png(dirB / "subB" / "b_sub.png")

# ---- T1: 多目录扫描 ----
comfy_output._cache.clear()
recs = comfy_output.scan_output_images([str(dirA), str(dirB)])
check("T1 扫描 5 条", len(recs) == 5, f"({len(recs)})")
ids = [r["id"] for r in recs]
check("T1 id 不冲突", len(set(ids)) == len(ids))
by_name = {Path(r["virtual_path"]).name: r for r in recs}
check("T1 A 根组=my_works/outA", by_name["a_root.png"]["group"] == "my_works/outA",
      repr(by_name["a_root.png"]["group"]))
check("T1 A 子组=my_works/outA/subA", by_name["a_sub.png"]["group"] == "my_works/outA/subA")
check("T1 B 根组=my_works/outB", by_name["b_root.png"]["group"] == "my_works/outB")
check("T1 B 子组=my_works/outB/subB", by_name["b_sub.png"]["group"] == "my_works/outB/subB")
check("T1 元数据提取", "alpha sub prompt" in by_name["a_sub.png"]["positive"],
      repr(by_name["a_sub.png"]["positive"]))
check("T1 无元数据记录正常", by_name["plain.png"]["positive"] == "")

# ---- T2: comfyui_dir 不再回退（解耦） + 新键优先 ----
comfy = td / "ComfyUI_legacy"
legacy_out = comfy / "output"
make_png(legacy_out / "leg.png")
store.save_setting("comfy_output_dirs", None)   # 未设置新键
store.save_setting("comfyui_dir", str(comfy))
dirs1 = comfy_output.configured_output_dirs(store)
check("T2 只设 comfyui_dir 不再回退 → []", dirs1 == [], repr(dirs1))
recs_legacy = comfy_output.scan_output_images(dirs1)
check("T2 空目录配置扫描 0 条", recs_legacy == [])
# 新键优先（即使旧键仍在，也不两者并存）
store.save_setting("comfy_output_dirs", [str(dirB)])
dirs2 = comfy_output.configured_output_dirs(store)
check("T2 新键优先且不含旧 output", len(dirs2) == 1 and Path(dirs2[0]).name == "outB", repr(dirs2))
store.save_setting("comfy_output_dirs", None)   # 复位，避免影响后续

# ---- T3: 增删目录缓存失效 ----
comfy_output._cache.clear()
cache_f = str(store.root / "comfy_output_cache.json")
ra = comfy_output.scan_output_images([str(dirA)], cache_f)
check("T3 扫 A=3 条", len(ra) == 3, f"({len(ra)})")
rab = comfy_output.scan_output_images([str(dirA), str(dirB)], cache_f)
check("T3 扫 A+B=5 条", len(rab) == 5, f"({len(rab)})")
rb = comfy_output.scan_output_images([str(dirB)], cache_f)
check("T3 扫 B=2 条", len(rb) == 2, f"({len(rb)})")
check("T3 B 结果不含 A 文件", all("outA" not in (r.get("virtual_path") or "") for r in rb))
# 从磁盘再加载 B（模拟新进程：清内存缓存）
comfy_output._cache.clear()
rb2 = comfy_output.scan_output_images([str(dirB)], cache_f)
check("T3 磁盘缓存 B=2 条", len(rb2) == 2, f"({len(rb2)})")

# ---- T4: 磁盘缓存 round-trip + 集合不匹配 ----
comfy_output._cache.clear()
comfy_output.scan_output_images([str(dirA), str(dirB)], cache_f)
cached = comfy_output.load_cached_records(cache_f, [str(dirA), str(dirB)])
check("T4 load_cached_records=5 条", len(cached) == 5, f"({len(cached)})")
check("T4 缓存含分组字段", all(r.get("group") for r in cached))
stale = comfy_output.load_cached_records(cache_f, [str(dirA)])
check("T4 目录集合不匹配返回空（不抛异常）", stale == [], f"({len(stale)})")

# ---- T5: 重名目录分组消歧 ----
dirC = td / "x" / "out"
dirD = td / "y" / "out"
make_png(dirC / "c.png")
make_png(dirD / "d.png")
comfy_output._cache.clear()
recs_cd = comfy_output.scan_output_images([str(dirC), str(dirD)])
groups_cd = {r["group"] for r in recs_cd}
check("T5 重名目录分组不冲突", len(groups_cd) == 2 and "my_works/out" not in groups_cd,
      repr(groups_cd))

# ---- T6: quick_group_counts 多目录（只枚举不解析） ----
counts = comfy_output.quick_group_counts([str(dirA), str(dirB)])
check("T6 quick 计数", counts.get("my_works/outA") == 1
      and counts.get("my_works/outA/subA") == 2
      and counts.get("my_works/outB") == 1
      and counts.get("my_works/outB/subB") == 1, repr(counts))

# ---- T7: gallery reload 含虚拟记录（复用缓存预生成模式） ----
store.save_setting("comfy_output_dirs", [str(dirA), str(dirB)])   # 图库读配置校验缓存集合
comfy_output._cache.clear()
comfy_output.scan_output_images([str(dirA), str(dirB)], cache_f)
gp = GalleryPanel(store)
gp.reload()
app.processEvents()
vrecs = [r for r in gp._records if r.get("is_virtual")]
check("T7 gallery 含 5 条虚拟记录", len(vrecs) == 5, f"({len(vrecs)})")
check("T7 虚拟记录缩略图可加载",
      not gp._tile_pixmap(next(r for r in vrecs if r.get("virtual_path")), 80).isNull())

print()
print("v3.3 多目录输出扫描", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
