# Image Uploader Skill

## 描述
多图床图片上传技能，支持 ImgBB、自建 CDN、飞书临时存储、S3/R2、Cloudflare Images 等多种后端。

## 触发词
- "上传图片"
- "图床上传"
- "图片托管"

## 核心能力
- 多后端支持：ImgBB / S3 / R2 / Cloudflare Images / 飞书临时 / 自建 CDN
- 自动重试 / 指数退避
- 多 Key 轮转（ImgBB 5 Key 轮转）
- 上传后自动返回 CDN URL + Base64 Data URI
- 批量上传 / 并发控制
- 失败自动切换备用图床

## 支持的存储后端

| 后端 | 适用场景 | 优点 | 缺点 |
|------|----------|------|------|
| **ImgBB** | 临时、测试、小批量 | 免费、免注册、API 简单 | 限流、非永久、无 CDN |
| **S3 / R2** | 生产、大批量、永久 | 可控、CDN、永久、便宜 | 需配置桶、权限 |
| **Cloudflare Images** | 生产、自动变体、CDN | 自动 WebP/AVIF、全球 CDN、变体 | 计费复杂、需 CF 账号 |
| **飞书临时** | 内部流转、审核 | 免上传、直接写字段 | 仅飞书内可访问、有期限 |
| **自建 CDN** | 完全可控、域名自定 | 完全控制、域名品牌 | 运维成本高 |

## 核心能力

### 1. 单图上传
```python
from skills.image_uploader import ImageUploader

uploader = ImageUploader(
    primary="r2",           # 主存储
    fallback=["imgbb", "cf_images"],  # 备用
    imgbb_keys=[KEY1, KEY2, KEY3, KEY4, KEY5]  # 5 Key 轮转
)

result = uploader.upload(
    image_path="product_main.png",
    target="main",          # main / lifestyle / aplus / thumbnail
    platform="amazon",      # 用于命名规范
    metadata={"spu_id": "SPU-123", "type": "main"}
)
# result = {"url": "https://cdn.xxx/SPU-123_main.png", "base64": "data:image/png;base64,...", "backend": "r2"}
```

### 2. 批量上传
```python
results = uploader.batch_upload(
    image_paths=["1.png", "2.png", "3.png"],
    target="lifestyle",
    platform="amazon",
    n_workers=4
)
```

### 3. 飞书临时字段写入
```python
# 直接写入飞书 Base A 临时图片字段
uploader.upload_to_feishu_temp(
    image_path="product_main.png",
    record_id="rec_xxxxx",
    field_name="临时主图"
)
```

## 存储后端配置

### ImgBB (5 Key 轮转)
```env
IMGBB_KEY_1=xxx
IMGBB_KEY_2=xxx
IMGBB_KEY_3=xxx
IMGBB_KEY_4=xxx
IMGBB_KEY_5=xxx
```

### S3 / R2
```env
R2_ACCOUNT_ID=xxx
R2_ACCESS_KEY_ID=xxx
R2_SECRET_ACCESS_KEY=xxx
R2_BUCKET=opc-images
R2_PUBLIC_URL=https://pub-xxx.r2.dev
R2_ENDPOINT=https://xxx.r2.cloudflarestorage.com
```

### Cloudflare Images
```env
CF_IMAGES_ACCOUNT_ID=xxx
CF_IMAGES_API_TOKEN=xxx
CF_IMAGES_DOMAIN=images.xxx.workers.dev
```

### Cloudflare R2 (推荐生产)
```env
R2_ACCOUNT_ID=xxx
R2_ACCESS_KEY_ID=xxx
R2_SECRET_ACCESS_KEY=xxx
R2_BUCKET=opc-images
R2_PUBLIC_URL=https://images.mydomain.com
R2_ENDPOINT=https://xxx.r2.cloudflarestorage.com
```

### 飞书临时存储
```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
FEISHU_BASE_ID=ONy9bZ0oFaaiSEsf4ggcs61enRc
FEISHU_TABLE_ID=tbl75glY29VulRLm
```

## 文件命名规范

```
{spu_id}_{type}_{index}.{ext}

示例：
SPU-12345_main_1.png
SPU-12345_lifestyle_1.png
SPU-12345_lifestyle_2.png
SPU-12345_aplus_1.png
SPU-12345_thumbnail_1.png
```

## 平台/类型映射

| 类型 | 说明 | 尺寸 | 背景 |
|------|------|------|------|
| `main` | 主图 | 1024x1024 | 白底 |
| `lifestyle` | 场景图 | 1024x1024 | 生活场景 |
| `aplus_large` | A+ 大图 | 2928x1200 | 按需 |
| `aplus_standard` | A+ 标准 | 1600x1200 | 按需 |
| `aplus_dual` | A+ 双图 | 1300x700 | 按需 |
| `aplus_carousel` | A+ 轮播 | 2928x1200 | 按需 |
| `aplus_hotspot` | A+ 热点 | 2928x1200 | 按需 |
| `thumbnail` | 缩略图 | 400x400 | 白底/透明 |

## 关键规则

1. **上传后必须返回**：CDN URL + Base64 Data URI（供 Agnes AI / 飞书写入）
2. **失败自动切换**：主存储失败 → 依次尝试备用存储
3. **ImgBB 5 Key 轮转**：单 Key 限流自动切下一个
4. **文件命名**：`{spu_id}_{type}_{index}.{ext}`
4. **Base64 输出**：`data:image/png;base64,xxxxx`（供 Agnes AI 图生图 / 飞书写入）
5. **幂等性**：同路径同配置二次上传返回相同 URL

## CLI 调用

```bash
# 单张
python -m skills.image_uploader --input product_main.png --type main --spu SPU-12345

# 批量
python -m skills.image_uploader --input-dir ./images --spu SPU-12345 --type main

# 飞书临时字段
python -m skills.image_uploader --input product.jpg --feishu-record rec_xxx --feishu-field "临时主图"
```

## 输出格式
```json
{
  "success": true,
  "url": "https://images.mydomain.com/SPU-12345_main_1.png",
  "base64": "data:image/png;base64,iVBORw0KGgo...",
  "backend": "r2",
  "spu_id": "SPU-12345",
  "type": "main",
  "width": 1024,
  "height": 1024,
  "size_bytes": 245760
}
```

## 技能元数据
```yaml
name: image-uploader
description: "多图床图片上传 — ImgBB/S3/R2/CF Images/飞书临时"
version: "1.0.0"
triggers:
  - "上传图片"
  - "图床上传"
  - "图片托管"
capabilities:
  - multi_backend_upload
  - batch_upload
  - base64_output
  - feishu_temp_write
limits:
  max_file_size: 20MB
  max_batch: 50
  concurrent: 4
```