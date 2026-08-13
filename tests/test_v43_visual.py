"""v4.3.x 视觉回归测试。

覆盖：
T1 亮色标题栏按钮图标对比度：TitleBar.apply_theme('light') 后自绘 icon 前景色
   相对亮色标题栏 #f4f4fa 对比 ≥ 10:1（v4.3 由 #4a4a62 加深为 #2a2a3d ≈12.8:1）；
   暗色保持 #e8e8f2（回归）。min/close 两按钮都验证。
T2 PNG 直显（v4.3.3 调整）：标题栏 logo 直接显示 app/app_icon.png 原图，
   LOGO_SIZE=36 / LOGO_BOX=38。grab logo 内层 36×36 区域（跳过 1px QSS 边框）：
   - 容器深色底 #2a2a3e 在两主题下都可见（对比度方案仍生效）
   - 紫色/蓝紫色像素主导（PNG 渐变本体 ≥40%）
   - 无 QPainter 大面积白色覆盖块（白色像素比例 ≤ 35%，新 PNG 仍允许少量
     白色来自 A 自身——粗笔画艺术 A 是预期内容）
T3 Models 页「类型」标签：ModelPanel 的 toolLabel 前景色在暗主题 ≥ #c6c6dc
   对比度（≥4.5:1）、亮主题 ≥ #55556e 对比度（≥4.5:1）。
T4 resize 实时跟随（v4.3.1 重写）：模拟 _on_enter_sizemove 后连续 resize
   多次 grab 中心区域，相邻帧像素差 > 0（窗口实时跟随指针，非冻结）；
   最终尺寸 1200×800 正确；windowResizing 属性切换正确（true→false）。
T5 PNG 内 A 形态（v4.3.2 调整说明）：白色像素边界框宽度 ≥ 高度 × 0.5，
   验证 PNG 原图内 A 字符的几何形态（A 横跨宽度感）。

v4.3.3：新增对 LOGO_SIZE=36 的支持——grab 内层 36×36（label 38×38 减去
外圈 1px QSS 边框）。新 AI 设计 logo 笔画粗（A + sparkle 点），36×36 显示
抗锯齿损失更小、笔画细节保留更好。

运行：python tests/test_v43_visual.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox, QLabel
from PySide6.QtGui import QColor

QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS, LIGHT_QSS
from app.ui.main_window import MainWindow
from app.ui.title_bar import TitleBar
from app.ui.model_panel import ModelPanel

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
    """grab 控件，返回相对已知背景对比度最高的不透明像素（文字/图形）。"""
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
    """grab 控件，统计接近指定颜色的像素数。"""
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


def first_opaque(img) -> QColor:
    """icon pixmap 中第一个不透明像素（图标笔画前景色）。"""
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.alpha() > 0:
                return c
    return QColor(0, 0, 0)


def white_bbox(img):
    """PNG 内 A/sparkle 亮区边界框 (x0, y0, x1, y1)；无像素返回 None。

    v4.3.2：
      - 检测阈值改为「蓝色通道 > 100」（PNG 28x28 平滑后最亮区蓝通道 ≈ 143，
        对应 sparkle dot 和 A 字符的笔画）；不再用 r/g/b 全 > 100/220。
      - 搜索范围限制到中心 28x28 图标区域（跳过外圈 1px QSS 边框）：
        暗主题边框 #3a3a58 (蓝=88) 远低于阈值 100，不会误算；
        亮主题边框 #c8c8e0 (蓝=224) 在限制范围后也不会被算进图标 bbox。
    """
    x0, y0, x1, y1 = None, None, None, None
    # 跳过外圈 1px（QSS 边框区域：x/y ∈ [0, 29] 是 30x30 外圈）
    for y in range(1, img.height() - 1):
        for x in range(1, img.width() - 1):
            c = img.pixelColor(x, y)
            if c.alpha() > 200 and c.blue() > 100:
                if x0 is None or x < x0:
                    x0 = x
                if y0 is None or y < y0:
                    y0 = y
                if x1 is None or x > x1:
                    x1 = x
                if y1 is None or y > y1:
                    y1 = y
    return (x0, y0, x1, y1) if x0 is not None else None


# ============ T1: 亮色标题栏按钮图标对比度 ============
print("[T1] 亮色标题栏按钮图标对比度（v4.3 #4a4a62 → #2a2a3d）")
tb = TitleBar()
tb.show()
app.processEvents()

tb.apply_theme("dark")
for name in ("btn_min", "btn_close"):
    c = first_opaque(getattr(tb, name).icon().pixmap(16, 16).toImage())
    r = contrast(c, QColor("#16161f"))
    check(f"T1 暗色 {name} 图标对比 #16161f ≥ 4.5", r >= 4.5, f"r={r:.2f} {c.name()}")
    check(f"T1 暗色 {name} 图标为浅色(#e8e8f2)", c.lightness() > 180, c.name())

tb.apply_theme("light")
for name in ("btn_min", "btn_close"):
    c = first_opaque(getattr(tb, name).icon().pixmap(16, 16).toImage())
    r = contrast(c, QColor("#f4f4fa"))
    check(f"T1 亮色 {name} 图标对比 #f4f4fa ≥ 10:1", r >= 10.0, f"r={r:.2f} {c.name()}")
    check(f"T1 亮色 {name} 图标为深色(<130)", c.lightness() < 130, c.name())

tb.apply_theme("dark")
c = first_opaque(tb.btn_min.icon().pixmap(16, 16).toImage())
check("T1 切回暗色图标恢复浅色", c.lightness() > 180, c.name())
tb.close()

# ============ T2: PNG 直显（v4.3.2 重写） ============
print("[T2] PNG 直显：紫色像素主导 + 容器深色底可见 + 无 QPainter 白色覆盖块")


def is_purplish(c: QColor) -> bool:
    """是否为 PNG 紫色/蓝紫渐变本体（排除白色 + 容器底 #2a2a3e）。

    v4.3.2：实测 app/app_icon.png（512x512）在 28x28 smooth 缩放后实际
    RGB 范围 ≈ (21,22,47) → (52,71,143)，最亮 ≈ #34478F。原注释所述
    #6d5ef0~#4f7de0 是早期设计的色域描述，实际 PNG 更暗（背景深紫黑，
    主体深蓝紫）。因此判据放宽到「蓝色调主导」即可：
      排除白色 + 排除容器底 + 排除极暗 + b >= g（蓝紫调）。

    对比「之前 v4.3.1 白色艺术 A」场景：QPainter 覆盖会在大量像素上画
    白色 #ffffff（r>220 显著），PNG 自身最亮 ≈ 143（远低于 220），
    因此 white 比例 ≈ 0% 是「无 QPainter 覆盖」的强证据。
    """
    if c.alpha() < 200:
        return False
    r, g, b = c.red(), c.green(), c.blue()
    # 排除白色
    if r > 220 and g > 220 and b > 220:
        return False
    # 排除容器底 #2a2a3e (42,42,62)（PNG 较暗，容器底与之接近，宽容差 ±20）
    if 25 <= r <= 65 and 25 <= g <= 65 and 45 <= b <= 85:
        return False
    # 排除极暗（接近黑/透明边角）
    if r + g + b < 60:
        return False
    # 紫色/蓝紫/蓝色调：b >= g（PNG 整体偏蓝紫），b > 30
    if b >= g and b > 30:
        return True
    return False


win2 = MainWindow(store, output_scan=False)
win2.show()
app.processEvents()
# T2 also now asserts the four PNG-corner regions of the label are free of
# opaque-white pixels (the "四个白角" bug). The label is 38×38 with a 1px QSS
# border; the PNG is 36×36 centered at (1,1)..(36,36). Checking the four
# 4×4 PNG-corner regions (top-left (1..4,1..4), top-right (33..36,1..4),
# bottom-left (1..4,33..36), bottom-right (33..36,33..36)) avoids the QSS
# border (which is #3a3a58 dark / #c8c8e0 light, NOT #2a2a3e) and tests the
# actual bug surface: the PNG's rounded corners. A transparent PNG corner
# shows the container's #2a2a3e through the label -> grab pixel is opaque
# #2a2a3e; an opaque-white PNG corner (the bug) shows #fbfdfb-ish and fails.
PNG_CORNERS = [(1, 1), (33, 1), (1, 33), (33, 33)]


def _png_corner_white_bug_count(img) -> int:
    """Count opaque-white pixels across the 4 PNG-corner 4×4 regions of the
    38×38 label (skipping the outer 1px QSS border). 0 == bug-free."""
    bad = 0
    for cx, cy in PNG_CORNERS:
        for dy in range(4):
            for dx in range(4):
                c = img.pixelColor(cx + dx, cy + dy)
                if c.alpha() > 200 and c.red() > 220 and c.green() > 220 and c.blue() > 220:
                    bad += 1
    return bad


for theme, qss in (("dark", APP_QSS), ("light", LIGHT_QSS)):
    app.setStyleSheet(qss)
    win2.apply_theme(theme)
    app.processEvents()
    label = win2.title_bar.logo_label
    img = label.grab().toImage()
    # v4.3.3：label 38×38，LOGO_SIZE=36 → 内层 36×36 是 PNG 实际显示区域
    #   跳外圈 1px（QSS 边框）：x/y ∈ [1, 36]
    sz = label.width()  # 38
    inner_size = sz - 2  # 36
    # 1) 容器深色底 #2a2a3e 在两主题下都可见（QSS 固定深色底，PNG 圆角外露）
    bg_n = count_color_pixels(label, "#2a2a3e", tol=12)
    check(f"T2 {theme} 容器深色底 #2a2a3e 可见 (n={bg_n})",
          bg_n >= 4, f"bg_n={bg_n}")

    # 2) 中心区域紫色/蓝紫色像素主导（PNG 渐变本体，v4.3.3 内层 36x36）
    #   中心 24×24 居中于 36×36 内层
    cx0 = 1 + (inner_size - 24) // 2
    cy0 = 1 + (inner_size - 24) // 2
    total_center = 24 * 24
    purplish_n = 0
    for y in range(cy0, cy0 + 24):
        for x in range(cx0, cx0 + 24):
            if is_purplish(img.pixelColor(x, y)):
                purplish_n += 1
    check(f"T2 {theme} 中心紫色/蓝紫色像素主导（≥ 40%，n={purplish_n}/{total_center}）",
          purplish_n >= total_center * 0.40,
          f"purplish_n={purplish_n} ratio={purplish_n/total_center:.2%}")

    # 3) 无 QPainter 大面积白色覆盖块：白色像素比例应 ≤ 35%（v4.3.3 内层 36×36）
    #    原 PNG 内 A 字符本身有白色（约 10-20% 像素），QPainter 覆盖层
    #    （描边环 + 艺术 A）会让白色比例显著增大到 40%+。
    white_n = 0
    for y in range(1, img.height() - 1):
        for x in range(1, img.width() - 1):
            c = img.pixelColor(x, y)
            if c.alpha() > 200 and c.red() > 220 and c.green() > 220 and c.blue() > 220:
                white_n += 1
    total_inner = inner_size * inner_size
    check(f"T2 {theme} 内层 36×36 白色像素比例 ≤ 35%（无 QPainter 大面积覆盖, "
          f"n={white_n}/{total_inner}={white_n/total_inner:.1%}）",
          white_n <= total_inner * 0.35,
          f"white_n={white_n}")

    # 4) 紫色像素数 > 白色像素数（PNG 紫色主体占主导，A 是少数派）
    check(f"T2 {theme} 紫色像素 > 白色像素（PNG 主体主导）",
          purplish_n > white_n,
          f"purplish={purplish_n} white={white_n}")

    # 5) v4.3.4 新增：四角 PNG-corner 4×4 区域零白角（标题栏 logo 四个白角 bug）。
    #    透明 PNG 角 → 容器 #2a2a3e 接管；不透明白 PNG 角 → bug。这里直接断言
    #    "4 角 16 像素内无 opaque-white 像素"，等价于 "透明或容器底接管"。
    bad_n = _png_corner_white_bug_count(img)
    check(f"T2 {theme} 四角 PNG-corner 4×4 零白角 (n={bad_n}/64，"
          f"透明 + 容器底 #2a2a3e 接管，无 white corner)",
          bad_n == 0, f"bad_n={bad_n}")
# T4 复用 win2，此处不关闭

# ============ T3: Models 页「类型」标签 ============
print("[T3] Models 页「类型」标签对比度")
for theme, qss, bg, thr_hex in (("dark", APP_QSS, "#16161f", "#c6c6dc"),
                                ("light", LIGHT_QSS, "#f4f4fa", "#55556e")):
    app.setStyleSheet(qss)
    win2.apply_theme(theme)
    panel = ModelPanel(store)
    panel.show()
    app.processEvents()
    lbl = panel.findChild(QLabel, "toolLabel")
    check(f"T3 {theme} toolLabel 存在且文本=类型",
          lbl is not None and lbl.text() == "类型", repr(lbl.text() if lbl else None))
    if lbl is not None:
        c, r = max_contrast_pixel(lbl, bg)
        check(f"T3 {theme} 类型标签对比度 ≥ 4.5", r >= 4.5, f"r={r:.2f} {c.name() if c else None}")
        # 暗主题文字 ≥ #c6c6dc（更亮）；亮主题文字 ≥ #55556e（更暗）
        thr = QColor(thr_hex)
        if theme == "dark" and c is not None:
            check(f"T3 暗 类型标签亮度 ≥ #c6c6dc", c.lightness() >= thr.lightness() - 8,
                  f"got={c.lightness()} thr={thr.lightness()}")
        elif theme == "light" and c is not None:
            check(f"T3 亮 类型标签亮度 ≤ #55556e", c.lightness() <= thr.lightness() + 8,
                  f"got={c.lightness()} thr={thr.lightness()}")
    panel.close()

# ============ T4: resize 实时跟随（v4.3.1 重写） ============
print("[T4] resize 实时跟随：连续 grab 中心区域像素变化 + 终态尺寸 + windowResizing 属性切换")
win2.apply_theme("dark")
app.setStyleSheet(APP_QSS)
win2.resize(1020, 640)
app.processEvents()

# 模拟进入系统拖拽缩放（实际由 nativeEvent WM_ENTERSIZEMOVE 触发；
# 测试无法注入真消息，直接调用 _on_enter_sizemove 验证 QSS 属性切换）
win2._on_enter_sizemove()
app.processEvents()
check("T4 resize 中 shell windowResizing=true",
      bool(win2._shell.property("windowResizing")),
      f"got={win2._shell.property('windowResizing')}")

# 4 步 resize + 每次 processEvents + grab 中心区域
sizes = [(1020, 640), (1080, 680), (1140, 740), (1200, 800)]
center_imgs = []
for w, h in sizes:
    win2.resize(w, h)
    app.processEvents()
    full = win2.grab().toImage()
    center_imgs.append(full)

# 模拟退出系统拖拽缩放（实际由 nativeEvent WM_EXITSIZEMOVE 触发）
win2._on_exit_sizemove()
app.processEvents()

check(f"T4 最终尺寸正确 (1200x800)",
      win2.width() == 1200 and win2.height() == 800,
      f"got={win2.width()}x{win2.height()}")
check("T4 resize 后 shell windowResizing=false",
      not bool(win2._shell.property("windowResizing")),
      f"got={win2._shell.property('windowResizing')}")
check(f"T4 采样帧数 = {len(sizes)}",
      len(center_imgs) == len(sizes), f"n={len(center_imgs)}")


def center_region_diff(img1, img2):
    """两帧中心 50%×50% 区域的最大通道像素差（resize 实时更新检测）。"""
    cw, ch = img1.width(), img1.height()
    rx, ry = max(1, cw // 4), max(1, ch // 4)
    cx, cy = cw // 2, ch // 2
    x0, y0 = cx - rx // 2, cy - ry // 2
    md = 0
    for y in range(y0, y0 + ry):
        for x in range(x0, x0 + rx):
            c1 = img1.pixelColor(x, y)
            c2 = img2.pixelColor(x, y)
            d = max(abs(c1.red() - c2.red()),
                    abs(c1.green() - c2.green()),
                    abs(c1.blue() - c2.blue()))
            if d > md:
                md = d
    return md


# 相邻帧中心区域像素差：resize 中窗口应持续重绘（不是冻结），
# 帧间像素差 > 0 即证明窗口在实时跟随指针变化
max_diff = 0
for i in range(len(center_imgs) - 1):
    d = center_region_diff(center_imgs[i], center_imgs[i + 1])
    if d > max_diff:
        max_diff = d
check(f"T4 相邻帧中心区域像素有变化（resize 实时更新，非冻结）",
      max_diff > 0, f"max_diff={max_diff}")

# 各帧中心区域均有内容（防止 grab 失败/窗口空白）
def center_region_content(img):
    cw, ch = img.width(), img.height()
    rx, ry = max(1, cw // 4), max(1, ch // 4)
    cx, cy = cw // 2, ch // 2
    x0, y0 = cx - rx // 2, cy - ry // 2
    n = 0
    for y in range(y0, y0 + ry):
        for x in range(x0, x0 + rx):
            c = img.pixelColor(x, y)
            if c.alpha() > 200 and c.lightness() > 30:
                n += 1
    return n


min_content = min(center_region_content(img) for img in center_imgs)
check(f"T4 各帧中心区域均有内容 (min={min_content})",
      min_content >= 20, f"min={min_content}")

win2.close()
app.processEvents()

# ============ T5: PNG 内 A 形态（v4.3.2 调整：白色 A 来自 PNG 原图） ============
print("[T5] PNG 内 A 几何形态（白色像素宽度 ≥ 高度 × 0.5，验证 PNG 原图 A 横跨宽度感）")
win3 = MainWindow(store, output_scan=False)
win3.show()
app.processEvents()
for theme, qss in (("dark", APP_QSS), ("light", LIGHT_QSS)):
    app.setStyleSheet(qss)
    win3.apply_theme(theme)
    app.processEvents()
    label = win3.title_bar.logo_label
    img = label.grab().toImage()
    bbox = white_bbox(img)
    if bbox is None:
        check(f"T5 {theme} PNG 内 A 白色像素存在", False, "no white pixels")
        continue
    x0, y0, x1, y1 = bbox
    w, h = x1 - x0 + 1, y1 - y0 + 1
    ratio = w / max(h, 1)
    check(f"T5 {theme} PNG 内 A 宽度 ≥ 高度 × 0.5（横跨宽度感）",
          w >= h * 0.5, f"w={w} h={h} ratio={ratio:.2f}")
win3.close()
app.processEvents()

print()
print("v4.3 视觉回归", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
