# Build Risk DB Skill

## 描述
从 Excel 风险词表构建 SQLite 风险词库，供 `keyword_tool.py --risk-check` 使用。

## 触发词
- "构建风险词库"
- "更新风险词库"

## 核心能力
- 读取 Excel 风险词表
- 三级风险分级写入 SQLite
- 平台专属规则分离存储
- 版本管理、增量更新

## Excel 源文件格式
```
跨境电商风险词词库.xlsx
工作表: 风险词库
列: 关键词, 替代词, 风险等级, 风险类型, 平台, 违规后果
```

## 风险分级定义

| 等级 | 定义 | 处理 |
|------|------|------|
| 一级（致命） | 法律/平台红线 | 立即熔断，禁止输出 |
| 二级（高危） | 警告 + 建议替换 | 标注 ⚠️，需用户确认 |
| 三级（中危） | 标注风险可保留 | 静默替换/标注 |

## 数据库 Schema
```sql
-- risk_keywords.db
CREATE TABLE risk_keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    alternative TEXT,
    level TEXT NOT NULL,          -- 一级（致命）/二级（高危）/三级（中危）
    platform TEXT NOT NULL,       -- amazon/etsy/all
    risk_type TEXT NOT NULL,      -- 法律/平台/宣传/医疗/敏感/格式/认证
    consequence TEXT,             -- 违规后果
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(keyword, platform)
);

CREATE TABLE risk_checklist (
    seq INTEGER PRIMARY KEY,
    category TEXT NOT NULL,       -- 侵权合规/宣传合规/医疗健康/平台规则/敏感内容/格式合规/认证合规
    check_item TEXT NOT NULL
);
```

## Excel 列映射
| Excel列 | DB字段 |
|---------|--------|
| 关键词 | keyword |
| 替代词 | alternative |
| 风险等级 | level |
| 风险类型 | risk_type |
| 平台 | platform |
| 违规后果 | consequence |

## 使用示例

### 构建/全量更新
```bash
python -m skills.build_risk_db --excel "跨境电商风险词词库.xlsx" --output risk_keywords.db
```

### 增量更新
```bash
python -m skills.build_risk_db --excel "新增风险词.xlsx" --merge risk_keywords.db
```

### 验证/统计
```bash
python -m skills.build_risk_db --stats risk_keywords.db
```

## 调用示例 (供 keyword_tool.py 调用)
```python
from skills.build_risk_db import RiskDB

db = RiskDB("risk_keywords.db")

# 扫描文本
hits = db.scan_text(text="This product cures cancer", platform="amazon")
# hits = [{"keyword": "cures cancer", "level": "一级（致命）", ...}]

# 列出清单
checklist = db.get_checklist()
# checklist = [{"seq": 1, "category": "侵权合规", "check_item": "..."}, ...]
```

## Excel 样例数据
| 关键词 | 替代词 | 风险等级 | 风险类型 | 平台 | 违规后果 |
|--------|--------|----------|----------|------|----------|
| cures cancer | helps support wellness | 一级（致命） | 医疗健康 | all | FDA 违规，账号封禁 |
| best seller | popular choice | 三级（中危） | 宣传违规 | amazon | Search Terms 禁用 |
| for iPhone | compatible with iPhone | 二级（高危） | 侵权风险 | all | VeRO 投诉，下架 |
| lifetime warranty | 12-month quality support | 二级（高危） | 宣传违规 | all | 广告法违规 |

## 版本记录
| 版本 | 日期 | 变更 |
|------|------|------|
| 1.0.0 | 2026-07-13 | 初版：Excel→SQLite、三级分级、平台分离 |