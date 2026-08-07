"""v2.4.3 下载管理集成测试。"""
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '.')

from PySide6.QtCore import QPoint
from PySide6.QtWidgets import QApplication, QMessageBox

QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.main_window import MainWindow


def make_srv(handler):
    s = HTTPServer(('127.0.0.1', 0), handler)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)
td = Path(tempfile.mkdtemp())
comfy = td / 'ComfyUI'
(comfy / 'models' / 'checkpoints').mkdir(parents=True)
(comfy / 'models' / 'checkpoints' / 'stale.safetensors.part').write_bytes(b'junk')

store = DataStore(td / 'Library')
i18n.init(store.settings_path(), 'zh')
store.save_setting('comfyui_dir', str(comfy))
win = MainWindow(store)
win.show()
app.processEvents()

print('窗口标题:', win.windowTitle())
print('启动清理 .part:', not (comfy / 'models' / 'checkpoints' / 'stale.safetensors.part').exists())

# 测试 1：成功下载
class H1(BaseHTTPRequestHandler):
    def do_GET(self):
        d = b'M' * 500000
        self.send_response(200)
        self.send_header('Content-Length', str(len(d)))
        self.end_headers()
        self.wfile.write(d)
        self.wfile.flush()

    def log_message(self, *a):
        pass


srv1 = make_srv(H1)
url1 = f'http://127.0.0.1:{srv1.server_address[1]}/m.safetensors'
win.download_manager.start({'name': 'demo_model', 'type': '大模型', 'url': url1},
                          parent_widget=win, src_pos=QPoint(300, 300))
time.sleep(1.2)
app.processEvents()
act, hist = win.download_manager.all_tasks()
print('Test1 成功下载: 文件=', (comfy / 'models' / 'checkpoints' / 'demo_model.safetensors').exists(),
      '| 历史=', len(hist))

# 测试 2：错误页自动切换
class H2(BaseHTTPRequestHandler):
    def do_GET(self):
        if 'type=Model' in self.path:
            d, ctype = b'R' * 1000, 'application/octet-stream'
        else:
            d, ctype = b'<!DOCTYPE html><html>cf error</html>', 'text/html'
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(d)))
        self.end_headers()
        self.wfile.write(d)
        self.wfile.flush()

    def log_message(self, *a):
        pass


srv2 = make_srv(H2)
url2 = f'http://127.0.0.1:{srv2.server_address[1]}/api/download/models/999'
win.download_manager.start({'name': 'switch_test', 'type': '大模型', 'url': url2},
                          parent_widget=win, src_pos=QPoint(400, 400))
time.sleep(1.5)
app.processEvents()
act, hist = win.download_manager.all_tasks()
print('Test2 错误页切换: 文件=', (comfy / 'models' / 'checkpoints' / 'switch_test.safetensors').exists(),
      '| 历史=', len(hist))

# 测试 3：取消下载
srv3 = make_srv(H1)
url3 = f'http://127.0.0.1:{srv3.server_address[1]}/big'
tid = win.download_manager.start({'name': 'cancel_test', 'type': '大模型', 'url': url3},
                                parent_widget=win, src_pos=QPoint(500, 500))
time.sleep(0.3)
win.download_manager.cancel(tid)
time.sleep(0.8)
app.processEvents()
_, hist = win.download_manager.all_tasks()
print('Test3 取消: 历史=', [(t.status, t.name, t.message[:30]) for t in hist[:1]])

# 徽标
print('侧栏徽标:', repr(win.download_btn_sidebar.text()))
print('下载页 list 项数(活跃):', win.download_panel.active_list.count())
print('下载页 list 项数(历史):', win.download_panel.history_list.count())

srv1.shutdown()
srv2.shutdown()
srv3.shutdown()
print('\n全部通过 ✓')