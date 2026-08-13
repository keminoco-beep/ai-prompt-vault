"""v4.1 新 AI logo 集成 + 侧栏顶部 brand 删除 测试。

覆盖：
T1 MainWindow 构造后侧栏/标题栏不再有 #logoDot QLabel
   （侧栏 brand 已删除；TitleBar logo 改为 PNG pixmap 且 objectName=appLogo）
T2 app.ico 文件存在且合法（含多尺寸 ICO entries）
T3 app/app_icon.png 加载为 QPixmap 非空；TitleBar 的 logo_label pixmap 不为 null

依赖：Pillow（PIL）用于 ICO 验证；如未安装跳过 T2 子项而不整体失败。

运行：python tests/test_v41_logo.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication, QMessageBox, QLabel
from PySide6.QtGui import QPixmap

# 静默化弹窗（避免阻塞测试）
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

from app import i18n
from app.data_store import DataStore
from app.ui.main_window import MainWindow
from app.ui.title_bar import TitleBar
from app.config import APP_NAME, VERSION, app_icon_png_path

app = QApplication([])
td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")

ok = True


def check(name: str, cond: bool, extra: str = "") -> None:
    """断言辅助：失败时打印 ✗ + 上下文，不抛异常以保证后续断言继续运行。"""
    global ok
    print(f"  {'✓' if cond else '✗'} {name}" + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        ok = False


# ============ T1: 侧栏无 logoDot ============
print("[T1] MainWindow 构造后侧栏/窗口无 logoDot QLabel")
win = MainWindow(store, output_scan=False)
logo_dot_labels = win.findChildren(QLabel, name="logoDot")
check("T1 窗口内无 logoDot QLabel", len(logo_dot_labels) == 0,
      f"count={len(logo_dot_labels)}")
# 防御性：窗口仍应保有 TitleBar（logo 改成 appLogo），不应回退到 brand
check("T1 TitleBar 仍存在", win.title_bar is not None)
win.show()
app.processEvents()

# ============ T2: app.ico 文件存在且合法 ICO ============
print("[T2] app.ico 文件存在且为合法 ICO（含多尺寸）")
ico_path = Path("app.ico")
check("T2 app.ico 文件存在", ico_path.is_file(),
      f"path={ico_path.resolve()}")
if ico_path.is_file():
    check("T2 app.ico 非空", ico_path.stat().st_size > 0,
          f"size={ico_path.stat().st_size}")
    try:
        from PIL import Image
        # verify() 会读 + 校验 ICO 头
        Image.open(ico_path).verify()
        # 重新打开读取 sizes（verify 后需 reopen）
        ico_im = Image.open(ico_path)
        check("T2 app.ico 合法 ICO 格式", ico_im.format == "ICO",
              f"format={ico_im.format}")
        sizes = ico_im.ico.sizes() if hasattr(ico_im, "ico") else set()
        check("T2 app.ico 含多尺寸（>=6 种）", len(sizes) >= 6,
              f"sizes={sorted(sizes)}")
        # 期望包含的尺寸
        expected = {(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)}
        check("T2 app.ico 含完整 6 种预期尺寸",
              expected.issubset(set(sizes)),
              f"missing={expected - set(sizes)}")
    except Exception as e:
        check("T2 PIL 可验证 app.ico", False, repr(e))
else:
    check("T2 app.ico 合法 ICO 格式", False, "文件不存在，跳过校验")
    check("T2 app.ico 含多尺寸（>=6 种）", False, "文件不存在，跳过校验")

# ============ T3: app/app_icon.png + TitleBar logo ============
print("[T3] app/app_icon.png 加载 + TitleBar logo_label pixmap 不为 null")
png_path = Path("app/app_icon.png")
check("T3 app/app_icon.png 文件存在", png_path.is_file(),
      f"path={png_path.resolve()}")
check("T3 app_icon_png_path() 指向同位置",
      str(app_icon_png_path().resolve()) == str(png_path.resolve()) or
      app_icon_png_path().name == "app_icon.png",
      f"helper={app_icon_png_path()}")

pm = QPixmap(str(png_path)) if png_path.is_file() else QPixmap()
check("T3 app/app_icon.png 加载为 QPixmap 非空", not pm.isNull(),
      f"size={pm.size().width()}x{pm.size().height()}")
# TitleBar 通过 findChildren 找（objectName=appLogo）；同时 instance 属性 logo_label
tb_logo_labels = win.findChildren(QLabel, name="appLogo")
check("T3 TitleBar 有 appLogo QLabel", len(tb_logo_labels) >= 1,
      f"count={len(tb_logo_labels)}")
if tb_logo_labels:
    tb_pm = tb_logo_labels[0].pixmap()
    check("T3 TitleBar appLogo pixmap 不为 null", not tb_pm.isNull(),
          f"size={tb_pm.size().width()}x{tb_pm.size().height()}")
    # v4.3.3：原硬编码 28 改为读 TitleBar.LOGO_SIZE 常量（v4.3.3 由 28→36）
    check(f"T3 TitleBar appLogo pixmap 尺寸 == {TitleBar.LOGO_SIZE} (LOGO_SIZE)",
          tb_pm.size().width() == TitleBar.LOGO_SIZE
          and tb_pm.size().height() == TitleBar.LOGO_SIZE,
          f"got={tb_pm.size().width()}x{tb_pm.size().height()}")
# 直接访问 TitleBar 实例属性
if win.title_bar is not None and hasattr(win.title_bar, "logo_label"):
    inst_pm = win.title_bar.logo_label.pixmap()
    check("T3 win.title_bar.logo_label.pixmap 非空",
          not inst_pm.isNull(),
          f"size={inst_pm.size().width()}x{inst_pm.size().height()}")

# 收尾：中断后台线程（若有）
win.close()
app.processEvents()

print()
print("v4.1 logo + 侧栏 brand 删除", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)