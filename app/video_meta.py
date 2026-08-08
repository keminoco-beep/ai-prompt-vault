"""视频工具：首帧提取与时长获取。

基于 Qt Multimedia（QMediaPlayer + QVideoSink），无外部二进制依赖，
与图片缩略图流程解耦：UI 只调用 extract_first_frame / video_duration。
"""
from PySide6.QtCore import QUrl, QEventLoop, QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink

# 视频扩展名（导入时识别）
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".wmv", ".flv", ".m4v", ".mpg", ".mpeg"}

_FRAME_TIMEOUT_MS = 15000   # 首帧提取超时
_DURATION_TIMEOUT_MS = 8000  # 时长读取超时


def is_video_path(path) -> bool:
    from pathlib import Path
    return Path(path).suffix.lower() in VIDEO_EXTS


def _new_player():
    """创建静音播放器（复用样板代码）。"""
    player = QMediaPlayer()
    audio = QAudioOutput()
    audio.setVolume(0)
    player.setAudioOutput(audio)
    return player


def video_duration(path) -> float:
    """同步获取视频时长（秒）。失败或超时返回 0.0。"""
    try:
        player = _new_player()
        player.setSource(QUrl.fromLocalFile(str(path)))
        loop = QEventLoop()

        def on_status(s):
            if s in (QMediaPlayer.MediaStatus.LoadedMedia,
                     QMediaPlayer.MediaStatus.InvalidMedia):
                loop.quit()

        player.mediaStatusChanged.connect(on_status)
        QTimer.singleShot(_DURATION_TIMEOUT_MS, loop.quit)
        loop.exec()
        d = player.duration()  # ms
        player.stop()
        player.setSource(QUrl())
        return d / 1000.0 if d > 0 else 0.0
    except Exception:
        return 0.0


def extract_first_frame(path, thumb_path, max_side: int = 400) -> bool:
    """提取视频首帧保存为缩略图。返回是否成功。

    - 阻塞直到拿到首帧或超时（15s）
    - 超时/解码失败返回 False（调用方自行兜底显示占位图）
    """
    try:
        player = _new_player()
        sink = QVideoSink()
        result = {"ok": False}
        loop = QEventLoop()

        def on_frame(frame):
            if result["ok"]:
                return
            img = frame.toImage()
            if img.isNull():
                return
            result["ok"] = True
            pm = QPixmap.fromImage(img)
            if max_side > 0 and (pm.width() > max_side or pm.height() > max_side):
                pm = pm.scaled(max_side, max_side, Qt.KeepAspectRatio,
                               Qt.SmoothTransformation)
            result["ok"] = pm.save(str(thumb_path), "PNG")
            loop.quit()

        sink.videoFrameChanged.connect(on_frame)
        player.setVideoSink(sink)
        player.setSource(QUrl.fromLocalFile(str(path)))
        # 兜底：拿到帧立即退出；15s 超时强制退出
        QTimer.singleShot(_FRAME_TIMEOUT_MS, loop.quit)
        player.play()
        loop.exec()
        player.stop()
        player.setSource(QUrl())
        return bool(result["ok"])
    except Exception:
        return False