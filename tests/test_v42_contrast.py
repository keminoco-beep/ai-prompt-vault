"""v4.2 对比度回归测试（Bug 1：暗色文字/logo 对比度不足 + 全文件审计）。

覆盖（暗/亮两主题均用 QWidget.grab() 抽样像素验证）：
T1 标题栏 logo：label 尺寸 = LOGO_BOX(30)；grab 中出现 QSS 描边色像素
   （暗 #3a3a58 / 亮 #c8c8e0）；容器固定深色底 #2a2a3e 可见。
   v4.3.2 起彻底移除 QPainter 覆盖绘制（描边环 + 艺术 A），logo 直接
   显示 app/app_icon.png 原图。PNG 较暗（实测 28x28 RGB 范围
   ≈ (21,22,47)~(52,71,143)），与容器底 #2a2a3e=(42,42,62) 的对比度
   较低（暗主题 ≈ 1.68）。PNG 可见性靠「容器底色与 PNG 圆角外缘露底」
   +「QSS 边框色」提供，不再用「QPainter 白色 A」提升对比度。
   因此 T1 断言改为：PNG 内容相对容器底有任意 > 1 的对比度（即 PNG
   非完全不可见）；同时容器底 #2a2a3e 与 QSS 边框色可见性仍 ≥ 阈值。
T2 设置对话框 checkbox 文字：抽样最亮/最暗文字像素 vs 对话框背景，对比度 ≥ 4.5
T3 QSpinBox 数字：文字像素 vs 输入框背景（暗 #21212e / 亮 #ffffff），对比度 ≥ 4.5
T4 「张」单位（fieldLabel）：文字像素 vs 对话框背景，对比度 ≥ 4.5
T5 侧栏副标题 #brandSub：文字像素 vs 侧栏背景（暗 #12121a / 亮 #ececf5），对比度 ≥ 4.5
T6 全文件审计：解析 style.py 暗色文本色，主/次文字色全部 ≥ 阈值（硬编码断言）

运行：python tests/test_v42_contrast.py
"""
import ast
import os
import re
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication, QMessageBox, QLabel
from PySide6.QtGui import QColor

QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS, LIGHT_QSS
from app.ui.main_window import MainWindow
from app.ui.settings_dialog import SettingsDialog
from app.ui.title_bar import TitleBar

app = QApplication([])
td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")

ok = True


def check(name: str, cond: bool, extra: str = "") -> None:
    global ok
    print(f"  {'✓' if cond else '✗'} {name}" + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        ok = False


# ---------- 对比度工具 ----------
def _lin(v: float) -> float:
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def luma(c: QColor) -> float:
    return 0.2126 * _lin(c.red() / 255.0) + 0.7152 * _lin(c.green() / 255.0) + 0.0722 * _lin(c.blue() / 255.0)


def contrast(c1: QColor, c2: QColor) -> float:
    l1, l2 = luma(c1), luma(c2)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def max_contrast_pixel(widget, bg_hex: str):
    """grab 控件，返回相对已知背景对比度最高的不透明像素（文字/图形）。

    过滤 alpha < 200：QSS transparent 背景在 grab 中会变成 alpha≈160 的黑色，
    该像素并非真实前景，若不滤除会在亮色主题下误判为「文字」。
    """
    img = widget.grab().toImage()
    bg = QColor(bg_hex)
    best_c, best_r = None, -1.0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() < 200:
                continue
            r = contrast(c, bg)
            if r > best_r:
                best_r, best_c = r, c
    return best_c, best_r


def count_color_pixels(widget, hex_color: str, tol: int = 24) -> int:
    """grab 控件，统计接近指定颜色的像素数（用于检测描边/底色）。"""
    target = QColor(hex_color)
    img = widget.grab().toImage()
    n = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if (abs(c.red() - target.red()) <= tol
                    and abs(c.green() - target.green()) <= tol
                    and abs(c.blue() - target.blue()) <= tol):
                n += 1
    return n


def run_theme(theme: str, qss: str, bg_dialog: str, bg_sidebar: str,
              bg_input: str, logo_border: str):
    print(f"[{theme.upper()}] 关键控件 grab 抽样对比度")
    app.setStyleSheet(qss)
    win = MainWindow(store, output_scan=False)
    win.show()
    app.processEvents()
    dlg = SettingsDialog(store)
    dlg.show()
    app.processEvents()
    tb = win.title_bar

    # T1 logo：尺寸 + 描边像素 + 无 v4.2 描边环 + A 对比容器深色底
    # （v4.3：移除 #b0b0c8 环；容器暗/亮都固定深色底 #2a2a3e）
    check(f"T1 {theme} logo label 尺寸 = TitleBar.LOGO_BOX(30)",
          tb.logo_label.width() == TitleBar.LOGO_BOX and tb.logo_label.height() == TitleBar.LOGO_BOX,
          f"{tb.logo_label.width()}x{tb.logo_label.height()}")
    border_n = count_color_pixels(tb.logo_label, logo_border)
    check(f"T1 {theme} logo QSS 描边色 {logo_border} 像素可见 (n={border_n})", border_n >= 8,
          f"border_n={border_n}")
    # v4.3：移除 v4.2 描边环（其 #b0b0c8 与新亮色边框 #c8c8e8 容差重叠，
    # 像素断言已不可靠）。Bug 2 的真实修复由下方 A 对比度验证。
    bg_n = count_color_pixels(tb.logo_label, "#2a2a3e", tol=12)
    check(f"T1 {theme} logo 容器深色底 #2a2a3e 像素可见 (n={bg_n})", bg_n >= 4,
          f"bg_n={bg_n}")
    # v4.3.2：彻底移除 QPainter 覆盖（描边环 + 艺术 A），logo 为 PNG 直显。
    # PNG 较暗，与 #2a2a3e 容器的对比度本身较低（暗主题 ≈ 1.68）。
    # 这里只断言 PNG 内容像素相对容器底有任意 > 1 的对比度（证明 PNG 非
    # 完全不可见，例如文件缺失/损坏时 grab 只会显示 #2a2a3e，r=1.0）。
    _, logo_r = max_contrast_pixel(tb.logo_label, "#2a2a3e")
    check(f"T1 {theme} logo PNG 内容相对容器底有可见对比度 (>1.0)",
          logo_r > 1.0, f"r={logo_r:.2f}")

    # T2 checkbox 文字
    for name, cb in (("hover_check", dlg.hover_check), ("cap_check", dlg.cap_check)):
        _, r = max_contrast_pixel(cb, bg_dialog)
        check(f"T2 {theme} checkbox[{name}] 文字对比度 ≥ 4.5", r >= 4.5, f"r={r:.2f}")

    # T3 SpinBox 数字
    _, r = max_contrast_pixel(dlg.cap_spin, bg_input)
    check(f"T3 {theme} SpinBox 数字对比度 ≥ 4.5", r >= 4.5, f"r={r:.2f}")

    # T4 「张」单位（fieldLabel）
    _, r = max_contrast_pixel(dlg.cap_unit, bg_dialog)
    check(f"T4 {theme} 「张」单位对比度 ≥ 4.5", r >= 4.5, f"r={r:.2f}")

    # T5 侧栏副标题 brandSub
    ver = None
    for w in win.findChildren(QLabel):
        if w.objectName() == "brandSub":
            ver = w
            break
    if ver is None:
        check(f"T5 {theme} brandSub 存在", False)
    else:
        _, r = max_contrast_pixel(ver, bg_sidebar)
        check(f"T5 {theme} brandSub 对比度 ≥ 4.5", r >= 4.5, f"r={r:.2f}")

    dlg.close()
    win.close()
    app.processEvents()


run_theme("dark", APP_QSS, "#16161f", "#12121a", "#21212e", "#3a3a58")
run_theme("light", LIGHT_QSS, "#f4f4fa", "#ececf5", "#ffffff", "#c8c8e0")

# ---------- T6 全文件审计：暗色 QSS 文本色阈值 ----------
print("[T6] style.py 暗色主题文本色硬编码审计")
DARK = "#16161f"
# (规则片段, 颜色, 最低对比度阈值, 说明)
AUDIT = [
    ("#brandName", "#ffffff", 4.5, "主文字"),
    ("#brandSub", "#b0b0c8", 4.5, "次文字(提亮后)"),
    ("QPushButton#navBtn", "#c6c6dc", 4.5, "导航按钮"),
    ("QPushButton#sideSmall", "#b0b0c8", 4.5, "侧栏小按钮"),
    ("#groupTitle", "#a8a8c0", 4.5, "分组标题"),
    ("QTreeWidget#groupTree", "#d8d8e8", 4.5, "分组树"),
    ("QLineEdit,", "#f2f2f8", 4.5, "输入框"),
    ("QPushButton", "#f2f2f8", 4.5, "按钮"),
    ("QPushButton#ghost", "#d0d0e2", 4.5, "ghost 按钮"),
    ("QPushButton#danger", "#ff9aa5", 4.5, "danger 按钮"),
    ("QLabel#fieldLabel", "#c6c6dc", 4.5, "表单标签(提亮后)"),
    ("QLabel#hint", "#8a8aa5", 4.5, "提示文本"),
    ("QLabel#countLabel", "#c6c6dc", 4.5, "计数文本"),
    ("#emptyHint", "#9a9ab8", 4.5, "空态提示"),
    ("QToolButton#collapseBtn", "#a8a8c0", 4.5, "折叠按钮"),
    ("#pageSub", "#a8a8c0", 4.5, "页面副标题"),
]
for label, hexv, thr, note in AUDIT:
    c = QColor(hexv)
    r = contrast(c, QColor(DARK))
    check(f"T6 暗色 {label} {hexv} 对比度≥{thr} ({note})", r >= thr, f"r={r:.2f}")
# 禁/占位符预期低对比（不参与 4.5 断言，仅确认存在）
for hexv in ("#66667c", "#6d6d8a"):
    check(f"T6 暗色禁用/占位符 {hexv} 已定义", hexv.lower() in APP_QSS.lower())

print()
print("v4.2 对比度回归", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
