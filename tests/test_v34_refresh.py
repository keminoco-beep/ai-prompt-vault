"""v3.4 测试：选定 output 文件夹后图库刷新（Bug 2）修复回归。

覆盖：
1. _on_output_dirs_changed 后图库立即 reload（读磁盘缓存含虚拟记录）
2. 切页到图库页（_on_page_changed idx==1）reload 触发
3. _on_output_scanned 无条件 reload（当前页不是图库时也能刷新）+ 清除扫描中标记

运行：python tests/test_v34_refresh.py
"""
import os, sys, tempfile
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

td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")

out = td / "ComfyUI" / "output"
(out / "sub").mkdir(parents=True)
from PySide6.QtGui import QImage, QColor
img = QImage(320, 240, QImage.Format_RGB32)
img.fill(QColor(60, 120, 200))
img.save(str(out / "a.png"), "PNG")
img.save(str(out / "sub" / "b.png"), "PNG")
store.save_setting("comfy_output_dirs", [str(out)])

# 预生成磁盘缓存（模拟首次扫描完成写缓存）
cache_f = str(store.root / "comfy_output_cache.json")
comfy_output._cache.clear()
comfy_output.scan_output_images(str(out), cache_f)

win = MainWindow(store, output_scan=False)   # 不启动 800ms 启动扫描定时器
win.show()
app.processEvents()

# ---- T1: _on_output_dirs_changed 后图库立即含虚拟记录（读缓存） ----
win.gallery_panel._records = []              # 模拟图库尚未加载
win.gallery_panel.reload()
before = [r["id"] for r in win.gallery_panel._records]
check("T1 初始 reload 后含虚拟记录", any(r.get("is_virtual") for r in win.gallery_panel._records),
      f"(count={len(before)})")

win.gallery_panel._records = []              # 清空，模拟"图库空"
win._on_output_dirs_changed()                # 修复：内部会 reload（读缓存）
app.processEvents()
after = [r["id"] for r in win.gallery_panel._records]
check("T1 _on_output_dirs_changed 后图库非空且含虚拟记录",
      len(after) > 0 and any(r.get("is_virtual") for r in win.gallery_panel._records),
      f"(count={len(after)})")

# ---- T2: 切页到图库页 reload 触发（设置页 → 图库页） ----
win.gallery_panel._records = []
win.stack.setCurrentIndex(2)                 # 模型管理页
app.processEvents()
check("T2 切到模型页不加载图库", len(win.gallery_panel._records) == 0)
win.stack.setCurrentIndex(1)                 # 图库页 → _on_page_changed(1) reload
app.processEvents()
check("T2 切回图库页后含虚拟记录",
      any(r.get("is_virtual") for r in win.gallery_panel._records),
      f"(count={len(win.gallery_panel._records)})")

# ---- T3: _on_output_scanned 无条件 reload（当前页不是图库也刷新）+ 清除扫描标记 ----
img.save(str(out / "c.png"), "PNG")
comfy_output._cache.clear()
comfy_output.scan_output_images(str(out), cache_f)   # 更新缓存含 c.png
win.gallery_panel._records = []
win.gallery_panel.set_scanning(True)
win.stack.setCurrentIndex(2)                 # 当前页不是图库
win._on_output_scanned()                     # 无条件 reload
app.processEvents()
check("T3 扫描完成无条件 reload 含新增图",
      len(win.gallery_panel._records) >= 3,
      f"(count={len(win.gallery_panel._records)})")
check("T3 扫描完成清除扫描中标记", win.gallery_panel._scanning is False)

# ---- T4: 空态扫描提示（_scanning=True 时空态显示扫描文案） ----
win.gallery_panel._records = []
win.gallery_panel.set_scanning(True)
win.gallery_panel._apply()
app.processEvents()
check("T4 扫描中空态提示", "正在后台扫描输出文件夹…" in win.gallery_panel.empty_label.text(),
      repr(win.gallery_panel.empty_label.text()))
win.gallery_panel.set_scanning(False)
win.gallery_panel._apply()
app.processEvents()
check("T4 非扫描空态提示恢复", "正在后台扫描输出文件夹…" not in win.gallery_panel.empty_label.text(),
      repr(win.gallery_panel.empty_label.text()))

# 收尾：中断后台线程（若有），避免退出告警
win.close()
app.processEvents()

print()
print("v3.4 图库刷新（output 目录变更）", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
