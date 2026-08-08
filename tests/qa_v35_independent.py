"""QA 独立复验脚本（v3.5 分片渲染 + 刷新按钮）——fresh eyes，不信任实现者自测。

与 tests/test_v35_refresh.py 独立编写，重点补充：
- R1 大数据分片：320 条（纯真实，避开 VIRT_CAP 干扰）→ 定时器启动、首批 40、
  分步推进（观测到多个中间批次数）、完成后定时器停
- R2 窗口响应性：分片渲染期间事件循环仍处理事件（0ms 哨兵定时器多次触发 +
  分批推进非单次同步爆发）
- R3 防堆积：分片中途 _apply 小集 → 旧分片停、新渲染完成、无残留
- R4 刷新按钮：点击 → refreshRequested 发射；MainWindow._start_output_scan 链路
  触发（configured_output_dirs spy）；独立面板无 MainWindow → reload 兜底
- R5 小数据集（<= GRID_CHUNK）同步渲染不启定时器

运行：QT_QPA_PLATFORM=offscreen python tests/qa_v35_independent.py
"""
import os, sys, tempfile, time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QPushButton
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app import comfy_output
from app.ui.gallery_panel import GalleryPanel, GRID_CHUNK
from app.ui.main_window import MainWindow

app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)

td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")          # 临时 store（不碰真实 Library）
i18n.init(store.settings_path(), "zh")

ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {name}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        ok = False

def make_records(n: int) -> list:
    """n 条纯真实记录（无 image/thumb 文件 → 占位图；避免 VIRT_CAP 干扰）。"""
    return [{
        "id": f"r{i:04d}", "title": f"记录 {i}", "positive": f"prompt {i}",
        "negative": "", "models": [], "loras": [], "tags": [],
        "base_model": "Krea 2", "width": 512, "height": 512,
        "created_at": "2026-01-01", "source": "local", "group": "",
    } for i in range(n)]

def pump(seconds: float, step: float = 0.002):
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(step)

def pump_until(cond, timeout: float = 10.0, step: float = 0.002):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if cond():
            return True
        time.sleep(step)
    app.processEvents()
    return cond()

# ================= R1: 大数据分片 =================
print("[R1] 大数据分片：320 条（纯真实）→ 分批 QTimer 渲染")
gp = GalleryPanel(store)
gp._records = make_records(320)
gp._apply()
check("R1 _apply 后定时器已启动", gp._chunk_timer.isActive())
check("R1 首批未同步渲染（count=0）", gp.gallery.count() == 0, f"(count={gp.gallery.count()})")
# 观测分批推进：记录 processEvents 后观测到的中间批次数集合
seen = set()
deadline = time.time() + 10.0
while time.time() < deadline and gp._chunk_timer.isActive():
    app.processEvents()
    seen.add(gp.gallery.count())
    time.sleep(0.001)
app.processEvents()
final = gp.gallery.count()
seen.add(final)
intermediate = sorted(c for c in seen if 0 < c < 320)
check("R1 观测到首批 40（GRID_CHUNK）", 40 in seen, f"(seen={sorted(seen)[:6]}...)")
check("R1 分步推进（>=3 个中间批次）", len(intermediate) >= 3, f"(中间批次={len(intermediate)}个)")
check("R1 渲染完成 320 条", final == 320, f"(count={final})")
check("R1 完成后定时器已停止", not gp._chunk_timer.isActive())
check("R1 _by_uid 预填全部 320", len(gp._by_uid) == 320, f"(by_uid={len(gp._by_uid)})")
check("R1 计数标签 = 共 320 张", "320" in gp.count_label.text(), repr(gp.count_label.text()))

# ================= R2: 窗口响应性（分片期间事件循环仍工作） =================
print("[R2] 窗口响应性：分片渲染期间事件循环仍处理事件")
gp2 = GalleryPanel(store)
gp2._records = make_records(320)
gp2._apply()
check("R2 前置：定时器活跃", gp2._chunk_timer.isActive())
ticks = {"n": 0}
def _tick():
    ticks["n"] += 1
sentinel = QTimer()
sentinel.setInterval(0)
sentinel.timeout.connect(_tick)
sentinel.start()
# 中途调度一个经事件循环投递的回调（模拟用户操作/其他定时器在分片期间被处理）
delivered = {"n": 0}
def _deliver():
    delivered["n"] += 1
QTimer.singleShot(0, _deliver)
# 推进事件循环直到渲染到第 3 批（>=120）且未完成
mid_ok = pump_until(lambda: 80 <= gp2.gallery.count() < 320, timeout=5.0)
mid = gp2.gallery.count()
check("R2 渲染到中途（>=2 批且未完成）", mid_ok, f"(mid={mid})")
check("R2 分片期间事件循环仍活跃（哨兵定时器触发 >0）", ticks["n"] > 0, f"(ticks={ticks['n']})")
check("R2 分片期间 0ms 单发回调已投递", delivered["n"] == 1, f"({delivered['n']})")
check("R2 分片仍在进行（事件循环未阻塞导致渲染提前完成/卡死）",
      gp2._chunk_timer.isActive(), f"(active={gp2._chunk_timer.isActive()})")
sentinel.stop()
done2 = pump_until(lambda: not gp2._chunk_timer.isActive(), timeout=10.0)
check("R2 收尾：全部渲染完成", done2 and gp2.gallery.count() == 320,
      f"(count={gp2.gallery.count()})")

# ================= R3: 防堆积（分片中途 _apply 小集） =================
print("[R3] 防堆积：分片中途 _apply 小集 → 旧分片停、新渲染完成")
gp3 = GalleryPanel(store)
gp3._records = make_records(320)
gp3._apply()
mid_ok = pump_until(lambda: 0 < gp3.gallery.count() < 320, timeout=3.0)
mid = gp3.gallery.count()
check("R3 前置：中途渲染中", mid_ok and gp3._chunk_timer.isActive(), f"(mid={mid})")
gp3._records = make_records(5)
gp3._apply()
app.processEvents()
check("R3 旧分片定时器已停", not gp3._chunk_timer.isActive())
check("R3 新小集立即显示 5 条（无旧 item 残留）", gp3.gallery.count() == 5,
      f"(count={gp3.gallery.count()})")
check("R3 分片状态复位", gp3._chunk_records is None and gp3._chunk_pos == 0
      and gp3._chunk_size == 0)

# ================= R4a: 刷新按钮 → refreshRequested + MainWindow 扫描链路 =================
print("[R4] 「刷新」按钮：点击 → refreshRequested 发射 → MainWindow._start_output_scan")
win = MainWindow(store, output_scan=False)
win.show()
app.processEvents()
gp4 = win.gallery_panel
btns = [b for b in gp4.findChildren(QPushButton) if b.text() == "刷新"]
check("R4 刷新按钮存在且唯一", len(btns) == 1, f"(n={len(btns)})")
check("R4 ghost 样式", len(btns) == 1 and btns[0].objectName() == "ghost")
sig_calls = {"n": 0}
def _on_sig():
    sig_calls["n"] += 1
gp4.refreshRequested.connect(_on_sig)
real_cod = comfy_output.configured_output_dirs
scan_calls = {"n": 0}
def spy_cod(st):
    scan_calls["n"] += 1
    return []   # 空目录 → _start_output_scan 早退（不启动真实线程）
comfy_output.configured_output_dirs = spy_cod
btns[0].click()
app.processEvents()
comfy_output.configured_output_dirs = real_cod
check("R4 点击发 refreshRequested 信号", sig_calls["n"] == 1, f"({sig_calls['n']})")
check("R4 MainWindow._start_output_scan 链路被触发", scan_calls["n"] >= 1,
      f"({scan_calls['n']})")
win.close()
app.processEvents()

# ================= R4b: 独立面板（无 MainWindow）→ reload 兜底 =================
print("[R4b] 独立 GalleryPanel（无 MainWindow）：点刷新 → reload 兜底")
gp5 = GalleryPanel(store)
gp5._records = make_records(5)
gp5._apply()
check("R4b 前置：小集同步 5 条", gp5.gallery.count() == 5)
reload_calls = {"n": 0}
orig_reload = gp5.reload
def spy_reload():
    reload_calls["n"] += 1
    return orig_reload()
gp5.reload = spy_reload
btn5 = [b for b in gp5.findChildren(QPushButton) if b.text() == "刷新"][0]
btn5.click()
app.processEvents()
check("R4b 独立面板点刷新触发 reload 兜底", reload_calls["n"] >= 1,
      f"({reload_calls['n']})")
gp5.reload = orig_reload

# ================= R5: 小数据集同步渲染 =================
print("[R5] 小数据集（<= GRID_CHUNK）同步渲染不启定时器")
gp6 = GalleryPanel(store)
gp6._records = make_records(GRID_CHUNK)
gp6._apply()
check("R5 恰好 GRID_CHUNK 条同步出全部", gp6.gallery.count() == GRID_CHUNK,
      f"(count={gp6.gallery.count()})")
check("R5 不启定时器", not gp6._chunk_timer.isActive())
gp6._records = make_records(1)
gp6._apply()
check("R5 1 条立即显示且不启定时器", gp6.gallery.count() == 1
      and not gp6._chunk_timer.isActive())

print()
print("QA 独立复验", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
