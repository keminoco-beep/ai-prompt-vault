"""作品集导出：把选中记录打包为 zip（图片/视频 + prompts.json 清单）。

- prompts.json：完整字段（标题/提示词/模型/参数/来源等），便于二次整理或分享
- 图片/视频文件按记录文件名归档
"""
import json
import shutil
import time
from pathlib import Path


def export_records(store, records: list, dest_dir: str) -> tuple:
    """导出 records 到 dest_dir/export_<时间戳>/。

    返回 (导出数, 错误信息或 "")。记录无媒体文件时仍导出 prompts.json 条目。
    """
    try:
        dest = Path(dest_dir) / f"AI-Prompt-Vault-导出-{time.strftime('%Y%m%d_%H%M%S')}"
        dest.mkdir(parents=True, exist_ok=True)
        media_dir = dest / "media"
        media_dir.mkdir(exist_ok=True)
        n = 0
        errors = []
        manifest = []
        for r in records:
            item = dict(r)
            # 媒体文件归档
            for key, base_dir in (("image_file", store.images_dir),
                                  ("video_file", store.videos_dir)):
                fname = r.get(key)
                if fname:
                    src = base_dir / fname
                    if src.exists():
                        try:
                            shutil.copy2(str(src), str(media_dir / fname))
                            item[key] = fname  # 相对 media/ 的文件名
                        except Exception as e:
                            errors.append(f"{fname}: {e}")
            # 缩略图不入包（体积大，可由媒体文件重建）
            item.pop("thumb_file", None)
            manifest.append(item)
            n += 1
        (dest / "prompts.json").write_text(
            json.dumps({"exported_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                        "count": n, "records": manifest},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        return n, "；".join(errors) if errors else ""
    except Exception as e:  # noqa: BLE001
        return 0, str(e)