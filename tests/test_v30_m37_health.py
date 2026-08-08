"""M3.7 模型健康检查：空文件/疑似损坏/下载残留 状态标记 + 摘要 + 详情。"""
import os, sys, tempfile
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

from app import i18n
from app.data_store import DataStore
from app.ui.style import APP_QSS
from app.ui.model_panel import ModelPanel

app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)
td = Path(tempfile.mkdtemp())
comfy = td / "ComfyUI"
(comfy / "models" / "checkpoints").mkdir(parents=True)
(comfy / "models" / "loras").mkdir(parents=True)
# 正常模型（2MB）
(comfy / "models" / "checkpoints" / "good.safetensors").write_bytes(b"G" * 2_000_000)
# 空文件
(comfy / "models" / "checkpoints" / "empty.safetensors").write_bytes(b"")
# 疑似损坏（<1KB）
(comfy / "models" / "loras" / "tiny.safetensors").write_bytes(b"<!DOCTYPE html>")
# 下载残留（.part 存在）
(comfy / "models" / "loras" / "half.safetensors").write_bytes(b"H" * 500_000)
(comfy / "models" / "loras" / "half.safetensors.part").write_bytes(b"H" * 300_000)

store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")
store.save_setting("comfyui_dir", str(comfy))

ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {name}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        ok = False

panel = ModelPanel(store)
panel.reload()
app.processEvents()

# ---- T1: 状态识别 ----
by_rel = {m["rel"]: m for m in panel._models}
check("T1 扫描到 4 个模型", len(panel._models) == 4, f"({len(panel._models)})")
check("T1 good=ok", by_rel.get("checkpoints/good.safetensors", {}).get("status") == "ok")
check("T1 empty=zero", by_rel.get("checkpoints/empty.safetensors", {}).get("status") == "zero")
check("T1 tiny=tiny", by_rel.get("loras/tiny.safetensors", {}).get("status") == "tiny")
check("T1 half=part", by_rel.get("loras/half.safetensors", {}).get("status") == "part")

# ---- T2: 摘要 ----
check("T2 摘要显示异常数", "3" in panel.health_label.text() and "⚠" in panel.health_label.text(),
      repr(panel.health_label.text()))

# ---- T3: 树节点标记 ----
texts = []
def walk(items):
    for it in items:
        texts.append(it.text(0))
        walk([it.child(i) for i in range(it.childCount())])
walk([panel.tree.topLevelItem(i) for i in range(panel.tree.topLevelItemCount())])
check("T3 异常模型带 ⚠", any("empty" in t and "⚠" in t for t in texts))
check("T3 正常模型无标记", any(t.startswith("good.safetensors") and "⚠" not in t for t in texts))

# ---- T4: 选中异常模型 → 详情健康说明 ----
def select(rel):
    panel.tree.clearSelection()
    for i in range(panel.tree.topLevelItemCount()):
        g = panel.tree.topLevelItem(i)
        for j in range(g.childCount()):
            c = g.child(j)
            if c.data(0, 0x0100) == rel:  # Qt.UserRole
                c.setSelected(True)
                panel._on_select()
                return c

c = select("checkpoints/empty.safetensors")
check("T4 空文件详情提示", "空文件" in panel.info_health.text(), repr(panel.info_health.text()))
select("loras/half.safetensors")
check("T4 残留详情提示", ".part" in panel.info_health.text(), repr(panel.info_health.text()))
select("checkpoints/good.safetensors")
check("T4 正常模型无提示", panel.info_health.text() == "", repr(panel.info_health.text()))

print()
print("M3.7 模型健康检查", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
