"""One-command build script: produces dist/AI绘图资料整理.exe (Windows, single file).

Usage:
    pip install pyinstaller
    python build.py

打包瘦身（T01）：
    在 PyInstaller 运行前，把 site-packages/PySide6/ 下无用的 Qt 二进制栈
    （QML/Quick/PDF/SVG/OpenGL/虚拟键盘 + 多余翻译）临时移入
    build/_pyside6_trim/，构建结束后（try/finally）原样移回。

    为什么必须这样做：
      --exclude-module 只能删 Python 模块，删不掉 Qt DLL —— PySide6 hook 会
      按目录收集插件二进制，并连带收集其 DLL 依赖：
        qtvirtualkeyboardplugin -> Qt6VirtualKeyboard -> Qt6Qml/Qt6Quick/Qt6OpenGL
        qpdf -> Qt6Pdf；qsvg/qsvgicon -> Qt6Svg
      且 hook 无条件收集 opengl32sw.dll（约 20.6MB）。
      因此采用「构建期二进制预裁剪」：移动而非删除，保证可恢复。
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD_DIR = ROOT / "build"
# 临时备份目录（位于 build/ 下；main() 开头会先恢复残留备份再清理 build/）
TRIM_DIR = BUILD_DIR / "_pyside6_trim"

APP_NAME = "AI绘图资料整理"
ICON = ROOT / "app.ico"
MAIN = ROOT / "main.py"

# --------------------------------------------------------------------------
# PySide6 安装目录：动态定位（本机/CI 兼容）
# --------------------------------------------------------------------------
try:
    import PySide6
except ImportError as exc:  # pragma: no cover - 构建环境问题
    print(f"FATAL: PySide6 未安装或无法导入: {exc}")
    sys.exit(2)
PYSIDE = Path(PySide6.__file__).resolve().parent

# --------------------------------------------------------------------------
# 二进制预裁剪清单（相对 PYSIDE 目录）
# --------------------------------------------------------------------------
# QML/Quick/PDF/SVG/OpenGL/虚拟键盘 栈的 DLL（Qt6Pdf 在 6.5+ 拆分为 Qt6Pdf.dll，
# Qt6Quick/Qt6Qml 为 QtMultimedia 之外完全无用的前端栈）
TRIM_DLLS = [
    "Qt6Qml.dll",
    "Qt6QmlModels.dll",
    "Qt6QmlMeta.dll",
    "Qt6QmlWorkerScript.dll",
    "Qt6Quick.dll",
    "Qt6VirtualKeyboard.dll",
    "Qt6OpenGL.dll",
    "Qt6Pdf.dll",
    "Qt6Svg.dll",
    "opengl32sw.dll",
]
# 对应插件（目录扫描型收集，移走即不收集；同时切断上述 DLL 依赖链）
TRIM_PLUGINS = [
    "plugins/platforminputcontexts/qtvirtualkeyboardplugin.dll",
    "plugins/imageformats/qpdf.dll",
    "plugins/imageformats/qsvg.dll",
    "plugins/iconengines/qsvgicon.dll",
]
# 翻译：只保留 QFileDialog 按钮文案依赖的语言（qtbase_zh_CN/ja/es），其余 .qm 全部移走
KEEP_TRANSLATIONS = {"qtbase_zh_CN.qm", "qtbase_ja.qm", "qtbase_es.qm"}

# --------------------------------------------------------------------------
# PyInstaller 模块排除
# 必须保留：PySide6.QtMultimedia（video_meta 用）/ QtGui / QtWidgets / QtCore / QtNetwork
# --------------------------------------------------------------------------
EXCLUDE = [
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore", "PySide6.QtCharts",
    "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtHttpServer",
    "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtPositioning",
    "PySide6.QtLocation", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "PySide6.QtSensors", "PySide6.QtSerialPort", "PySide6.QtSql",
    "PySide6.QtStateMachine", "PySide6.QtTest", "PySide6.QtWebChannel",
    "PySide6.QtWebSockets", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtMultimediaWidgetsQuick", "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2", "PySide6.QtQuickWidgets", "PySide6.QtDesigner",
    "PySide6.QtHelp",
    # 与二进制预裁剪配套的模块排除（DLL 已移走，Python 模块一并排除）
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets",
    "PySide6.QtSvg", "PySide6.QtSvgWidgets",
    "PySide6.QtVirtualKeyboard",
]


def py_bin() -> str:
    return sys.executable


def find_dll(name: str) -> Path:
    """locate OpenSSL DLLs shipped with the Python runtime (if any).

    venv 下 DLLs 目录位于 base_prefix（如 envs/default -> versions/3.13.12），
    因此同时搜索 sys.base_prefix，保证与旧构建行为一致。
    """
    exe = Path(sys.executable)
    bases = [exe.parent, Path(sys.base_prefix) / "DLLs", Path(sys.base_prefix)]
    for base in bases:
        for candidate in [base / "DLLs" / name, base / name]:
            if candidate.exists():
                return candidate
    return None


def _kill_running_app() -> None:
    """结束可能占用 dist/ 或 PySide6 DLL 的旧进程，避免文件锁。"""
    if os.name != "nt":
        return
    try:
        subprocess.run(["taskkill", "/F", "/IM", f"{APP_NAME}.exe"],
                       capture_output=True, check=False)
    except OSError as exc:
        print(f"  [warn] taskkill 不可用: {exc}")


def _trim_pyside6_backup() -> None:
    """构建前把无用 Qt 二进制移入临时备份目录（移动而非删除，保证可恢复）。"""
    if not PYSIDE.is_dir():
        print(f"  [skip] PySide6 目录不存在: {PYSIDE}")
        return
    TRIM_DIR.mkdir(parents=True, exist_ok=True)
    moved = 0
    for rel in TRIM_DLLS + TRIM_PLUGINS:
        src = PYSIDE / rel
        if not src.exists():
            print(f"  [skip] {rel} 不存在（可能已被裁剪）")
            continue
        dst = TRIM_DIR / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        moved += 1
    # 翻译：保留 qtbase_zh_CN/ja/es，其余 .qm 全部移走
    tr_dir = PYSIDE / "translations"
    if tr_dir.is_dir():
        tr_backup = TRIM_DIR / "translations"
        tr_backup.mkdir(parents=True, exist_ok=True)
        for qm in tr_dir.glob("*.qm"):
            if qm.name in KEEP_TRANSLATIONS:
                continue
            shutil.move(str(qm), str(tr_backup / qm.name))
            moved += 1
    print(f"[trim] 已移走 {moved} 个 PySide6 文件 -> {TRIM_DIR}")


def _restore_pyside6() -> None:
    """构建后把临时备份的文件移回 site-packages（幂等：无备份则跳过）。"""
    if not TRIM_DIR.is_dir():
        return
    restored = 0
    for src in sorted(TRIM_DIR.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(TRIM_DIR)
        dst = PYSIDE / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        restored += 1
    # 清理备份目录中的空目录
    for d in sorted(TRIM_DIR.rglob("*"), reverse=True):
        if d.is_dir():
            try:
                d.rmdir()
            except OSError:
                pass
    if restored:
        print(f"[restore] 已移回 {restored} 个 PySide6 文件 -> {PYSIDE}")


def main() -> int:
    # CI/Windows 下 stdout/stderr 默认 cp1252，打印中文会 UnicodeEncodeError（历史复发坑）
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    # 崩溃恢复：上次构建若异常中断，先移回残留备份，再清理 build/（避免误删备份）
    _restore_pyside6()

    if os.name != "nt":
        print("Note: on non-Windows platforms PyInstaller still builds, "
              "but the exe is intended for Windows.")

    _kill_running_app()
    # clean：只清理构建产物与旧 exe，**绝不删除 dist/Library（用户数据目录）**
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR, ignore_errors=True)
    DIST.mkdir(exist_ok=True)
    for f in DIST.glob("*.exe"):
        try:
            f.unlink(missing_ok=True)
        except OSError:
            pass

    cmd = [py_bin(), "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed",
           "--name", APP_NAME, f"--icon={ICON}",
           "--optimize", "1", "--noupx"]
    for mod in EXCLUDE:
        cmd.append(f"--exclude-module={mod}")
    # include OpenSSL DLLs if present (required by requests on some runtimes)
    for dll in ("libssl-3-x64.dll", "libcrypto-3-x64.dll"):
        p = find_dll(dll)
        if p:
            cmd.append(f"--add-binary={p};.")
    cmd.append(str(MAIN))

    # 构建期二进制预裁剪：PyInstaller 运行前移走无用 Qt 二进制，结束后必定移回
    _trim_pyside6_backup()
    try:
        print("Running:", " ".join(cmd))
        code = subprocess.call(cmd, cwd=str(ROOT))
    finally:
        _restore_pyside6()

    if code != 0:
        print("Build failed.")
        return code
    exe = DIST / f"{APP_NAME}.exe"
    size_bytes = exe.stat().st_size
    print(f"Done: {exe} ({size_bytes / 1e6:.1f} MB decimal, "
          f"{size_bytes / 1024 / 1024:.2f} MiB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
