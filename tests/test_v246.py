"""v2.4.6 验证：暂停/继续（断点续传）+ 空白窗口不轰炸 + 超长文件名 elide。"""
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

from app import i18n, comfy
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.main_window import MainWindow


class RangeServer(BaseHTTPRequestHandler):
    """支持 Range 的下载服务器（每 64KB 分片，稍慢便于测试暂停）。"""
    DATA = bytes(range(256)) * 4096  # 1MB

    def do_GET(self):
        try:
            total = len(self.DATA)
            rng = self.headers.get('Range')
            start = 0
            if rng:
                # bytes=start-
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
            self.send_header('Content-Type', 'application/octet-stream')
            self.end_headers()
            # 慢速发送（每 128KB sleep 0.2s）便于测试暂停
            for i in range(0, len(body), 131072):
                self.wfile.write(body[i:i + 131072])
                self.wfile.flush()
                time.sleep(0.2)
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

srv = HTTPServer(('127.0.0.1', 0), RangeServer)
threading.Thread(target=srv.serve_forever, daemon=True).start()
url = f'http://127.0.0.1:{srv.server_address[1]}/model.safetensors'

# ==== T1: 暂停 → 继续（断点续传）====
tid = win.download_manager.start({'name': 'pause_test', 'type': '大模型', 'url': url},
                                 parent_widget=win, src_pos=QPoint(300, 300))
time.sleep(1.0)  # 下载一部分
app.processEvents()
win.download_manager.pause(tid)
time.sleep(0.8)
app.processEvents()
t = win.download_manager.tasks[tid]
part = comfy_dir / 'models' / 'checkpoints' / 'pause_test.safetensors.part'
print(f'T1 暂停: status={t.status}, part 大小={part.stat().st_size if part.exists() else 0}')
assert t.status == 'paused', f"暂停后 status 应为 paused, 实际 {t.status}"
assert part.exists(), ".part 应保留（断点）"
paused_size = part.stat().st_size
print('   ✓ 暂停成功且保留断点')

# 继续
win.download_manager.resume(tid)
time.sleep(2.5)
app.processEvents()
t = win.download_manager.tasks.get(tid)
dest = comfy_dir / 'models' / 'checkpoints' / 'pause_test.safetensors'
print(f'T1 恢复: status={t.status if t else None}, 最终文件={dest.exists() and dest.stat().st_size}')
assert dest.exists(), "恢复后应下载完成"
assert dest.stat().st_size == len(RangeServer.DATA), "文件大小应等于服务器数据完整大小"
print('   ✓ 断点续传成功，文件完整')

# ==== T2: 空白窗口不轰炸（多次失败只弹一次引导）====
win.download_manager._guide_shown = False
from app.ui.download_manager import DownloadTask
class HtmlError(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            self.send_response(200)
            self.send_header('Content-Type', 'text/html')
            self.send_header('Content-Length', '200')
            self.end_headers()
            self.wfile.write(b'<!DOCTYPE html><html>error</html>')
        except Exception:
            pass
    def log_message(self, *a): pass
srv2 = HTTPServer(('127.0.0.1', 0), HtmlError)
threading.Thread(target=srv2.serve_forever, daemon=True).start()
url2 = f'http://127.0.0.1:{srv2.server_address[1]}/api/download/models/1'

exec_count = {'n': 0}
orig_exec = QMessageBox.exec
def fake_exec(self):
    exec_count['n'] += 1
    return QMessageBox.Cancel
QMessageBox.exec = fake_exec
# 两次失败 → 引导窗只应出现一次
win.download_manager.start({'name': 'fail1', 'type': '大模型', 'url': url2}, parent_widget=win)
time.sleep(1.0)
app.processEvents()
win.download_manager.start({'name': 'fail2', 'type': '大模型', 'url': url2}, parent_widget=win)
time.sleep(1.5)
app.processEvents()
print(f'T2 引导窗去重: exec 调用次数={exec_count["n"]} (应=1)')
assert exec_count['n'] == 1, "多次失败只弹一次引导窗"
print('   ✓ 不再弹窗轰炸')
QMessageBox.exec = orig_exec
srv2.shutdown()

# ==== T3: 超长文件名 elide ====
win.gallery_btn.click()
app.processEvents()
gp = win.gallery_panel
long_title = "M8FZGN3PBDRDH3VQH8EDJTT5N0?sig=CfDJ8J868rbHQQlNuTOL2qbAsuR9M2NuUPq-uGlLmOZLpstMKC7yWIiJQ9oNij5_ORbusq9hfewvI_g81j8Em2zoxRNOYu1wGjUycfw5tn5zR2g1dOPjJZpK8voXAI7yv3qb9TCnQ9mLdkCBCPnB_MJVDctjoz9DI13gsbXM15EOgFB79iBi17C1DPPcGQ97pp4tGtEnCXVN-bz30_DO5UeQd7_j1VifkpGdA0q9vvbeOva8foo60SKha-UG4Pd9Y6Mq5Z8wgp9HKuW4pmrvUVDyGZ6tpDbDeH095NusGQqUInQ3&exp=2026-09-14T14:38:33.0858533Z"
store.add({'title': long_title, 'positive': 'p', 'negative': '', 'base_model': '其他',
           'models': [{'name': long_title, 'type': '大模型', 'url': ''}],
           'loras': [], 'width': 1024, 'height': 768, 'source': 'local',
           'source_url': '', 'image_file': '', 'thumb_file': ''})
gp.reload()
app.processEvents()
gp.gallery.setCurrentRow(0)
gp._on_selection_changed(store.records[-1])
app.processEvents()
sb = gp.sidebar
shown_title = sb.title_label.text()
print(f'T3 标题 elide: 显示长度={len(shown_title)}（原 {len(long_title)}）')
assert len(shown_title) < len(long_title), "超长标题应被截断"
assert shown_title.startswith("M8FZ") and shown_title.endswith("Z") or "…" in shown_title
print(f'   显示: {shown_title[:60]}...')
print('   ✓ 超长文件名中间截断')

srv.shutdown()
print()
print('全部 v2.4.6 验证通过 ✓')