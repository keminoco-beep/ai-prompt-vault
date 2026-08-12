"""应用配置：路径与常量。"""
import sys
from pathlib import Path

# 软件名（中英界面统一显示此名）
APP_NAME = "AI-Prompt-Vault"
VERSION = "3.2.0"

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
    """默认资料库子文件夹：所有保存的数据（图片/缩略图/索引）都归纳在这里。

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


def resolve_library_dir(custom: str = "") -> Path:
    """多资料库：返回实际使用的资料库路径。

    - custom 为空 → 默认资料库（library_dir()，自动迁移旧中文名）
    - custom 非空 → 用户自定义路径（目录不存在时自动创建）
    设置项 library_dir_custom 存在默认库的 settings.json 中，main() 启动时
    先读默认库设置再决定使用哪个库。
    """
    custom = (custom or "").strip()
    if not custom:
        return library_dir()
    d = Path(custom).expanduser().resolve()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        return library_dir()
    return d
