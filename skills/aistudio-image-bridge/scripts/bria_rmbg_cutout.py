#!/usr/bin/env python3
"""remove_background — BRIA-RMBG-2.0 后端实现（对应 Agent 工具 remove_background）

Nano Banana 2 Lite (gemini-3.1-flash-lite-image) 无法直出透明 PNG（Google 图像模型全家族
只输出 flat RGB、无 alpha 通道）。本后端把 Path 1 抓到的干净 JPEG 用 BRIA-RMBG-2.0 抠出
alpha 蒙版 → 透明 PNG。

按用户给定的「后端必须写的代码」要求，本文件实现：
  - MODE_PRESETS 参数映射表：每个 mode 自动绑定最优模型 + 参数
  - 质量自检函数 + 阈值配置：自动判断抠图结果是否合格
  - 重试 / 降级 / 兜底逻辑：质检失败时自动换参数或换预处理（最多 3 次）
  - DPI 校正 + 尺寸归一化预处理：避免异常输入导致模型失效
  - 结构化 metadata 返回：让 Agent 能读懂结果状态并正确回应

依赖（用户负责安装；权重用本地目录加载，无需运行时鉴权）：
  pip install torch torchvision pillow transformers numpy kornia
  # 权重复用本地目录（推荐，免鉴权）：
  #   huggingface-cli download briaai/RMBG-2.0 --local-dir ./models/rmbg-2.0
  #   运行时设 RMBG_MODEL_DIR=./models/rmbg-2.0 即走本地（脚本已自动识别）
  # ⚠️ briaai/RMBG-2.0 是 GATED 仓库：首次下载权重前必须先 HUGGINGFACE 鉴权，否则 401
  #   1) 浏览器打开 https://huggingface.co/briaai/RMBG-2.0 点「Agree」接受许可
  #   2) huggingface-cli login  （或设环境变量 HF_TOKEN=你的 read token 后再 download）
  # ⚠️ numpy 体系必须与 torch 一致（D:/anaconda/python.exe 的踩坑清单，2026-08-18 实测）：
  #   anaconda 自带 numpy1.x 编译的 scipy/sklearn/pandas/pyarrow/numexpr/bottleneck 会与
  #   用户站 numpy2.x(torch/transformers 所在) ABI 冲突 → 全部 --user 重装到用户站：
  #     D:/anaconda/python.exe -m pip install --user --force-reinstall --no-deps ^
  #       scikit-learn pandas pyarrow scipy numexpr bottleneck kornia narwhals
  #   （bottleneck/numexpr 为 pandas 可选依赖，缺了只告警不崩；其余为硬依赖必须修）
  # 国内网络：首次运行前设 HF_ENDPOINT=https://hf-mirror.com 加速（注意镜像可能未同步该 gated 权重）

CLI（契约对齐 Agent Tool Definition）：
  python bria_rmbg_cutout.py --image-url clean.jpg --mode pod_print --out clean_cut.png
  python bria_rmbg_cutout.py --image-url clean.jpg --mode product --keep-shadow true
  python bria_rmbg_cutout.py --image-url clean.jpg --mode pod_print --matting-strength 1.0 --meta meta.json

作为 Agent 工具被调用时，stdout 输出结构化 metadata (JSON)，供 Agent 读懂结果状态。
"""
import argparse
import sys
import os
import json

MODE_PRESETS = {
    "pod_print": {
        "model": "briaai/RMBG-2.0",
        "matting_strength": 0.95,   # POD 印花/徽章/Logo/贴纸：边缘最锐利
        "keep_shadow": False,
        "desc": "POD印花/徽章/Logo/矢量图形/贴纸设计稿",
        "edge": "hard",
    },
    "product": {
        "model": "briaai/RMBG-2.0",
        "matting_strength": 0.6,    # 商品主体：柔和过渡
        "keep_shadow": False,      # 默认去阴影；用户要保留时显式 keep_shadow=true
        "desc": "电商商品主体/产品展示图",
        "edge": "soft",
    },
    "portrait": {
        "model": "briaai/RMBG-2.0",
        "matting_strength": 0.75,   # 人像发丝级精细
        "keep_shadow": False,
        "desc": "人像发丝级精细抠图",
        "edge": "smooth",
    },
}
VALID_MODES = list(MODE_PRESETS.keys())
QC_THRESHOLD = 0.6          # 质量分低于此值判不合格
MAX_ATTEMPTS = 3            # 最多重试次数（含首次）
MAX_SIDE = 2048             # 预处理尺寸上限，避免巨图 OOM


def _need_deps():
    missing = []
    for m in ("numpy", "torch", "torchvision", "transformers"):
        try:
            __import__(m)
        except Exception:
            missing.append(m)
    if missing:
        sys.stderr.write(
            "缺少依赖，无法运行 BRIA-RMBG-2.0：\n"
            "  请先安装: pip install " + " ".join(missing) + "\n"
            "  (权重 briaai/RMBG-2.0 首次运行会自动下载，约 500MB；\n"
            "   国内可设 HF_ENDPOINT=https://hf-mirror.com 加速)\n"
        )
        return True
    return False


# ---- 预处理：尺寸归一化 + DPI 校正 ------------------------------------------
def _preprocess(image_url):
    """打开图片、转 RGB、超大尺寸归一化、抽取 DPI 信息。返回 (PIL_RGB, dpi)。"""
    from PIL import Image
    raw = Image.open(image_url)
    w, h = raw.size
    dpi = raw.info.get("dpi")  # (x, y) 或 None
    im = raw.convert("RGB")
    if max(im.size) > MAX_SIDE:
        scale = MAX_SIDE / max(im.size)
        im = im.resize((int(im.size[0] * scale), int(im.size[1] * scale)),
                       Image.LANCZOS)
    return im, dpi, w, h


# ---- 模型加载（单例缓存，供重试复用）--------------------------------------
_MODEL_CACHE = {}

def _resolve_model_id(model_id):
    """若设了 RMBG_MODEL_DIR 且为有效目录，则改从本地目录加载（运行时无需 HF 鉴权）。"""
    local = os.environ.get("RMBG_MODEL_DIR")
    if local and os.path.isdir(local):
        return local
    return model_id


def _load_model(model_id, device, token=None):
    import torch
    from transformers import AutoModelForImageSegmentation
    model_id = _resolve_model_id(model_id)
    if device is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
    key = (model_id, device)
    if key not in _MODEL_CACHE:
        if token is None:
            token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
        m = AutoModelForImageSegmentation.from_pretrained(
            model_id, trust_remote_code=True, token=token
        )
        try:
            torch.set_float32_matmul_precision("high")
        except Exception:
            pass
        m.to(device).eval()
        _MODEL_CACHE[key] = m
    return _MODEL_CACHE[key], device


def _run_model(im, model, device):
    """返回 0..1 的 alpha 蒙版 (np.float32, HxW)。"""
    import torch
    from torchvision import transforms
    import numpy as np
    transform_image = transforms.Compose([
        transforms.Resize((1024, 1024)),
        transforms.ToTensor(),
        transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
    ])
    inp = transform_image(im).unsqueeze(0).to(device)
    with torch.no_grad():
        preds = model(inp)[-1].sigmoid().cpu()
    pred = preds[0].squeeze()
    mask = transforms.ToPILImage()(pred).resize(im.size, Image.BILINEAR)
    return np.asarray(mask).astype(np.float32) / 255.0


# ---- 边缘柔化：matting_strength -> sigmoid 锐度 ----------------------------
def _apply_matting(mask_np, matting_strength):
    """matting_strength(0..1) 越大边缘越锐利。返回 0..1 alpha。"""
    import numpy as np
    k = max(0.1, matting_strength * 10.0)   # 0.1~10 的锐度系数
    return 1.0 / (1.0 + np.exp(-(mask_np - 0.5) * k))


# ---- 降级清理：中值滤波去椒盐噪点 ------------------------------------------
def _morph_cleanup(alpha_np):
    from PIL import Image, ImageFilter
    import numpy as np
    im = Image.fromarray((alpha_np * 255).astype(np.uint8), "L")
    im = im.filter(ImageFilter.MedianFilter(3))
    return np.asarray(im).astype(np.float32) / 255.0


# ---- 质量自检 + 阈值 -------------------------------------------------------
def _qc(alpha_np):
    """返回 (score, reason, warning)。score<QC_THRESHOLD 视为不合格。"""
    import numpy as np
    fg = float((alpha_np > 0.5).mean())
    if fg < 0.01:
        return 0.0, "empty_result", "前景占比过低(<1%)，疑似未检出主体"
    if fg > 0.99:
        return 0.0, "no_cutout", "前景占比过高(>99%)，疑似未去背"
    # 边缘一致性：边界带梯度密度（过高=毛刺/过羽化，过低=方块化）
    gx = np.abs(np.diff(alpha_np, axis=1))
    gy = np.abs(np.diff(alpha_np, axis=0))
    edge = (gx.sum() + gy.sum()) / alpha_np.size
    score = 1.0
    if edge < 0.0015:
        score = 0.7     # 过度二值化/方块边缘
    elif edge > 0.07:
        score = 0.7     # 过度羽化/噪点边缘
    return score, "ok", None


# ---- 阴影保留（仅 product 模式 keep_shadow=true）---------------------------
def _add_shadow(rgba, offset=(0, 10), blur=14, opacity=0.35):
    """从主体 alpha 合成柔和投影，置于主体下方（透明 PNG 内含软阴影）。"""
    from PIL import Image, ImageFilter
    alpha = rgba.split()[3]
    shadow = alpha.filter(ImageFilter.GaussianBlur(blur))
    shadow = shadow.transform(
        shadow.size, Image.AFFINE, (1, 0, offset[0], 0, 1, offset[1])
    )
    dark = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    dark.putalpha(shadow)
    dark.putalpha(dark.split()[3].point(lambda a: int(a * opacity)))
    return Image.alpha_composite(dark, rgba)


# ---- 预加载（供 FastAPI server 启动时 warm the cache）-----------------------
def warmup(model_id=None, device=None):
    """预加载模型到 _MODEL_CACHE；server 启动事件里调用一次即可。"""
    if model_id is None:
        model_id = MODE_PRESETS["pod_print"]["model"]
    _load_model(model_id, device)


# ---- 主接口 ----------------------------------------------------------------
def remove_background(image_url, mode="pod_print", keep_shadow=None,
                      matting_strength=None, out=None, device=None, meta_out=None,
                      token=None):
    if mode not in VALID_MODES:
        raise ValueError(f"mode 必须是 {VALID_MODES} 之一，收到: {mode!r}")
    preset = MODE_PRESETS[mode]
    if keep_shadow is None:
        keep_shadow = preset["keep_shadow"]
    if matting_strength is None:
        matting_strength = preset["matting_strength"]
    if out is None:
        out = os.path.splitext(image_url)[0] + "_bria.png"

    from PIL import Image
    import numpy as np

    im, dpi, raw_w, raw_h = _preprocess(image_url)
    model, device = _load_model(preset["model"], device, token=token)

    warning = None
    last_quality = None
    final_alpha = None
    status = "partial"
    for attempt in range(MAX_ATTEMPTS):
        # 重试时逐步加大锐度，尝试纠偏
        k = matting_strength * (1.0 + 0.15 * attempt)
        mask = _run_model(im, model, device)
        alpha = _apply_matting(mask, k)
        if attempt > 0:
            alpha = _morph_cleanup(alpha)
        score, reason, w = _qc(alpha)
        last_quality = (score, reason, fg_of(alpha))
        if score >= QC_THRESHOLD:
            final_alpha = alpha
            status = "success"
            break
        warning = f"质检未过(第{attempt + 1}次, {reason})，自动重试/降级"
    else:
        # 3 次均不合格 -> 兜底用最后一次结果，标记 partial
        final_alpha = alpha

    rgba = im.convert("RGBA")
    rgba.putalpha((final_alpha * 255).astype(np.uint8))
    if keep_shadow and mode == "product":
        rgba = _add_shadow(rgba)

    # DPI 校正：把输入 DPI 写回输出，保证打印物理尺寸正确
    save_kwargs = {}
    if dpi:
        save_kwargs["dpi"] = dpi
    rgba.save(out, **save_kwargs)

    fg_ratio = fg_of(final_alpha)
    q_score, q_reason, _ = last_quality
    meta = {
        "status": status,
        "tool": "remove_background",
        "mode": mode,
        "model": preset["model"],
        "input": {
            "path": image_url,
            "width": raw_w,
            "height": raw_h,
            "dpi": list(dpi) if dpi else None,
            "size_bytes": os.path.getsize(image_url),
        },
        "output": {
            "path": out,
            "width": rgba.width,
            "height": rgba.height,
            "dpi": list(dpi) if dpi else None,
            "format": "PNG",
            "alpha_channel": True,
        },
        "quality": {
            "score": round(float(q_score), 3),
            "foreground_ratio": round(float(fg_ratio), 4),
            "passed": bool(q_score >= QC_THRESHOLD),
        },
        "attempts": (attempt + 1),
        "keep_shadow": bool(keep_shadow),
        "matting_strength": matting_strength,
        "warning": warning,
    }
    if meta_out:
        with open(meta_out, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    return out, meta


def fg_of(alpha_np):
    import numpy as np
    return float((alpha_np > 0.5).mean())


def main():
    ap = argparse.ArgumentParser(description="remove_background (BRIA-RMBG-2.0) 去背 -> 透明 PNG")
    ap.add_argument("--image-url", required=True, help="待处理图片路径/URL")
    ap.add_argument("--mode", default="pod_print", choices=VALID_MODES,
                    help="pod_print=POD印花/图形; product=商品主体; portrait=人像")
    ap.add_argument("--keep-shadow", default=None, choices=["true", "false"],
                    help="仅 product 模式有效：是否保留商品自然投影")
    ap.add_argument("--matting-strength", type=float, default=None,
                    help="边缘柔化强度 0..1（默认按 mode 预设）")
    ap.add_argument("--out", default=None, help="输出透明 PNG 路径")
    ap.add_argument("--device", default=None, help="cpu / cuda (默认自动)")
    ap.add_argument("--meta", default=None, help="把结构化 metadata 写到该 JSON 文件")
    args = ap.parse_args()

    if _need_deps():
        sys.exit(2)
    keep_shadow = None
    if args.keep_shadow == "true":
        keep_shadow = True
    elif args.keep_shadow == "false":
        keep_shadow = False
    try:
        out, meta = remove_background(
            args.image_url, mode=args.mode, keep_shadow=keep_shadow,
            matting_strength=args.matting_strength, out=args.out,
            device=args.device, meta_out=args.meta,
        )
    except Exception as e:
        sys.stderr.write(f"remove_background 失败: {repr(e)}\n")
        sys.exit(1)
    # stdout 输出结构化 metadata，供 Agent 读取状态
    sys.stdout.write(json.dumps(meta, ensure_ascii=False) + "\n")
    if meta.get("warning"):
        sys.stderr.write("WARNING: " + meta["warning"] + "\n")


if __name__ == "__main__":
    main()
