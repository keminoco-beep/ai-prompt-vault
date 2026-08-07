"""数据存储：资料库子文件夹内的索引 JSON 与图片文件管理。"""
import json
import shutil
import time
import uuid
from pathlib import Path

import sys

if sys.platform == "win32":
    try:
        import ctypes
    except Exception:
        ctypes = None


def _ts() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def normalize_record(rec: dict) -> dict:
    """记录字段规范化：补齐新字段 models[]/base_model，并兼容迁移旧数据。"""
    if not isinstance(rec, dict):
        return rec
    rec.setdefault("models", [])
    rec.setdefault("base_model", "其他")
    rec.setdefault("base_model_raw", "")
    rec.setdefault("loras", [])
    rec.setdefault("group", "")   # 手动分组名，"" = 未分组

    # 旧数据迁移：只有 model_name / model_type / loras，没有 models[] 时补齐
    models = rec.get("models") or []
    if not models and (rec.get("model_name") or rec.get("loras")):
        models = []
        if rec.get("model_name"):
            models.append({
                "name": str(rec.get("model_name") or ""),
                "type": str(rec.get("model_type") or "其他"),
                "url": "",
                "base_model": rec.get("base_model_raw") or "",
            })
        for lo in (rec.get("loras") or []):
            if isinstance(lo, str) and lo.strip():
                models.append({"name": lo.strip(), "type": "LoRA", "url": "",
                               "base_model": ""})
        rec["models"] = models

    # loras 与 models 中的 LoRA 保持一致（便于筛选与展示）
    if models:
        loras = [m["name"] for m in models
                 if m.get("type") == "LoRA" and m.get("name")]
        for lo in (rec.get("loras") or []):
            if lo and lo not in loras:
                loras.append(lo)
        rec["loras"] = loras

    # 主模型大类缺失时尝试从 models 推导
    if rec.get("base_model") in (None, "", "其他") and models:
        try:
            from app.civitai import base_model_group
            for m in models:
                if m.get("base_model"):
                    rec["base_model"] = base_model_group(m["base_model"])
                    rec["base_model_raw"] = m["base_model"]
                    break
        except Exception:
            pass
    if not rec.get("base_model"):
        rec["base_model"] = "其他"
    return rec


class DataStore:
    """负责资料库文件夹：images/  thumbs/  trash/  data.json"""

    def __init__(self, root: Path):
        self.root = Path(root)
        self.images_dir = self.root / "images"
        self.thumbs_dir = self.root / "thumbs"
        self.trash_dir = self.root / "trash"
        for d in (self.images_dir, self.thumbs_dir, self.trash_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.data_file = self.root / "data.json"
        self._groups = []
        self._records = self._load()
        self._seq = 0

    # ---------- 索引 ----------
    def _load(self) -> list:
        if not self.data_file.exists():
            return []
        try:
            data = json.loads(self.data_file.read_text(encoding="utf-8"))
            self._groups = [g for g in (data.get("groups") or []) if isinstance(g, str) and g.strip()]
            recs = data.get("records", []) if isinstance(data, dict) else data
            return [normalize_record(r) for r in recs if isinstance(r, dict)]
        except Exception:
            # 索引损坏时备份后重建
            try:
                shutil.copy2(self.data_file, self.data_file.with_suffix(".bak.json"))
            except Exception:
                pass
            return []

    def save(self):
        payload = {"version": 1, "groups": self._groups, "records": self._records}
        tmp = self.data_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.data_file)

    # ---------- 手动分组 ----------
    @property
    def groups(self) -> list:
        return list(self._groups)

    def add_group(self, name: str) -> bool:
        name = (name or "").strip()
        if not name or name in self._groups:
            return False
        self._groups.append(name)
        self.save()
        return True

    def rename_group(self, old: str, new: str) -> bool:
        old = (old or "").strip()
        new = (new or "").strip()
        if not old or not new or old not in self._groups or new in self._groups:
            return False
        self._groups[self._groups.index(old)] = new
        for r in self._records:
            if r.get("group") == old:
                r["group"] = new
        self.save()
        return True

    def remove_group(self, name: str) -> bool:
        name = (name or "").strip()
        if not name or name not in self._groups:
            return False
        self._groups.remove(name)
        for r in self._records:
            if r.get("group") == name:
                r["group"] = ""
        self.save()
        return True

    def set_record_group(self, rid: str, group: str):
        rec = self.get(rid)
        if rec:
            rec["group"] = (group or "").strip()
            self.save()

    # ---------- 设置 ----------
    def settings_path(self) -> Path:
        return self.root / "settings.json"

    def load_setting(self, key: str, default=None):
        try:
            if self.settings_path().exists():
                data = json.loads(self.settings_path().read_text(encoding="utf-8"))
                return data.get(key, default)
        except Exception:
            pass
        return default

    def save_setting(self, key: str, value):
        try:
            data = {}
            if self.settings_path().exists():
                data = json.loads(self.settings_path().read_text(encoding="utf-8"))
            data[key] = value
            self.settings_path().write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

    # ---------- 记录 CRUD ----------
    @property
    def records(self) -> list:
        return self._records

    def get(self, rid: str):
        for r in self._records:
            if r["id"] == rid:
                return r
        return None

    def next_image_name(self, ext: str = "png") -> str:
        self._seq += 1
        return f"img_{_ts()}_{self._seq:03d}.{ext}"

    def add(self, record: dict) -> dict:
        rec = normalize_record(dict(record))
        rec.setdefault("id", uuid.uuid4().hex[:12])
        rec.setdefault("created_at", time.strftime("%Y-%m-%d %H:%M:%S"))
        self._records.append(rec)
        self.save()
        return rec

    def update(self, rid: str, fields: dict) -> dict:
        rec = self.get(rid)
        if not rec:
            return None
        rec.update(normalize_record(fields))
        rec["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        self.save()
        return rec

    def remove(self, rid: str) -> dict:
        """软删除：图片/缩略图移入 trash/，记录移除。"""
        rec = self.get(rid)
        if not rec:
            return None
        for key in ("image_file", "thumb_file"):
            f = rec.get(key)
            if f:
                src = self.images_dir / f if key == "image_file" else self.thumbs_dir / f
                if src.exists():
                    try:
                        shutil.move(str(src), str(self.trash_dir / src.name))
                    except Exception:
                        pass
        self._records = [r for r in self._records if r["id"] != rid]
        self.save()
        return rec

    def purge_trash(self):
        """清空回收站（真正删除）。"""
        for f in self.trash_dir.iterdir():
            try:
                if f.is_file():
                    f.unlink()
            except Exception:
                pass

    # ---------- 文件导入 ----------
    def save_uploaded_bytes(self, data: bytes, ext: str) -> str:
        name = self.next_image_name(ext)
        (self.images_dir / name).write_bytes(data)
        return name

    def copy_file_into(self, src: str) -> str:
        src = Path(src)
        ext = src.suffix.lower().lstrip(".") or "png"
        if ext not in ("png", "jpg", "jpeg", "webp", "bmp", "gif"):
            ext = "png"
        name = self.next_image_name(ext)
        shutil.copy2(str(src), str(self.images_dir / name))
        return name

    # ---------- 打开文件夹 ----------
    def reveal_in_explorer(self, path: str):
        import subprocess
        subprocess.Popen(["explorer", "/select,", str(path)] if sys.platform == "win32" else ["xdg-open", str(path)])

    def open_folder(self, path: str):
        import subprocess
        subprocess.Popen(["explorer", str(path)] if sys.platform == "win32" else ["xdg-open", str(path)])
