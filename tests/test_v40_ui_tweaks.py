"""v4.0 UI 修正测试：
① SpinBox「张」单位改独立 QLabel（不再 setSuffix，避免暗色 QSS 下中文单位
   溢出渲染到输入框编辑区内）
② 新图片缩略图生成/兜底（delta + thumb_gen：合法图有缩略图、损坏图不阻塞且
   记日志；占位图不缓存、缩略图生成后 _refresh_missing_thumbs 精准重渲染——
   修复「一些新图片永远显示占位图」）
③ grid 滚轮按像素滚动（ScrollPerPixel + singleStep=20，一格位移 ≤ 行高一半，
   不再体感翻页）
④ 设置页输出文件夹列表 UI 重构（每行一个文件夹 + 浏览/×；标题=自动导入文件夹；
   添加/删除/浏览/清空/保存链路 + i18n 三表同步）

运行：python tests/test_v40_ui_tweaks.py
"""
import os, sys, tempfile, ast, logging
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QMessageBox, QFileDialog, QAbstractItemView
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
from PySide6.QtCore import Qt, QPoint, QPointF, QUrl
from PySide6.QtGui import QWheelEvent, QDesktopServices

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.gallery_panel import GalleryPanel
from app.ui.settings_dialog import SettingsDialog
from app import comfy_output

app = QApplication([])
app.setStyleSheet(APP_QSS)
td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")

ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {name}" + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        ok = False

# 1x1 透明 PNG（硬编码字节，合法：IHDR 可读尺寸 1x1，无元数据 chunk）
PNG_1x1 = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
    "0000000a49444154789c63000100000500010d0a2db40000000049454e44ae426082"
)

def make_virtual(n, prefix="v"):
    """构造 n 条 is_virtual=True 的虚拟记录（供滚动测试，不落盘）。"""
    return [{
        "id": f"vout:{prefix}{i}", "title": f"{prefix}{i}", "tags": [], "positive": "",
        "negative": "", "base_model": "其他", "base_model_raw": "", "models": [], "loras": [],
        "sampler": "", "steps": "", "cfg": "", "seed": "",
        "width": 0, "height": 0, "source": "comfy_output", "source_url": "",
        "image_file": "", "thumb_file": "", "media_type": "image", "video_file": "",
        "group": "my_works", "is_virtual": True,
        "virtual_path": f"C:/fake/output/{prefix}{i}.png",
        "created_at": "2026-01-01 00:00:00",
    } for i in range(n)]

def drain_chunks(gp):
    """把分片渲染全部执行完（大数据量逐批推进，测试确定性）。"""
    for _ in range(1000):
        if gp._chunk_records is None:
            break
        gp._render_grid_chunk()
    app.processEvents()

def reset_comfy_state():
    comfy_output._cache.clear()
    comfy_output.clear_memos()

# ============ T1: SpinBox 单位改独立 QLabel ============
print("[T1] SpinBox「张」单位改独立 QLabel")
dlg1 = SettingsDialog(store)
check("T1 cap_spin 已移除 suffix", dlg1.cap_spin.suffix() == "", repr(dlg1.cap_spin.suffix()))
check("T1 单位在独立 QLabel（张）", dlg1.cap_unit.text() == "张", repr(dlg1.cap_unit.text()))
check("T1 单位 QLabel 紧邻 SpinBox", dlg1.cap_spin.parent() is dlg1.cap_unit.parent())

# ============ T2: 增量新增图片缩略图生成 + 损坏文件兜底 ============
print("[T2] 增量新增图片缩略图生成 + 损坏文件兜底")
reset_comfy_state()
out_d = td / "out_t2"
out_d.mkdir(parents=True, exist_ok=True)
cache_f = str(store.root / "comfy_output_cache.json")
if Path(cache_f).exists():
    Path(cache_f).unlink()
thumb_dir = str(store.root / "comfy_output_thumbs")
(out_d / "good.png").write_bytes(PNG_1x1)
(out_d / "bad.png").write_bytes(b"NOTPNG-not-a-real-image")
(out_d / "note.txt").write_text("ignore me")     # 不支持的扩展名 → 不应入图库
res = comfy_output.scan_output_images_delta([str(out_d)], cache_f)
check("T2 delta added=2（仅图片）", res.get("added") == 2, repr(res))
check("T2 非图片扩展名不入库",
      all(not r.get("virtual_path", "").endswith(".txt") for r in res.get("records", [])))
good_rec = next((r for r in res.get("records", [])
                 if r.get("virtual_path", "").endswith("good.png")), None)
bad_rec = next((r for r in res.get("records", [])
                if r.get("virtual_path", "").endswith("bad.png")), None)
check("T2 合法/损坏记录均生成", good_rec is not None and bad_rec is not None)

# 捕获缩略图生成日志
class _Handler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.msgs = []
    def emit(self, record):
        self.msgs.append(record.getMessage())
h = _Handler()
comfy_output.logger.addHandler(h)
comfy_output.logger.setLevel(logging.WARNING)
done = comfy_output.generate_all_thumbs([str(out_d)], thumb_dir)
comfy_output.logger.removeHandler(h)
check("T2 thumb_gen 成功 1 张（合法图）", done == 1, f"done={done}")
tp_good = comfy_output.thumb_path_for_rec(store, good_rec)
tp_bad = comfy_output.thumb_path_for_rec(store, bad_rec)
check("T2 合法图有缩略图", tp_good.exists() and tp_good.stat().st_size >= 100, str(tp_good))
check("T2 损坏图无缩略图", not tp_bad.exists(), str(tp_bad))
check("T2 失败有清晰日志（含路径）", any("bad.png" in m for m in h.msgs), repr(h.msgs[:3]))

# 模拟用户在 grid 模式看新图片
store.save_setting("comfy_output_dirs", [str(out_d)])
gp2 = GalleryPanel(store)
app.processEvents()
good_uid = good_rec["id"]
bad_uid = bad_rec["id"]
pm_good = gp2._tile_pixmap(good_rec, 100)
check("T2 grid 合法图 tile 非空", pm_good is not None and not pm_good.isNull())
check("T2 grid 合法图命中缩略图缓存", f"{good_uid}@100" in gp2._pm_cache)
pm_bad = gp2._tile_pixmap(bad_rec, 100)
check("T2 grid 损坏图 tile 占位非空", pm_bad is not None and not pm_bad.isNull())
check("T2 损坏图 uid 记入缺失集合", bad_uid in gp2._missing_thumb_uids)
check("T2 占位图不缓存 uid 条目（可刷新）", f"{bad_uid}@100" not in gp2._pm_cache)

# ============ T2b: 缩略图生成后占位图精准重渲染 ============
print("[T2b] 缩略图生成后 _refresh_missing_thumbs 重渲染（不依赖 reload 重建）")
reset_comfy_state()
out_b = td / "out_t2b"
out_b.mkdir(parents=True, exist_ok=True)
if Path(cache_f).exists():
    Path(cache_f).unlink()
(out_b / "fresh.png").write_bytes(PNG_1x1)
res_b = comfy_output.scan_output_images_delta([str(out_b)], cache_f)
store.save_setting("comfy_output_dirs", [str(out_b)])
gp_b = GalleryPanel(store)
app.processEvents()
fresh_rec = next((r for r in res_b.get("records", [])
                  if r.get("virtual_path", "").endswith("fresh.png")), None)
fresh_uid = fresh_rec["id"] if fresh_rec else None
li = None
for i in range(gp_b.gallery.count()):
    it = gp_b.gallery.item(i)
    if it.data(Qt.UserRole) == fresh_uid:
        li = it
        break
check("T2b 找到新图片 tile", li is not None)
check("T2b 缩略图未生成时在缺失集合", fresh_uid in gp_b._missing_thumb_uids)
icon_before = li.icon().cacheKey() if li else -1
# 生成缩略图：记录数据不变 → reload 指纹相同 → 不重建（这正是旧 bug 场景）
comfy_output.generate_all_thumbs([str(out_b)], thumb_dir)
tp_fresh = comfy_output.thumb_path_for_rec(store, fresh_rec)
check("T2b 缩略图已生成", tp_fresh.exists() and tp_fresh.stat().st_size >= 100)
gp_b.reload()
app.processEvents()
li_after = None
for i in range(gp_b.gallery.count()):
    it = gp_b.gallery.item(i)
    if it.data(Qt.UserRole) == fresh_uid:
        li_after = it
        break
check("T2b reload 指纹相同未重建（同一 item）", li is not None and li is li_after)
check("T2b 刷新前 tile 仍是占位图", li.icon().cacheKey() == icon_before)
gp_b._refresh_missing_thumbs()
check("T2b 刷新后 tile 图标已更新", li.icon().cacheKey() != icon_before)
check("T2b 刷新后移出缺失集合", fresh_uid not in gp_b._missing_thumb_uids)

# ============ T3: grid 滚轮按像素滚动 ============
print("[T3] grid 滚轮按像素滚动（ScrollPerPixel）")
gp3 = GalleryPanel(store)
gp3.zoom.setValue(320)
gp3._records = make_virtual(80)
gp3._search_index = {r["id"]: gp3._hay_for(r) for r in gp3._records}
gp3._apply()
drain_chunks(gp3)
check("T3 verticalScrollMode=ScrollPerPixel",
      gp3.gallery.verticalScrollMode() == QAbstractItemView.ScrollPerPixel,
      str(gp3.gallery.verticalScrollMode()))
check("T3 singleStep=20", gp3.gallery.verticalScrollBar().singleStep() == 20,
      str(gp3.gallery.verticalScrollBar().singleStep()))
gp3.gallery.resize(320, 320)
gp3.gallery.show()
app.processEvents()
gp3.gallery.doItemsLayout()   # 强制计算 item 布局 → 滚动条范围生效（offscreen 下必需）
app.processEvents()
vbar = gp3.gallery.verticalScrollBar()
grid_h = gp3.gallery.gridSize().height()
check("T3 有滚动范围", vbar.maximum() > 0, f"max={vbar.maximum()}")
# 模拟滚轮向下滚一格（angleDelta=-120）
ev = QWheelEvent(QPointF(160, 160), QPointF(0, 0), QPoint(0, 0), QPoint(0, -120),
                 Qt.NoButton, Qt.NoModifier, Qt.NoScrollPhase, False)
before = vbar.value()
gp3.gallery.wheelEvent(ev)
app.processEvents()
after = vbar.value()
delta = abs(after - before)
check("T3 滚一格位移 ≤ 行高一半（按像素）", delta <= max(1, grid_h // 2),
      f"delta={delta} grid_h={grid_h}")

# ============ T4: 设置页输出文件夹列表 UI 重构 ============
print("[T4] 设置页输出文件夹列表 UI 重构")
store.save_setting("comfy_output_dirs", None)
dirA = td / "dirA"
dirB = td / "dirB"
dirA.mkdir(parents=True, exist_ok=True)
dirB.mkdir(parents=True, exist_ok=True)
pathA = str(dirA.resolve())
pathB = str(dirB.resolve())
dlg = SettingsDialog(store)
check("T4 标题=自动导入文件夹", dlg.out_dir_title.text() == "自动导入文件夹",
      repr(dlg.out_dir_title.text()))
check("T4 初始行数=0", len(dlg._dir_rows) == 0, str(len(dlg._dir_rows)))
check("T4 初始内部列表空", dlg._output_dirs == [])

real_getdir = QFileDialog.getExistingDirectory
real_openurl = QDesktopServices.openUrl
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(dirA))
dlg._add_output_dir()
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(dirB))
dlg._add_output_dir()
check("T4 添加 2 个文件夹后行数=2", len(dlg._dir_rows) == 2, str(len(dlg._dir_rows)))
check("T4 内部列表同步", dlg._output_dirs == [pathA, pathB], repr(dlg._output_dirs))
check("T4 行路径显示正确", dlg._dir_rows[0]["edit"].text() == pathA,
      repr(dlg._dir_rows[0]["edit"].text()))
# 已存在路径不重复添加
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(dirA))
dlg._add_output_dir()
check("T4 重复路径不重复添加", len(dlg._dir_rows) == 2, str(len(dlg._dir_rows)))
# 删除第 2 行的「×」
dlg._dir_rows[1]["del"].click()
check("T4 删除第2行后行数=1", len(dlg._dir_rows) == 1, str(len(dlg._dir_rows)))
check("T4 删除后内部=[A]", dlg._output_dirs == [pathA], repr(dlg._output_dirs))
# 「浏览」→ QDesktopServices.openUrl spy
calls = []
QDesktopServices.openUrl = staticmethod(lambda u: calls.append(u) or True)
dlg._dir_rows[0]["browse"].click()
check("T4 浏览调 openUrl(dirA)", len(calls) == 1 and calls[0] == QUrl.fromLocalFile(pathA),
      repr(calls))
# 清空
dlg._clear_output_dirs()
check("T4 清空后行数=0", len(dlg._dir_rows) == 0 and dlg._output_dirs == [],
      f"rows={len(dlg._dir_rows)} dirs={dlg._output_dirs}")
# _save 写入 comfy_output_dirs 与内部列表一致（normalize 会排序，dirA<dirB）
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(dirA))
dlg._add_output_dir()
QFileDialog.getExistingDirectory = staticmethod(lambda *a, **k: str(dirB))
dlg._add_output_dir()
dlg._save()
saved = store.load_setting("comfy_output_dirs")
check("T4 _save 写入与内部一致", saved == [pathA, pathB] and set(saved) == set(dlg._output_dirs),
      repr(saved))
check("T4 保存后行数=2（_save 同步行）", len(dlg._dir_rows) == 2, str(len(dlg._dir_rows)))
QFileDialog.getExistingDirectory = real_getdir
QDesktopServices.openUrl = real_openurl

# ============ T5: i18n 三表一致 + 新 key + en_keys.txt 同步 ============
print("[T5] i18n 三表一致 + 新 key + en_keys.txt 同步")
src = open("app/i18n.py", encoding="utf-8").read()
tree = ast.parse(src)
tables = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_LANG_TABLES"
                                            for t in node.targets):
        tables = {k.value: {kk.value: vv.value for kk, vv in zip(v.keys, v.values)}
                  for k, v in zip(node.value.keys, node.value.values)}
en, es, ja = tables["en"], tables["es"], tables["ja"]
check("T5 三表 key 集合一致", set(en) == set(es) == set(ja),
      f"{len(en)}/{len(es)}/{len(ja)}")
for k in ["自动导入文件夹", "浏览", "张", "添加文件夹",
          "可添加多个输出文件夹，图库将按文件夹自动分组。"]:
    check(f"T5 key 三表齐备: {k[:12]}…", k in en and k in es and k in ja)
en_txt = (Path(__file__).resolve().parent.parent / "en_keys.txt").read_text(encoding="utf-8")
check("T5 en_keys.txt 含「自动导入文件夹」", "'自动导入文件夹'" in en_txt)
check("T5 en_keys.txt 含「浏览」", "'浏览'" in en_txt)

print()
print("v4.0 UI 修正（SpinBox 单位/缩略图/滚轮/文件夹列表）",
      "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
