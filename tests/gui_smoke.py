"""GUI 离屏冒烟测试：实例化主窗口、模拟数据、切换板块、缩放/筛选。"""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QPushButton
from PySide6.QtCore import QTimer, Qt

from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.main_window import MainWindow
from app.ui.gallery_panel import GalleryPanel
from app.thumbs import make_thumbnail, rounded_pixmap

FAIL = []


def check(name, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + name + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


def _wait_search(app, ms=220):
    """等待搜索防抖定时器（150ms）触发 _apply，再检查结果。

    v3.6 搜索防抖后 setText 不立即过滤；这里让事件循环跑满防抖窗口，
    保证后续断言读到的是过滤后的图库状态。
    """
    end = time.monotonic() + ms / 1000.0
    while time.monotonic() < end:
        app.processEvents()
        time.sleep(0.01)


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(APP_QSS)

    td = tempfile.TemporaryDirectory()
    store = DataStore(Path(td.name) / "库")

    # 造一张测试图（生成 1024x1024 渐变 PNG）
    from PySide6.QtGui import QImage, QPainter, QColor, QLinearGradient, QBrush
    img = QImage(1024, 1024, QImage.Format_RGB32)
    p = QPainter(img)
    g = QLinearGradient(0, 0, 1024, 1024)
    g.setColorAt(0, QColor("#7c6cff"))
    g.setColorAt(1, QColor("#5ee0c8"))
    p.fillRect(img.rect(), QBrush(g))
    p.end()
    img.save(str(store.images_dir / "img_test_001.png"), "PNG")
    img.save(str(store.images_dir / "img_test_002.png"), "PNG")

    rec1 = store.add({
        "title": "测试夜景", "tags": ["城市", "夜景"], "positive": "night city, neon lights",
        "negative": "blur", "base_model": "Krea 2", "base_model_raw": "Krea 2",
        "models": [
            {"name": "Krea2 Turbo_FP8", "type": "大模型", "url": "https://civitai.com/models/2723583", "base_model": "Krea 2"},
            {"name": "add_detail", "type": "LoRA", "url": "https://civitai.com/models/999", "base_model": ""},
        ],
        "loras": ["add_detail"], "sampler": "DPM++", "steps": "28", "cfg": "7", "seed": "1",
        "width": 1024, "height": 1024, "source": "civitai", "source_url": "https://civitai.com/images/1",
        "image_file": "img_test_001.png", "thumb_file": "",
    })
    rec2 = store.add({
        "title": "竖版人像", "tags": [], "positive": "portrait", "negative": "",
        "base_model": "Flux.1", "models": [
            {"name": "flux1dev", "type": "大模型", "url": "https://civitai.com/models/123", "base_model": "Flux.1 Dev"}],
        "loras": [], "width": 1080, "height": 1920,
        "source": "local", "source_url": "", "image_file": "img_test_002.png", "thumb_file": "",
    })
    make_thumbnail(str(store.images_dir / "img_test_001.png"),
                   str(store.thumbs_dir / "img_test_001.png"), 400)

    win = MainWindow(store)
    win.show()
    app.processEvents()

    gp = win.gallery_panel
    gp.reload()
    app.processEvents()
    check("图库加载 2 条", gp.gallery.count() == 2, f"count={gp.gallery.count()}")
    check("标题显示", gp.gallery.item(0).text() == "测试夜景", gp.gallery.item(0).text())
    check("计数标签", "2" in gp.count_label.text())

    # 缩放
    gp.zoom.setValue(360)
    app.processEvents()
    check("缩放后仍 2 条", gp.gallery.count() == 2)

    # 筛选（按主模型大类）
    gp.base_combo.setCurrentText("Krea 2")
    app.processEvents()
    check("主模型大类筛选 Krea2=1", gp.gallery.count() == 1)
    gp.base_combo.setCurrentText("全部")
    gp.search.setText("不存在的词xyz")
    _wait_search(app)
    check("空结果提示状态", gp.gallery.count() == 0 and gp.stack.currentIndex() == 2)
    gp.search.setText("")
    gp.ratio_combo.setCurrentText("9:16")
    app.processEvents()
    check("比例筛选 9:16=1", gp.gallery.count() == 1, f"count={gp.gallery.count()}")
    gp.ratio_combo.setCurrentText("全部比例")
    gp.lora_combo.setCurrentText("add_detail")
    app.processEvents()
    check("LoRA 筛选=1", gp.gallery.count() == 1)
    gp.lora_combo.setCurrentText("全部")
    gp.search.setText("人像")
    _wait_search(app)
    check("搜索 人像=1", gp.gallery.count() == 1)
    gp.search.setText("flux1dev")
    _wait_search(app)
    check("搜索 模型名=1", gp.gallery.count() == 1)
    gp.search.setText("")

    # 悬浮浮窗对象
    check("浮窗可创建", gp._popup is not None)

    # ---- v2.1 新功能：排序 / 显示模式 / 分组 / 复制 ----
    # 排序：按标题升序
    gp.sort_combo.setCurrentIndex(1)   # 标题
    gp._sort_desc = False
    gp.sort_dir_btn.setText("↑")
    gp._apply()
    app.processEvents()
    check("排序-标题升序", gp.gallery.item(0).text() in ("人像", "测试夜景"), gp.gallery.item(0).text())
    # 按导入时间（默认）
    gp.sort_combo.setCurrentIndex(0)
    gp._sort_desc = True
    gp.sort_dir_btn.setText("↓")
    gp._apply()
    app.processEvents()
    # 显示模式：列表
    gp._set_view_mode("table")
    app.processEvents()
    check("列表模式行数=2", gp.detail.rowCount() == 2, f"rows={gp.detail.rowCount()}")
    check("列表模式列=8", gp.detail.columnCount() == 8)
    check("列表模式显示", gp.stack.currentIndex() == 1)
    # 列表表头排序（按尺寸面积）
    gp.detail.sortItems(6, Qt.DescendingOrder)
    app.processEvents()
    check("列表按尺寸排序", gp.detail.rowCount() == 2)
    # 切回平铺
    gp._set_view_mode("grid")
    app.processEvents()
    check("切回平铺", gp.stack.currentIndex() == 0)

    # 分组
    store.add_group("风景")
    store.add_group("人像")
    check("分组创建", store.groups == ["风景", "人像"])
    store.set_record_group(rec1["id"], "风景")
    gp.set_group("风景")
    app.processEvents()
    check("按组筛选 风景=1", gp.gallery.count() == 1, f"count={gp.gallery.count()}")
    gp.set_group("全部")
    app.processEvents()
    check("全部=2", gp.gallery.count() == 2)
    win.refresh_groups()
    app.processEvents()
    tree = win.group_tree
    top = tree.topLevelItem(0)
    check("分组树子项=4", top.childCount() == 4, f"n={top.childCount()}")
    from app.filters import group_counts
    cnt = group_counts(store.records)
    check("分组计数 风景=1", cnt.get("风景") == 1)
    check("分组重命名", store.rename_group("风景", "风景集") and store.groups == ["风景集", "人像"])
    check("分组删除", store.remove_group("人像") and store.groups == ["风景集"])
    store.remove_group("风景集")
    # 分组计数动态刷新（groupChanged 信号触发 main_window.refresh_groups）
    win.refresh_groups()
    store.add_group("动态组")
    win.refresh_groups()
    app.processEvents()
    top = win.group_tree.topLevelItem(0)
    found = any(top.child(i).text(0).startswith("动态组") for i in range(top.childCount()))
    check("侧栏分组动态更新", found)
    store.remove_group("动态组")

    # 右侧详情面板
    check("侧栏组件存在", gp.sidebar is not None)
    check("侧栏初始无记录", gp.sidebar._record is None)
    gp.gallery.setCurrentRow(0)
    app.processEvents()
    check("选中同步到侧栏", gp.sidebar._record is not None and gp.sidebar._record["id"] == rec1["id"])
    check("侧栏标题", gp.sidebar.title_label.text() == rec1["title"])
    check("侧栏提示词", gp.sidebar.pos_text.toPlainText() == rec1["positive"])
    # 列表模式选中同步
    gp._set_view_mode("table")
    gp.detail.selectRow(0)
    app.processEvents()
    check("列表选中同步到侧栏", gp.sidebar._record is not None)
    gp._set_view_mode("grid")
    app.processEvents()

    # 复制按钮存在
    check("图库复制按钮", hasattr(gp, "view_grid_btn") and gp.view_grid_btn.isChecked())
    cp_btn = [b for b in gp.findChildren(QPushButton) if b.text() == "复制提示词"]
    check("一键复制按钮", len(cp_btn) == 1)

    # 详情对话框（新模型清单 + 分组下拉）
    from app.ui.detail_dialog import DetailDialog
    store.add_group("测试组")
    dlg = DetailDialog(rec1, str(store.images_dir / rec1["image_file"]), parent=win)
    check("详情对话框字段", dlg.title_edit.text() == "测试夜景")
    check("详情主模型大类", dlg.base_combo.currentText() == "Krea 2")
    check("详情模型清单行数", len(dlg.model_rows) == 2, f"rows={len(dlg.model_rows)}")
    check("详情模型链接", dlg.model_rows[0]["url"].text().startswith("https://civitai.com/models/"))
    check("详情分组下拉", dlg.group_combo.findData("测试组") >= 0)
    dlg.group_combo.setCurrentIndex(dlg.group_combo.findData("测试组"))
    dlg.pos_edit.setPlainText("changed prompt")
    dlg._save()
    check("详情保存字段", dlg.record["positive"] == "changed prompt")
    check("详情保存模型", len(dlg.record["models"]) == 2)
    check("详情保存分组", dlg.record["group"] == "测试组")
    store.remove_group("测试组")

    # 收藏面板冒烟
    cp = win.collect_panel
    check("收藏面板待保存=0", len(cp.pending) == 0)
    # 模拟粘贴图片
    from PySide6.QtGui import QClipboard
    QApplication.clipboard().setImage(img, QClipboard.Clipboard)
    cp.add_from_clipboard()
    app.processEvents()
    check("粘贴图片→待保存=1", len(cp.pending) == 1, f"len={len(cp.pending)}")
    cp._apply_form(list(cp.pending.values())[0])
    cp.title_edit.setText("粘贴测试")
    cp.pos_edit.setPlainText("pasted prompt <lora:x1:1>")
    cp.save_current()
    app.processEvents()
    check("保存后待保存=0", len(cp.pending) == 0)
    check("保存后图库=3", gp.gallery.count() == 3, f"count={gp.gallery.count()}")
    saved = [r for r in store.records if r["title"] == "粘贴测试"]
    check("保存记录含LoRA", bool(saved) and "x1" in saved[0]["loras"])
    check("保存记录尺寸", bool(saved) and saved[0]["width"] == 1024)

    # 删除一条
    store.remove(rec2["id"])
    gp.reload()
    app.processEvents()
    check("删除后图库=2", gp.gallery.count() == 2)

    win.close()
    td.cleanup()
    print()
    if FAIL:
        print(f"失败 {len(FAIL)} 项：{FAIL}")
        sys.exit(1)
    print("GUI 冒烟测试全部通过 ✓")
    sys.exit(0)


if __name__ == "__main__":
    main()
