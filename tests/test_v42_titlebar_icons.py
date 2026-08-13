"""v4.2 标题栏窗口按钮图标测试（Bug 3：中间按钮不居中偏小）。

覆盖：
T1 三按钮使用 QIcon（自绘 16×16 pixmap），不再依赖几何字符
T2 每个按钮 icon pixmap 非空、尺寸 16×16、中心区域有非透明像素
T3 图标几何居中：最小化图标的水平线位于垂直中心行；
   关闭图标的 × 沿两条对角线对称分布
T4 最大化/还原切换：模拟 isMaximized 后 _update_max_icon 换成 restore 图标
   （双层方框），还原后换回 max（单方框）
T5 主题切换 apply_theme：暗/亮图标颜色不同（抽样像素颜色变化）
T6 按钮仍可点击触发窗口控制（最小化 spy）

运行：python tests/test_v42_titlebar_icons.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QImage, QColor

QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.main_window import MainWindow

app = QApplication([])
app.setStyleSheet(APP_QSS)
td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")

ok = True


def check(name: str, cond: bool, extra: str = "") -> None:
    global ok
    print(f"  {'✓' if cond else '✗'} {name}" + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        ok = False


def icon_img(btn) -> QImage:
    pm = btn.icon().pixmap(16, 16)
    return pm.toImage()


def opaque_count(img: QImage) -> int:
    n = 0
    for y in range(img.height()):
        for x in range(img.width()):
            if img.pixelColor(x, y).alpha() > 0:
                n += 1
    return n


def row_has_pixels(img: QImage, y: int) -> bool:
    return any(img.pixelColor(x, y).alpha() > 0 for x in range(img.width()))


def count_in_quadrants(img: QImage):
    """统计非透明像素在左上/右上/左下/右下四象限的数量（判断对称性）。"""
    h, w = img.height(), img.width()
    mid_x, mid_y = w // 2, h // 2
    counts = {"tl": 0, "tr": 0, "bl": 0, "br": 0}
    for y in range(h):
        for x in range(w):
            if img.pixelColor(x, y).alpha() > 0:
                if x < mid_x and y < mid_y:
                    counts["tl"] += 1
                elif x >= mid_x and y < mid_y:
                    counts["tr"] += 1
                elif x < mid_x and y >= mid_y:
                    counts["bl"] += 1
                else:
                    counts["br"] += 1
    return counts


win = MainWindow(store, output_scan=False)
win.show()
app.processEvents()
tb = win.title_bar

# ============ T1: 使用 QIcon（无文本字符） ============
print("[T1] 三按钮使用自绘 QIcon")
for b in ("btn_min", "btn_max", "btn_close"):
    btn = getattr(tb, b)
    check(f"T1 {b} 有 icon", not btn.icon().isNull())
    check(f"T1 {b} 无文本", btn.text() == "", repr(btn.text()))

def bbox(img: QImage):
    """非透明像素包围盒 (min_x, min_y, max_x, max_y)；无像素返回 None。"""
    xs, ys = [], []
    for y in range(img.height()):
        for x in range(img.width()):
            if img.pixelColor(x, y).alpha() > 0:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    return min(xs), min(ys), max(xs), max(ys)


# ============ T2: 图标 pixmap 非空 + 16x16 + 内容居中 ============
print("[T2] icon pixmap 16x16 且内容非空、居中")
for b in ("btn_min", "btn_max", "btn_close"):
    img = icon_img(getattr(tb, b))
    check(f"T2 {b} pixmap 尺寸 16x16",
          img.width() == 16 and img.height() == 16, f"{img.width()}x{img.height()}")
    n = opaque_count(img)
    check(f"T2 {b} 有非透明像素", n >= 20, f"n={n}")
    box = bbox(img)
    check(f"T2 {b} 包围盒非空", box is not None, f"box={box}")
    if box is not None:
        min_x, min_y, max_x, max_y = box
        # 包围盒应居中：左右边距差 ≤ 1px，上下边距差 ≤ 1px
        l, r = min_x, 15 - max_x
        t, b_ = min_y, 15 - max_y
        check(f"T2 {b} 水平居中 (l={l} r={r})", abs(l - r) <= 1, f"l={l} r={r}")
        check(f"T2 {b} 垂直居中 (t={t} b={b_})", abs(t - b_) <= 1, f"t={t} b={b_}")

# ============ T3: 几何居中 / 对称 ============
print("[T3] 图标几何居中与对称")
img_min = icon_img(tb.btn_min)
# 最小化：水平线应在垂直中心行（y=8 ± 1）
center_rows = [y for y in range(16) if row_has_pixels(img_min, y)]
check("T3 最小化图标线条在垂直中心行", any(abs(y - 8) <= 1 for y in center_rows),
      f"rows={center_rows}")
img_close = icon_img(tb.btn_close)
q = count_in_quadrants(img_close)
# × 图标应四象限大致对称（各方向差异不超过 40%）
quad_vals = [q["tl"], q["tr"], q["bl"], q["br"]]
mx, mn = max(quad_vals), min(quad_vals)
check("T3 关闭图标四象限对称", mx > 0 and (mx - mn) <= max(4, mx // 2),
      f"quad={q}")
img_max = icon_img(tb.btn_max)
qmax = count_in_quadrants(img_max)
qmax_vals = [qmax["tl"], qmax["tr"], qmax["bl"], qmax["br"]]
check("T3 最大化方框四象限对称", max(qmax_vals) > 0 and (max(qmax_vals) - min(qmax_vals)) <= max(4, max(qmax_vals) // 2),
      f"quad={qmax}")

# ============ T4: 最大化/还原图标切换 ============
print("[T4] 最大化/还原图标切换")
_orig_ismax = win.isMaximized
win.isMaximized = lambda: True
tb._update_max_icon()
img_restore = icon_img(tb.btn_max)
# restore 是双层方框：像素数应明显多于单方框 max
n_restore = opaque_count(img_restore)
n_max = opaque_count(img_max)
check("T4 还原图标像素多于最大化单方框", n_restore > n_max, f"{n_restore} vs {n_max}")
check("T4 最大化状态下 tooltip=还原", tb.btn_max.toolTip() == "还原", repr(tb.btn_max.toolTip()))
win.isMaximized = lambda: False
tb._update_max_icon()
img_max2 = icon_img(tb.btn_max)
n_max2 = opaque_count(img_max2)
check("T4 还原后换回最大化方框", abs(n_max2 - n_max) <= 8, f"{n_max2} vs {n_max}")
check("T4 还原后 tooltip=最大化", tb.btn_max.toolTip() == "最大化", repr(tb.btn_max.toolTip()))
win.isMaximized = _orig_ismax

# ============ T5: 主题切换图标颜色 ============
print("[T5] 暗/亮主题图标颜色不同")
def sample_icon_color(img: QImage) -> QColor:
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() > 0:
                return c
    return QColor(0, 0, 0)


dark_c = sample_icon_color(icon_img(tb.btn_min))
tb.apply_theme("light")
light_c = sample_icon_color(icon_img(tb.btn_min))
check("T5 暗色图标为浅色(#e8e8f2)", dark_c.lightness() > 180, dark_c.name())
check("T5 亮色图标为深色(#4a4a62)", light_c.lightness() < 130, light_c.name())
tb.apply_theme("dark")
back_c = sample_icon_color(icon_img(tb.btn_min))
check("T5 切回暗色图标恢复浅色", back_c.lightness() > 180, back_c.name())

# ============ T6: 按钮仍触发窗口控制 ============
print("[T6] 最小化按钮触发 showMinimized")
min_calls = []
_orig_min = win.showMinimized
win.showMinimized = lambda: min_calls.append("min")
tb.btn_min.click()
app.processEvents()
check("T6 最小化按钮触发 showMinimized", min_calls == ["min"], repr(min_calls))
win.showMinimized = _orig_min

win.close()
app.processEvents()

print()
print("v4.2 标题栏图标", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
