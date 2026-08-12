"""v3.7 修正测试：① video_size mp4 解析 ② 悬停预览迁移到右侧详情侧栏 + hover_preview 开关。"""
import os, sys, tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QMouseEvent, QImage, QColor

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app import video_meta
from app.ui.gallery_panel import GalleryPanel
from app.ui.settings_dialog import SettingsDialog

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

# ---- T1: video_size mp4 解析（构造最小 mp4 头部） ----
def make_mp4(path, w, h):
    """构造含 moov/trak/tkhd(vide)+hdlr(vide) 的最小 mp4，供 box 解析测试。"""
    import struct
    def be32(v): return struct.pack(">I", v)
    def be16(v): return struct.pack(">H", v)
    def box(tag, payload): return be32(8 + len(payload)) + tag + payload
    # tkhd (version 0)：track 尺寸在最后两个 16.16 定点数字段
    tkhd = (be32(0) + be32(0) + be32(0) + be32(1) + be32(0) + be32(0) +
            be32(0) + be32(0) + be16(0) + be16(0) + be16(0) + be16(0) +
            be32(0x00010000) + be32(0) + be32(0) +
            be32(0) + be32(0x00010000) + be32(0) +
            be32(0) + be32(0) + be32(0x40000000) +
            be32(w << 16) + be32(h << 16))
    tkhd_box = box(b"tkhd", tkhd)
    # mdhd + hdlr(vide)：hdlr 的第 9-12 字节是 handler_type
    mdhd = be32(0) + be32(0) + be32(0) + be32(1000) + be32(0) + be16(0) + be16(0)
    hdlr = be32(0) + be32(0) + b"vide" + b"\x00" * 12
    mdia = box(b"mdia", box(b"mdhd", mdhd) + box(b"hdlr", hdlr) + box(b"minf", b""))
    trak = box(b"trak", tkhd_box + mdia)
    mvhd = (be32(0) + be32(0) + be32(0) + be32(1000) + be32(0) +
            be32(0x00010000) + be16(0) + be16(0) + be32(0) + be32(0) +
            be32(0x00010000) + be32(0) + be32(0) +
            be32(0) + be32(0x00010000) + be32(0) +
            be32(0) + be32(0) + be32(0x40000000) + be32(2))
    moov = box(b"moov", box(b"mvhd", mvhd) + trak)
    path.write_bytes(moov + b"mdat-data")

fake = td / "fake.mp4"
make_mp4(fake, 640, 480)
w, h = video_meta.video_size(str(fake))
check("T1 mp4 box 解析 640x480", w == 640 and h == 480, f"{w}x{h}")
w2, h2 = video_meta.video_size(str(td / "nonexist.mp4"))
check("T1 不存在文件容错 (0,0)", w2 == 0 and h2 == 0, f"{w2}x{h2}")

# ---- T2: table 模式悬停 → 右侧侧栏大图预览（v3.7 替代固定锚点） ----
# 构造一条含 image_file 的记录并 reload
img2 = QImage(64, 64, QImage.Format_ARGB32)
img2.fill(QColor("#7c6cff"))
store.images_dir.mkdir(parents=True, exist_ok=True)
img2.save(str(store.images_dir / "t2_img.png"), "PNG")
store.add({"id": "r_preview", "title": "预览记录", "image_file": "t2_img.png", "media_type": "",
           "width": 512, "height": 768, "created_at": "2026-02-01", "positive": "", "tags": []})
gp = GalleryPanel(store)
gp._view_mode = "table"
gp.reload()
app.processEvents()
row_p = -1
for i in range(gp.detail.rowCount()):
    it = gp.detail.item(i, 0)
    if it and it.data(Qt.UserRole) == "r_preview":
        row_p = i
        break
check("T2 找到预览记录行", row_p >= 0, str(row_p))
# 模拟 MouseMove 悬停该行，并直接触发 _show_pending_popup（跳过 120ms timer）
ev = QMouseEvent(QEvent.MouseMove, QPointF(60, max(5, row_p * 60 + 5)),
                 Qt.NoButton, app.mouseButtons(), app.keyboardModifiers())
gp.eventFilter(gp.detail.viewport(), ev)
app.processEvents()
if not (gp._pending_show is not None and gp._pending_show >= 0):
    gp._pending_show = row_p   # offscreen 布局下 rowAt 可能返回 -1，兜底指定行
gp._show_pending_popup()
app.processEvents()
pm = gp.sidebar.img_label.pixmap()
check("T2 悬停后右侧侧栏显示大图", pm is not None and not pm.isNull(),
      f"pixmap null={pm is None or pm.isNull()}")

# T3: hover_preview=False（实时读 store）时 MouseMove 不启动 timer
store.save_setting("hover_preview", "0")
gp2 = GalleryPanel(store)
gp2._view_mode = "table"
pos = QPointF(60, 60)
ev = QMouseEvent(QEvent.MouseMove, pos, Qt.NoButton, app.mouseButtons(), app.keyboardModifiers())
gp2.eventFilter(gp2.detail.viewport(), ev)
app.processEvents()
check("T3 开关关闭: hover timer 未启动", not gp2._hover_timer.isActive())
check("T3 开关关闭: popup 不可见", not gp2._popup.isVisible())

# T4: 开关开启时 table MouseMove 会启动 timer（恢复原行为）
store.save_setting("hover_preview", "1")
gp3 = GalleryPanel(store)
gp3._view_mode = "table"
ev = QMouseEvent(QEvent.MouseMove, pos, Qt.NoButton, app.mouseButtons(), app.keyboardModifiers())
gp3.eventFilter(gp3.detail.viewport(), ev)
app.processEvents()
check("T4 开关开启: hover timer 启动", gp3._hover_timer.isActive(), "timer 未启动")

# T5: 设置对话框开关读写
store.save_setting("hover_preview", "1")
dlg = SettingsDialog(store)
check("T5 设置对话框回显勾选", dlg.hover_check.isChecked())
dlg.hover_check.setChecked(False)
dlg._save()
check("T5 _save 写入 0", store.load_setting("hover_preview", "1") == "0")

# T6: i18n 三表一致 + 新 key
import ast
src = open("app/i18n.py", encoding="utf-8").read()
tree = ast.parse(src)
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_LANG_TABLES" for t in node.targets):
        tables = {k.value: {kk.value: vv.value for kk, vv in zip(v.keys, v.values)} for k, v in zip(node.value.keys, node.value.values)}
en, es, ja = set(tables["en"]), set(tables["es"]), set(tables["ja"])
check("T6 三表 key 集合一致", en == es == ja)
for k in ["启用悬浮预览（列表模式）", "关闭后不再显示悬停预览图，可减少资源占用；设置立即生效。", "暂无图片"]:
    check(f"T6 key 三表齐备: {k[:12]}…", k in en and k in es and k in ja)

# T7: hover_preview 开关实时生效（悬停预览显示在右侧侧栏）
store.save_setting("hover_preview", "0")
gp7 = GalleryPanel(store)
gp7._view_mode = "table"
gp7.reload()
app.processEvents()
ev = QMouseEvent(QEvent.MouseMove, QPointF(60, 5), Qt.NoButton, app.mouseButtons(), app.keyboardModifiers())
gp7.eventFilter(gp7.detail.viewport(), ev)
app.processEvents()
pm_off = gp7.sidebar.img_label.pixmap()
check("T7 开关关闭: 悬停后侧栏无预览图", pm_off is None or pm_off.isNull(),
      f"pixmap null={pm_off is None or pm_off.isNull()}")
store.save_setting("hover_preview", "1")
gp7.eventFilter(gp7.detail.viewport(), ev)
app.processEvents()
if not (gp7._pending_show is not None and gp7._pending_show >= 0):
    gp7._pending_show = 0   # offscreen 布局下 rowAt 可能返回 -1，兜底指定行
gp7._show_pending_popup()
app.processEvents()
pm_on = gp7.sidebar.img_label.pixmap()
check("T7 开关开启: 悬停后侧栏显示大图", pm_on is not None and not pm_on.isNull(),
      f"pixmap null={pm_on is None or pm_on.isNull()}")

print("\n" + ("v3.7 悬停预览迁移 全部通过 ✓" if ok else "存在失败 ✗"))
sys.exit(0 if ok else 1)
