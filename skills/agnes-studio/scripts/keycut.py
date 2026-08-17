#!/usr/bin/env python3
"""
Agnes Studio S4 — 键色抠图（确定性颜色阈值，无任何本地 ML 分割模型）

背景：本地 ML 抠图（rembg/BRIA/u2net）历史实测边缘质量不达标，已禁用。
本技能抠图路线 = 云端生成模型把主体放到纯色键色背景（gen.py 垫图）→ 本脚本做
确定性的颜色阈值转 alpha。边缘质量由云端模型决定，本脚本只做数学运算。

用法：
  python keycut.py --image 键色结果.png --output 透明底.png          # --key 默认 auto
  python keycut.py --image 键色结果.png --key FF00FF --tolerance 110 --despill

--key auto（默认）：从图像四周边缘环带自动检测键色（中位数取样 + 均匀性校验），
适用于生成模型输出的"近似绿幕"（实测 agnes 输出约 RGB(65,170,25) 而非纯 #00FF00）。
"""
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def hex_to_rgb(h: str):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def detect_key_color(arr: np.ndarray, border_ratio: float = 0.04):
    """从图像边缘环带检测键色。返回 (key_rgb_float, 边缘均匀性std)。

    假设主体不贴边（键色 prompt 已要求主体居中留边）。
    """
    h, w, _ = arr.shape
    t = max(2, int(min(h, w) * border_ratio))
    border = np.concatenate([
        arr[:t, :, :].reshape(-1, 3),
        arr[-t:, :, :].reshape(-1, 3),
        arr[:, :t, :].reshape(-1, 3),
        arr[:, -t:, :].reshape(-1, 3),
    ]).astype(np.float32)
    key = np.median(border, axis=0)
    std = float(border.std(axis=0).mean())
    return key, std


def keycut(img: Image.Image, key_rgb: tuple, tolerance: float,
           feather: int, despill: bool) -> Image.Image:
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)
    kr, kg, kb = key_rgb

    dist = np.sqrt(np.sum((arr - np.array([kr, kg, kb], dtype=np.float32)) ** 2,
                          axis=2))

    # alpha 斜坡：inner 之内全透明，outer 之外全不透明
    inner = tolerance * 0.55
    outer = tolerance * 1.15
    alpha = np.clip((dist - inner) / max(outer - inner, 1e-6), 0.0, 1.0) * 255.0
    alpha = alpha.astype(np.uint8)

    # 轻度羽化（只作用于 alpha 通道）
    if feather > 0:
        alpha_img = Image.fromarray(alpha, mode="L").filter(
            ImageFilter.GaussianBlur(radius=feather / 2))
        alpha = np.asarray(alpha_img)

    rgb = arr.astype(np.float32)

    # 去键色溢出（despill）：半透明边缘像素中，键色通道不得高于其余两通道的较大值
    if despill:
        edge = (alpha > 8) & (alpha < 247)
        if key_rgb[1] >= key_rgb[0] and key_rgb[1] >= key_rgb[2]:  # 绿幕
            limit = np.maximum(rgb[..., 0], rgb[..., 2])
            rgb[..., 1] = np.where(edge, np.minimum(rgb[..., 1], limit), rgb[..., 1])
        elif key_rgb[0] >= key_rgb[1] and key_rgb[0] >= key_rgb[2]:  # 红/品红幕
            limit = np.maximum(rgb[..., 1], rgb[..., 2])
            rgb[..., 0] = np.where(edge, np.minimum(rgb[..., 0], limit), rgb[..., 0])
        else:  # 蓝幕
            limit = np.maximum(rgb[..., 0], rgb[..., 1])
            rgb[..., 2] = np.where(edge, np.minimum(rgb[..., 2], limit), rgb[..., 2])

    out = np.dstack([rgb.astype(np.uint8), alpha])
    return Image.fromarray(out, mode="RGBA")


def main():
    ap = argparse.ArgumentParser(description="键色抠图（确定性，无 ML）")
    ap.add_argument("--image", "-i", required=True, help="键色背景图（云端生成结果）")
    ap.add_argument("--output", "-o", default=None, help="输出路径（默认 {原名}_cutout.png）")
    ap.add_argument("--key", default="auto",
                    help="键色 hex（如 00FF00）或 auto=自动检测边缘键色，默认 auto")
    ap.add_argument("--tolerance", type=float, default=90.0,
                    help="键色容差（RGB 欧氏距离），默认 90；边缘泛键色时调大")
    ap.add_argument("--feather", type=int, default=2, help="alpha 羽化像素，默认 2")
    ap.add_argument("--despill", action="store_true",
                    help="去除半透明边缘的键色溢出")
    ap.add_argument("--preview", default=None,
                    help="可选：输出棋盘格/白底预览图路径")
    args = ap.parse_args()

    src = Path(args.image)
    if not src.exists():
        sys.exit(f"ERROR: 文件不存在: {src}")

    img = Image.open(src)
    w, h = img.size
    arr = np.asarray(img.convert("RGB"), dtype=np.float32)

    detected_key = None
    if args.key.lower() == "auto":
        key_rgb_f, border_std = detect_key_color(arr)
        detected_key = [int(round(v)) for v in key_rgb_f]
        key_rgb = tuple(detected_key)
        key_label = (f"auto 检测到 RGB{tuple(detected_key)} "
                     f"(边缘均匀性std={border_std:.1f})")
        if border_std > 40:
            print(f"WARNING: 边缘颜色不均匀 (std={border_std:.0f})，"
                  "背景可能不是纯色键色，结果可能不可靠；"
                  "可显式指定 --key 重试", file=sys.stderr)
    else:
        key_rgb = hex_to_rgb(args.key)
        key_label = f"#{args.key.upper()}"

    print(f"输入: {src} ({w}x{h}) | 键色 {key_label} | "
          f"tolerance={args.tolerance} feather={args.feather} "
          f"despill={args.despill}", file=sys.stderr)

    result = keycut(img, key_rgb, args.tolerance, args.feather, args.despill)

    # 统计
    alpha = np.asarray(result)[..., 3]
    opaque_ratio = float(np.mean(alpha > 240))
    transparent_ratio = float(np.mean(alpha < 15))
    print(f"不透明像素占比 {opaque_ratio:.1%} | 全透明占比 {transparent_ratio:.1%}",
          file=sys.stderr)
    if opaque_ratio > 0.95:
        print("WARNING: 几乎全图不透明，键色阈值可能未命中（考虑调大 --tolerance "
              "或换 --key）", file=sys.stderr)
    if transparent_ratio > 0.99:
        print("WARNING: 几乎全图透明，主体可能被吃掉（考虑调小 --tolerance）",
              file=sys.stderr)

    out = Path(args.output) if args.output else src.with_name(src.stem + "_cutout.png")
    result.save(out)
    print(f"输出: {out} ({out.stat().st_size / 1024:.1f} KB)", file=sys.stderr)

    if args.preview:
        bg = Image.new("RGB", result.size, (255, 255, 255))
        bg.paste(result, mask=result.split()[3])
        bg.save(args.preview)
        print(f"预览: {args.preview}", file=sys.stderr)

    # stdout 输出 JSON 摘要，便于上游解析
    import json
    print(json.dumps({
        "output": str(out.resolve()),
        "size": [w, h],
        "detected_key": detected_key,
        "opaque_ratio": round(opaque_ratio, 4),
        "transparent_ratio": round(transparent_ratio, 4),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
