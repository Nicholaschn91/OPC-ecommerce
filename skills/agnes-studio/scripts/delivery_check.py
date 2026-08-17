#!/usr/bin/env python3
"""
Agnes Studio S13 — 印刷交付检查（纯检查，不生成图片）

检查项：分辨率 DPI（按目标印刷尺寸）、背景透明度、RGB/CMYK 提醒、
文字安全区（需 agent 提供文本层位置）、出血提醒。

用法：
  python delivery_check.py --input 成品.png
  python delivery_check.py --input 成品.png --target-width-mm 300 --cmyk --text-safety-mm 5
"""
import argparse
import json
import sys
from pathlib import Path

from PIL import Image


def check(input_path: Path, target_width_mm: float, require_cmyk: bool,
          text_layers: list, text_safety_mm: float) -> dict:
    img = Image.open(input_path)
    w, h = img.size

    # DPI：按目标印刷宽度计算（25.4mm = 1 inch）
    dpi = w / (target_width_mm / 25.4) if target_width_mm > 0 else None
    resolution_pass = dpi is not None and dpi >= 300

    # 背景透明度
    background = "image"
    if img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        alpha = rgba.getchannel("A")
        extrema = alpha.getextrema()
        if extrema[0] == 0:
            # 统计全透明像素占比判断是否"透明底"
            import numpy as np
            arr = np.asarray(alpha)
            transparent_ratio = float((arr < 15).mean())
            background = "transparent" if transparent_ratio > 0.05 else "solid"

    defects = []
    if dpi is not None and dpi < 300:
        defects.append(f"分辨率不足：{dpi:.0f} DPI < 300 DPI（目标印刷宽 "
                       f"{target_width_mm}mm），需先走 S5 放大")
    if require_cmyk and img.mode != "CMYK":
        defects.append("色彩模式为 RGB，实物印刷需转 CMYK；荧光色系转换后色偏明显，"
                       "建议准备替代色")
    if require_cmyk:
        defects.append("提醒：裁切类物料需留 3mm 出血（本脚本不自动检测出血，请人工确认）")

    # 文字安全区（可选）
    text_safety = None
    if text_layers:
        safe_ratio = text_safety_mm / target_width_mm if target_width_mm else 0.02
        violations = []
        for tl in text_layers:
            pos = tl.get("position", {})
            xr, yr = pos.get("x_ratio", 0.5), pos.get("y_ratio", 0.5)
            if min(xr, yr, 1 - xr, 1 - yr) < safe_ratio:
                violations.append(f"'{tl.get('content', '')[:15]}' 距边缘 "
                                  f"< {text_safety_mm}mm")
        text_safety = len(violations) == 0
        defects.extend(violations)

    verdict = "pass" if (resolution_pass and not defects) else "fix_and_recheck"

    return {
        "file": str(input_path.resolve()),
        "pixel_size": [w, h],
        "target_width_mm": target_width_mm,
        "dpi": round(dpi, 1) if dpi else None,
        "resolution_pass": resolution_pass,
        "color_mode": img.mode,
        "cmyk_required": require_cmyk,
        "background": background,
        "text_safety": text_safety,
        "defects": defects,
        "verdict": verdict,
    }


def main():
    ap = argparse.ArgumentParser(description="S13 印刷交付检查")
    ap.add_argument("--input", "-i", required=True, help="成品文件")
    ap.add_argument("--target-width-mm", type=float, default=300.0,
                    help="目标印刷宽度 mm，默认 300（DPI 按此计算）")
    ap.add_argument("--cmyk", action="store_true", help="要求 CMYK 交付（实物印刷）")
    ap.add_argument("--text-safety-mm", type=float, default=5.0,
                    help="文字安全距离 mm，默认 5")
    ap.add_argument("--text-spec", default=None,
                    help="排版 spec JSON（含 text_layers 时做文字安全区校验）")
    args = ap.parse_args()

    src = Path(args.input)
    if not src.exists():
        sys.exit(f"ERROR: 文件不存在: {src}")

    text_layers = []
    if args.text_spec:
        spec = json.loads(Path(args.text_spec).read_text(encoding="utf-8"))
        text_layers = spec.get("text_layers", [])

    result = check(src, args.target_width_mm, args.cmyk, text_layers,
                   args.text_safety_mm)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if result["verdict"] == "pass" else 2)


if __name__ == "__main__":
    main()
