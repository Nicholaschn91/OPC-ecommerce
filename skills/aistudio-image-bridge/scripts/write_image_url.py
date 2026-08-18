#!/usr/bin/env python3
"""Write generated image URLs to Feishu 设计方案图片 field.

Usage:
  python write_image_url.py <record_id> <url1> [url2 url3 ...]
  python write_image_url.py <record_id> --file <urls_file>  (one URL per line)
"""

import sys
import json
import os

# Reuse feishu_products_io from same scripts directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import feishu_products_io as f


APP_TOKEN = "ONy9bZ0oFaaiSEsf4ggcs61enRc"
TABLE_ID = "tbl75glY29VulRLm"
FIELD_NAME = "设计方案图片"


def write_image_urls(record_id, urls):
    """
    Write image URLs to record's 设计方案图片 field.
    Joins multiple URLs with newlines.
    Returns dict: {success, field_value, error}
    """
    token = f.get_token()
    design_images = "\n".join(urls)

    # Use the same pattern as write_design_file.py
    import requests

    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/{record_id}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "fields": {
            FIELD_NAME: design_images,
        }
    }

    resp = requests.put(url, headers=headers, json=body, timeout=30)
    data = resp.json()

    if data.get("code") == 0:
        # Verify write
        verify = f.get_record(token, record_id)
        fields = verify.get("fields", {})
        written = fields.get(FIELD_NAME, "")
        return {
            "success": True,
            "field_value": written,
            "code": data.get("code"),
            "msg": data.get("msg", ""),
        }
    else:
        return {
            "success": False,
            "error": data.get("msg", str(data)),
            "code": data.get("code"),
        }


def main():
    if len(sys.argv) < 3:
        print("Usage: python write_image_url.py <record_id> <url1> [url2 ...]", file=sys.stderr)
        print("       python write_image_url.py <record_id> --file <urls_file>", file=sys.stderr)
        sys.exit(1)

    record_id = sys.argv[1]

    if sys.argv[2] == "--file":
        if len(sys.argv) < 4:
            print("ERROR: --file requires a filename", file=sys.stderr)
            sys.exit(2)
        with open(sys.argv[3], 'r', encoding='utf-8') as fh:
            urls = [line.strip() for line in fh if line.strip()]
    else:
        urls = sys.argv[2:]

    if not urls:
        print("ERROR: No URLs provided", file=sys.stderr)
        sys.exit(3)

    result = write_image_urls(record_id, urls)

    if result["success"]:
        print(f"OK: Wrote {len(urls)} URLs to record {record_id}")
        print(f"Field value ({len(result['field_value'])} chars):")
        for i, url in enumerate(urls):
            print(f"  [{i+1}] {url}")
    else:
        print(f"ERROR ({result['code']}): {result['error']}", file=sys.stderr)
        sys.exit(4)


if __name__ == '__main__':
    main()
