# 图片元数据解析测试
import base64
import json
import struct
import sys
import tempfile
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.image_meta import extract_image_meta

FAIL = []


def check(name, cond, detail=""):
    print(("  ✓ " if cond else "  ✗ ") + name + (f"  {detail}" if detail and not cond else ""))
    if not cond:
        FAIL.append(name)


def make_png(path, text_chunks):
    def chunk(ctype, data):
        return struct.pack(">I", len(data)) + ctype + data + struct.pack(">I", zlib.crc32(ctype + data) & 0xffffffff)
    ihdr = struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0)
    raw = b"".join(b"\x00" + bytes(64 * 3) for _ in range(64))
    idat = zlib.compress(raw)
    data = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat)
    for k, v in text_chunks.items():
        data += chunk(b"tEXt", k.encode() + b"\x00" + v.encode())
    data += chunk(b"IEND", b"")
    Path(path).write_bytes(data)


def main():
    td = Path(tempfile.mkdtemp())

    # A1111
    params = ("masterpiece, best quality, 1girl, city night\n"
              "Negative prompt: lowres, bad anatomy\n"
              "Steps: 28, Sampler: DPM++ 2M Karras, CFG scale: 7, Seed: 123456789, "
              "Size: 512x768, Model: dreamshaperXL_v21")
    make_png(td / "a1111.png", {"parameters": params})
    m = extract_image_meta(td / "a1111.png")
    check("A1111 正向", m.get("positive", "").startswith("masterpiece"))
    check("A1111 负向", m.get("negative") == "lowres, bad anatomy")
    check("A1111 参数", m.get("steps") == "28" and m.get("sampler") == "DPM++ 2M Karras")
    check("A1111 CFG/Seed", m.get("cfg") == "7" and m.get("seed") == "123456789")
    check("A1111 模型", m.get("model_name") == "dreamshaperXL_v21")
    check("A1111 尺寸", m.get("width") == 512 and m.get("height") == 768)

    # NovelAI
    nai = {"prompt": "1girl, masterpiece", "uc": "lowres", "sampling_steps": 28,
           "sampler": "k_euler", "cfg_scale": 5.0, "seed": 42, "width": 832, "height": 1216}
    make_png(td / "nai.png", {"Comment": base64.b64encode(json.dumps(nai).encode()).decode()})
    m2 = extract_image_meta(td / "nai.png")
    check("NovelAI 正向", m2.get("positive") == "1girl, masterpiece")
    check("NovelAI 负向", m2.get("negative") == "lowres")
    check("NovelAI 参数", m2.get("steps") == "28" and m2.get("sampler") == "k_euler")
    check("NovelAI 尺寸", m2.get("width") == 832 and m2.get("height") == 1216)

    # ComfyUI
    comfy = {
        "4": {"class_type": "CLIPTextEncode", "inputs": {"text": "masterpiece, cyberpunk"}},
        "5": {"class_type": "CLIPTextEncode", "inputs": {"text": "blurry"}},
        "6": {"class_type": "LoraLoader", "inputs": {"lora_name": "add_detail.safetensors"}},
        "7": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "flux1dev.safetensors"}},
    }
    make_png(td / "comfy.png", {"prompt": json.dumps(comfy)})
    m3 = extract_image_meta(td / "comfy.png")
    check("ComfyUI 正向", m3.get("positive") == "masterpiece, cyberpunk")
    check("ComfyUI 负向", m3.get("negative") == "blurry")
    check("ComfyUI 模型", m3.get("model_name") == "flux1dev.safetensors")
    check("ComfyUI LoRA", m3.get("loras") == ["add_detail.safetensors"])

    # 无元数据图片
    make_png(td / "plain.png", {})
    check("无元数据返回空", extract_image_meta(td / "plain.png") == {})

    print()
    if FAIL:
        print(f"失败 {len(FAIL)} 项：{FAIL}")
        sys.exit(1)
    print("图片元数据解析测试全部通过 ✓")
    sys.exit(0)


if __name__ == "__main__":
    main()
