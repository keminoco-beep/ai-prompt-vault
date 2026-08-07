"""v2.4.7 验证：增量刷新不打断点击 + 暂停后删除有效 + 按钮文案。"""
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '.')

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QApplication, QMessageBox

QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.main_window import MainWindow


class SlowRangeServer(BaseHTTPRequestHandler):
    """慢速下载服务器（支持 Range，便于测试暂停/删除）。"""
    DATA = bytes(range(256)) * 8192  # 2MB

    def do_GET(self):
        try:
            total = len(self.DATA)
            start = 0
            rng = self.headers.get('Range')
            if rng:
                try:
                    start = int(rng.split('=')[1].split('-')[0])
                except Exception:
                    start = 0
            if start > 0:
                self.send_response(206)
                self.send_header('Content-Range', f'bytes {start}-{total - 1}/{total}')
                body = self.DATA[start:]
            else:
                self.send_response(200)
                body = self.DATA
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            for i in range(0, len(body), 65536):
                self.wfile.write(body[i:i + 65536])
                self.wfile.flush()
                time.sleep(0.15)
        except Exception:
            pass

    def log_message(self, *a):
        pass


app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)
td = Path(tempfile.mkdtemp())
comfy_dir = td / 'ComfyUI'
(comfy_dir / 'models' / 'checkpoints').mkdir(parents=True)
store = DataStore(td / 'Library')
i18n.init(store.settings_path(), 'zh')
store.save_setting('comfyui_dir', str(comfy_dir))
win = MainWindow(store)
win.resize(1100, 720)
win.show()
app.processEvents()

srv = HTTPServer(('127.0.0.1', 0), SlowRangeServer)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f'http://127.0.0.1:{srv.server_address[1]}/m.safetensors'

# ==== T1：增量刷新不打断（item 复用，widget 不重建）====
tid = win.download_manager.start({'name': 'incr_test', 'type': '大模型', 'url': url},
                                 parent_widget=win, src_pos=QPoint(300, 300))
time.sleep(0.5)
app.processEvents()
win.download_btn_sidebar.click()
app.processEvents()
panel = win.download_panel
# 记录第一次 widget 引用
item0 = panel.active_list.item(0)
w0 = panel.active_list.itemWidget(item0)
time.sleep(0.8)  # 多次刷新（节流 300ms → 至少 2 次 taskUpdated）
app.processEvents()
item0b = panel.active_list.item(0)
w0b = panel.active_list.itemWidget(item0b)
same_widget = (w0 is w0b)
print(f'T1 增量刷新: item 数={panel.active_list.count()}, widget 复用={same_widget}')
assert same_widget, "刷新后 widget 应复用（不重建）"
print('   ✓ 列表不再整体重建，点击/选中不会被中断')
assert w0b.cancel_btn.text() == '删除'
print(f'   ✓ 按钮文案: {w0b.cancel_btn.text()}')

# ==== T2：暂停后点删除有效 ====
win.download_manager.pause(tid)
time.sleep(0.8)
app.processEvents()
t = win.download_manager.tasks.get(tid)
part = comfy_dir / 'models' / 'checkpoints' / 'incr_test.safetensors.part'
print(f'T2 暂停: status={t.status if t else None}, part={part.exists()}')
assert t and t.status == 'paused', "应先暂停"
assert part.exists(), ".part 应存在"

# 暂停状态下删除
win.download_manager.cancel(tid)
time.sleep(0.3)
app.processEvents()
t = win.download_manager.tasks.get(tid)
print(f'T2 删除: tasks 中={t is not None}, part 存在={part.exists()}, 历史={len(win.download_manager.history)}')
assert t is None, "删除后任务应移出活动列表"
assert not part.exists(), "删除后 .part 应被清理"
assert any(h.id == tid for h in win.download_manager.history), "应进入历史"
print('   ✓ 暂停后删除有效（.part 清理 + 移入历史）')

# ==== T3：暂停按钮 → 继续按钮 文案切换 ====
# 再下载一个，暂停，检查按钮变"继续"
tid2 = win.download_manager.start({'name': 'pause_btn', 'type': '大模型', 'url': url},
                                  parent_widget=win, src_pos=QPoint(400, 400))
time.sleep(0.6)
app.processEvents()
panel._refresh_all()
app.processEvents()
# 找到该任务的 widget
w2 = None
for i in range(panel.active_list.count()):
    item = panel.active_list.item(i)
    if item.data(Qt.UserRole) == tid2:
        w2 = panel.active_list.itemWidget(item)
        break
win.download_manager.pause(tid2)
time.sleep(0.8)
app.processEvents()
print(f'T3 暂停按钮: 暂停后按钮文案={w2.pause_btn.text() if w2 else None} (应=继续)')
assert w2 and w2.pause_btn.text() == '继续', "暂停后按钮应变'继续'"
# 恢复
win.download_manager.resume(tid2)
time.sleep(0.3)
app.processEvents()
panel._refresh_all()
app.processEvents()
print(f'T3 恢复按钮: 恢复后按钮文案={w2.pause_btn.text() if w2 else None} (应=暂停)')
assert w2 and w2.pause_btn.text() == '暂停'
print('   ✓ 暂停/继续按钮文案正确切换')

# 清理
win.download_manager.cancel(tid2)
time.sleep(0.3)
app.processEvents()
srv.shutdown()
print()
print('全部 v2.4.7 验证通过 ✓')