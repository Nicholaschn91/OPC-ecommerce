# Image Resizer Skill

## 描述
智能图片尺寸标准化技能，按电商平台规范自动调整尺寸、比例、格式，输出符合各平台主图、垫图、A+ 模块规范的图片。

## 触发词
- "调整尺寸"
- "统一尺寸"
- "图片压缩"
- "格式转换"

## 核心能力
- 多平台预设：Amazon/Etsy/eBay/Shopify/TikTok Shop
- 多规格输出：主图/垫图/A+模块/缩略图
- 智能裁剪：内容感知裁剪、居中、比例保持
- 格式转换：PNG/JPG/WebP/AVIF
- 压缩优化：质量/大小平衡
- 批量处理

## 平台预设规范

| 平台 | 图片类型 | 尺寸 | 比例 | 格式 | 背景 | 质量 |
|------|----------|------|------|------|------|------|
| **Amazon** | 主图 | 1024x1024 | 1:1 | PNG | 白底 #FFFFFF | 90 |
| Amazon | 垫图 | 1024x1024 | 1:1 | PNG | 透明 | 90 |
| Amazon | A+ Large | 2928x1200 | 21:9 | JPG | 按需 | 85 |
| Amazon | A+ Standard | 1600x1200 | 4:3 | JPG | 按需 | 85 |
| **Etsy** | 主图 | 2000x2000 | 1:1 | JPG | 白底/生活场景 | 85 |
| Etsy | 缩略图 | 570xN | 4:3 | JPG | 按需 | 85 |
| **eBay** | 主图 | 1600x1600 | 1:1 | JPG | 白底 | 85 |
| eBay | 垫图 | 1600x1600 | 1:1 | PNG | 透明 | 90 |
| **Shopify** | 主图 | 2048x2048 | 1:1 | JPG | 白底 | 85 |
| **TikTok Shop** | 主图 | 1080x1080 | 1:1 | JPG | 生活场景 | 85 |

## 通用规格（跨平台）

| 类型 | 尺寸 | 比例 | 用途 |
|------|------|------|------|
| 主图标准 | 1024x1024 | 1:1 | 通用主图 |
| 高清主图 | 2048x2048 | 1:1 | 高清展示 |
| 垫图标准 | 1024x1024 | 1:1 | 透明底垫图 |
| A+ 大图 | 2928x1200 | 21:9 | Amazon A+ |
| A+ 标准 | 1600x1200 | 4:3 | Amazon A+ |
| A+ 双图文 | 1300x700 | 16:9 | Amazon A+ |
| A+ 轮播 | 2928x1200 | 21:9 | Amazon A+ |
| 缩略图 | 400x400 | 1:1 | 列表/搜索 |

## 处理模式

| 模式 | 行为 | 适用场景 |
|------|------|----------|
| `fit` | 等比缩放至目标框内，保留全图 | 完整展示商品 |
| `fill` | 等比缩放填满目标框，超出裁剪 | 垫图、主图 |
| `crop_center` | 居中裁剪至目标比例 | 统一比例 |
| `smart_crop` | 内容感知裁剪（显著性检测） | 模特穿戴、复杂场景 |
| `pad` | 等比缩放+填充背景色 | 需保留完整图像 |

## API 接口

### Python
```python
from skills.image_resizer import ImageResizer

resizer = ImageResizer()

# 单张 - 按平台预设
result = resizer.resize(
    image_path="input.png",
    platform="amazon",
    image_type="main",        # main / lifestyle / aplus_large / aplus_standard / thumbnail
    output_dir="output/"
)
# result = {"path": "...", "width": 1024, "height": 1024, "format": "png"}

# 单张 - 自定义规格
result = resizer.resize_custom(
    image_path="input.png",
    width=1024,
    height=1024,
    mode="fill",              # fit / fill / crop_center / smart_crop / pad
    background="#FFFFFF",     # pad 模式填充色
    format="png",             # png / jpg / webp / avif
    quality=90,
    output_dir="output/"
)

# 批量 - 按平台预设
results = resizer.batch_resize(
    image_paths=["1.png", "2.png", "3.png"],
    platform="amazon",
    types=["main", "lifestyle", "aplus_large"],
    output_dir="output/"
)

# 批量 - 统一规格
results = resizer.batch_resize_custom(
    image_paths=["1.png", "2.png"],
    width=1024,
    height=1024,
    mode="fill",
    background="#FFFFFF",
    format="png",
    quality=90,
    output_dir="output/"
)
```

### CLI
```bash
# 单张 - 平台预设
python -m skills.image_resizer --input input.png --platform amazon --type main --output output/

# 单张 - 自定义
python -m skills.image_resizer -i in.png -o out/ -w 1024 -h 1024 -m fill -bg "#FFFFFF" -f png -q 90

# 批量 - 平台预设
python -m skills.image_resizer --input-dir ./images --platform amazon --types main,lifestyle,aplus --output-dir ./output

# 批量 - 统一规格
python -m skills.image_resizer -i ./images -o ./output -w 1024 -h 1024 -m fill
```

## 核心参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `platform` | - | amazon/etsy/ebay/shopify/tiktok |
| `type` | `main` | main/lifestyle/aplus_large/aplus_standard/aplus_dual/aplus_carousel/aplus_hotspot/thumbnail |
| `width` | - | 自定义宽度 |
| `height` | - | 自定义高度 |
| `mode` | `fill` | fit/fill/crop_center/smart_crop/pad |
| `background` | `#FFFFFF` | pad模式填充色 / 透明用 `transparent` |
| `format` | `png` | png/jpg/webp/avif |
| `quality` | `90` | 1-100 (jpg/webp/avif) |
| `n_workers` | 4 | 并发数 |

## 智能裁剪

- 使用 **显著性检测** 识别商品主体区域
- `smart_crop` 模式自动识别商品主体，保证主体完整在框内
- 支持人脸/商品 logo/品牌标识保护区域

## 输出格式
```json
{
  "success": true,
  "path": "output/image_main.png",
  "width": 1024,
  "height": 1024,
  "format": "png",
  "size_bytes": 245760,
  "original": {"width": 3000, "height": 2000},
  "mode": "fill",
  "platform": "amazon",
  "type": "main"
}
```

## 批量处理规范
- 输入：文件夹 / 文件列表 / CSV (path, platform, type)
- 输出：`{output_dir}/{platform}/{type}/{original_name}.{ext}`
- 命名：`{original_name}_{type}.{ext}` 如 `product_main.png`
- 并发：默认 4
- 进度：tqdm 进度条

## 质检指标
| 指标 | 标准 |
|------|------|
| 尺寸准确性 | 宽高完全匹配目标规格 |
| 比例正确性 | 宽高比完全匹配目标比例 |
| 无畸变 | 商品主体无拉伸/压缩 |
| 背景纯净 | 白底纯净/透明底完全透明 |
| 无黑边/白边 | 裁剪边缘干净 |
| 文件大小 | 符合平台上传限制 |

## 版本记录
| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-07-13 | 初版：多平台预设、智能裁剪、批量 |