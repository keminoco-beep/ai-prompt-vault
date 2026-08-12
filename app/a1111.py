"""Automatic1111 / WebUI outputs 目录集成：扫描图片并导入资料库。

- scan_outputs: 递归收集 outputs 下支持的图片文件（png 优先，含元数据）
- import_from_outputs: 逐张复制进资料库 + 提取内嵌生成参数 + 生成缩略图 + 建记录
- 按内容 SHA-256 去重（同一张图重复导入自动跳过）

不依赖任何外部库，后台线程调用不阻塞 UI。
"""
import hashlib
import time
from pathlib import Path

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}


def scan_outputs(out_dir) -> list:
    """递归扫描 outputs 目录，返回图片文件路径列表（按修改时间排序，新的在前）。"""
    out_dir = Path(out_dir)
    if not out_dir.is_dir():
        return []
    files = []
    for p in out_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in IMAGE_EXTS:
            files.append(p)
    files.sort(key=lambda p: p.stat().st_mtime if p.exists() else 0, reverse=True)
    return files


def _file_sha256(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def import_from_outputs(store, out_dir, progress_cb=None):
    """导入 A1111 outputs 目录的全部图片。

    progress_cb: callback(done, total, current_name)，后台线程调用。
    返回 (imported, skipped, errors)。
    """
    files = scan_outputs(out_dir)
    total = len(files)
    # 已存在图片的内容指纹（避免重复导入）
    existing = set()
    for rec in store.records:
        f = rec.get("image_file")
        if f and (store.images_dir / f).exists():
            try:
                existing.add(_file_sha256(store.images_dir / f))
            except Exception:
                pass
    imported = skipped = errors = 0
    for i, src in enumerate(files):
        try:
            if progress_cb:
                progress_cb(i, total, src.name)
            digest = _file_sha256(src)
            if digest in existing:
                skipped += 1
                continue
            existing.add(digest)
            rec = _import_one(store, src)
            if rec:
                imported += 1
            else:
                skipped += 1
        except Exception:
            errors += 1
    if progress_cb:
        progress_cb(total, total, "")
    return imported, skipped, errors


def _import_one(store, src: Path):
    """复制一张图进资料库并提取元数据，返回记录 dict（无可识别数据也保存）。"""
    from app.image_meta import extract_image_meta
    from app.thumbs import make_thumbnail, image_size

    name = store.copy_file_into(str(src))
    image_path = str(store.images_dir / name)
    w, h = image_size(image_path)
    meta = extract_image_meta(image_path)

    models = []
    mn = meta.get("model_name") or ""
    if mn:
        models.append({"name": mn, "type": "大模型", "url": "", "base_model": ""})
    loras = meta.get("loras") or []

    tname = name.rsplit(".", 1)[0] + ".png"
    thumb = tname if make_thumbnail(image_path, str(store.thumbs_dir / tname), 400) else ""

    rec = {
        "title": (meta.get("positive") or "")[:24] or src.stem[:24],
        "tags": [],
        "positive": meta.get("positive") or "",
        "negative": meta.get("negative") or "",
        "base_model": meta.get("base_model") or "其他",
        "base_model_raw": meta.get("base_model_raw") or "",
        "models": models,
        "loras": loras,
        "sampler": meta.get("sampler") or "",
        "steps": meta.get("steps") or "",
        "cfg": meta.get("cfg") or "",
        "seed": meta.get("seed") or "",
        "width": w or 0,
        "height": h or 0,
        "source": "local",
        "source_url": "",
        "image_file": name,
        "thumb_file": thumb,
        "media_type": "image",
        "video_file": "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    store.add(rec)
    return rec
