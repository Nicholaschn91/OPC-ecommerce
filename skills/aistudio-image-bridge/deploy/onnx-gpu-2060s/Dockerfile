# BRIA-RMBG-2.0 ONNX Runtime GPU 服务
# 针对 RTX 2060 Super 8GB 显存优化, 稳定运行不 OOM
# 兼容 2060S 的 CUDA 11.8 (不使用 CUDA 12.x, 2060S 兼容性差)
FROM mcr.microsoft.com/onnxruntime/server:v1.17.3-cuda11.8-cudnn8

WORKDIR /app

# 精简依赖, 无冗余
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && \
    rm -rf /root/.cache/pip

# 模型通过 volume 挂载, 不进镜像 (换模型/清缓存不用重建镜像)
COPY main.py .

# 缓存目录
RUN mkdir -p /app/cache

EXPOSE 8000

# 单 Worker 启动: ONNX 无需多进程, 避免显存翻倍
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
