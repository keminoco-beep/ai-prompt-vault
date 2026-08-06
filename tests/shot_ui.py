# UI 截图诊断：渲染收藏页/详情对话框/图库页并保存 PNG
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QBrush, QLinearGradient

from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.main_window import MainWindow
from app.ui.detail_dialog import DetailDialog

app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)

td = tempfile.mkdtemp()
store = DataStore(Path(td) / "库")

# 生成测试图
img = QImage(512, 512, QImage.Format_ARGB32)
p = QPainter(img)
g = QLinearGradient(0, 0, 512, 512)
g.setColorAt(0, QColor("#7c6cff"))
g.setColorAt(1, QColor("#5ee0c8"))
p.fillRect(img.rect(), QBrush(g))
p.end()
img.save(str(store.images_dir / "img_t.png"), "PNG")

rec1 = store.add({
    "title": "测试夜景 赛博朋克", "tags": ["城市", "夜景"],
    "positive": "night city, neon lights, cinematic, ultra detailed",
    "negative": "blur, lowres",
    "base_model": "Krea 2", "base_model_raw": "Krea 2",
    "models": [
        {"name": "Krea2 Turbo_FP8", "type": "大模型",
         "url": "https://civitai.com/models/2723583", "base_model": "Krea 2"},
        {"name": "add_detail", "type": "LoRA",
         "url": "https://civitai.com/models/999", "base_model": ""},
    ],
    "loras": ["add_detail"], "sampler": "DPM++", "steps": "28", "cfg": "7", "seed": "1",
    "width": 1024, "height": 1024, "source": "civitai",
    "source_url": "https://civitai.com/images/1",
    "image_file": "img_t.png", "thumb_file": "",
})
store.add({
    "title": "竖版人像", "tags": [], "positive": "portrait", "negative": "",
    "base_model": "Flux.1",
    "models": [{"name": "flux1dev", "type": "大模型", "url": "", "base_model": "Flux.1 Dev"}],
    "loras": [], "width": 1080, "height": 1920,
    "source": "local", "source_url": "", "image_file": "img_t.png", "thumb_file": "",
})
from app.thumbs import make_thumbnail
make_thumbnail(str(store.images_dir / "img_t.png"), str(store.thumbs_dir / "img_t.png"), 400)

win = MainWindow(store)
win.show()
app.processEvents()

out = Path(__file__).resolve().parent / "shots"
out.mkdir(exist_ok=True)

# 1. 收藏页
win.collect_btn.click()
app.processEvents()
win.collect_panel._apply_form(list(win.collect_panel.pending.values())[0]) if False else None
win.grab().save(str(out / "1_collect.png"))

# 2. 详情对话框
dlg = DetailDialog(rec1, str(store.images_dir / rec1["image_file"]), parent=win)
dlg.show()
app.processEvents()
dlg.grab().save(str(out / "2_detail.png"))
dlg.close()

# 3. 图库页（平铺）
win.gallery_btn.click()
app.processEvents()
win.gallery_panel._set_view_mode("grid")
app.processEvents()
win.grab().save(str(out / "3_gallery.png"))

# 4. 图库列表模式
win.gallery_panel._set_view_mode("table")
app.processEvents()
win.grab().save(str(out / "4_table.png"))

print("saved:", [str(f) for f in out.iterdir()])
