"""v4.2 i18n 全语言审计测试（Bug 2：英文版仍显示中文）。

覆盖：
T1 四表 key 集合两两一致（en/es/ja，zh 为源 key）+ 所有值非空
T2 遍历 app/ + main.py 所有 tr()/tr_format() 字面量，断言每个 key 都在
   en/es/ja 表中（专有名词 AI-Prompt-Vault / Civitai API Key 已补全）
T3 en_keys.txt 与 en 表 key 集合一致（双向）
T4 模块级冻结修复：en 语言下构造 DropZone，占位文本含英文
   （"Drop images here"），副文本含英文；PLACEHOLDER_TEXT_KEY 保留 zh 原文
T5 DropZone 占位文本 en/es/ja 均有非空翻译

运行：python tests/test_v42_i18n_audit.py
"""
import ast
import os
import sys
import tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")

from PySide6.QtWidgets import QApplication, QMessageBox, QLabel

QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)

from app import i18n
from app.data_store import DataStore
from app.ui.collect_panel import DropZone, PLACEHOLDER_TEXT_KEY
from app.ui.style import APP_QSS

ROOT = Path(__file__).resolve().parent.parent

ok = True


def check(name: str, cond: bool, extra: str = "") -> None:
    global ok
    print(f"  {'✓' if cond else '✗'} {name}" + (f"  [{extra}]" if extra and not cond else ""))
    if not cond:
        ok = False


# ---------- T1: 三表 key 集合一致 + 非空 ----------
print("[T1] en/es/ja 三表 key 集合一致 + 值非空")
src = (ROOT / "app" / "i18n.py").read_text(encoding="utf-8")
tree = ast.parse(src)
tables = None
for node in ast.walk(tree):
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_LANG_TABLES"
                                            for t in node.targets):
        tables = {k.value: {kk.value: vv.value for kk, vv in zip(v.keys, v.values)}
                  for k, v in zip(node.value.keys, node.value.values)}
en, es, ja = tables["en"], tables["es"], tables["ja"]
check("T1 en==es key 集合", set(en) == set(es), f"{len(en)}/{len(es)}")
check("T1 es==ja key 集合", set(es) == set(ja), f"{len(es)}/{len(ja)}")
empty = [k for k in en if not en.get(k)] + [k for k in es if not es.get(k)] + [k for k in ja if not ja.get(k)]
check("T1 三表无空值", not empty, f"empty={empty[:5]}")

# ---------- T2: 遍历 tr() 字面量 ----------
print("[T2] 遍历 tr()/tr_format() 字面量，全部在表中")
calls = set()
for path in sorted(list((ROOT / "app").rglob("*.py"))) + [ROOT / "main.py"]:
    ptree = ast.parse(path.read_text(encoding="utf-8"))
    for n in ast.walk(ptree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("tr", "tr_format"):
            if n.args and isinstance(n.args[0], ast.Constant) and isinstance(n.args[0].value, str):
                calls.add(n.args[0].value)
missing = sorted(c for c in calls if c not in en)
check("T2 所有 tr() 字面量均存在于 en 表", not missing, f"missing={missing}")
# 这些 key 在 zh 下也应原样可用（t() 无翻译返回原文）
check("T2 三表均含专有名词 AI-Prompt-Vault",
      "AI-Prompt-Vault" in en and "AI-Prompt-Vault" in es and "AI-Prompt-Vault" in ja)
check("T2 三表均含 Civitai API Key",
      "Civitai API Key" in en and "Civitai API Key" in es and "Civitai API Key" in ja)

# ---------- T3: en_keys.txt 同步 ----------
print("[T3] en_keys.txt 与 en 表 key 集合一致")
txt_keys = set()
for ln in (ROOT / "en_keys.txt").read_text(encoding="utf-8").splitlines():
    s = ln.strip()
    if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
        try:
            txt_keys.add(ast.literal_eval(s))
        except Exception:
            pass
check("T3 en_keys.txt 集合 == en 表", txt_keys == set(en),
      f"missing={sorted(set(en)-txt_keys)[:5]} extra={sorted(txt_keys-set(en))[:5]}")
check("T3 en_keys.txt 含新增 key 重新扫描输出文件夹",
      "重新扫描输出文件夹，立即显示新增图片（手动刷新）" in txt_keys)

# ---------- T4: 模块级冻结修复（DropZone en 语言下显示英文） ----------
print("[T4] en 语言 DropZone 占位/副文本为英文")
app = QApplication([])
app.setStyleSheet(APP_QSS)
td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "en")
check("T4 PLACEHOLDER_TEXT_KEY 保留 zh 原文",
      PLACEHOLDER_TEXT_KEY.startswith("把网页上的例图直接拖到这里"),
      repr(PLACEHOLDER_TEXT_KEY[:20]))
dz = DropZone()
dz.show()
app.processEvents()
text = dz.text.text()
sub = dz.sub.text()
check("T4 占位文本含 'Drop images here'", "Drop images here" in text, repr(text[:60]))
check("T4 占位文本不含中文『把网页』", "把网页" not in text, repr(text[:60]))
check("T4 副文本含 'Drop multiple images'", "Drop multiple images" in sub, repr(sub[:60]))
check("T4 副文本不含中文『支持一次』", "支持一次" not in sub, repr(sub[:60]))

# ---------- T5: 占位文本三语言非空 ----------
print("[T5] 占位/副文本三语言翻译非空")
key_ph = PLACEHOLDER_TEXT_KEY
key_sub = "支持一次拖入多张图片，也支持拖入本地图片文件"
for lang, table in (("en", en), ("es", es), ("ja", ja)):
    check(f"T5 {lang} 占位文本非空", bool(table.get(key_ph)), repr(table.get(key_ph, "")[:40]))
    check(f"T5 {lang} 副文本非空", bool(table.get(key_sub)), repr(table.get(key_sub, "")[:40]))
# 语言切回 zh 不影响后续
i18n.init(store.settings_path(), "zh")

print()
print("v4.2 i18n 全语言审计", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
