"""
BRIA-RMBG-2.0 ONNX Runtime GPU 服务 (RTX 2060 Super 8GB 优化)

模型: 挂载于 /app/models/rmbg2.onnx  (BRIA RMBG-2.0 导出的 FP32 ONNX)
推理: ONNX Runtime GPU (CUDA 11.8), FP32 (2060S FP16 弱于 FP32, 故用 FP32)
协议: 与 bria_rmbg_server.py 一致, 供 Agent Function Calling 调用

用户约束 (2026-08-18):
  1. 禁止任何输入尺寸缩放: preprocess 固定 1024, 输出 mask 归回原分辨率 (保持原始分辨率抠图)
  2. ONNX 加载路径固定 /app/models/rmbg2.onnx
  3. 显存安全阀: nvidia-smi 显示 >7.5GB 时, 将 docker-compose 的
     ONNXRUNTIME_GPU_MEM_LIMIT 从 5GB 降至 4GB 并重启容器
     (本文件会读取该环境变量并注入 CUDA provider, 使其真实生效)
"""
import os
import io
import base64
import logging
from typing import Optional

import numpy as np
import onnxruntime as ort
from PIL import Image, ImageFilter
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("rmbg")

MODEL_PATH = os.environ.get("RMBG_ONNX_PATH", "/app/models/rmbg2.onnx")
MODEL_INPUT_SIZE = 1024  # 固定, 禁止任何基于 min(size) 的缩放分支

# 与 bria_rmbg_cutout.py 一致的预设 (matting 锐化强度)
MODE_PRESETS = {
    "pod_print": {"matting_strength": 0.95},  # 锐边
    "product":   {"matting_strength": 0.6},   # 柔边
    "portrait":  {"matting_strength": 0.85},  # 发丝级
}

_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_STD = np.array([0.229, 0.224, 0.225], dtype=np.float32)

_session = None


def get_session():
    """单例加载 ONNX (单 worker, 进程内复用)."""
    global _session
    if _session is None:
        so = ort.SessionOptions()
        # 显存上限: 读 ONNXRUNTIME_GPU_MEM_LIMIT (字节), 默认 5GB
        providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        provider_options = [{}, {}]
        mem = os.environ.get("ONNXRUNTIME_GPU_MEM_LIMIT")
        if mem:
            try:
                provider_options[0] = {
                    "device_id": 0,
                    "gpu_mem_limit": int(mem),
                }
                logger.info("CUDA gpu_mem_limit = %s bytes", mem)
            except ValueError:
                logger.warning("ONNXRUNTIME_GPU_MEM_LIMIT 非整数, 忽略: %s", mem)
        logger.info("loading ONNX from %s", MODEL_PATH)
        _session = ort.InferenceSession(
            MODEL_PATH,
            sess_options=so,
            providers=providers,
            provider_options=provider_options,
        )
        logger.info("active providers: %s", _session.get_providers())
    return _session


def preprocess(img: Image.Image):
    """固定 1024 输入, 禁止缩放条件判断. 返回 (tensor[1,3,1024,1024], 原图尺寸)."""
    orig_w, orig_h = img.size
    # 固定缩放到 1024x1024 供模型推理 (无 min(size) 分支)
    resized = img.resize((MODEL_INPUT_SIZE, MODEL_INPUT_SIZE), Image.BILINEAR)
    arr = np.asarray(resized, dtype=np.float32) / 255.0
    arr = (arr - _MEAN) / _STD
    arr = arr.transpose(2, 0, 1)[None, ...]  # [1,3,1024,1024]
    return arr.astype(np.float32), (orig_w, orig_h)


def postprocess(mask: np.ndarray, orig_size):
    """ONNX 输出 -> 原分辨率 mask 图. 支持 [1,1,H,W] 与 [1,H,W]."""
    m = np.asarray(mask).squeeze()
    if m.ndim != 2:
        # 兜底: 取第一个通道
        m = np.asarray(mask).reshape(np.asarray(mask).shape[-2], np.asarray(mask).shape[-1])
    m = (m * 255.0).clip(0, 255).astype(np.uint8)
    return Image.fromarray(m).resize(orig_size, Image.BILINEAR)


def apply_matting(alpha: np.ndarray, strength: Optional[float]):
    """sigmoid 锐化: alpha = 1/(1+exp(-s*(a-0.5))). strength=None 则原样返回."""
    if strength is None:
        return alpha
    return 1.0 / (1.0 + np.exp(-strength * (alpha - 0.5)))


def add_soft_shadow(rgba: Image.Image) -> Image.Image:
    """product 模式 keep_shadow: 合成柔和接触阴影 (仅呈现用, 非还原原图阴影)."""
    alpha = np.asarray(rgba.split()[-1]).astype(np.float32) / 255.0
    # 偏移 + 高斯模糊 -> 暗色剪影
    shadow = Image.fromarray((alpha * 255).astype(np.uint8), mode="L")
    shadow = shadow.filter(ImageFilter.GaussianBlur(8))
    sh_arr = np.asarray(shadow, dtype=np.float32) / 255.0
    # 向下偏移 6px
    sh = np.zeros_like(sh_arr)
    sh[6:, :] = sh_arr[:-6, :]
    # 合成: 白底 + 暗阴影 + 前景
    h, w = alpha.shape
    out = np.ones((h, w, 3), dtype=np.float32)  # 白底
    for c in range(3):
        out[:, :, c] = out[:, :, c] * (1 - sh) * 0.85  # 阴影区压暗
    fg = np.asarray(rgba.convert("RGB"), dtype=np.float32) / 255.0
    a3 = alpha[:, :, None]
    comp = out * (1 - a3) + fg * a3
    comp = (comp * 255).clip(0, 255).astype(np.uint8)
    res = Image.fromarray(comp, mode="RGB").convert("RGBA")
    res.putalpha(Image.fromarray((alpha * 255).clip(0, 255).astype(np.uint8), mode="L"))
    return res


def quick_qc(alpha: np.ndarray, mode: str):
    fg = float(alpha.mean())
    warnings = []
    if mode == "pod_print" and (fg < 0.05 or fg > 0.95):
        warnings.append("前景占比异常, 请检查原图是否为有效印花设计稿")
    elif mode == "product" and fg < 0.1:
        warnings.append("检测到主体过小, 可能存在误删, 建议人工复核")
    gx = np.abs(np.diff(alpha, axis=1)).mean()
    gy = np.abs(np.diff(alpha, axis=0)).mean()
    edge = float((gx + gy) / 2.0)
    return {
        "warnings": warnings,
        "foreground_coverage": round(fg * 100, 1),
        "edge_gradient": round(edge, 3),
    }


app = FastAPI()


class RemoveBgRequest(BaseModel):
    image_url: str                      # 本地路径 / http(s) URL / data:image base64
    mode: str = "pod_print"             # pod_print | product | portrait
    keep_shadow: bool = False           # product 模式合成柔和阴影
    matting_strength: Optional[float] = None


def load_image(src: str) -> Image.Image:
    if src.startswith("data:image"):
        b64 = src.split(",", 1)[1]
        return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    if src.startswith("http://") or src.startswith("https://"):
        import urllib.request
        with urllib.request.urlopen(src, timeout=30) as r:
            return Image.open(io.BytesIO(r.read())).convert("RGB")
    return Image.open(src).convert("RGB")


@app.on_event("startup")
def _warmup():
    try:
        get_session()
        logger.info("model warmed up")
    except Exception as e:
        logger.error("warmup failed: %s", e)


@app.get("/health")
def health():
    try:
        s = get_session()
        return {"status": "ok", "providers": s.get_providers()}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.post("/remove_background")
def remove_background(req: RemoveBgRequest):
    preset = MODE_PRESETS.get(req.mode)
    if not preset:
        raise HTTPException(400, f"unsupported mode: {req.mode}")
    try:
        img = load_image(req.image_url)
    except Exception as e:
        raise HTTPException(400, f"cannot load image: {e}")

    sess = get_session()
    x, orig_size = preprocess(img)
    out = sess.run(None, {sess.get_inputs()[0].name: x})[0]
    mask_img = postprocess(out, orig_size)

    alpha = np.asarray(mask_img, dtype=np.float32) / 255.0
    matting = req.matting_strength if req.matting_strength is not None else preset["matting_strength"]
    alpha = apply_matting(alpha, matting)
    alpha_u8 = (alpha * 255).clip(0, 255).astype(np.uint8)

    rgba = img.convert("RGBA")
    rgba.putalpha(Image.fromarray(alpha_u8, mode="L"))

    if req.mode == "product" and req.keep_shadow:
        rgba = add_soft_shadow(rgba)

    buf = io.BytesIO()
    rgba.save(buf, format="PNG")
    img_b64 = base64.b64encode(buf.getvalue()).decode()

    qc = quick_qc(alpha, req.mode)
    return {
        "image_base64": img_b64,
        "metadata": {
            "mode": req.mode,
            "matting_strength": matting,
            "keep_shadow": req.keep_shadow,
            "foreground_coverage": qc["foreground_coverage"],
            "edge_gradient": qc["edge_gradient"],
            "warnings": qc["warnings"],
        },
        "warning": qc["warnings"][0] if qc["warnings"] else None,
    }
