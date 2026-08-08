"""One-command build script: produces dist/AI绘图资料整理.exe (Windows, single file).

Usage:
    pip install pyinstaller
    python build.py
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"

APP_NAME = "AI绘图资料整理"
ICON = ROOT / "app.ico"
MAIN = ROOT / "main.py"


def py_bin() -> str:
    return sys.executable


def find_dll(name: str) -> Path:
    """locate OpenSSL DLLs shipped with the Python runtime (if any)."""
    exe = Path(sys.executable)
    for candidate in [exe.parent / "DLLs" / name, exe.parent / name]:
        if candidate.exists():
            return candidate
    return None


def main() -> int:
    if os.name != "nt":
        print("Note: on non-Windows platforms PyInstaller still builds, "
              "but the exe is intended for Windows.")
    # clean
    for p in [ROOT / "build", DIST]:
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
    DIST.mkdir(exist_ok=True)

    cmd = [py_bin(), "-m", "PyInstaller", "--noconfirm", "--onefile", "--windowed",
           "--name", APP_NAME, f"--icon={ICON}"]
    # include OpenSSL DLLs if present (required by requests on some runtimes)
    for dll in ("libssl-3-x64.dll", "libcrypto-3-x64.dll"):
        p = find_dll(dll)
        if p:
            cmd.append(f"--add-binary={p};.")
    cmd.append(str(MAIN))

    print("Running:", " ".join(cmd))
    code = subprocess.call(cmd, cwd=str(ROOT))
    if code != 0:
        print("Build failed.")
        return code
    exe = DIST / f"{APP_NAME}.exe"
    print(f"Done: {exe} ({exe.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
