# Image Post-Processor Skill

## 描述
商品采集完成后的图片后处理技能，负责：
1. 去除图片背景（白底/透明底）
2. 统一图片尺寸规格（按平台规范）
3. 调用视觉模型生成详尽 ALT 文本
4. 输出标准化图片包供后续环节使用

## 触发词
- "处理图片"
- "图片后处理"
- "去除背景"
- "统一尺寸"
- "生成ALT"

## 核心能力
- **背景移除**: RemBG (u2net/isnet) / SAM / 专用 API，fallback 级联
- **尺寸标准化**: 主图 1024x1024 白底 / 垫图 1024x1024 透明底 / A+ 模块按 Track 规范
- **ALT 生成**: GLM-4V / Qwen-VL / GPT-4o，≤125 字符纯英文
- **质检**: 背景纯净、尺寸达标、ALT 覆盖核心卖点、无水印/边框/文字
- **上传 CDN**: ImgBB / 自建 / 飞书临时
- **Base64 输出**: `data:image/png;base64,...` 供 Agnes AI / 飞书写入

## 处理流水线
```
原图下载（并发、重试、去重、校验）
    ↓
背景移除（RemBG/SAM/专用API）
    ↓
尺寸标准化
    - 主图：1024×1024 / 1:1 / 白底 #FFFFFF / PNG
    - 垫图：1024×1024 / 1:1 / 透明底 / PNG
    - A+ 模块：1600×1200 (4:3) / 1300×700 (16:9) / 2928×1200 (21:9)
    ↓
视觉模型生成 ALT（GLM-4V / Qwen-VL / GPT-4o）
    - 提示词模板：含产品名称、品类、材质、核心卖点
    - 输出：≤125 字符纯英文 ALT
    ↓
质检
    - 背景是否纯净（白/透明）
    - 尺寸是否达标
    - ALT 是否包含核心卖点/材质/功能
    - 无水印、无边框、无文字叠加
    ↓
上传 CDN / 图床（ImgBB / 自建 / 飞书临时）
    ↓
生成 Base64 Data URI（供后续 Visual Agent / Agnes / 飞书写入）
    ↓
写入飞书 Base A 临时字段 `图片素材包_JSON`
```

## 技术规范

| 项 | 规范 |
|----|------|
| **背景移除** | RemBG (u2net/isnet) / SAM / 专用 API，fallback 级联 |
| **主图尺寸** | 1024×1024 / 1:1 / 白底 #FFFFFF / PNG |
| **垫图尺寸** | 1024×1024 / 1:1 / 透明底 / PNG |
| **A+ 模块** | 1600×1200 (4:3) / 1300×700 (16:9) / 2928×1200 (21:9) |
| **ALT 文本** | ≤125 字符 / 纯英文 / 含：材质、核心功能、视觉特征、使用场景 |
| **输出格式** | PNG (无损) / WebP (可选，质量 90) |
| **并发限制** | 下载 5 并发 / 视觉模型 2 并发 / 上传 3 并发 |
| **失败重试** | 下载 3 次 / 模型 2 次 / 上传 3 次 |
| **超时** | 下载 30s / 模型 60s / 上传 30s |

## 视觉模型 Prompt 模板

```
你是专业电商图片描述师。请为以下商品图片生成 ≤125 字符的纯英文 ALT 文本。

商品信息：
- 名称：{product_name}
- 品类：{category}
- 材质：{materials}
- 核心卖点：{key_features}

图片内容提示：{image_hint}

要求：
1. 纯英文，≤125 字符
2. 必须包含：材质、核心功能、视觉特征、使用场景
3. 禁止：主观形容词、营销词、品牌名、促销词
4. 格式：单句，无标点符号结尾

示例：
"A stainless steel vacuum insulated water bottle with matte finish, leak-proof screw lid, shown on white background"
```

## 输出格式

```json
{
  "spu_id": "SPU-12345",
  "feishu_record_id": "rec_xxxxx",
  "processed_images": [
    {
      "original_url": "https://...",
      "processed_url": "https://cdn.xxx/SPU-12345_img1_white_1024x1024.png",
      "base64_data": "data:image/png;base64,iVBORw0KGgo...",
      "alt_text": "A stainless steel vacuum insulated water bottle with matte finish, leak-proof screw lid, shown on white background",
      "dimensions": {"width": 1024, "height": 1024},
      "format": "png",
      "background_removed": true,
      "processing_timestamp": "2026-07-13T10:30:00Z"
    }
  ],
  "processing_status": "completed",
  "total_images": 5,
  "failed_images": 0
}
```

## 技能依赖

| 技能 | 用途 |
|------|------|
| `image-bg-remover` | 背景移除（RemBG/SAM） |
| `image-resizer` | 尺寸标准化 |
| `vision-alt-generator` | ALT 文本生成（GLM-4V/Qwen-VL/GPT-4o） |
| `image-uploader` | 图床上传 |
| `base64-encoder` | Base64 Data URI 生成 |
| `feishu-writer` | 飞书写入 |

## 版本记录
| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-07-13 | 初版：背景移除、尺寸标准化、ALT生成、CDN上传、Base64输出 |