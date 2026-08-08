"""v3.0 M2.2 并发限制测试：下载队列 ≤3 + 导入线程池 ≤2。"""
import os
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
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
store = DataStore(td / 'Library')
i18n.init(store.settings_path(), 'zh')
store.save_setting('comfyui_dir', str(comfy))
win = MainWindow(store)
win.show()
app.processEvents()


class Slow(BaseHTTPRequestHandler):
    """慢速下载服务器：每 64KB sleep 0.4s，共 2MB。"""
    def do_GET(self):
        try:
            body = b"S" * 1_000_000
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            for i in range(0, len(body), 65536):
                self.wfile.write(body[i:i + 65536])
                self.wfile.flush()
                time.sleep(0.1)
        except Exception:
            pass
    def log_message(self, *a): pass

srv = ThreadingHTTPServer(('127.0.0.1', 0), Slow)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{srv.server_address[1]}/'

# ---- T1: 一次加入 5 个下载 → 最多 3 个并发 ----
for i in range(5):
    win.download_manager.start({'name': f'm{i}', 'type': '大模型', 'url': base},
                               parent_widget=win)
app.processEvents()

def running():
    return sum(1 for t in win.download_manager.tasks.values()
               if t.status == 'downloading')
def pending():
    return sum(1 for t in win.download_manager.tasks.values()
               if t.status == 'pending')

app.processEvents()
r, p = running(), pending()
print(f'T1 并发: running={r} (应<=3), pending={p} (应>=2)')
assert r <= 3, f"并发下载应 ≤3, 实际 {r}"
assert p >= 2, f"应有等待任务, 实际 {p}"
print('   ✓ 下载队列并发上限 3')

# 等第一批完成，验证队列推进
time.sleep(2)
app.processEvents()
r = running()
print(f'   5s 后 running={r} (等待任务应被启动)')
# 全部完成（5 个 × 约 8s）——等足够久
time.sleep(15)
app.processEvents()
done = sum(1 for t in win.download_manager.history if t.status == 'done')
print(f'   最终完成 {done}/5')
for t in win.download_manager.history:
    print(f'   {t.name}: {t.status} msg={t.message[:50]}')
for tid, t in win.download_manager.tasks.items():
    print(f'   活动 {t.name}: {t.status} msg={t.message[:50]}')
assert done == 5, f'5 个任务应全部完成, 实际 {done}'
print('   ✓ 队列按序推进，全部完成')
srv.shutdown()

# ---- T2: 导入线程池 max=2 ----
from PySide6.QtCore import QThreadPool
pool = win.collect_panel.pool
print(f'T2 导入线程池 maxThreadCount={pool.maxThreadCount()} (应=2)')
assert pool.maxThreadCount() == 2
print('   ✓ 导入并发上限 2')

print()
print('M2.2 并发限制测试全部通过 ✓')