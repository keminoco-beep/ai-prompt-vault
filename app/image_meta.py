"""图片内嵌元数据提取：解析 PNG tEXt/zTXt/iTXt 中的生成参数。

支持：
- A1111 / SD WebUI 的 "parameters"（正负提示词 + Steps/Sampler/CFG/Seed/Model/Size）
- NovelAI 的 "Comment"（base64 编码的 JSON）
- ComfyUI 的 "prompt" / "workflow"（JSON 工作流，提取 CLIPTextEncode 与模型/LoRA）
全部使用标准库实现（struct/zlib/base64/json/re），无第三方依赖。
"""
import base64
import json
import re
import struct
import zlib
from pathlib import Path

PNG_SIG = b"\x89PNG\r\n\x1a\n"


def png_text_chunks(path) -> dict:
    """解析 PNG 文件的所有 tEXt/zTXt/iTXt 文本块，返回 {关键字: 内容}。"""
    try:
        data = Path(path).read_bytes()
    except Exception:
        return {}
    if data[:8] != PNG_SIG:
        return {}
    out = {}
    pos = 8
    n = len(data)
    while pos + 12 <= n:
        try:
            length = struct.unpack(">I", data[pos:pos + 4])[0]
            ctype = data[pos + 4:pos + 8].decode("latin1")
            chunk = data[pos + 8:pos + 8 + length]
            if ctype == "tEXt":
                key, _, val = chunk.partition(b"\x00")
                out[key.decode("latin1")] = val.decode("utf-8", "replace")
            elif ctype == "zTXt":
                key, rest = chunk.split(b"\x00", 1)
                out[key.decode("latin1")] = zlib.decompress(rest[1:]).decode("utf-8", "replace")
            elif ctype == "iTXt":
                parts = chunk.split(b"\x00", 4)
                if len(parts) == 5:
                    key, flag, _meth, _lang, rest = parts
                    text = zlib.decompress(rest) if flag == b"\x01" else rest
                    out[key.decode("latin1")] = text.decode("utf-8", "replace")
            pos += 12 + length
            if ctype == "IEND":
                break
        except Exception:
            pos += 12 + length
    return out


def _parse_a1111(text: str) -> dict:
    """解析 SD WebUI 的 parameters 文本。"""
    out = {}
    lines = (text or "").split("\n")
    pos_lines, neg_lines = [], []
    in_neg = False
    meta_line = ""
    for ln in lines:
        if ln.startswith("Negative prompt:"):
            in_neg = True
            neg_lines.append(ln[len("Negative prompt:"):].strip())
        elif in_neg:
            if re.search(r"\b(Steps|Sampler|CFG scale|Seed|Size|Model|Clip skip"
                         r"|Denoising strength|Hires upscale|ENSD)\b", ln):
                meta_line = ln
                break
            neg_lines.append(ln)
        else:
            pos_lines.append(ln)
    out["positive"] = "\n".join(pos_lines).strip()
    out["negative"] = "\n".join(neg_lines).strip()
    if meta_line:
        meta = {}
        for m in re.finditer(r"([A-Za-z][\w ]*?):\s*([^,]+)", meta_line):
            meta[m.group(1).strip().lower()] = m.group(2).strip()
        out["steps"] = meta.get("steps", "")
        out["sampler"] = meta.get("sampler", "")
        out["cfg"] = meta.get("cfg scale", "")
        out["seed"] = meta.get("seed", "")
        out["model_name"] = meta.get("model", "")
        sz = meta.get("size", "")
        m = re.match(r"(\d+)\s*[x×]\s*(\d+)", sz)
        if m:
            out["width"], out["height"] = int(m.group(1)), int(m.group(2))
    return out


def _parse_novelai(comment: str) -> dict:
    """解析 NovelAI 的 base64 Comment。"""
    try:
        raw = base64.b64decode(comment)
        data = json.loads(raw)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    out = {}
    out["positive"] = str(data.get("prompt", "") or "")
    out["negative"] = str(data.get("uc", "") or "")
    out["steps"] = str(data.get("sampling_steps", "") or "")
    out["sampler"] = str(data.get("sampler", "") or "")
    out["cfg"] = str(data.get("cfg_scale", "") or "")
    out["seed"] = str(data.get("seed", "") or "")
    w, h = data.get("width"), data.get("height")
    if isinstance(w, (int, float)) and isinstance(h, (int, float)):
        out["width"], out["height"] = int(w), int(h)
    return out


def _parse_comfyui(prompt_json: str) -> dict:
    """从 ComfyUI 工作流 JSON 提取正向/负向/模型/LoRA。"""
    try:
        data = json.loads(prompt_json)
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    pos = neg = model = ""
    loras = []
    clip_texts = []
    for _nid, node in data.items():
        if not isinstance(node, dict):
            continue
        ct = str(node.get("class_type", "") or "")
        inputs = node.get("inputs")
        if not isinstance(inputs, dict):
            continue
        if "CLIPTextEncode" in ct:
            text = str(inputs.get("text", "") or "")
            if "negative" in ct.lower() or text.startswith("(("):
                neg = neg or text
            else:
                clip_texts.append(text)
        elif "CheckpointLoader" in ct:
            model = model or str(inputs.get("ckpt_name", "") or "")
        elif "UNETLoader" in ct:
            model = model or str(inputs.get("unet_name", "") or "")
        elif "LoraLoader" in ct:
            name = str(inputs.get("lora_name", "") or "")
            if name:
                loras.append(name)
    # 标准工作流通常正向节点在前、负向节点在后
    pos = pos or (clip_texts[0] if clip_texts else "")
    if not neg and len(clip_texts) > 1:
        neg = clip_texts[1]
    out = {}
    if pos:
        out["positive"] = pos
    if neg:
        out["negative"] = neg
    if model:
        out["model_name"] = model
    if loras:
        out["loras"] = loras
    return out


def extract_image_meta(path) -> dict:
    """从图片文件提取生成参数（正负提示词/采样参数/模型等）。非 PNG 或无可识别数据返回 {}。"""
    chunks = png_text_chunks(path)
    if not chunks:
        return {}
    out = {}
    if chunks.get("parameters"):
        out.update(_parse_a1111(chunks["parameters"]))
    if chunks.get("Comment"):
        out.update(_parse_novelai(chunks["Comment"]))
    cprompt = chunks.get("prompt") or chunks.get("workflow") or ""
    if cprompt and not out.get("positive"):
        out.update(_parse_comfyui(cprompt))
    return out
