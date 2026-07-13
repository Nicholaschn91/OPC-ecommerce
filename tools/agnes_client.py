#!/usr/bin/env python3
"""
Agnes AI Client — 供 Visual Agent 调用的图像/视频生成工具
用法：
  python agnes_client.py img2img --image-path x.png --prompt "xxx" --strength 0.7
  python agnes_client.py txt2img --prompt "xxx" --width 1024 --height 1024
  python agnes_client.py video --prompt "xxx" --image-path x.png --wait
  python agnes_client.py poll --task-id vid_xxxxx
"""

import os
import sys
import time
import base64
import argparse
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

# ──── Config ──────────────────────────────────────────────
AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
BASE_URL = os.environ.get("AGNES_BASE_URL", "https://api.agnes.ai")

if not AGNES_API_KEY:
    print("[WARN] AGNES_API_KEY not set in environment", file=sys.stderr)

HEADERS = {
    "Authorization": f"Bearer {AGNES_API_KEY}",
    "Content-Type": "application/json"
}

# ──── Helpers ─────────────────────────────────────────────
def image_to_data_uri(path: str) -> str:
    """读取本地图片 → Base64 Data URI"""
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    ext = Path(path).suffix.lower()
    mime = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp"
    }.get(ext, "image/png")
    return f"data:{mime};base64,{b64}"

def handle_429(func):
    """429 重试装饰器：睡 60s 重试一次"""
    def wrapper(*args, **kwargs):
        resp = func(*args, **kwargs)
        if resp.status_code == 429:
            print("⚠️ 429 Rate limited, sleeping 60s...", file=sys.stderr)
            time.sleep(60)
            resp = func(*args, **kwargs)
        return resp
    return wrapper

# ──── API Calls ───────────────────────────────────────────
@handle_429
def txt2img(prompt: str, negative_prompt: str = "", width: int = 1024, height: int = 1024,
            steps: int = 25, cfg_scale: float = 7.0, sampler: str = "euler_a",
            seed: int = -1, n: int = 1) -> Dict:
    """文生图"""
    payload = {
        "model": "agnes-image-2.1-flash",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg_scale": cfg_scale,
        "sampler": sampler,
        "seed": seed,
        "n": n
    }
    resp = requests.post(f"{BASE_URL}/v1/images/generations", headers=HEADERS, json=payload, timeout=60)
    return resp.json()

@handle_429
def img2img(prompt: str, image_path: str, negative_prompt: str = "", strength: float = 0.7,
            width: int = 1024, height: int = 1024, steps: int = 20, cfg_scale: float = 7.0) -> Dict:
    """图生图（接受本地图片路径，自动转 Base64 Data URI）"""
    data_uri = image_to_data_uri(image_path)
    payload = {
        "model": "agnes-image-2.1-flash",
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "image": data_uri,
        "strength": strength,
        "width": width,
        "height": height,
        "steps": steps,
        "cfg_scale": cfg_scale
    }
    resp = requests.post(f"{BASE_URL}/v1/images/generations", headers=HEADERS, json=payload, timeout=60)
    return resp.json()

@handle_429
def video_submit(prompt: str, image_path: str = None, end_image_path: str = None,
                 width: int = 1280, height: int = 720, num_frames: int = 16, fps: int = 8, seed: int = -1) -> Dict:
    """提交视频生成任务（异步）"""
    payload = {
        "model": "agnes-video-v2.0",
        "prompt": prompt,
        "width": width,
        "height": height,
        "num_frames": num_frames,
        "fps": fps,
        "seed": seed
    }
    if image_path:
        payload["image"] = image_to_data_uri(image_path)
    if end_image_path:
        payload["end_image"] = image_to_data_uri(end_image_path)
    
    resp = requests.post(f"{BASE_URL}/v1/videos", headers=HEADERS, json=payload, timeout=30)
    return resp.json()

def video_poll(task_id: str, interval: int = 10, timeout: int = 300) -> Dict:
    """轮询视频任务直到完成或超时"""
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(f"{BASE_URL}/v1/videos/{task_id}", headers=HEADERS, timeout=15)
        data = resp.json()
        status = data.get("status", "unknown")
        print(f"  [{time.time()-start:.0f}s] status: {status}", file=sys.stderr)
        if status == "succeeded":
            return data
        if status == "failed":
            raise RuntimeError(f"Video generation failed: {data.get('error')}")
        time.sleep(interval)
    raise TimeoutError(f"Video generation timeout after {timeout}s")


# ──── CLI ──────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Agnes AI Client")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # txt2img
    p1 = sub.add_parser("txt2img", help="文生图")
    p1.add_argument("--prompt", required=True)
    p1.add_argument("--negative-prompt", default="")
    p1.add_argument("--width", type=int, default=1024)
    p1.add_argument("--height", type=int, default=1024)
    p1.add_argument("--steps", type=int, default=25)
    p1.add_argument("--cfg", type=float, default=7.0)
    p1.add_argument("--sampler", default="euler_a")
    p1.add_argument("--seed", type=int, default=-1)
    p1.add_argument("--n", type=int, default=1)

    # img2img
    p2 = sub.add_parser("img2img", help="图生图")
    p2.add_argument("--prompt", required=True)
    p2.add_argument("--image-path", required=True)
    p2.add_argument("--negative-prompt", default="")
    p2.add_argument("--strength", type=float, default=0.7)
    p2.add_argument("--width", type=int, default=1024)
    p2.add_argument("--height", type=int, default=1024)
    p2.add_argument("--steps", type=int, default=20)
    p2.add_argument("--cfg", type=float, default=7.0)

    # video
    p3 = sub.add_parser("video", help="提交视频生成任务")
    p3.add_argument("--prompt", required=True)
    p3.add_argument("--image-path", help="起始帧图片路径（图生视频）")
    p3.add_argument("--end-image-path", help="结束帧图片路径（关键帧动画）")
    p3.add_argument("--width", type=int, default=1280)
    p3.add_argument("--height", type=int, default=720)
    p3.add_argument("--frames", type=int, default=16)
    p3.add_argument("--fps", type=int, default=8)
    p3.add_argument("--seed", type=int, default=-1)
    p3.add_argument("--wait", action="store_true", help="提交后自动轮询等待完成")

    # poll
    p4 = sub.add_parser("poll", help="轮询视频任务")
    p4.add_argument("--task-id", required=True)
    p4.add_argument("--interval", type=int, default=10)
    p4.add_argument("--timeout", type=int, default=300)

    args = parser.parse_args()

    try:
        if args.cmd == "txt2img":
            result = txt2img(args.prompt, args.negative_prompt, args.width, args.height,
                             args.steps, args.cfg, args.sampler, args.seed, args.n)
            print(result)
        elif args.cmd == "img2img":
            result = img2img(args.prompt, args.image_path, args.negative_prompt,
                             args.strength, args.width, args.height, args.steps, args.cfg)
            print(result)
        elif args.cmd == "video":
            result = video_submit(args.prompt, args.image_path, args.end_image_path,
                                  args.width, args.height, args.frames, args.fps, args.seed)
            print(result)
            if args.wait and result.get("task_id"):
                print("等待视频生成完成...", file=sys.stderr)
                result = video_poll(result["task_id"])
                print(result)
        elif args.cmd == "poll":
            result = video_poll(args.task_id, args.interval, args.timeout)
            print(result)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)