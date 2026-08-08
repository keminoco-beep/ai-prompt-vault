"""v3.4 测试：幽灵记录（查重删除后重启复现）修复 + 查重排除虚拟记录 + 文件缺失标记。

覆盖：
1. remove 全链路持久化：临时库 add→remove→重启无（含 data.json 旧索引复活回归——
   真实库的幽灵记录根因是 SqliteStore._migrate_if_needed 每次启动从 data.json 回灌，
   修复后仅 SQLite 空表时才迁移，删除持久生效）
2. 查重排除虚拟记录：构造 1 真实 + 1 虚拟重复图 → find_duplicate_groups 只列真实
3. 文件缺失标记：记录存在但 image_file/thumb_file 缺失 → _tile_pixmap 不崩、
   _missing_marker 生效、标题带标记；正常记录无标记
4. i18n 新增 key 四语一致（文件缺失 / 正在后台扫描输出文件夹…）

运行：python tests/test_v34_ghost.py
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
from app.dupe_util import find_duplicate_groups

app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)

ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {name}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        ok = False

# ============ T1: remove 全链路持久化 + data.json 复活回归 ============
print("[T1] remove 全链路持久化（模拟真实库 data.json 旧索引存在）")
td = Path(tempfile.mkdtemp())
lib = td / "Library"
lib.mkdir(parents=True)
# 旧版 data.json（迁移源）含一条"已删除"记录 + 一条保留记录
data = {"records": [
    {"id": "ghost001", "title": "g1", "image_file": "g1.jpg", "thumb_file": "g1.png"},
    {"id": "keep001", "title": "k1", "image_file": "k1.jpg", "thumb_file": "k1.png"},
]}
(lib / "data.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

s1 = DataStore(lib)
s1.add({"id": "newrec", "title": "new", "image_file": "n.jpg", "thumb_file": "n.png"})
check("T1 首次启动含旧索引记录", len(s1.records) == 3, repr([r["id"] for r in s1.records]))
s1.remove("ghost001")                       # 用户删除
check("T1 remove 后内存无 ghost001", all(r["id"] != "ghost001" for r in s1.records))
del s1

s2 = DataStore(lib)                          # 重启（模拟）
check("T1 重启后 ghost001 不复活（修复）",
      all(r["id"] != "ghost001" for r in s2.records),
      repr([r["id"] for r in s2.records]))
check("T1 keep001 保留", any(r["id"] == "keep001" for r in s2.records))
check("T1 newrec 保留", any(r["id"] == "newrec" for r in s2.records))

# ============ T2: 查重排除虚拟记录 ============
print("[T2] 查重排除虚拟记录")
from PySide6.QtGui import QImage, QColor
store2 = DataStore(td / "Lib2")
i18n.init(store2.settings_path(), "zh")
store2.thumbs_dir.mkdir(parents=True, exist_ok=True)
img = QImage(64, 64, QImage.Format_RGB32)
img.fill(QColor(30, 120, 200))
p_real = store2.thumbs_dir / "dup_real.png"
p_real2 = store2.thumbs_dir / "dup_real2.png"
p_virt = store2.thumbs_dir / "dup_virt.png"
img.save(str(p_real), "PNG")
img.save(str(p_real2), "PNG")
img.save(str(p_virt), "PNG")
from app.dupe_util import image_dhash
check("T2 三图 dHash 一致", image_dhash(str(p_real)) == image_dhash(str(p_real2))
      == image_dhash(str(p_virt)) != "")

rec_real = store2.add({"id": "real001", "title": "真实1", "thumb_file": "dup_real.png"})
rec_real2 = store2.add({"id": "real002", "title": "真实2", "thumb_file": "dup_real2.png"})
rec_virt = {"id": "vout:abc:def", "title": "虚拟", "is_virtual": True,
            "virtual_path": str(p_virt), "thumb_file": ""}
records = [rec_real, rec_real2, rec_virt]

# 解析器连虚拟记录也解析（最坏情况：若不过滤，虚拟会并入重复组）
def thumb_of(r):
    if r.get("thumb_file"):
        p = store2.thumbs_dir / r["thumb_file"]
        return str(p) if p.exists() else ""
    if r.get("virtual_path"):
        p = Path(r["virtual_path"])
        return str(p) if p.exists() else ""
    return ""

from app.ui.gallery_panel import GalleryPanel
real_only = GalleryPanel.real_records(records)
check("T2 real_records 过滤虚拟", len(real_only) == 2
      and all(r["id"] not in ("vout:abc:def",) for r in real_only),
      repr([r["id"] for r in real_only]))
groups_all = find_duplicate_groups(records, thumb_of)
check("T2 全量（不过滤）1 组 3 张", len(groups_all) == 1 and len(groups_all[0]) == 3,
      repr([[r["id"] for r in g] for g in groups_all]))
groups_real = find_duplicate_groups(real_only, thumb_of)
check("T2 过滤虚拟后 1 组 2 张真实", len(groups_real) == 1 and len(groups_real[0]) == 2,
      repr([[r["id"] for r in g] for g in groups_real]))
check("T2 组内只有真实记录", all(not r.get("is_virtual") for g in groups_real for r in g))
check("T2 组内不含虚拟 id",
      all(all(r["id"] != "vout:abc:def" for r in g) for g in groups_real))

# 虚拟记录 id 不在 store 中：store.remove 返回 None（清理时不应报错/静默失败）
store2._records = [r for r in store2._records if r["id"] != "real001"]
store2._storage.remove_record("vout:abc:def")   # 应无异常（行不存在）
check("T2 虚拟 id remove 无异常", True)

# ============ T3: 文件缺失标记 ============
print("[T3] 文件缺失标记（幽灵记录提示，不自动删）")
rec_missing = store2.add({"id": "miss001", "title": "缺失", "image_file": "no_such.jpg",
                          "thumb_file": "no_such.png"})
rec_ok = store2.add({"id": "ok001", "title": "正常", "thumb_file": "dup_real.png"})
gp = GalleryPanel(store2)
gp.reload()
app.processEvents()

pm = gp._tile_pixmap(rec_missing, 80)
check("T3 文件缺失 _tile_pixmap 不崩且非空", pm is not None and not pm.isNull())
marker = gp._missing_marker(rec_missing)
check("T3 缺失记录标记生效", "文件缺失" in marker, repr(marker))
check("T3 正常记录无标记", gp._missing_marker(rec_ok) == "")

# 标题带标记（网格 + 表格）
gp._view_mode = "grid"
gp._apply()
app.processEvents()
titles = [gp.gallery.item(i).text() for i in range(gp.gallery.count())]
miss_titles = [t for t in titles if "文件缺失" in t]
check("T3 网格标题带缺失标记", len(miss_titles) == 1, repr(miss_titles))
gp._view_mode = "table"
gp._apply()
app.processEvents()
tbl_titles = [gp.detail.item(r, 1).text() for r in range(gp.detail.rowCount())]
check("T3 表格标题带缺失标记", sum(1 for t in tbl_titles if "文件缺失" in t) == 1,
      repr(tbl_titles))

# 缺失记录仍保留在 store（不自动删除）
check("T3 不自动删除缺失记录", any(r["id"] == "miss001" for r in store2.records))

# ============ T4: i18n 新 key 四语一致 ============
print("[T4] i18n 新增 key 四语一致")
en_keys = set(i18n._LANG_TABLES["en"].keys())
es_keys = set(i18n._LANG_TABLES["es"].keys())
ja_keys = set(i18n._LANG_TABLES["ja"].keys())
check("T4 es key 集 == en", en_keys == es_keys)
check("T4 ja key 集 == en", en_keys == ja_keys)
check("T4 新 key 存在且非原文",
      i18n._LANG_TABLES["en"].get("文件缺失") == "File Missing"
      and i18n._LANG_TABLES["es"].get("文件缺失") == "Archivo faltante"
      and i18n._LANG_TABLES["ja"].get("文件缺失") == "ファイル欠落")
check("T4 扫描提示新 key 存在",
      i18n._LANG_TABLES["en"].get("正在后台扫描输出文件夹…")
      and i18n._LANG_TABLES["es"].get("正在后台扫描输出文件夹…")
      and i18n._LANG_TABLES["ja"].get("正在后台扫描输出文件夹…"))

i18n.init(td / "settings.json", "zh")

print()
print("v3.4 幽灵记录/查重排除虚拟/缺失标记", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
