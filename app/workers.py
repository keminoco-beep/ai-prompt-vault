"""后台任务：网络下载与 Civitai 提取（不阻塞 UI）。

注意：WorkerSignals 必须由调用方 parented 到一个长期存在的 QObject（如主面板），
否则 QRunnable 被 QThreadPool 自动删除后，TaskSignals 容易随之销毁或成为孤儿，
导致 done/failed 信号在跨线程投递过程中被丢弃，UI 永远收不到回调。
"""
import re

from PySide6.QtCore import QRunnable, Signal, QObject

from app.i18n import t as tr, tr_format
from app import civitai


class WorkerSignals(QObject):
    done = Signal(object)   # dict 结果
    failed = Signal(str)


class Worker(QRunnable):
    """在 QThreadPool 中执行 fn，结果通过外部传入的 signals 报告。

    signals 必须 parented 到一个长期存在的 QObject（如主面板）。
    """

    def __init__(self, signals: WorkerSignals, fn, *args, **kwargs):
        super().__init__()
        self.signals = signals
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        if self._cancelled:
            return
        try:
            result = self.fn(*self.args, **self.kwargs)
        except Exception as e:  # noqa: BLE001
            try:
                self.signals.failed.emit(f"{type(e).__name__}: {e}")
            except RuntimeError:
                pass  # signals 已被销毁（极端边界）
            return
        if self._cancelled:
            return
        try:
            self.signals.done.emit(result)
        except RuntimeError:
            pass


# ---------------- 具体任务 ----------------
def _log_import_error(store, link: str, err: str):
    """把导入失败写入 资料库/import.log，便于定位网络问题。"""
    import datetime
    try:
        from app.config import library_dir
        f = library_dir() / "import.log"
        line = f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {link} -> {err}\n"
        with open(f, "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


def import_civitai(store, link: str) -> dict:
    """提取 Civitai 链接信息并下载图片。返回 {fields, image_file, error}。"""
    try:
        parsed = civitai.parse_link(link)
        if not parsed:
            return {"fields": None, "image_file": None, "error": tr("无法识别的 Civitai 链接")}
        if parsed["kind"] == "image":
            info = civitai.fetch_image(parsed["id"])
        elif parsed["kind"] == "model":
            info = civitai.fetch_model(parsed["id"])
        else:
            info = civitai.fetch_model_version(parsed["id"])
    except Exception as e:  # noqa: BLE001
        _log_import_error(store, link, f"{type(e).__name__}: {e}")
        raise
    # fetch_* 返回的已是完整记录字段（含 meta 归一化结果），无需再次转换
    fields = dict(info)
    fields["source_url"] = link

    image_file = None
    error = ""
    url = fields.get("image_url") or ""
    if url:
        ext = "jpg"
        m = re.search(r"\.(png|jpe?g|webp|gif|bmp)(?:$|[?/])", url, re.I)
        if m:
            ext = "png" if m.group(1).lower() == "png" else "jpg"
        name = store.next_image_name(ext)
        ok, err = civitai.download_image(url, str(store.images_dir / name))
        if ok:
            image_file = name
        else:
            error = tr_format("图片下载失败（{err}）", err=err)
            _log_import_error(store, link, error)
    return {"fields": fields, "image_file": image_file, "error": error}


def download_web_image(store, url: str) -> dict:
    ext = "jpg"
    m = re.search(r"\.(png|jpe?g|webp|gif|bmp)(?:$|[?/])", url, re.I)
    if m:
        ext = "png" if m.group(1).lower() == "png" else "jpg"
    name = store.next_image_name(ext)
    ok, err = civitai.download_image(url, str(store.images_dir / name))
    if not ok:
        return {"image_file": None, "error": tr_format("图片下载失败（{err}）", err=err)}
    return {"image_file": name, "error": ""}


def copy_local_file(store, path: str) -> dict:
    try:
        name = store.copy_file_into(path)
        return {"image_file": name, "error": ""}
    except Exception as e:  # noqa: BLE001
        return {"image_file": None, "error": tr_format("复制文件失败（{e}）", e=e)}
