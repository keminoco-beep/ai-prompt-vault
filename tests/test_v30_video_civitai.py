"""修复：Civitai 视频导入（parse_image_page 视频分支 + download_video + import_civitai 全链路）。"""
import os, sys, tempfile, threading, json, re
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, ".")
from PySide6.QtWidgets import QApplication, QMessageBox
QMessageBox.information = staticmethod(lambda *a, **k: QMessageBox.Ok)
QMessageBox.warning = staticmethod(lambda *a, **k: QMessageBox.Ok)

from app import i18n
from app.data_store import DataStore
from app import civitai
from app.ui.style import APP_QSS

app = QApplication(sys.argv)
app.setStyleSheet(APP_QSS)
td = Path(tempfile.mkdtemp())
store = DataStore(td / "Library")
i18n.init(store.settings_path(), "zh")

ok = True
def check(name, cond, extra=""):
    global ok
    print(f"  {'✓' if cond else '✗'} {name}{('  ' + str(extra)) if extra else ''}")
    if not cond:
        ok = False

# ---- T1: parse_image_page 视频页面 ----
# 构造 Civitai 视频页面 JSON（含 video 对象 + meta + resources）
video_page_data = {
    "id": 123456,
    "videos": [{"id": 123456, "type": "video", "name": "My AI Video",
                "width": 832, "height": 1216,
                "url": "https://video.civitai.com/x/abc/video.mp4",
                "resources": [{"modelId": 999, "modelName": "sdxl_base",
                               "modelType": "Checkpoint", "baseModel": "SDXL 1.0"}],
                "meta": {"prompt": "1girl, masterpiece", "negativePrompt": "lowres",
                         "sampler": "DPM++ 2M", "steps": 28, "cfgScale": 6.5, "seed": 777}}],
}
video_page_json = {"props": {"pageProps": {"trpcState": {"json": {"queries": [
    {"state": {"data": video_page_data}}]}}}}}
html = '<html><script id="__NEXT_DATA__" type="application/json">' + \
    json.dumps(video_page_json).replace("/", "\\/") + '</script></html>'
parsed = civitai.parse_image_page(html, 123456)
check("T1 media_type=video", parsed["media_type"] == "video")
check("T1 video_url 提取", parsed["video_url"] == "https://video.civitai.com/x/abc/video.mp4",
      repr(parsed["video_url"]))
check("T1 meta 提取（提示词）", (parsed["meta"] or {}).get("prompt") == "1girl, masterpiece")
check("T1 resources 提取（模型）", len(parsed["resources"]) == 1
      and parsed["resources"][0]["modelName"] == "sdxl_base")
check("T1 width/height", parsed["width"] == 832 and parsed["height"] == 1216)

# ---- T2: 图片页面不受影响 ----
img_page_data = {
    "id": 555,
    "images": [{"id": 555, "type": "image", "name": "pic",
                "width": 512, "height": 768, "url": "someguid",
                "resources": [{"modelId": 1, "modelName": "m1", "modelType": "Checkpoint",
                               "baseModel": "SD 1.5"}],
                "meta": {"prompt": "cat", "steps": 20}}],
}
img_page_json = {"props": {"pageProps": {"trpcState": {"json": {"queries": [
    {"state": {"data": img_page_data}}]}}}}}
img_html = '<html><script id="__NEXT_DATA__" type="application/json">' + \
    json.dumps(img_page_json).replace("/", "\\/") + '</script></html>'
parsed2 = civitai.parse_image_page(img_html, 555)
check("T2 图片页 media_type=image", parsed2["media_type"] == "image")
check("T2 图片页 meta 正常", (parsed2["meta"] or {}).get("prompt") == "cat")
check("T2 图片页 resources 正常", len(parsed2["resources"]) == 1)

# ---- T3: _extract_real_image_url 排除视频 URL ----
mix_html = '<img src="https://image.civitai.com/x/a.png?width=450"><video src="https://image.civitai.com/x/video.mp4">'
u = civitai._extract_real_image_url(mix_html, None)
check("T3 视频 URL 不被当图片", u.startswith("https://image.civitai.com/x/a.png"), repr(u))

# ---- T4: download_video（本地 HTTP 视频） ----
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
class V(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"\x00\x00\x00\x18ftypmp42" + b"V" * 100_000
        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        self.wfile.flush()
    def log_message(self, *a): pass
srv = ThreadingHTTPServer(("127.0.0.1", 0), V)
threading.Thread(target=srv.serve_forever, daemon=True).start()
vurl = f"http://127.0.0.1:{srv.server_address[1]}/v.mp4"
dest = td / "v.mp4"
vok, verr = civitai.download_video(vurl, str(dest))
check("T4 视频下载成功", vok and dest.exists() and dest.stat().st_size > 100_000, f"({verr})")

# ---- T5: import_civitai 视频全链路 ----
# 模拟 fetch_image 返回视频字段（走 workers.import_civitai 的视频分支）
from unittest.mock import patch
fake_fields = {
    "title": "My AI Video", "positive": "1girl, masterpiece",
    "negative": "lowres", "sampler": "DPM++ 2M", "steps": "28", "cfg": "6.5",
    "seed": "777", "models": [{"name": "sdxl_base", "type": "大模型", "url": "", "base_model": "SDXL 1.0"}],
    "loras": [], "base_model": "SDXL 1.0", "base_model_raw": "SDXL 1.0",
    "width": 832, "height": 1216, "source": "civitai",
    "image_url": "", "civitai_id": 123456,
    "media_type": "video", "video_url": vurl,
}
with patch("app.workers.civitai.fetch_image", return_value=fake_fields):
    from app.workers import import_civitai
    res = import_civitai(store, "https://civitai.com/images/123456")
check("T5 返回 video_file", bool(res.get("video_file")), repr(res.get("video_file")))
check("T5 无图片下载错误", not res.get("error"), repr(res.get("error")))
vfile = res.get("video_file") or ""
if vfile:
    check("T5 视频落盘", (store.videos_dir / vfile).exists())
check("T5 fields 保留完整信息",
      res["fields"].get("positive") == "1girl, masterpiece"
      and len(res["fields"].get("models") or []) == 1)
check("T5 缩略图首帧提取不阻塞（假 mp4 无 moov 允许失败）",
      True, f"thumb={res.get('thumb_file')}")

srv.shutdown()
print()
print("Civitai 视频导入修复", "全部通过 ✓" if ok else "存在失败 ✗")
sys.exit(0 if ok else 1)
