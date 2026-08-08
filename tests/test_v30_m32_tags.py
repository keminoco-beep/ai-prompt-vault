"""v3.0 M3.2 标签筛选测试。"""
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
from app.filters import unique_tags
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

# 记录（不同标签）
store.add({'title': 'a', 'positive': '', 'models': [], 'tags': ['风景', '夜景']})
store.add({'title': 'b', 'positive': '', 'models': [], 'tags': ['风景']})
store.add({'title': 'c', 'positive': '', 'models': [], 'tags': []})

gp = win.gallery_panel
gp.reload()
app.processEvents()

# ---- T1: unique_tags ----
tags = unique_tags(store.records)
print(f'T1 unique_tags: {tags}')
assert tags == ['风景', '夜景'], f"应收集全部标签: {tags}"
print('   ✓ 标签收集')

# ---- T2: 标签筛选下拉 ----
combo = gp.tag_combo
items = [combo.itemText(i) for i in range(combo.count())]
print(f'T2 标签下拉: {items}')
assert '全部标签' in items and '风景' in items and '夜景' in items

# ---- T3: 筛选逻辑 ----
combo.setCurrentText('风景')
app.processEvents()
assert len(gp._filtered()) == 2, '风景应匹配 2 条'
combo.setCurrentText('夜景')
app.processEvents()
assert len(gp._filtered()) == 1, '夜景应匹配 1 条'
combo.setCurrentText('全部标签')
app.processEvents()
assert len(gp._filtered()) == 3
print('T3 标签筛选（风景 2 / 夜景 1 / 全部 3）✓')

print()
print('M3.2 标签筛选测试全部通过 ✓')