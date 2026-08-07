"""全局 QSS：苹果风暗色主题（macOS 风格）。

设计规范：
  分层     #12121a 侧栏 / #16161f 主背景 / #1c1c28 面板 / #21212e 输入框 / #262632 浮层
  强调     #6d5ef0 紫（hover #7c6cff / pressed #5547d0 / 渐变 #6d5ef0→#4f7de0）
  文字     #f2f2f8 主 / #a8a8c0 次 / #8a8aa5 弱 / #66667c 禁用
  边框     #26263a 常规 / #33334c hover / #6d5ef0 焦点
  圆角     主面板 14px / 按钮 10px / 输入框 10px / 列表项 10px / 菜单 12px
性能      仅纯色 + 少量线性渐变，无阴影/毛玻璃，低开销
"""
APP_QSS = """
* { outline: none; }

QMainWindow, QDialog, QMessageBox, QMenu, QToolTip {
    background-color: #16161f;
    color: #f2f2f8;
}

/* ---------- 侧边栏 ---------- */
#sidebar {
    background-color: #12121a;
    border-right: 1px solid #1f1f2c;
}
#brandName { color: #ffffff; font-size: 17px; font-weight: 700; }
#brandSub  { color: #9a9ab5; font-size: 11px; }
#logoDot {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #8b7bff, stop:0.5 #6d9bff, stop:1 #5ee0c8);
    border-radius: 18px;
}
QPushButton#navBtn {
    background: transparent; color: #c6c6dc;
    border: none; border-radius: 10px;
    padding: 11px 14px; margin: 2px 10px;
    font-size: 14px; text-align: left;
}
QPushButton#navBtn:hover { background: #1c1c2a; color: #ffffff; }
QPushButton#navBtn:checked {
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #5b4bd6, stop:1 #3f6fd8);
    color: #ffffff; font-weight: 600;
}
QPushButton#sideSmall {
    background: transparent; color: #b0b0c8; border: 1px solid #2a2a3e;
    border-radius: 9px; padding: 7px 10px; font-size: 12px;
}
QPushButton#sideSmall:hover { background: #1e1e2c; color: #ffffff; border-color: #3a3a58; }
QPushButton#sideSmall:pressed { background: #14141e; }

/* ---------- 分组区 / 模型管理 ---------- */
#groupTitle { color: #a8a8c0; font-size: 12px; font-weight: 600; }
QTreeView { show-decoration-selected: false; outline: 0; }
QTreeWidget#groupTree {
    background: transparent; border: none; color: #d8d8e8;
    font-size: 12px; outline: none;
}
QTreeWidget#groupTree::item {
    height: 26px; border-radius: 7px; padding: 0 4px;
}
QTreeWidget#groupTree::item:hover { background: #1c1c2a; }
QTreeWidget#groupTree::item:selected { background: #262244; color: #ffffff; border: none; }

/* ---------- 输入控件 ---------- */
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox, QSpinBox {
    background-color: #21212e;
    border: 1px solid #2c2c42;
    border-radius: 10px;
    padding: 6px 10px;
    color: #f2f2f8;
    selection-background-color: #5b4bd6;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus, QSpinBox:focus {
    border: 1px solid #6d5ef0;
    background-color: #232333;
}
QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover, QComboBox:hover { border-color: #3a3a58; }
QLineEdit:disabled, QPlainTextEdit:disabled { color: #66667c; background: #1a1a26; }
QLineEdit::placeholder, QPlainTextEdit::placeholder { color: #6d6d8a; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox::down-arrow {
    image: none; width: 0; height: 0;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid #a8a8c0;
}
QComboBox QAbstractItemView {
    background-color: #262632; color: #f2f2f8;
    border: 1px solid #3a3a58; border-radius: 10px;
    selection-background-color: #5b4bd6; selection-color: #ffffff;
    padding: 4px;
}
QSpinBox::up-button, QSpinBox::down-button { width: 18px; border: none; background: transparent; }

/* ---------- 按钮（苹果风圆角 + 完整悬停/按下反馈） ---------- */
QPushButton {
    background-color: #26263a; color: #f2f2f8;
    border: 1px solid #33334c; border-radius: 10px;
    padding: 7px 16px; font-size: 13px;
}
QPushButton:hover { background-color: #31314a; border-color: #40405e; }
QPushButton:pressed { background-color: #1b1b28; border-color: #2e2e46; }
QPushButton:disabled { color: #66667c; background: #1c1c28; border-color: #262638; }
QPushButton#primary {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d5ef0, stop:1 #4f7de0);
    border: none; color: #ffffff; font-weight: 600; padding: 8px 20px;
}
QPushButton#primary:hover {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #7d6ef8, stop:1 #5f8df0);
}
QPushButton#primary:pressed {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #5547d0, stop:1 #3f6fd8);
}
QPushButton#ghost { background: transparent; border: 1px solid #33334c; color: #d0d0e2; }
QPushButton#ghost:hover { background: #26263a; color: #ffffff; border-color: #40405e; }
QPushButton#ghost:pressed { background: #181824; }
QPushButton#danger { background: transparent; border: 1px solid #5e2a36; color: #ff9aa5; }
QPushButton#danger:hover { background: #331820; border-color: #e05262; color: #ffb3bb; }
QPushButton#danger:pressed { background: #221016; }

/* ---------- 标签 ---------- */
QLabel#fieldLabel { color: #a8a8c0; font-size: 12px; }
QLabel#hint { color: #8a8aa5; font-size: 12px; }
QLabel#countLabel { color: #a8a8c0; font-size: 12px; }

/* ---------- 列表 ---------- */
QListWidget {
    background: transparent; border: none;
    color: #f2f2f8;
}
QListWidget::item { border-radius: 10px; color: #d8d8e8; padding: 4px; }
QListWidget::item:hover { background: #1e1e2c; }
QListWidget::item:selected { background: #2a2650; border: 1px solid #6d5ef0; }
QListWidget#pendingList::item { border-radius: 9px; }
QListWidget#galleryList { background: transparent; }
QListWidget#galleryList::item { background: transparent; }
QListWidget#galleryList::item:hover { background: transparent; }
QListWidget#galleryList::item:selected { background: #20202e; border-radius: 12px; }

/* ---------- 详细列表（表格） ---------- */
QTableWidget#detailTable {
    background: #14141d; border: 1px solid #26263a; border-radius: 12px;
    color: #f2f2f8; gridline-color: #1f1f2c;
    font-size: 12px;
}
QTableWidget#detailTable::item { padding: 4px 8px; border: none; }
QTableWidget#detailTable::item:selected { background: #2a2650; color: #ffffff; }
QHeaderView::section {
    background-color: #1c1c28; color: #a8a8c0;
    border: none; border-bottom: 1px solid #26263a;
    padding: 7px 8px; font-weight: 600; font-size: 12px;
}
QHeaderView::section:hover { background-color: #24243a; color: #ffffff; }

/* ---------- 滚动条 ---------- */
QScrollBar:vertical { background: transparent; width: 9px; margin: 2px; }
QScrollBar::handle:vertical { background: #3a3a56; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #4a4a6a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QScrollBar:horizontal { background: transparent; height: 9px; margin: 2px; }
QScrollBar::handle:horizontal { background: #3a3a56; border-radius: 4px; min-width: 30px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ---------- 菜单 ---------- */
QMenu {
    background-color: #262632; border: 1px solid #3a3a58; border-radius: 12px;
    padding: 6px; color: #f2f2f8;
}
QMenu::item { padding: 7px 22px 7px 12px; border-radius: 7px; }
QMenu::item:selected { background: #6d5ef0; color: #ffffff; }
QMenu::separator { height: 1px; background: #33334c; margin: 5px 8px; }

/* ---------- 滑块 ---------- */
QSlider::groove:horizontal { height: 5px; background: #2c2c42; border-radius: 2px; }
QSlider::handle:horizontal {
    background: #6d5ef0; width: 16px; height: 16px; margin: -6px 0;
    border-radius: 8px;
}
QSlider::handle:horizontal:hover { background: #7c6cff; }
QSlider::handle:horizontal:pressed { background: #5547d0; }

/* ---------- 浮窗 ---------- */
#popupCard {
    background-color: #1c1c28; border: 1px solid #3a3a58; border-radius: 14px;
}
#popupTitle { color: #ffffff; font-size: 14px; font-weight: 700; }
#popupSection { color: #9a9ab8; font-size: 11px; font-weight: 600; }
#popupText { color: #d8d8e8; font-size: 12px; }
#chip {
    background-color: #26263a; color: #d0d0e4; border: 1px solid #33334c;
    border-radius: 8px; padding: 2px 8px; font-size: 11px;
}
#chipAccent { background-color: #2a2650; color: #b6aaff; border: 1px solid #5245ad; }

/* ---------- 弹窗（QMessageBox / QInputDialog / QFileDialog 内部文字必须亮色） ---------- */
QMessageBox, QInputDialog, QFileDialog {
    background-color: #1c1c28;
    color: #f2f2f8;
}
QMessageBox QLabel, QInputDialog QLabel, QFileDialog QLabel {
    color: #f2f2f8;
    background: transparent;
}
QMessageBox QLabel#qt_msgboxex_icon_label { background: transparent; }
QInputDialog QLineEdit, QFileDialog QLineEdit {
    background-color: #21212e; border: 1px solid #2c2c42; border-radius: 10px;
    color: #f2f2f8; padding: 6px 10px;
}
QInputDialog QLineEdit:focus { border: 1px solid #6d5ef0; }
QInputDialog QPushButton, QMessageBox QPushButton, QFileDialog QPushButton {
    background-color: #26263a; color: #f2f2f8; border: 1px solid #33334c;
    border-radius: 10px; padding: 7px 18px; font-size: 13px; min-width: 70px;
}
QInputDialog QPushButton:hover, QMessageBox QPushButton:hover, QFileDialog QPushButton:hover {
    background-color: #31314a; border-color: #40405e;
}
QInputDialog QPushButton:default, QMessageBox QPushButton:default {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 #6d5ef0, stop:1 #4f7de0);
    border: none; color: #ffffff; font-weight: 600;
}
QFileDialog QTreeView, QFileDialog QListView, QFileDialog QTableView {
    background-color: #16161f; color: #f2f2f8; border: 1px solid #2c2c42; border-radius: 8px;
}
QFileDialog QTreeView::item:selected, QFileDialog QListView::item:selected {
    background: #2a2650; color: #ffffff;
}

/* ---------- 下载列表 ---------- */
QListWidget#downloadList {
    background-color: #101018; border: 1px solid #26263a; border-radius: 10px;
    color: #d8d8e8; outline: none; padding: 4px;
}
QListWidget#downloadList::item {
    border-radius: 7px; padding: 6px 10px; background: transparent;
    border: 1px solid transparent;
}
QListWidget#downloadList::item:hover { background: #1e1e2c; }
QListWidget#downloadList::item:selected { background: #2a2650; border: 1px solid #5245ad; color: #ffffff; }

/* ---------- 模型管理 ---------- */
QTreeWidget#modelTree {
    background-color: #101018; border: 1px solid #26263a; border-radius: 12px;
    color: #d8d8e8; font-size: 12px; outline: none; padding: 6px;
}
QTreeWidget#modelTree::item {
    height: 28px; border-radius: 7px; padding: 0 6px;
}
QTreeWidget#modelTree::item:hover { background: #1e1e2c; }
QTreeWidget#modelTree::item:selected { background: #2a2650; color: #ffffff; border: none; }
QFrame#modelDetail {
    background-color: #16161f; border: 1px solid #26263a; border-radius: 12px;
}
QFrame#modelDetail QLabel { color: #d8d8e8; }
QFrame#modelDetail QLineEdit {
    background-color: #21212e; border: 1px solid #2c2c42; border-radius: 10px;
    color: #f2f2f8; padding: 6px 10px;
}

/* ---------- 其他 ---------- */
QSplitter::handle { background: #1f1f2c; width: 3px; }
QToolTip {
    background-color: #262632; color: #f2f2f8; border: 1px solid #3a3a58;
    padding: 4px 8px; border-radius: 8px;
}
#pageTitle { color: #ffffff; font-size: 19px; font-weight: 700; }
#pageSub { color: #a8a8c0; font-size: 12px; }
#emptyHint { color: #9a9ab8; font-size: 14px; }
QToolButton#collapseBtn {
    background: transparent; border: none; color: #a8a8c0;
    font-size: 12px; border-radius: 7px; padding: 3px 6px;
}
QToolButton#collapseBtn:hover { background: #24243a; color: #ffffff; }
QToolButton#collapseBtn:pressed { background: #181824; }

/* ---------- 设置页 API Key 标注 ---------- */
#keyNote {
    color: #7ee0a8; background: #14241c;
    border: 1px solid #2a5c3f; border-radius: 7px;
    padding: 2px 8px; font-size: 11px;
}

/* ---------- 操作按钮：自适应内容（不限制固定宽度），最小 48px 适合 2 个中文字 ---------- */
QPushButton#ghost, QPushButton#primary {
    min-width: 48px;
    padding: 4px 12px;
}
/* 更紧凑的下载/打开按钮（在密集列表中使用）—— 不强固定宽度，但保证 padding 一致 */

"""
