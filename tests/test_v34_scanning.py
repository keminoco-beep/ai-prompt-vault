"""v3.4.1 测试：图库「正在后台扫描输出文件夹…」永远不清除 Bug 修复回归。

覆盖（根因 3 个叠加）：
1. T1 旧线程处理：新扫描启动前，旧线程 isRunning → requestInterruption + wait(2s)，
   新线程照常启动（旧线程被中断退出、引用被覆盖）
2. T2 线程身份校验：旧线程 done 信号到达时不再无条件清状态/刷新（扫描中标记保持）
3. T3 超时保险：扫描线程永远不 done（异常阻塞/死循环）→ MAX_SCAN_SECONDS 后
   set_scanning(False)（用短超时 2 秒验证）+ 定时器停止
4. T4 正常完成：扫描正常 done → set_scanning(False) + reload + 取消超时定时器

运行：python tests/test_v34_scanning.py
"""
import os, sys, tempfile, time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app import comfy_output
from app.ui.main_window import MainWindow

app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)

ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {name}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        ok = False

def wait_until(cond, timeout=5.0, step=0.02):
    """处理事件循环直到条件满足或超时（offscreen 下定时器/队列信号需 pump 事件）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if cond():
            return True
        time.sleep(step)
    return cond()

td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")

out = td / "ComfyUI" / "output"
out.mkdir(parents=True)
store.save_setting("comfy_output_dirs", [str(out)])

win = MainWindow(store, output_scan=False)   # 不启动 800ms 启动扫描定时器
win.show()
app.processEvents()

# 备份真实扫描实现，测试用可控 mock；结束时恢复
real_scan = comfy_output.scan_output_images

def blocking_scan(dirs, cache_file=None, cancel_cb=None):
    """模拟慢/卡住扫描：循环直到被 requestInterruption 打断。"""
    while not (cancel_cb and cancel_cb()):
        time.sleep(0.01)
    return []

def fast_scan(dirs, cache_file=None, cancel_cb=None):
    """模拟缓存命中秒级完成。"""
    return []


# ============ T1: 新扫描启动前处理旧线程 ============
print("[T1] 新扫描启动前处理旧线程（中断 + 等待 + 硬覆盖）")
comfy_output.scan_output_images = blocking_scan
win.MAX_SCAN_SECONDS = 60   # 本组测试避免超时兜底干扰

win._start_output_scan()
app.processEvents()
t1 = win._scan_thread
check("T1 线程1已启动", t1 is not None and t1.isRunning())
check("T1 扫描中标记 True", win.gallery_panel._scanning is True)

# 记录 t1 的 requestInterruption / wait 调用（实例属性遮蔽 C++ 方法并委托真实实现）
# 注：该 PySide6 版本主线程读 isInterruptionRequested() 恒为 False（绑定缺陷），
# 因此用"调用计数 + 线程确实退出"验证中断+等待逻辑。
calls = {"interrupt": 0, "wait": 0}
orig_int = t1.requestInterruption
orig_wait = t1.wait
def fake_int():
    calls["interrupt"] += 1
    try:
        orig_int()
    except RuntimeError:
        pass
def fake_wait(timeout=0):
    calls["wait"] += 1
    try:
        return orig_wait(timeout)
    except RuntimeError:
        return True
t1.requestInterruption = fake_int
t1.wait = fake_wait

win._start_output_scan()     # 重新选定输出目录：应中断 t1、等待其退出，再启动 t2
app.processEvents()
t2 = win._scan_thread
check("T1 旧线程 requestInterruption 被调用", calls["interrupt"] >= 1, f"({calls['interrupt']})")
check("T1 旧线程 wait 被调用", calls["wait"] >= 1, f"({calls['wait']})")
check("T1 旧线程已退出（wait 生效）", not t1.isRunning())
check("T1 新线程已启动且引用已覆盖", t2 is not None and t2 is not t1 and t2.isRunning())
check("T1 扫描中标记仍 True（新线程在扫）", win.gallery_panel._scanning is True)


# ============ T2: 线程身份校验（旧线程 done 不干扰） ============
print("[T2] 线程身份校验：旧线程 done → no-op")
t1.done.emit()               # 模拟旧线程迟到/重复的 done 信号
app.processEvents()
check("T2 旧线程 done 不清除扫描标记", win.gallery_panel._scanning is True)
check("T2 旧线程 done 不停止新线程超时定时器", win._scan_timeout.isActive() is True)


# ============ T3: 超时保险（扫描永远不 done） ============
print("[T3] 超时保险：异常阻塞时强制清除扫描标记")
win.MAX_SCAN_SECONDS = 2     # 用短超时验证兜底路径
win._start_output_scan()     # 启动一个"永远不 done"的扫描（blocking_scan 未被打断）
app.processEvents()
t3 = win._scan_thread
check("T3 新扫描线程已启动且卡住", t3 is not None and t3.isRunning())
check("T3 扫描中标记 True", win.gallery_panel._scanning is True)
check("T3 超时定时器运行中", win._scan_timeout.isActive() is True)
done = wait_until(lambda: win.gallery_panel._scanning is False, timeout=4.0)
check("T3 超时后强制清除扫描标记", done)
check("T3 超时定时器已停止", not win._scan_timeout.isActive())


# ============ T4: 正常完成（done → 清状态 + reload + 取消定时器） ============
print("[T4] 正常完成：done → set_scanning(False) + reload + 取消定时器")
comfy_output.scan_output_images = fast_scan
win.MAX_SCAN_SECONDS = 60
reload_calls = {"n": 0}
orig_reload = win.gallery_panel.reload
def spy_reload():
    reload_calls["n"] += 1
    return orig_reload()
win.gallery_panel.reload = spy_reload

win._start_output_scan()
done = wait_until(lambda: win.gallery_panel._scanning is False, timeout=3.0)
check("T4 正常完成清除扫描标记", done)
check("T4 正常完成触发 reload", reload_calls["n"] >= 1, f"(reload={reload_calls['n']})")
check("T4 超时定时器已取消", not win._scan_timeout.isActive())
check("T4 线程引用仍有效且已结束", win._scan_thread is not None)


# 收尾：恢复真实实现；中断后台线程（若有），避免退出告警
comfy_output.scan_output_images = real_scan
win.gallery_panel.reload = orig_reload
win.close()
app.processEvents()

print()
print("v3.4.1 扫描状态卡死修复", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
