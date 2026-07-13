# Image Background Remover Skill

## 描述
智能背景移除技能，支持多种模型（RemBG, SAM, BiRefNet），输出透明底 PNG，供电商主图、垫图、A+ 模块使用。

## 触发词
- "移除背景"
- "抠图"
- "透明底"
- "去背景"

## 核心能力
- 多模型支持：RemBG (u2net, isnet), SAM, BiRefNet, ModNet
- 批量处理：支持文件夹/列表批量抠图
- 精细边缘：毛发、半透明物体、复杂边缘优化
- 白底/透明底双输出
- 边缘羽化/平滑
- 前景抠图质量评分

## 模型对比

| 模型 | 适用场景 | 速度 | 精度 | 显存 |
|------|----------|------|------|------|
| u2net | 通用、人像、物品 | 快 | 高 | 低 |
| isnet | 通用、细节丰富 | 中 | 极高 | 中 |
| sam | 任意分割、交互式 | 慢 | 极高 | 高 |
| birefnet | 高精度、毛发、半透明 | 中 | 极高 | 中 |
| modnet | 视频、实时 | 极快 | 中 | 低 |

## 处理流程

```
输入图片
    ↓
预处理（Resize ≤ 2048, 归一化）
    ↓
模型推理（获取 Alpha Matte）
    ↓
后处理
  - 边缘羽化 (Gaussian Blur, radius=2)
  - 小噪点去除 (Morphology Open, kernel=3)
  - 孔洞填充 (Morphology Close, kernel=5)
  - Alpha 阈值化 (可选)
    ↓
输出
  - 透明底 PNG (RGBA)
  - 可选：白底 JPG (RGB)
  - Alpha Mask (单通道)
```

## API 接口

### Python
```python
from skills.image_bg_remover import BackgroundRemover

remover = BackgroundRemover(model="isnet")  # 默认 isnet

# 单张
result = remover.remove(
    image_path="input.jpg",
    output_dir="output/",
    model="isnet",        # 可选覆盖
    alpha_matting=True,   # 精细边缘
    foreground_threshold=240,
    background_threshold=10,
    erode_size=10
)
# result = {"rgba_path": "...", "mask_path": "...", "white_bg_path": "..."}

# 批量
results = remover.batch_remove(
    image_paths=["1.jpg", "2.png", "3.webp"],
    output_dir="output/",
    model="birefnet",     # 高精度模式
    n_workers=4
)
```

### CLI
```bash
# 单张
python -m skills.image_bg_remover --input input.jpg --output output/ --model isnet

# 批量文件夹
python -m skills.image_bg_remover --input-dir ./images --output-dir ./output --model birefnet --workers 4

# 指定输出格式
python -m skills.image_bg_remover -i in.jpg -o out/ --format png,jpg --white-bg
```

## 核心参数

| 参数 | 默认 | 说明 |
|------|------|------|
| `model` | `isnet` | u2net/isnet/sam/birefnet/modnet |
| `alpha_matting` | `True` | 精细边缘抠图 |
| `foreground_threshold` | 240 | 前景阈值 |
| `background_threshold` | 10 | 背景阈值 |
| `erode_size` | 10 | 腐蚀大小 |
| `output_format` | `png` | png/jpg/webp |
| `white_bg` | `False` | 是否额外输出白底图 |
| `n_workers` | 4 | 批量并发数 |

## 依赖
```bash
pip install rembg[gpu] onnxruntime-gpu opencv-python pillow numpy
# 或 CPU 版
pip install rembg[cpu] opencv-python pillow numpy
```

## 质量评分指标
| 指标 | 优秀 | 合格 | 不合格 |
|------|------|------|--------|
| 边缘锯齿 | 无 | 轻微 | 明显 |
| 半透明保留 | 完美 | 大部分 | 丢失 |
| 细节保留 (毛发) | 完整 | 基本完整 | 断裂 |
| 色彩溢出 | 无 | 极微 | 明显 |
| Alpha 干净度 | 纯净 | 极少噪点 | 噪点多 |

## 输出格式
```json
{
  "success": true,
  "rgba_path": "output/image_rgba.png",
  "mask_path": "output/image_mask.png",
  "white_bg_path": "output/image_white.jpg",
  "metrics": {
    "edge_score": 0.95,
    "transparency_score": 0.98,
    "detail_score": 0.92,
    "overall": 0.95
  },
  "model": "isnet",
  "processing_time": 2.3
}
```

## 批量处理规范
- 输入：文件夹路径 / 文件列表 / CSV (含路径列)
- 输出：保持原目录结构 / 统一输出目录
- 命名：`{original_name}_rgba.png`, `{original_name}_mask.png`
- 并发：默认 4，显存不足时自动降级
- 进度：tqdm 进度条 + 日志

## 版本记录
| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-07-13 | 初版：多模型抠图、批量、质量评分 |