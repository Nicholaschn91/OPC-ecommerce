# Vision ALT Generator Skill

## 描述
视觉模型生成图片 ALT 文本技能，调用 GLM-4V / Qwen-VL / GPT-4o 等多模态模型生成 ≤125 字符的纯英文 ALT 文本，供电商主图、垫图、A+ 模块使用。

## 触发词
- "生成ALT"
- "图片描述"
- "ALT文本"

## 核心能力
- 多模型支持：GLM-4V (NVIDIA NIM) / Qwen-VL (百炼) / GPT-4o
- 结构化输出：≤125 字符纯英文 ALT
- 批量处理：支持文件夹/列表批量生成
- 模板化提示词：含产品名称、品类、材质、核心卖点
- 质量门禁：长度检查、关键词覆盖、合规检查

## 调用链路
```
图片 URL / Base64 / 本地路径
    ↓
Vision Model (GLM-4V / Qwen-VL / GPT-4o)
    ↓
结构化 ALT 文本 (≤125 chars, pure English)
    ↓
质量门禁 (长度、关键词覆盖、合规)
    ↓
写入飞书 {Platform}_RefImage_ALT_Img1~N 字段
```

## API 接口

### Python
```python
from skills.vision_alt_generator import VisionALTGenerator

generator = VisionALTGenerator(model="glm-4v")  # glm-4v / qwen-vl / gpt-4o

# 单张生成
result = generator.generate_alt(
    image_path="product.jpg",
    product_info={
        "name": "Insulated Water Bottle",
        "category": "Home & Kitchen",
        "materials": ["stainless steel", "BPA-free plastic"],
        "key_features": ["vacuum insulation", "leak-proof", "24h cold"]
    }
)
# result = {"alt_text": "A stainless steel vacuum insulated water bottle with matte finish, leak-proof screw lid, shown on white background"}

# 批量生成
results = generator.batch_generate(
    image_paths=["1.jpg", "2.jpg", "3.jpg"],
    product_infos=[{"name": "...", "category": "..."}, ...],
    n_workers=2
)
```

### CLI
```bash
# 单张
python -m skills.vision_alt_generator --image product.jpg --name "Water Bottle" --category "Home"

# 批量（CSV: image_path,product_name,category,materials,features）
python -m skills.vision_alt_generator --csv batch.csv --output alts.json
```

## 视觉模型对比

| 模型 | 提供商 | 上下文 | 速度 | 精度 | 成本 |
|------|--------|--------|------|------|------|
| GLM-4V | NVIDIA NIM | 1M | 中 | 极高 | 免费额度 |
| Qwen-VL | 百炼 | 32K | 快 | 高 | 按量 |
| GPT-4o | OpenAI | 128K | 中 | 极高 | 按量 |
| GLM-4V-9B | 本地 | 1M | 慢 | 高 | 显存 |

## Prompt 模板

```text
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

## 强制正向关键词（全局叠加）

### 皮肤真实度
```
real human hands, natural skin texture, subtle skin pores, faint skin lines, natural uniform skin tone, anatomically correct fingers, standard joint proportion, soft natural light penetration, no skin reflection distortion, photorealistic, non-plastic skin
```

### 画面质感
```
commercial product photography, ultra-realistic, 8K, sharp focus, soft indoor natural daylight, consistent scene lighting, clean minimalist home background, stable motion, no blurry, no deformation, true-to-life texture
```

### 全局负面避坑词
```
cartoon, anime, 3d render, CGI, plastic skin, fake smooth skin, deformed hands, extra fingers, missing fingers, bright fake skin, inconsistent light, overexposure, filter, fantasy effect, blurry texture
```

## 输出格式
```json
{
  "success": true,
  "alt_text": "A stainless steel vacuum insulated water bottle with matte finish, leak-proof screw lid, shown on white background",
  "char_count": 112,
  "keywords_covered": ["stainless steel", "vacuum insulated", "leak-proof", "matte finish"],
  "compliance": "PASS",
  "model": "glm-4v",
  "processing_time": 1.8
}
```

## 质量门禁
| 检查项 | 标准 | 不通过处理 |
|--------|------|------------|
| 字符数 | ≤125 | 截断/重写 |
| 纯英文 | 是 | 重写 |
| 关键词覆盖 | 材质+功能+视觉 ≥3个 | 重写 |
| 合规 | 无负面词 | 重写 |
| 主观词 | 无 | 移除 |

## 环境变量
```env
VISION_MODEL=glm-4v              # glm-4v / qwen-vl / gpt-4o
GLM4V_API_KEY=your_nvidia_nim_key
GLM4V_BASE_URL=https://integrate.api.nvidia.com/v1
QWEN_VL_API_KEY=your_bailian_key
OPENAI_API_KEY=your_openai_key
VISION_MODEL_TIMEOUT=60
VISION_MAX_CONCURRENT=2
```

## 依赖
```bash
pip install openai requests aiohttp pillow aiofiles tqdm
```

## 版本记录
| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-07-13 | 初版：多模型ALT生成、质量门禁、合规检查 |