"""v3.5 剪贴板兼容性：复制前清理无效控制字符（NULL / ASCII 控制字符 / DEL）。

背景：用户反馈部分提示词/文件名导入后出现方块（tofu），且含方块或中文的提示词
「一键复制」到下游工具（SD WebUI / ComfyUI）不可用。实测剪贴板层面可 round-trip
任意 unicode，真正的问题是无害控制字符（如 NULL \\x00）被下游工具拒绝/截断，
或在字体替换下显示为方块。修复：复制前统一移除 ASCII 控制字符（保留 \\t \\n \\r
与全部可见 unicode——中文/emoji/私用区/非 BMP），并给出「已清理 N 个不可见字符」
的可见反馈。

覆盖：
1. T1 sanitize_for_clipboard：NULL/控制字符被清，中文/emoji/私用区/换行/制表保留；
   removed_count 正确
2. T2 sanitize 边界：空字符串、全控制字符、混合、超长文本（>10000 字符）
3. T3 safe_copy_to_clipboard：setText 后 QApplication.clipboard().text() == cleaned
4. T4 复制按钮回调：detail_sidebar._copy_record("positive") 对含 NULL 的记录 →
   反馈「已清理 1 个不可见字符」且剪贴板正确
5. T5 i18n 三表（en/es/ja）key 集合一致 + 新 key 齐备 + en_keys.txt 同步

运行：python tests/test_v35_clipboard.py
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.text_clean import sanitize_for_clipboard, safe_copy_to_clipboard
from app.ui.detail_sidebar import DetailSidebar

app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)

ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {name}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        ok = False

td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")


# ============ T1: sanitize_for_clipboard 基础 ============
print("[T1] sanitize_for_clipboard：控制字符被清，可见字符保留")
text1 = "hello\x00world\u4e2d\u6587\U0001F3AF\ue000\n\t\r "
cleaned1, removed1 = sanitize_for_clipboard(text1)
check("T1 NULL 被移除、removed==1", removed1 == 1, f"(removed={removed1})")
check("T1 中文/emoji/私用区/换行/制表/空格保留",
      cleaned1 == "helloworld中文🎯\ue000\n\t\r ",
      repr(cleaned1))
check("T1 清理后不再含 \\x00", "\x00" not in cleaned1)

# 全部 C0 控制字符（除 \t\n\r）+ DEL 都应被移除
ctrl_chars = "".join(chr(c) for c in range(0x00, 0x20) if c not in (0x09, 0x0A, 0x0D)) + "\x7f"
cleaned2, removed2 = sanitize_for_clipboard(ctrl_chars)
check("T1 全部 30 个控制字符+DEL 被清空", removed2 == 30 and cleaned2 == "",
      f"(removed={removed2}, cleaned={cleaned2!r})")

# \t \n \r 必须保留
cleaned3, removed3 = sanitize_for_clipboard("a\tb\nc\rd")
check("T1 制表/换行/回车保留", cleaned3 == "a\tb\nc\rd" and removed3 == 0,
      repr(cleaned3))

# 无私用区/非 BMP 字符被误伤
cleaned4, removed4 = sanitize_for_clipboard("中文🎯\ue000\U0001F680\U00010000")
check("T1 中文/emoji/私用区/非 BMP 全部保留", removed4 == 0 and cleaned4 == "中文🎯\ue000\U0001F680\U00010000",
      repr(cleaned4))


# ============ T2: 边界 ============
print("[T2] sanitize 边界：空/全控制/混合/超长")
c2a, r2a = sanitize_for_clipboard("")
check("T2 空字符串 -> ('', 0)", c2a == "" and r2a == 0, f"({c2a!r}, {r2a})")
c2b, r2b = sanitize_for_clipboard("\x00\x01\x02\x1f\x7f")
check("T2 全控制字符 -> ('', 5)", c2b == "" and r2b == 5, f"({c2b!r}, {r2b})")
c2c, r2c = sanitize_for_clipboard("a\x00b\x1fc")
check("T2 混合 -> 'abc'，removed=2", c2c == "abc" and r2c == 2, f"({c2c!r}, {r2c})")
long_text = ("x" * 10001) + "\x00"
c2d, r2d = sanitize_for_clipboard(long_text)
check("T2 超长(>10000) 只清 1 个 NULL", r2d == 1 and len(c2d) == 10001,
      f"(removed={r2d}, len={len(c2d)})")
# 无控制字符时不重建字符串（同一对象）
pure = "pure text 纯文本"
c2e, r2e = sanitize_for_clipboard(pure)
check("T2 无控制字符时返回原对象", r2e == 0 and c2e is pure, f"(removed={r2e})")


# ============ T3: safe_copy_to_clipboard ============
print("[T3] safe_copy_to_clipboard：清理后写入剪贴板")
ok3, rem3 = safe_copy_to_clipboard("best\x00quality 中文🎯\n")
check("T3 返回 (True, 1)", ok3 is True and rem3 == 1, f"({ok3}, {rem3})")
check("T3 剪贴板 == 清理后文本",
      app.clipboard().text() == "bestquality 中文🎯\n",
      repr(app.clipboard().text()))
ok3b, rem3b = safe_copy_to_clipboard("")
check("T3 空文本 -> (False, 0)", ok3b is False and rem3b == 0, f"({ok3b}, {rem3b})")
ok3c, rem3c = safe_copy_to_clipboard("\x00\x01\x02")
check("T3 全控制字符 -> (False, 3)", ok3c is False and rem3c == 3, f"({ok3c}, {rem3c})")
ok3d, rem3d = safe_copy_to_clipboard("\ue000🎯中文 normal")
check("T3 私用区/emoji/中文 round-trip 成功", ok3d is True and rem3d == 0,
      f"({ok3d}, {rem3d})")


# ============ T4: 复制按钮回调（detail_sidebar._copy_record） ============
print("[T4] detail_sidebar._copy_record('positive')：含 NULL 记录 → 清理+反馈")
sidebar = DetailSidebar(store)
rec_with_null = {
    "id": "clip-null-1", "title": "含 NULL 的记录",
    "positive": "masterpiece\x00best quality", "negative": "blurry",
    "models": [], "steps": "28", "sampler": "DPM++", "cfg": "7", "seed": "1",
    "base_model": "其他", "base_model_raw": "",
}
sidebar._record = rec_with_null
sidebar._copy_record("positive")
check("T4 剪贴板已清理 NULL",
      app.clipboard().text() == "masterpiecebest quality",
      repr(app.clipboard().text()))
fb = sidebar.copy_status.text()
check("T4 反馈含「已复制 ✓」", fb.startswith("已复制 ✓"), repr(fb))
check("T4 反馈含「已清理 1 个不可见字符」", "已清理 1 个不可见字符" in fb, repr(fb))

# 负向也走同一逻辑
rec_neg = {"id": "clip-null-2", "title": "t", "positive": "p",
           "negative": "n\x00n2", "models": [], "base_model": "其他"}
sidebar._record = rec_neg
sidebar._copy_record("negative")
check("T4 负向剪贴板已清理 NULL",
      app.clipboard().text() == "nn2", repr(app.clipboard().text()))
check("T4 负向反馈含「已清理 1 个不可见字符」",
      "已清理 1 个不可见字符" in sidebar.copy_status.text(),
      repr(sidebar.copy_status.text()))

# 无控制字符时不显示清理提示
rec_clean = {"id": "clip-clean", "title": "t", "positive": "plain", "negative": "",
             "models": [], "base_model": "其他"}
sidebar._record = rec_clean
sidebar._copy_record("positive")
check("T4 无控制字符时反馈不含「已清理」",
      "已清理" not in sidebar.copy_status.text(),
      repr(sidebar.copy_status.text()))
check("T4 无控制字符时剪贴板原样",
      app.clipboard().text() == "plain", repr(app.clipboard().text()))


# ============ T5: i18n 三表一致 + 新 key 齐备 + en_keys.txt 同步 ============
print("[T5] i18n 三表 key 集合一致 + 新 key 齐备")
en_keys = set(i18n._LANG_TABLES["en"].keys())
es_keys = set(i18n._LANG_TABLES["es"].keys())
ja_keys = set(i18n._LANG_TABLES["ja"].keys())
check("T5 es key 集 == en（无缺无多）", en_keys == es_keys,
      f"差集 {sorted(en_keys ^ es_keys)[:5]}")
check("T5 ja key 集 == en（无缺无多）", en_keys == ja_keys,
      f"差集 {sorted(en_keys ^ ja_keys)[:5]}")
check("T5 三表数量一致", len(en_keys) == len(es_keys) == len(ja_keys),
      f"({len(en_keys)}/{len(es_keys)}/{len(ja_keys)})")

import re
ph = re.compile(r"\{[^}]+\}")
ph_bad = []
for lang in ("es", "ja"):
    tab = i18n._LANG_TABLES[lang]
    for k, en_v in i18n._LANG_TABLES["en"].items():
        if set(ph.findall(en_v)) != set(ph.findall(tab.get(k, ""))):
            ph_bad.append(f"{lang}:{k}")
check("T5 es/ja 全部 {占位符} 保留", not ph_bad, ph_bad[:5])

for key in ("已清理 {n} 个不可见字符", "复制失败：{err}"):
    check(f"T5 新 key「{key}」三表齐备",
          all(key in i18n._LANG_TABLES[l] for l in ("en", "es", "ja")))

# 占位符替换真实可用（zh 界面）
i18n.set_language("zh")
check("T5 tr_format(已清理) zh 可用",
      i18n.tr_format("已清理 {n} 个不可见字符", n=3) == "已清理 3 个不可见字符",
      repr(i18n.tr_format("已清理 {n} 个不可见字符", n=3)))
check("T5 tr_format(复制失败) zh 可用",
      i18n.tr_format("复制失败：{err}", err="test") == "复制失败：test",
      repr(i18n.tr_format("复制失败：{err}", err="test")))

# en_keys.txt 同步（新 key 已追加）
en_txt = (Path(__file__).resolve().parent.parent / "en_keys.txt").read_text(encoding="utf-8")
check("T5 en_keys.txt 含「已清理 {n} 个不可见字符」",
      "'已清理 {n} 个不可见字符'" in en_txt)
check("T5 en_keys.txt 含「复制失败：{err}」", "'复制失败：{err}'" in en_txt)

# 恢复语言，避免影响后续测试
i18n.init(store.settings_path(), "zh")

print()
print("v3.5 剪贴板兼容性", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
