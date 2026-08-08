"""v3.0 M2.1 API Key 加密存储测试。"""
import os
import sys
import tempfile
from pathlib import Path

os.environ['QT_QPA_PLATFORM'] = 'offscreen'
sys.path.insert(0, '.')

from app import i18n
from app.data_store import DataStore
from app.crypto_util import protect, unprotect

td = Path(tempfile.mkdtemp())
store = DataStore(td / 'Library')
i18n.init(store.settings_path(), 'zh')

# ---- T1: protect/unprotect 往返 ----
for text in ["civ_test123456", "", "中文密钥+特殊字符!@#", "civ_" + "x" * 100]:
    stored = protect(text)
    assert unprotect(stored) == text, f"往返失败: {text!r} -> {stored!r}"
print('T1 protect/unprotect 往返 ✓')

# ---- T2: 存储为密文（非明文）----
key = "civ_secret_key_123"
store.save_setting('civitai_api_key', key)
raw = (store.settings_path()).read_text(encoding='utf-8')
assert key not in raw, f"密钥不应明文存储: {raw}"
print('T2 存储为密文（settings.json 不含明文密钥）✓')
print(f'   存储值: {raw.splitlines()[3].strip() if len(raw.splitlines())>3 else raw[:60]}')

# ---- T3: 读取解密 ----
assert store.load_setting('civitai_api_key') == key
print('T3 读取解密 ✓')

# ---- T4: 旧版明文兼容 ----
import json
store.settings_path().write_text(json.dumps({'civitai_api_key': 'civ_old_plain'}), encoding='utf-8')
assert store.load_setting('civitai_api_key') == 'civ_old_plain'
print('T4 旧版明文兼容 ✓')

# ---- T5: 其他设置不受影响 ----
store.save_setting('comfyui_dir', r'C:\ComfyUI')
assert store.load_setting('comfyui_dir') == r'C:\ComfyUI'
print('T5 其他设置不受影响 ✓')

print()
print('M2.1 API Key 加密测试全部通过 ✓')