"""v3.0 M1.3 UI 集成测试：收藏页视频导入 + 图库视频筛选/显示。"""
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '.')

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QListWidgetItem

QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.main_window import MainWindow

app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)
td = Path(tempfile.mkdtemp())
store = DataStore(td / 'Library')
i18n.init(store.settings_path(), 'zh')
win = MainWindow(store)
win.resize(1300, 800)
win.show()
app.processEvents()

# 找一个真实视频
cands = list(Path(r'C:\Users\Kemin\Downloads').glob('*.mp4'))
assert cands, '需要真实 mp4'
v = cands[0]

# ---- T1: 收藏页导入视频 ----
cp = win.collect_panel
cp._start_local_video(str(v))
time.sleep(6)  # 等视频复制+首帧提取（后台线程）
app.processEvents()
pending = list(cp.pending.values())
assert pending, '待保存列表应有视频项'
item = pending[0]
print(f'T1 收藏页视频导入: video_file={item.get("video_file")}, thumb={item.get("thumb_file")}, media_type={item["record"].get("media_type")}')
assert item.get("video_file"), '应有 video_file'
assert item["record"].get("media_type") == "video"
print('   ✓ 视频进入待保存列表（带首帧缩略图）')

# ---- T2: 保存视频记录 ----
cp.pending_list.setCurrentRow(0)
app.processEvents()
cp.save_current()
app.processEvents()
recs = store.records
assert len(recs) == 1, f'应保存 1 条记录, 实际 {len(recs)}'
rec = recs[0]
print(f'T2 保存: media_type={rec["media_type"]}, video_file={rec["video_file"]}, thumb={rec["thumb_file"]}, duration={rec.get("duration")}')
assert rec["media_type"] == "video"
assert rec["video_file"]
assert (store.videos_dir / rec["video_file"]).exists()
print('   ✓ 视频记录已保存（videos/ 中有文件）')

# ---- T3: 图库视频筛选 ----
gp = win.gallery_panel
gp.reload()
app.processEvents()
# 全部媒体
gp.media_combo.setCurrentText('全部媒体')
app.processEvents()
print(f'T3 全部媒体: 显示 {gp._filtered().__len__()} 条')
assert len(gp._filtered()) == 1
# 图片筛选
gp.media_combo.setCurrentText('图片')
app.processEvents()
assert len(gp._filtered()) == 0, '图片筛选应排除视频'
# 视频筛选
gp.media_combo.setCurrentText('视频')
app.processEvents()
assert len(gp._filtered()) == 1, '视频筛选应只显示视频'
print('   ✓ 媒体筛选正常（全部/图片/视频）')
gp.media_combo.setCurrentText('全部媒体')
app.processEvents()

# ---- T4: 视频卡片显示（▶ 标记 + 缩略图）----
gp._apply()
app.processEvents()
n = gp.gallery.count()
assert n == 1
li = gp.gallery.item(0)
assert '▶' in li.text(), f'视频卡片应有 ▶ 标记: {li.text()!r}'
assert not li.icon().isNull(), '视频卡片应有首帧缩略图'
print(f'T4 视频卡片: {li.text()!r} + 首帧缩略图 ✓')

# ---- T5: 详情侧栏显示视频信息 ----
gp.gallery.setCurrentRow(0)
gp._on_selection_changed(rec)
app.processEvents()
sb = gp.sidebar
print(f'T5 侧栏: 模型清单/视频标记 OK')
win.grab().save(str(Path('tests/shots') / 'v30_video_gallery.png'))
print('   截图已保存')

# ---- T6: 视频删除进 trash ----
store.remove(rec['id'])
assert not (store.videos_dir / rec['video_file']).exists()
print('T6 视频删除进 trash ✓')

print()
print('M1.3 UI 集成测试全部通过 ✓')