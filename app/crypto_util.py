"""轻量密钥保护：Windows DPAPI 加密 + 跨平台兜底。

存储格式："dpapi:v1:<base64>"（Windows）/ "plain:v1:<base64>"（其他平台）。
旧版本明文值（无前缀）直接兼容读取。
"""
import base64
import sys

_PREFIX_DPAPI = "dpapi:v1:"
_PREFIX_PLAIN = "plain:v1:"


def protect(text: str) -> str:
    """加密字符串，返回带前缀的存储值。"""
    data = (text or "").encode("utf-8")
    if not data:
        return ""
    if sys.platform == "win32":
        try:
            blob = _dpapi(data, protect=True)
            return _PREFIX_DPAPI + base64.b64encode(blob).decode("ascii")
        except Exception:
            pass  # DPAPI 失败时回退明文
    return _PREFIX_PLAIN + base64.b64encode(data).decode("ascii")


def unprotect(stored: str) -> str:
    """解密存储值；旧版明文（无前缀）原样返回。"""
    if not stored:
        return ""
    if stored.startswith(_PREFIX_DPAPI):
        try:
            blob = base64.b64decode(stored[len(_PREFIX_DPAPI):].encode("ascii"))
            return _dpapi(blob, protect=False).decode("utf-8", errors="replace")
        except Exception:
            return ""  # 解密失败返回空（安全：不泄露密文）
    if stored.startswith(_PREFIX_PLAIN):
        try:
            return base64.b64decode(stored[len(_PREFIX_PLAIN):].encode("ascii")).decode("utf-8", errors="replace")
        except Exception:
            return ""
    return stored  # 旧版明文


def _dpapi(data: bytes, protect: bool) -> bytes:
    """Windows DPAPI：protect=True 加密，False 解密。"""
    import ctypes

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.c_void_p)]

    buf = ctypes.create_string_buffer(data, len(data))
    blob_in = DATA_BLOB(len(data), ctypes.cast(buf, ctypes.c_void_p))
    blob_out = DATA_BLOB()
    fn = ctypes.windll.crypt32.CryptProtectData if protect else ctypes.windll.crypt32.CryptUnprotectData
    ok = fn(ctypes.byref(blob_in), None, None, None, None, 0, ctypes.byref(blob_out))
    if not ok:
        raise OSError(f"DPAPI {'protect' if protect else 'unprotect'} failed")
    try:
        return ctypes.string_at(blob_out.pbData, blob_out.cbData)
    finally:
        ctypes.windll.kernel32.LocalFree(blob_out.pbData)