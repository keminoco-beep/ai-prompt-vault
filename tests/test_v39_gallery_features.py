"""v3.9 测试：① 虚拟作品显示上限可配置 ② 输出文件夹增量扫描（diff 不重扫）③ reload 指纹跳过（刷新不闪烁）。

覆盖：
- F1：设置读写（默认 250 勾选；改 cap=50 保存后 store 值正确；回显）；
      _apply() 在虚拟记录 > cap 时截断到 cap、enabled=0 时不截断（无提示）；
      settingsApplied 信号在 _save 时发出。
- F2：scan_output_images_delta——临时 output 目录 + 2 个硬编码 1x1 PNG：
      首次 delta → added=2 且缓存写入；再跑无变化 → added=0 且缓存 mtime 未变（不写盘）；
      删除 1 文件 → removed=1；新增 → added=1；改写 → changed=1；
      无元数据 PNG 容错（_build_virtual_record 仍生成记录，尺寸 1x1）。
- F3：reload 指纹跳过——首次 reload 后塞哨兵 item + 记录 count_label；再次 reload
      （数据未变）→ 哨兵仍在/文本未变（未被重建覆盖）、_fp 已更新；数据变化 → 重建。

运行：python tests/test_v39_gallery_features.py
"""
import os, sys, tempfile, json, time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QMessageBox, QListWidgetItem
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.gallery_panel import GalleryPanel, _records_fingerprint
from app.ui.settings_dialog import SettingsDialog
from app import comfy_output
from app.thumbs import image_size

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
    """构造 n 条 is_virtual=True 的虚拟记录（供 _apply 截断测试，不落盘）。"""
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

def has_sentinel(gp):
    for i in range(gp.gallery.count()):
        if gp.gallery.item(i).text() == "SENTINEL_MARKER":
            return True
    return False

# ============ F1: 虚拟作品显示数量可配置 ============
print("[F1] 虚拟作品显示数量可配置（设置读写 + _apply 截断）")
# T1: 默认值：勾选 + 250（fresh store 无设置键 → 走默认）
dlg = SettingsDialog(store)
check("F1 默认勾选", dlg.cap_check.isChecked(), f"checked={dlg.cap_check.isChecked()}")
check("F1 默认 250", dlg.cap_spin.value() == 250, str(dlg.cap_spin.value()))

# T2: 改 cap=50 保存后 store 值正确
dlg.cap_spin.setValue(50)
dlg._save()
check("F1 保存 enabled=1", store.load_setting("virtual_cap_enabled", "1") == "1")
check("F1 保存 count=50", store.load_setting("virtual_cap_count", "250") == "50")

# T3: 回显 + 取消勾选写 0
dlg2 = SettingsDialog(store)
check("F1 回显勾选", dlg2.cap_check.isChecked())
check("F1 回显 50", dlg2.cap_spin.value() == 50, str(dlg2.cap_spin.value()))
dlg2.cap_check.setChecked(False)
dlg2._save()
check("F1 取消勾选写 0", store.load_setting("virtual_cap_enabled", "1") == "0")
# 恢复：截断测试用 enabled=1 + count=50（QSpinBox 合法下限，与需求一致）
store.save_setting("virtual_cap_enabled", "1")
store.save_setting("virtual_cap_count", "50")

# T4: _apply 在虚拟记录 > cap 时截断（cap=50，55 条虚拟 → 显示 50 条 + 提示）
gp = GalleryPanel(store)
gp._records = make_virtual(55)
gp._search_index = {r["id"]: gp._hay_for(r) for r in gp._records}
gp._apply()
drain_chunks(gp)
check("F1 截断到 50", gp.gallery.count() == 50, f"(count={gp.gallery.count()})")
check("F1 截断提示文案", "仅显示前 50 张" in gp.count_label.text(),
      repr(gp.count_label.text()))

# T5: enabled=0 时不截断（55 条全显示，无提示）
store.save_setting("virtual_cap_enabled", "0")
gp._apply()
drain_chunks(gp)
check("F1 不限制显示 55", gp.gallery.count() == 55, f"(count={gp.gallery.count()})")
check("F1 不限制无提示", "仅显示前" not in gp.count_label.text(),
      repr(gp.count_label.text()))
check("F1 不限制文案=共 55 张", gp.count_label.text() == "共 55 张",
      repr(gp.count_label.text()))

# T6: settingsApplied 信号在 _save 时发出（主窗口仅刷新分组+图库，不触发重扫）
emits = [0]
dlg3 = SettingsDialog(store)
dlg3.settingsApplied.connect(lambda: emits.__setitem__(0, emits[0] + 1))
dlg3._save()
check("F1 settingsApplied emit=1", emits[0] == 1, f"({emits[0]})")

# ============ F2: 输出文件夹增量扫描（diff 不重扫） ============
print("[F2] scan_output_images_delta（新增/无变化/删除/变化）")
comfy_output._cache.clear()
comfy_output.clear_memos()
out_d = td / "out_delta"
out_d.mkdir(parents=True, exist_ok=True)
cache_f = str(store.root / "comfy_output_cache.json")
if Path(cache_f).exists():
    Path(cache_f).unlink()
(out_d / "a.png").write_bytes(PNG_1x1)
(out_d / "b.png").write_bytes(PNG_1x1)
w, h = image_size(str(out_d / "a.png"))
check("F2 PNG 头可读尺寸 1x1", (w, h) == (1, 1), f"({w}x{h})")

# 首次 delta：无缓存 → 退化为全量 → added=2，缓存写入
res1 = comfy_output.scan_output_images_delta([str(out_d)], cache_f)
check("F2 首次 added=2", res1.get("added") == 2, repr(res1))
check("F2 首次返回记录 2 条", len(res1.get("records") or []) == 2,
      f"(records={len(res1.get('records') or [])})")
check("F2 首次写入磁盘缓存", Path(cache_f).exists())
data1 = json.loads(Path(cache_f).read_text(encoding="utf-8"))
check("F2 缓存 files=2", len(data1.get("files", {})) == 2,
      f"({len(data1.get('files', {}))})")
rec_a = next((r for r in res1.get("records", [])
              if r.get("virtual_path", "").endswith("a.png")), None)
check("F2 无元数据 PNG 容错生成记录（尺寸 1x1）",
      rec_a is not None and rec_a.get("width") == 1 and rec_a.get("height") == 1,
      f"w={rec_a.get('width') if rec_a else None} h={rec_a.get('height') if rec_a else None}")

# 二次 delta：无变化 → added/removed/changed=0，不写盘（缓存文件 mtime 不变）
mtime1 = Path(cache_f).stat().st_mtime_ns
time.sleep(0.05)   # 确保即使误写盘 mtime 也会变化
res2 = comfy_output.scan_output_images_delta([str(out_d)], cache_f)
check("F2 二次无变化 added=0", res2.get("added") == 0 and res2.get("removed") == 0
      and res2.get("changed") == 0, repr(res2))
check("F2 二次无变化 records 空", len(res2.get("records") or []) == 0)
check("F2 二次不写盘（mtime 未变）", Path(cache_f).stat().st_mtime_ns == mtime1,
      f"(mtime changed)")

# 删除 1 文件 → removed=1
(out_d / "a.png").unlink()
res3 = comfy_output.scan_output_images_delta([str(out_d)], cache_f)
check("F2 删除 removed=1", res3.get("removed") == 1, repr(res3))
check("F2 删除后缓存 files=1",
      len(json.loads(Path(cache_f).read_text(encoding="utf-8")).get("files", {})) == 1)

# 新增 1 文件 → added=1
(out_d / "c.png").write_bytes(PNG_1x1)
res4 = comfy_output.scan_output_images_delta([str(out_d)], cache_f)
check("F2 新增 added=1", res4.get("added") == 1, repr(res4))
check("F2 新增返回记录 1 条", len(res4.get("records") or []) == 1,
      f"(records={len(res4.get('records') or [])})")

# 内容变化（size 变化）→ changed=1
(out_d / "b.png").write_bytes(PNG_1x1 + b"\x00")
res5 = comfy_output.scan_output_images_delta([str(out_d)], cache_f)
check("F2 变化 changed=1", res5.get("changed") == 1, repr(res5))

# 保持现有对外行为不变：load_cached_records / load_cached_groups 仍可用
comfy_output._cache.clear()
comfy_output.clear_memos()
recs_cached = comfy_output.load_cached_records(cache_f, comfy_output.normalize_output_dirs([str(out_d)]))
check("F2 load_cached_records 兼容（缓存 2 条）", len(recs_cached) == 2,
      f"({len(recs_cached)})")

# ============ F3: reload 指纹跳过（刷新不闪烁） ============
print("[F3] reload 指纹比较跳过重建（内容未变时不重建 UI）")
store.save_setting("comfy_output_dirs", [])
comfy_output._cache.clear()
comfy_output.clear_memos()
gp3 = GalleryPanel(store)
gp3.reload()
app.processEvents()
# 首次 reload 后：塞哨兵 item + 记录 count_label 文本
sentinel = QListWidgetItem("SENTINEL_MARKER")
gp3.gallery.addItem(sentinel)
sentinel_count = gp3.gallery.count()
text_before = gp3.count_label.text()
fp_before = gp3._fp
check("F3 首次指纹已更新", fp_before is not None)
# 再次 reload（数据未变）→ 指纹相同 → 跳过重建 → 哨兵仍在、文本未变
gp3.reload()
app.processEvents()
check("F3 二次 reload 哨兵仍在", has_sentinel(gp3) and gp3.gallery.count() == sentinel_count,
      f"(count={gp3.gallery.count()} vs {sentinel_count})")
check("F3 二次 reload count_label 未变", gp3.count_label.text() == text_before,
      repr(gp3.count_label.text()))
check("F3 二次 reload 指纹已更新", gp3._fp == fp_before)
# 指纹函数本身
rA = make_virtual(2)
rB = make_virtual(2)
check("F3 指纹：相同内容相同", _records_fingerprint(rA) == _records_fingerprint(rB))
rB[0]["width"] = 512
check("F3 指纹：字段变化不同", _records_fingerprint(rA) != _records_fingerprint(rB))
# 数据变化 → 指纹不同 → 重建（哨兵被清除）
store.add({"id": "f3_rec", "title": "新增记录", "image_file": "", "media_type": "",
           "width": 64, "height": 64, "created_at": "2026-02-02", "positive": "", "tags": []})
gp3.reload()
app.processEvents()
check("F3 数据变化后重建（哨兵被清除）", not has_sentinel(gp3),
      f"(count={gp3.gallery.count()})")
check("F3 数据变化后新记录可见",
      any(r.get("id") == "f3_rec" for r in gp3._records))

print()
print("v3.9 图库功能（上限配置/增量扫描/指纹跳过）", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
