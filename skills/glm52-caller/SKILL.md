# GLM-5.2 Caller Skill

## 描述
纯 GLM-5.2 调用封装（NVIDIA NIM，1M 上下文、中英双语）。不含任何任务逻辑——只负责把提示词发给模型并返回结果。

## 触发词
- "调用GLM"
- "GLM分析"
- "长文本处理"

## 核心能力
- 1M 上下文窗口
- 中英双语支持
- 支持长文本分析、总结、翻译
- 无任务逻辑，纯调用封装

## 环境变量
```env
GLM_API_KEY=your_nvidia_nim_key
GLM_BASE_URL=https://integrate.api.nvidia.com/v1
GLM_MODEL=glm-5.2
```

## 调用示例
```python
from skills.glm52_caller import GLM52Client

client = GLM52Client()
response = client.chat([
    {"role": "system", "content": "你是专业的电商文案分析师"},
    {"role": "user", "content": "分析这段文案的合规风险: ..."}
])
```

## 配置文件
```yaml
# SKILL.md 片段
name: glm52-caller
description: "纯 GLM-5.2 调用封装（NVIDIA NIM，1M 上下文、中英双语）"
version: "1.0.0"
triggers:
  - "调用GLM"
  - "GLM分析"
  - "长文本处理"
capabilities:
  - long_context_analysis
  - bilingual_support
  - content_special
limits:
  context_window: 1000000
  rpm: 60
```