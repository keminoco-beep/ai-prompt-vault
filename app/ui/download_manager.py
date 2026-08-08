"""下载任务管理（DownloadManager + DownloadTask + DownloadThread）。

- 全局单例（挂在 MainWindow），跟踪所有下载任务（下载中 + 已完成历史）
- 主线程创建任务时弹 TypePickDialog（"其他"类型）；确定保存目录
- 子线程里跑 resolve_download_url（避免主线程阻塞）+ 流式下载
- 速度采样（每段间隔计算）+ 进度回调
- 信号：taskAdded / taskUpdated / taskFinished / flyRequested（飞行动画起点）
"""
import collections
import time
import uuid
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from app import comfy
from app.i18n import t as tr, tr_format


class DownloadThread(QThread):
    """后台下载单个模型。子线程里做 resolve + 流式下载（主线程不卡）。

    支持暂停（保留 .part）/取消（删除 .part）/断点续传（Range）。
    """
    progress = Signal(int, int, float)   # got, total, speed(bytes/s)

    def __init__(self, url: str, dest: Path, parent=None, resume_offset: int = 0):
        super().__init__(parent)
        self.url = url
        self.dest = dest
        self.result = (False, "未执行")
        self.api_key = ""
        self.resume_offset = resume_offset
        self._pause_flag = False
        self._last_got = 0
        self._last_t = time.time()

    def run(self):
        try:
            # 在子线程里解析官方端口（可能 15s 网络等待）
            real_url = comfy.resolve_download_url(self.url, timeout=15.0)
        except Exception as e:
            self.result = (False, str(e))
            self.finished_ok_safe()
            return
        self.result = comfy.download_file(
            real_url, self.dest,
            progress_cb=self._on_progress,
            cancel_cb=lambda: self.isInterruptionRequested(),
            pause_cb=lambda: self._pause_flag,
            timeout=60.0,
            api_key=self.api_key,
            resume_offset=self.resume_offset)
        self.finished_ok_safe()

    def pause(self):
        """请求暂停：下载循环在下一个 chunk 处停止，保留 .part。"""
        self._pause_flag = True

    def finished_ok_safe(self):
        pass

    def _on_progress(self, got, total):
        now = time.time()
        dt = max(now - self._last_t, 0.001)
        speed = max((got - self._last_got) / dt, 0)
        self._last_got = got
        self._last_t = now
        self.progress.emit(got, total, speed)


class DownloadTask:
    """单个下载任务状态。"""
    STATUS_PENDING = "pending"
    STATUS_DOWNLOADING = "downloading"
    STATUS_PAUSED = "paused"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"

    def __init__(self, task_id: str, name: str, url: str, mtype: str, dest_dir: Path):
        self.id = task_id
        self.name = name
        self.url = url
        self.mtype = mtype
        self.dest_dir = dest_dir
        self.status = self.STATUS_PENDING
        self.got = 0
        self.total = 0
        self.speed = 0.0
        self.message = ""
        self.thread: DownloadThread = None
        self.start_time = time.time()
        self.last_emit_t = 0.0     # 节流：UI 刷新时间戳
        self.end_time = 0.0
        self.final_dest: Path = None  # 下载成功后的最终路径

    def progress_ratio(self) -> float:
        if self.total > 0:
            return min(self.got / self.total, 1.0)
        return 0.0

    def elapsed_str(self) -> str:
        end = self.end_time or time.time()
        sec = int(end - self.start_time)
        if sec < 60:
            return f"{sec}{tr('秒')}"
        return f"{sec // 60}{tr('分')} {sec % 60}{tr('秒')}"

    def status_label(self) -> str:
        return {"done": "完成", "failed": "失败",
                "cancelled": "已取消"}.get(self.status, self.status)


class DownloadManager(QObject):
    """全局下载任务管理（挂在 MainWindow）。"""
    taskAdded = Signal(str)            # task_id
    taskUpdated = Signal(str)          # task_id
    taskFinished = Signal(str, bool, str)  # task_id, ok, msg
    flyRequested = Signal(int, int)    # 飞行动画起点（global pos）

    HISTORY_ID = "__history__"

    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.tasks = {}        # id -> DownloadTask
        self.history = collections.deque(maxlen=100)
        self._comfy_dir = store.load_setting("comfyui_dir", "") or ""

    def comfy_dir(self) -> str:
        self._comfy_dir = self.store.load_setting("comfyui_dir", "") or ""
        return self._comfy_dir

    def active_count(self) -> int:
        return sum(1 for t in self.tasks.values()
                   if t.status in (DownloadTask.STATUS_PENDING,
                                   DownloadTask.STATUS_DOWNLOADING,
                                   DownloadTask.STATUS_PAUSED))

    def all_tasks(self):
        """所有正在下载/暂停的任务 + 历史（按时间倒序）。"""
        active = [t for t in self.tasks.values()
                  if t.status in (DownloadTask.STATUS_PENDING,
                                  DownloadTask.STATUS_DOWNLOADING,
                                  DownloadTask.STATUS_PAUSED)]
        return list(active), list(self.history)

    def start(self, model_info: dict, parent_widget=None, src_pos=None) -> str:
        """主线程：创建任务，确定 dest_dir，启动 thread。"""
        name = (model_info.get("name") or "").strip()
        url = (model_info.get("url") or "").strip()
        mtype = model_info.get("type") or "其他"
        if not name or not url:
            return ""
        comfy_dir = self.comfy_dir()
        if not comfy_dir or not Path(comfy_dir).is_dir():
            from PySide6.QtWidgets import QMessageBox
            from app.config import APP_NAME
            QMessageBox.information(
                parent_widget, tr(APP_NAME),
                tr("请先在「设置」中选择 ComfyUI 文件夹，再下载模型。"))
            return ""

        # 下载鉴权：Civitai API Key（可选，解决 403/HTML 错误页）
        api_key = self.store.load_setting("civitai_api_key", "") or ""

        # 确定保存目录（"其他"类型弹窗选择）
        try:
            dest_dir = comfy.comfy_dir_for(comfy_dir, mtype)
        except comfy.ComfyError:
            from app.ui.download_dialog import TypePickDialog
            dlg = TypePickDialog(name, comfy_dir, parent_widget)
            from PySide6.QtWidgets import QDialog
            if dlg.exec() != QDialog.Accepted or not dlg.picked:
                return ""
            dest_dir = comfy.comfy_dir_for(comfy_dir, mtype, dlg.picked)

        ext = ".safetensors"
        dest = dest_dir / comfy.safe_filename(name, ext)

        # 已存在则跳过
        if dest.exists():
            from PySide6.QtWidgets import QMessageBox
            from app.config import APP_NAME
            QMessageBox.information(parent_widget, tr(APP_NAME),
                                    tr_format("模型「{name}」已存在，跳过下载。", name=name))
            return ""

        # 创建任务（进入等待队列，由 _pump 按并发上限启动）
        task_id = uuid.uuid4().hex[:12]
        task = DownloadTask(task_id, name, url, mtype, dest_dir)
        task.status = DownloadTask.STATUS_PENDING
        task.thread = DownloadThread(url, dest, self)
        task.thread.api_key = api_key
        task.thread.progress.connect(lambda g, t, s, tid=task_id: self._on_progress(tid, g, t, s))
        task.thread.finished.connect(lambda tid=task_id: self._on_finished(tid))
        self.tasks[task_id] = task
        self.taskAdded.emit(task_id)

        # 触发飞行动画（主窗口连接 → 在侧栏下载列表按钮位置显示动画）
        if src_pos:
            self.flyRequested.emit(int(src_pos.x()), int(src_pos.y()))

        self._pump()
        return task_id

    MAX_ACTIVE = 3  # 同时下载上限（避免带宽/磁盘争抢）

    def _pump(self):
        """按并发上限启动等待中的任务。"""
        running = sum(1 for t in self.tasks.values()
                      if t.status == DownloadTask.STATUS_DOWNLOADING)
        for t in list(self.tasks.values()):
            if running >= self.MAX_ACTIVE:
                break
            if t.status == DownloadTask.STATUS_PENDING:
                t.status = DownloadTask.STATUS_DOWNLOADING
                t.thread.start()
                self.taskUpdated.emit(t.id)
                running += 1

    def _on_progress(self, task_id, got, total, speed):
        t = self.tasks.get(task_id)
        if not t:
            return
        # 防御负值（某些 CDN 返回负 Content-Length）
        t.got = max(0, got)
        t.total = max(0, total)
        t.speed = max(0.0, speed)
        # 节流：UI 刷新间隔 ≥ 300ms，避免高带宽下载时频繁重绘
        now = time.time()
        if now - t.last_emit_t >= 0.3:
            self.taskUpdated.emit(task_id)
            t.last_emit_t = now

    def _on_finished(self, task_id):
        t = self.tasks.get(task_id)
        if not t:
            return
        t.end_time = time.time()
        ok, msg = t.thread.result
        t.message = msg
        if "已暂停" in msg:
            # 暂停：保留 .part，任务停留在活动列表（可恢复）
            t.status = DownloadTask.STATUS_PAUSED
            self.taskUpdated.emit(task_id)
            self._pump()   # 释放并发名额给下一个等待任务
            return
        t.status = DownloadTask.STATUS_DONE if ok else (
            DownloadTask.STATUS_CANCELLED if "已取消" in msg else DownloadTask.STATUS_FAILED)
        if ok and t.thread.dest.exists():
            t.final_dest = t.thread.dest
            t.got = t.total = t.thread.dest.stat().st_size
        self.taskFinished.emit(task_id, ok, msg)
        self.taskUpdated.emit(task_id)
        # 移到历史
        self.history.appendleft(t)
        self.taskUpdated.emit(self.HISTORY_ID)
        # API Key 缺失导致的失败：弹引导窗（设置 Key / 打开网页 / 取消）。
        # 只自动弹一次，避免多任务失败时弹窗轰炸（其余失败可点击历史项查看）。
        # 兼容中英文错误消息（"HTML 错误页" / "HTML error page" / API Key / 403）
        if not ok and any(k in msg for k in ("HTML", "403", "API Key")):
            if not getattr(self, "_guide_shown", False):
                self._guide_shown = True
                self._show_apikey_guide(t)
        # 释放并发名额，启动下一个等待任务
        self._pump()

    def _show_apikey_guide(self, task):
        """下载失败（疑似缺 API Key）时弹引导窗：去设置 / 打开 Civitai / 取消。"""
        from PySide6.QtWidgets import QMessageBox, QWidget
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices
        from app.config import APP_NAME
        parent_w = self.parent() if isinstance(self.parent(), QWidget) else None
        box = QMessageBox(parent_w)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle(tr(APP_NAME))
        box.setText(tr("下载失败：需要登录态（API Key）"))
        box.setInformativeText(
            tr_format("模型「{name}」下载失败：{err}\n\nCivitai 官方下载需要登录凭证。你可以：\n"
                      "① 在「设置」填入 Civitai API Key 后重试\n"
                      "② 直接打开 Civitai 模型页手动下载",
                      name=task.name, err=task.message[:100]))
        box.setStandardButtons(QMessageBox.Cancel)
        btn_settings = box.addButton(tr("去设置"), QMessageBox.AcceptRole)
        btn_open = box.addButton(tr("打开模型页"), QMessageBox.ActionRole)
        box.exec()
        clicked = box.clickedButton()
        if clicked is btn_settings:
            from app.ui.settings_dialog import SettingsDialog
            from PySide6.QtWidgets import QApplication
            main_win = QApplication.activeWindow()
            SettingsDialog(self.store, main_win).exec()
        elif clicked is btn_open:
            QDesktopServices.openUrl(QUrl(task.url))

    def cancel(self, task_id):
        """取消下载（删除任务 + 清理 .part）。

        - 下载中：中断线程（线程结束后删 .part）
        - 已暂停：线程已结束，直接清理 .part 并移入历史
        """
        t = self.tasks.get(task_id)
        if not t:
            return
        if t.thread and t.thread.isRunning():
            t.thread.requestInterruption()
            return
        # 线程已结束（暂停/等待状态）：直接清理断点文件并移入历史
        if t.thread:
            part = t.thread.dest.with_name(t.thread.dest.name + ".part")
            try:
                if part.exists():
                    part.unlink()
            except Exception:
                pass
        t.status = DownloadTask.STATUS_CANCELLED
        t.end_time = time.time()
        t.message = "已取消"
        self.tasks.pop(task_id, None)
        self.history.appendleft(t)
        self.taskUpdated.emit(self.HISTORY_ID)

    def pause(self, task_id):
        """暂停下载：保留 .part，可断点续传。"""
        t = self.tasks.get(task_id)
        if t and t.thread and t.thread.isRunning():
            t.thread.pause()
        elif t and t.status == DownloadTask.STATUS_PAUSED:
            pass  # 已暂停

    def resume(self, task_id) -> bool:
        """恢复下载：从 .part 断点续传。返回 False 表示无法恢复。"""
        t = self.tasks.get(task_id)
        if not t:
            return False
        if t.status != DownloadTask.STATUS_PAUSED:
            return False
        # 检查 .part 断点
        part = t.thread.dest.with_name(t.thread.dest.name + ".part")
        off = part.stat().st_size if part.exists() else 0
        api_key = self.store.load_setting("civitai_api_key", "") or ""
        # 新线程（带 resume_offset）
        t.status = DownloadTask.STATUS_DOWNLOADING
        t.thread = DownloadThread(t.url, t.thread.dest, self, resume_offset=off)
        t.thread.api_key = api_key
        t.thread.progress.connect(lambda g, tot, s, tid=task_id: self._on_progress(tid, g, tot, s))
        t.thread.finished.connect(lambda tid=task_id: self._on_finished(tid))
        t.thread.start()
        self.taskUpdated.emit(task_id)
        return True

    def clear_history(self):
        self.history.clear()
        self.taskUpdated.emit(self.HISTORY_ID)

    def remove_finished(self, task_id):
        """从活动列表移除已完成任务（历史里继续保留）。"""
        if task_id in self.tasks:
            del self.tasks[task_id]
            self.taskUpdated.emit(task_id)

    def cleanup_partials(self) -> int:
        """清理 ComfyUI models/ 下残留 .part 半成品文件。"""
        return comfy.cleanup_partial_files(self.comfy_dir())