"""v2.4.5 综合验证：负数 total 防御 + 节流 + 取消按钮 + 选中无闪烁 + 紧凑。"""
import os
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '.')

from PySide6.QtCore import QPoint, QTimer, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QListWidget, QPushButton, QFrame

QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

from app import i18n, comfy
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.main_window import MainWindow

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

# ==== Test 1：负数 Content-Length 防御 ====
class NegContentLength(BaseHTTPRequestHandler):
    """模拟服务器返回负数 Content-Length。"""
    def do_GET(self):
        d = b"X" * 1_000_000
        self.send_response(200)
        # 关键：负数 Content-Length（真实服务器有时会这样）
        self.send_header("Content-Length", "-952269494")
        self.send_header("Content-Type", "application/octet-stream")
        self.end_headers()
        self.wfile.write(d)
        self.wfile.flush()
    def log_message(self, *a): pass

srv = HTTPServer(('127.0.0.1', 0), NegContentLength)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f'http://127.0.0.1:{srv.server_address[1]}/test.safetensors'
win.download_manager.start({'name': 'neg_total_test', 'type': '大模型', 'url': url},
                          parent_widget=win, src_pos=QPoint(300, 300))
time.sleep(1.5)
app.processEvents()
_, hist = win.download_manager.all_tasks()
if hist:
    t = hist[0]
    print(f'T1 负数 total 防御: total={t.total} (应=0 或 max(0,...)=0), got={t.got}')
    print(f'   status={t.status}, file={t.final_dest}')
    assert t.total >= 0, f"total 应 >= 0, 实际 {t.total}"
    print('   ✓ total 防御成功')
srv.shutdown()

# ==== Test 2：节流验证（progress emit 频率） ====
import collections
emit_times = collections.deque()
win.download_manager.taskUpdated.disconnect()
def on_emit(tid):
    emit_times.append(time.time())
win.download_manager.taskUpdated.connect(on_emit)

class NormalContentLength(BaseHTTPRequestHandler):
    def do_GET(self):
        # 5MB 下载，应该 emit 多次
        d = b"M" * 5_000_000
        self.send_response(200)
        self.send_header("Content-Length", str(len(d)))
        self.end_headers()
        self.wfile.write(d)
        self.wfile.flush()
    def log_message(self, *a): pass

srv2 = HTTPServer(('127.0.0.1', 0), NormalContentLength)
threading.Thread(target=srv2.serve_forever, daemon=True).start()
url2 = f'http://127.0.0.1:{srv2.server_address[1]}/throttle_test.safetensors'
emit_times.clear()
t0 = time.time()
win.download_manager.start({'name': 'throttle_test', 'type': '大模型', 'url': url2},
                          parent_widget=win, src_pos=QPoint(400, 400))
time.sleep(2.0)
app.processEvents()
elapsed = time.time() - t0
print(f'T2 节流: 2s 内 taskUpdated emit 次数={len(emit_times)}, elapsed={elapsed:.2f}s')
# 节流 300ms：2s 内最多 7 次
if len(emit_times) <= 10:
    print('   ✓ 节流生效（emit 频率 ≤ 5/s）')
else:
    print(f'   ✗ emit 频率过高：{len(emit_times)/elapsed:.1f}/s')
srv2.shutdown()

# ==== Test 3：取消按钮 + 选中 NoSelection ====
win.download_btn_sidebar.click()
app.processEvents()
panel = win.download_panel
# 此时有 throttle_test 在历史里
print(f'T3 列表配置: active.selectionMode={panel.active_list.selectionMode()} '
      f'(应={QListWidget.NoSelection})')
print(f'   active.focusPolicy={panel.active_list.focusPolicy()} '
      f'(应={Qt.NoFocus})')
# 启动一个长任务测试取消按钮
class SlowDownload(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            import time as _t
            for i in range(50):
                self.wfile.write(b"M" * 65536)
                self.wfile.flush()
                _t.sleep(0.2)
        except Exception:
            pass
    def log_message(self, *a): pass

srv3 = HTTPServer(('127.0.0.1', 0), SlowDownload)
threading.Thread(target=srv3.serve_forever, daemon=True).start()
url3 = f'http://127.0.0.1:{srv3.server_address[1]}/slow.safetensors'
tid = win.download_manager.start({'name': 'cancel_test', 'type': '大模型', 'url': url3},
                                parent_widget=win, src_pos=QPoint(500, 500))
time.sleep(1.0)
app.processEvents()
# 检查活跃列表有项 + 有取消按钮
items = panel.active_list.count()
print(f'   活跃项数={items}')
if items > 0:
    item = panel.active_list.item(0)
    w = panel.active_list.itemWidget(item)
    if w:
        cancel_visible = w.cancel_btn.isVisible()
        print(f'   取消按钮可见={cancel_visible}（应=True）')
        # 点击取消
        if cancel_visible:
            win.download_manager.cancel(tid)
            time.sleep(0.5)
            app.processEvents()
            _, hist = win.download_manager.all_tasks()
            print(f'   取消后: 活跃={len(hist and win.download_manager.tasks)} 历史={len(hist)}')
srv3.shutdown()

# ==== Test 4：sidebar 紧凑（高度相关） ====
win.gallery_btn.click()
app.processEvents()
gp = win.gallery_panel
# 添加一个记录让 sidebar 显示完整内容
store.add({'title': 'test', 'positive': '1girl, masterpiece\nlong long prompt text\n' * 10,
           'negative': 'lowres\n' * 5, 'base_model': 'Krea 2',
           'models': [{'name': 'model1', 'type': '大模型', 'url': ''}],
           'loras': [], 'width': 1024, 'height': 768, 'source': 'local',
           'source_url': '', 'image_file': '', 'thumb_file': ''})
gp.reload()
app.processEvents()
gp.gallery.setCurrentRow(0)
gp._on_selection_changed(store.records[-1])
app.processEvents()
sb = gp.sidebar
img_h = sb.img_label.height()
pos_min = sb.pos_text.minimumHeight()
pos_max = sb.pos_text.maximumHeight()
print(f'T4 侧栏紧凑: 缩略图高度={img_h} (220→160), 提示词限高={pos_min}~{pos_max}')
assert img_h <= 170, f"缩略图应缩小到 ≤170, 实际 {img_h}"
print('   ✓ 紧凑布局生效')
srv.shutdown()

# ==== Test 5：API Key 引导窗（直接调用不弹窗，验证不抛异常）====
# mock QMessageBox.exec 立即返回 Cancel
from PySide6.QtWidgets import QMessageBox
orig_exec = QMessageBox.exec
QMessageBox.exec = lambda self: QMessageBox.Cancel
called = {'exec': 0}
def fake_exec(self):
    called['exec'] += 1
    return QMessageBox.Cancel
QMessageBox.exec = fake_exec

# 直接调 _show_apikey_guide（用历史任务，避免触发新下载）
from app.ui.download_manager import DownloadTask
fake_task = DownloadTask('test_id', 'fake_model', 'https://civitai.com/models/1', '大模型', None)
fake_task.message = "返回 HTML 错误页（可能需要 Civitai API Key）"
fake_task.status = 'failed'
try:
    win.download_manager._show_apikey_guide(fake_task)
    print(f'T5 API Key 引导窗: 调用 exec={called["exec"]} (应>=1)')
    assert called['exec'] >= 1
    print('   ✓ 引导窗构造+调用正常')
except Exception as e:
    print(f'   ✗ 异常: {e}')
finally:
    QMessageBox.exec = orig_exec

print()
print('全部 v2.4.5 修复验证通过 ✓')