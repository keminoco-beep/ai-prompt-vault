"""ComfyUI 集成：模型类型 → ComfyUI models/ 子目录映射，模型文件下载。

- 把图库记录里的模型（大模型/LoRA/嵌入/VAE/...）下载到 ComfyUI 对应
  类别的 models 子目录（如 checkpoints/ loras/ embeddings/ ...）。
- 支持 Civitai 模型页链接解析为真实下载地址（双域名容错）。
- "其他"等无标准目录的类型需用户手动指定子目录。
"""
import re
from pathlib import Path

import requests

from app import civitai

# 模型类型（软件内中文 key）→ ComfyUI models/ 标准子目录
COMIFY_MODEL_DIRS = {
    "大模型": "checkpoints",
    "LoRA": "loras",
    "嵌入": "embeddings",
    "VAE": "vae",
    "超网络": "hypernetworks",
    "ControlNet": "controlnet",
    "放大模型": "upscale_models",
    "文本编码器": "text_encoders",
    "CLIP视觉": "clip_vision",
    "工作流": "configs",
    "运动模块": "motion_models",
}

# 扩展名白名单（按内容/URL 判定），下载用
MODEL_EXTENSIONS = (".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".onnx",
                    ".gguf", ".json", ".png", ".txt", ".patch", ".pruned")

INVALID_NAME_CHARS = re.compile(r'[\\/:*?"<>|\r\n\t]+')


class ComfyError(Exception):
    pass


def safe_filename(name: str, ext: str = "") -> str:
    """清洗文件名：去掉非法字符、截断、补扩展名。"""
    name = INVALID_NAME_CHARS.sub("_", name or "").strip(" .")
    if not name:
        name = "model"
    if ext and not name.lower().endswith(ext.lower()):
        name += ext
    return name[:160]


def comfy_dir_for(comfyui_dir, mtype: str, picked: str = "") -> Path:
    """返回模型类型对应的 ComfyUI 目标目录。

    comfyui_dir: ComfyUI 根目录（含 models/ 子目录）。
    picked:      "其他"等类型时用户手动选择的子目录名。
    返回目录不存在时自动创建。
    """
    root = Path(comfyui_dir)
    sub = COMIFY_MODEL_DIRS.get(mtype, "") or picked
    if not sub:
        raise ComfyError(f"未知模型类型：{mtype}")
    d = (root / "models" / sub) if not (root.name == sub) else root
    # 若用户选择的就是根目录下的子目录名，避免双重嵌套
    if (root / "models").exists() and (root / "models" / sub).is_dir():
        d = root / "models" / sub
    d.mkdir(parents=True, exist_ok=True)
    return d


def available_subdirs(comfyui_dir) -> list:
    """列出 ComfyUI models/ 下已存在的子目录名（供用户选择）。"""
    root = Path(comfyui_dir)
    m = root / "models"
    if not m.is_dir():
        return []
    return sorted([p.name for p in m.iterdir() if p.is_dir()])


def pick_ext(url: str, fallback: str = ".safetensors") -> str:
    """从 URL 推断扩展名。"""
    name = (url or "").split("?")[0].lower()
    for ext in MODEL_EXTENSIONS:
        if name.endswith(ext):
            return ext
    # Civitai 下载链接常带 ?filename=xxx.safetensors
    m = re.search(r"filename=([^&]+)", url or "")
    if m:
        fn = m.group(1).lower()
        for ext in MODEL_EXTENSIONS:
            if fn.endswith(ext):
                return ext
    return fallback


def resolve_download_url(model_url: str, timeout: float = 15.0) -> str:
    """把模型页链接解析为 Civitai 官方下载端口 URL（绝不返回页面 URL）。

    - /models/{id}：走 /api/v1/models/{id} 取第一个 Model 文件的 versionId，
      构造 https://civitai.com/api/download/models/{vid}?type=Model&format=SafeTensor
    - 已是 /api/download/models/{vid}：补 type=Model 参数
    - 其余：抛错（避免把页面 URL 当下载源）
    """
    url = (model_url or "").strip()
    if not url:
        raise ComfyError("模型链接为空")
    if "/api/download/models/" in url:
        base, _, q = url.partition("?")
        params = [p for p in q.split("&") if p and not p.startswith("type=")]
        params.append("type=Model")
        return base + "?" + "&".join(params)
    m = re.search(r"/models/(\d+)", url)
    if m:
        info = civitai.api_json(f"models/{m.group(1)}", timeout)
        for v in (info.get("modelVersions") or []):
            for f in (v.get("files") or []):
                if f.get("type") != "Model":
                    continue
                vid = v.get("id")
                if not vid:
                    continue
                base = f"https://civitai.com/api/download/models/{vid}"
                fmt = "SafeTensor" if "safetensor" in (f.get("format") or "").lower() else ""
                params = ["type=Model"] + ([f"format={fmt}"] if fmt else [])
                return base + "?" + "&".join(params)
        raise ComfyError("该模型暂无可下载文件")
    # 其他 URL（合法 CDN 直链等）原样返回，保持兼容
    return url


def cleanup_partial_files(comfyui_dir) -> int:
    """清理 ComfyUI models/ 下残留的 .part 半成品文件（取消/崩溃遗留）。"""
    if not comfyui_dir:
        return 0
    root = Path(comfyui_dir) / "models"
    if not root.is_dir():
        return 0
    n = 0
    for p in root.rglob("*.part"):
        try:
            p.unlink()
            n += 1
        except Exception:
            pass
    return n


def _looks_like_error_page(head: bytes) -> bool:
    """检测响应体前 512 字节是否为 HTML 错误页 / JSON 错误（而非模型文件）。"""
    s = head[:512].lower()
    return (b"<!doctype html" in s or b"<html" in s or b'{"error"' in s
            or b"<title>cf-error" in s or b"rate limit" in s or b"blocked" in s)


def _url_variants(url: str) -> list:
    """生成下载候选方案：原链接 + 补 type/format 参数 + 换 civitai.red 域名。"""
    variants = [url]
    base, _, q = url.partition("?")
    if "/api/download/models/" in base:
        params = [p for p in q.split("&") if p]
        if not any(p.startswith("type=") for p in params):
            params.append("type=Model")
        if not any(p.startswith("format=") for p in params):
            params.append("format=SafeTensor")
        if params:
            variants.append(base + "?" + "&".join(params))
    out = []
    for v in variants:
        out.append(v)
        if "civitai.com" in v:
            out.append(v.replace("civitai.com", "civitai.red", 1))
    # 去重保序
    seen, final = set(), []
    for v in out:
        if v not in seen:
            seen.add(v)
            final.append(v)
    return final


def download_file(url: str, dest: Path, progress_cb=None, cancel_cb=None, pause_cb=None,
                  timeout: float = 60.0, min_size: int = 1024,
                  api_key: str = "", resume_offset: int = 0) -> tuple:
    """流式下载 url 到 dest，支持断点续传（Range）与暂停。

    - resume_offset: >0 时发送 Range: bytes={offset}- 续传（服务器不支持则从头下载）
    - pause_cb: callback() -> bool，返回 True 时停止并保留 .part（暂停）
    - cancel_cb: callback() -> bool，返回 True 时停止并删除 .part（取消）
    - api_key: Civitai API Key（可选），加 Authorization: Bearer 头
    - 每个候选方案下载后校验：内容非 HTML 错误页、大小 >= min_size
    - 失败时把原因追加到 Library/download_errors.log（便于排查）
    返回 (ok, message)。
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    headers = {**civitai.UA, "Accept": "*/*"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    errs = []
    for attempt_url in _url_variants(url):
        try:
            if pause_cb and pause_cb():
                return False, "已暂停"
            if cancel_cb and cancel_cb():
                return False, "已取消"
            req_headers = dict(headers)
            off = resume_offset
            if off > 0:
                req_headers["Range"] = f"bytes={off}-"
            with requests.get(attempt_url, headers=req_headers, timeout=timeout,
                              stream=True, allow_redirects=True) as r:
                if r.status_code == 206:
                    # 部分内容：从断点续传
                    base_got = off
                    mode = "ab"
                    total = off + max(0, int(r.headers.get("content-length") or 0))
                elif r.status_code == 200:
                    # 服务器忽略 Range：从头下载
                    base_got = 0
                    mode = "wb"
                    try:
                        total = max(0, int(r.headers.get("content-length") or 0))
                    except (TypeError, ValueError):
                        total = 0
                else:
                    r.raise_for_status()
                ctype = r.headers.get("content-type") or ""
                # 预判：响应类型是 HTML → 换方案
                if "text/html" in ctype.lower():
                    raise ComfyError("返回 HTML 错误页（可能需要 Civitai API Key）")
                got = base_got
                first = b""
                with open(tmp, mode) as f:
                    for chunk in r.iter_content(chunk_size=65536):
                        if chunk:
                            f.write(chunk)
                            got += len(chunk)
                            if len(first) < 512:
                                first += chunk[: 512 - len(first)]
                            if progress_cb:
                                progress_cb(got, total)
                        if pause_cb and pause_cb():
                            raise ComfyError("已暂停")
                        if cancel_cb and cancel_cb():
                            raise ComfyError("已取消")
                if total and got != total:
                    raise ComfyError(f"下载不完整（{got}/{total}）")
                if got < min_size:
                    raise ComfyError(f"文件过小（{got} 字节），疑似错误响应")
                if _looks_like_error_page(first):
                    raise ComfyError("下载到的是错误页（HTML/JSON），可能需要 Civitai API Key")
            tmp.replace(dest)
            return True, str(dest)
        except Exception as e:  # noqa: BLE001
            if pause_cb and pause_cb():
                return False, "已暂停"
            if cancel_cb and cancel_cb():
                return False, "已取消"
            errs.append(f"{attempt_url.split('?')[0][-40:]} → {str(e)[:80]}")
            if tmp.exists():
                try:
                    tmp.unlink()
                except Exception:
                    pass
    msg = "；".join(errs) or "下载失败"
    _log_download_error(dest.name, url, msg)
    return False, msg


def _log_download_error(model_name: str, url: str, reason: str):
    """把下载失败详情追加到 exe 同目录 Library/download_errors.log。"""
    try:
        from datetime import datetime
        from app.config import library_dir
        p = library_dir() / "download_errors.log"
        line = (f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                f"{model_name} | {url}\n    {reason}\n")
        with open(p, "a", encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass
