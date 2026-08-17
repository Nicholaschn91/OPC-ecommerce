#!/usr/bin/env python3
"""
Agnes Video V2.0 — 文生视频 / 图生视频 / 关键帧动画
模型: agnes-video-v2.0

免费用户铁律:
1. 控制并发: 默认串行
2. 增加延时: 每次请求间休眠 2~3s
3. 429 重试: 自动暂停 60s 后重试
"""

import argparse
import json
import os
import random
import sys
import time
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import base64

# ── Config ──────────────────────────────────────────────────────────────

CREATE_ENDPOINT = "https://apihub.agnes-ai.com/v1/videos"
# 推荐方式: 用 video_id 查询
RESULT_ENDPOINT_TEMPLATE = "https://apihub.agnes-ai.com/agnesapi?video_id={}"

DEFAULT_MODEL = "agnes-video-v2.0"
SKILL_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = SKILL_DIR / ".env"
USAGE_FILE = SKILL_DIR / ".agnes_video_usage.json"

# ── Free-tier rate-limit iron rules ─────────────────────────────────────
MAX_CONCURRENT = 0
MIN_DELAY = 2.0
MAX_DELAY = 3.0
RATE_LIMIT_WAIT = 60

# ── Video parameters ───────────────────────────────────────────────────
# num_frames must follow 8n+1 and <= 441
FRAME_RATE_DEFAULT = 24
# Recommended frames for common durations
FRAME_OPTIONS = {
    "3":  (81, FRAME_RATE_DEFAULT),
    "5":  (121, FRAME_RATE_DEFAULT),
    "10": (241, FRAME_RATE_DEFAULT),
    "18": (441, FRAME_RATE_DEFAULT),
}
DURATION_MAP = {k: v for k, v in FRAME_OPTIONS.items()}

# Resolution presets
RESOLUTION_PRESETS = {
    "480p":  (854, 480),
    "720p":  (1280, 720),
    "1080p": (1920, 1080),
    # Aspect ratio presets (width x height)
    "16:9":  (1280, 720),
    "9:16":  (720, 1280),
    "1:1":   (768, 768),
    "4:3":   (1024, 768),
    "3:4":   (768, 1024),
    # Manual
    "1280x720":   (1280, 720),
    "720x1280":   (720, 1280),
    "1024x1024":  (1024, 1024),
    "1152x768":   (1152, 768),
    "768x1152":   (768, 1152),
}


# ── Helpers ─────────────────────────────────────────────────────────────

def _inter_request_delay() -> float:
    """铁律2: 每次请求间休眠 2~3s（随机）。"""
    return random.uniform(MIN_DELAY, MAX_DELAY)


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
    sys.exit(1)


# ── Image reference resolver ──────────────────────────────────────
_EXT_MIME = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp",
}


def resolve_image_ref(ref: str | None) -> str | None:
    """Normalize an image reference for the API payload.

    - http(s):// or data: URI -> passed through unchanged
    - local file path (exists) -> read + base64 data URI (API accepts inline)
    - anything else -> returned as-is with a warning (best-effort)
    """
    if not ref:
        return ref
    if ref.startswith(("http://", "https://", "data:")):
        return ref
    p = Path(ref)
    if p.exists():
        mime = _EXT_MIME.get(p.suffix.lower(), "image/png")
        b64 = base64.b64encode(p.read_bytes()).decode()
        return f"data:{mime};base64,{b64}"
    print(f"WARNING: --image/--keyframes value is not a URL/data-URI nor an "
          f"existing file: {ref[:60]}", file=sys.stderr)
    return ref


# ── API: Create Task ───────────────────────────────────────────────────

def create_video_task(api_key: str, model: str, payload: dict,
                      max_retries: int = 3) -> dict:
    """创建视频生成任务。返回完整响应 JSON。"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    consecutive_429 = 0

    for attempt in range(max_retries + 1):
        if attempt > 0:
            if consecutive_429 > 0:
                wait = RATE_LIMIT_WAIT
            else:
                wait = min(2 ** attempt, 60)
            print(f"  [Retry {attempt}/{max_retries}] waiting {wait}s...",
                  file=sys.stderr)
            time.sleep(wait)

        req = Request(CREATE_ENDPOINT, data=json.dumps(payload).encode(),
                      headers=headers, method="POST")

        try:
            with urlopen(req, timeout=360) as resp:
                result = json.loads(resp.read().decode())
                record_video_usage(1)
                return result
        except HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code == 429:
                consecutive_429 += 1
                print(f"  >>> 429 Too Many Requests (#{consecutive_429}). "
                      f"Waiting {RATE_LIMIT_WAIT}s...", file=sys.stderr)
                if attempt < max_retries:
                    continue
                print(f"  >>> Max retries after {consecutive_429}x 429.",
                      file=sys.stderr)
                sys.exit(1)
            elif e.code == 503:
                consecutive_429 = 0
                print(f"  >>> 503 Service Unavailable. Waiting 10s...",
                      file=sys.stderr)
                time.sleep(10)
                if attempt < max_retries:
                    continue
                print(f"  ERROR: HTTP {e.code} — {body[:300]}",
                      file=sys.stderr)
                sys.exit(1)
            elif e.code == 400:
                consecutive_429 = 0
                print(f"  ERROR: HTTP 400 — {body[:500]}", file=sys.stderr)
                sys.exit(1)
            elif e.code == 401:
                print(f"  ERROR: HTTP 401 Unauthorized. Check API Key.",
                      file=sys.stderr)
                sys.exit(1)
            else:
                consecutive_429 = 0
                print(f"  ERROR: HTTP {e.code} — {body[:300]}", file=sys.stderr)
                if attempt < max_retries:
                    continue
                sys.exit(1)
        except URLError as e:
            consecutive_429 = 0
            print(f"  ERROR: Network — {e.reason}", file=sys.stderr)
            if attempt < max_retries:
                continue
            sys.exit(1)

    sys.exit(1)


# ── API: Poll Result ──────────────────────────────────────────────────

def poll_video_result(video_id: str, api_key: str,
                      max_wait: int = 600, poll_interval: int = 5) -> dict:
    """轮询视频生成结果，直到 completed/failed。"""
    url = RESULT_ENDPOINT_TEMPLATE.format(video_id)
    consecutive_429 = 0
    last_status_printed = ""

    for attempt in range(max_wait // poll_interval + 1):
        if attempt > 0:
            d = max(poll_interval, _inter_request_delay())
            print(f"  ⏳ 等待 {d:.0f}s... ({attempt*poll_interval}s/{max_wait}s)",
                  file=sys.stderr)
            time.sleep(d)

        req = Request(url, headers={"Authorization": f"Bearer {api_key}"})
        try:
            with urlopen(req, timeout=120) as resp:
                result = json.loads(resp.read().decode())
                consecutive_429 = 0

                status = result.get("status", "")
                progress = result.get("progress", 0)
                # 去重：只有状态变化时才打印
                status_key = f"{status}:{progress}"
                if status_key != last_status_printed:
                    print(f"  Status: {status} | Progress: {progress}%")
                    last_status_printed = status_key

                if status == "completed":
                    return result
                elif status == "failed":
                    err = result.get("error") or "Unknown error"
                    print(f"  ERROR: Task failed — {err}", file=sys.stderr)
                    sys.exit(1)
                elif status in ("queued", "in_progress"):
                    continue
                else:
                    continue

        except HTTPError as e:
            body = e.read().decode(errors="replace")
            if e.code == 429:
                consecutive_429 += 1
                print(f"  >>> 429 on poll. Waiting {RATE_LIMIT_WAIT}s...",
                      file=sys.stderr)
                time.sleep(RATE_LIMIT_WAIT)
                continue
            elif e.code == 503:
                print(f"  >>> 503 Service Unavailable, waiting 10s...",
                      file=sys.stderr)
                time.sleep(10)
                continue
            elif e.code == 404:
                print(f"  >>> 404 (still processing), continuing...",
                      file=sys.stderr)
                continue
            else:
                print(f"  ERROR: HTTP {e.code} — {body[:300]}",
                      file=sys.stderr)
                sys.exit(1)
        except URLError as e:
            print(f"  ERROR: Network — {e.reason}", file=sys.stderr)
            time.sleep(poll_interval)
            continue

    print(f"ERROR: Timeout after {max_wait}s.", file=sys.stderr)
    sys.exit(1)


# ── Download Video ────────────────────────────────────────────────────

def download_video(url: str, output_path: str, max_retries: int = 3):
    """下载视频文件。"""
    consecutive_429 = 0
    for attempt in range(max_retries + 1):
        if attempt > 0:
            wait = RATE_LIMIT_WAIT if consecutive_429 > 0 else min(2 ** attempt, 60)
            print(f"  [Download Retry {attempt}/{max_retries}] waiting {wait}s...",
                  file=sys.stderr)
            time.sleep(wait)

        req = Request(url)
        try:
            with urlopen(req, timeout=360) as resp:
                data = resp.read()
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_bytes(data)
                print(f"  Downloaded: {output_path} ({len(data)/1024/1024:.1f} MB)")
                return
        except HTTPError as e:
            if e.code == 429:
                consecutive_429 += 1
                print(f"  >>> 429 on download.", file=sys.stderr)
                continue
            else:
                print(f"  ERROR: Download HTTP {e.code}", file=sys.stderr)
                if attempt < max_retries:
                    continue
                sys.exit(1)
        except Exception as e:
            print(f"  ERROR: Download — {e}", file=sys.stderr)
            if attempt < max_retries:
                continue
            sys.exit(1)
    sys.exit(1)


# ── Daily Usage Tracker ───────────────────────────────────────────────

def _read_usage() -> dict:
    if USAGE_FILE.exists():
        try:
            return json.loads(USAGE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def _write_usage(data: dict):
    USAGE_FILE.write_text(json.dumps(data))


def record_video_usage(count: int = 1):
    today = date.today().isoformat()
    usage = _read_usage()
    usage[today] = usage.get(today, 0) + count
    usage = {k: v for k, v in usage.items() if k >= date.today().isoformat()}
    _write_usage(usage)


# ── Build Payload ─────────────────────────────────────────────────────

def build_payload(args) -> dict:
    """根据命令行参数构建 API payload。"""
    payload = {
        "model": args.model,
        "prompt": args.prompt,
    }

    # Duration -> num_frames + frame_rate
    if args.duration in DURATION_MAP:
        nf, fr = DURATION_MAP[args.duration]
        payload["num_frames"] = nf
        payload["frame_rate"] = fr
    else:
        payload["num_frames"] = args.num_frames
        payload["frame_rate"] = args.frame_rate

    # Resolution
    if args.resolution in RESOLUTION_PRESETS:
        w, h = RESOLUTION_PRESETS[args.resolution]
        payload["width"] = w
        payload["height"] = h
    elif "x" in args.resolution:
        w, h = args.resolution.split("x")
        payload["width"] = int(w)
        payload["height"] = int(h)
    else:
        # Default: 720p landscape
        payload["width"] = 1280
        payload["height"] = 720

    # Image for img2vid (图生视频) — 顶层 image 字段
    if args.image and not args.keyframes:
        payload["image"] = resolve_image_ref(args.image)

    # Negative prompt
    if args.negative_prompt:
        payload["negative_prompt"] = args.negative_prompt

    # Seed
    if args.seed is not None:
        payload["seed"] = args.seed

    # Inference steps
    if args.inference_steps:
        payload["num_inference_steps"] = args.inference_steps

    # Keyframe mode (关键帧动画) — extra_body
    if args.keyframes:
        if args.image:
            print("WARNING: --image and --keyframes are mutually exclusive. "
                  "Using --keyframes mode.", file=sys.stderr)
        payload["mode"] = "keyframes"
        payload["extra_body"] = {
            "mode": "keyframes",
            "image": [resolve_image_ref(k) for k in args.keyframes],
        }

    return payload


# ── Main workflow ─────────────────────────────────────────────────────

def generate_video(args, api_key: str):
    """文生视频 / 图生视频 / 关键帧动画 主流程。"""
    payload = build_payload(args)

    print(f"Model: {payload['model']}")
    print(f"Prompt: {payload['prompt'][:80]}{'...' if len(payload['prompt']) > 80 else ''}")
    print(f"Resolution: {payload.get('width')}x{payload.get('height')}")
    print(f"Frames: {payload.get('num_frames')} @ {payload.get('frame_rate')}fps")
    if "image" in payload and not args.keyframes:
        im = payload["image"]
        print(f"Input image: {im[:60]}{'...' if len(im) > 60 else ''}")
    if args.keyframes:
        print(f"Keyframes: {len(args.keyframes)}")
    if args.negative_prompt:
        print(f"Negative prompt: {args.negative_prompt[:60]}...")
    if args.seed is not None:
        print(f"Seed: {args.seed}")

    # Step 1: 创建任务
    print("\n[Step 1] Creating video task...")
    task_result = create_video_task(api_key, args.model, payload, args.retries)

    task_id = task_result.get("task_id") or task_result.get("id", "")
    video_id = task_result.get("video_id", "")
    status = task_result.get("status", "")
    size = task_result.get("size", "")
    seconds = task_result.get("seconds", "")

    print(f"\nTask created!")
    print(f"  task_id:  {task_id}")
    print(f"  video_id: {video_id}")
    print(f"  status:   {status}")
    print(f"  size:     {size}")
    print(f"  duration: {seconds}s")

    if not video_id:
        print("ERROR: No video_id in response.", file=sys.stderr)
        sys.exit(1)

    # Step 2: 轮询结果
    print(f"\n[Step 2] Polling for completion (max {args.max_wait}s)...")
    result = poll_video_result(
        video_id, api_key,
        max_wait=args.max_wait,
        poll_interval=args.poll_interval,
    )

    video_url = result.get("url")
    if not video_url:
        print("ERROR: No video URL in result.", file=sys.stderr)
        sys.exit(1)

    print(f"\nVideo ready: {video_url}")

    # Step 3: 下载
    if args.download:
        print(f"\n[Step 3] Downloading video...")
        out_path = args.output
        download_video(video_url, out_path, args.retries)
    else:
        print(f"\nVideo URL saved to: {args.output}")
        Path(args.output).write_text(video_url)


# ── Main ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Agnes Video V2.0 — 文生视频 / 图生视频 / 关键帧动画"
    )
    parser.add_argument("--prompt", help="视频内容的文本描述")
    parser.add_argument("--output", default="output.mp4",
                        help="输出文件路径（--download 时为视频文件，否则为 URL 文本）")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"模型名称 (默认 {DEFAULT_MODEL})")
    parser.add_argument("--duration", choices=list(DURATION_MAP.keys()),
                        default="5",
                        help="视频时长: 3s(81帧), 5s(121帧), 10s(241帧), 18s(441帧)")
    parser.add_argument("--resolution", default="1280x720",
                        help="分辨率: 480p/720p/1080p/16:9/9:16/1:1/4:3/3:4/WxH")
    parser.add_argument("--num-frames", type=int, default=None,
                        help="手动设置帧数 (必须 8n+1, <=441, 覆盖 --duration)")
    parser.add_argument("--frame-rate", type=int, default=None,
                        help="手动设置帧率 (覆盖 --duration)")
    parser.add_argument("--image",
                        help="图生视频: 输入图片（本地路径自动转 base64；也支持公网 URL 或 data URI）")
    parser.add_argument("--keyframes", action="append",
                        help="关键帧动画: 输入图片（本地路径自动转 base64；也支持 URL/data URI，可多次指定，与 --image 互斥)")
    parser.add_argument("--negative-prompt", dest="negative_prompt",
                        help="反向提示词")
    parser.add_argument("--seed", type=int, default=None,
                        help="随机种子 (可复现)")
    parser.add_argument("--inference-steps", type=int, dest="inference_steps",
                        help="推理步数")
    parser.add_argument("--retries", type=int, default=3,
                        help="最大重试次数")
    parser.add_argument("--max-wait", type=int, default=600,
                        help="轮询最大等待时间 (秒, 默认 600)")
    parser.add_argument("--poll-interval", type=int, default=5,
                        help="轮询间隔 (秒, 默认 5)")
    parser.add_argument("--download", action="store_true",
                        help="下载视频到本地")
    parser.add_argument("--usage", action="store_true",
                        help="查看今日用量")

    args = parser.parse_args()

    if args.usage:
        usage = _read_usage()
        today = date.today().isoformat()
        used = usage.get(today, 0)
        print(f"Today: {used} video-seconds generated")
        print(f"Iron rules: SERIAL | 2-3s delay | 429=60s retry")
        sys.exit(0)

    if not args.prompt:
        print("ERROR: --prompt required", file=sys.stderr)
        sys.exit(1)

    # Validate num_frames
    if args.num_frames is not None:
        if args.num_frames > 441:
            print("ERROR: num_frames must be <= 441", file=sys.stderr)
            sys.exit(1)
        if (args.num_frames - 1) % 8 != 0:
            print(f"WARNING: num_frames={args.num_frames} does not follow 8n+1 rule. "
                  f"Will be auto-normalized by API.", file=sys.stderr)

    api_key = load_env("AGNES_API_KEY")
    generate_video(args, api_key)


if __name__ == "__main__":
    main()
