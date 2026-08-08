"""v2.4.1 端到端实操测试：收藏→保存→图库→复制→下载→模型管理→设置→侧栏拉伸。

- 本地 HTTP 服务器模拟模型下载源，验证下载不卡 UI + 文件落盘
- 全流程模拟真实用户操作
"""
import os
import struct
import sys
import tempfile
import threading
import time
import zlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '.')

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.main_window import MainWindow

# offscreen 下弹窗会阻塞：mock 成直接返回
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append((name, ok, detail))
    print(f"  {'✓' if ok else '✗'} {name} {detail}")


def make_png(path, text_chunks):
    def chunk(ctype, data):
        return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", zlib.crc32(ctype + data) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(64 * 3) for _ in range(64))
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw))
    for k, v in text_chunks.items():
        data += chunk(b"tEXt", k.encode() + b"\x00" + v.encode())
    data += chunk(b"IEND", b"")
    Path(path).write_bytes(data)


class MockServer(HTTPServer):
    pass


def serve_once(data: bytes):
    """单文件 HTTP 服务：GET 返回 data。"""
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            self.wfile.flush()

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}/model.safetensors", srv


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)

    # 临时目录：库 + ComfyUI
    td = Path(tempfile.mkdtemp())
    comfy_root = td / "ComfyUI"
    (comfy_root / "models" / "checkpoints").mkdir(parents=True)
    (comfy_root / "models" / "loras").mkdir(parents=True)
    # 预置两个模型文件（一个长文件名）
    long_name = "very_long_model_name_for_stretch_test_" + "x" * 80 + ".safetensors"
    (comfy_root / "models" / "checkpoints" / long_name).write_bytes(b"checkpoint-bytes")
    (comfy_root / "models" / "loras" / "style_lora.safetensors").write_bytes(b"lora-bytes")

    store = DataStore(td / "Library")
    i18n.init(store.settings_path(), "zh")
    store.save_setting("comfyui_dir", str(comfy_root))
    win = MainWindow(store)
    win.show()
    app.processEvents()

    print("== 1. 收藏作品（带内嵌元数据的图片）==")
    img_p = td / "meta.png"
    params = ("1girl, masterpiece\nNegative prompt: lowres\nSteps: 20, Sampler: Euler a, "
              "CFG scale: 7, Seed: 1, Size: 512x768, Model: testModel")
    make_png(img_p, {"parameters": params})
    cp = win.collect_panel
    cp._start_local_copy(str(img_p))
    app.processEvents()
    time.sleep(1.2)
    app.processEvents()
    check("本地导入自动提取", list(cp.pending.values())[0]["record"].get("positive", "").startswith("1girl"))
    cp.save_all()
    app.processEvents()
    check("保存记录", len(store.records) == 1)

    print("== 2. 图库浏览 ==")
    win.gallery_btn.click()
    app.processEvents()
    gp = win.gallery_panel
    gp.reload()
    app.processEvents()
    check("图库显示 1 张", gp.gallery.count() == 1)
    gp.gallery.setCurrentRow(0)
    app.processEvents()
    gp._on_selection_changed(store.records[0])
    app.processEvents()
    sb = gp.sidebar
    check("侧栏显示记录", sb._record is not None and sb.pos_text.toPlainText().startswith("1girl"))
    app.clipboard().clear()
    sb._copy_record("positive")
    check("复制提示词", app.clipboard().text().startswith("1girl"))

    print("== 3. 模型管理 ==")
    win.model_btn.click()
    app.processEvents()
    mp = win.model_panel
    app.processEvents()
    # 扫描：checkpoints 1 个长名 + loras 1 个
    names = [m["rel"] for m in mp._models]
    check("扫描出 2 个模型", len(names) == 2, f"({names})")
    # 选中长名模型 → 侧栏/详情不撑破（面板宽度 < 900 且 info_name 换行）
    check("长名模型在列表", any(long_name in n for n in names))
    # 备注
    long_rel = next(n for n in names if long_name in n)
    mp._current = next(m for m in mp._models if m["rel"] == long_rel)
    mp.note_edit.setText("测试备注")
    mp._save_note()
    app.processEvents()
    check("备注保存", store.root.joinpath("model_notes.json").exists())
    # 复制文件名
    mp._copy_name()
    check("复制文件名", app.clipboard().text() == long_name)

    print("== 4. 下载流程（本地 HTTP 模拟，验证不卡 UI）==")
    fake_model = b"\x00" * 2_000_000  # 2MB
    url, srv = serve_once(fake_model)

    # 4a/b/c: 下载核心已迁移到 DownloadManager（v2.4.3 重构），由 test_download_v243 覆盖
    print("  (下载测试见 test_download_v243.py)")

    print("== 5. 侧栏拉伸修复 ==")
    # 给图库记录加一个超长模型名，检查 sidebar 宽度不超最大 440
    rec = store.records[0]
    rec["models"] = [{"name": long_name, "type": "大模型", "url": "https://civitai.com/models/1"}]
    store.save()
    win.gallery_btn.click()
    app.processEvents()
    gp.reload()
    app.processEvents()
    gp.gallery.setCurrentRow(0)
    app.processEvents()
    gp._on_selection_changed(rec)
    app.processEvents()
    sb_w = sb.width() if sb.width() > 0 else sb.maximumWidth()
    check("侧栏宽度 <= 440", sb_w <= 440, f"(width={sb_w})")

    print("== 6. 设置对话框 ==")
    from app.ui.settings_dialog import SettingsDialog
    dlg = SettingsDialog(store, win)
    # v3.3 解耦：设置页「输出文件夹」多选行只读 comfy_output_dirs；
    # comfyui_dir 仅用于模型下载，不再回退迁移为输出目录列表。
    # 未设置 comfy_output_dirs 时输出目录为空。
    out_dirs = dlg._output_dirs
    check("设置回显输出目录为空（comfyui_dir 不再回退）", out_dirs == [], f"({out_dirs})")

    print()
    failed = [r for r in RESULTS if not r[1]]
    print(f"端到端结果: {len(RESULTS) - len(failed)}/{len(RESULTS)} 通过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
