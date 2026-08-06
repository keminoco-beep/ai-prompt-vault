"""应用配置：路径与常量。"""
import sys
from pathlib import Path

APP_NAME = "AI绘图资料整理"      # 中文品牌名（界面按语言显示 tr(APP_NAME)）
APP_NAME_EN = "AIPromptsVault"
VERSION = "2.3.2"

# 资料库文件夹名：固定英文，不随界面语言变化（避免切换语言找不到数据）。
# 旧版中文名「资料库」会在首次启动时自动迁移（见 library_dir）。
LIBRARY_DIR_NAME = "Library"
LIBRARY_DIR_NAME_OLD = "资料库"


def app_dir() -> Path:
    """程序所在目录（打包后为 exe 所在目录；开发时为项目根目录）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def library_dir() -> Path:
    """资料库子文件夹：所有保存的数据（图片/缩略图/索引）都归纳在这里。

    首次运行时若发现旧版中文名「资料库」存在而新名不存在，自动重命名迁移，
    保证老用户数据无缝升级。
    """
    base = app_dir()
    d = base / LIBRARY_DIR_NAME
    if not d.exists():
        old = base / LIBRARY_DIR_NAME_OLD
        if old.exists():
            try:
                old.rename(d)
            except Exception:
                pass
    d.mkdir(parents=True, exist_ok=True)
    return d
