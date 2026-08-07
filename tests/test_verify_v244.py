"""v2.4.4 修复验证：截图模型管理树 + 验证飞行动画 + 验证下载列表按钮唯一。"""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '.')

from PySide6.QtCore import QPoint, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.main_window import MainWindow

app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)
td = Path(tempfile.mkdtemp())
comfy = td / 'ComfyUI'
(comfy / 'models' / 'checkpoints').mkdir(parents=True)
(comfy / 'models' / 'loras').mkdir(parents=True)
(comfy / 'models' / 'checkpoints' / 'test_model.safetensors').write_bytes(b'x')
(comfy / 'models' / 'loras' / 'lora1.safetensors').write_bytes(b'y')

store = DataStore(td / 'Library')
i18n.init(store.settings_path(), 'zh')
store.save_setting('comfyui_dir', str(comfy))
win = MainWindow(store)
win.resize(1100, 720)
win.show()
app.processEvents()

# 1. 下载列表按钮唯一性（去掉导航里的，只留侧栏一个）
from PySide6.QtWidgets import QPushButton
btns = [b for b in win.findChildren(QPushButton) if '下载列表' in b.text()]
print('下载列表按钮数量:', len(btns), '| 文本:', [b.text() for b in btns])

# 2. 模型管理树截图（验证箭头）
win.model_btn.click()
app.processEvents()
mp = win.model_panel
mp.reload()
app.processEvents()
time.sleep(0.3)
app.processEvents()
shots = Path('tests/shots')
shots.mkdir(exist_ok=True)
# 树 widget 截图
pix = mp.tree.grab()
ok = pix.save(str(shots / 'v243_model_tree.png'))
print('模型树截图:', ok, '尺寸:', pix.width(), 'x', pix.height())

# 3. 飞行动画验证：触发 fly，检查 label 位置随时间变化
win.gallery_btn.click()
app.processEvents()
from PySide6.QtCore import QPoint as QP
# 模拟右键触发（调用 manager.start → flyRequested）
win.download_manager.flyRequested.emit(500, 400)
app.processEvents()
time.sleep(0.15)
app.processEvents()
anims = getattr(win, '_fly_anims', [])
print('动画对象持有:', len(anims), '| 动画运行中:', sum(1 for a in anims if a.state() == 1))
time.sleep(0.8)
app.processEvents()
anims = getattr(win, '_fly_anims', [])
print('动画结束后持有:', len(anims))

# 4. 下载页导航（无 nav 按钮，只侧栏按钮可用）
win.download_btn_sidebar.click()
app.processEvents()
print('下载页当前页:', win.stack.currentIndex(), '== 3:', win.stack.currentIndex() == 3)

win.grab().save(str(shots / 'v243_main_win.png'))
print('主窗口截图已保存')
print('完成')