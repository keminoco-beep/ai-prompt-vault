"""v3.0 M1 视频支持测试：数据层 + 导入链路 + 首帧提取。"""
import os
import shutil
import sys
import tempfile
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '.')

from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

from app import i18n
from app.data_store import DataStore, normalize_record
from app.workers import import_local_video
from app.video_meta import is_video_path, video_duration, extract_first_frame

td = Path(tempfile.mkdtemp())
store = DataStore(td / 'Library')
i18n.init(store.settings_path(), 'zh')

# 找一个真实视频做测试
cands = list(Path(r'C:\Users\Kemin\Downloads').glob('*.mp4'))
assert cands, '需要真实 mp4 测试'
v = cands[0]
print(f'测试视频: {v.name} ({v.stat().st_size/1e6:.1f} MB)')

# ---- T1: is_video_path ----
assert is_video_path(v), 'mp4 应被识别'
assert not is_video_path(__file__), 'py 不应被识别'
print('T1 is_video_path ✓')

# ---- T2: 视频导入全链路 ----
res = import_local_video(store, str(v))
print(f'T2 导入: {res}')
assert res['video_file'], f'导入失败: {res}'
video_rel = res['video_file']
assert (store.videos_dir / video_rel).exists(), '视频文件应在 videos/'
print('   ✓ 视频复制到 videos/')
if res['thumb_file']:
    assert (store.thumbs_dir / res['thumb_file']).exists(), '缩略图应存在'
    print(f"   ✓ 首帧缩略图生成 ({res['thumb_file']})")
if res['duration']:
    print(f"   ✓ 时长 {res['duration']:.2f}s")
else:
    print('   (时长未提取，可接受)')

# ---- T3: 记录保存 + normalize 兼容 ----
rec = store.add({
    'title': 'test video', 'positive': '', 'negative': '',
    'media_type': 'video', 'video_file': video_rel,
    'thumb_file': res.get('thumb_file') or '',
    'base_model': '其他', 'models': [], 'loras': [],
    'source': 'local', 'source_url': '',
})
assert rec['media_type'] == 'video'
assert rec['video_file'] == video_rel
# 旧记录兼容
old = normalize_record({'title': 'img', 'positive': 'p'})
assert old['media_type'] == 'image'
assert old['video_file'] == ''
print('T3 记录字段 + 旧数据兼容 ✓')

# ---- T4: 删除视频进 trash ----
store.remove(rec['id'])
assert not (store.videos_dir / video_rel).exists(), '视频应移出 videos/'
trash_files = list(store.trash_dir.glob('*.mp4'))
assert trash_files, '视频应进入 trash/'
print(f'T4 删除视频进 trash ✓ ({trash_files[0].name})')

# ---- T5: video_meta 独立模块 ----
d = video_duration(str(v))
assert d > 0, f'时长应 > 0, 实际 {d}'
out = td / 'frame.png'
assert extract_first_frame(str(v), out)
from PySide6.QtGui import QPixmap
pm = QPixmap(str(out))
assert pm.width() > 0
print(f'T5 video_meta 独立模块 ✓ (时长 {d:.2f}s, 首帧 {pm.width()}x{pm.height()})')

print()
print('M1 数据层 + 导入链路测试全部通过 ✓')