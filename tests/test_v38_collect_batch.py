"""v3.8 批量收藏回归测试：① 多 Civitai 链接批量保存时各记录提示词互不串扰
② 导入中/无图项被跳过 ③ 链接尾随中文标点仍可解析。"""
import os, sys, tempfile, ast
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
from PySide6.QtGui import QImage, QColor

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.collect_panel import CollectPanel, _strip_url_trailing, _id_of

app = QApplication([])
app.setStyleSheet(APP_QSS)
td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")

ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {name}" + (f"  {extra}" if extra and not cond else ""))
    if not cond:
        ok = False


def make_img(name, color="#7c6cff"):
    im = QImage(48, 48, QImage.Format_ARGB32)
    im.fill(QColor(color))
    im.save(str(store.images_dir / name), "PNG")


make_img("t38_a.png", "#aa2233")
make_img("t38_b.png", "#22aa33")

# ---- T1: 主 bug 回归 —— 多链接批量保存，各记录 positive 互不串扰 ----
def civitai_fields(pos, sid, mid=1):
    return {
        "source": "civitai",
        "source_url": f"https://civitai.com/images/{sid}",
        "positive": pos,
        "negative": f"neg of {sid}",
        "models": [{"name": f"Model{sid}", "type": "大模型",
                    "url": f"https://civitai.com/models/{mid}", "base_model": "SDXL"}],
        "base_model": "SDXL",
        "base_model_raw": "SDXL 1.0",
        "sampler": "DPM++ 2M", "steps": "28", "cfg": "7", "seed": str(sid),
    }

panel = CollectPanel(store)
uid_a = panel._make_pending(civitai_fields("POSITIVE_ALPHA unique", 111), image_file="t38_a.png", uid="uid_a")
uid_b = panel._make_pending(civitai_fields("POSITIVE_BETA distinct", 222), image_file="t38_b.png", uid="uid_b")

# 选中 A（表单会填充 A 的数据），再模拟用户在表单上编辑标题
panel._select_uid(uid_a)
app.processEvents()
panel.title_edit.setText("User edited title")

# merge_form=False 不应污染 item["record"]（bug #5 副作用核实）
rec_b_before = panel._build_record(panel.pending[uid_b], merge_form=False)
check("T1 merge_form=False 不污染 record", panel.pending[uid_b]["record"]["positive"] == "POSITIVE_BETA distinct")
check("T1 merge_form=False 直接用导入数据", rec_b_before["positive"] == "POSITIVE_BETA distinct")

panel.save_all()
app.processEvents()

saved = {r["source_url"]: r for r in store.records}
check("T1 两条记录都已保存", "https://civitai.com/images/111" in saved and "https://civitai.com/images/222" in saved)
check("T1 记录A positive 正确", saved["https://civitai.com/images/111"]["positive"] == "POSITIVE_ALPHA unique",
      saved.get("https://civitai.com/images/111", {}).get("positive"))
check("T1 记录B positive 正确（不被表单污染）", saved["https://civitai.com/images/222"]["positive"] == "POSITIVE_BETA distinct",
      saved.get("https://civitai.com/images/222", {}).get("positive"))
check("T1 两条 positive 互不相同", saved["https://civitai.com/images/111"]["positive"] != saved["https://civitai.com/images/222"]["positive"])
check("T1 表单编辑仅作用于当前选中项A", saved["https://civitai.com/images/111"]["title"] == "User edited title",
      saved.get("https://civitai.com/images/111", {}).get("title"))
check("T1 非选中项B 未带表单标题", saved["https://civitai.com/images/222"]["title"] != "User edited title",
      saved.get("https://civitai.com/images/222", {}).get("title"))
check("T1 save_all 后 pending 清空", not panel.pending)

# ---- T2: 导入中项被跳过（save_all + save_current） ----
n_before = len(store.records)
panel2 = CollectPanel(store)
uid_imp = panel2._make_pending({"source": "civitai", "source_url": "https://civitai.com/images/333"},
                               image_file=None, uid="uid_imp")
panel2.pending[uid_imp]["state"] = "importing"
uid_ready = panel2._make_pending({"source": "civitai", "source_url": "https://civitai.com/images/444",
                                  "positive": "ready prompt"}, image_file="t38_a.png", uid="uid_ready")
panel2.save_all()
app.processEvents()
check("T2 save_all 只保存 ready 项", len(store.records) == n_before + 1)
check("T2 导入中项仍在 pending", "uid_imp" in panel2.pending)
check("T2 ready 项已保存并移除", "uid_ready" not in panel2.pending)
check("T2 提示含跳过导入中", "导入中" in panel2.status_label.text(), panel2.status_label.text())

panel2._select_uid(uid_imp)
panel2.save_current()
app.processEvents()
check("T2 save_current 拒绝导入中项", "uid_imp" in panel2.pending)
check("T2 save_current 提示等待导入", "请等待导入完成" in panel2.status_label.text(),
      panel2.status_label.text())

# ---- T2b: 无图且非视频的 ready 项跳过并计数 ----
n_before2 = len(store.records)
uid_noimg = panel2._make_pending({"source": "civitai", "source_url": "https://civitai.com/images/555"},
                                 image_file=None, uid="uid_noimg")
panel2.save_all()
app.processEvents()
check("T2b 无图项未被保存", len(store.records) == n_before2)
check("T2b 无图项仍在 pending", "uid_noimg" in panel2.pending)
check("T2b 提示含无图片跳过", "无图片" in panel2.status_label.text(), panel2.status_label.text())

# ---- T3: _import_links 链接尾随中文标点仍能解析 ----
parsed_log = []
panel3 = CollectPanel(store)
panel3._start_civitai_import = lambda parsed: parsed_log.append(parsed)
panel3.link_edit.setText("https://civitai.com/images/111。\nhttps://civitai.com/images/222，https://civitai.com/models/333。）")
panel3._import_links()
ids = [p["id"] for p in parsed_log]
check("T3 中文标点尾随链接全部解析", ids == [111, 222, 333], str(ids))

check("T3 strip 句号", _strip_url_trailing("https://civitai.com/images/1。") == "https://civitai.com/images/1")
check("T3 strip 括号句号", _strip_url_trailing("https://civitai.com/models/3。）") == "https://civitai.com/models/3")
check("T3 strip 不破坏正常 URL", _strip_url_trailing("https://civitai.com/images/1?v=2") == "https://civitai.com/images/1?v=2")

# ---- T4: 去重 _id_of 覆盖实际 source_url 格式（bug #6 核实） ----
check("T4 images 格式", _id_of("https://civitai.com/images/123456") == 123456)
check("T4 models 格式", _id_of("https://civitai.com/models/789") == 789)
check("T4 model-versions 格式", _id_of("https://civitai.com/api/v1/model-versions/456") == 456)
check("T4 单数 image 格式", _id_of("https://civitai.com/image/999") == 999)

# ---- T6: i18n 三表 key 集合一致 + 新 key 齐备 ----
src = open("app/i18n.py", encoding="utf-8").read()
tree = ast.parse(src)
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_LANG_TABLES" for t in node.targets):
        tables = {k.value: {kk.value: vv.value for kk, vv in zip(v.keys, v.values)}
                  for k, v in zip(node.value.keys, node.value.values)}
        en, es, ja = set(tables["en"]), set(tables["es"]), set(tables["ja"])
        check("T6 三表 key 集合一致", en == es == ja)
        for k in ["有 {n} 条仍在导入中，已跳过", "有 {n} 条无图片，已跳过", "请等待导入完成"]:
            check(f"T6 新 key 齐备: {k[:14]}…", k in en and k in es and k in ja)

print("\n" + ("v3.8 批量收藏回归 全部通过 ✓" if ok else "存在失败 ✗"))
sys.exit(0 if ok else 1)
