# Agnes AI 图像/视频生成技能

## 核心端点

| 模型 | 端点 | 方式 | 说明 |
|------|------|------|------|
| **agnes-image-2.1-flash** | `POST /v1/images/generations` | 同步 | 文生图、图生图（接受 Base64 Data URI） |
| **agnes-video-v2.0** | `POST /v1/videos` | 异步 | 文生视频、图生视频、关键帧动画，需轮询等待 |

## API Key 与 Base URL

| 项 | 值 |
|----|-----|
| **Base URL** | `https://api.agnes.ai`（或本地代理） |
| **API Key** | 存储在 `~/.workbuddy/skills/agnes-image/.env` |

> **免费额度铁律**：
> - 图片 20 RPM（请求/分钟），429 立即退避 60s
> - 批量生成串行执行，单请求间隔 2-3s
> - 视频异步任务，提交后每 10s 轮询一次，超时 300s

---

## 1. 图像生成 (agnes-image-2.1-flash)

### 1.1 文生图

```bash
curl -X POST "https://api.agnes.ai/v1/images/generations" \
  -H "Authorization: Bearer $AGNES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "A beautiful sunset over mountains, photorealistic, 8k",
    "negative_prompt": "blurry, low quality, watermark",
    "width": 1024,
    "height": 1024,
    "steps": 25,
    "cfg_scale": 7.0,
    "sampler": "euler_a",
    "seed": -1,
    "n": 1
  }'
```

### 1.2 图生图 (Image-to-Image)

**关键**：`image` 字段接受 **Base64 Data URI** 格式：`data:image/png;base64,xxxxx`

```bash
curl -X POST "https://api.agnes.ai/v1/images/generations" \
  -H "Authorization: Bearer $AGNES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-image-2.1-flash",
    "prompt": "Transform into cyberpunk style, neon lights, rain",
    "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...",
    "strength": 0.75,
    "width": 1024,
    "height": 1024,
    "steps": 20,
    "cfg_scale": 7.0
  }'
```

| 参数 | 说明 | 推荐值 |
|------|------|--------|
| `strength` | 重绘强度 0-1，越大越不像原图 | 0.6-0.8 |
| `image` | **必须** Base64 Data URI | `data:image/png;base64,...` |

### 1.3 批量生成铁律

```python
# 伪代码：严格串行 + 限速
for prompt in prompts:
    result = call_agnes_image(prompt)
    if result.status == 429:
        sleep(60)
        result = call_agnes_image(prompt)  # 重试一次
    sleep(2.5)  # 2-3s 间隔
```

---

## 2. 视频生成 (agnes-video-v2.0)

### 2.1 文生视频

```bash
# 提交任务
curl -X POST "https://api.agnes.ai/v1/videos" \
  -H "Authorization: Bearer $AGNES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-v2.0",
    "prompt": "Camera orbits around a futuristic car, neon city background, 4k",
    "negative_prompt": "blurry, distorted, low fps",
    "width": 1280,
    "height": 720,
    "num_frames": 16,
    "fps": 8,
    "seed": -1
  }'

# 响应：{"task_id": "vid_xxxxx", "status": "pending"}
```

### 2.2 图生视频 / 关键帧动画

```bash
curl -X POST "https://api.agnes.ai/v1/videos" \
  -H "Authorization: Bearer $AGNES_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "agnes-video-v2.0",
    "prompt": "Camera slowly zooms in, subtle parallax",
    "image": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUg...",  # 起始帧
    "end_image": "data:image/png;base64,...",  # 可选：结束帧
    "width": 1024,
    "height": 576,
    "num_frames": 24,
    "fps": 12
  }'
```

### 2.3 轮询获取结果

```bash
# 每 10s 轮询一次
curl "https://api.agnes.ai/v1/videos/vid_xxxxx" \
  -H "Authorization: Bearer $AGNES_API_KEY"

# 成功响应：
# {
#   "task_id": "vid_xxxxx",
#   "status": "succeeded",
#   "video_url": "https://cdn.agnes.ai/xxx.mp4",
#   "cover_url": "https://cdn.agnes.ai/xxx.jpg"
# }
```

---

## 3. Visual Agent 集成规范

### 3.1 何时调用

| 阶段 | 场景 | 调用方式 |
|------|------|----------|
| **批次 2 (7-Shot)** | 生成 Prompt 后，可选同步生成预览图 | 文生图，每图位 1 张 |
| **批次 3 (A+)** | A+ 模块图片生成 | 文生图，按 Slot 数量 |
| **垫图处理** | 垫图风格迁移/增强 | 图生图 (strength 0.3-0.5) |
| **视频需求** | 产品展示短视频/广告素材 | 文生视频/图生视频 |

### 3.2 调用封装 (Python 示例)

```python
# tools/agnes_client.py
import os, time, base64, requests
from pathlib import Path

AGNES_API_KEY = os.environ.get("AGNES_API_KEY")
BASE_URL = "https://api.agnes.ai"  # 或本地代理

def img2img_base64(image_path: str, prompt: str, strength=0.7):
    """读取本地图片 → Base64 Data URI → 图生图"""
    b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
    data_uri = f"data:image/png;base64,{b64}"
    
    resp = requests.post(
        f"{BASE_URL}/v1/images/generations",
        headers={"Authorization": f"Bearer {AGNES_API_KEY}"},
        json={
            "model": "agnes-image-2.1-flash",
            "prompt": prompt,
            "image": data_uri,
            "strength": strength,
            "width": 1024,
            "height": 1024,
            "steps": 20
        },
        timeout=60
    )
    if resp.status_code == 429:
        time.sleep(60)
        return img2img_base64(image_path, prompt, strength)
    return resp.json()

def video_submit(prompt: str, image_path: str = None, end_image_path: str = None):
    """提交视频生成任务"""
    payload = {
        "model": "agnes-video-v2.0",
        "prompt": prompt,
        "width": 1280,
        "height": 720,
        "num_frames": 16,
        "fps": 8
    }
    if image_path:
        b64 = base64.b64encode(Path(image_path).read_bytes()).decode()
        payload["image"] = f"data:image/png;base64,{b64}"
    if end_image_path:
        b64 = base64.b64encode(Path(end_image_path).read_bytes()).decode()
        payload["end_image"] = f"data:image/png;base64,{b64}"
    
    resp = requests.post(
        f"{BASE_URL}/v1/videos",
        headers={"Authorization": f"Bearer {AGNES_API_KEY}"},
        json=payload,
        timeout=30
    )
    return resp.json()  # {"task_id": "...", "status": "pending"}

def video_poll(task_id: str, interval=10, timeout=300):
    """轮询视频任务"""
    start = time.time()
    while time.time() - start < timeout:
        resp = requests.get(
            f"{BASE_URL}/v1/videos/{task_id}",
            headers={"Authorization": f"Bearer {AGNES_API_KEY}"},
            timeout=15
        )
        data = resp.json()
        if data["status"] == "succeeded":
            return data
        if data["status"] == "failed":
            raise RuntimeError(f"Video generation failed: {data.get('error')}")
        time.sleep(interval)
    raise TimeoutError("Video generation timeout")
```

### 3.3 Visual Agent Prompt 中的引用规范

生成的 Prompt 末尾**必须**包含 Agnes 调用提示（供下游自动化使用）：

```text
[V2 版权垫图声明] [T_47 动作化描述] [P_Base_05 肌肤写真] [P_Scene_01 自然光] --ar 1:1
# AGNES_HINT: img2img(data:image/png;base64,{{ref_image_b64}}), strength=0.65, prompt="..." 
```

---

## 4. 配置文件

### `~/.workbuddy/skills/agnes-image/.env`
```env
AGNES_API_KEY=sk-xxxxxxxxxxxx
AGNES_BASE_URL=https://api.agnes.ai
```

### `~/.hermes/.env` (供 Hermes 模型调用)
```env
AGNES_API_KEY=sk-xxxxxxxxxxxx
```

---

## 5. 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 429 Too Many Requests | 超过 20 RPM | 睡眠 60s 重试，批量强制串行 |
| 视频任务长时间 pending | 队列拥堵 | 增加轮询间隔到 15-20s，超时设 300s+ |
| 图生图完全不像原图 | strength 过高 | 降到 0.5-0.7 |
| Base64 太大导致 413 | 图片分辨率过高 | 预压缩至 1024x1024 以内 |
| 免费额度用完 | 本周配额耗尽 | 等下周重置，或接入付费 Key |

---

## 6. 技能元数据 (供 WorkBuddy/注册表)

```yaml
# SKILL.md 片段
name: agnes-media
description: "Agnes AI 图像/视频生成 — 文生图、图生图、文生视频、关键帧动画"
version: "2.1.0"
triggers:
  - "生成图片"
  - "生成视频"
  - "文生图"
  - "图生图"
  - "文生视频"
  - "AI作图"
capabilities:
  - image_generation
  - image_to_image
  - video_generation
  - keyframe_animation
limits:
  rpm: 20
  video_timeout: 300
  retry_on_429: 60
```