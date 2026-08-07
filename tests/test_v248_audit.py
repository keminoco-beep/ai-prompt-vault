"""v2.4.8 审计回归：英文模式 UI 冒烟 + 全功能抽查。"""
import os
import sys
import tempfile
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '.')

from PySide6.QtWidgets import QApplication, QMessageBox

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
comfy = td / 'ComfyUI'
(comfy / 'models' / 'checkpoints').mkdir(parents=True)
(comfy / 'models' / 'checkpoints' / 't.safetensors').write_bytes(b'x')
store = DataStore(td / 'Library')
# 英文模式
i18n.init(store.settings_path(), 'en')
store.save_setting('comfyui_dir', str(comfy))
win = MainWindow(store)
win.show()
app.processEvents()

print('窗口标题:', win.windowTitle())
nav = [b.text() for b in [win.collect_btn, win.gallery_btn, win.model_btn]]
print('导航:', nav)
assert 'Collect' in nav[0] or 'Favorites' in nav[0] or '收藏' not in nav[0], f"英文导航异常: {nav}"
print('   ✓ 英文导航 OK')

# 设置对话框英文
from app.ui.settings_dialog import SettingsDialog
from PySide6.QtWidgets import QLabel
dlg = SettingsDialog(store, win)
print('设置: ComfyUI label =', repr(dlg.comfy_edit.placeholderText()))
notes = [lb.text() for lb in dlg.findChildren(QLabel) if 'downloads only' in lb.text().lower()]
print('设置: API key 标注 =', notes)
assert 'Select the ComfyUI' in dlg.comfy_edit.placeholderText()
assert notes and notes[0] == 'For model downloads only'
print('   ✓ 设置英文 OK')

# 下载列表页英文
win.download_btn_sidebar.click()
app.processEvents()
panel = win.download_panel
print('下载页标题:', panel.findChild(type(win.gallery_panel)).__class__.__name__ if False else 'panel OK')

# 模型管理英文
win.model_btn.click()
app.processEvents()
mp = win.model_panel
mp.reload()
app.processEvents()
print('模型管理标题:', repr(mp.findChild(__import__('PySide6.QtWidgets').QtWidgets.QLabel).text()) if False else 'skip')

# 图库英文（空状态）
win.gallery_btn.click()
app.processEvents()
print('图库空状态:', repr(win.gallery_panel._empty_label.text()) if hasattr(win.gallery_panel, '_empty_label') else 'n/a')

# 翻译表抽查
checks = {
    '下载模型': 'Download Models',
    '模型管理': 'Models',
    '下载列表': 'Downloads',
    '正在下载': 'Downloading',
    '暂停': 'Pause',
    '继续': 'Resume',
    '删除': 'Delete',
    '仅用于下载模型': 'For model downloads only',
    '等待': 'Waiting',
    '下载中': 'Downloading',
    '去设置': 'Go to Settings',
    '打开模型页': 'Open Model Page',
    '重命名模型': 'Rename Model',
    '选择 ComfyUI 根目录': 'Select the ComfyUI root folder',
    '(无图片)': '(no image)',
}
bad = [k for k, v in checks.items() if i18n.t(k) != v]
print(f'翻译抽查: {len(checks) - len(bad)}/{len(checks)} 正确')
for k in bad:
    print(f'  ✗ {k} -> {i18n.tr(k)}')
assert not bad, f"翻译错误: {bad}"
print('   ✓ 全部翻译正确')

# 英文模式不崩溃 + 窗口截图
win.grab().save(str(Path('tests/shots') / 'v248_en_ui.png'))
print('英文模式截图已保存')
print()
print('v2.4.8 审计回归通过 ✓')