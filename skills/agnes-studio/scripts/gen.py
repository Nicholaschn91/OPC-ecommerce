#!/usr/bin/env python3
"""
Agnes Image — 文生图 & 垫图生图
Models: agnes-image-2.1-flash (default, .com 与 .cn 同名)

Endpoint Failover（双域双令牌）:
  - 默认 .com (apihub.agnes-ai.com) 主用：海外/VPN 隧道可用时直连快；本机经 TUN/VPN 可达
  - .cn (api.agnes-ai.cn) 兜底：结果图床为 storage.googleapis.com，故 .cn 强制 b64_json 内联返回以避开 Google（国内无 VPN 被墙）
  - **双令牌**：.com 用 AGNES_API_KEY，.cn 用 AGNES_API_KEY_CN（未配置时回退 AGNES_API_KEY）。
    注意：两域凭据是用户两种代理环境各自的令牌，并非"同一把 key 两域通用"——
    failover 必须按域名用各自 key，否则兜底端点必 401。
  - 401/403 与网络/5xx 一样触发 failover：任一端点报错自动用另一个（用该域自己的 key）
  - 顺序可用 env 覆盖：AGNES_BASE_URL（主）/ AGNES_FALLBACK_URL（备）
  - 文档：https://www.agnes-ai.cn/zh-Hans/docs/agnes-image-21-flash
"""

import argparse
import base64
import json
import os
import random
import sys
import time
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ── Config ──────────────────────────────────────────────────────────────

# Endpoint 列表由 _build_endpoints() 动态构建（含 .cn 备份），见下方 API Call 段
DEFAULT_MODEL = "agnes-image-2.1-flash"
ALT_MODEL = "agnes-image-2.0-flash"
SKILL_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = SKILL_DIR / ".env"
USAGE_FILE = SKILL_DIR / ".agnes_usage.json"
_LAST_AUTH_ERROR = False  # 跨 endpoint 累计是否出现过 401/403，供 call_agnes 末态提示

SIZE_CHOICES = [
    # 1K (RPM=20)
    "1024x1024", "1024x768", "768x1024",
    # 2K (RPM=10) — 跨境电商主流
    "2048x2048", "2048x1536", "1536x2048",
    # 3K/4K (RPM=1) — 谨慎使用
    "3072x3072", "4096x4096",
]

# ── Preset prompts (--preset) ───────────────────────────────────────────
# Format: {"key": {"prompt": "...{var}...", "description": "..."}}
# {变量} 占位符通过 --vars product_name=法兰绒毛毯,material=棉 替换

PRESETS = {
    "lineart": {
        "prompt": (
            "Convert the product into a professional-grade black and white line art drawing. "
            "Use clear, smooth, closed black lines to accurately extract the subject outline, "
            "internal structure, and main patterns. Repair blurry, missing, or unreasonable "
            "details, ensuring complete structure and clear hierarchy. Pure white background, "
            "remove all color, grayscale, shadows, textures, and noise. "
            "Keep only clean, unambiguous line art. High resolution, best quality."
        ),
        "description": "产品转黑白线稿图"
    },
    "shaped-mousepad": {
        "prompt": (
            "主体设定：参考原图中的主体对象（只保留主体不要出现背景），将其转换成一个异形鼠标垫，"
            "轮廓形状与主体相似。"
            "产品工艺：产品展示图: 纯白色背景，展示了一款异形鼠标垫，鼠标垫表面印有图案，"
            "图案特征与主体一致，鼠标垫边缘印刷白色，鼠标垫表面平整（鼠标垫边缘与鼠标垫图一致），"
            "鼠标垫边缘为平整切口。"
            "场景/风格：亚马逊主图要求，纯白背景，整体构图为俯视特写,光线明亮，"
            "产品占据图片85%以上区域，清晰可见，无水印。商业摄影风格，8k 高清，比例1:1。"
        ),
        "description": "产品转异形鼠标垫"
    },
    "shaped-doll": {
        "prompt": (
            "主体设定：参考「商品主图原图（上传）」中的主体对象（只保留主体不要出现背景），"
            "将其转换成玩偶，全幅印花，玩偶符合实物逻辑。"
            "产品工艺：玩偶身材与四肢细长(全幅印花，印花图案与照片一致)，"
            "玩偶上全幅印刷着主体，调整主体的姿势以适配玩偶，带有自然的布料感，"
            "人偶整体应呈现饱满的 PP 棉填充效果，表面有轻微短毛绒质感。"
            "场景/风格：亚马逊主图要求，纯白背景，产品占据图片85%以上区域，"
            "清晰可见，无水印。商业摄影风格，8k 高清，比例1:1。"
        ),
        "description": "产品转玩偶（全幅印花+PP棉填充，需激活口令）",
        "default_image": "assets/doll-blank.png",
        "activation_key": "老鼠干",
    },
    "shaped-handwarmer": {
        "prompt": (
            "主体设定：参考上传图片中的主体对象（只保留主体头部，不要出现背景）"
            "细节特征与「商品主图原图（上传）」一致，"
            "将其转换成一个3D 实体异形暖手抱枕。"
            "产品工艺：暖手抱枕形状需严格遵循主体头部的轮廓。"
            "暖手抱枕边缘为白色，暖手抱枕造型参考「抱枕造型（复制）」。"
            "暖手抱枕整体应呈现饱满的 PP 棉填充效果，表面有轻微短毛绒质感。"
            "场景/风格：亚马逊主图要求，纯白背景，产品占据图片85%以上区域，"
            "清晰可见，无水印。商业摄影风格，8k 高清，比例1:1。"
            "特别注意：暖手抱枕一体成型，两边侧边中间有狭长开口。"
        ),
        "description": "产品转3D异形暖手抱枕（需激活口令）",
        "default_image": "assets/head-pillow.jpg",
        "activation_key": "头部",
    },

    # ── 站外引流预设（external-traffic）──────────────────────────────
    # 通用技法 + {变量}，不绑定具体商品。POD 线主打情感/揭示/真人感，
    # 激光雕刻线主打工艺质感/刻字对比。搭配 --image 垫图或纯文生图均可。
    "ad-reveal": {
        "prompt": (
            "Cinematic product reveal shot: a {source_photo} on a phone or tablet "
            "screen transforming into a real {product} in the customer's hands, "
            "the magical moment of a memory becoming a physical gift. "
            "Warm intimate lighting, soft bokeh background of {scene}, "
            "shallow depth of field, authentic e-commerce advertisement style, "
            "vertical composition, no text overlay, photorealistic, 8k."
        ),
        "description": "POD线·照片变实物揭示型（情感礼物王牌钩子）",
    },
    "ad-gift": {
        "prompt": (
            "Lifestyle photography: a happy {recipient} holding or receiving a "
            "{product} as a gift in a {scene}, genuine emotional reaction, "
            "warm festive or cozy atmosphere, {emotion} expression, "
            "soft natural light, candid authentic moment, "
            "high-conversion social ad style, vertical composition, "
            "no text, photorealistic, 8k."
        ),
        "description": "POD线·情感礼物场景",
    },
    "ad-ugc": {
        "prompt": (
            "User-generated-content style photo: a real person holding a {product} "
            "in a casual everyday setting, natural hand grip, slight imperfection, "
            "smartphone POV, authentic unfiltered look, bright indoor {scene} "
            "lighting, relatable and trustworthy, TikTok or Instagram ad aesthetic, "
            "vertical 9:16 composition, no text, photorealistic, 8k."
        ),
        "description": "POD线·真人手持真实感（UGC风）",
    },
    "ad-craft": {
        "prompt": (
            "Extreme close-up craftsmanship shot of a {product} made of {material}, "
            "showing fine laser-engraved detail and texture, premium tactile surface, "
            "dramatic directional lighting highlighting the engraving depth, "
            "luxury artisan feel, dark moody background, "
            "high-end product advertisement, square or vertical composition, "
            "no text, photorealistic, 8k."
        ),
        "description": "激光线·工艺质感特写",
    },
    "ad-engrave": {
        "prompt": (
            "A split-concept product shot: on one side a plain {material} {product}, "
            "on the other the same {product} with a precise laser-engraved "
            "{engraved_text} and custom logo, emphasizing personalization and "
            "permanence, clean studio lighting, before-and-after personalization "
            "story, premium customized gift vibe, vertical composition, "
            "no text, photorealistic, 8k."
        ),
        "description": "激光线·刻字瞬间/对比",
    },
}

# ── Free-tier rate-limit iron rules ─────────────────────────────────────
# 1. Concurrency: SERIAL (0) or MAX_N=2–3
# 2. Inter-request delay: 2–3 s minimum
# 3. 429 handling: pause 60 s then retry (up to max_retries)
# ────────────────────────────────────────────────────────────────────────
RPM_MAP = {1: 20, 2: 10, 3: 1, 4: 1}
MAX_DAILY = 4000

# ── Concurrency control ────────────────────────────────────────────────
# 0 = strictly serial (recommended for free tier)
# 1-3 = allow N concurrent API calls (uses ThreadPoolExecutor)
MAX_CONCURRENT = 0           # 铁律1: 默认串行执行

# ── Inter-request delay ────────────────────────────────────────────────
MIN_DELAY = 2.0              # 铁律2: 最小休眠 2s
MAX_DELAY = 3.0              # 铁律2: 最大休眠 3s

# ── 429 back-off ───────────────────────────────────────────────────────
RATE_LIMIT_WAIT = 60         # 铁律3: 429 后暂停 60s


def _size_tier(size: str) -> int:
    """Map size string to resolution tier (1K→1, 2K→2, 3K→3, 4K→4)."""
    w = int(size.split("x")[0])
    if w <= 1024: return 1
    if w <= 2048: return 2
    if w <= 3072: return 3
    return 4


def _inter_request_delay() -> float:
    """铁律2: 每次请求间休眠 2~3s（随机）。"""
    return random.uniform(MIN_DELAY, MAX_DELAY)


# ── Daily Limit Tracker ─────────────────────────────────────────────────

def _read_usage() -> dict:
    if USAGE_FILE.exists():
        try:
            return json.loads(USAGE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write_usage(data: dict):
    USAGE_FILE.write_text(json.dumps(data))


def check_daily_limit(batch_count: int):
    """Check and warn if batch would exceed daily limit."""
    today = date.today().isoformat()
    usage = _read_usage()
    used_today = usage.get(today, 0)

    if used_today + batch_count > MAX_DAILY:
        remaining = MAX_DAILY - used_today
        print(f"WARNING: Daily limit = {MAX_DAILY}, used = {used_today}, "
              f"remaining = {remaining}", file=sys.stderr)
        print(f"  Requested batch size ({batch_count}) exceeds remaining quota.",
              file=sys.stderr)
        response = input(f"  Continue with first {remaining} images? [y/N] ")
        if response.lower() != 'y':
            sys.exit(0)

    return today, used_today


def record_usage(count: int):
    """Increment today's usage counter."""
    today, _ = check_daily_limit(0)  # get today without batch check
    usage = _read_usage()
    usage[today] = usage.get(today, 0) + count
    # prune old entries
    usage = {k: v for k, v in usage.items() if k >= date.today().isoformat()}
    _write_usage(usage)


# ── Helpers ─────────────────────────────────────────────────────────────

def load_env(var: str) -> str:
    val = os.environ.get(var)
    if val:
        return val
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{var}="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if val and "your-" not in val.lower():
                        return val
    print(f"ERROR: {var} not found.", file=sys.stderr)
    print(f"  Set in environment or {ENV_FILE}", file=sys.stderr)
    print(f"  Get a key at: https://agnes-ai.com", file=sys.stderr)
    sys.exit(1)


def encode_image(path: str) -> str:
    p = Path(path)
    if not p.exists():
        print(f"ERROR: Image not found: {path}", file=sys.stderr)
        sys.exit(1)
    ext = p.suffix.lower()
    mime_map = {".png": "image/png", ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg", ".webp": "image/webp"}
    mime = mime_map.get(ext, "image/png")
    with open(p, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    return f"data:{mime};base64,{b64}"


# ── API Call ────────────────────────────────────────────────────────────

def _out_fmt_for(url: str, force_b64: bool) -> str:
    """国内 .cn 端点结果落在 storage.googleapis.com（Google，国内无 VPN 被墙），
    故 .cn 强制 b64_json 内联返回，彻底避开外部图床拉取。"""
    if force_b64 or "agnes-ai.cn" in url:
        return "b64_json"
    return "url"


def _key_env_for(base: str) -> str:
    """按域名返回应使用的 key 环境变量名。"""
    if base.rstrip("/") == "https://api.agnes-ai.cn/v1":
        return "AGNES_API_KEY_CN"
    return "AGNES_API_KEY"


def _key_for(env_name: str, fallback_key: str = None) -> str:
    """取指定域名的 key；.cn key 未配置时回退主 key（向后兼容单 key 场景）。"""
    try:
        return load_env(env_name)
    except SystemExit:
        if fallback_key:
            return fallback_key
        raise


def _build_endpoints(force_b64: bool = False) -> list:
    """构建 endpoint 列表 [(url, out_fmt), ...]。
    默认 .com 主用（海外/VPN 直连快），.cn 兜底（国内无 VPN 时 .com 被墙自动切）。
    可用 env 覆盖顺序：AGNES_BASE_URL（主）/ AGNES_FALLBACK_URL（备）。"""
    primary = os.environ.get("AGNES_BASE_URL",
                             "https://apihub.agnes-ai.com/v1").rstrip("/")
    fallback = os.environ.get("AGNES_FALLBACK_URL",
                             "https://api.agnes-ai.cn/v1").rstrip("/")
    seen = set()
    pairs = []
    for b in (primary, fallback):
        if b and b not in seen:
            seen.add(b)
            pairs.append((b, _key_env_for(b)))
    return [(b + "/images/generations", _out_fmt_for(b, force_b64), ke)
            for (b, ke) in pairs]


def _extract_bytes(result: dict, url: str):
    data = result.get("data") or []
    if not data:
        print(f"    >>> empty response from {url}", file=sys.stderr)
        return None
    entry = data[0]
    img_url = entry.get("url")
    if img_url:
        try:
            with urlopen(Request(img_url), timeout=120) as r:
                return r.read()
        except Exception as e:
            print(f"    WARNING: result URL fetch failed: {e}", file=sys.stderr)
    b64 = entry.get("b64_json")
    if b64:
        return base64.b64decode(b64)
    print("    >>> no image in response", file=sys.stderr)
    return None


def _post_with_retry(url, headers, payload, max_retries):
    """单 endpoint 重试：429 按铁律重试；网络/5xx → None 触发 failover；
    401/403 → 直接退出。返回图片 bytes 或 None。"""
    consecutive_429 = 0
    for attempt in range(max_retries + 1):
        if attempt > 0:
            wait = RATE_LIMIT_WAIT if consecutive_429 > 0 else min(2 ** attempt, 60)
            print(f"    [retry {attempt}/{max_retries}] wait {wait}s...",
                  file=sys.stderr)
            time.sleep(wait)
        req = Request(url, data=json.dumps(payload).encode(),
                      headers=headers, method="POST")
        try:
            with urlopen(req, timeout=360) as resp:
                return _extract_bytes(json.loads(resp.read().decode()), url)
        except HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code == 429:
                consecutive_429 += 1
                print(f"    >>> 429 Too Many Requests (#{consecutive_429}). "
                      f"Waiting {RATE_LIMIT_WAIT}s...", file=sys.stderr)
                if attempt < max_retries:
                    continue
                return None
            if e.code in (500, 502, 503, 504):
                print(f"    >>> HTTP {e.code} degraded → failover", file=sys.stderr)
                return None
            if e.code in (401, 403):
                print(f"    >>> HTTP {e.code} auth error: {body[:200]} "
                      f"→ failover", file=sys.stderr)
                global _LAST_AUTH_ERROR
                _LAST_AUTH_ERROR = True
                return None
            print(f"    >>> HTTP {e.code}: {body[:300]}", file=sys.stderr)
            if attempt < max_retries:
                continue
            return None
        except (URLError, ConnectionError) as e:
            print(f"    >>> network error: {getattr(e, 'reason', e)} → failover",
                  file=sys.stderr)
            return None
    return None


def call_agnes(api_key: str, model: str, payload: dict,
               max_retries: int = 3, endpoints: list = None) -> bytes:
    """铁律3: 429 自动暂停 60s 后重试；endpoint 网络/5xx 失败自动 failover 到下一备用。
    返回图片 bytes。response_format 按 endpoint 注入（.cn → b64_json 避 Google 图床）。"""
    endpoints = endpoints or _build_endpoints()
    global _LAST_AUTH_ERROR
    _LAST_AUTH_ERROR = False

    for ei, (url, out_fmt, key_env) in enumerate(endpoints, 1):
        k = _key_for(key_env, api_key)
        headers = {
            "Authorization": f"Bearer {k}",
            "Content-Type": "application/json",
        }
        attempt = dict(payload)
        attempt["model"] = model
        eb = dict(attempt.get("extra_body") or {})
        eb["response_format"] = out_fmt
        attempt["extra_body"] = eb
        attempt.pop("return_base64", None)

        print(f"  [endpoint {ei}/{len(endpoints)}] {url} "
              f"(response_format={out_fmt}, key={key_env})", file=sys.stderr)
        img = _post_with_retry(url, headers, attempt, max_retries)
        if img is not None:
            return img
        print(f"  ↳ endpoint {ei} failed, failing over...", file=sys.stderr)

    print("  ERROR: all endpoints failed.", file=sys.stderr)
    if _LAST_AUTH_ERROR:
        print("  HINT: 所有端点均返回 401/403 —— 请检查 AGNES_API_KEY 在双域是否有效。",
              file=sys.stderr)
    sys.exit(1)


# ── Single ──────────────────────────────────────────────────────────────

def generate_single(args, api_key: str, endpoints: list = None):
    payload = {
        "model": args.model,
        "prompt": args.prompt,
        "size": args.size,
    }
    if args.image:
        # 图生图: image 在 extra_body 内；response_format 由 call_agnes 按 endpoint 注入
        # (.cn 强制 b64_json 避开 Google 图床)
        payload["extra_body"] = {"image": args.image}

    print(f"Model: {args.model} | Size: {args.size} | Format: {args.format}")
    print(f"Prompt: {args.prompt[:80]}{'...' if len(args.prompt) > 80 else ''}")
    if args.image:
        print(f"Ref images: {len(args.image)}")

    image_bytes = call_agnes(api_key, args.model, payload, args.retries, endpoints)
    record_usage(1)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(image_bytes)
    print(f"Done! → {out_path.resolve()} ({len(image_bytes)/1024:.1f} KB)")


# ── Batch ───────────────────────────────────────────────────────────────

def _generate_one(args, api_key: str, prompt: str, index: int,
                  base_payload: dict, endpoints: list = None) -> tuple:
    """Generate a single image. Returns (success: bool, out_path: str, kb: float)."""
    stem = Path(args.output).stem
    suffix = Path(args.output).suffix or ".png"
    parent = Path(args.output).parent
    out = parent / f"{stem}_{index:03d}{suffix}"

    payload = dict(base_payload, prompt=prompt)

    try:
        img_bytes = call_agnes(api_key, args.model, payload, args.retries, endpoints)
        record_usage(1)
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(img_bytes)
        kb = len(img_bytes) / 1024
        return True, str(out), kb
    except SystemExit:
        return False, str(out), 0


def _worker_fn(task):
    """ThreadPoolExecutor worker wrapper."""
    return _generate_one(*task)


def generate_batch(args, api_key: str, endpoints: list = None):
    # Read prompts
    if args.batch == "-":
        lines = [l.strip() for l in sys.stdin
                 if l.strip() and not l.strip().startswith("#")]
    else:
        bp = Path(args.batch)
        if not bp.exists():
            print(f"ERROR: {args.batch} not found", file=sys.stderr)
            sys.exit(1)
        lines = [l.strip() for l in bp.read_text(encoding="utf-8").splitlines()
                 if l.strip() and not l.strip().startswith("#")]

    if not lines:
        print("ERROR: No prompts found.", file=sys.stderr)
        sys.exit(1)

    # Daily limit check
    check_daily_limit(len(lines))
    today, used = check_daily_limit(0)

    # 铁律1: 确定并发数
    max_workers = max(1, min(MAX_CONCURRENT, len(lines)))
    if max_workers == 1:
        mode_label = "SERIAL"
    else:
        mode_label = f"CONCURRENT (N={max_workers})"

    base_payload = {"model": args.model, "size": args.size}
    if args.image:
        # response_format 由 call_agnes 按 endpoint 注入（.cn → b64_json）
        base_payload["extra_body"] = {"image": args.image}

    success = 0
    fail = 0
    start = time.time()

    print(f"Batch: {len(lines)} prompts | Daily used: {used}/{MAX_DAILY}")
    print(f"Size: {args.size} | Mode: {mode_label} | Delay: {MIN_DELAY}-{MAX_DELAY}s")
    est_time = len(lines) * (_inter_request_delay() + 10)
    print(f"Est. time: ~{est_time//60:.0f}m {est_time%60:.0f}s")
    print("-" * 60)

    if max_workers == 1:
        # ── SERIAL mode (铁律1: 串行) ──
        for i, prompt in enumerate(lines, 1):
            elapsed = time.time() - start
            eta = (elapsed / max(i - 1, 1)) * (len(lines) - i + 1)
            print(f"\n[{i}/{len(lines)}] ETA {eta/60:.0f}m "
                  f"{prompt[:60]}{'...' if len(prompt) > 60 else ''}")

            ok, out, kb = _generate_one(args, api_key, prompt, i, base_payload)
            if ok:
                print(f"  → {out} ({kb:.1f} KB)")
                success += 1
            else:
                print(f"  → FAILED")
                fail += 1

            if i < len(lines):
                d = _inter_request_delay()
                print(f"  → delay {d:.1f}s")
                time.sleep(d)

    else:
        # ── CONCURRENT mode (铁律1: N并发，但每批内仍串行+延时) ──
        from concurrent.futures import ThreadPoolExecutor, as_completed

        # 分批处理：每批最多 max_workers 个任务，批间遵守延时
        batch_index = 0
        while batch_index < len(lines):
            batch = lines[batch_index:batch_index + max_workers]
            batch_num = batch_index // max_workers + 1

            # 构造任务列表
            tasks = [(args, api_key, prompt, idx + 1, base_payload, endpoints)
                     for idx, prompt in enumerate(batch)]

            # 并发执行本批
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {executor.submit(_worker_fn, t): idx
                           for idx, t in enumerate(tasks)}
                for future in as_completed(futures):
                    idx_in_batch = futures[future]
                    global_i = batch_index + idx_in_batch + 1
                    prompt_text = lines[global_i - 1][:60]
                    print(f"\n[{global_i}/{len(lines)}] {prompt_text}{'...' if len(lines[global_i-1]) > 60 else ''}")
                    try:
                        ok, out, kb = future.result()
                        if ok:
                            print(f"  → {out} ({kb:.1f} KB)")
                            success += 1
                        else:
                            print(f"  → FAILED")
                            fail += 1
                    except Exception as e:
                        print(f"  → ERROR: {e}")
                        fail += 1

            batch_index += max_workers

            # 批间延时（铁律2）
            if batch_index < len(lines):
                d = _inter_request_delay()
                print(f"\n  → batch delay {d:.1f}s")
                time.sleep(d)

    elapsed = time.time() - start
    print(f"\n{'=' * 60}")
    print(f"Done: {success}/{len(lines)} ok, {fail} fail, "
          f"{elapsed/60:.1f}m elapsed, daily used: {used + success}/{MAX_DAILY}")


# ── Main ────────────────────────────────────────────────────────────────

def main():
    global MAX_DAILY  # allow --max-daily override

    parser = argparse.ArgumentParser(
        description="Agnes Image — 文生图 & 垫图生图"
    )
    parser.add_argument("--prompt", help="图像描述 / 编辑指令")
    parser.add_argument("--preset", choices=list(PRESETS.keys()),
                        help=f"预设提示词: {', '.join(PRESETS.keys())}")
    parser.add_argument("--vars", metavar="K=V,...",
                        help="替换预设中的 {变量}，如 product_name=毛毯,material=棉")
    parser.add_argument("--unlock", metavar="KEY",
                        help="激活受保护预设的口令")
    parser.add_argument("--list-presets", action="store_true",
                        help="列出所有预设提示词并退出")
    parser.add_argument("--output", default="output.png")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        choices=[DEFAULT_MODEL, ALT_MODEL])
    parser.add_argument("--size", default="2048x2048", choices=SIZE_CHOICES)
    parser.add_argument("--image", action="append",
                        help="参考图 (可重复指定，本地路径自动转 base64)")
    parser.add_argument("--format", default="url", choices=["url", "b64"],
                        help="输出格式: url(默认) 或 b64")
    parser.add_argument("--retries", type=int, default=3,
                        help="最大重试次数")
    parser.add_argument("--concurrency", type=int, default=None,
                        help="并发数 (默认串行, 设1-3启用并发)")
    parser.add_argument("--max-daily", type=int, default=MAX_DAILY,
                        help=f"日限额 (默认 {MAX_DAILY})")
    parser.add_argument("--batch", metavar="FILE",
                        help="批量文件，一行一个 prompt，'-' = stdin")
    parser.add_argument("--usage", action="store_true",
                        help="查看今日用量")

    args = parser.parse_args()

    # 铁律1: 应用 --concurrency 覆盖
    if hasattr(args, 'concurrency') and args.concurrency is not None:
        MAX_CONCURRENT = max(0, min(args.concurrency, 3))

    # --list-presets
    if getattr(args, 'list_presets', False):
        for name, p in PRESETS.items():
            print(f"[{name}] {p['description']}")
            print(p['prompt'])
            print()
        sys.exit(0)

    # --preset: apply preset + substitute {vars} + merge with --prompt
    if getattr(args, 'preset', None):
        p = PRESETS[args.preset]
        base_prompt = p['prompt']

        # Activation key check
        if p.get("activation_key"):
            if not getattr(args, 'unlock', None):
                print(f"ERROR: preset '{args.preset}' requires --unlock <key>",
                      file=sys.stderr)
                sys.exit(1)
            if args.unlock != p["activation_key"]:
                print(f"ERROR: wrong unlock key for preset '{args.preset}'",
                      file=sys.stderr)
                sys.exit(1)
            print(f"Activated: {args.preset}")

        # Variable substitution from --vars
        if getattr(args, 'vars', None):
            for kv in args.vars.split(","):
                k, _, v = kv.partition("=")
                if k and v:
                    base_prompt = base_prompt.replace(f"{{{k}}}", v)

        if args.prompt:
            args.prompt = f"{base_prompt} {args.prompt}"
        else:
            args.prompt = base_prompt

    if args.usage:
        usage = _read_usage()
        today = date.today().isoformat()
        used = usage.get(today, 0)
        print(f"Today: {used}/{MAX_DAILY} images")
        print(f"Concurrency mode: SERIAL (0) | CONCURRENT 1-3 (铁律1)")
        print(f"Inter-request delay: {MIN_DELAY}-{MAX_DELAY}s (铁律2)")
        print(f"429 back-off: {RATE_LIMIT_WAIT}s automatic retry (铁律3)")
        sys.exit(0)

    if not args.batch and not args.prompt:
        print("ERROR: --prompt required (or --batch)", file=sys.stderr)
        sys.exit(1)

    if args.prompt and len(args.prompt) > 10000:
        print("ERROR: prompt > 10000 chars", file=sys.stderr)
        sys.exit(1)

    # Apply --max-daily override
    MAX_DAILY = args.max_daily

    api_key = load_env("AGNES_API_KEY")

    # Endpoint failover 列表（.com 主用 / .cn 兜底；--format b64 时全强制 b64）
    endpoints = _build_endpoints(force_b64=(args.format == "b64"))

    # Preset default_image (pre-loaded skill asset, added BEFORE user's --image)
    if getattr(args, 'preset', None):
        p = PRESETS[args.preset]
        if p.get("default_image"):
            preset_img = str(SKILL_DIR / p["default_image"])
            if not args.image:
                args.image = []
            args.image.insert(0, preset_img)  # preset image first, user's image second

    # Default reference image from .env (if --image not provided)
    if not args.image:
        default_img = os.environ.get("AGNES_DEFAULT_IMAGE")
        if not default_img and ENV_FILE.exists():
            with open(ENV_FILE) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("AGNES_DEFAULT_IMAGE="):
                        default_img = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
        if default_img:
            print(f"Using default reference: {default_img}")
            args.image = [default_img]

    # Encode local images
    if args.image:
        encoded = []
        for img in args.image:
            if img.startswith("http://") or img.startswith("https://"):
                encoded.append(img)
            else:
                print(f"Encoding: {img}")
                encoded.append(encode_image(img))
        args.image = encoded

    if args.batch:
        generate_batch(args, api_key, endpoints)
    else:
        generate_single(args, api_key, endpoints)


if __name__ == "__main__":
    main()
