"""v3.0 M3.1 批量操作 + 导出测试。"""
import json
import os
import sys
import tempfile
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '.')

from PySide6.QtWidgets import QApplication, QMessageBox, QAbstractItemView

QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

from app import i18n
from app.data_store import DataStore
from app.export_util import export_records
from app.ui.style import APP_QSS
from app.ui.main_window import MainWindow

app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)
td = Path(tempfile.mkdtemp())
store = DataStore(td / 'Library')
i18n.init(store.settings_path(), 'zh')
win = MainWindow(store)
win.resize(1200, 760)
win.show()
app.processEvents()

# 准备 3 条记录（含图片 + 视频）
for i in range(3):
    fn = f'img_{i}.png'
    (store.images_dir / fn).write_bytes(b'PNGDATA' * 100)
    store.add({'title': f'图{i}', 'positive': f'p{i}', 'models': [],
               'image_file': fn, 'thumb_file': '', 'group': ''})
# 视频记录
v = list(Path(r'C:\Users\Kemin\Downloads').glob('*.mp4'))[0]
res = store.add({'title': '视频1', 'positive': '', 'models': [],
                 'media_type': 'video', 'video_file': v.name,
                 'duration': 6.0, 'group': ''})
# 复制视频文件进 videos/
import shutil as _sh
_sh.copy2(str(v), str(store.videos_dir / v.name))

gp = win.gallery_panel
gp.reload()
app.processEvents()

# ---- T1: 多选 ----
gp.gallery.setSelectionMode(QAbstractItemView.ExtendedSelection)
for i in range(gp.gallery.count()):
    gp.gallery.item(i).setSelected(True)
app.processEvents()
sel = gp._selected_records()
print(f'T1 多选: 选中 {len(sel)} 条（共 {gp.gallery.count()}）')
assert len(sel) == gp.gallery.count() == 4
print('   ✓ 网格多选正常')

# ---- T2: 批量导出 ----
out = td / 'export_test'
n, err = export_records(store, sel, str(out))
print(f'T2 导出: n={n}, err={err!r}')
assert n == 4
assert (out / 'AI-Prompt-Vault-导出-*').exists() or any(
    p.name.startswith('AI-Prompt-Vault-导出') for p in out.iterdir())
exp_dir = next(p for p in out.iterdir() if p.name.startswith('AI-Prompt-Vault-导出'))
manifest = json.loads((exp_dir / 'prompts.json').read_text(encoding='utf-8'))
assert manifest['count'] == 4
assert (exp_dir / 'media' / 'img_0.png').exists()
assert (exp_dir / 'media' / v.name).exists()
print(f'   ✓ 导出 zip 结构完整（media/ + prompts.json {manifest["count"]} 条）')

# ---- T3: 批量删除 ----
gp._batch_delete(sel)
app.processEvents()
print(f'T3 批量删除: 剩余 {len(store.records)} 条')
assert len(store.records) == 0
assert list(store.trash_dir.glob('img_*.png')), '图片应进 trash'
print('   ✓ 批量删除（含 trash）')

# ---- T4: 批量改分组 ----
store.add_group('风景')
for i in range(2):
    store.add({'title': f'x{i}', 'positive': '', 'models': [], 'group': ''})
gp.reload()
app.processEvents()
# 批量改分组（store 层；UI 弹窗在离屏下无法交互，逻辑相同）
sel2 = store.records[:2]
for r in sel2:
    store.set_record_group(r['id'], '风景')
assert all(store.get(r['id'])['group'] == '风景' for r in sel2)
print('T4 批量改分组（store 层）✓')

print()
print('M3.1 批量操作 + 导出测试全部通过 ✓')