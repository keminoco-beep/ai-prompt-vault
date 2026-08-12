"""AI 绘图资料整理 - 程序入口。

用法：
  python main.py            正常启动
  python main.py --selftest 启动后 2.5 秒自动退出（用于打包自测）
"""
import sys

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont

from app.config import APP_NAME, library_dir, resolve_library_dir
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.main_window import MainWindow


def _run_diag() -> int:
    """诊断模式：测试 exe 环境下的网络与关键依赖，结果写入 exe 同目录 diag.log。"""
    import datetime
    import traceback
    from pathlib import Path

    from app import civitai
    log = []
    log.append(f"diag time: {datetime.datetime.now()}")
    try:
        import requests
        log.append(f"requests: {requests.__version__}")
        log.append(f"certifi: {requests.certs.where()}")
        log.append(f"certifi exists: {Path(requests.certs.where()).exists()}")
        import urllib3
        log.append(f"urllib3: {urllib3.__version__}")
        for host in civitai.HOSTS:
            try:
                r = requests.get(f"https://{host}/images/132699963",
                                 headers=civitai.UA, timeout=15)
                log.append(f"{host}: HTTP {r.status_code} len={len(r.text)}")
            except Exception as e:
                log.append(f"{host}: {type(e).__name__}: {str(e)[:200]}")
        # 完整导入测试
        try:
            info = civitai.fetch_image(132699963, timeout=15)
            log.append(f"fetch_image: OK positive_len={len(info.get('positive') or '')}")
        except Exception as e:
            log.append(f"fetch_image: FAIL {type(e).__name__}: {str(e)[:200]}")
    except Exception:
        log.append("TRACEBACK:\n" + traceback.format_exc())
    out = Path(__file__).resolve().parent / "diag.log" if not getattr(sys, "frozen", False) \
        else Path(sys.executable).resolve().parent / "diag.log"
    out.write_text("\n".join(log), encoding="utf-8")
    print("\n".join(log))
    return 0


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_QSS)
    app.setFont(QFont("Microsoft YaHei UI", 10))

    if "--diag" in sys.argv:
        return _run_diag()

    store = DataStore(library_dir())
    # 多语言初始化：读取默认资料库 settings.json 中的语言偏好
    from app import i18n
    i18n.init(store.settings_path(), store.load_setting("language", "zh"))
    # 多资料库：根据默认库设置决定实际使用的资料库路径
    custom = store.load_setting("library_dir_custom", "")
    if custom:
        store = DataStore(resolve_library_dir(custom))
        i18n.init(store.settings_path(), store.load_setting("language", "zh"))
    # 主题：按保存的设置加载（默认暗色）
    from app.ui import style as st
    st.set_theme(store.load_setting("theme", "dark"))
    app.setStyleSheet(st.qss())

    selftest = "--selftest" in sys.argv
    win = MainWindow(store, output_scan=not selftest)
    win.show()
    if selftest:
        # QTimer 在主线程事件循环内触发退出（跨线程 quit 在 PySide6 下不可靠）
        QTimer.singleShot(2500, app.quit)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
