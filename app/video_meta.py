"""视频工具：首帧提取、时长获取与分辨率读取。

基于 Qt Multimedia（QMediaPlayer + QVideoSink），无外部二进制依赖，
与图片缩略图流程解耦：UI 只调用 extract_first_frame / video_duration / video_size。

v3.7 R1 修复：video_size 原先直接调用 QMediaPlayer.videoSize()——
该属性在 PySide6 中不存在（正确 API 是 QVideoSink.videoSize()），
导致每次都在状态回调里抛 AttributeError、静默吞掉后返回 (0,0)，
表格「尺寸」列恒显示"未知"。修复方案：
1. 优先用纯 stdlib 解析容器头（ISO BMFF mp4/mov/m4v 的 moov/trak/tkhd、
   RIFF avi、EBML webm/mkv）——不依赖 Qt 事件循环，后台线程/offscreen 同样可靠、绝不挂起
2. 其余容器回退 Qt 后端，改用 QVideoSink.videoSize() + 首帧探测，
   并加 QCoreApplication 存在性守卫（无事件循环时直接返回 (0,0)，防挂起）
"""
from PySide6.QtCore import QUrl, QEventLoop, QTimer, Qt
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput, QVideoSink

# 视频扩展名（导入时识别）
VIDEO_EXTS = {".mp4", ".webm", ".mov", ".mkv", ".avi", ".wmv", ".flv", ".m4v", ".mpg", ".mpeg"}

_FRAME_TIMEOUT_MS = 15000   # 首帧提取超时
_DURATION_TIMEOUT_MS = 8000  # 时长读取超时
_SIZE_TIMEOUT_MS = 5000      # 分辨率读取超时


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


# ================= v3.7 R1：纯 stdlib 容器解析（不依赖 Qt 事件循环） =================

def _read_box_header(f, pos, fsize):
    """读取 ISO BMFF box 头。返回 (type, payload_start, payload_size) 或 None。"""
    if pos + 8 > fsize:
        return None
    f.seek(pos)
    hdr = f.read(8)
    if len(hdr) < 8:
        return None
    size = int.from_bytes(hdr[:4], "big")
    btype = hdr[4:8]
    hdr_len = 8
    if size == 1:            # 64-bit largesize
        ext = f.read(8)
        if len(ext) < 8:
            return None
        size = int.from_bytes(ext, "big")
        hdr_len = 16
    elif size == 0:          # 延伸到文件末尾
        size = fsize - pos
    if size < hdr_len:
        return None
    return (btype, pos + hdr_len, size - hdr_len)


def _find_child_box(f, start, end, wanted):
    """在 [start, end) 的兄弟 box 中查找指定类型，返回 (payload_start, payload_size)。"""
    pos = start
    while pos + 8 <= end:
        h = _read_box_header(f, pos, end)
        if h is None:
            break
        btype, pstart, psize = h
        if btype == wanted:
            return (pstart, psize)
        pos += (pstart - pos) + psize
    return None


def _tkhd_size(f, pstart, psize) -> tuple:
    """从 tkhd payload 提取 width/height（16.16 定点数）。"""
    if psize < 84:
        return (0, 0)
    f.seek(pstart)
    ver = f.read(4)[0]
    # 宽高偏移：version+flags(4) + 时间字段(20 或 32) + reserved(8) + layer等(8) + matrix(36)
    off = (4 + 32 + 8 + 8 + 36) if ver == 1 else (4 + 20 + 8 + 8 + 36)
    if psize < off + 8:
        return (0, 0)
    f.seek(pstart + off)
    wb = f.read(4)
    hb = f.read(4)
    if len(wb) < 4 or len(hb) < 4:
        return (0, 0)
    w = int(round(int.from_bytes(wb, "big") / 65536))
    h = int(round(int.from_bytes(hb, "big") / 65536))
    return (w, h) if w > 0 and h > 0 else (0, 0)


def _mp4_size(path) -> tuple:
    """解析 ISO BMFF（mp4/mov/m4v/3gp）：moov → trak → (tkhd + mdia/hdlr)。

    优先取 handler_type == 'vide' 的轨道；找不到 vide 轨道时回退第一个有 tkhd 的轨道。
    纯 stdlib、按偏移 seek，大文件也快；失败返回 (0, 0)。
    """
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            fsize = f.tell()
            # 顶层找 moov（可能在 mdat 之后，需顺序跳过）
            pos = 0
            moov = None
            while pos + 8 <= fsize:
                h = _read_box_header(f, pos, fsize)
                if h is None:
                    break
                btype, pstart, psize = h
                if btype == b"moov":
                    moov = (pstart, psize)
                    break
                pos += (pstart - pos) + psize
            if moov is None:
                return (0, 0)
            mstart, msize = moov
            mend = mstart + msize
            # 第一轮：只取 vide 轨道
            pos = mstart
            while pos + 8 <= mend:
                h = _read_box_header(f, pos, mend)
                if h is None:
                    break
                btype, pstart, psize = h
                if btype == b"trak":
                    tstart, tend = pstart, pstart + psize
                    is_video = False
                    mdia = _find_child_box(f, tstart, tend, b"mdia")
                    if mdia:
                        hdlr = _find_child_box(f, mdia[0], mdia[0] + mdia[1], b"hdlr")
                        if hdlr and hdlr[1] >= 12:
                            f.seek(hdlr[0] + 8)
                            if f.read(4) == b"vide":
                                is_video = True
                    if is_video:
                        tkhd = _find_child_box(f, tstart, tend, b"tkhd")
                        if tkhd:
                            sz = _tkhd_size(f, tkhd[0], tkhd[1])
                            if sz != (0, 0):
                                return sz
                pos += (pstart - pos) + psize
            # 第二轮：无 vide 轨道标记时回退任意轨道 tkhd
            pos = mstart
            while pos + 8 <= mend:
                h = _read_box_header(f, pos, mend)
                if h is None:
                    break
                btype, pstart, psize = h
                if btype == b"trak":
                    tkhd = _find_child_box(f, pstart, pstart + psize, b"tkhd")
                    if tkhd:
                        sz = _tkhd_size(f, tkhd[0], tkhd[1])
                        if sz != (0, 0):
                            return sz
                pos += (pstart - pos) + psize
            return (0, 0)
    except Exception:
        return (0, 0)


def _avi_size(path) -> tuple:
    """解析 RIFF AVI：找 'strh'+'vids' 流，其 'strf' BITMAPINFOHEADER 的 biWidth/biHeight。"""
    try:
        with open(path, "rb") as f:
            head = f.read(262144)  # 头信息足够大；AVI 索引在文件尾不影响
        idx = 0
        while True:
            i = head.find(b"strh", idx)
            if i < 0 or i + 12 > len(head):
                break
            if head[i + 8:i + 12] == b"vids":
                j = head.find(b"strf", i)
                if j >= 0 and j + 16 <= len(head):
                    w = int.from_bytes(head[j + 12:j + 16], "little", signed=False)
                    h = int.from_bytes(head[j + 16:j + 20], "little", signed=True)
                    w, h = abs(w), abs(h)
                    return (w, h) if w > 0 and h > 0 else (0, 0)
            idx = i + 4
        return (0, 0)
    except Exception:
        return (0, 0)


def _ebml_read_id(f):
    """读 EBML 元素 ID（首字节前导 1 位决定长度，长度 <=4）。"""
    b0 = f.read(1)
    if not b0:
        return None
    byte = b0[0]
    length = 1
    mask = 0x80
    while not (byte & mask):
        mask >>= 1
        length += 1
        if length > 4:
            return None
    rest = f.read(length - 1)
    if len(rest) < length - 1:
        return None
    val = byte
    for b in rest:
        val = (val << 8) | b
    return val


def _ebml_read_size(f):
    """读 EBML VINT 尺寸；返回 int，unknown-size（全 1）返回 -1。"""
    b0 = f.read(1)
    if not b0:
        return None
    byte = b0[0]
    length = 1
    mask = 0x80
    while not (byte & mask):
        mask >>= 1
        length += 1
        if length > 8:
            return None
    val = byte & (mask - 1)
    for _ in range(length - 1):
        b = f.read(1)
        if not b:
            return None
        val = (val << 8) | b[0]
    all_ones = (1 << (7 * length)) - 1
    return -1 if val == all_ones else val


_EBML_SEGMENT = 0x18538067
_EBML_TRACKS = 0x1654AE6B
_EBML_TRACK_ENTRY = 0xAE
_EBML_VIDEO = 0xE0
_EBML_PIXEL_WIDTH = 0xB0
_EBML_PIXEL_HEIGHT = 0xBA


def _ebml_video_children(f, start, end) -> tuple:
    """遍历 Video 元素子元素，取 PixelWidth/PixelHeight（uint32）。"""
    w = h = 0
    pos = start
    while pos + 2 <= end:
        f.seek(pos)
        pid = _ebml_read_id(f)
        if pid is None:
            break
        psize = _ebml_read_size(f)
        if psize is None:
            break
        dstart = f.tell()
        if pid == _EBML_PIXEL_WIDTH and psize == 4:
            f.seek(dstart)
            w = int.from_bytes(f.read(4), "big")
        elif pid == _EBML_PIXEL_HEIGHT and psize == 4:
            f.seek(dstart)
            h = int.from_bytes(f.read(4), "big")
        if w and h:
            return (w, h)
        if psize < 0 or psize == 0:
            break
        pos = dstart + psize
    return (w, h)


def _ebml_find_video(f, start, end) -> tuple:
    """递归找 Tracks → TrackEntry → Video → PixelWidth/Height。"""
    pos = start
    while pos + 2 <= end:
        f.seek(pos)
        elem_id = _ebml_read_id(f)
        if elem_id is None:
            break
        size = _ebml_read_size(f)
        if size is None:
            break
        dstart = f.tell()
        if elem_id == _EBML_VIDEO:
            dsize = (end - dstart) if size < 0 else size
            return _ebml_video_children(f, dstart, dstart + dsize)
        if elem_id in (_EBML_TRACKS, _EBML_TRACK_ENTRY) and size > 0:
            r = _ebml_find_video(f, dstart, dstart + size)
            if r != (0, 0):
                return r
        if size < 0 or size == 0:
            break
        pos = dstart + size
    return (0, 0)


def _ebml_size(path) -> tuple:
    """解析 EBML（webm/mkv）：Segment → Tracks → TrackEntry → Video → PixelWidth/Height。"""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            fsize = f.tell()
            f.seek(0)
            while f.tell() + 2 <= fsize:
                pos = f.tell()
                elem_id = _ebml_read_id(f)
                if elem_id is None:
                    break
                size = _ebml_read_size(f)
                if size is None:
                    break
                dstart = f.tell()
                if elem_id == _EBML_SEGMENT:
                    dsize = (fsize - dstart) if size < 0 else size
                    return _ebml_find_video(f, dstart, dstart + dsize)
                if size < 0 or size == 0:
                    break
                f.seek(dstart + size)
        return (0, 0)
    except Exception:
        return (0, 0)


def _qt_video_size(path) -> tuple:
    """Qt 后端探测（容器解析覆盖不到的格式，如 wmv/flv/mpg）。

    必须存在 QCoreApplication（否则事件循环不工作，会挂起）——不存在直接返回 (0,0)。
    v3.7 修复：videoSize 取自 QVideoSink（旧代码误用 QMediaPlayer.videoSize()，
    该属性在 PySide6 中不存在，导致恒返 (0,0)）。
    """
    from PySide6.QtCore import QCoreApplication
    if QCoreApplication.instance() is None:
        return (0, 0)
    player = _new_player()
    sink = QVideoSink()
    player.setVideoSink(sink)
    result = {"size": (0, 0)}
    loop = QEventLoop()

    def on_frame(frame):
        if result["size"] != (0, 0):
            return
        img = frame.toImage()
        if not img.isNull():
            result["size"] = (img.width(), img.height())
            loop.quit()

    def on_status(s):
        if s == QMediaPlayer.MediaStatus.InvalidMedia:
            loop.quit()
        elif s == QMediaPlayer.MediaStatus.LoadedMedia:
            sz = sink.videoSize()
            if sz.isValid() and sz.width() > 0 and sz.height() > 0:
                result["size"] = (sz.width(), sz.height())
                loop.quit()
            else:
                # 元数据未携带尺寸 → 首帧探测（sink 已连接，播放即收帧）
                player.play()

    sink.videoFrameChanged.connect(on_frame)
    player.mediaStatusChanged.connect(on_status)
    player.setSource(QUrl.fromLocalFile(str(path)))
    QTimer.singleShot(_SIZE_TIMEOUT_MS, loop.quit)
    loop.exec()
    player.stop()
    player.setSource(QUrl())
    return result["size"]


def video_size(path) -> tuple:
    """同步获取视频分辨率 (width, height)。

    - 优先纯 stdlib 容器解析（ISO BMFF mp4/mov/m4v、RIFF avi、EBML webm/mkv）：
      不依赖 Qt 事件循环，后台线程 / offscreen 环境同样可靠、不会挂起
    - 其余容器回退 QMediaPlayer + QVideoSink（需存在 QCoreApplication）
    - 失败/超时返回 (0,0)，调用方兜底显示"未知"
    - 应在后台线程调用
    """
    try:
        w, h = _mp4_size(str(path))
        if w and h:
            return (w, h)
    except Exception:
        pass
    try:
        w, h = _avi_size(str(path))
        if w and h:
            return (w, h)
    except Exception:
        pass
    try:
        w, h = _ebml_size(str(path))
        if w and h:
            return (w, h)
    except Exception:
        pass
    try:
        return _qt_video_size(str(path))
    except Exception:
        return (0, 0)


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
