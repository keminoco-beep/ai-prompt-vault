import os
import sys
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QFont

app = QApplication(sys.argv)
app.setFont(QFont("Microsoft YaHei UI", 10))

from app.ui.main_window import make_app_icon_file

out = Path(__file__).resolve().parent / "app.ico"
make_app_icon_file(str(out))
print("icon created:", out.stat().st_size, "bytes")
