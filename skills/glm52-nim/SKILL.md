# GLM-5.2 NIM Skill (百炼 qwen 回退)

## 描述
GLM-5.2 NIM 调用 + 百炼 qwen 回退链路。支持关键词管道处理。

## 触发词
- "关键词管道"
- "词库处理"
- "T1-T5分级"

## 核心能力
- 关键词数据全链路处理：重算衍生指标、百炼 qwen3.7-max 污染分流、T1-T5 自适应分级
- CSV/SQLite/xlsx 三联存储
- 关键词污染审查、聚类、意图分析

## 脚本路径
```
~/.workbuddy/skills/glm52-nim/scripts/
├── glm52.py              # GLM-5.2 NIM 调用
├── clean_keywords.py     # 关键词清洗
├── keyword_pipeline.py   # 关键词管道主流程
```

## 环境变量
```env
GLM52_API_KEY=your_nim_key
GLM52_BASE_URL=https://integrate.api.nvidia.com/v1
BAILIAN_API_KEY=your_bailian_key
BAILIAN_MODEL=qwen-max
```

## 调用示例
```python
from skills.glm52_nim import GLM52NIMPipeline

pipeline = GLM52NIMPipeline()
result = pipeline.process_keywords(
    csv_path="keywords.csv",
    spu_id="SPU-123",
    category="Home Textiles"
)
```