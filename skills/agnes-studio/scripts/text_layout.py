#!/usr/bin/env python3
"""
Agnes Studio S10 — 文字排版渲染（文字永不进扩散模型）

分层铁律：文字由本脚本确定性渲染后叠加，不写入生成 prompt。
输入为排版 spec JSON（结构见 references/prompts-l2.md P9）。

用法：
  python text_layout.py --spec spec.json --base 底图.png --output 成品.png
  python text_layout.py --spec spec.json --output 文字层.png --canvas 2048x2048   # 无底图，出透明文字层
"""
import argparse
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def load_font(font_spec: str, size_pt: int, base_height: int):
    """font_spec: 字体文件路径，或 windows 内置字体名（不含路径时按常见目录查找）。"""
    candidates = [Path(font_spec)] if font_spec else []
    if font_spec and not Path(font_spec).exists():
        for d in (Path("C:/Windows/Fonts"), Path("/Library/Fonts"),
                  Path.home() / ".fonts"):
            candidates.append(d / font_spec)
            candidates.append(d / (font_spec + ".ttf"))
    for c in candidates:
        if c.exists():
            try:
                return ImageFont.truetype(str(c), max(8, int(size_pt * base_height / 720)))
            except OSError:
                continue
    print(f"WARNING: 字体 {font_spec!r} 未找到，回退内置默认字体（仅限打样，商用必须换授权字体）",
          file=sys.stderr)
    try:
        return ImageFont.truetype("arial.ttf", max(8, int(size_pt * base_height / 720)))
    except OSError:
        return ImageFont.load_default()


def parse_color(color: str):
    c = color.lstrip("#")
    if len(c) == 6:
        r, g, b = int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)
        return (r, g, b, 255)
    if len(c) == 8:
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4, 6))
    return (0, 0, 0, 255)


def render_layer(layer: dict, canvas: Image.Image):
    W, H = canvas.size
    content = layer["content"]
    font = load_font(layer.get("font", ""), layer.get("size_pt", 72), H)
    color = parse_color(layer.get("color", "#000000"))
    pos = layer.get("position", {})
    x = pos.get("x_ratio", 0.5) * W
    y = pos.get("y_ratio", 0.5) * H
    anchor_map = {
        "bottom_center": ("mm", (x, y)),
        "top_center": ("mm", (x, y)),
        "center": ("mm", (x, y)),
    }
    anchor, xy = anchor_map.get(pos.get("anchor", "center"), ("mm", (x, y)))

    draw = ImageDraw.Draw(canvas, "RGBA")
    layout = layer.get("layout", "single_line")

    if layout == "auto_wrap":
        # 简单按字符数换行：估算每行最大字数
        max_w = W * 0.9
        lines, cur = [], ""
        for ch in content:
            test = cur + ch
            bbox = draw.textbbox((0, 0), test, font=font)
            if bbox[2] - bbox[0] > max_w and cur:
                lines.append(cur)
                cur = ch
            else:
                cur = test
        if cur:
            lines.append(cur)
        line_h = draw.textbbox((0, 0), "测Ag", font=font)[3] - draw.textbbox((0, 0), "测Ag", font=font)[1]
        total_h = line_h * len(lines)
        y0 = y - total_h / 2
        for i, line in enumerate(lines):
            draw.text((x, y0 + i * line_h + line_h / 2), line, font=font,
                      fill=color, anchor="mm")
    elif layout == "arc":
        # 简易弧形排字：逐字符绕圆心旋转
        import math
        radius = min(W, H) * 0.35
        n = len(content)
        span = math.radians(min(120, 18 * n))
        start = -math.pi / 2 - span / 2
        for i, ch in enumerate(content):
            ang = start + span * (i / max(n - 1, 1))
            cx = x + radius * math.cos(ang)
            cy = y + radius * math.sin(ang)
            ch_img = Image.new("RGBA", (font.size * 2, font.size * 2), (0, 0, 0, 0))
            d2 = ImageDraw.Draw(ch_img)
            d2.text((font.size, font.size), ch, font=font, fill=color, anchor="mm")
            ch_img = ch_img.rotate(-math.degrees(ang) - 90, resample=Image.BICUBIC,
                                   expand=False)
            canvas.paste(ch_img, (int(cx - font.size), int(cy - font.size)), ch_img)
        return
    else:  # single_line
        draw.text(xy, content, font=font, fill=color, anchor=anchor)


def main():
    ap = argparse.ArgumentParser(description="S10 文字排版渲染")
    ap.add_argument("--spec", required=True, help="排版 spec JSON 文件")
    ap.add_argument("--base", default=None, help="底图（叠加输出成品）")
    ap.add_argument("--canvas", default=None, help="无底图时的画布尺寸 WxH")
    ap.add_argument("--output", "-o", required=True, help="输出路径")
    args = ap.parse_args()

    spec = json.loads(Path(args.spec).read_text(encoding="utf-8-sig"))
    layers = spec.get("text_layers", [])
    if not layers:
        sys.exit("ERROR: spec 中没有 text_layers。")

    # 画布
    if args.base:
        canvas = Image.open(args.base).convert("RGBA")
    elif args.canvas:
        w, h = (int(v) for v in args.canvas.lower().split("x"))
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    else:
        sys.exit("ERROR: 必须提供 --base 底图或 --canvas 尺寸。")

    safe = spec.get("safe_area_ratio", 0.05)
    for layer in layers:
        # 安全区校验
        pos = layer.get("position", {})
        xr, yr = pos.get("x_ratio", 0.5), pos.get("y_ratio", 0.5)
        if min(xr, yr, 1 - xr, 1 - yr) < safe:
            print(f"WARNING: 文字位置 ({xr:.2f},{yr:.2f}) 距边缘小于安全区 "
                  f"{safe:.0%}，印刷可能被裁切", file=sys.stderr)
        render_layer(layer, canvas)
        print(f"已渲染: {layer['content'][:20]!r} @ ({xr:.2f},{yr:.2f})", file=sys.stderr)

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(out)
    print(f"输出: {out} ({out.stat().st_size / 1024:.1f} KB)", file=sys.stderr)
    print(json.dumps({"output": str(out.resolve()),
                      "layers_rendered": len(layers)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
