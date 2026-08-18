#!/usr/bin/env python3
"""bria_rmbg_server.py — remove_background 的 FastAPI 服务化封装

复用 bria_rmbg_cutout.py 的**已验证内核**（MODE_PRESETS / matting_strength 边缘锐化 /
质量自检+阈值 / 重试降级兜底 / DPI 校正 / 结构化 metadata），对外暴露 Agent Tool
Definition 约定的 POST /remove_background 接口。

修复了原始 FastAPI 骨架的 bug：
  - BRIA pipeline 不接受 `matting` 参数 → 改用共享内核（matting_strength 真正作用到 alpha）
  - matting_strength 原只计算未作用 → 现已在 _apply_matting 中生效
  - keep_shadow 原未使用 → product 模式可合成软阴影（透明 PNG 内含）
  - 补齐 阈值判定 / 重试降级 / DPI 校正 / 真实图片加载（http(s) URL / data: base64 / 本地路径）

依赖（与内核一致）：
  pip install torch torchvision pillow transformers numpy kornia
  pip install fastapi uvicorn

启动：
  D:/anaconda/python.exe -m uvicorn bria_rmbg_server:app --host 127.0.0.1 --port 8123

接口：
  POST /remove_background
    body: {
      "image_url": "<http(s) URL | data:image/png;base64,... | 本地路径>",
      "mode": "pod_print | product | portrait",   # 默认 pod_print
      "keep_shadow": false,                         # 仅 product 模式生效
      "matting_strength": null,                     # 0..1，默认按 mode 预设
      "out": null                                   # 可选：落盘透明 PNG 路径
    }
  返回：
    { "image_base64": "<PNG base64>", "metadata": {...}, "warning": "..." | null }

  GET /health  -> {"status":"ok","modes":[...]}
"""
import os
import io
import base64
import tempfile
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

# ---- 复用已验证内核（同一目录）--------------------------------------------
import bria_rmbg_cutout as core

app = FastAPI(title="BRIA-RMBG-2.0 remove_background service", version="1.0")


@app.on_event("startup")
def _on_startup():
    """启动时预加载模型到缓存；失败不阻断启动（首请求时重试）。"""
    try:
        core.warmup()
    except Exception as e:  # noqa: BLE001
        print(f"[warn] BRIA model warmup failed: {e}")


# ---- 输入解析：URL / base64 / 本地路径 -> 本地临时文件 ----------------------
def _resolve_input(image_url: str) -> str:
    """把各种来源解析成本地文件路径（返回的路径若是临时文件需调用方清理）。"""
    if image_url.startswith("data:"):
        _, b64 = image_url.split(",", 1)
        data = base64.b64decode(b64)
        fd, p = tempfile.mkstemp(suffix=".png")
        os.write(fd, data)
        os.close(fd)
        return p
    if image_url.startswith("http://") or image_url.startswith("https://"):
        import urllib.request
        data = urllib.request.urlopen(image_url, timeout=30).read()
        fd, p = tempfile.mkstemp(suffix=".png")
        os.write(fd, data)
        os.close(fd)
        return p
    # 本地路径：原样返回
    if not os.path.exists(image_url):
        raise FileNotFoundError(f"本地图片不存在: {image_url}")
    return image_url


# ---- 请求 / 响应模型 -------------------------------------------------------
class RemoveBgRequest(BaseModel):
    image_url: str
    mode: str = "pod_print"
    keep_shadow: bool = False
    matting_strength: Optional[float] = None
    out: Optional[str] = None


@app.post("/remove_background")
def remove_background(req: RemoveBgRequest):
    if req.mode not in core.VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的 mode: {req.mode!r}，可选 {core.VALID_MODES}",
        )

    is_temp = False
    try:
        src = _resolve_input(req.image_url)
        is_temp = (src != req.image_url)
        out_path = req.out or tempfile.mktemp(suffix="_bria.png")

        out_file, meta = core.remove_background(
            src,
            mode=req.mode,
            keep_shadow=req.keep_shadow,
            matting_strength=req.matting_strength,
            out=out_path,
        )

        with open(out_file, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("ascii")

        return {
            "image_base64": img_b64,
            "metadata": meta,
            "warning": meta.get("warning"),
        }
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"remove_background 失败: {repr(e)}")
    finally:
        if is_temp:
            try:
                os.remove(src)
            except OSError:
                pass


@app.get("/health")
def health():
    return {"status": "ok", "modes": core.VALID_MODES,
            "presets": {k: v["matting_strength"] for k, v in core.MODE_PRESETS.items()}}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8123)
