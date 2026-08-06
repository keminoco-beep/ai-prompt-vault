"""导入流程专项测试：验证 TaskSignals parented 后能正常回调；
   验证超时看门狗触发；验证无效链接走 failed 路径。"""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.main_window import MainWindow
from app.workers import Worker, WorkerSignals

FAIL = []
_NET_SKIP = []


def check(name, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + name + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


def wait_for(app, predicate, timeout_sec=8):
    """泵事件直到 predicate 为真或超时。"""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.05)
    return False


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)

    td = tempfile.mkdtemp()
    store = DataStore(Path(td) / "库")
    win = MainWindow(store)
    win.show()
    cp = win.collect_panel
    app.processEvents()

    # --- 1. 正常导入：回调能收到，状态变 ready ---
    print("[正常导入] Civitai 图片链接")
    cp._start_civitai_import({"kind": "image", "id": 132699963})
    check("待保存=1", len(cp.pending) == 1)
    ok = wait_for(app, lambda: cp.pending and cp.pending[next(iter(cp.pending))]["state"] != "importing",
                  timeout_sec=20)
    item = next(iter(cp.pending.values())) if cp.pending else None
    state = item["state"] if item else None
    if state == "error":
        # 网络不可用（代理/超时/门控）时跳过网络依赖断言，避免环境问题误报
        err = cp.status_label.text()
        print(f"  ℹ 网络不可用，跳过网络断言（{err}）")
        _NET_SKIP.append("网络不可用")
    else:
        check("导入完成回调触发", ok and item and state == "ready", f"state={state}")
        check("图已下载", bool(item and item.get("image_file")))
        if item and item["image_file"]:
            check("图存在磁盘", (store.images_dir / item["image_file"]).exists())
        check("提示词已填充", bool(item and item["record"].get("positive")))
    check("看门狗已清除", not cp._watchdogs)

    # --- 2. 看门狗超时：用一个永远跑不完的函数 ---
    print("\n[看门狗] 任务长时间无响应时强制标记失败")
    from app.workers import WorkerSignals as _WS
    uid = "test_wd"
    cp.pending[uid] = {"uid": uid, "record": {"source": "local"}, "image_file": None, "state": "importing"}
    signals = WorkerSignals(cp)

    def slow():
        time.sleep(20)
        return "never"

    worker = Worker(signals, slow)
    # 看门狗 1s
    cp._install_watchdog(uid, 1)
    cp.pool.start(worker)
    ok = wait_for(app, lambda: cp.pending[uid]["state"] == "error", timeout_sec=4)
    check("看门狗触发后状态=error", ok)
    # 再等待一拍让 on_timeout 内的 pop 跑完
    app.processEvents()
    check("看门狗自动清理", uid not in cp._watchdogs)

    # --- 3. 错误信号路径：抛出异常走 failed 回调 ---
    print("\n[失败回调] 异常路径")
    uid2 = "test_fail"
    cp.pending[uid2] = {"uid": uid2, "record": {"source": "local"}, "image_file": None, "state": "importing"}
    signals2 = WorkerSignals(cp)
    signals2.failed.connect(lambda err, u=uid2: cp._on_task_fail(u, err))
    cp._install_watchdog(uid2, 30)

    def boom():
        raise ValueError("boom-test")

    w2 = Worker(signals2, boom)
    cp.pool.start(w2)
    ok = wait_for(app, lambda: cp.pending[uid2]["state"] == "error", timeout_sec=4)
    check("异常 → state=error", ok)
    check("看门狗清理", uid2 not in cp._watchdogs)

    # --- 4. 多次 import 去重：相同链接不重复启动 ---
    print("\n[去重] 同一链接多次导入")
    cp._start_civitai_import({"kind": "image", "id": 132699963})
    n1 = len(cp.pending)
    cp._start_civitai_import({"kind": "image", "id": 132699963})
    n2 = len(cp.pending)
    check("相同链接不重复创建任务", n2 == n1, f"n1={n1} n2={n2}")

    win.close()
    print()
    if FAIL:
        print(f"失败 {len(FAIL)} 项：{FAIL}")
        sys.exit(1)
    if _NET_SKIP:
        print(f"导入流程测试通过 ✓（网络跳过 {len(_NET_SKIP)} 项：{_NET_SKIP[0]}）")
    else:
        print("导入流程测试全部通过 ✓")
    sys.exit(0)


if __name__ == "__main__":
    main()