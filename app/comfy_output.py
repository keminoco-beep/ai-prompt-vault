"""ComfyUI 输出文件夹（output）扫描：生成「我的作品」虚拟记录。

v3.3 多目录改造：
- **多目录**：设置页直接填写 1 个或多个 output 文件夹绝对路径（comfy_output_dirs），
  不再自动拼接 comfyui_dir/output。
- **comfyui_dir 与图库解耦**：comfyui_dir 仅用于模型下载（download_manager / model_panel /
  app.comfy），configured_output_dirs 只读 comfy_output_dirs，**不再回退 comfyui_dir**，
  避免「ComfyUI 根目录」与「我的作品」输出文件夹重复导入（见 configured_output_dirs）。
- **按文件夹自动分组**：
  - 单个目录 → 根下图片归 `my_works`，子目录归 `my_works/<子目录>`（保持 v3.1 行为）
  - 多目录 → 每个目录一个顶层分组 `my_works/<目录名>`（目录名取 basename，
    重名时拼父级名或哈希后缀避免冲突），其下子目录 `my_works/<目录名>/<子目录>`
- **记录 id 目录唯一**：id 前缀带目录稳定哈希（sha1(绝对路径)[:8]），
  避免不同目录同相对路径互相冲突。
- **磁盘缓存带目录标识**：files/recs 的 key 为 `{目录哈希}/{相对路径}`，
  缓存文件记录 dirs 集合；目录集合变化时旧缓存整体失效（读不出就全量重扫一次，不报错）。

设计要点（沿用 v3.1）：
- **虚拟引用**：不复制文件进资料库（避免双倍占用硬盘），记录只保存绝对路径
- **双层缓存**：
  - 内存缓存：进程内（mtime, size）判断，未变化不重解析；key 为目录列表规范化 key
  - 磁盘缓存：Library/comfy_output_cache.json，**避免每次启动全量重扫**
    （实测真实 output 4000+ PNG 全量解析需 4 分钟，磁盘缓存让启动秒级）
- **异步扫描**：UI 层用后台线程首次扫描，启动不卡（见 main_window）
- 记录字段与 data_store.normalize_record 完全同构，可无缝进入图库/筛选/详情
"""
import hashlib
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

logger = logging.getLogger(__name__)

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
GROUP_ROOT = "my_works"   # 固定 key（不随语言翻译），显示时用 tr("我的作品")

# 内存缓存：{dirs_key: {"files": {dir_hash/rel: [mtime, size]}, "recs": {dir_hash/rel: rec}}}
_cache = {}
_CACHE_DIRTY = set()   # 兼容保留（历史上未使用，写盘由 scan 直接完成）

# 磁盘缓存 memo：{(cache_file, dirs_key): {"files": ..., "recs": ..., "groups": ..., "mtime": ...}}
# 目的：同一进程内 refresh_groups（load_cached_groups）与 GalleryPanel.reload
# （load_cached_records）各读一次 comfy_output_cache.json（实测 8.8MB）→ 二次解析
# 120ms+103ms。memo 命中直接返回，不再解析 JSON；mtime 校验防外部改写/删除。
_disk_memo = {}

# thumb_path_for_rec 结果缓存：{uid: Path}（避免每个 tile 都做 sha1 + mkdir）
_thumb_path_cache = {}


def _memo_key(cache_file, dirs_key):
    return (str(cache_file), dirs_key)


def clear_memos():
    """清空磁盘缓存 memo 与缩略图路径缓存（目录集合变化/磁盘缓存被删时调用）。"""
    _disk_memo.clear()
    _thumb_path_cache.clear()


# ---------------- 目录解析与规范化 ----------------

def _resolve_output_dir(d) -> str:
    """把用户填写的路径解析为实际 output 文件夹绝对路径。

    只把路径本身当作 output 文件夹（不再把「含 output 子目录的 ComfyUI 根目录」
    自动落到 output——comfyui_dir 与图库输出目录已解耦，避免重复导入）。
    目录不存在返回 ""。
    """
    if not d:
        return ""
    p = Path(str(d)).expanduser()
    if not p.is_dir():
        return ""
    return str(p.resolve())


def normalize_output_dirs(dirs) -> list:
    """把任意输入（单个字符串 / Path / 列表）规范化为去重排序的输出目录列表。

    每个条目都被当作 output 文件夹本身（不再支持"传 comfyui_dir 根目录自动落到
    output 子目录"的旧兼容——comfyui_dir 与图库输出目录已解耦）。
    """
    if isinstance(dirs, (str, Path)):
        dirs = [dirs]
    out, seen = [], set()
    for d in (dirs or []):
        r = _resolve_output_dir(d)
        if r and r not in seen:
            seen.add(r)
            out.append(r)
    out.sort()
    return out


def configured_output_dirs(store) -> list:
    """从 store 读取当前输出目录配置（「我的作品」图库唯一配置入口）。

    - 只读新键 comfy_output_dirs（JSON 数组，output 文件夹绝对路径）；
    - 为空/未设置返回 []（**不再回退 comfyui_dir**，避免与模型下载根目录重复导入）；
    - comfyui_dir 仅用于模型下载（download_manager / model_panel / app.comfy），
      与「我的作品」图库完全解耦。
    """
    dirs = store.load_setting("comfy_output_dirs", None)
    if dirs is None or not dirs:
        return []
    return normalize_output_dirs(dirs)


def _dirs_key(dirs) -> str:
    """目录列表的规范化 key（排序后用分号连接），用于内存缓存与磁盘缓存校验。"""
    return ";".join(sorted(str(d) for d in (dirs or [])))


def _dir_hash(d) -> str:
    """单个目录的稳定哈希前缀（8 位）。"""
    return hashlib.sha1(str(d).encode("utf-8")).hexdigest()[:8]


def _dir_hashes(dirs) -> dict:
    """{目录: 哈希}；哈希碰撞时延长到 12 位兜底。"""
    out, used = {}, set()
    for d in dirs:
        h = _dir_hash(d)
        if h in used:
            h = hashlib.sha1(str(d).encode("utf-8")).hexdigest()[:12]
        used.add(h)
        out[d] = h
    return out


def _display_names(dirs) -> dict:
    """{目录: 显示名}，在 dirs 列表内保证唯一。

    默认用 basename；重名目录用「父目录名-basename」消歧，仍冲突则加哈希后缀。
    """
    names = {}
    by_base = {}
    for d in dirs:
        base = Path(d).name or Path(d).parent.name or "output"
        by_base.setdefault(base, []).append(d)
    for base, members in by_base.items():
        if len(members) == 1:
            names[members[0]] = base
    for base, members in by_base.items():
        if len(members) == 1:
            continue
        for d in members:
            parent = Path(d).parent.name
            cand = f"{parent}-{base}" if parent and parent != base else ""
            if not cand:
                cand = f"{base}-{_dir_hash(d)}"
            names[d] = cand
    # 最终唯一性兜底（极少数跨组名巧合冲突）
    seen = set()
    for d in dirs:
        n = names[d]
        if n in seen:
            names[d] = f"{Path(d).name}-{_dir_hash(d)}"
        seen.add(names[d])
    return names


def _group_prefix_for(dirs, d, display_names=None) -> str:
    """目录 d 在 dirs 列表中的「我的作品」分组前缀。

    单目录：根文件直接归 GROUP_ROOT（my_works）；
    多目录：每个目录归 my_works/<显示名>。
    """
    if len(dirs) <= 1:
        return GROUP_ROOT
    dn = (display_names or _display_names(dirs))[d]
    return f"{GROUP_ROOT}/{dn}"


# ---------------- 磁盘缓存 ----------------

def _load_disk_cache(cache_file, dirs_key=None):
    """从磁盘加载缓存（文件不存在/解析失败/目录集合不匹配返回空，绝不抛异常）。

    模块级 memo：同一进程内 refresh_groups 与 GalleryPanel.reload 各读一次
    comfy_output_cache.json（实测 8.8MB），命中 memo 直接返回不再解析 JSON。
    memo 带文件 mtime/size 校验：磁盘文件被外部改写/删除时自动失效重读。
    """
    try:
        mkey = _memo_key(cache_file, dirs_key)
        cached = _disk_memo.get(mkey)
        if cached is not None:
            try:
                st = Path(cache_file).stat()
                if cached.get("mtime") == (st.st_mtime_ns, st.st_size):
                    return cached["files"], cached["recs"]
            except OSError:
                _disk_memo.pop(mkey, None)
                return {}, {}
        data = json.loads(Path(cache_file).read_text(encoding="utf-8"))
        if dirs_key is not None and data.get("dirs") != dirs_key:
            return {}, {}
        files = {k: [float(v[0]), int(v[1])] for k, v in data.get("files", {}).items()}
        recs = {k: dict(v) for k, v in data.get("recs", {}).items()}
        try:
            st = Path(cache_file).stat()
            mtime = (st.st_mtime_ns, st.st_size)
        except OSError:
            mtime = None
        _disk_memo[mkey] = {"files": files, "recs": recs, "groups": None, "mtime": mtime}
        return files, recs
    except Exception:
        return {}, {}


def _save_disk_cache(cache_file, files, recs, dirs_key):
    if not cache_file:
        return
    try:
        payload = {
            "files": {k: v for k, v in files.items()},
            "recs": {k: v for k, v in recs.items()},
            "dirs": dirs_key,
            "saved_at": time.time(),
        }
        Path(cache_file).write_text(
            json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        # 同步 memo：后续 load_cached_records / load_cached_groups 直接命中新内容
        try:
            st = Path(cache_file).stat()
            mtime = (st.st_mtime_ns, st.st_size)
        except OSError:
            mtime = None
        _disk_memo[_memo_key(cache_file, dirs_key)] = {
            "files": files, "recs": recs, "groups": None, "mtime": mtime}
    except Exception:
        pass


def invalidate_stale_cache(cache_file, dirs) -> bool:
    """配置变化后删除与当前目录集合失配的磁盘缓存；匹配/文件缺失时不动。

    供 _on_output_dirs_changed 调用：配置已变，旧缓存（dirs 集合 != 新配置）必然
    失配——主动删除，避免 scan_output_images 白加载 9.5MB 旧数据再丢弃全量重扫。
    仅当缓存仍匹配当前配置时保留（信号误触发/测试直调时不误删有效缓存）。
    返回是否删除了文件。
    """
    if not cache_file:
        return False
    try:
        cf = Path(cache_file)
        dkey = _dirs_key(dirs)
        if not cf.exists():
            _disk_memo.pop(_memo_key(cf, dkey), None)
            return False
        files, recs = _load_disk_cache(cf, dkey)
        if files or recs:
            return False   # 缓存与当前配置匹配：有效，保留
        cf.unlink()
        _disk_memo.pop(_memo_key(cf, dkey), None)
        return True
    except Exception:
        return False


def load_cached_records(cache_file, dirs=None) -> list:
    """只读磁盘缓存返回虚拟记录列表（**不枚举目录**，启动秒级）。

    dirs 可选：传入当前目录列表时校验缓存与目录集合匹配，不匹配返回空（不抛异常）。
    供 UI 同步路径使用；目录变更由后台线程 scan_output_images 更新缓存后刷新。
    优先用已扫描驻留的模块级 _cache（scan_output_images 刚跑完），否则回退磁盘缓存
    （同样带 memo，同一进程内二次读不重新解析 JSON）。
    """
    if not cache_file:
        return []
    key = _dirs_key(dirs) if dirs is not None else None
    if key is not None and key in _cache:
        recs = _cache[key]["recs"]
    else:
        _files, recs = _load_disk_cache(cache_file, key)
    out = list(recs.values())
    out.sort(key=lambda r: r.get("_mtime", 0), reverse=True)
    return out


def load_cached_groups(cache_file, dirs=None) -> dict:
    """只读磁盘缓存返回 {group: count}（不枚举目录，启动秒级）。

    基于 load_cached_records 的同一份已解析 recs 计数（**不二次解析 JSON**）；
    group 计数按 (cache_file, dirs) memo 化，多次调用零开销。
    """
    if not cache_file:
        return {}
    key = _dirs_key(dirs) if dirs is not None else None
    mkey = _memo_key(cache_file, key)
    entry = _disk_memo.get(mkey)
    if entry is not None and entry.get("groups") is not None:
        return dict(entry["groups"])
    out = {}
    for r in load_cached_records(cache_file, dirs):
        g = r.get("group") or GROUP_ROOT
        out[g] = out.get(g, 0) + 1
    entry = _disk_memo.get(mkey)
    if entry is not None:
        entry["groups"] = out
    return out


# ---------------- 轻量分组统计 ----------------

def quick_group_counts(dirs) -> dict:
    """轻量分组统计：**只枚举文件不解析 PNG 元数据**（秒级）。

    用于无磁盘缓存时刷新分组树（首次启动/缓存缺失/目录变更），让「我的作品」
    分组立即可见；元数据由后台线程 scan_output_images 补全。
    分组规则与 _build_virtual_record 一致（多目录 → my_works/<目录名>）。
    """
    out = {}
    dirs = normalize_output_dirs(dirs)
    if not dirs:
        return out
    display_names = _display_names(dirs)
    for d in dirs:
        root = Path(d)
        if not root.is_dir():
            continue
        prefix = _group_prefix_for(dirs, d, display_names)
        try:
            for p in root.rglob("*"):
                if p.is_file() and p.suffix.lower() in IMAGE_EXTS and not p.name.endswith(".part"):
                    rel_parts = p.relative_to(root).parts
                    sub = "/".join(rel_parts[:-1]) if len(rel_parts) > 1 else ""
                    g = prefix if not sub else f"{prefix}/{sub}"
                    out[g] = out.get(g, 0) + 1
        except OSError:
            continue
    return out


# ---------------- 缩略图缓存 ----------------
# 虚拟记录不复制原图，但首屏渲染需要小缩略图：生成到 Library/comfy_output_thumbs/
# （JPEG 400px 内，单张 20~60KB），后台线程逐批生成，避免启动卡顿。
# 缩略图 key 用 {目录哈希}/{相对路径}，多目录同 rel 不互相覆盖。

def thumb_dir_for(store) -> Path:
    d = Path(store.root) / "comfy_output_thumbs"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass
    return d


def thumb_path(key: str, thumb_dir) -> Path:
    """输出目录相对 key（含目录标识）→ 缩略图缓存路径（JPEG）。"""
    h = hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]
    return Path(thumb_dir) / f"{h}.jpg"


def thumb_path_for_rec(store, rec) -> Path:
    """按虚拟记录反推其缩略图缓存路径（与 generate_all_thumbs 的 key 一致）。

    结果按 uid memo 化：避免每个 tile 渲染都做 sha1 + thumb_dir.mkdir（~ms 级
    磁盘 IO）。uid 对同一记录稳定，目录集合变化时 clear_memos() 一并清空。
    """
    uid = rec.get("id")
    if uid:
        cached = _thumb_path_cache.get(uid)
        if cached is not None:
            return cached
    dh = rec.get("_dir_hash") or ""
    rel_key = rec.get("_rel") or ""
    if not rel_key:
        # 旧缓存记录回退：从 virtual_path 反推（output 段之后为相对路径）
        vp = Path(rec.get("virtual_path") or "")
        parts = vp.parts
        try:
            idx = parts.index("output")
            rel_key = "/".join(parts[idx + 1:])
        except ValueError:
            rel_key = vp.name
    result = thumb_path(f"{dh}/{rel_key}" if dh else rel_key, thumb_dir_for(store))
    if uid:
        if len(_thumb_path_cache) > 4000:   # 防无限增长（上限远大于虚拟记录上限）
            _thumb_path_cache.clear()
        _thumb_path_cache[uid] = result
    return result


def fast_thumb(src_path: str, dst_path: str, max_side: int = 400) -> bool:
    """快速缩略图：QImageReader 只解码缩小的尺寸，不加载全图（大图提速数十倍）。

    失败返回 False 并记录 warning 日志（含真实异常，供排查损坏/不支持的图片），
    由调用方决定跳过还是兜底。
    """
    try:
        from PySide6.QtCore import QSize
        from PySide6.QtGui import QImageReader
        reader = QImageReader(src_path)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid() and (size.width() > max_side or size.height() > max_side):
            if size.width() >= size.height():
                reader.setScaledSize(QSize(max_side, max(1, int(size.height() * max_side / size.width()))))
            else:
                reader.setScaledSize(QSize(max(1, int(size.width() * max_side / size.height())), max_side))
        img = reader.read()
        if img.isNull():
            logger.warning("缩略图生成失败（无法解码，%s）：%s",
                           reader.errorString() or "unknown error", src_path)
            return False
        if not img.save(dst_path, "JPG", 85):
            logger.warning("缩略图保存失败：%s -> %s", src_path, dst_path)
            return False
        return True
    except Exception as e:
        logger.warning("缩略图生成异常：%s（%s）", src_path, e)
        return False


def generate_all_thumbs(dirs, thumb_dir, cancel_cb=None, batch_cb=None):
    """后台线程：为所有虚拟记录生成缺失的缩略图。

    batch_cb: callback(done, total) 每生成 batch 张回调一次（用于刷新 UI）。
    幂等：已有有效缩略图的记录直接跳过；失败的记录不生成缩略图文件，下次调用
    会自动重试（配合 main_window 的链式重启，增量新增文件保证最终被处理）。
    """
    recs = scan_output_images(dirs)   # 用内存/磁盘缓存快速拿记录
    total = len(recs)
    done = 0
    failed = 0
    missing_src = 0
    batch = 0
    try:
        Path(thumb_dir).mkdir(parents=True, exist_ok=True)   # QImage.save 不自动建目录
    except Exception:
        pass
    for r in recs:
        if cancel_cb and cancel_cb():
            return done
        abs_path = r.get("virtual_path")
        if not abs_path:
            continue
        dh = r.get("_dir_hash") or ""
        rel_key = r.get("_rel")
        if not rel_key:
            root = Path(r.get("_dir") or "")
            if not root.is_dir():
                continue
            try:
                rel_key = Path(abs_path).relative_to(root).as_posix()
            except Exception:
                continue
        key = f"{dh}/{rel_key}" if dh else rel_key
        tp = thumb_path(key, thumb_dir)
        if not tp.exists() or tp.stat().st_size < 100:
            if not Path(abs_path).is_file():
                # 记录存在但源文件已被删除/移动：跳过，不阻塞其他文件
                missing_src += 1
                continue
            if not fast_thumb(abs_path, str(tp)):
                failed += 1
                continue
        done += 1
        batch += 1
        if batch_cb and batch >= 60:
            batch_cb(done, total)
            batch = 0
    if batch_cb:
        batch_cb(done, total)
    if failed or missing_src:
        logger.warning("缩略图生成完成：成功 %s，失败 %s，源缺失 %s（共 %s）",
                       done, failed, missing_src, total)
    return done


# ---------------- 扫描 ----------------

def scan_output_images(dirs, cache_file=None, cancel_cb=None) -> list:
    """扫描多个 output 文件夹（递归）返回虚拟记录列表（新的在前）。

    dirs：输出目录列表（output 文件夹路径本身；不再支持传 comfyui_dir 根目录自动
    落到 output 子目录——comfyui_dir 与图库输出目录已解耦）。
    cache_file：磁盘缓存路径（通常 store.root/"comfy_output_cache.json"）。
    cancel_cb：callback() -> bool，返回 True 时中止扫描（用于关闭窗口时打断）。
    首次扫描（无磁盘缓存）可能较慢，UI 调用方应在后台线程执行。
    """
    dirs = normalize_output_dirs(dirs)
    if not dirs:
        return []
    key = _dirs_key(dirs)
    state = _cache.get(key)
    if state is None:
        files, recs = ({}, {})
        if cache_file:
            files, recs = _load_disk_cache(cache_file, key)
            if not files and not recs:
                # 缓存失效（dirs 集合不匹配 / 文件损坏 / 解析失败）：明确"缓存已失效"，
                # 先删除磁盘缓存文件——避免本次白加载旧数据再丢弃重扫，
                # 也避免下次启动再误读；后续 _save_disk_cache 全新写入。
                try:
                    Path(cache_file).unlink()
                except Exception:
                    pass
                _disk_memo.pop(_memo_key(cache_file, key), None)
        state = {"files": files, "recs": recs}
        _cache[key] = state

    hashes = _dir_hashes(dirs)
    display_names = _display_names(dirs)
    hash_to_dir = {h: d for d, h in hashes.items()}

    # 1. 枚举当前文件（key 带目录哈希，多目录同 rel 不冲突）
    current = {}
    for d in dirs:
        if cancel_cb and cancel_cb():
            return []
        dh = hashes[d]
        root = Path(d)
        if not root.is_dir():
            continue
        try:
            for p in root.rglob("*"):
                if cancel_cb and cancel_cb():
                    return []
                if p.is_file() and p.suffix.lower() in IMAGE_EXTS and not p.name.endswith(".part"):
                    rel = p.relative_to(root).as_posix()
                    try:
                        st = p.stat()
                    except OSError:
                        continue
                    current[f"{dh}/{rel}"] = [st.st_mtime, st.st_size]
        except OSError:
            continue

    # 2. 清理已删除文件
    changed = False
    for k in [k for k in state["files"] if k not in current]:
        state["files"].pop(k, None)
        state["recs"].pop(k, None)
        changed = True

    # 3. 增量解析新增/变化文件
    #    多线程并行（ThreadPoolExecutor ≤ 8）：读 PNG 尾部元数据是独立 IO/CPU 操作，
    #    线程安全；实测真实 output 4877 图全量解析 255s → ~40s。
    #    并行只算 rec 列表（_build_records_parallel），合并进 state 回到本线程完成，
    #    避免共享可变状态；结果顺序无关（第 5 步统一按 mtime 排序）。
    tasks = []
    for k, (mtime, size) in current.items():
        if cancel_cb and cancel_cb():
            return []
        prev = state["files"].get(k)
        if prev == [mtime, size] and k in state["recs"]:
            continue
        dh, rel = k.split("/", 1)
        d = hash_to_dir.get(dh)
        if d is None:
            continue
        tasks.append((k, d, rel, mtime, size))

    if tasks:
        parsed = _build_records_parallel(tasks, dirs, display_names, cancel_cb)
        for k, _d, _rel, mtime, size in tasks:
            if k in parsed:
                state["recs"][k] = parsed[k]
                state["files"][k] = [mtime, size]
                changed = True

    # 4. 有变化则写回磁盘缓存
    if changed and cache_file:
        _save_disk_cache(cache_file, state["files"], state["recs"], key)

    # 5. 按 mtime 倒序（新图在前）
    recs = list(state["recs"].values())
    recs.sort(key=lambda r: r.get("_mtime", 0), reverse=True)
    return recs


def _file_snapshot(dirs) -> dict:
    """只枚举输出目录树中所有图片文件的 (mtime, size)，不读文件内容。

    v3.9：增量扫描的目录快照——仅 os.scandir 目录项读取（不解析 PNG 元数据、
    不读文件体），4877 图目录树枚举 <1s，远轻于全量解析（~40s）。
    key 为 {目录哈希}/{相对路径}（与 scan_output_images / 磁盘缓存一致）。
    """
    dirs = normalize_output_dirs(dirs)
    if not dirs:
        return {}
    hashes = _dir_hashes(dirs)
    out = {}
    for d in dirs:
        dh = hashes[d]
        root = Path(d)
        if not root.is_dir():
            continue
        try:
            stack = [root]
            while stack:
                cur = stack.pop()
                with os.scandir(cur) as it:
                    for e in it:
                        try:
                            if e.is_dir(follow_symlinks=False):
                                stack.append(Path(e.path))
                            elif e.is_file(follow_symlinks=False):
                                name = e.name
                                if name.lower().endswith(tuple(IMAGE_EXTS)) \
                                        and not name.endswith(".part"):
                                    rel = Path(e.path).relative_to(root).as_posix()
                                    st = e.stat()
                                    out[f"{dh}/{rel}"] = [st.st_mtime, st.st_size]
                        except OSError:
                            continue
        except OSError:
            continue
    return out


def scan_output_images_delta(dirs, cache_file=None, cancel_cb=None) -> dict:
    """增量扫描输出文件夹：只解析新增/变化文件，不重扫已有（省磁盘读写、0 卡顿）。

    v3.9：定时监听用——对比磁盘缓存（files+recs）与当前目录快照 diff：
    - 新增（快照有、缓存无）→ 后台并行解析元数据（复用 _build_records_parallel，
      只处理新增文件，避免重复解析已有文件）
    - 删除/移动（快照无、缓存有）→ 从缓存移除
    - mtime/size 变化 → 重新解析该文件
    仅当有变化才写回磁盘缓存；无变化返回空结果不写盘（真正 0 开销）。
    无磁盘缓存/缓存失配 → 退化为全量 scan_output_images 并返回其结果。

    返回 {"added": n, "removed": n, "changed": n, "records": [...]}；
    records 为本次新增/变化的记录列表（供调用方 reload）。
    """
    dirs = normalize_output_dirs(dirs)
    if not dirs:
        return {"added": 0, "removed": 0, "changed": 0, "records": []}
    key = _dirs_key(dirs)
    # 读磁盘缓存作为已知集（以磁盘为准，与内存缓存解耦；写回时同步内存缓存）
    files, recs = ({}, {})
    if cache_file:
        files, recs = _load_disk_cache(cache_file, key)
    if not files and not recs:
        # 无缓存/缓存失配：退化为全量扫描（行为与 scan_output_images 一致）
        full = scan_output_images(dirs, cache_file, cancel_cb)
        return {"added": len(full), "removed": 0, "changed": 0,
                "records": full, "full": True}

    current = _file_snapshot(dirs)
    hashes = _dir_hashes(dirs)
    display_names = _display_names(dirs)
    hash_to_dir = {h: d for d, h in hashes.items()}

    # 1. diff：新增（快照有、缓存无）+ 变化（mtime/size 不同）
    added_keys = []
    changed_tasks = []   # (key, dir, rel, mtime, size)
    for k in sorted(current):
        if cancel_cb and cancel_cb():
            return {"added": 0, "removed": 0, "changed": 0, "records": []}
        mtime, size = current[k]
        prev = files.get(k)
        if prev is None:
            added_keys.append(k)
        elif prev != [mtime, size]:
            dh, rel = k.split("/", 1)
            d = hash_to_dir.get(dh)
            if d is not None:
                changed_tasks.append((k, d, rel, mtime, size))

    # 2. 删除/移动：快照无、缓存有
    removed_keys = [k for k in files if k not in current]
    removed = len(removed_keys)

    # 3. 并行解析新增/变化文件（只处理这些，已有文件零重复解析）
    tasks = []
    for k in added_keys:
        dh, rel = k.split("/", 1)
        d = hash_to_dir.get(dh)
        if d is None:
            continue
        mtime, size = current[k]
        tasks.append((k, d, rel, mtime, size))
    tasks.extend(changed_tasks)

    parsed = _build_records_parallel(tasks, dirs, display_names, cancel_cb) if tasks else {}
    for k, _d, _rel, mtime, size in tasks:
        if k in parsed:
            recs[k] = parsed[k]
            files[k] = [mtime, size]

    changed = len(removed_keys) > 0 or bool(parsed)
    if changed:
        for k in removed_keys:
            files.pop(k, None)
            recs.pop(k, None)
        if cache_file:
            _save_disk_cache(cache_file, files, recs, key)
        # 同步内存缓存：load_cached_records 优先读 _cache，避免全量扫描后的
        # 旧 state 覆盖磁盘缓存的新内容（gallery reload 直接读到新记录）
        state = _cache.get(key)
        if state is None:
            state = {"files": {}, "recs": {}}
            _cache[key] = state
        state["files"] = files
        state["recs"] = recs

    new_records = [parsed[t[0]] for t in tasks if t[0] in parsed]
    return {"added": len(added_keys), "removed": removed, "changed": len(changed_tasks),
            "records": new_records}


def _build_virtual_record(root: Path, rel: str, mtime: float,
                          prefix: str, dir_hash: str) -> dict:
    """为单个 output 文件构建虚拟记录（含元数据提取）。

    prefix：该目录的「我的作品」分组前缀（单目录为 my_works，多目录为 my_works/<目录名>）。
    """
    abs_path = root / rel
    rel_parts = Path(rel).parts
    sub = "/".join(rel_parts[:-1]) if len(rel_parts) > 1 else ""
    group = prefix if not sub else f"{prefix}/{sub}"
    digest = hashlib.sha1(rel.encode("utf-8")).hexdigest()[:12]

    rec = {
        "id": f"vout:{dir_hash}:{digest}",
        "title": Path(rel).name,
        "tags": [],
        "positive": "",
        "negative": "",
        "base_model": "其他",
        "base_model_raw": "",
        "models": [],
        "loras": [],
        "sampler": "",
        "steps": "",
        "cfg": "",
        "seed": "",
        "width": 0,
        "height": 0,
        "source": "comfy_output",
        "source_url": "",
        "image_file": "",
        "thumb_file": "",
        "media_type": "image",
        "video_file": "",
        "group": group,
        "is_virtual": True,
        "virtual_path": str(abs_path),
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(mtime)),
        "_mtime": mtime,
        "_rel": rel,
        "_dir": str(root),
        "_dir_hash": dir_hash,
    }
    # 提取生成参数（ComfyUI PNG：prompt/workflow chunks）
    try:
        from app.image_meta import extract_image_meta
        from app.thumbs import image_size
        meta = extract_image_meta(str(abs_path))
        if meta.get("positive"):
            rec["positive"] = meta["positive"]
            rec["title"] = meta["positive"][:24] or rec["title"]
        if meta.get("negative"):
            rec["negative"] = meta["negative"]
        mn = meta.get("model_name") or ""
        if mn:
            rec["models"] = [{"name": mn, "type": "大模型", "url": "", "base_model": ""}]
        rec["loras"] = meta.get("loras") or []
        w, h = image_size(str(abs_path))
        rec["width"] = int(w or 0)
        rec["height"] = int(h or 0)
    except Exception:
        pass
    return rec


def _build_records_parallel(tasks, dirs, display_names, cancel_cb=None, max_workers=None):
    """多线程并行构建多条虚拟记录（读 PNG 尾部元数据，纯 IO/CPU 操作，线程安全）。

    tasks: [(key, dir_path, rel, mtime, size)]，key 为 state 的 {dir_hash}/{rel}。
    dirs/display_names：与 scan_output_images 相同的目录列表与显示名映射
    （分组前缀在提交前算好，工作线程只做 _build_virtual_record 纯读计算）。
    cancel_cb: callback() -> bool，返回 True 时停止等待剩余 future（尽量优雅退出）。
    返回 {key: rec}（仅已成功解析的；单个失败跳过，不阻塞整体）。
    注意：结果顺序无关（调用方最终按 mtime 排序），并行安全即可。
    """
    if not tasks:
        return {}
    workers = max_workers or min(8, max(1, (os.cpu_count() or 4)))
    prefix_by = {d: _group_prefix_for(dirs, d, display_names) for d in dirs}
    out = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="comfy_parse") as ex:
        fut_map = {}
        for key, d, rel, mtime, size in tasks:
            if cancel_cb and cancel_cb():
                break
            dh = key.split("/", 1)[0]
            fut = ex.submit(_build_virtual_record, Path(d), rel, mtime,
                            prefix_by[d], dh)
            fut_map[fut] = key
        for fut in as_completed(fut_map):
            if cancel_cb and cancel_cb():
                # 取消：不再等待剩余 future（cancel_futures 取消未启动的，
                # 已运行的至多 workers 个会在 with 退出前自然完成）
                ex.shutdown(wait=False, cancel_futures=True)
                return out
            key = fut_map[fut]
            try:
                rec = fut.result()
            except Exception:
                continue   # 单个文件解析失败：跳过，不阻塞整体扫描
            out[key] = rec
    return out


def virtual_groups(dirs, cache_file=None) -> dict:
    """返回 {group: count}（虚拟记录的 my_works 分组统计，含子组）。"""
    out = {}
    for r in scan_output_images(dirs, cache_file):
        g = r.get("group") or GROUP_ROOT
        out[g] = out.get(g, 0) + 1
    return out
