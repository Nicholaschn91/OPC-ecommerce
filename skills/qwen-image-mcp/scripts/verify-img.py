#!/usr/bin/env python3
"""
verify-img.py — 终版 PROMPT ↔ 出图 落实度验证（PNG 纯 stdlib / JPEG 走 Pillow）

用户场景：终版模型给了 7 段 PROMPT（含 NEGATIVE / 模块说明 / 移动端构图检查），用千问 AI生图
或豆包图生图垫图出图后，下载到本地。本脚本对照 PROMPT 的关键元素做**像素级抽样**，判断出图是否真的落实。

不是替换人工核验——是给人工核验一份**结构化预筛报告**，把"明显不达标"的图先标红，省去逐张盯。

== 用法 ==
  python verify-img.py --ref <参考图.png|.jpg> --out <出图1.png> [<出图2.png> ...] --prompt <PROMPT.txt>
  （参考图支持 PNG / JPG；出图同上。PNG 走纯 stdlib 解码；JPG/JPEG 走 Pillow）

== 输出 ==
  控制台 JSON：每张出图给出 {pass, score, checks:[{name, ok, evidence}], fail_reasons}
  也写到 --report 指定的文件。

== 检查项（每张出图） ==
  R1 尺寸比例：宽高比是否在目标比例（默认 1:1 ±5%）
  R2 非纯白非纯黑：主体区域非全白/全黑（生成失败占位图识别）
  R3 与参考图色调相似：HSV 直方图与参考图 cosine ≥ 阈值（默认 0.6）
       —— 防止出图与参考图"画风完全不一致"（如给了咖啡棕参考图却出了蓝色钱包）
  R4 暖色调主导（仅当 prompt 提到 warm/coffee/brown 时启发式启用）
       —— HSV H 通道在 0-40° 或 320-360°（暖色环）占比 ≥ 阈值（默认 35%）
  R5 主体居中：图像中心 40%×40% 区域与外圈亮度方差比 ≥ 阈值（默认 0.9；原 1.2 过严导致千问大量误杀）
       —— 检测"主体放角落/角落空白"
  R6 禁止元素粗筛：图像四角 100px 区域内不出现明显 saturation 高饱和红色（≥ 80% 阈值）
       —— 抓"出现礼盒/丝带"等不该出现的彩色元素
  R7 文字水印：图像任意 16×16 patch 标准差 < 5 的占比 < 30%
       —— 抓"全屏 gradient 占位 / 全屏水印"

== 已知限制 ==
- 无 ML 模型，所有检查是启发式像素统计，假阳/假阴不可避免
- 不替代最终人工核验；建议 R1-R7 全通过 + 视觉一致性人工确认后才认定落实
- PNG 走纯 stdlib 解码（无第三方依赖）；JPG/JPEG 走 Pillow（托管 venv 首次需 `pip install Pillow`）
"""
import sys, os, json, struct, zlib, argparse, math, re
from pathlib import Path

# ---------- PNG 解码（纯 stdlib） ----------

def _png_chunks(buf):
    """Yield (type, data) for each PNG chunk after the 8-byte signature."""
    assert buf[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG file"
    i = 8
    while i < len(buf):
        ln = struct.unpack(">I", buf[i:i+4])[0]
        t = buf[i+4:i+8].decode("ascii")
        data = buf[i+8:i+8+ln]
        yield t, data
        i += 8 + ln + 4  # len + type + data + crc

def _paeth(a, b, c):
    p = a + b - c
    pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
    if pa <= pb and pa <= pc: return a
    if pb <= pc: return b
    return c

def decode_png_rgb(path):
    """Decode PNG → (w, h, list of (r,g,b) flat row-major). Supports 8-bit RGB/RGBA/grayscale."""
    with open(path, "rb") as f:
        buf = f.read()
    width = height = bit_depth = color_type = None
    idat = b""
    for t, data in _png_chunks(buf):
        if t == "IHDR":
            width, height, bit_depth, color_type = struct.unpack(">IIBB", data[:10])
        elif t == "IDAT":
            idat += data
        elif t == "IEND":
            break
    raw = zlib.decompress(idat)
    assert bit_depth == 8, f"only 8-bit PNGs supported, got {bit_depth}"
    # color_type: 0=gray, 2=RGB, 3=palette, 4=GA, 6=RGBA
    bpp = {0:1, 2:3, 3:1, 4:2, 6:4}[color_type]
    stride = width * bpp
    out = bytearray()
    prev = bytearray(stride)
    pos = 0
    for y in range(height):
        ftype = raw[pos]; pos += 1
        row = bytearray(raw[pos:pos+stride]); pos += stride
        if ftype == 0:
            pass
        elif ftype == 1:  # Sub
            for x in range(bpp, stride):
                row[x] = (row[x] + row[x-bpp]) & 0xff
        elif ftype == 2:  # Up
            for x in range(stride):
                row[x] = (row[x] + prev[x]) & 0xff
        elif ftype == 3:  # Average
            for x in range(stride):
                a = row[x-bpp] if x >= bpp else 0
                row[x] = (row[x] + (a + prev[x]) // 2) & 0xff
        elif ftype == 4:  # Paeth
            for x in range(stride):
                a = row[x-bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x-bpp] if x >= bpp else 0
                row[x] = (row[x] + _paeth(a, b, c)) & 0xff
        else:
            raise ValueError(f"unknown filter {ftype}")
        out.extend(row)
        prev = row
    # to flat (r,g,b) — drop alpha if present
    rgb = []
    if color_type == 2:    # RGB
        for i in range(0, len(out), 3):
            rgb.append((out[i], out[i+1], out[i+2]))
    elif color_type == 6:  # RGBA → drop A
        for i in range(0, len(out), 4):
            rgb.append((out[i], out[i+1], out[i+2]))
    elif color_type == 0:  # gray → R=G=B
        for v in out:
            rgb.append((v, v, v))
    else:
        raise ValueError(f"unsupported color_type {color_type}")
    return width, height, rgb

# ---------- JPEG 解码（走 Pillow；参考图常为 JPG） ----------

def decode_jpeg_rgb(path):
    """Decode JPEG → (w, h, flat (r,g,b) list) via Pillow. PNG 用纯 stdlib，JPG 用 Pillow。"""
    try:
        from PIL import Image
    except ImportError:
        raise RuntimeError(
            "JPEG 参考图需要 Pillow。请在该托管 venv 执行一次："
            "Scripts/pip.exe install Pillow（Windows）。PNG 出图仍可用纯 stdlib 路径。"
        )
    with Image.open(path) as im:
        im = im.convert("RGB")
        w, h = im.size
        px = im.load()
        rgb = [px[x, y] for y in range(h) for x in range(w)]
    return w, h, rgb

def load_image_rgb(path):
    """按扩展名派发：PNG → 纯 stdlib；JPG/JPEG → Pillow。返回 (w, h, flat (r,g,b) list)。"""
    ext = Path(path).suffix.lower()
    if ext in (".png",):
        return decode_png_rgb(path)
    if ext in (".jpg", ".jpeg"):
        return decode_jpeg_rgb(path)
    # 其余扩展名先试 PNG（大部分生成图是无扩展名或 .png）
    try:
        return decode_png_rgb(path)
    except Exception:
        return decode_jpeg_rgb(path)

# ---------- 像素特征 ----------

def rgb_to_hsv(r, g, b):
    rf, gf, bf = r/255.0, g/255.0, b/255.0
    mx, mn = max(rf, gf, bf), min(rf, gf, bf)
    d = mx - mn
    if d == 0:
        h = 0
    elif mx == rf:
        h = ((gf - bf) / d) % 6
    elif mx == gf:
        h = (bf - rf) / d + 2
    else:
        h = (rf - gf) / d + 4
    h = (h * 60) % 360
    s = 0 if mx == 0 else d / mx
    v = mx
    return h, s, v

def cos_hist(pixels, h_bins=18, s_bins=4, v_bins=4):
    """Build a coarse HSV histogram for similarity comparison."""
    hist = [0.0] * (h_bins * s_bins * v_bins)
    for r,g,b in pixels:
        h,s,v = rgb_to_hsv(r,g,b)
        # ignore near-white & near-black
        if v > 0.95 or v < 0.05: continue
        hi = min(int(h / (360/h_bins)), h_bins-1)
        si = min(int(s * s_bins), s_bins-1)
        vi = min(int(v * v_bins), v_bins-1)
        hist[(hi * s_bins + si) * v_bins + vi] += 1
    # l2 normalize
    norm = math.sqrt(sum(x*x for x in hist)) or 1.0
    return [x/norm for x in hist]

def hist_cos(a, b):
    return sum(x*y for x,y in zip(a, b))

def patch_variance(pixels, w, h, x0, y0, sz=16):
    """Std dev of grayscale in a sz×sz patch."""
    vals = []
    for y in range(y0, min(y0+sz, h)):
        for x in range(x0, min(x0+sz, w)):
            r,g,b = pixels[y*w + x]
            vals.append((r+g+b)/3)
    if not vals: return 0
    m = sum(vals)/len(vals)
    return math.sqrt(sum((v-m)**2 for v in vals)/len(vals))

# ---------- 检查项 ----------

def check_ratio(w, h, target=1.0, tol=0.05):
    actual = w/h
    ok = abs(actual - target) <= tol
    return {"name":"R1 比例 1:1±5%", "ok":ok, "evidence":f"{w}×{h} (ratio {actual:.3f}, target {target})"}

def check_not_blank(pixels):
    # sample every 50th pixel, count distinct luma buckets
    samples = pixels[::50]
    buckets = set()
    for r,g,b in samples:
        l = int(((r+g+b)/3) / 32)
        buckets.add(min(l, 7))
    ok = len(buckets) >= 4
    return {"name":"R2 非纯白/纯黑占位", "ok":ok, "evidence":f"luma buckets={len(buckets)} (≥4 才是有效图)"}

def check_color_match(out_pixels, ref_pixels):
    ha = cos_hist(out_pixels)
    hb = cos_hist(ref_pixels)
    sim = hist_cos(ha, hb)
    ok = sim >= 0.6
    return {"name":"R3 与参考图色调相似", "ok":ok, "evidence":f"HSV hist cosine={sim:.3f} (≥0.6)"}

def check_warm_dominant(pixels, threshold=0.35):
    h_bins = 36
    warm = 0; total = 0
    for r,g,b in pixels[::20]:
        h,s,v = rgb_to_hsv(r,g,b)
        if v < 0.1 or v > 0.95 or s < 0.1: continue
        total += 1
        deg = h
        if deg <= 40 or deg >= 320:
            warm += 1
    if total == 0:
        return {"name":"R4 暖色调主导", "ok":False, "evidence":"no colored pixels sampled"}
    ratio = warm/total
    ok = ratio >= threshold
    return {"name":"R4 暖色调主导", "ok":ok, "evidence":f"warm ratio={ratio:.2%} (≥{threshold:.0%})"}

def check_centered_subject(pixels, w, h):
    cx, cy = w//2, h//2
    cw, ch = int(w*0.4), int(h*0.4)
    edge_pixels = []
    for x in range(0, w, 8):
        for y in range(0, h, 8):
            if x < cx-cw//2 or x > cx+cw//2 or y < cy-ch//2 or y > cy+ch//2:
                edge_pixels.append(pixels[y*w + x])
    center_pixels = []
    for x in range(cx-cw//2, cx+cw//2, 8):
        for y in range(cy-ch//2, cy+ch//2, 8):
            center_pixels.append(pixels[y*w + x])
    def std(p):
        if not p: return 0
        m = sum(sum(c) for c in p)/(3*len(p))
        return math.sqrt(sum(((sum(c)/3)-m)**2 for c in p)/len(p))
    cs, es = std(center_pixels), std(edge_pixels)
    ratio = (cs + 1e-3) / (es + 1e-3)
    ok = ratio >= 0.9
    return {"name":"R5 主体居中(中心方差>外圈)", "ok":ok, "evidence":f"中心 std={cs:.1f} 外圈 std={es:.1f} 比={ratio:.2f} (≥0.9)"}

def check_no_red_corner(pixels, w, h, sz=100, sat_thr=0.8, hue_thr=(0, 30)):
    """Detect high-saturation red in 4 corners → likely gift box/ribbon."""
    hits = 0
    total = 0
    for (x0, y0) in [(0,0), (w-sz,0), (0,h-sz), (w-sz,h-sz)]:
        for dy in range(0, sz, 4):
            for dx in range(0, sz, 4):
                r,g,b = pixels[(y0+dy)*w + (x0+dx)]
                hh, ss, vv = rgb_to_hsv(r, g, b)
                total += 1
                if ss >= sat_thr and (hue_thr[0] <= hh <= hue_thr[1]):
                    hits += 1
    ratio = hits/total if total else 0
    ok = ratio < 0.15
    return {"name":"R6 四角无高饱红(无礼盒)", "ok":ok, "evidence":f"高饱红占比={ratio:.2%} (<15%)"}

def check_low_variance_ratio(pixels, w, h, sz=16, ratio_thr=0.30):
    """Detect large flat patches → watermark/placeholder."""
    flat = 0; total = 0
    for y in range(0, h-sz, sz):
        for x in range(0, w-sz, sz):
            var = patch_variance(pixels, w, h, x, y, sz)
            total += 1
            if var < 5:
                flat += 1
    ratio = flat/total if total else 0
    ok = ratio < ratio_thr
    return {"name":"R7 非大面积平铺(水印)", "ok":ok, "evidence":f"flat patch 占比={ratio:.2%} (<{ratio_thr:.0%})"}

# ---------- main ----------

def verify_one(out_path, ref_pixels, prompt_text, target_ratio=1.0):
    out_w, out_h, out_pixels = load_image_rgb(out_path)
    checks = [
        check_ratio(out_w, out_h, target=target_ratio),
        check_not_blank(out_pixels),
        check_color_match(out_pixels, ref_pixels),
    ]
    if re.search(r"\b(warm|coffee|brown|crazy.horse|leather|tan|cognac)\b", prompt_text, re.I):
        checks.append(check_warm_dominant(out_pixels))
    checks.append(check_centered_subject(out_pixels, out_w, out_h))
    checks.append(check_no_red_corner(out_pixels, out_w, out_h))
    checks.append(check_low_variance_ratio(out_pixels, out_w, out_h))
    fails = [c for c in checks if not c["ok"]]
    score = (len(checks) - len(fails)) / len(checks)
    return {"pass": not fails, "score": round(score, 3), "checks": checks, "fail_reasons":[c["name"] for c in fails]}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", required=True, help="参考图 PNG")
    ap.add_argument("--out", required=True, nargs="+", help="出图 PNG（1+ 张）")
    ap.add_argument("--prompt", required=True, help="PROMPT 文本文件")
    ap.add_argument("--report", help="可选：报告落盘 JSON 路径")
    ap.add_argument("--ratio", type=float, default=1.0, help="目标比例（默认 1:1）")
    args = ap.parse_args()
    prompt = Path(args.prompt).read_text(encoding="utf-8")
    print(f"[ref] decoding {args.ref}...", file=sys.stderr)
    ref_w, ref_h, ref_pixels = load_image_rgb(args.ref)
    print(f"      {ref_w}×{ref_h}, {len(ref_pixels):,} pixels", file=sys.stderr)
    results = []
    for out in args.out:
        print(f"[out] {out}...", file=sys.stderr)
        try:
            r = verify_one(out, ref_pixels, prompt, target_ratio=args.ratio)
        except Exception as e:
            r = {"pass": False, "score": 0, "checks": [], "fail_reasons": [f"decode error: {e}"]}
        r["file"] = out
        results.append(r)
        tag = "✅" if r["pass"] else "❌"
        print(f"  {tag} score={r['score']} fails={r['fail_reasons']}", file=sys.stderr)
    overall_pass = all(r["pass"] for r in results)
    report = {"overall_pass": overall_pass, "results": results}
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[report] saved to {args.report}", file=sys.stderr)
    sys.exit(0 if overall_pass else 2)

if __name__ == "__main__":
    main()
