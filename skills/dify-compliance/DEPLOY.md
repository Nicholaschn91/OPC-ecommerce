# Dify 合规检测技能部署文档

## 概述
本文档描述 Dify 合规检测技能的部署、配置与运行方式。

## 目录结构
```
skills/dify-compliance/
├── SKILL.md              # 技能元数据与能力说明
├── __init__.py           # 包导出
├── client.py             # Dify API 客户端
├── parser.py             # 结果解析与飞书字段映射
├── feishu_writer.py      # 飞书字段回写
├── cli.py                # CLI 入口
└── DEPLOY.md             # 本文档
```

---

## 环境要求
- Python 3.10+
- 依赖包见下方安装步骤
- Dify 应用已部署并可访问
- 飞书多维表格已配置

---

## 1. 依赖安装

```bash
# 核心依赖
pip install requests

# 飞书写入需要
pip install lark-oapi

# 开发/测试依赖
pip install pytest pytest-mock
```

---

## 2. 环境变量配置

创建 `.env` 文件或在环境中设置：

```bash
# Dify 配置
DIFY_API_KEY=app-xxxxxxxxxxxx          # Dify 应用 API Key
DIFY_BASE_URL=https://api.dify.ai       # Dify API 基础地址（私有部署需修改）
DIFY_WORKFLOW_ID=wf-xxxxxxxx            # Workflow ID（workflow 模式时必填）
DIFY_APP_TYPE=chatflow                  # workflow / chatflow

# 飞书配置
FEISHU_APP_ID=cli_xxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxx
FEISHU_BASE_ID=ONy9bZ0oFaaiSEsf4ggcs61enRc
FEISHU_TABLE_ID=tbl75glY29VulRLm
```

### 关键说明
- `DIFY_WORKFLOW_ID` 仅在 `DIFY_APP_TYPE=workflow` 时必填
- `DIFY_APP_TYPE=chatflow` 时使用 `/v1/chat-messages` 端点
- 飞书字段名需与多维表格完全一致（见 `feishu_writer.py` 中的字段映射）

---

## 3. Dify 应用部署

### 3.1 导入应用定义
使用 `skills/dify-compliance/dify_compliance_agent.yml` 导入 Dify 应用：

1. 进入 Dify 控制台 → 应用 → 从 DSL 导入
2. 上传 `dify_compliance_agent.yml`
3. 发布应用并获取 API Key

### 3.2 知识库配置
必须绑定风险词知识库：
1. 将 `risk_keywords.db` 导出为 CSV/Markdown
2. 在 Dify 知识库中创建 "合规风险词库"
3. 导入数据，启用语义检索
4. 在应用中关联该知识库

### 3.3 输入变量映射
Dify 应用需定义以下输入变量（对应 `client.py` `_build_dify_inputs`）：

| 变量名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| spu_id | string | ✓ | SPU ID |
| platforms | string | ✓ | 逗号分隔平台列表 |
| scan_scope | string | | draft/visual_final/full |
| amazon_title | string | | Amazon 标题 |
| amazon_bullets | string | | Amazon 五点描述 |
| amazon_description | string | | Amazon 描述 |
| amazon_st | string | | Amazon Search Terms |
| amazon_faq | string | | Amazon FAQ |
| etsy_title | string | | Etsy 标题 |
| etsy_tags | string | | Etsy Tags |
| etsy_description | string | | Etsy 描述 |
| ebay_title_matrix | string | | eBay 标题矩阵 |
| ebay_bullets | string | | eBay Bullets |
| ebay_item_specifics | string | | eBay Item Specifics |
| ebay_desc_html | string | | eBay HTML 描述 |
| visual_prompts_amazon | string | | Amazon 视觉 Prompt |
| visual_prompts_etsy | string | | Etsy 视觉 Prompt |
| visual_prompts_ebay | string | | eBay 视觉 Prompt |
| aplus_copy | string | | A+ 文案 |
| aplus_prompt | string | | A+ Prompt |

---

## 4. 飞书多维表格配置

### 字段映射（必须与 `feishu_writer.py` 一致）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| 合规扫描报告 | 多行文本 | 完整 Markdown 报告 |
| 合规状态 | 单选 | 通过 / 需修正 / 熔断 |
| 致命风险数 | 数字 | 一级风险计数 |
| 高危风险数 | 数字 | 二级风险计数 |
| 中危风险数 | 数字 | 三级风险计数 |

### 权限配置
- 应用需有多维表格读写权限
- 推荐使用飞书机器人身份写入

---

## 5. 运行方式

### 4.1 CLI 调试模式（无飞书回写）
```bash
# 进入项目根目录
cd /path/to/OPC_ecommerce

# 设置 PYTHONPATH
export PYTHONPATH=/path/to/OPC_ecommerce:$PYTHONPATH

# 运行
python -m skills.dify_compliance.cli \
  --spu SPU-12345 \
  --record rec_xxxxxx \
  --platforms amazon,etsy,ebay \
  --scope visual_final \
  --copy-file test_payload.json \
  --no-feishu \
  --output result.json
```

### 4.2 生产模式（完整链路）
```bash
# 确保环境变量已设置
export DIFY_API_KEY=app-xxx
export FEISHU_APP_ID=cli_xxx
export FEISHU_APP_SECRET=xxx

python -m skills.dify_compliance.cli \
  --spu SPU-12345 \
  --record rec_xxxxxx \
  --platforms amazon,etsy,ebay \
  --scope visual_final \
  --copy-file payload.json
```

### 4.3 Python 代码调用
```python
from skills.dify_compliance import DifyComplianceClient

client = DifyComplianceClient()
result = client.run_compliance_check(
    spu_id="SPU-12345",
    feishu_record_id="rec_xxxxxx",
    platforms=["amazon", "etsy", "ebay"],
    copy_fields={...},  # 见 client.py _build_dify_inputs
    scan_scope="visual_final"
)

if result.overall_status == "熔断":
    print("合规熔断，需人工介入")
```

---

## 5. 输入数据格式

### copy_fields 结构
```json
{
  "amazon": {
    "title": "string",
    "bullets": ["string"],
    "description": "string",
    "st": "string",
    "faq": [{"q": "", "a": ""}]
  },
  "etsy": {
    "title": "string",
    "tags": ["string"],
    "description": "string"
  },
  "ebay": {
    "title_matrix": ["string"],
    "bullets": ["string"],
    "item_specifics": {},
    "desc_html": "string"
  }
}
```

### visual_prompts 结构（可选）
```json
{
  "amazon": {"img1": "prompt", "img2": "prompt"},
  "etsy": {...},
  "ebay": {...}
}
```

### aplus_content 结构（可选）
```json
{
  "copy": {"01": "Headline\nBody"},
  "prompt": {"01": "prompt text"}
}
```

---

## 6. 输出结果格式

### 成功返回
```json
{
  "overall_status": "通过|需修正|熔断",
  "summary": {"fatal": 0, "high": 2, "medium": 5},
  "details": [
    {
      "platform": "amazon",
      "field": "amazon_bullets",
      "risk_level": "二级（高危）",
      "risk_type": "夸大宣传",
      "hit_keyword": "lifetime guarantee",
      "original_text": "Offers a lifetime guarantee",
      "suggested_replacement": "Offers a long-lasting warranty",
      "platform_rule": "Amazon 绝对化用语红线（FTC 指引）",
      "action_required": "user_confirm_replace",
      "location": "Bullet 3"
    }
  ],
  "report_markdown": "## 合规扫描报告\n..."
}
```

### 错误返回
```json
{
  "overall_status": "ERROR",
  "summary": {"fatal": 0, "high": 0, "medium": 0},
  "details": [],
  "report_markdown": "",
  "error": "Dify API call failed after 3 attempts: Connection timeout"
}
```

---

## 6. 风险分级映射

| Dify 输出 | 本地标准 | 处理动作 |
|-----------|----------|----------|
| 一级（致命） | fatal | CIRCUIT_BREAK 立即熔断 |
| 二级（高危） | high | 需用户确认替换 |
| 三级（中危） | medium | 静默替换/标注建议 |

---

## 7. 错误处理与重试策略

| 错误类型 | 处理方式 |
|----------|----------|
| Dify API 429 | 指数退避重试 3 次（10s/30s/60s） |
| Dify API 5xx | 重试 2 次（5s/15s） |
| 网络超时 | 60s 总超时，分段连接/读取超时 |
| 返回格式不符 | 记录原始响应，返回 ERROR 状态，人工介入 |

---

## 8. 限流与配额

- 单 SPU 单次扫描 ≤ 1 次并发
- 分钟级并发 ≤ 5 SPU
- 免费额度用尽 → 返回 `QUOTA_EXCEEDED`，Boss 暂停调度

---

## 9. 版本记录

| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-07-13 | 初版：三层扫描、三级风险、飞书回写、事件发布 |

---

## 10. 故障排查

| 现象 | 排查步骤 |
|------|----------|
| `ModuleNotFoundError: skills.dify_compliance` | 检查 `PYTHONPATH` 包含项目根目录 |
| `lark-oapi` import 失败 | `pip install lark-oapi` |
| Dify 返回 401 | 检查 `DIFY_API_KEY` 是否正确 |
| Dify 返回 404 | 检查 `DIFY_WORKFLOW_ID` / 端点是否匹配 |
| 飞书写入失败 | 检查 `FEISHU_APP_ID/SECRET`、Base/Table ID 是否正确 |
| 返回 `QUOTA_EXCEEDED` | 免费额度用尽，需升级或等待重置 |

---

## 10. 本地开发调试

```bash
# 语法检查
python -m py_compile skills/dify_compliance/cli.py

# 单元测试
pytest skills/dify_compliance/tests/ -v

# 端到端测试（无飞书回写）
python -m skills.dify_compliance.cli \
  --spu TEST-001 \
  --record rec_test \
  --platforms amazon \
  --scope visual_final \
  --copy-file test_payload.json \
  --no-feishu
```