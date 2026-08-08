"""核心逻辑测试：链接解析、meta 归一化、筛选、数据存储（无需 Qt 窗口）。"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import civitai
from app.civitai import parse_link, normalize_meta, build_record_from_civitai
from app.filters import ratio_bucket, filter_records, unique_loras, merge_loras
from app.data_store import DataStore

FAIL = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {detail}")
        FAIL.append(name)


def test_parse_link():
    print("[链接解析] civitai.com / civitai.red 双域名兼容")
    cases = [
        ("https://civitai.com/images/2345678", ("image", 2345678)),
        ("https://civitai.com/image/123456", ("image", 123456)),
        ("https://civitai.red/images/345678", ("image", 345678)),
        ("https://civitai.red/image/456789?period=AllTime", ("image", 456789)),
        ("https://civitai.com/api/v1/images/567890", ("image", 567890)),
        ("https://civitai.com/models/123456", ("model", 123456)),
        ("https://civitai.red/models/654321", ("model", 654321)),
        ("https://civitai.com/api/v1/models/789012", ("model", 789012)),
        ("https://civitai.com/api/v1/model-versions/111213", ("model_version", 111213)),
        ("https://civitai.red/model-versions/141516", ("model_version", 141516)),
        ("随便一段文字 https://civitai.com/images/998877 混合", ("image", 998877)),
    ]
    for url, expect in cases:
        r = parse_link(url)
        kind, id_ = expect
        check(f"{url[:60]}", r and r["kind"] == kind and r["id"] == id_,
              f"got {r}")
    check("非链接文本", parse_link("你好世界") is None)
    check("普通网址", parse_link("https://example.com/a.png") is None)


def test_normalize():
    print("[meta 归一化]")
    meta = {
        "prompt": "masterpiece, girl, <lora:add_detail:0.8>, city night",
        "negativePrompt": "bad hands, lowres",
        "Model": "dreamshaperXL_v21",
        "sampler": "DPM++ 2M Karras",
        "steps": 28,
        "cfgScale": 7.0,
        "seed": 123456789,
        "Size": "1024x1024",
        "resources": [
            {"name": "dreamshaperXL_v21", "type": "Checkpoint"},
            {"name": "add_detail", "type": "lora"},
            {"name": "badhandv4", "type": "LoRA"},
        ],
    }
    n = normalize_meta(meta)
    check("正向", n["positive"].startswith("masterpiece"))
    check("负向", "lowres" in n["negative"])
    check("模型名", n["model_name"] == "dreamshaperXL_v21")
    check("尺寸", (n["width"], n["height"]) == (1024, 1024))
    check("采样器/步数/CFG/种子", n["sampler"] == "DPM++ 2M Karras" and n["steps"] == "28" and n["cfg"] == "7.0" and n["seed"] == "123456789")
    check("LoRA 收集(资源+提示词)", "add_detail" in n["loras"] and "badhandv4" in n["loras"])
    # 大小写不固定字段
    n2 = normalize_meta({"PositivePrompt": "a", "negative": "b", "model": "m1", "Size": "512 x 768"})
    check("大小写容错", n2["positive"] == "a" and n2["negative"] == "b" and n2["model_name"] == "m1")
    check("尺寸解析空格x", (n2["width"], n2["height"]) == (512, 768))

    # ComfyUI 工作流图：width/height 是嵌套 dict，steps 为 int（曾导致 TypeError 崩溃）
    comfy = {
        "prompt": "A fantasy warrior, painterly",
        "cfgScale": 1, "steps": 8, "sampler": "Euler", "seed": 393955335001901,
        "comfy": {"prompt": {"1": {"inputs": {}}}},
        "vaes": ["qwen_image_vae.safetensors"],
        "Model": "Flux\\krea2_turbo_fp8",
        "width": {"_meta": {"title": "Flux Resolution Calc"}, "inputs": {"megapixel": "1.5"}},
        "height": {"_meta": {"title": "Flux Resolution Calc"}, "inputs": {"megapixel": "1.5"}},
        "models": ["Flux\\krea2_turbo_fp8.safetensors"],
        "denoise": 1, "scheduler": "simple",
    }
    nc = normalize_meta(comfy)
    check("ComfyUI 不崩溃", True)
    check("ComfyUI 正向保留", nc["positive"] == "A fantasy warrior, painterly")
    check("ComfyUI 尺寸容错=0", (nc["width"], nc["height"]) == (0, 0))
    check("ComfyUI steps 转 str", nc["steps"] == "8")
    check("ComfyUI seed 大数", nc["seed"] == "393955335001901")
    check("ComfyUI 模型名", nc["model_name"] == "Flux\\krea2_turbo_fp8")
    rec = build_record_from_civitai(
        {"meta": comfy, "url": "https://image.civitai.com/x/1/original=true/1.jpeg",
         "width": 1024, "height": 1472, "id": 1}, "https://civitai.com/images/1")
    check("ComfyUI 顶层尺寸优先", (rec["width"], rec["height"]) == (1024, 1472))

    # 新模型字段：页面 resources → models[]/base_model/超链接
    rec2 = build_record_from_civitai({
        "meta": {"prompt": "p"}, "url": "u", "width": 1024, "height": 1024, "id": 2,
        "resources": [
            {"modelName": "Krea2 Turbo_FP8", "modelType": "Checkpoint", "modelId": 2723583,
             "baseModel": "Krea 2", "imageId": 2},
            {"modelName": "add_detail", "modelType": "LORA", "modelId": 999, "baseModel": "Krea 2"},
        ],
    }, "https://civitai.com/images/2")
    check("主模型大类 Krea 2", rec2["base_model"] == "Krea 2")
    check("主模型原始 baseModel", rec2["base_model_raw"] == "Krea 2")
    check("模型清单 2 个", len(rec2["models"]) == 2)
    check("主模型链接", rec2["models"][0]["url"] == "https://civitai.com/models/2723583")
    check("主模型类型 大模型", rec2["models"][0]["type"] == "大模型")
    check("LoRA 类型映射", rec2["models"][1]["type"] == "LoRA")
    check("LoRA 汇总含 add_detail", "add_detail" in rec2["loras"])

    # base_model_group 归并
    from app.civitai import base_model_group
    check("分组 Flux.1", base_model_group("Flux.1 Krea") == "Flux.1")
    check("分组 Flux.1 Dev", base_model_group("Flux.1 Dev") == "Flux.1")
    check("分组 Flux.2", base_model_group("Flux.2 D") == "Flux.2")
    check("分组 Krea 2", base_model_group("Krea 2") == "Krea 2")
    check("分组 SDXL", base_model_group("SDXL 1.0") == "SDXL")
    check("分组 Pony", base_model_group("Pony") == "Pony")
    check("分组 Illustrious", base_model_group("Illustrious") == "Illustrious")
    check("分组 NoobAI", base_model_group("NoobAI") == "NoobAI")
    check("分组 SD1.5", base_model_group("SD 1.5") == "SD 1.5")
    check("分组 SD3.5", base_model_group("SD 3.5 Large") == "SD 3.5")
    check("分组 未知", base_model_group("ZImageBase") == "其他")
    check("分组 空", base_model_group("") == "其他")


def test_filters():
    print("[筛选逻辑]")
    recs = [
        {"id": "1", "title": "夜景", "tags": ["城市"], "positive": "night city", "negative": "blur",
         "base_model": "Krea 2", "models": [
             {"name": "Krea2 Turbo", "type": "大模型", "url": "https://civitai.com/models/1", "base_model": "Krea 2"},
             {"name": "detail", "type": "LoRA", "url": "", "base_model": ""}],
         "loras": ["detail"], "width": 1024, "height": 1024, "source": "civitai"},
        {"id": "2", "title": "人像", "tags": ["肖像"], "positive": "portrait <lora:face:0.6>", "negative": "",
         "base_model": "Flux.1", "models": [
             {"name": "flux1dev", "type": "大模型", "url": "", "base_model": "Flux.1 Dev"},
             {"name": "face", "type": "LoRA", "url": "", "base_model": ""}],
         "loras": ["face"], "width": 768, "height": 512, "source": "local"},
        {"id": "3", "title": "竖图", "tags": [], "positive": "vertical", "negative": "",
         "base_model": "Flux.2", "models": [{"name": "flux2krea", "type": "大模型", "url": "", "base_model": "Flux.2 Krea"}],
         "loras": [], "width": 1080, "height": 1920, "source": "local"},
        {"id": "4", "title": "", "tags": [], "positive": "wide banner", "negative": "",
         "base_model": "其他", "models": [], "loras": [], "width": 2200, "height": 1000,
         "source": "civitai"},
    ]
    check("比例 1:1", ratio_bucket(1024, 1024) == "1:1")
    check("比例 16:9", ratio_bucket(1920, 1080) == "16:9")
    check("比例 9:16", ratio_bucket(1080, 1920) == "9:16")
    check("比例 3:2", ratio_bucket(1500, 1000) == "3:2")
    check("比例 超宽", ratio_bucket(2200, 1000) == "超宽")
    check("全部", len(filter_records(recs)) == 4)
    check("按主模型大类 Krea 2", [r["id"] for r in filter_records(recs, base_model="Krea 2")] == ["1"])
    check("按主模型大类 Flux.1", [r["id"] for r in filter_records(recs, base_model="Flux.1")] == ["2"])
    check("按比例 1:1", [r["id"] for r in filter_records(recs, ratio="1:1")] == ["1"])
    check("按比例 9:16", [r["id"] for r in filter_records(recs, ratio="9:16")] == ["3"])
    check("按LoRA detail", [r["id"] for r in filter_records(recs, lora="detail")] == ["1"])
    check("按LoRA 部分匹配 face", [r["id"] for r in filter_records(recs, lora="face")] == ["2"])
    check("按来源 civitai", [r["id"] for r in filter_records(recs, source="来自Civitai")] == ["1", "4"])
    check("搜索 城市", [r["id"] for r in filter_records(recs, search="城市")] == ["1"])
    check("搜索 prompt 词", [r["id"] for r in filter_records(recs, search="portrait")] == ["2"])
    check("搜索 模型名", [r["id"] for r in filter_records(recs, search="flux2krea")] == ["3"])
    check("搜索 大类", [r["id"] for r in filter_records(recs, search="krea 2")] == ["1"])
    check("组合 大类+来源", [r["id"] for r in filter_records(recs, base_model="Krea 2", source="来自Civitai")] == ["1"])
    check("LoRA 汇总", unique_loras(recs) == ["detail", "face"])
    check("merge_loras 去重", merge_loras(["detail"], "a <lora:detail:0.5> <lora:new:1>") == ["detail", "new"])
    # 手动分组筛选
    recs[0]["group"] = "风景"
    recs[1]["group"] = ""
    check("分组筛选 风景", [r["id"] for r in filter_records(recs, group="风景")] == ["1"])
    check("分组筛选 未分组", [r["id"] for r in filter_records(recs, group="未分组")] == ["2", "3", "4"])
    check("分组筛选 全部不过滤", len(filter_records(recs, group="全部")) == 4)
    from app.filters import group_counts
    cnt = group_counts(recs)
    check("分组计数", cnt.get("风景") == 1 and cnt.get("") == 3)


def test_store():
    print("[数据存储]")
    with tempfile.TemporaryDirectory() as td:
        st = DataStore(Path(td) / "库")
        check("目录结构", (st.images_dir.exists() and st.thumbs_dir.exists()
                           and st.trash_dir.exists() and st.root.exists()))
        rec = st.add({"title": "测试", "positive": "p", "image_file": "img_a.png"})
        check("add 返回 id", bool(rec["id"]))
        st2 = DataStore(st.root)
        check("重载持久化", st2.records[0]["title"] == "测试")
        st.update(rec["id"], {"positive": "p2"})
        st3 = DataStore(st.root)
        check("update 持久化", st3.get(rec["id"])["positive"] == "p2")
        # 模拟图片文件
        (st.images_dir / "img_a.png").write_bytes(b"fake")
        st.remove(rec["id"])
        check("remove 移除记录", st.get(rec["id"]) is None)
        check("remove 移入回收站", (st.trash_dir / "img_a.png").exists())
        # v3.0：索引在 SQLite（library.db）；旧 data.json 不再生成
        check("索引文件存在(SQLite)", st._storage.db_path.exists())


if __name__ == "__main__":
    test_parse_link()
    test_normalize()
    test_filters()
    test_store()
    print()
    if FAIL:
        print(f"共 {len(FAIL)} 项失败：{FAIL}")
        sys.exit(1)
    print("全部核心测试通过 ✓")
