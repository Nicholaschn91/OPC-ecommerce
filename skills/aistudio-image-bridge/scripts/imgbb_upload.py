#!/usr/bin/env python3
"""Upload image to ImgBB and return the permanent URL.

Uses ImgBB API keys from ~/.image-seo-workflow/config.json.
Rotates through keys with automatic fallback on failure.
"""

import os
import sys
import json
import time
import base64
import urllib.request
import urllib.error


CONFIG_PATH = os.path.expanduser("~/.image-seo-workflow/config.json")


def load_config():
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def upload_image(image_path, api_key, expiration=None):
    """
    Upload image to ImgBB.
    Returns dict: {success, url, delete_url, error}
    """
    try:
        with open(image_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')

        data = urllib.parse.urlencode({'image': b64}).encode('ascii')
        url = f'https://api.imgbb.com/1/upload?key={api_key}'
        if expiration:
            url += f'&expiration={expiration}'

        req = urllib.request.Request(url, data=data, method='POST')
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode())
            if result.get('success'):
                return {
                    'success': True,
                    'url': result['data']['url'],
                    'display_url': result['data'].get('display_url', ''),
                    'delete_url': result['data'].get('delete_url', ''),
                }
            else:
                return {'success': False, 'error': str(result)}
    except Exception as e:
        return {'success': False, 'error': str(e)}


def upload_with_rotation(image_path, start_index=None):
    """
    Upload with key rotation. Tries each key until success.
    Returns dict: {success, url, key_index, error}
    """
    config = load_config()
    keys = config.get('imgbb_api_keys', [])
    if not keys:
        return {'success': False, 'error': 'No ImgBB API keys configured'}

    start = start_index if start_index is not None else config.get('imgbb_api_key_index', 0)
    # Rotate: start from start_index, wrap around
    order = list(range(start, len(keys))) + list(range(0, start))

    for idx in order:
        key = keys[idx]
        result = upload_image(image_path, key)
        if result['success']:
            return {
                'success': True,
                'url': result['url'],
                'display_url': result.get('display_url', ''),
                'key_index': idx,
            }
        else:
            print(f"  Key {idx} failed: {result.get('error', 'unknown')[:80]}", file=sys.stderr)
            time.sleep(1)

    return {'success': False, 'error': 'All ImgBB keys exhausted'}


def main():
    if len(sys.argv) < 2:
        print("Usage: python imgbb_upload.py <image_path> [start_key_index]", file=sys.stderr)
        sys.exit(1)

    image_path = sys.argv[1]
    start_index = int(sys.argv[2]) if len(sys.argv) > 2 else None

    if not os.path.exists(image_path):
        print(f"ERROR: File not found: {image_path}", file=sys.stderr)
        sys.exit(2)

    result = upload_with_rotation(image_path, start_index)

    if result['success']:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"ERROR: {result['error']}", file=sys.stderr)
        sys.exit(3)


if __name__ == '__main__':
    main()
