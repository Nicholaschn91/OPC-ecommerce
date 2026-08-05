# Dify 合规检测技能

## 核心功能
- 组装 Dify API 所需的完整输入载荷
- 调用 Dify Workflow/Chatflow API（阻塞模式）
- 解析结构化输出 → 飞书字段回写 + 事件发布
- 处理三级风险的差异化动作

## Dify 应用配置
```yaml
# 来自 dify_compliance_agent.yml
app:
  mode: chat
  name: "Listing 合规审核"
  description: "跨境电商 Listing 合规审核智能体"
  icon: "🛡️"
  features:
    file_upload:
      enabled: true
      allowed_file_extensions: [.txt, .csv]
      allowed_file_types: [document]
  workflow:
    retriever_resource:
      enabled: true
    model:
      name: gpt-4o-mini
      provider: ""
      temperature: 0.5
```

## 环境变量
```env
# ~/.hermes/.env 或 ~/.workbuddy/skills/dify-compliance/.env
DIFY_API_KEY=app-xxxxxxxxxxxx
DIFY_BASE_URL=https://your-dify-domain  # 或 http://localhost:5000
DIFY_WORKFLOW_ID=compliance-check-v1    # 可选，若用 chat-messages 则不需要
DIFY_APP_TYPE=chatflow                  # workflow / chatflow
```

## 调用接口（供 Agent 内部调用）

### Python
```python
from skills.dify_compliance import DifyComplianceClient

client = DifyComplianceClient()

result = client.run_compliance_check(
    spu_id="SPU-12345",
    feishu_record_id="rec_xxxxx",
    platforms=["amazon", "etsy", "ebay"],
    copy_fields={...},      # 见 AGENT.md 第 2 节
    visual_prompts={...},   # 可选
    aplus_content={...},    # 可选
    scan_scope="visual_final"  # draft / visual_final / full
)

# result = {
#   "overall_status": "需修正",
#   "summary": {"fatal": 0, "high": 2, "medium": 5},
#   "details": [...],
#   "report_markdown": "## 合规扫描报告..."
# }
```

### CLI（调试用）
```bash
python -m skills.dify_compliance.cli \
  --spu SPU-12345 \
  --record rec_xxxxx \
  --platforms amazon,etsy,ebay \
  --scope visual_final \
  --copy-file copy_payload.json
```

## 内部实现结构
```
skills/dify-compliance/
├── SKILL.md
├── __init__.py
├── client.py          # DifyComplianceClient
├── parser.py          # 结果解析、风险分级映射
├── feishu_writer.py   # 飞书字段回写
├── event_publisher.py # 事件发布
└── cli.py             # CLI 入口
```

## 风险分级映射（与 Dify 输出一致）

| Dify Level | 本地 Level | 处理动作 |
|------------|------------|----------|
| 一级（致命） | fatal | CIRCUIT_BREAK 立即熔断，禁止输出 |
| 二级（高危） | high | 标注 ⚠️ + 给出替代词，**需用户确认"替换"**后回写 |
| 三级（中危） | medium | 静默替换 / 标注建议，不阻塞流程 |

## 错误处理
| 错误类型 | 处理 |
|----------|------|
| Dify API 429 | 指数退避重试 3 次（10s/30s/60s） |
| Dify API 5xx | 重试 2 次，失败则返回 `{"overall_status": "ERROR", "error": "..."}` |
| 网络超时 | 60s 总超时，分段连接/读取超时 |
| 返回格式不符 | 记录原始响应，返回 `ERROR` 状态，人工介入 |

## 限流与配额
- 单 SPU 单次扫描 ≤ 1 次并发
- 分钟级并发 ≤ 5 SPU
- 免费额度用尽 → 返回 `QUOTA_EXCEEDED`，Boss 暂停调度

## 版本记录
| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-07-13 | 初版：三层扫描、三级风险、飞书回写、事件发布 |