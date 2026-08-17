#!/usr/bin/env python3
"""
Agnes Studio S9 — 元素提取（剪影 / 爪印 / 手写字）

输入必须是带 alpha 通道的透明底 PNG（通常来自 S4 云端抠图产出）。
硬约束：禁止本地 ML 分割模型（rembg/BRIA/u2net，历史实测不达标）；
本脚本只做 alpha 通道与颜色的确定性运算。

用法：
  python element_extract.py --image 透明底.png --type silhouette --output 剪影.png
  python element_extract.py --image 透明底.png --type paw_print --output 爪印.png
  python element_extract.py --image 透明底.png --type handwriting --threshold 128
"""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def load_rgba(path: Path) -> Image.Image:
    img = Image.open(path)
    if img.mode != "RGBA":
        sys.exit(f"ERROR: {path.name} 没有 alpha 通道（模式 {img.mode}）。"
                 "请先用 S4 云端抠图产出透明底 PNG。禁止用本地 ML 抠图替代。")
    return img


def extract_silhouette(img: Image.Image, smooth: int) -> Image.Image:
    """主体 alpha → 填黑剪影。"""
    alpha = img.split()[3]
    if smooth > 0:
        alpha = alpha.filter(ImageFilter.MedianFilter(smooth if smooth % 2 else smooth + 1))
    black = Image.new("RGB", img.size, (0, 0, 0))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(black, mask=alpha)
    out.putalpha(alpha)
    return out


def extract_paw_print(img: Image.Image, pad_dark_threshold: float = 0.75,
                      smooth: int = 3) -> Image.Image:
    """在透明底主体上按 alpha + 深色聚类取肉垫区域 → 单色剪影。

    原理：爪印肉垫通常比毛色更深（明度更低）。取主体内明度低于
    (主体中位明度 * pad_dark_threshold) 的连通深色区域作为爪印。
    失败场景（肉垫与毛色接近）→ 退出并提示改用 silhouette。
    """
    arr = np.asarray(img)
    rgb = arr[..., :3].astype(np.float32)
    alpha = arr[..., 3]
    mask = alpha > 128

    if not mask.any():
        sys.exit("ERROR: 图像中没有不透明主体。")

    luma = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2])
    median_luma = float(np.median(luma[mask]))
    dark_mask = mask & (luma < median_luma * pad_dark_threshold)

    ratio = float(dark_mask.sum() / mask.sum())
    if ratio < 0.005:
        sys.exit(f"ERROR: 深色区域占比 {ratio:.2%} 过低，未检出爪印候选。"
                 "可能肉垫颜色与毛色接近，请改用 --type silhouette 或人工指定 mask。")
    if ratio > 0.6:
        sys.exit(f"ERROR: 深色区域占比 {ratio:.2%} 过高，主体本身偏暗，"
                 "爪印聚类不可靠。请人工指定 mask 或改用 silhouette。")

    # 去除孤立噪点（3x3 开运算近似）
    dm_img = Image.fromarray((dark_mask * 255).astype(np.uint8), mode="L")
    if smooth > 0:
        dm_img = dm_img.filter(ImageFilter.MedianFilter(smooth if smooth % 2 else smooth + 1))
    dm = np.asarray(dm_img) > 128

    black = Image.new("RGB", img.size, (0, 0, 0))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    alpha_out = Image.fromarray((dm * 255).astype(np.uint8), mode="L")
    out.paste(black, mask=alpha_out)
    out.putalpha(alpha_out)
    print(f"爪印检出：深色区域占主体 {ratio:.1%}（中位明度 {median_luma:.0f}）",
          file=sys.stderr)
    return out


def extract_handwriting(img: Image.Image, threshold: int = 128) -> Image.Image:
    """灰度阈值二值化 → 按 alpha 去底。深色笔画视为文字。"""
    arr = np.asarray(img)
    rgb = arr[..., :3].astype(np.float32)
    alpha = arr[..., 3]
    luma = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2])
    ink = (alpha > 128) & (luma < threshold)
    if not ink.any():
        sys.exit(f"ERROR: 阈值 {threshold} 下未检出笔画，试试调高 --threshold。")
    ink_img = Image.fromarray((ink * 255).astype(np.uint8), mode="L")
    black = Image.new("RGB", img.size, (0, 0, 0))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(black, mask=ink_img)
    out.putalpha(ink_img)
    return out


def make_preview(out_img: Image.Image) -> Image.Image:
    """白底预览。"""
    bg = Image.new("RGB", out_img.size, (255, 255, 255))
    bg.paste(out_img, mask=out_img.split()[3])
    return bg


def main():
    ap = argparse.ArgumentParser(description="S9 元素提取（确定性，无 ML）")
    ap.add_argument("--image", "-i", required=True, help="透明底 PNG（S4 产出）")
    ap.add_argument("--type", "-t", required=True,
                    choices=["silhouette", "paw_print", "handwriting"])
    ap.add_argument("--output", "-o", default=None)
    ap.add_argument("--smooth", type=int, default=3, help="边缘平滑核大小，默认 3")
    ap.add_argument("--threshold", type=int, default=128,
                    help="handwriting 二值化阈值，默认 128")
    ap.add_argument("--pad-dark", type=float, default=0.75,
                    help="paw_print 深色判定系数，默认 0.75")
    args = ap.parse_args()

    src = Path(args.image)
    if not src.exists():
        sys.exit(f"ERROR: 文件不存在: {src}")

    img = load_rgba(src)
    print(f"输入: {src} ({img.size[0]}x{img.size[1]}) | 类型: {args.type}",
          file=sys.stderr)

    if args.type == "silhouette":
        result = extract_silhouette(img, args.smooth)
    elif args.type == "paw_print":
        result = extract_paw_print(img, args.pad_dark, args.smooth)
    else:
        result = extract_handwriting(img, args.threshold)

    out = Path(args.output) if args.output else \
        src.with_name(f"{src.stem}_{args.type}.png")
    result.save(out)
    preview_path = out.with_name(out.stem + "_preview.png")
    make_preview(result).save(preview_path)

    print(f"输出: {out} | 预览: {preview_path}", file=sys.stderr)
    print(json.dumps({
        "type": args.type,
        "output": str(out.resolve()),
        "preview": str(preview_path.resolve()),
        "size": list(result.size),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
