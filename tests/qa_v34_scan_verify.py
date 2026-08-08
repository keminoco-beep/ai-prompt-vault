"""QA 独立复验：v3.4.1 图库「正在后台扫描输出文件夹…」永远不清除 Bug 修复。

与工程师 tests/test_v34_scanning.py 完全独立编写（fresh eyes），聚焦用户实测场景：
  S1 快速重新选定输出目录（A → 立刻改 B）：
     旧线程被中断+等待、新线程正常跑；新线程 done → set_scanning(False) + 图库 reload
     含 B 的虚拟记录；旧线程迟到 done 不干扰状态（身份校验）。
  S2 模拟扫描永久阻塞：线程永不 done → MAX_SCAN_SECONDS(2s) 后 _force_clear_scanning
     强制清除扫描标记（UI 不卡死）+ reload 读缓存；定时器停止。
  S3 正常完成：真实 scan_output_images 完成 → set_scanning(False) + reload + 定时器取消。
  S4 空目录：comfy_output_dirs 空 → _start_output_scan 直接 set_scanning(False) 返回。

运行：QT_QPA_PLATFORM=offscreen python tests/qa_v34_scan_verify.py
"""
import os, sys, time, tempfile, json
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QImage
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
import app.comfy_output as co
from app.ui.main_window import MainWindow

app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)

ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {name}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        ok = False

def wait_until(cond, timeout=6.0, step=0.02):
    deadline = time.time() + timeout
    while time.time() < deadline:
        app.processEvents()
        if cond():
            return True
        time.sleep(step)
    return cond()

# ---------- 环境：临时 store（不碰真实 Library） ----------
td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")

outA = td / "ComfyUI_A" / "output"; outA.mkdir(parents=True)
outB = td / "ComfyUI_B" / "output"; outB.mkdir(parents=True)
cache_file = str(store.root / "comfy_output_cache.json")

# B 目录放一张真实小 PNG，便于验证真实扫描/缓存链路
img = QImage(4, 4, QImage.Format_RGB32)
img.fill(0xFF4477AA)
img.save(str(outB / "b_sample.png"), "PNG")

win = MainWindow(store, output_scan=False)   # 不启动 800ms 启动扫描定时器
win.show()
app.processEvents()

real_scan = co.scan_output_images
release = {"go": False}          # 供 S2 释放卡死线程

def blocking_scan(dirs, cache_file=None, cancel_cb=None):
    """模拟慢/卡住扫描：等待取消或外部释放。"""
    while not (cancel_cb and cancel_cb()) and not release["go"]:
        time.sleep(0.01)
    return []

def forever_scan(dirs, cache_file=None, cancel_cb=None):
    """模拟异常阻塞/死循环：忽略 cancel，永不 done（直到外部释放）。"""
    while not release["go"]:
        time.sleep(0.01)
    return []

def fast_scan_write(dirs, cache_file=None, cancel_cb=None):
    """模拟真实扫描流程：构建虚拟记录并写磁盘缓存后秒回。"""
    hashes = co._dir_hashes(dirs)
    display_names = co._display_names(dirs)
    recs, files = {}, {}
    for d in dirs:
        dh = hashes[d]
        root = Path(d)
        if not root.is_dir():
            continue
        for p in root.rglob("*"):
            if p.is_file() and p.suffix.lower() in co.IMAGE_EXTS and not p.name.endswith(".part"):
                rel = p.relative_to(root).as_posix()
                try:
                    st = p.stat()
                except OSError:
                    continue
                k = f"{dh}/{rel}"
                files[k] = [st.st_mtime, st.st_size]
                recs[k] = co._build_virtual_record(
                    root, rel, st.st_mtime, co._group_prefix_for(dirs, d, display_names), dh)
    if cache_file:
        co._save_disk_cache(cache_file, files, recs, co._dirs_key(dirs))
    return list(recs.values())

reload_spy = {"n": 0}
orig_reload = win.gallery_panel.reload
def spy_reload():
    reload_spy["n"] += 1
    return orig_reload()
win.gallery_panel.reload = spy_reload

# ============ S1 快速重新选定输出目录（用户实测场景） ============
print("[S1] 快速重新选定输出目录 A → B（旧线程中断等待 + 新线程正常跑 + 旧 done 不干扰）")
store.save_setting("comfy_output_dirs", [str(outA)])
co.scan_output_images = blocking_scan
win.MAX_SCAN_SECONDS = 60

win._start_output_scan()
app.processEvents()
t1 = win._scan_thread
check("S1 旧线程(t1)已启动", t1 is not None and t1.isRunning())
check("S1 扫描中标记 True", win.gallery_panel._scanning is True)

# 用户立刻在设置里改选 B → 保存 → _on_output_dirs_changed → _start_output_scan
store.save_setting("comfy_output_dirs", [str(outB)])
co.scan_output_images = fast_scan_write
reload_spy["n"] = 0
win._start_output_scan()
app.processEvents()
t2 = win._scan_thread
check("S1 旧线程已退出（中断+wait 生效）", not t1.isRunning())
check("S1 新线程(t2)已启动且引用已覆盖", t2 is not None and t2 is not t1 and t2.isRunning())
check("S1 扫描中标记仍 True（新线程在扫）", win.gallery_panel._scanning is True)

# 旧线程迟到 done → 身份校验应忽略（不清状态、不 reload）
before_reload = reload_spy["n"]
t1.done.emit()
app.processEvents()
check("S1 旧线程迟到 done 不清扫描标记", win.gallery_panel._scanning is True)
check("S1 旧线程迟到 done 不触发 reload", reload_spy["n"] == before_reload, f"(reload={reload_spy['n']})")

# 新线程完成 → 清状态 + reload 含 B 虚拟记录
done = wait_until(lambda: win.gallery_panel._scanning is False, timeout=4.0)
check("S1 新线程完成 → set_scanning(False)", done)
check("S1 完成触发 reload", reload_spy["n"] >= 1, f"(reload={reload_spy['n']})")
check("S1 超时定时器已取消", not win._scan_timeout.isActive())
recs = win.gallery_panel._records
b_recs = [r for r in recs if r.get("is_virtual") and str(r.get("virtual_path", "")).startswith(str(outB))]
check("S1 图库 reload 含 B 的虚拟记录", len(b_recs) >= 1, f"(B virtual records={len(b_recs)})")
data = json.loads(Path(cache_file).read_text(encoding="utf-8"))
check("S1 磁盘缓存 dirs key 匹配 B", data.get("dirs") == co._dirs_key([str(outB)]), f"(cache dirs={data.get('dirs')})")

# ============ S2 模拟扫描永久阻塞（超时兜底，UI 不卡死） ============
print("[S2] 模拟扫描永久阻塞 → MAX_SCAN_SECONDS=2 超时兜底强制清除")
store.save_setting("comfy_output_dirs", [str(outA)])
release["go"] = False
co.scan_output_images = forever_scan
win.MAX_SCAN_SECONDS = 2
reload_spy["n"] = 0

win._start_output_scan()
app.processEvents()
t3 = win._scan_thread
check("S2 卡住线程(t3)已启动", t3 is not None and t3.isRunning())
check("S2 扫描中标记 True", win.gallery_panel._scanning is True)
check("S2 超时定时器运行中", win._scan_timeout.isActive())

done = wait_until(lambda: win.gallery_panel._scanning is False, timeout=4.0)
check("S2 超时后强制清除扫描标记（UI 不卡死）", done)
check("S2 超时定时器已停止", not win._scan_timeout.isActive())
check("S2 超时兜底触发 reload（读缓存）", reload_spy["n"] >= 1, f"(reload={reload_spy['n']})")

# 释放卡死线程，避免退出挂起；线程 done 到达后状态仍为 False
release["go"] = True
wait_until(lambda: not (t3.isRunning() if t3 else False), timeout=4.0)
app.processEvents()
check("S2 线程释放后状态仍 False", win.gallery_panel._scanning is False)

# ============ S3 正常完成（真实扫描链路） ============
print("[S3] 正常完成：真实 scan_output_images → done → 清状态 + reload + 取消定时器")
store.save_setting("comfy_output_dirs", [str(outB)])
co.scan_output_images = real_scan   # 真实实现：B 只有 1 张 PNG，秒级
win.MAX_SCAN_SECONDS = 60
reload_spy["n"] = 0

win._start_output_scan()
app.processEvents()
t4 = win._scan_thread
check("S3 扫描线程已启动", t4 is not None and t4.isRunning())
check("S3 扫描中标记 True", win.gallery_panel._scanning is True)

done = wait_until(lambda: win.gallery_panel._scanning is False, timeout=6.0)
check("S3 正常完成 → set_scanning(False)", done)
check("S3 完成触发 reload", reload_spy["n"] >= 1, f"(reload={reload_spy['n']})")
check("S3 超时定时器已取消", not win._scan_timeout.isActive())
recs = win.gallery_panel._records
b_recs = [r for r in recs if r.get("is_virtual") and str(r.get("virtual_path", "")).startswith(str(outB))]
check("S3 图库含 B 真实虚拟记录", len(b_recs) >= 1, f"(B virtual records={len(b_recs)})")

# ============ S4 空目录 ============
print("[S4] 空目录：comfy_output_dirs=[] → 直接 set_scanning(False) 返回")
store.save_setting("comfy_output_dirs", [])
before = win._scan_thread
win._start_output_scan()
app.processEvents()
check("S4 扫描中标记 False", win.gallery_panel._scanning is False)
check("S4 未创建新线程", win._scan_thread is before)
check("S4 超时定时器未运行", not win._scan_timeout.isActive())

# ---------- 收尾 ----------
co.scan_output_images = real_scan
win.gallery_panel.reload = orig_reload
win.close()
app.processEvents()

print()
print("QA 独立复验 v3.4.1 扫描链路", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
