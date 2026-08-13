"""v4.1 无边框主窗口 + 自绘标题栏测试。

覆盖：
T1 MainWindow 无边框标志（FramelessWindowHint）+ windowShell 外壳存在
T2 TitleBar 三窗口按钮存在；最小化按钮触发 showMinimized
T3 双击标题栏空白区切换最大化/还原（按钮区域不触发）
T4 标题栏空白区拖动 → window.pos() 变化
T5 最大化时 shell 的 maximized 属性为 true（QSS 属性选择器生效依据）
T6 暗/亮主题切换后标题栏按钮样式无异常
T7 i18n 三表 key 集合一致 + 新 key（最小化/最大化/还原）齐备 + en_keys.txt 同步

运行：python tests/test_v41_titlebar.py
"""
import os, sys, tempfile, ast
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

from PySide6.QtCore import Qt, QEvent, QPoint, QPointF
from PySide6.QtGui import QMouseEvent

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS, LIGHT_QSS
from app.ui.main_window import MainWindow
from app.ui.title_bar import TitleBar

app = QApplication([])
app.setStyleSheet(APP_QSS)
td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")

ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {name}" + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        ok = False


def dblclick_event(widget, local_pos, button=Qt.LeftButton):
    """构造发送给 widget 的双击事件（local 为 widget 坐标，global 自动映射）。"""
    gp = widget.mapToGlobal(QPoint(int(local_pos.x()), int(local_pos.y())))
    return QMouseEvent(QEvent.MouseButtonDblClick, QPointF(local_pos), QPointF(0, 0),
                       QPointF(gp), button, button, Qt.NoModifier)


def press_event(widget, local_pos):
    gp = widget.mapToGlobal(QPoint(int(local_pos.x()), int(local_pos.y())))
    return QMouseEvent(QEvent.MouseButtonPress, QPointF(local_pos), QPointF(0, 0),
                       QPointF(gp), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)


def move_event(widget, local_pos):
    gp = widget.mapToGlobal(QPoint(int(local_pos.x()), int(local_pos.y())))
    return QMouseEvent(QEvent.MouseMove, QPointF(local_pos), QPointF(0, 0),
                       QPointF(gp), Qt.NoButton, Qt.LeftButton, Qt.NoModifier)


def release_event(widget, local_pos):
    gp = widget.mapToGlobal(QPoint(int(local_pos.x()), int(local_pos.y())))
    return QMouseEvent(QEvent.MouseButtonRelease, QPointF(local_pos), QPointF(0, 0),
                       QPointF(gp), Qt.LeftButton, Qt.NoButton, Qt.NoModifier)


# ============ T1: 无边框 + windowShell ============
print("[T1] MainWindow 无边框 + windowShell")
win = MainWindow(store, output_scan=False)
check("T1 FramelessWindowHint 已设置",
      bool(win.windowFlags() & Qt.FramelessWindowHint), repr(win.windowFlags()))
check("T1 windowShell 存在且 objectName 正确",
      win._shell is not None and win._shell.objectName() == "windowShell",
      repr(getattr(win, "_shell", None)))
check("T1 TitleBar 存在", win.title_bar is not None and isinstance(win.title_bar, TitleBar))
check("T1 最小尺寸保持 1020x640",
      win.minimumSize().width() >= 1020 and win.minimumSize().height() >= 640)
win.show()
app.processEvents()

tb = win.title_bar

# ============ T2: 三按钮 + 最小化 ============
print("[T2] TitleBar 三按钮 + 最小化")
check("T2 btn_min/btn_max/btn_close 存在",
      tb.btn_min is not None and tb.btn_max is not None and tb.btn_close is not None)
check("T2 按钮 objectName",
      tb.btn_min.objectName() == "tbMin" and tb.btn_max.objectName() == "tbMax"
      and tb.btn_close.objectName() == "tbClose",
      f"{tb.btn_min.objectName()}/{tb.btn_max.objectName()}/{tb.btn_close.objectName()}")
check("T2 标题栏高 44", tb.height() == TitleBar.HEIGHT, str(tb.height()))

# offscreen 下最小化状态可能受限：用 spy 断言「最小化槽被调用」
min_calls = []
_orig_min = win.showMinimized
win.showMinimized = lambda: min_calls.append("min")
tb.btn_min.click()
app.processEvents()
check("T2 最小化按钮触发 showMinimized", min_calls == ["min"], repr(min_calls))
win.showMinimized = _orig_min

# ============ T3: 双击标题栏空白区切换最大化/还原 ============
print("[T3] 双击标题栏空白区切换最大化/还原")
max_calls = []
_orig_show_max = win.showMaximized
_orig_show_normal = win.showNormal
win.showMaximized = lambda: max_calls.append("max")
win.showNormal = lambda: max_calls.append("normal")
_orig_ismax = win.isMaximized

# 空白区（标题栏左侧，不在按钮上）双击
blank = QPointF(120, 20)
win.isMaximized = lambda: False
tb.mouseDoubleClickEvent(dblclick_event(tb, blank))
check("T3 非最大化双击空白区 → showMaximized", max_calls == ["max"], repr(max_calls))

win.isMaximized = lambda: True
tb.mouseDoubleClickEvent(dblclick_event(tb, blank))
check("T3 最大化双击空白区 → showNormal", max_calls == ["max", "normal"], repr(max_calls))

# 双击按钮区域不应触发最大化
max_calls.clear()
win.isMaximized = lambda: False
btn_center = QPointF(tb.btn_max.geometry().center())
tb.mouseDoubleClickEvent(dblclick_event(tb, btn_center))
check("T3 双击按钮区域不触发最大化", max_calls == [], repr(max_calls))

win.showMaximized = _orig_show_max
win.showNormal = _orig_show_normal
win.isMaximized = _orig_ismax
win.showNormal()
app.processEvents()

# ============ T4: 标题栏拖动 → pos 变化 ============
print("[T4] 标题栏空白区拖动 → window.pos() 变化")
_orig_ismax2 = win.isMaximized
win.isMaximized = lambda: False
win.showNormal()
app.processEvents()
p0 = win.pos()
tb.mousePressEvent(press_event(tb, QPointF(150, 20)))
tb.mouseMoveEvent(move_event(tb, QPointF(250, 60)))
app.processEvents()
p1 = win.pos()
check("T4 拖动后 pos 变化", p1 != p0, f"{p0} -> {p1}")
check("T4 位移符合拖动差值", p1 == p0 + QPoint(100, 40), f"{p0} -> {p1}")
tb.mouseReleaseEvent(release_event(tb, QPointF(250, 60)))
win.isMaximized = _orig_ismax2

# ============ T5: 最大化时 shell maximized 属性 ============
print("[T5] 最大化时 shell 的 maximized 属性 = true")
win.showMaximized()
app.processEvents()
if win._shell.property("windowMaximized") is True:
    check("T5 真实最大化后 shell windowMaximized=true", True)
    win.showNormal()
    app.processEvents()
    check("T5 还原后 shell windowMaximized=false", win._shell.property("windowMaximized") is False,
          repr(win._shell.property("windowMaximized")))
else:
    # 个别 offscreen 平台窗口状态不可靠时：直接验证同步逻辑（等价「槽被调用」断言）
    print("  (offscreen 真实最大化受限，改用直接同步逻辑断言)")
    _orig_ismax3 = win.isMaximized
    win.isMaximized = lambda: True
    win._sync_window_state()
    check("T5 (offscreen) 同步逻辑 windowMaximized=true", win._shell.property("windowMaximized") is True)
    win.isMaximized = lambda: False
    win._sync_window_state()
    check("T5 (offscreen) 同步逻辑 windowMaximized=false", win._shell.property("windowMaximized") is False)
    win.isMaximized = _orig_ismax3
    win.showNormal()
app.processEvents()

# ============ T6: 暗/亮主题切换标题栏无异常 ============
print("[T6] 暗/亮主题切换标题栏按钮样式无异常")
try:
    win.apply_theme("dark")
    app.processEvents()
    dark_ok = (win.title_bar.btn_min is not None and win.title_bar.btn_close is not None)
    check("T6 暗色主题切换无异常且按钮存活", dark_ok)
    win.apply_theme("light")
    app.processEvents()
    check("T6 亮色主题切换无异常", app.styleSheet() == LIGHT_QSS)
    check("T6 亮色后按钮仍存活", win.title_bar.btn_max is not None)
    win.apply_theme("dark")
    app.processEvents()
    check("T6 切回暗色无异常", app.styleSheet() == APP_QSS)
except Exception as e:
    check("T6 主题切换无异常", False, repr(e))

# ============ T7: i18n 三表一致 + en_keys.txt 同步 ============
print("[T7] i18n 三表一致 + en_keys.txt 同步")
src = open("app/i18n.py", encoding="utf-8").read()
tree = ast.parse(src)
tables = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_LANG_TABLES"
                                            for t in node.targets):
        tables = {k.value: {kk.value: vv.value for kk, vv in zip(v.keys, v.values)}
                  for k, v in zip(node.value.keys, node.value.values)}
en, es, ja = tables["en"], tables["es"], tables["ja"]
check("T7 三表 key 集合一致", set(en) == set(es) == set(ja),
      f"{len(en)}/{len(es)}/{len(ja)}")
for k in ["最小化", "最大化", "还原"]:
    check(f"T7 三表齐备: {k}", k in en and k in es and k in ja)
check("T7 标题栏 tooltip 本地化",
      tb.btn_min.toolTip() == "最小化" and tb.btn_close.toolTip() == "关闭",
      f"{tb.btn_min.toolTip()!r}/{tb.btn_close.toolTip()!r}")
en_txt = (Path(__file__).resolve().parent.parent / "en_keys.txt").read_text(encoding="utf-8")
check("T7 en_keys.txt 含 最小化/最大化/还原",
      "'最小化'" in en_txt and "'最大化'" in en_txt and "'还原'" in en_txt)

# 收尾：中断后台线程（若有），避免退出告警
win.close()
app.processEvents()

print()
print("v4.1 无边框主窗口 + 自绘标题栏", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
