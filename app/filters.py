"""筛选逻辑：主模型大类分类、图片比例分类、记录过滤、模型/LoRA 汇总。"""
from math import gcd

RATIOS = ["全部比例", "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3", "超宽", "超高", "其他"]


def record_model_names(rec: dict) -> list:
    """记录中的所有模型名（models[] + loras），用于搜索与展示。"""
    names = [m.get("name") for m in (rec.get("models") or []) if m.get("name")]
    for lo in (rec.get("loras") or []):
        if lo and lo not in names:
            names.append(lo)
    return names


def unique_tags(records: list) -> list:
    """记录中的所有标签（去重保序），用于标签筛选下拉。"""
    seen, out = set(), []
    for r in records:
        for t in (r.get("tags") or []):
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    return out


def ratio_bucket(w: int, h: int) -> str:
    if not w or not h:
        return "其他"
    r = w / h
    if abs(r - 1) < 0.03:
        return "1:1"
    if abs(r - 16 / 9) < 0.05:
        return "16:9"
    if abs(r - 9 / 16) < 0.05:
        return "9:16"
    if abs(r - 4 / 3) < 0.06:
        return "4:3"
    if abs(r - 3 / 4) < 0.06:
        return "3:4"
    if abs(r - 3 / 2) < 0.07:
        return "3:2"
    if abs(r - 2 / 3) < 0.07:
        return "2:3"
    if r > 2.1:
        return "超宽"
    if r < 1 / 2.1:
        return "超高"
    return "其他"


def ratio_text(w: int, h: int) -> str:
    if not w or not h:
        return "未知"
    g = gcd(w, h)
    return f"{w // g}:{h // g}"


def unique_loras(records: list) -> list:
    seen = {}
    for r in records:
        for lo in r.get("loras") or []:
            key = lo.strip().lower()
            if key and key not in seen:
                seen[key] = lo.strip()
    return sorted(seen.values(), key=str.lower)


def merge_loras(existing: list, positive_prompt: str) -> list:
    """合并已有的 LoRA 列表与提示词中的 <lora:...>，去重保序。"""
    import re
    out = []
    seen = set()

    def add(name):
        nm = name.strip()
        key = nm.lower()
        if nm and key not in seen:
            seen.add(key)
            out.append(nm)

    for lo in existing or []:
        add(str(lo))
    for m in re.finditer(r"<lora:([^:>]+)(?::([\d.]+))?>", positive_prompt or "", re.I):
        add(m.group(1))
    return out


def filter_records(records: list, base_model: str = "全部", ratio: str = "全部比例",
                   lora: str = "全部", source: str = "全部", search: str = "",
                   group: str = "全部", media_type: str = "全部",
                   tag: str = "全部", search_index=None) -> list:
    """筛选记录。

    base_model: 主模型大类（如 Krea 2 / Flux.1 / Flux.2 / SDXL …），对应记录 base_model。
    lora: 使用的 LoRA 名称（部分匹配）。
    search: 关键词搜索（标题/标签/提示词/模型名/主模型大类）。
    group: 手动分组（"全部"=不过滤，"未分组"=group 为空，其他=指定组名）。
    search_index: 可选 {record_id: 预计算小写 hay}（调用方 reload 时一次构建）。
        提供时搜索命中为 O(1) 子串判断，避免每次按键重复拼接 hay（实测 35ms/键）；
        缺省 None 回退原逻辑（逐条拼接），签名向后兼容。
    """
    out = []
    search = (search or "").strip().lower()
    base_all = base_model in ("全部", "全部类型")
    ratio_all = ratio in ("全部", "全部比例")
    lora_all = lora in ("全部",)
    source_all = source in ("全部", "全部来源")
    media_all = media_type in ("全部", "全部媒体", "")
    tag_all = tag in ("全部", "全部标签", "")
    for r in records:
        if not media_all and (r.get("media_type") or "image") != media_type:
            continue
        if not tag_all and tag not in (r.get("tags") or []):
            continue
        if not base_all and (r.get("base_model") or "其他") != base_model:
            continue
        if not ratio_all and ratio_bucket(r.get("width"), r.get("height")) != ratio:
            continue
        if not lora_all:
            if not any(lora.lower() in lo.lower() for lo in (r.get("loras") or [])):
                continue
        if not source_all:
            rs = r.get("source") or ""
            if source == "来自Civitai" and rs != "civitai":
                continue
            if source == "本地导入" and rs == "civitai":
                continue
        if group != "全部":
            rg = r.get("group") or ""
            if group == "未分组":
                if rg:
                    continue
            elif rg != group and not rg.startswith(group + "/"):
                continue
        if search:
            if search_index is not None:
                # O(1) 命中：直接查预计算索引；缺 id 兜底走原逻辑
                hay = search_index.get(r.get("id"))
                if hay is None:
                    hay = " ".join([
                        r.get("title") or "", ",".join(r.get("tags") or []),
                        r.get("positive") or "", r.get("negative") or "",
                        r.get("base_model") or "", r.get("base_model_raw") or "",
                        " ".join(record_model_names(r)),
                    ]).lower()
                if search not in hay:
                    continue
            else:
                hay = " ".join([
                    r.get("title") or "", ",".join(r.get("tags") or []),
                    r.get("positive") or "", r.get("negative") or "",
                    r.get("base_model") or "", r.get("base_model_raw") or "",
                    " ".join(record_model_names(r)),
                ]).lower()
                if search not in hay:
                    continue
        out.append(r)
    return out


def group_counts(records: list) -> dict:
    """统计每个分组（含未分组）的记录数。返回 {组名: 数量, "": 未分组数量}。"""
    counts = {"": 0}
    for r in records:
        g = r.get("group") or ""
        counts[g] = counts.get(g, 0) + 1
    return counts
