"""v3.5 测试：图库分片渲染（加载不卡死）+ 「刷新」按钮（手动重扫输出文件夹）。

覆盖：
1. T1 分片渲染不阻塞：350 条记录（含虚拟）GalleryPanel + _apply → 分片定时器
   启动、首批出现、最终 item 数 == 预期（50 真实 + 250 虚拟上限 = 300）
2. T2 分片取消：渲染中途再次 _apply → 旧分片停止、新渲染正常完成（小集同步 /
   大集重新分片两种）
3. T3 刷新按钮存在（ghost 样式）+ 点击触发扫描信号（refreshRequested →
   MainWindow._start_output_scan）
4. T4 独立面板（无 MainWindow）点刷新 → reload 兜底
5. T5 小数据集同步渲染回归（<= GRID_CHUNK 立即出全部，保既有测试确定性）

运行：python tests/test_v35_refresh.py
"""
import os, sys, tempfile, time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")

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

ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {name}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        ok = False

td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")


def pump(seconds: float, step: float = 0.005):
    """驱动事件循环（offscreen 下定时器/信号需 pump 事件），真实时间推进 seconds。"""
    deadline = time.time() + seconds
    while time.time() < deadline:
        app.processEvents()
        time.sleep(step)


def pump_until(cond, timeout: float = 10.0, step: float = 0.005):
    """处理事件循环直到条件满足或超时（带超时防死循环）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if cond():
            return True
        time.sleep(step)
    app.processEvents()
    return cond()


def make_records(n_real: int, n_virt: int) -> list:
    """构造测试记录：n_real 条真实 + n_virt 条虚拟（无文件 → 占位图，测分片机制）。"""
    recs = []
    for i in range(n_real):
        recs.append({
            "id": f"r{i:03d}", "title": f"真实 {i}", "positive": f"prompt real {i}",
            "negative": "", "models": [], "loras": [], "tags": [],
            "base_model": "Krea 2", "width": 512, "height": 512,
            "created_at": "2026-01-01", "source": "local", "group": "",
        })
    for i in range(n_virt):
        recs.append({
            "id": f"v{i:03d}", "title": f"虚拟 {i}", "positive": f"prompt virt {i}",
            "negative": "", "models": [], "loras": [], "tags": [],
            "base_model": "Flux.1", "width": 1024, "height": 1024,
            "created_at": "2026-01-01", "source": "local", "group": "my_works",
            "is_virtual": True, "virtual_path": "",
        })
    return recs


# ============ T1: 分片渲染不阻塞（大数据量分批 QTimer） ============
print("[T1] 分片渲染：350 条（50 真实 + 300 虚拟 → VIRT_CAP 250）→ 预期 300")
gp = GalleryPanel(store)
gp._records = make_records(50, 300)
gp._apply()
check("T1 分片定时器已启动", gp._chunk_timer.isActive())
check("T1 渲染前 gallery 为空（首批未同步全量）", gp.gallery.count() == 0,
      f"(count={gp.gallery.count()})")
# 驱动事件循环直到首批出现（16ms 定时器）
pump_until(lambda: gp.gallery.count() > 0, timeout=5.0)
first = gp.gallery.count()
check("T1 首批已渲染且未全量（分批推进）", 0 < first < 300, f"(首批 {first})")
check("T1 首批后定时器仍在运行（后续批次待渲染）", gp._chunk_timer.isActive())
# 持续 pump 直到渲染完成
done = pump_until(lambda: not gp._chunk_timer.isActive(), timeout=10.0)
final = gp.gallery.count()
check("T1 渲染最终完成", done and final == 300, f"(count={final})")
check("T1 最终 item 数 == 预期 300", final == 300)
check("T1 渲染完成后定时器已停止", not gp._chunk_timer.isActive())
check("T1 计数标签立即显示总数", "300" in gp.count_label.text(),
      repr(gp.count_label.text()))
check("T1 记录全在 _by_uid（悬停/右键可查）", len(gp._by_uid) == 300,
      f"(by_uid={len(gp._by_uid)})")


# ============ T2a: 分片取消（中途 _apply 小集 → 旧分片停止 + 同步完成） ============
print("[T2a] 分片取消：渲染中途 _apply 小数据集 → 旧分片停止、新渲染同步完成")
gp2 = GalleryPanel(store)
gp2._records = make_records(50, 300)
gp2._apply()
# 推进到「已有部分渲染但未全量」（首批即满足，避免等太久把渲染跑完）
mid_ok = pump_until(lambda: 0 < gp2.gallery.count() < 300, timeout=3.0)
mid = gp2.gallery.count()
check("T2a 中途已有部分渲染且定时器活跃", mid_ok and gp2._chunk_timer.isActive(),
      f"(mid={mid})")
gp2._records = make_records(20, 0)   # 模拟筛选/排序：小集 → 同步路径
gp2._apply()
app.processEvents()
check("T2a 旧分片定时器已停止", not gp2._chunk_timer.isActive())
check("T2a 新渲染立即完成（无旧 item 残留）", gp2.gallery.count() == 20,
      f"(count={gp2.gallery.count()})")
check("T2a 分片状态已复位", gp2._chunk_records is None and gp2._chunk_pos == 0)


# ============ T2b: 分片取消（中途 _apply 大集 → 新分片正常完成） ============
print("[T2b] 分片取消：渲染中途 _apply 新大集 → 旧分片停止、新渲染正常完成")
gp2._records = make_records(50, 300)
gp2._apply()
mid_ok = pump_until(lambda: 0 < gp2.gallery.count() < 300, timeout=3.0)
check("T2b 旧分片渲染中", mid_ok and gp2._chunk_timer.isActive(),
      f"(mid={gp2.gallery.count()})")
gp2._records = make_records(0, 100)   # 100 虚拟 → 全部显示（< VIRT_CAP）
gp2._apply()
check("T2b 新 _apply 已取消旧分片并重启定时器", gp2._chunk_timer.isActive())
done2 = pump_until(lambda: not gp2._chunk_timer.isActive(), timeout=10.0)
check("T2b 新渲染正常完成 100 条", done2 and gp2.gallery.count() == 100,
      f"(count={gp2.gallery.count()})")


# ============ T3: 刷新按钮存在 + 点击触发扫描信号 ============
print("[T3] 「刷新」按钮：存在 + 点击触发 MainWindow._start_output_scan")
win = MainWindow(store, output_scan=False)   # 不启动 800ms 启动扫描定时器
win.show()
app.processEvents()
gp3 = win.gallery_panel
btns = [b for b in gp3.findChildren(QPushButton) if b.text() == "刷新"]
check("T3 刷新按钮存在", len(btns) == 1, f"(n={len(btns)})")
check("T3 刷新按钮 ghost 样式（与查重一致）", len(btns) == 1 and btns[0].objectName() == "ghost")
# 信号发射：额外监听 refreshRequested
sig_calls = {"n": 0}
gp3.refreshRequested.connect(lambda: sig_calls.__setitem__("n", sig_calls["n"] + 1))
# MainWindow 接线：_start_output_scan 会调用 configured_output_dirs；spy 验证链路触发
real_cod = comfy_output.configured_output_dirs
scan_calls = {"n": 0}
def spy_cod(st):
    scan_calls["n"] += 1
    return []   # 空目录配置 → _start_output_scan 早退（不启动真实线程）
comfy_output.configured_output_dirs = spy_cod
btns[0].click()
app.processEvents()
comfy_output.configured_output_dirs = real_cod
check("T3 点击发 refreshRequested 信号", sig_calls["n"] == 1, f"({sig_calls['n']})")
check("T3 信号已接到 MainWindow._start_output_scan（后台扫描链路触发）",
      scan_calls["n"] >= 1, f"({scan_calls['n']})")


# ============ T4: 独立面板（无 MainWindow）点刷新 → reload 兜底 ============
print("[T4] 独立 GalleryPanel（无 MainWindow）：点刷新 → reload 兜底")
gp4 = GalleryPanel(store)
gp4._records = make_records(5, 0)
gp4._apply()
check("T4 前置：小集同步显示 5 条", gp4.gallery.count() == 5)
reload_calls = {"n": 0}
orig_reload = gp4.reload
def spy_reload():
    reload_calls["n"] += 1
    return orig_reload()
gp4.reload = spy_reload
btn4 = [b for b in gp4.findChildren(QPushButton) if b.text() == "刷新"][0]
btn4.click()
app.processEvents()
check("T4 独立面板点刷新触发 reload 兜底", reload_calls["n"] >= 1, f"({reload_calls['n']})")
gp4.reload = orig_reload


# ============ T5: 小数据集同步渲染回归（保既有测试确定性） ============
print("[T5] 小数据集（<= GRID_CHUNK）同步渲染回归")
gp5 = GalleryPanel(store)
gp5._records = make_records(GRID_CHUNK, 0)
gp5._apply()
check("T5 恰好 GRID_CHUNK 条同步出全部", gp5.gallery.count() == GRID_CHUNK,
      f"(count={gp5.gallery.count()})")
check("T5 同步渲染不启定时器", not gp5._chunk_timer.isActive())
gp5._records = make_records(3, 0)
gp5._apply()
check("T5 小集立即显示（3 条）", gp5.gallery.count() == 3 and not gp5._chunk_timer.isActive())


# 收尾
win.close()
app.processEvents()

print()
print("v3.5 分片渲染 + 刷新按钮", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
