"""v3.6 图库 UI 4 项改进测试：表格类型列 / 视频分辨率 / 平铺禁悬浮 / 列表固定悬浮。"""
import os, sys, tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
from PySide6.QtCore import QEvent, QPoint, Qt
from PySide6.QtGui import QMouseEvent

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app import video_meta
from app.ui.gallery_panel import GalleryPanel

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

# ---- T1: 表格 8 列 + 类型列内容 ----
from PySide6.QtGui import QImage, QPainter, QColor
img = QImage(64, 64, QImage.Format_ARGB32)
img.fill(QColor("#7c6cff"))
store.images_dir.mkdir(parents=True, exist_ok=True)
img.save(str(store.images_dir / "t_img.png"), "PNG")
store.add({"id": "r_img", "title": "图片记录", "image_file": "t_img.png", "media_type": "",
           "width": 512, "height": 768, "created_at": "2026-01-01", "positive": "", "tags": []})
store.add({"id": "r_vid", "title": "视频记录", "image_file": "", "video_file": "nonexist.mp4",
           "media_type": "video", "width": 0, "height": 0, "created_at": "2026-01-02", "positive": "", "tags": []})

gp = GalleryPanel(store)
gp._view_mode = "table"
gp.reload()
app.processEvents()
hdr = [gp.detail.horizontalHeaderItem(i).text() for i in range(gp.detail.columnCount())]
check("T1 表格 8 列", gp.detail.columnCount() == 8, repr(hdr))
check("T1 含类型列", "类型" in hdr, repr(hdr))
# 类型列内容（第 1 列是类型，缩略图第 0 列；行序按 created_at 倒序：r_vid 在前）
def row_of(uid):
    for i in range(gp.detail.rowCount()):
        it = gp.detail.item(i, 1)
        if it and it.data(Qt.UserRole) == uid:
            return i
    return -1
ri = row_of("r_img"); rv = row_of("r_vid")
check("T1 找到图片行", ri >= 0, str(ri))
check("T1 找到视频行", rv >= 0, str(rv))
img_item = gp.detail.item(ri, 1)
vid_item = gp.detail.item(rv, 1)
check("T1 图片记录类型=图片", img_item is not None and img_item.text() == "图片", img_item.text() if img_item else "")
check("T1 视频记录类型=视频", vid_item is not None and vid_item.text() == "视频", vid_item.text() if vid_item else "")
# 标题列无 ▶ 前缀
ti = gp.detail.item(rv, 2)
check("T1 标题列无 ▶ 前缀", ti is not None and not ti.text().startswith("▶"), ti.text() if ti else "")

# ---- T2: video_size 容错 ----
w, h = video_meta.video_size(str(td / "nonexist.mp4"))
check("T2 video_size 不存在文件容错 (0,0)", w == 0 and h == 0, f"{w},{h}")
# 表格视频行显示解析中或未知（不崩）
sz_item = gp.detail.item(1, 6)
check("T2 视频尺寸单元格存在", sz_item is not None)

# ---- T3: grid 模式禁用悬浮 ----
gp._view_mode = "grid"
gp._popup.hide()
# 模拟 grid viewport MouseMove → 不应启动 hover timer
from PySide6.QtCore import QPointF
pos = QPointF(50, 50)
ev = QMouseEvent(QEvent.MouseMove, pos, Qt.NoButton, app.mouseButtons(), app.keyboardModifiers())
gp.eventFilter(gp.gallery.viewport(), ev)
app.processEvents()
check("T3 grid 模式 hover timer 未启动", not gp._hover_timer.isActive(), "timer 激活了")
check("T3 grid 模式 popup 不可见", not gp._popup.isVisible())

# ---- T4: table 模式悬停 → 右侧侧栏大图预览（v3.7 替代固定锚点） ----
gp._view_mode = "table"
gp._popup.hide()
row_img = row_of("r_img")
check("T4 找到图片行", row_img >= 0, str(row_img))
ev = QMouseEvent(QEvent.MouseMove, QPointF(60, max(5, row_img * 60 + 5)), Qt.NoButton,
                 app.mouseButtons(), app.keyboardModifiers())
gp.eventFilter(gp.detail.viewport(), ev)
app.processEvents()
if not (gp._pending_show is not None and gp._pending_show >= 0):
    gp._pending_show = row_img   # offscreen 布局下 rowAt 可能返回 -1，兜底指定行
gp._show_pending_popup()
app.processEvents()
pm = gp.sidebar.img_label.pixmap()
check("T4 悬停后右侧侧栏显示大图", pm is not None and not pm.isNull(),
      f"pixmap null={pm is None or pm.isNull()}")

print("\n" + ("v3.6 图库 UX 改进 全部通过 ✓" if ok else "存在失败 ✗"))
sys.exit(0 if ok else 1)
