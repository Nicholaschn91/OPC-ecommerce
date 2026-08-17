#!/usr/bin/env python3
"""
Agnes 多模态 ALT 文本生成 — base64 内联方式（Endpoint Failover 国内备份）。

特点：
  - 无外部图床依赖，图片以 base64 data URI 直接传给 Agnes 视觉模型
  - 自动缩图降 token（白底产品图 768px 已足够，避免浪费）
  - 兼容所有常见图片格式（JPEG/PNG/WebP）
  - Endpoint 自动 failover：.com (agnes-2.0-flash) 主用，.cn (agnes-2.5-flash) 兜底
    （401/403 与网络/5xx 一样触发 failover：按域名用各自 key 兜底，双令牌环境不串号）

用法:
  python alt.py --image product.png              # 默认 768px（甜点区）
  python alt.py --image product.png --size 512    # 简单产品，最低 token
  python alt.py --image product.png --size 1024   # 极致细节（不推荐）
  python alt.py --image product.png -o alt.txt    # 输出到文件
  python alt.py --image product.png --name "金毛异形暖手抱枕"  # 带品名，ALT 识别更准
"""
import argparse
import base64
import json
import sys
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

# Endpoint failover: .com 主用（agnes-2.0-flash，本机经 TUN/VPN 可达），.cn 兜底（agnes-2.5-flash）。
# **双令牌**：.com 用 AGNES_API_KEY，.cn 用 AGNES_API_KEY_CN（未配置回退主 key）。
# 两域凭据是用户两种代理环境各自的令牌，failover 必须按域名用各自 key，否则兜底端点必 401。
ENDPOINTS = [
    ("https://apihub.agnes-ai.com/v1/chat/completions", "agnes-2.0-flash", "AGNES_API_KEY"),
    ("https://api.agnes-ai.cn/v1/chat/completions", "agnes-2.5-flash", "AGNES_API_KEY_CN"),
]
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"

# 尺寸建议速查（白底电商产品图）
SIZE_RECS = {
    512:  "简单/纯色/轮廓清晰、无文字的产品（~620 token）",
    768:  "带纹理/刻字/图案/多色的详细产品【推荐默认】（~940 token）",
    1024: "极致细节（~1390 token，边际递减，一般不推荐用于 ALT）",
}


def load_key() -> str:
    env = ENV_PATH.read_text(encoding="utf-8")
    for line in env.splitlines():
        if line.startswith("AGNES_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("AGNES_API_KEY not found — set it in .env")


def _key_for(env_name: str, fallback_key: str = None) -> str:
    """取指定域名的 key；.cn key 未配置时回退主 key（向后兼容单 key 场景）。"""
    env = ENV_PATH.read_text(encoding="utf-8")
    for line in env.splitlines():
        if line.startswith(f"{env_name}="):
            return line.split("=", 1)[1].strip()
    if fallback_key:
        return fallback_key
    raise SystemExit(f"{env_name} not found — set it in .env")


def downscale(path: Path, max_side: int) -> str:
    """缩放到 max_side 以内，保持比例。返回 JPEG base64 data URI 字符串。"""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = min(max_side / w, max_side / h, 1.0)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    img = img.resize((nw, nh), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    print(f"  缩放 {w}x{h} -> {nw}x{nh}  ({len(buf.getvalue())//1024} KB JPEG)",
          file=sys.stderr)
    return f"data:image/jpeg;base64,{b64}"


def generate(key: str, data_uri: str, name: str = None,
             endpoints: list = None) -> dict:
    endpoints = endpoints or ENDPOINTS
    user_text = (
        "Write ONE e-commerce ALT text (under 125 characters) for this "
        "white-background product image. Be literal and specific. Include "
        "product type, material, shape, color, and dominant visual features. "
        "Use natural English suitable for Amazon/eBay listing images.")
    if name:
        user_text += (
            f"\nNote: this product is known as '{name}'. Use this name to correctly "
            f"identify the product type, but still describe ONLY visible visual "
            f"features objectively — do not invent details not in the image.")
    for (url, model, key_env) in endpoints:
        k = _key_for(key_env, key)
        headers = {"Authorization": f"Bearer {k}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": (
                    "You are an e-commerce image ALT text specialist for cross-border "
                    "POD products. Write concise, accurate, SEO-friendly English ALT text "
                    "(under 125 characters). Focus on: product type, material, shape, "
                    "color, texture, and key visual features.")},
                {"role": "user", "content": [
                    {"type": "text", "text": user_text},
                    {"type": "image_url", "image_url": {"url": data_uri}},
                ]},
            ],
            "max_tokens": 800,
            "temperature": 0.3,
        }
        print(f"  → endpoint: {url} (model {model})", file=sys.stderr)
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=90)
        except requests.RequestException as e:
            print(f"  ↳ network error: {e} → failover", file=sys.stderr)
            continue
        if resp.status_code == 200:
            return resp.json()
        if resp.status_code in (500, 502, 503, 504):
            print(f"  ↳ HTTP {resp.status_code} degraded → failover",
                  file=sys.stderr)
            continue
        if resp.status_code in (401, 403):
            print("  ↳ auth error:", resp.text[:200], "→ failover", file=sys.stderr)
            continue
        print(f"  ↳ HTTP {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
        continue
    print("Agnes API 错误: 所有 endpoint 均失败", file=sys.stderr)
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(
        description="Agnes 2.0 Flash ALT 文本生成（base64 内联）")
    ap.add_argument("--image", "-i", required=True,
                    help="输入图片路径（支持 JPG/PNG/WebP）")
    ap.add_argument("--size", "-s", type=int, default=768,
                    choices=[256, 384, 512, 640, 768, 1024],
                    help="缩放到此边长内再送模型 [default: 768 推荐默认]")
    ap.add_argument("--output", "-o", default=None,
                    help="输出路径 [默认: stdout]")
    ap.add_argument("--name", "-n", default=None,
                    help="品名（可选，提升 ALT 产品类型识别准确度，如 '金毛异形暖手抱枕'）")

    args = ap.parse_args()

    if not Path(args.image).exists():
        print(f"Error: file not found: {args.image}", file=sys.stderr)
        sys.exit(1)

    # ---- 执行 ----
    print(f"[alt.py] Agnes 多模态 ALT 生成 (failover: .com → .cn)", file=sys.stderr)
    print(f"  图片: {args.image}  | 目标尺寸: {args.size}px", file=sys.stderr)

    if args.size in SIZE_RECS:
        print(f"  建议: {SIZE_RECS[args.size]}", file=sys.stderr)

    key = load_key()
    uri = downscale(Path(args.image), args.size)
    result = generate(key, uri, args.name)

    if "choices" not in result:
        print("Agnes API 错误:", json.dumps(result, ensure_ascii=False)[:500],
              file=sys.stderr)
        sys.exit(1)

    alt_text = result["choices"][0]["message"]["content"].strip()
    # 兜底：agnes-2.0-flash 为推理模型，max_tokens 不足时答案可能落在 reasoning_content
    # （末次 "Draft N:" 草稿行）。content 为空时回退提取，避免产出空白 ALT。
    if not alt_text:
        import re as _re
        rc = result["choices"][0]["message"].get("reasoning_content", "") or ""
        drafts = _re.findall(r"Draft\s+\d+:\s*(.+)", rc)
        alt_text = (drafts[-1].strip() if drafts else rc.strip())
    usage = result.get("usage", {})
    tok_total = usage.get("total_tokens", "?")
    tok_prompt = usage.get("prompt_tokens", "?")

    print(f"\n===== ALT 文本 =====\n{alt_text}\n", file=sys.stderr)
    print(f"  tokens: prompt={tok_prompt} total={tok_total}", file=sys.stderr)

    # ---- 输出 ----
    out_str = alt_text if args.output is None else ""
    if args.output is not None:
        Path(args.output).write_text(alt_text, encoding="utf-8")
        print(f"  已写入: {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
