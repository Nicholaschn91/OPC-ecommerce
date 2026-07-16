# OPC Multi-Agent System — Agent Registry

> 所有 Agent 的统一注册表。每个 Agent 的职责边界、输入输出、依赖关系在此定义。
> 更新此文件时，同步更新对应 Agent 的 AGENT.md。

## Agent 列表

| # | Agent | 编号 | 职责 | 输入 | 输出 | 依赖 |
|---|-------|------|------|------|------|------|
| 1 | Boss | 00 | 主控 Orchestrator | 全局事件 | 路由决策、人工闸门 | 所有 Agent |
| 2 | Scraper | 01 | 数据采集（HiCustom + 1688） | 商品链接 | `spu_fetched` 事件 | Boss |
| 3 | Keyword Grader | 02 | 关键词分级与冻结快照 | 品类数据 | `keyword_snapshot_ready` | Boss, Scraper |
| 4 | Router | 03 | 战略提案 + 变体判定 | `spu_fetched` + 关键词快照 | `proposal_ready` 事件 | Boss, Scraper, Keyword Grader |
| 5 | SEO | 04 | 初版 Listing 文案生成 | `proposal_ready` | `draft_done` 事件 | Router |
| 6 | Visual | 05 | 终版 Listing + 视觉 Prompt + A+ | `draft_done` | `visual_final` 事件 | SEO |
| 7 | Dify Compliance | 06 | 合规检测（三层扫描） | `visual_final` | `compliance_check_result` | Visual |
| 8 | Ads | 07 | 广告方案生成 | `compliance_check_result` | 广告文案 + 预算建议 | Dify Compliance |
| 9 | CS | 08 | 客服话术生成 | 产品信息 | FAQ + 客服脚本 | Visual |
| 10 | Image Post-Processor | 09 | 图像处理（URL→Base64、去背、缩放、上传） | 视觉 Prompt | 已上传的图片 URL | Visual |

## 数据流

```
Scraper ──spu_fetched─────────────┐
Keyword Grader ──keyword_snapshot_ready ──┐
                                           ▼
                                    Router ──proposal_ready──┐
                                                               ▼
                                          SEO ──draft_done────────────┐
                                                                  ▼
                                         Visual ──visual_final──────────┐
                                                                 ▼
                                Dify Compliance ──compliance_check_result──┐
                                                                        ▼
                                               Ads ──ad_campaign_data
                                               CS ──customer_service_scripts
                                               Image Post-Processor ──image_urls
```

## 职责边界（飞书字段写权限）

| Agent | 可读字段 | 可写字段 | 禁止写入 |
|-------|----------|----------|----------|
| Boss | 所有 | 事件总线 | 无 |
| Scraper | 目标页面 | 输入字段（颜色/尺码/价格等） | 策略/文案/视觉 |
| Keyword Grader | keyword_database.db | category/tier/keyword_snapshot | 商品数据/文案 |
| Router | 输入字段 + 关键词快照 | strategy/platform/track/VISUAL_HANDOFF | 初版文案/视觉 |
| SEO | SPU_CONTEXT YAML + 关键词快照 | Amazon/Etsy/eBay 初版字段 | 视觉/A+/ST |
| Visual | VisualBridge + 初版文案 | 终版字段 + 视觉 Prompt + A+ | ST/合规字段 |
| Dify Compliance | 所有终版字段 | 合规扫描报告 + 合规状态 | 文案/视觉 |
| Ads | 初版 title/ST/pain points | 广告活动字段 | 初版文案/视觉 |
| CS | 产品信息 + 终版文案 | 客服话术字段 | 产品数据/视觉 |
| Image Post-Processor | 视觉 Prompt | 图片 URL 字段 | 文案/合规 |

## 人工闸门

| 闸门 | 触发条件 | 确认方式 | 超时 |
|------|----------|----------|------|
| CRITICAL_STOP | Router 提案产出 | "确认"/"继续"/"通过"/"OK" | 300s |
| HUMAN_CONFIRM | 各平台初版产出 | 同上 | 300s |
| COMPLIANCE_CONFIRM | Dify L2 风险 | "替换"/"replace"/"修正"/"fix" + 确认 | 300s |
| CIRCUIT_BREAK | Dify L1 风险 | 自动熔断，需人工介入 | 无限 |

## 铁律

1. **三振出局** — 任何任务连续失败 3 次 → 立即中断、输出错误详情、等待人工介入
2. **合规熔断** — 触碰法律/平台红线立即中止
3. **只读边界** — shared/databases/ 对子 Agent 只读
4. **变体铁律** — 每个 Listing 最多 2 个变体维度
5. **越权清除** — 任何跨边界写入 → Boss 拦截 → 清除脏数据 → 重跑

## 版本历史

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-07-15 | v1.0 | 初始注册表，10 个 Agent |
