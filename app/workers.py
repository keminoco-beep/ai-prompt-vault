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
    # ---- 视频：下载视频文件 + 首帧缩略图 + 时长（不走图片下载） ----
    if fields.get("media_type") == "video":
        url = fields.get("video_url") or ""
        if not url:
            url = fields.get("image_url") or ""
        vres = download_web_video(store, url)
        if vres.get("video_file"):
            fields["video_file"] = vres["video_file"]
            fields["thumb_file"] = vres["thumb_file"]
            fields["duration"] = vres["duration"]
            return {"fields": fields, "image_file": None,
                    "video_file": vres["video_file"],
                    "thumb_file": vres["thumb_file"],
                    "error": vres["error"]}
        error = vres["error"] or tr("视频下载失败")
        _log_import_error(store, link, error)
        return {"fields": fields, "image_file": None, "video_file": None,
                "thumb_file": "", "error": error}

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
    return {"fields": fields, "image_file": image_file, "video_file": None,
            "thumb_file": "", "error": error}


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


def download_web_video(store, url: str) -> dict:
    """下载 Civitai 视频到 videos/ + 提取首帧缩略图 + 时长。

    返回 {video_file, thumb_file, duration, error}。
    """
    from pathlib import Path
    from app.video_meta import extract_first_frame, video_duration
    if not url:
        return {"video_file": None, "thumb_file": "", "duration": 0,
                "error": tr("视频地址为空")}
    ext = "mp4"
    m = re.search(r"\.(mp4|webm|mov|m4v|mkv|avi)(?:$|[?/])", url, re.I)
    if m:
        ext = m.group(1).lower()
    name = store.next_video_name(ext)
    ok, err = civitai.download_video(url, str(store.videos_dir / name))
    if not ok:
        return {"video_file": None, "thumb_file": "", "duration": 0,
                "error": tr_format("视频下载失败（{err}）", err=err)}
    thumb_name = Path(name).stem + ".png"
    ok_frame = extract_first_frame(str(store.videos_dir / name),
                                   str(store.thumbs_dir / thumb_name))
    duration = 0
    try:
        duration = video_duration(str(store.videos_dir / name))
    except Exception:
        pass
    return {"video_file": name,
            "thumb_file": thumb_name if ok_frame else "",
            "duration": duration or 0,
            "error": ""}


def copy_local_file(store, path: str) -> dict:
    try:
        name = store.copy_file_into(path)
        return {"image_file": name, "error": ""}
    except Exception as e:  # noqa: BLE001
        return {"image_file": None, "error": tr_format("复制文件失败（{e}）", e=e)}


def import_local_video(store, path: str) -> dict:
    """导入本地视频：复制到 videos/ + 提取首帧缩略图。

    返回 {video_file, thumb_file, duration, error}。首帧提取失败不阻塞导入
    （缩略图缺失时 UI 显示视频占位图）。
    """
    from pathlib import Path
    from app.video_meta import extract_first_frame, video_duration, is_video_path
    src = Path(path)
    if not src.is_file() or not is_video_path(src):
        return {"video_file": None, "error": tr("不是受支持的视频文件")}
    try:
        video_name = store.copy_video_into(str(src))
        # 提取首帧缩略图
        thumb_name = Path(video_name).stem + ".png"
        thumb_path = store.thumbs_dir / thumb_name
        duration = 0.0
        ok_frame = extract_first_frame(str(store.videos_dir / video_name),
                                       str(thumb_path))
        if ok_frame:
            duration = video_duration(str(store.videos_dir / video_name))
        return {
            "video_file": video_name,
            "thumb_file": thumb_name if ok_frame else "",
            "duration": duration,
            "error": "",
        }
    except Exception as e:  # noqa: BLE001
        return {"video_file": None, "error": tr_format("复制文件失败（{e}）", e=e)}
