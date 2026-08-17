#!/usr/bin/env python3
"""Upload image files as attachments to Feishu Bitable '设计方案图片' field.

Usage:
  python upload_to_feishu.py <record_id> <image1.png> [image2.png ...]   # replace mode (default)
  python upload_to_feishu.py <record_id> -a <image1.png>                  # append mode
"""

import os, sys, json, urllib.request

# 飞书凭证从 references/config.json 读取（不入库，gitignored）
import os as _os, json as _json
def _load_feishu_cfg():
    _p = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "references", "config.json")
    try:
        with open(_p, encoding="utf-8") as _f:
            return _json.load(_f)
    except FileNotFoundError:
        raise SystemExit(f"缺少飞书配置: {_p}\n请复制 references/config.example.json 为 config.json 并填入 APP_ID/APP_SECRET")
_CFG = _load_feishu_cfg()
APP_ID = _CFG["APP_ID"]
APP_SECRET = _CFG["APP_SECRET"]
APP_TOKEN = "ONy9bZ0oFaaiSEsf4ggcs61enRc"
TABLE_ID = "tbl75glY29VulRLm"
FIELD_NAME = "设计方案图片"

def api(method, url, token=None, body=None, content_type="application/json"):
    headers = {"Content-Type": content_type}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body is not None and content_type == "application/json" else body
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())

def get_token():
    tok = api("POST", "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
              body={"app_id": APP_ID, "app_secret": APP_SECRET})
    t = tok.get("tenant_access_token")
    if not t:
        raise SystemExit("TOKEN FAIL: " + json.dumps(tok, ensure_ascii=False))
    return t

def get_record(token, record_id):
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/{record_id}"
    return api("GET", url, token=token)

def upload_file(token, filepath):
    """Upload file to Feishu Drive, return file_token."""
    boundary = "----FormBoundary7MA4YWxkTrZu0gW"
    filename = os.path.basename(filepath)
    
    with open(filepath, "rb") as f:
        file_data = f.read()
    
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file_name"\r\n\r\n{filename}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="parent_type"\r\n\r\nbitable_file\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="parent_node"\r\n\r\n{APP_TOKEN}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="size"\r\n\r\n{len(file_data)}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + file_data + f"\r\n--{boundary}--\r\n".encode()
    
    url = "https://open.feishu.cn/open-apis/drive/v1/medias/upload_all"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": f"multipart/form-data; boundary={boundary}"
    }
    
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        result = json.loads(r.read().decode())
        if result.get("code") != 0:
            raise RuntimeError(f"Upload failed: {result.get('msg')} (code={result.get('code')})")
        return result["data"]["file_token"]

def write_attachments(token, record_id, file_tokens):
    """Write file_tokens to attachment field."""
    attachments = [{"file_token": ft} for ft in file_tokens]
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/{record_id}"
    body = {"fields": {FIELD_NAME: attachments}}
    result = api("PUT", url, token=token, body=body)
    if result.get("code") != 0:
        raise RuntimeError(f"Write failed: {result.get('msg')} (code={result.get('code')})")
    return result

def verify_attachments(token, record_id):
    """Read back and verify."""
    rec = get_record(token, record_id)
    fields = rec.get("data", {}).get("record", {}).get("fields", {})
    return fields.get(FIELD_NAME, [])

def main():
    args = sys.argv[1:]
    append_mode = False
    
    if "-a" in args or "--append" in args:
        append_mode = True
        args = [a for a in args if a not in ("-a", "--append")]
    
    if len(args) < 2:
        print("Usage: python upload_to_feishu.py <record_id> <image1.png> [image2.png ...]", file=sys.stderr)
        print("       python upload_to_feishu.py <record_id> -a <image.png>    (append)", file=sys.stderr)
        sys.exit(1)
    
    record_id = args[0]
    image_paths = args[1:]
    
    for p in image_paths:
        if not os.path.exists(p):
            print(f"ERROR: File not found: {p}", file=sys.stderr)
            sys.exit(2)
    
    token = get_token()
    
    # Get existing attachments if appending
    existing_tokens = []
    if append_mode:
        try:
            existing = verify_attachments(token, record_id)
            existing_tokens = [a["file_token"] for a in existing] if existing else []
            print(f"Existing attachments: {len(existing_tokens)}")
        except Exception as e:
            print(f"Warning: Could not read existing attachments: {e}", file=sys.stderr)
    
    # Upload each image
    new_tokens = []
    for i, p in enumerate(image_paths):
        print(f"[{i+1}/{len(image_paths)}] Uploading: {os.path.basename(p)} ... ", end="", flush=True)
        try:
            ft = upload_file(token, p)
            new_tokens.append(ft)
            print(f"OK ({ft[:16]}...)")
        except Exception as e:
            print(f"FAILED: {e}")
    
    if not new_tokens:
        print("ERROR: No files uploaded successfully", file=sys.stderr)
        sys.exit(3)
    
    # Combine and write
    all_tokens = (existing_tokens + new_tokens) if append_mode else new_tokens
    print(f"\nWriting {len(all_tokens)} attachment(s) to record {record_id} ... ", end="", flush=True)
    write_attachments(token, record_id, all_tokens)
    print("OK")
    
    # Verify
    attachments = verify_attachments(token, record_id)
    if attachments:
        print(f"VERIFY: {len(attachments)} attachment(s) in field '设计方案图片'")
        for i, a in enumerate(attachments):
            print(f"  [{i+1}] {a.get('name', '?')} ({a.get('file_token', '?')[:20]}...)")
    else:
        print("WARNING: No attachments found after write!", file=sys.stderr)

if __name__ == "__main__":
    main()
