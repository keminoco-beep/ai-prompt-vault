"""v3.1.0 发布截图：离屏渲染主界面/图库页/详情，保存 PNG 到 release/screenshots/。"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QImage, QPainter, QColor, QBrush, QLinearGradient, QFont, QFontDatabase
from PySide6.QtCore import QFile, QIODevice

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS, set_theme
from app.ui.main_window import MainWindow

app = QApplication(sys.argv)
# offscreen 缺中文字体 → 加载 Windows 系统字体（YaHei 微软雅黑 / simsun.ttc 兜底）
for font_path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc", r"C:\Windows\Fonts\simsun.ttc"):
    if QFile.exists(font_path):
        fid = QFontDatabase.addApplicationFont(font_path)
        if fid >= 0:
            fams = QFontDatabase.applicationFontFamilies(fid)
            print(f"加载字体: {font_path} → {fams[:1]}")
app.setFont(QFont("Microsoft YaHei UI", 10))
set_theme("dark")
app.setStyleSheet(APP_QSS)

td = tempfile.mkdtemp()
store = DataStore(Path(td) / "Library")
i18n.init(store.settings_path(), "en")   # 英文界面截图（GitHub 国际展示）

# 造 6 张渐变测试图（不同配色，避免截图全是同色）
grads = [
    ("#7c6cff", "#5ee0c8"), ("#ff6c8c", "#ffb86c"), ("#4cc9f0", "#4361ee"),
    ("#f72585", "#b5179e"), ("#06d6a0", "#118ab2"), ("#ffd166", "#ef476f"),
]
for i, (c1, c2) in enumerate(grads):
    img = QImage(768, 512, QImage.Format_ARGB32)
    p = QPainter(img)
    g = QLinearGradient(0, 0, 768, 512)
    g.setColorAt(0, QColor(c1))
    g.setColorAt(1, QColor(c2))
    p.fillRect(img.rect(), QBrush(g))
    p.end()
    f = store.images_dir / f"img_{i}.png"
    img.save(str(f), "PNG")
    store.add({
        "id": f"shot_{i}", "title": f"Sample Art {i+1} · Cyberpunk {['City', 'Portrait', 'Landscape'][i % 3]}",
        "tags": ["sample", "city", "cyberpunk", "neon"],
        "positive": "night city, neon lights, cinematic, ultra detailed, masterpiece",
        "negative": "blur, lowres, bad anatomy",
        "base_model": ["Krea 2", "Flux.1", "SDXL"][i % 3],
        "models": [{"name": "Krea2 Turbo_FP8", "type": "Checkpoint", "url": "https://civitai.com/models/1"},
                   {"name": "detail_enhancer", "type": "LoRA", "url": ""}],
        "sampler": "DPM++ 2M", "steps": 28, "cfg": 6.5, "seed": 12345 + i,
        "source": "civitai", "image_file": f"img_{i}.png",
    })

out_dir = Path(__file__).resolve().parent.parent / "release" / "screenshots"
out_dir.mkdir(parents=True, exist_ok=True)

win = MainWindow(store, output_scan=False)
win.resize(1280, 800)
win.show()
app.processEvents()

def snap(name):
    pm = win.grab()
    path = out_dir / name
    pm.save(str(path), "PNG")
    print(f"已保存 {path} ({pm.width()}x{pm.height()})")

snap("main_collect.png")
# 切到图库页
win.gallery_btn.setChecked(True)
win.stack.setCurrentIndex(1)
app.processEvents()
snap("gallery.png")
# 切到模型管理页
try:
    win.model_btn.setChecked(True)
    win.stack.setCurrentIndex(2)
    app.processEvents()
    snap("models.png")
except Exception as e:
    print("模型页截图跳过:", e)

print("完成")
