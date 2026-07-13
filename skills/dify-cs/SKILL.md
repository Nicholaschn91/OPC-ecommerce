# 关键词工具

## 描述
子Agent关键词取用工具 — 按 SPU / T1-T5 层级 / 排序指标 筛选取用关键词。

## 依赖
- Python 3.9+
- sqlite3
- 依赖 `keyword_database.db` 和 `risk_keywords.db`

## 用法
```bash
# 列出所有 SPU
python keyword_tool.py --list-spus

# 按 SPU 取 T4(先锋) 关键词 — 旧格式（兼容）
python keyword_tool.py --spu S1-24 --tier T4 --sort conversion_rate --top 5

# 按品类取词 — V3 格式（推荐）
python keyword_tool.py --category TEXT-MATS-FLCE --tier T4 --sort conversion_rate --top 5

# 取 T3(主力) 关键词
python keyword_tool.py --spu S1-24 --tier T3 --sort purchase_intent --top 8

# 取多层级联合
python keyword_tool.py --spu S1-24 --tier T4,T3 --sort monthly_views --top 10

# 全层级总览
python keyword_tool.py --spu S1-24 --all-tiers

# 利润权重排序（需传 unit_price）
python keyword_tool.py --spu S1-24 --tier T4 --sort profit_weight --unit-price 24.99 --top 8

# 查询否定词
python keyword_tool.py --spu S1-24 --negative-only

# JSON 输出（供 Coordinator 解析）
python keyword_tool.py --spu S1-24 --tier T4 --sort conversion_rate --top 5 --format json
```

## 核心功能
1. **关键词查询**: 按 SPU/品类、T1-T5层级、排序指标筛选
2. **否定词查询**: 按 SPU 查询否定词
3. **全层级总览**: 按 T4→T3→T2→T1→T5 顺序输出
4. **关键词冻结**: `--freeze` 写入 `listing_kw_snapshot` 表
5. **风险词扫描**: `--risk-check` 扫描文本或列出风险库
6. **合规检查清单**: `--risk-checklist` 输出 25 项清单

## 数据库路径
优先级：
1. 环境变量 `KEYWORD_DB_PATH`
2. 包内相对路径 `../keyword_database.db`
3. 桌面遗留路径 `C:\\Users\\Administrator.DESKTOP-AHRMISP\\Desktop\\keywords\\erank keywords\\keyword_database.db`

风险库同目录下 `risk_keywords.db`

## 排序指标
| 指标 | 排序方向 | 适用场景 |
|------|----------|----------|
| `conversion_rate` | 降序 | T4 利润尖刀选词 |
| `monthly_views` | 降序 | T1/T2 流量基石选词 |
| `monthly_sales` | 降序 | 热销词优先 |
| `supply_demand_ratio` | 升序 | 蓝海词发现 |
| `purchase_intent` | 降序 | 购买意图优先 |
| `competition` | 升序 | 低竞争词 |
| `profit_weight` | 降序 | conversion_rate × unit_price |

## 输出格式
- `markdown` (默认): 人类可读表格
- `json`: 供程序解析
- `list`: 仅关键词列表，每行一个