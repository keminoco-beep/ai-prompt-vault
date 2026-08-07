"""v2.4.10 视觉排查：截各页面查按钮/标签截断。"""
import os
import sys
import tempfile
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '.')

from PySide6.QtCore import Qt, QPoint
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
(comfy / 'models' / 'loras').mkdir(parents=True)
(comfy / 'models' / 'checkpoints' / 'realvisxlV40.safetensors').write_bytes(b'x' * 2000000)
(comfy / 'models' / 'loras' / 'detail_slider.safetensors').write_bytes(b'y' * 1000000)
(comfy / 'models' / 'loras' / 'breast_slider.safetensors').write_bytes(b'y' * 1000000)
(comfy / 'models' / 'loras' / 'krea2_textusion.safetensors').write_bytes(b'y' * 1000000)
(comfy / 'models' / 'loras' / 'long_loooong_name_for_test.safetensors').write_bytes(b'z' * 1000000)
store = DataStore(td / 'Library')
i18n.init(store.settings_path(), 'zh')
store.save_setting('comfyui_dir', str(comfy))
win = MainWindow(store)
win.resize(1400, 820)
win.show()
app.processEvents()

shots = Path('tests/shots')
shots.mkdir(exist_ok=True)
win.grab().save(str(shots / 'v2410_main.png'))
print('保存主窗口')

# 各页面
for label, btn in [
    ('collect', win.collect_btn),
    ('gallery', win.gallery_btn),
    ('model', win.model_btn),
    ('download', win.download_btn_sidebar),
]:
    btn.click()
    app.processEvents()
    win.grab().save(str(shots / f'v2410_{label}.png'))
    print(f'保存 {label}')

# 详情面板：在 gallery 选一张（带多种模型）
win.gallery_btn.click()
app.processEvents()
gp = win.gallery_panel
# 加一条带多模型的记录
store.add({
    'title': 'A dramatic fantasy illustration',
    'positive': '1girl, masterpiece, detailed eyes, long silver hair, ' * 5,
    'negative': 'lowres, blurry' * 5,
    'base_model': 'Krea 2',
    'models': [
        {'name': 'RealvisxlV40 + Krea 2', 'type': '大模型', 'url': 'https://civitai.com/models/1'},
        {'name': 'Krea 2 Turbo Official Comfy-Org Checkpoints (Krea2)', 'type': '大模型', 'url': 'https://civitai.com/models/2'},
        {'name': 'Krea2FilterBypass', 'type': 'LoRA', 'url': ''},
        {'name': '[KREA 2] Detail Slider', 'type': 'LoRA', 'url': ''},
        {'name': '[KREA 2] Breast Slider', 'type': 'LoRA', 'url': ''},
        {'name': 'Krea 2 NSFW V4', 'type': 'LoRA', 'url': ''},
        {'name': 'Krea2-realism-V1 | V2', 'type': 'LoRA', 'url': ''},
        {'name': 'Krea2_TextFusion_Refusal-Reduction LoRA', 'type': 'LoRA', 'url': ''},
        {'name': 'BeMyHero - NalaX', 'type': 'LoRA', 'url': ''},
    ],
    'loras': [],
    'width': 1344, 'height': 768,
    'source': 'civitai', 'source_url': 'https://civitai.com/images/1',
    'image_file': '', 'thumb_file': '',
})
gp.reload()
app.processEvents()
gp.gallery.setCurrentRow(0)
gp._on_selection_changed(store.records[-1])
app.processEvents()
win.grab().save(str(shots / 'v2410_gallery_with_detail.png'))
print('保存 gallery + detail')

# 下载列表页 + 一个正在下载任务（模拟）
win.download_btn_sidebar.click()
app.processEvents()
# 触发一个下载用于显示
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        for i in range(50):
            self.wfile.write(b'M' * 65536); self.wfile.flush(); time.sleep(0.3)
    def log_message(self, *a): pass
srv = HTTPServer(('127.0.0.1', 0), H); threading.Thread(target=srv.serve_forever, daemon=True).start()
import time as _t
win.download_manager.start({'name': 'Krea 2 Turbo Official Comfy-Org Checkpoints (Krea2)', 'type': '大模型',
                           'url': f'http://127.0.0.1:{srv.server_address[1]}/m.safetensors'},
                          parent_widget=win, src_pos=QPoint(400, 400))
_t.sleep(2)
app.processEvents()
win.grab().save(str(shots / 'v2410_download.png'))
print('保存 download with active task')

# 设置页
from app.ui.settings_dialog import SettingsDialog
dlg = SettingsDialog(store, win)
dlg.show()
app.processEvents()
dlg.grab().save(str(shots / 'v2410_settings.png'))
dlg.close()

# 模型管理
win.model_btn.click()
app.processEvents()
mp = win.model_panel
mp.reload()
app.processEvents()
# 选第一个
mp.tree.setCurrentItem(mp.tree.topLevelItem(0))
app.processEvents()
win.grab().save(str(shots / 'v2410_model_panel.png'))
print('保存 model panel')

print('\n截图保存完成')
srv.shutdown()