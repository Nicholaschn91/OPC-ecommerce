# Image URL to Base64 Skill

## 描述
将图片 URL/本地文件路径转换为 Base64 Data URI，供后续视觉模型、Agnes AI、飞书写入使用。

## 触发词
- "图片转base64"
- "URL转base64"
- "图片转datauri"

## 核心能力
- 支持 HTTP/HTTPS URL 下载 → Base64
- 支持本地文件路径 → Base64
- 支持飞书多维表格图片字段 URL → Base64
- 自动识别 MIME 类型
- 大文件分块处理
- 缓存机制（避免重复下载）

## API 接口

### Python
```python
from skills.image_url_to_base64 import ImageToBase64Converter

converter = ImageToBase64Converter()

# 单张转换
result = converter.url_to_base64("https://example.com/image.png")
# result = "data:image/png;base64,iVBORw0KGgo..."

# 批量转换
results = converter.batch_convert([
    "https://example.com/1.png",
    "https://example.com/2.jpg",
    "/local/path/image.png"
])

# 飞书图片字段转换
result = converter.feishu_field_to_base64(feishu_record, "图片字段名")
```

### CLI
```bash
# 单张
python -m skills.image_url_to_base64 --url "https://example.com/image.png"

# 批量（文件包含 URL 列表）
python -m skills.image_url_to_base64 --file urls.txt

# 本地文件
python -m skills.image_url_to_base64 --file /path/to/image.png
```

## 核心配置

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `timeout` | 30s | 下载超时 |
| `max_size` | 50MB | 单文件最大限制 |
| `cache_dir` | `~/.cache/image2base64` | 缓存目录 |
| `cache_ttl` | 7天 | 缓存过期 |
| `max_concurrent` | 5 | 并发下载数 |
| `retry` | 3次 | 失败重试 |

## 环境变量
```env
IMAGE_BASE64_CACHE_DIR=~/.cache/image2base64
IMAGE_BASE64_MAX_SIZE=52428800
IMAGE_BASE64_TIMEOUT=30
```

## 依赖
- `requests` / `httpx`
- `aiofiles` (异步文件)
- `PIL` (MIME 验证)

## 输出格式
```json
{
  "success": true,
  "data_uri": "data:image/png;base64,iVBORw0KGgo...",
  "mime_type": "image/png",
  "size_bytes": 102400,
  "width": 1024,
  "height": 1024,
  "source": "https://example.com/image.png",
  "cached": false
}
```

## 错误处理
| 错误类型 | 处理 |
|----------|------|
| 下载超时 | 重试 3 次，间隔 2s/5s/10s |
| 404/403 | 记录错误，返回失败标记 |
| 文件过大 | 自动压缩或拒绝 |
| MIME 不匹配 | 尝试从内容推断 |
| Base64 编码失败 | 记录错误，跳过 |

## 缓存策略
- Key: `sha256(url)` 或 `sha256(file_content)`
- 存储: `{cache_dir}/{key}.json` (含 data_uri, metadata)
- TTL: 7天，超时自动清理

## 版本记录
| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-07-13 | 初版：URL/本地文件 → Base64，缓存，批量 |