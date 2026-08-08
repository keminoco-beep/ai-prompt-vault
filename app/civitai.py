"""Civitai 链接解析与数据提取。

兼容 civitai.com 与 civitai.red 两个域名，均支持：
- 图片链接    https://civitai.com/images/123456
- 模型链接    https://civitai.com/models/123
- 版本链接    https://civitai.com/api/v1/model-versions/123

提取策略：
- 图片链接：解析网页内嵌的 __NEXT_DATA__（含完整 meta：正负提示词、采样器、
  步数、CFG、种子、LoRA 资源、模型等），图片地址取 og:image。
- 模型/版本链接：走官方 API /api/v1/models/{id} 与 /model-versions/{id}。
请求先试 civitai.com，失败自动切换到 civitai.red。
"""
import html as html_mod
import json
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

from app.i18n import t as tr, tr_format

UA = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

HOSTS = ["civitai.com", "civitai.red"]

_RE_IMG = re.compile(r"(?:civitai\.(?:com|red))/(?:api/v1/)?images?/(\d+)", re.I)
_RE_MODEL = re.compile(r"(?:civitai\.(?:com|red))/(?:api/v1/)?models?/(\d+)", re.I)
_RE_MODELV = re.compile(r"(?:civitai\.(?:com|red))/(?:api/v1/)?model-versions?/(\d+)", re.I)

# 资源类型 -> 中文类型
TYPE_LABEL = {
    "checkpoint": "大模型", "checkpoints": "大模型", "ckpt": "大模型",
    "lora": "LoRA", "locon": "LoRA", "lycoris": "LoRA",
    "textualinversion": "嵌入", "embedding": "嵌入", "ti": "嵌入",
    "vae": "VAE", "hypernetwork": "超网络", "hypernetworks": "超网络",
    "controlnet": "ControlNet", "other": "其他", "unknown": "其他",
}

# Civitai 官方 ModelType 枚举 -> 中文（用于模型清单展示与筛选）
MODEL_TYPE_MAP = {
    "Checkpoint": "大模型",
    "LORA": "LoRA", "LoCon": "LoRA", "DoRA": "LoRA",
    "TextualInversion": "嵌入", "Hypernetwork": "超网络",
    "Controlnet": "ControlNet", "VAE": "VAE", "Upscaler": "放大模型",
    "MotionModule": "运动模块", "TextEncoder": "文本编码器",
    "UNet": "UNet", "CLIPVision": "CLIP视觉", "CLIP": "CLIP", "LLM": "LLM",
    "Wildcards": "通配符", "Workflows": "工作流", "Detection": "检测",
    "VisionLanguage": "视觉语言", "AestheticGradient": "美学梯度",
    "Poses": "姿态", "Other": "其他",
}

# 主模型大类（按 Civitai 筛选中的 baseModel 聚合，用户常用视角）
BASE_MODEL_GROUPS = [
    "Flux.1", "Flux.2", "Krea 2", "SDXL", "Pony",
    "Illustrious", "NoobAI", "SD 1.5", "SD 3.5", "其他",
]


def model_type_label(raw) -> str:
    """Civitai ModelType -> 中文标签。"""
    return MODEL_TYPE_MAP.get(_to_str(raw).strip(), "其他")


def base_model_group(raw) -> str:
    """把 Civitai 原始 baseModel（如 'Flux.1 Krea'、'Krea 2'、'SDXL 1.0'）
    归并到用户视角的主模型大类。"""
    r = _to_str(raw).strip().lower()
    if not r or r in ("other", "unknown", "none"):
        return "其他"
    if "krea 2" in r or r == "krea2" or r.startswith("krea2"):
        return "Krea 2"
    if "flux.1" in r or r.startswith("flux1") or "flux 1" in r:
        return "Flux.1"
    if "flux.2" in r or r.startswith("flux2") or "flux 2" in r:
        return "Flux.2"
    if "sdxl" in r or "sd xl" in r:
        return "SDXL"
    if "pony" in r:
        return "Pony"
    if "illustrious" in r:
        return "Illustrious"
    if "noobai" in r:
        return "NoobAI"
    if re.match(r"sd ?[12]\.", r) or r.startswith("sd1") or r.startswith("sd2"):
        return "SD 1.5"
    if "sd 3" in r or "sd3" in r:
        return "SD 3.5"
    return "其他"


class CivitaiError(Exception):
    pass


# ---------------- 链接解析 ----------------
def parse_link(text: str):
    """解析 Civitai 链接，返回 {"kind": "image"|"model"|"model_version", "id": int} 或 None。"""
    if not text:
        return None
    m = _RE_IMG.search(text)
    if m:
        return {"kind": "image", "id": int(m.group(1))}
    m = _RE_MODELV.search(text)
    if m:
        return {"kind": "model_version", "id": int(m.group(1))}
    m = _RE_MODEL.search(text)
    if m:
        return {"kind": "model", "id": int(m.group(1))}
    return None


# ---------------- 基础请求（双域名容错） ----------------
def _get(host: str, path: str, timeout: float) -> requests.Response:
    r = requests.get(f"https://{host}/{path}", headers=UA, timeout=timeout)
    r.raise_for_status()
    return r


def request_path(path: str, timeout: float = 20.0) -> str:
    """请求相对路径（如 api/v1/models/1），双域名容错，返回文本。"""
    errs = []
    for host in HOSTS:
        try:
            return _get(host, path, timeout).text
        except Exception as e:  # noqa: BLE001
            code = getattr(e.response, "status_code", None) if getattr(e, "response", None) else None
            errs.append(f"{host}" + (f" HTTP {code}" if code else f" {type(e).__name__}"))
    raise CivitaiError(tr("访问 Civitai 失败：") + "；".join(errs))


def api_json(path: str, timeout: float = 20.0) -> dict:
    """请求 /api/v1/{path}，返回 JSON。"""
    text = request_path("api/v1/" + path, timeout)
    try:
        return json.loads(text)
    except Exception:
        raise CivitaiError(tr("Civitai 返回了无法解析的数据"))


# ---------------- meta 归一化 ----------------
def _find(meta: dict, *keys, default=None):
    for k in keys:
        if k in meta:
            return meta[k]
    return default


def _to_int(v):
    """安全转 int：ComfyUI 工作流 meta 中 width/height 可能是嵌套 dict
    （如 {"_meta":..., "inputs":...}），无法直接转数字时返回 0。"""
    if v is None or isinstance(v, bool):
        return 0
    if isinstance(v, dict):
        for k in ("number", "value", "int", "width", "height"):
            val = v.get(k)
            if val is not None and not isinstance(val, (dict, list)):
                try:
                    return int(float(val))
                except (TypeError, ValueError):
                    continue
        return 0
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _to_str(v):
    """安全转 str：dict/list/bool 等复杂结构返回 ''，避免把
    {'_meta':...} 之类的对象变成垃圾字符串。"""
    if isinstance(v, (dict, list, bool)) or v is None:
        return ""
    try:
        return str(v)
    except Exception:
        return ""


def _parse_size(size):
    try:
        m = re.match(r"(\d+)\s*[xX×]\s*(\d+)", _to_str(size))
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    return None, None


def normalize_meta(meta: dict, model_name_hint: str = "", model_type_hint: str = "") -> dict:
    """把 Civitai meta（大小写不固定）整理成统一字段。"""
    meta = meta or {}
    out = {
        "positive": "",
        "negative": "",
        "model_name": model_name_hint or "",
        "model_type": model_type_hint or "其他",
        "loras": [],
        "sampler": "",
        "steps": "",
        "cfg": "",
        "seed": "",
        "width": 0,
        "height": 0,
        "resources": [],
    }

    out["positive"] = _to_str(_find(meta, "prompt", "positivePrompt", "PositivePrompt", "positive", "text", default="")).strip()
    out["negative"] = _to_str(_find(meta, "negativePrompt", "NegativePrompt", "negative", "negative_prompt", default="")).strip()
    out["sampler"] = _to_str(_find(meta, "sampler", "Sampler", default=""))
    out["steps"] = _to_str(_find(meta, "steps", "Steps", default=""))
    out["cfg"] = _to_str(_find(meta, "cfgScale", "CFGScale", "cfg", "scale", default=""))
    out["seed"] = _to_str(_find(meta, "seed", "Seed", default=""))

    w, h = _parse_size(_find(meta, "Size", "size", default=""))
    if not w:
        w = _to_int(_find(meta, "width", "Width", default=0))
        h = _to_int(_find(meta, "height", "Height", default=0))
    out["width"], out["height"] = w, h

    mn = _to_str(_find(meta, "Model", "model", "baseModel", "ModelName", default="")).strip()
    out["model_name"] = mn or (model_name_hint or "")

    res = _find(meta, "resources", "Resources", default=[])
    resources = []
    if isinstance(res, list):
        for item in res:
            if isinstance(item, dict):
                name = _to_str(item.get("name") or item.get("modelName") or item.get("hash")).strip()
                rtype = _to_str(item.get("type") or item.get("modelType") or "other").lower()
                resources.append({"name": name, "type": rtype, "hash": _to_str(item.get("hash"))})
    out["resources"] = resources

    loras = []
    for r in resources:
        if r["type"] in ("lora", "locon", "lycoris") and r["name"]:
            loras.append(r["name"])
    for m in re.finditer(r"<lora:([^:>]+)(?::([\d.]+))?>", out["positive"], re.I):
        name = m.group(1).strip()
        if name and name not in loras:
            loras.append(name)
    for k, v in meta.items():
        if re.search(r"lora", str(k), re.I) and isinstance(v, str) and v.strip():
            nm = v.strip().split(",")[0].strip()
            if nm and nm not in loras and not re.match(r"^[\d.]+$", nm):
                loras.append(nm)
    out["loras"] = loras

    if not out["model_type"] or out["model_type"] == "其他":
        for r in resources:
            if r["type"] in ("checkpoint", "checkpoints", "ckpt"):
                out["model_type"] = TYPE_LABEL.get(r["type"], "大模型")
                break
    return out


def build_record_from_civitai(info: dict, source_url: str) -> dict:
    """把图片信息（meta + 页面 resources + 基础字段）整理成记录字段。

    关键新增：
    - models[]：图片使用的全部模型（name/type/url/base_model），url 指向 Civitai 模型页
    - base_model / base_model_raw：主模型大类（如 Krea 2、Flux.1）与其原始 baseModel
    """
    meta = info.get("meta") or {}
    hint = str(info.get("model_type") or "")
    norm = normalize_meta(meta, model_name_hint=info.get("model_name", ""),
                          model_type_hint=hint)

    w = _to_int(info.get("width")) or norm["width"]
    h = _to_int(info.get("height")) or norm["height"]
    if not w and norm["width"]:
        w, h = norm["width"], norm["height"]

    model_type = norm["model_type"]
    if not model_type or model_type == "其他":
        raw = str(meta.get("ModelType") or "").lower()
        if raw in TYPE_LABEL:
            model_type = TYPE_LABEL[raw]

    # ---- 模型清单：优先页面 resources（含 modelId），兜底用 meta 信息 ----
    resources = info.get("resources") or []
    models = []
    seen_names = set()
    for r in resources:
        if not isinstance(r, dict):
            continue
        name = _to_str(r.get("modelName") or r.get("name")).strip()
        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        mid = _to_int(r.get("modelId"))
        mtype = model_type_label(r.get("modelType") or r.get("type"))
        bm_raw = _to_str(r.get("baseModel")).strip()
        models.append({
            "name": name,
            "type": mtype,
            "url": f"https://civitai.com/models/{mid}" if mid else "",
            "base_model": bm_raw,
        })
    if not models and norm["model_name"]:
        models.append({"name": norm["model_name"], "type": model_type,
                       "url": "", "base_model": ""})

    # ---- 主模型大类：主模型(大模型)的 baseModel 优先，其次第一个模型 ----
    base_raw = ""
    for m in models:
        if m["type"] == "大模型" and m["base_model"]:
            base_raw = m["base_model"]
            break
    if not base_raw and models:
        base_raw = models[0]["base_model"]
    base_group = base_model_group(base_raw)

    # ---- LoRA 汇总：模型清单中的 LoRA + 提示词中的 <lora:...> ----
    loras = list(norm["loras"])
    for m in models:
        if m["type"] == "LoRA" and m["name"] and m["name"] not in loras:
            loras.append(m["name"])

    return {
        "title": _to_str(meta.get("Title") or meta.get("title") or info.get("title")).strip(),
        "tags": [],
        "positive": norm["positive"],
        "negative": norm["negative"],
        "base_model": base_group,
        "base_model_raw": base_raw,
        "models": models,
        "loras": loras,
        "sampler": norm["sampler"],
        "steps": norm["steps"],
        "cfg": norm["cfg"],
        "seed": norm["seed"],
        "width": int(w or 0),
        "height": int(h or 0),
        "source": "civitai",
        "source_url": source_url,
        "image_url": info.get("url", ""),
        "civitai_id": info.get("id"),
    }


# ---------------- 图片链接：解析网页内嵌数据 ----------------
def _extract_og_image(html: str) -> str:
    for pat in (
        r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"',
        r'<meta[^>]+content="([^"]+)"[^>]+property="og:image"',
    ):
        m = re.search(pat, html, re.I)
        if m:
            url = html_mod.unescape(m.group(1)).strip()
            if url and not url.endswith("/api/og"):
                return url
    return ""


def _widen_image_url(url: str, width: int = 0) -> str:
    """把 CDN 缩略尺寸（如 width=450）改成适合保存原图的大尺寸。"""
    if "image.civitai" not in url:
        return url
    target = max(int(width or 0), 1536)
    if target > 2048:
        target = 2048
    url = re.sub(r"width=\d+", f"width={target}", url)
    url = re.sub(r"quality=\d+", "quality=90", url)
    return url


def parse_image_page(html: str, img_id: int) -> dict:
    """从单图/视频页面提取 {meta, resources, width, height, url, title, media_type, video_url}。

    resources 为 Civitai 服务端生成的完整模型清单（含 modelId/modelName/modelType/
    baseModel），是主模型大类与模型超链接的权威来源（与 meta 是否公开无关）。
    支持视频页面：识别 type=video 对象，media_type=video，video_url 为视频文件地址。
    """
    result = {"meta": None, "resources": [], "width": 0, "height": 0,
              "url": "", "title": "", "media_type": "image", "video_url": ""}
    m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        return result
    try:
        data = json.loads(m.group(1))
    except Exception:
        return result

    meta_obj = None
    img_obj = None
    vid_obj = None
    resources = []

    def walk(o):
        nonlocal meta_obj, img_obj, vid_obj, resources
        if isinstance(o, dict):
            otype = o.get("type")
            oid = str(o.get("id"))
            if otype == "image":
                if img_obj is None and oid == str(img_id):
                    img_obj = o
                # resources 可能存在于 id 为 None 的详情变体中，
                # 单独按“含 modelId 的 resources”判断，并校验 imageId 归属
                if (not resources and isinstance(o.get("resources"), list)
                        and o.get("resources")
                        and isinstance(o["resources"][0], dict)
                        and "modelId" in o["resources"][0]):
                    rid = o["resources"][0].get("imageId")
                    if rid is None or str(rid) == str(img_id):
                        resources = o["resources"]
            elif otype == "video":
                if vid_obj is None and oid == str(img_id):
                    vid_obj = o
                # 视频对象也可能携带 resources（模型清单）
                if (not resources and isinstance(o.get("resources"), list)
                        and o.get("resources")
                        and isinstance(o["resources"][0], dict)
                        and "modelId" in o["resources"][0]):
                    resources = o["resources"]
            if meta_obj is None and isinstance(o.get("meta"), dict) and "prompt" in o.get("meta", {}):
                meta_obj = o["meta"]
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    if vid_obj:
        # 视频页面：media_type=video，width/height/title 来自视频对象
        result["media_type"] = "video"
        result["width"] = vid_obj.get("width") or 0
        result["height"] = vid_obj.get("height") or 0
        result["title"] = vid_obj.get("name") or ""
        result["video_url"] = _extract_video_url(html, vid_obj)
        # 视频页优先尝试封面图（无封面则留空，由导入端用首帧生成缩略图）
        result["url"] = _extract_real_image_url(html, None)
        if not result["url"] and img_obj:
            result["url"] = _extract_real_image_url(html, img_obj)
    if img_obj:
        result["width"] = result["width"] or (img_obj.get("width") or 0)
        result["height"] = result["height"] or (img_obj.get("height") or 0)
        result["title"] = result["title"] or (img_obj.get("name") or "")
    if meta_obj:
        result["meta"] = meta_obj
    result["resources"] = resources
    if not result["url"]:
        result["url"] = _extract_real_image_url(html, img_obj)
    return result


_VIDEO_EXTS = (".mp4", ".webm", ".mov", ".m4v", ".mkv", ".avi")


def _extract_video_url(html: str, vid_obj: dict) -> str:
    """从视频对象或页面 HTML 提取视频文件地址（mp4/webm/mov 等）。"""
    # 1. 对象 url 字段若是完整 http 地址
    u = (vid_obj or {}).get("url") or ""
    if isinstance(u, str) and u.startswith("http"):
        if u.lower().endswith(_VIDEO_EXTS) or "video" in u.lower():
            return u.split("\\")[0]
    # 2. 页面 HTML 中查找视频文件地址
    norm = html.replace("\\/", "/")
    for pat in (r"https://video\.civitai\.[^\"\s<]+",
                r"https://image\.civitai\.(?:com|red)/[^\"\s<]+\.(?:mp4|webm|mov|m4v|mkv|avi)[^\"\s<]*"):
        ms = re.findall(pat, norm)
        for murl in ms:
            if "/api/og" in murl:
                continue
            return murl.split("\\")[0]
    return ""


def _extract_real_image_url(html: str, img_obj: dict) -> str:
    """从页面提取真实的 CDN 原图地址（优先 original 变体，避开 /api/og 占位图）。"""
    # JSON 中斜杠被转义，先统一还原再匹配
    norm = html.replace("\\/", "/")
    guid = ""
    if img_obj:
        u = img_obj.get("url") or ""
        if "image.civitai" not in u:
            guid = u  # 页面里 url 字段通常是文件 GUID
    cdn_pat = r"https://image\.civitai\.(?:com|red)/[^\"\s<]+"
    candidates = re.findall(cdn_pat, norm)
    if not candidates:
        return ""
    # 排除视频文件地址（mp4/webm 等属于视频，不应作为图片返回）
    candidates = [u for u in candidates
                  if not u.lower().split("?")[0].endswith(_VIDEO_EXTS)]
    if not candidates:
        return ""
    if guid:
        for pref in ("original=true", "width=", ""):
            for u in candidates:
                if guid in u and (pref == "" or pref in u):
                    return _widen_image_url(u.split("\\")[0], img_obj.get("width") or 0)
    # 没有 guid 时：取最大的 width 变体
    best, best_w = "", -1
    for u in candidates:
        if "/api/og" in u:
            continue
        m = re.search(r"width=(\d+)", u)
        w = int(m.group(1)) if m else 99999 if "original" in u else -1
        if w > best_w:
            best, best_w = u, w
    if best:
        return _widen_image_url(best.split("\\")[0], 0)
    return ""


def _widen_image_url(url: str, width: int = 0) -> str:
    """把 CDN 缩略尺寸（如 width=450）改成适合保存原图的大尺寸。"""
    if "image.civitai" not in url:
        return url
    target = max(int(width or 0), 1536)
    if target > 2048:
        target = 2048
    url = re.sub(r"width=\d+", f"width={target}", url)
    url = re.sub(r"quality=\d+", "quality=90", url)
    return url


def fetch_image(id: int, timeout: float = 18.0, max_attempts: int = 2) -> dict:
    """按图片 ID 提取信息。

    Civitai 对中国区等受限区域会间歇性返回“SFW 门控”页面（meta 中 prompt 等字段
    被置空）。因此采用多轮多域名重试：优先返回含完整提示词的解析结果，轮次耗尽
    才退回降级结果（仅图片+模型名）。默认 2 轮 × 2 域名，最坏情况 ~80s 触发看门狗。
    """
    errs = []
    best = None
    for attempt in range(max_attempts):
        for host in HOSTS:
            try:
                html = _get(host, f"images/{id}", timeout).text
                parsed = parse_image_page(html, id)
                if parsed["meta"] or parsed["url"] or parsed["width"] or parsed["resources"]:
                    rec = build_record_from_civitai(
                        {"meta": parsed["meta"], "url": parsed["url"],
                         "width": parsed["width"], "height": parsed["height"],
                         "title": parsed["title"], "id": id,
                         "resources": parsed["resources"]},
                        f"https://civitai.com/images/{id}")
                    # 视频页：透传 media_type / video_url
                    rec["media_type"] = parsed["media_type"] or "image"
                    rec["video_url"] = parsed["video_url"] or ""
                    meta = parsed["meta"] or {}
                    if (parsed["media_type"] == "video"
                            and (rec["video_url"] or parsed["url"] or meta.get("prompt"))):
                        return rec  # 视频：只要有视频地址或提示词即可返回
                    if meta.get("prompt") or meta.get("negativePrompt") or meta.get("sampler") or meta.get("steps"):
                        return rec  # 完整 meta，直接返回
                    if best is None:
                        best = rec  # 降级结果暂存
                else:
                    errs.append(f"{host}{tr(': 页面未包含该图片数据')}")
            except Exception as e:  # noqa: BLE001
                code = getattr(e.response, "status_code", None) if getattr(e, "response", None) else None
                errs.append(f"{host}" + (f" HTTP {code}" if code else f" {type(e).__name__}"))
        if best is not None:
            time.sleep(0.35)  # 下一轮争取完整 meta
    if best is not None:
        return best
    raise CivitaiError(tr("读取 Civitai 图片信息失败：") + "；".join(errs) if errs else tr("读取 Civitai 图片信息失败"))


# ---------------- 模型 / 版本链接：官方 API ----------------
def fetch_model(id: int, timeout: float = 20.0) -> dict:
    data = api_json(f"models/{id}", timeout)
    versions = data.get("modelVersions") or []
    version = None
    for v in versions:
        if v.get("images"):
            version = v
            break
    if version is None and versions:
        version = versions[0]
    return _build_from_version(data, version, f"https://civitai.com/models/{id}")


def fetch_model_version(id: int, timeout: float = 20.0) -> dict:
    data = api_json(f"model-versions/{id}", timeout)
    return _build_from_version(data.get("model") or {}, data, f"https://civitai.com/api/v1/model-versions/{id}")


def _build_from_version(model_info: dict, version: dict, source_url: str) -> dict:
    images = (version or {}).get("images") or []
    img = images[0] if images else {}
    meta = img.get("meta") or {}
    model_name = model_info.get("name") or ""
    if not model_name:
        for m in model_info.get("modelVersions") or []:
            model_name = m.get("name") or model_name
    model_type = ""
    if isinstance(model_info.get("type"), str):
        model_type = TYPE_LABEL.get(model_info["type"].lower(), "")
    # 模型链接：优先版本对象里的 modelId（模型/版本 API 自带）
    mid = _to_int((version or {}).get("modelId"))
    bm_raw = _to_str((version or {}).get("baseModel")).strip()
    models = [{
        "name": model_name,
        "type": model_type or "大模型",
        "url": f"https://civitai.com/models/{mid}" if mid else "",
        "base_model": bm_raw,
    }]
    base = build_record_from_civitai(
        {"meta": meta, "url": img.get("url", ""), "width": img.get("width"),
         "height": img.get("height"),
         "model_name": model_name, "model_type": model_type,
         "id": img.get("id"), "resources": []}, source_url)
    base["models"] = models
    base["base_model_raw"] = bm_raw
    base["base_model"] = base_model_group(bm_raw)
    base["title"] = model_info.get("name") or base["title"]
    return base


# ---------------- 图片下载（image 域名容错） ----------------
def swap_image_host(url: str) -> str:
    return (url.replace("image.civitai.com", "image.civitai.red")
            .replace("image.civitai.red", "image.civitai.com"))


def download_image(url: str, dest: str, timeout: float = 30.0) -> tuple:
    """下载图片到 dest，返回 (ok, message)。先原地址，失败切换 image 域名重试。"""
    candidates = [url] if url else []
    swapped = swap_image_host(url)
    if swapped != url and swapped not in candidates:
        candidates.append(swapped)
    last_err = tr("无图片地址")
    for u in candidates:
        try:
            with requests.get(u, headers=UA, timeout=timeout, stream=True) as r:
                ctype = (r.headers.get("content-type") or "").lower()
                # 允许 image/* 与通用二进制（部分 CDN 返回 application/octet-stream）
                if r.status_code == 200 and (ctype.startswith("image") or ctype in (
                        "application/octet-stream", "application/binary", "")):
                    with open(dest, "wb") as f:
                        for chunk in r.iter_content(65536):
                            f.write(chunk)
                    # 完整性校验：非空 + 可解码为图片
                    if Path(dest).stat().st_size > 0 and _is_valid_image(dest):
                        return True, ""
                    last_err = tr("下载内容不是有效图片")
                    try:
                        Path(dest).unlink()
                    except Exception:
                        pass
                    continue
                last_err = f"HTTP {r.status_code}"
        except Exception as e:  # noqa: BLE001
            last_err = type(e).__name__
    return False, last_err


def _is_valid_image(path) -> bool:
    """校验文件可被解码为图片（避免下载到错误页/半截数据）。"""
    try:
        from PySide6.QtGui import QImage
        img = QImage(path)
        return not img.isNull()
    except Exception:
        return False


def download_video(url: str, dest: str, timeout: float = 60.0) -> tuple:
    """下载视频到 dest，返回 (ok, message)。先原地址，失败切换域名重试。"""
    candidates = [url] if url else []
    swapped = url.replace("video.civitai.com", "video.civitai.red") \
                 .replace("video.civitai.red", "video.civitai.com")
    if swapped != url and swapped not in candidates:
        candidates.append(swapped)
    last_err = tr("无视频地址")
    for u in candidates:
        try:
            with requests.get(u, headers=UA, timeout=timeout, stream=True) as r:
                ctype = (r.headers.get("content-type") or "").lower()
                is_video_ct = (ctype.startswith("video")
                               or ctype in ("application/octet-stream",
                                            "application/binary", ""))
                looks_video = Path(dest).suffix.lower() in (
                    ".mp4", ".webm", ".mov", ".m4v", ".mkv", ".avi")
                if r.status_code == 200 and is_video_ct and not (
                        "text/html" in ctype or "text/plain" in ctype):
                    with open(dest, "wb") as f:
                        for chunk in r.iter_content(65536):
                            f.write(chunk)
                    # 完整性：非空 + 头部字节数合理（视频文件通常 > 8KB）
                    size = Path(dest).stat().st_size
                    if size > 8192 or looks_video and size > 0:
                        return True, ""
                    last_err = tr_format("视频内容异常（{size} 字节）", size=size)
                    try:
                        Path(dest).unlink()
                    except Exception:
                        pass
                    continue
                last_err = f"HTTP {r.status_code} ({ctype})"
        except Exception as e:  # noqa: BLE001
            last_err = type(e).__name__
    return False, last_err
