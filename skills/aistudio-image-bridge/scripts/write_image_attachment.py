#!/usr/bin/env python3
"""
Upload image files as attachments to the Feishu Bitable 设计方案图片 field.

Usage:
  python write_image_attachment.py <record_id> <image1.png> [image2.png ...]

Flow:
  1. Upload each image to Feishu Drive (medias/upload_all)
  2. Collect file_tokens
  3. Write tokens to 设计方案图片 field (type 17 attachment)
  4. Verify read-back
"""

import os
import sys
import json
import time
import mimetypes
import requests


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

BASE_URL = "https://open.feishu.cn/open-apis"


def get_token():
    """Get tenant access token."""
    r = requests.post(
        f"{BASE_URL}/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET},
        timeout=15,
    )
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(f"Token error: {data}")
    return data["tenant_access_token"]


def upload_image_to_drive(token, file_path):
    """
    Upload an image to Feishu Drive.
    
    Returns: file_token string
    """
    file_name = os.path.basename(file_path)
    file_size = os.path.getsize(file_path)
    
    with open(file_path, "rb") as f:
        file_content = f.read()

    mime = mimetypes.guess_type(file_path)[0] or "image/png"
    
    r = requests.post(
        f"{BASE_URL}/drive/v1/medias/upload_all",
        headers={"Authorization": f"Bearer {token}"},
        data={
            "file_name": file_name,
            "parent_type": "bitable_file",
            "parent_node": APP_TOKEN,
            "size": str(file_size),
        },
        files={"file": (file_name, file_content, mime)},
        timeout=60,
    )
    
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(
            f"Failed to upload {file_name}: code={data.get('code')} msg={data.get('msg')}"
        )
    
    file_token = data["data"]["file_token"]
    print(f"  Uploaded: {file_name} -> {file_token}", file=sys.stderr)
    return file_token


def write_attachments(token, record_id, file_tokens):
    """
    Write file_tokens as attachments to the specified record.
    """
    attachments = [{"file_token": ft} for ft in file_tokens]
    
    r = requests.put(
        f"{BASE_URL}/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/{record_id}",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        json={"fields": {FIELD_NAME: attachments}},
        timeout=30,
    )
    
    data = r.json()
    if data.get("code") != 0:
        raise RuntimeError(
            f"Failed to write attachments: code={data.get('code')} msg={data.get('msg')}"
        )
    return data


def verify_attachments(token, record_id):
    """Read back and verify attachments were written.

    用列表接口（page_size=100）扫描目标 record_id，而非单条 GET —— 飞书铁律：
    单条 GET 偶发空 fields 是最终一致性陷阱，不可信；列表扫描才能确认字段非空。
    """
    url = f"{BASE_URL}/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records"
    headers = {"Authorization": f"Bearer {token}"}
    page_token = None
    while True:
        params = {"page_size": 100}
        if page_token:
            params["page_token"] = page_token
        r = requests.get(url, headers=headers, params=params, timeout=15)
        data = r.json()
        if data.get("code") != 0:
            return None
        items = (data.get("data", {}).get("items")
                 or data.get("data", {}).get("records") or [])
        for rec in items:
            if rec.get("record_id") == record_id:
                return rec.get("fields", {}).get(FIELD_NAME, [])
        nxt = data.get("data", {}).get("next_page_token")
        if not nxt:
            break
        page_token = nxt
    return None


def main():
    if len(sys.argv) < 3:
        print(
            "Usage: python write_image_attachment.py <record_id> <image1.png> [image2.png ...]",
            file=sys.stderr,
        )
        sys.exit(1)

    record_id = sys.argv[1]
    image_paths = sys.argv[2:]

    # Validate all files exist
    for p in image_paths:
        if not os.path.exists(p):
            print(f"ERROR: File not found: {p}", file=sys.stderr)
            sys.exit(2)

    print(f"Record: {record_id}", file=sys.stderr)
    print(f"Images: {len(image_paths)} files", file=sys.stderr)

    # Get token
    token = get_token()

    # Upload all images
    file_tokens = []
    for i, p in enumerate(image_paths):
        print(f"  [{i+1}/{len(image_paths)}] Uploading: {os.path.basename(p)}", file=sys.stderr)
        try:
            ft = upload_image_to_drive(token, p)
            file_tokens.append(ft)
        except Exception as e:
            print(f"  FAILED: {e}", file=sys.stderr)
            # Continue with remaining images
        time.sleep(0.5)  # Rate limit buffer

    if not file_tokens:
        print("ERROR: No images successfully uploaded", file=sys.stderr)
        sys.exit(3)

    # Write attachments to record
    print(f"  Writing {len(file_tokens)} attachments to record {record_id}...", file=sys.stderr)
    write_attachments(token, record_id, file_tokens)

    # Verify
    attachments = verify_attachments(token, record_id)
    if attachments:
        print(f"VERIFY OK: {len(attachments)} attachments in record {record_id}")
        for i, att in enumerate(attachments):
            ft = att.get("file_token", "?")
            fn = att.get("name", "?")
            print(f"  [{i+1}] {fn} ({ft})")
    else:
        print(f"VERIFY FAILED: No attachments found after write!", file=sys.stderr)
        sys.exit(4)


if __name__ == "__main__":
    main()
