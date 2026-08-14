#!/usr/bin/env python3
# sync-cookies.py — 从常用浏览器(Tabbit)同步 qianwen 登录 cookie 到 cdp-profile-h
# 用途：cdp-profile-h 是脚本专用隔离 profile，其 cookie 可能过期；本机 Tabbit 是常登录态，
#       复用它的 qianwen cookie 几乎不会过期。每次跑优化前若探针 NEED_LOGIN，运行本脚本即可。
#
# 依赖：cryptography（managed venv）；Windows DPAPI（crypt32.dll）；Tabbit 关闭时运行最佳。
# 用法：python sync-cookies.py
import sqlite3, json, base64, os, subprocess, sys
from ctypes import wintypes, byref, c_void_p, Structure, cast, create_string_buffer
import ctypes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

TABBIT_LS   = r"C:\Users\Administrator.DESKTOP-AHRMISP\AppData\Local\Tabbit\User Data\Local State"
TABBIT_NET  = r"C:\Users\Administrator.DESKTOP-AHRMISP\AppData\Local\Tabbit\User Data\Default\Network\Cookies"
CDP_LS      = r"C:\Users\Administrator.DESKTOP-AHRMISP\.workbuddy\skills\qwen-listing-optimizer\cdp-profile-h\Local State"
CDP_COOKIES = r"C:\Users\Administrator.DESKTOP-AHRMISP\.workbuddy\skills\qwen-listing-optimizer\cdp-profile-h\Default\Network\Cookies"
TMP         = r"C:\Users\Administrator.DESKTOP-AHRMISP\WorkBuddy\2026-07-16-11-36-41\_cookie_tmp\Tabbit_Cookies_sync"

crypt32 = ctypes.windll.crypt32
kernel32 = ctypes.windll.kernel32
kernel32.LocalFree.argtypes = [wintypes.HANDLE]
kernel32.LocalFree.restype = wintypes.HANDLE

class DATA_BLOB(Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", c_void_p)]

def dpapi_unprotect(data: bytes) -> bytes:
    blob_in = DATA_BLOB(len(data), cast(create_string_buffer(data, len(data)), c_void_p))
    blob_out = DATA_BLOB()
    if crypt32.CryptUnprotectData(byref(blob_in), None, None, None, None, 0, byref(blob_out)):
        buf = ctypes.string_at(blob_out.pbData, blob_out.cbData)
        kernel32.LocalFree(blob_out.pbData)
        return buf
    raise RuntimeError("CryptUnprotectData failed err=%d" % ctypes.GetLastError())

def get_aes_key(local_state_path: str) -> bytes:
    with open(local_state_path, "r", encoding="utf-8") as f:
        ls = json.load(f)
    enc = base64.b64decode(ls["os_crypt"]["encrypted_key"])
    assert enc[:5] == b"DPAPI"
    return dpapi_unprotect(enc[5:])

def decrypt(enc_value: bytes, key: bytes) -> bytes:
    if enc_value[:3] in (b"v10", b"v11"):
        nonce = enc_value[3:15]
        return AESGCM(key).decrypt(nonce, enc_value[15:], None)
    return enc_value

def reencrypt(plaintext: bytes, key: bytes, nonce: bytes) -> bytes:
    return b"v10" + nonce + AESGCM(key).encrypt(nonce, plaintext, None)

def tabbit_running() -> bool:
    try:
        out = subprocess.run(["tasklist"], capture_output=True, text=True, timeout=10).stdout
        return "Tabbit Browser.exe" in out
    except Exception:
        return False

def main():
    if not os.path.exists(TABBIT_LS):
        print("[SKIP] 未找到 Tabbit 浏览器，跳过 cookie 同步"); return
    if tabbit_running():
        print("[WARN] Tabbit 浏览器正在运行，Cookies 文件被锁。")
        print("       请先关闭 Tabbit 浏览器（登录态已落盘，重开仍在），再运行本脚本。")
        sys.exit(2)
    # 复制 Tabbit cookie 到临时副本（无锁）
    os.makedirs(os.path.dirname(TMP), exist_ok=True)
    import shutil
    shutil.copyfile(TABBIT_NET, TMP)
    tabbit_key = get_aes_key(TABBIT_LS)
    cdp_key = get_aes_key(CDP_LS)
    src = sqlite3.connect(TMP)
    dst = sqlite3.connect(CDP_COOKIES)
    cols = [r[1] for r in dst.execute("PRAGMA table_info(cookies)")]
    like = " OR ".join(["host_key LIKE '%%%s%%'" % d for d in ("qianwen","tongyi","aliyun","taobao","tb.cn")])
    rows = src.execute("SELECT %s FROM cookies WHERE %s" % (",".join(cols), like)).fetchall()
    ok = fail = 0
    for row in rows:
        d = dict(zip(cols, row))
        ev = d["encrypted_value"]
        try:
            pt = decrypt(ev, tabbit_key)
            nonce = ev[3:15] if ev[:3] in (b"v10", b"v11") else (b"\x00" * 12)
            d["encrypted_value"] = reencrypt(pt, cdp_key, nonce)
        except Exception as e:
            fail += 1; print("  FAIL %s/%s: %s" % (d["host_key"], d["name"], e)); continue
        ph = ",".join("?" * len(cols))
        dst.execute("INSERT OR REPLACE INTO cookies (%s) VALUES (%s)" % (",".join(cols), ph),
                    ["" if d[c] is None else d[c] for c in cols])
        ok += 1
    dst.commit(); src.close(); dst.close()
    v = sqlite3.connect(CDP_COOKIES)
    n = v.execute("SELECT COUNT(*) FROM cookies WHERE host_key LIKE '%qianwen%' OR host_key LIKE '%aliyun%'").fetchone()[0]
    v.close()
    print("[DONE] 注入 ok=%d fail=%d；cdp-profile-h 现有 %d 个 qianwen/aliyun cookie" % (ok, fail, n))

if __name__ == "__main__":
    main()
