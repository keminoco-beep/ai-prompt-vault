"""v3.0 M3.3 图片重复检测测试。"""
import os
import sys
import tempfile
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '.')

from PySide6.QtWidgets import QApplication, QMessageBox

QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)

from app import i18n
from app.data_store import DataStore
from app.dupe_util import image_dhash, hamming, find_duplicate_groups
from app.ui.style import APP_QSS
from app.ui.main_window import MainWindow

app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)
td = Path(tempfile.mkdtemp())
store = DataStore(td / 'Library')
i18n.init(store.settings_path(), 'zh')
win = MainWindow(store)
win.show()
app.processEvents()

# 生成测试图：随机噪声（真实图片纹理近似）+ 真实图缩放
import random
from PySide6.QtGui import QImage, QColor

def make_noise(name, seed, w=200, h=200):
    rnd = random.Random(seed)
    img = QImage(w, h, QImage.Format_RGB32)
    for y in range(h):
        for x in range(w):
            img.setPixelColor(x, y, QColor(rnd.randint(0, 255), rnd.randint(0, 255), rnd.randint(0, 255)))
    p = store.thumbs_dir / name
    img.save(str(p), 'PNG')
    return p

p1 = make_noise('t1.png', 1)                    # 图 A
p2 = make_noise('t2.png', 1)                    # 同图 A（重复）
p3 = make_noise('t3.png', 2)                    # 图 B（不同）
p4 = store.thumbs_dir / 't4.png'
QImage(str(p1)).scaled(400, 400, __import__('PySide6.QtCore', fromlist=['Qt']).Qt.KeepAspectRatio).save(str(p4), 'PNG')  # 图 A 放大版

# 3 张蓝缩略图（同哈希）+ 1 张橙
store.add({'title': '蓝1', 'positive': '', 'models': [], 'thumb_file': 't1.png'})
store.add({'title': '蓝2', 'positive': '', 'models': [], 'thumb_file': 't2.png'})
store.add({'title': '蓝3', 'positive': '', 'models': [], 'thumb_file': 't4.png'})
store.add({'title': '橙', 'positive': '', 'models': [], 'thumb_file': 't3.png'})

# ---- T1: dHash 一致/不同 ----
h1, h2, h3, h4 = image_dhash(str(p1)), image_dhash(str(p2)), image_dhash(str(p3)), image_dhash(str(p4))
print(f'T1 dHash: 蓝1={h1[:12]}… 蓝2={h2[:12]}… 蓝3={h4[:12]}… 橙={h3[:12]}…')
assert h1 == h2 == h4, '同色图哈希应一致'
assert h1 != h3, '不同色图哈希应不同'
print('   ✓ 感知哈希（同图一致/异图不同）')

# ---- T2: find_duplicate_groups ----
gp = win.gallery_panel
groups = find_duplicate_groups(store.records,
                               lambda r: str(store.thumbs_dir / r['thumb_file']) if r.get('thumb_file') else '')
print(f'T2 重复组: {len(groups)} 组, 组大小={[len(g) for g in groups]}')
assert len(groups) == 1 and len(groups[0]) == 3, '应发现 1 组 3 张重复'
print('   ✓ 重复分组')

# ---- T3: hamming 距离 ----
assert hamming(h1, h1) == 0
assert hamming(h1, h3) > 0
print('T3 hamming 距离 ✓')

# ---- T4: UI 查重按钮存在 ----
btns = [b.text() for b in win.gallery_panel.findChildren(
    __import__('PySide6.QtWidgets', fromlist=['QPushButton']).QPushButton) if '查重' in b.text()]
assert btns, '应有查重按钮'
print('T4 查重按钮 ✓')

print()
print('M3.3 图片重复检测测试全部通过 ✓')