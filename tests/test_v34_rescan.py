"""v3.4.2 测试：缓存失配导致每次启动全量重扫（用户实测 255s 卡死）根因修复回归。

用户实测根因：
- 旧缓存 comfy_output_cache.json 的 dirs 字段是 2 条（output 及其子目录），
  当前配置 comfy_output_dirs 只有 1 条 → _load_disk_cache 校验
  data.get("dirs") != dirs_key → 每次启动全量重扫（4877 图 255s），
  UI 一直显示「正在后台扫描输出文件夹…」。

修复（3 处）：
1. _on_output_dirs_changed：配置变化时先删旧缓存文件 + 清内存缓存（main_window）
2. scan_output_images：_load_disk_cache 失配时先 unlink 磁盘缓存（comfy_output）
3. scan_output_images：多线程并行解析 PNG 元数据（255s → ~40s）

覆盖：
- T1 缓存失配触发重扫：旧缓存 dirs=2 条 → scan(新 1 条, cache) → 全量重扫返回
  正确记录 → 缓存文件 dirs 更新为 1 条
- T2 失配时旧缓存被删除：失配扫描（不写回）后磁盘缓存文件已 unlink
- T3 配置变化删缓存：_on_output_dirs_changed → 缓存文件不存在 + 内存缓存清空
- T4 多线程正确性：20 个带元数据 PNG（含子目录）→ 20 条、id 唯一、元数据正确、
  与单线程基线逐字段一致（断言不依赖解析顺序）
- T5 性能烟雾：50 图 scan 完成不超时（不硬断言秒数，CI 环境波动）

运行：python tests/test_v34_rescan.py
"""
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
from app.ui.main_window import MainWindow

app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)

ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {name}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        ok = False

def make_png(path, text=None, size=(48, 48), color=(100, 150, 200)):
    """生成 PNG；text 非空时写入 ComfyUI 风格 prompt 元数据（真实尾部 chunk）。"""
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

td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")
cache_f = str(store.root / "comfy_output_cache.json")

# ============ T1: 缓存失配触发重扫（dirs 2 条 → 配置 1 条） ============
print("[T1] 缓存失配触发重扫（旧缓存 dirs=2 条，新配置 1 条）")
dirA = td / "outA"; dirB = td / "outB"
for i in range(3):
    make_png(dirA / f"a{i}.png", text=f"alpha prompt {i}")
for i in range(2):
    make_png(dirB / f"b{i}.png", text=f"beta prompt {i}")

# 预置旧缓存：用 dirs=2 条（dirA + dirB）写缓存（模拟用户早期多选目录的历史产物）
comfy_output._cache.clear()
recs_ab = comfy_output.scan_output_images([str(dirA), str(dirB)], cache_f)
check("T1 预置旧缓存 5 条", len(recs_ab) == 5, f"({len(recs_ab)})")
old = json.loads(Path(cache_f).read_text(encoding="utf-8"))
check("T1 旧缓存 dirs 为 2 条",
      old.get("dirs") == comfy_output._dirs_key([str(dirA), str(dirB)]),
      repr(old.get("dirs")))

# 当前配置只有 1 条（dirA）→ 应失配触发全量重扫，返回 dirA 的 3 条
comfy_output._cache.clear()
t0 = time.time()
recs = comfy_output.scan_output_images([str(dirA)], cache_f)
t1 = time.time()
check("T1 失配后重扫返回 3 条（dirA）", len(recs) == 3, f"({len(recs)})")
check("T1 重扫结果不含 dirB 文件",
      all("outB" not in (r.get("virtual_path") or "") for r in recs))
check("T1 重扫结果元数据正确",
      any("alpha prompt 1" in r.get("positive", "") for r in recs))
new = json.loads(Path(cache_f).read_text(encoding="utf-8"))
check("T1 缓存文件 dirs 更新为 1 条",
      new.get("dirs") == comfy_output._dirs_key([str(dirA)]), repr(new.get("dirs")))
check("T1 缓存文件 files=3", len(new.get("files", {})) == 3, f"({len(new.get('files', {}))})")
print(f"    (失配重扫耗时 {t1-t0:.3f}s)")

# ============ T2: 失配时旧缓存被删除 ============
print("[T2] 失配时旧缓存被删除（unlink，后续全新写入）")
# 重建 dirs=2 条的旧缓存
comfy_output._cache.clear()
comfy_output.scan_output_images([str(dirA), str(dirB)], cache_f)
check("T2 重建旧缓存 dirs=2 条",
      json.loads(Path(cache_f).read_text(encoding="utf-8")).get("dirs")
      == comfy_output._dirs_key([str(dirA), str(dirB)]))
# 屏蔽写回：若失配路径没有先 unlink，旧缓存文件会原样保留；有 unlink 则文件不存在
saved = {"called": False}
orig_save = comfy_output._save_disk_cache
comfy_output._save_disk_cache = lambda *a, **k: saved.__setitem__("called", True)
comfy_output._cache.clear()
recs2 = comfy_output.scan_output_images([str(dirA)], cache_f)
comfy_output._save_disk_cache = orig_save
check("T2 失配扫描返回 3 条", len(recs2) == 3, f"({len(recs2)})")
check("T2 失配扫描已触发（本应写回被屏蔽）", saved["called"] is True)
check("T2 旧缓存文件已被删除（不残留失配数据）", not Path(cache_f).exists())

# ============ T3: 配置变化删缓存（_on_output_dirs_changed） ============
print("[T3] 配置变化删缓存（_on_output_dirs_changed）")
out3 = td / "ComfyUI" / "output"
make_png(out3 / "x.png", text="config change prompt")
store.save_setting("comfy_output_dirs", [str(out3)])
comfy_output._cache.clear()
comfy_output.scan_output_images([str(out3)], cache_f)
check("T3 预置缓存存在", Path(cache_f).exists())

win = MainWindow(store, output_scan=False)   # 不启动 800ms 启动扫描定时器
win.show()
app.processEvents()

# 模拟「保存设置后配置变化」：改选新目录并触发 _on_output_dirs_changed；
# spy 掉 _start_output_scan（其内部会再启动后台线程写缓存，测试只验证删除动作）
start_calls = {"n": 0}
orig_start = win._start_output_scan
def spy_start():
    start_calls["n"] += 1
win._start_output_scan = spy_start
store.save_setting("comfy_output_dirs", [str(td / "out_new")])
win._on_output_dirs_changed()
win._start_output_scan = orig_start
app.processEvents()
check("T3 _on_output_dirs_changed 后缓存文件被删除", not Path(cache_f).exists())
check("T3 内存缓存被清空", comfy_output._cache == {}, repr(comfy_output._cache))
check("T3 后台扫描仍被调用（先删缓存再启动扫描）", start_calls["n"] == 1,
      f"(start={start_calls['n']})")
win.close()
app.processEvents()

# ============ T4: 多线程正确性（20 个带元数据 PNG，含子目录） ============
print("[T4] 多线程并行解析正确性（20 条、id 唯一、元数据正确、与单线程一致）")
out4 = td / "outT4"
for i in range(20):
    text = f"parallel-prompt-{i:02d}"
    if i % 2:
        make_png(out4 / "sub" / f"img_{i:02d}.png", text=text)
    else:
        make_png(out4 / f"img_{i:02d}.png", text=text)

comfy_output._cache.clear()
t0 = time.time()
recs4 = comfy_output.scan_output_images([str(out4)], cache_f)
t1 = time.time()
print(f"    (20 图并行解析耗时 {t1-t0:.3f}s)")
check("T4 返回 20 条", len(recs4) == 20, f"({len(recs4)})")
ids4 = [r["id"] for r in recs4]
check("T4 id 唯一", len(set(ids4)) == 20, f"(unique={len(set(ids4))})")
by_name = {Path(r["virtual_path"]).name: r for r in recs4}
check("T4 元数据提取正确",
      all(f"parallel-prompt-{i:02d}" in by_name[f"img_{i:02d}.png"]["positive"]
          for i in range(20)))
check("T4 子目录分组正确",
      by_name["img_01.png"]["group"] == "my_works/sub",
      repr(by_name["img_01.png"]["group"]))

# 单线程基线：逐文件直接调 _build_virtual_record（不走并行路径）
def serial_baseline(dirs):
    dirs = comfy_output.normalize_output_dirs(dirs)
    hashes = comfy_output._dir_hashes(dirs)
    display_names = comfy_output._display_names(dirs)
    out = {}
    for d in dirs:
        dh = hashes[d]
        root = Path(d)
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*")):
            if p.is_file() and p.suffix.lower() in comfy_output.IMAGE_EXTS \
                    and not p.name.endswith(".part"):
                rel = p.relative_to(root).as_posix()
                try:
                    st = p.stat()
                except OSError:
                    continue
                rec = comfy_output._build_virtual_record(
                    root, rel, st.st_mtime,
                    comfy_output._group_prefix_for(dirs, d, display_names), dh)
                out[str(rec["virtual_path"])] = rec
    return out

baseline = serial_baseline([str(out4)])
fields = ("id", "title", "positive", "negative", "base_model", "models", "loras",
          "width", "height", "group", "virtual_path", "_mtime", "_rel", "_dir", "_dir_hash")
consistent = all(
    all(r.get(f) == baseline.get(r.get("virtual_path"), {}).get(f) for f in fields)
    for r in recs4)
check("T4 并行结果与单线程基线逐字段一致（顺序无关）", consistent)
check("T4 基线覆盖全部 20 条", len(baseline) == 20, f"({len(baseline)})")

# ============ T5: 性能烟雾（50 图不超时） ============
print("[T5] 性能烟雾：50 图 scan 完成不超时")
out5 = td / "outT5"
for i in range(50):
    make_png(out5 / f"p_{i:03d}.png", text=f"smoke {i}")
comfy_output._cache.clear()
t0 = time.time()
recs5 = comfy_output.scan_output_images([str(out5)], cache_f)
t1 = time.time()
elapsed = t1 - t0
print(f"    (50 图扫描耗时 {elapsed:.3f}s)")
check("T5 返回 50 条", len(recs5) == 50, f"({len(recs5)})")
check("T5 50 图扫描 < 30s（烟雾，不硬断言秒数）", elapsed < 30, f"({elapsed:.2f}s)")

print()
print("v3.4.2 缓存失配重扫/并行解析", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
