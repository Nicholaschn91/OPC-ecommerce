#!/usr/bin/env python3
"""Feishu/Lark API helper — token management + record/image fetching."""

import json
import os
import sys
import time
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

def _load_env(var: str, default=None):
    """Read a secret from env first, then skill-level .env (gitignored)."""
    v = os.environ.get(var)
    if v:
        return v
    env_file = Path(__file__).resolve().parent.parent / ".env"
    if env_file.exists():
        for line in env_file.read_text().splitlines():
            line = line.strip()
            if line.startswith(f"{var}="):
                val = line.split("=", 1)[1].strip().strip('"').strip("'")
                if val and "your-" not in val.lower():
                    return val
    return default


APP_ID = _load_env("FEISHU_APP_ID")
APP_SECRET = _load_env("FEISHU_APP_SECRET")

# Token cache — reuse across calls (token lasts 2 hours)
_TOKEN_CACHE_FILE = Path(__file__).resolve().parent / ".feishu_token.json"
_TOKEN_CACHE_TTL = 7200  # 2 hours


def _get_cached_token() -> str | None:
    """Return cached token if still valid."""
    if _TOKEN_CACHE_FILE.exists():
        try:
            data = json.loads(_TOKEN_CACHE_FILE.read_text())
            if time.time() < data.get("expires_at", 0):
                return data["token"]
        except (json.JSONDecodeError, KeyError):
            pass
    return None


def _save_token(token: str, expire: int):
    _TOKEN_CACHE_FILE.write_text(json.dumps({
        "token": token,
        "expires_at": time.time() + expire,
    }))


def get_tenant_token() -> str:
    """Get or refresh tenant_access_token."""
    if not APP_ID or not APP_SECRET:
        print("ERROR: FEISHU_APP_ID / FEISHU_APP_SECRET 未设置。\n"
              "  请在运行环境导出这两个变量，或写入 gitignored 的 agnes-studio/.env，\n"
              "  切勿硬编码进脚本。", file=sys.stderr)
        sys.exit(1)
    cached = _get_cached_token()
    if cached:
        return cached

    req = Request(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        data=json.dumps({"app_id": APP_ID, "app_secret": APP_SECRET}).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode())
    if result.get("code") != 0:
        print(f"ERROR: Failed to get token: {result.get('msg')}", file=sys.stderr)
        sys.exit(1)
    token = result["tenant_access_token"]
    expire = result.get("expire", 7200)
    _save_token(token, expire)
    return token


def feishu_get(url: str, headers: dict | None = None) -> dict:
    """Generic GET request to Feishu API."""
    token = get_tenant_token()
    if not headers:
        headers = {}
    headers["Authorization"] = f"Bearer {token}"
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode())
    except HTTPError as e:
        body = e.read().decode(errors="replace")
        if e.code == 401:
            # Token expired, clear cache and retry
            _TOKEN_CACHE_FILE.unlink(missing_ok=True)
            token = get_tenant_token()
            headers["Authorization"] = f"Bearer {token}"
            req = Request(url, headers=headers)
            with urlopen(req, timeout=60) as resp2:
                return json.loads(resp2.read().decode())
        print(f"HTTP {e.code}: {body[:300]}", file=sys.stderr)
        sys.exit(1)


def feishu_post(url: str, body: dict) -> dict:
    """Generic POST request to Feishu API."""
    token = get_tenant_token()
    req = Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def get_record(base_id: str, table_id: str, record_id: str) -> dict:
    """Get a single record by ID."""
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{base_id}/tables/{table_id}/records/{record_id}"
    result = feishu_get(url)
    if result.get("code") != 0:
        print(f"ERROR: {result.get('msg')}", file=sys.stderr)
        sys.exit(1)
    return result["data"]["record"]


def list_records(base_id: str, table_id: str, view_id: str = "", page_size: int = 20, page_token: str = "") -> dict:
    """List records with pagination."""
    url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{base_id}/tables/{table_id}/records"
    params = f"?page_size={page_size}"
    if view_id:
        params += f"&view_id={view_id}"
    if page_token:
        params += f"&page_token={page_token}"
    result = feishu_get(url + params)
    if result.get("code") != 0:
        print(f"ERROR: {result.get('msg')}", file=sys.stderr)
        sys.exit(1)
    return result["data"]


def get_image_download_url(file_token: str) -> str:
    """Get temporary download URL for a Feishu image."""
    url = f"https://open.feishu.cn/open-apis/drive/v1/medias/batch_get_tmp_download_url?file_tokens={file_token}"
    result = feishu_get(url)
    if result.get("code") != 0:
        print(f"ERROR: {result.get('msg')}", file=sys.stderr)
        sys.exit(1)
    return result["data"]["tmp_download_urls"][0]["tmp_download_url"]


def download_image_to_bytes(download_url: str) -> bytes:
    """Download image from URL to bytes."""
    req = Request(
        download_url,
        headers={
            "Authorization": f"Bearer {get_tenant_token()}",
            "Referer": "https://open.feishu.cn/",
        },
    )
    with urlopen(req, timeout=60) as resp:
        return resp.read()


def get_record_images(base_id: str, table_id: str, record_id: str) -> list[dict]:
    """Get all images from a record's '图片' field, returning download URLs."""
    record = get_record(base_id, table_id, record_id)
    images = record["fields"].get("图片", [])
    result = []
    for img in images:
        file_token = img.get("file_token", "")
        if not file_token:
            continue
        dl_url = get_image_download_url(file_token)
        result.append({
            "name": img.get("name", ""),
            "file_token": file_token,
            "download_url": dl_url,
            "bytes": download_image_to_bytes(dl_url),
        })
    return result


if __name__ == "__main__":
    import base64
    import argparse

    parser = argparse.ArgumentParser(description="Feishu API helper")
    sub = parser.add_subparsers(dest="command")

    # get-images: download images from a record
    p_imgs = sub.add_parser("get-images", help="Get images from a record")
    p_imgs.add_argument("--base", required=True)
    p_imgs.add_argument("--table", required=True)
    p_imgs.add_argument("--record", required=True)

    # list: list records with image counts
    p_list = sub.add_parser("list", help="List records")
    p_list.add_argument("--base", required=True)
    p_list.add_argument("--table", required=True)
    p_list.add_argument("--page-size", type=int, default=20)

    args = parser.parse_args()

    if args.command == "get-images":
        imgs = get_record_images(args.base, args.table, args.record)
        for img in imgs:
            b64 = base64.b64encode(img["bytes"]).decode()
            print(f"IMAGE:{img['name']}:data:image/jpeg;base64,{b64}")
    elif args.command == "list":
        data = list_records(args.base, args.table, page_size=args.page_size)
        for rec in data["items"]:
            imgs = rec["fields"].get("图片", [])
            name = rec["fields"].get("商品名称", "N/A")[:30]
            print(f"{rec['record_id']} | {name} | {len(imgs)} 张图片")
