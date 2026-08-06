"""端到端：带内嵌提示词的图片导入 → 自动提取 → 保存 → 图库复制。"""
import os, struct, sys, tempfile, time, zlib
from pathlib import Path
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '.')
from PySide6.QtWidgets import QApplication
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.main_window import MainWindow


def make_png(path, text_chunks):
    def chunk(ctype, data):
        return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", zlib.crc32(ctype + data) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(64 * 3) for _ in range(64))
    idat = zlib.compress(raw)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat)
    for k, v in text_chunks.items():
        data += chunk(b"tEXt", k.encode() + b"\x00" + v.encode())
    data += chunk(b"IEND", b"")
    Path(path).write_bytes(data)


app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)
td = Path(tempfile.mkdtemp())
p = td / "meta_img.png"
params = ("1girl, masterpiece, city night\n"
          "Negative prompt: lowres\n"
          "Steps: 28, Sampler: DPM++ 2M Karras, CFG scale: 7, Seed: 42, "
          "Size: 512x768, Model: dreamshaperXL_v21")
make_png(p, {"parameters": params})

store = DataStore(td / "Library")
win = MainWindow(store)
win.show()
app.processEvents()
cp = win.collect_panel

# 导入（worker 复制 + 自动提取）
cp._start_local_copy(str(p))
app.processEvents()
time.sleep(1.5)
app.processEvents()
item = list(cp.pending.values())[0]
print("提取后 record.positive:", repr(item["record"].get("positive", ""))[:45])

# 保存（当前选中项可能为 None → 直接用 save_all 语义）
cp.save_all()
app.processEvents()
rec = store.records[0]
print("保存后 rec.positive:", repr(rec.get("positive", ""))[:45])
print("保存后 rec.negative:", repr(rec.get("negative", ""))[:45])
print("保存后 rec.sampler/steps/cfg/seed:", rec.get("sampler"), rec.get("steps"), rec.get("cfg"), rec.get("seed"))
print("保存后 rec.models:", rec.get("models"))
print("保存后 rec.base_model:", repr(rec.get("base_model")))

# 图库浏览 → 复制
win.gallery_btn.click()
app.processEvents()
gp = win.gallery_panel
gp.reload()
app.processEvents()
gp.gallery.setCurrentRow(0)
app.processEvents()
gp._on_selection_changed(store.records[0])
app.processEvents()
sb = gp.sidebar
app.clipboard().clear()
sb._copy_record("positive")
cb = app.clipboard().text()
print()
print("复制正向:", repr(cb)[:60], "| OK:", "1girl, masterpiece" in cb)
sb._copy_record("all")
all_cb = app.clipboard().text()
print("复制全部:", repr(all_cb)[:150])
ok = ("1girl, masterpiece" in cb and "dreamshaperXL_v21" in all_cb
      and "Steps: 28" in all_cb and "Sampler: DPM++" in all_cb)
print()
print("全链路结果:", "通过" if ok else "失败")
