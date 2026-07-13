# AGENT_BOUNDARIES.md — 核心边界定义（飞书字段权限矩阵）

**全局铁律**：越权即被主控拦截、清除脏数据、重跑。

---

## 飞书字段级写权限矩阵

| Agent | 读权限边界 | 写权限边界（飞书字段级） |
|-------|-----------|------------------------|
| **00_Scraper** | 仅目标商品页面 DOM/API | 仅 Base A 输入字段；**不读飞书其他、不写战略/文案** |
| **00b_Image_PostProcessor** | `spu_fetched` 事件载荷（含图片 URL、商品基础信息） | **仅** Base A 临时字段 `图片素材包_JSON`；**不写战略/文案/终版** |
| **01_Router** | Base A 输入字段 + keyword_tool（由 keyword-grader 代理） | 仅战略字段 / 平台分流 / 赛道选择 / VISUAL_HANDOFF |
| **02_SEO_to_Listing** | 仅 `SPU_CONTEXT` YAML + 平台专属 skill 包 | 仅 Amazon/Etsy/eBay 初版字段 |
| **03_Visual** | VisualBridge + 初版文案 | 仅终版字段 + 视觉 Prompt + A+ Copy/Prompt |
| **04_Ads** | 仅初版标题/ST/痛点 | 仅广告方案 |
| **05_Keyword_Grader** | 仅 `keyword_database.db`（只读） | 仅主控确认后的品类/分级字段 |
| **06_Dify_Compliance** | 所有文案字段 + 视觉 Prompt + A+ 内容 | **仅** `合规扫描报告` + `合规状态` 字段；<br>二级风险经用户确认后可回写对应文案字段 |
| **07_Customer_Service** | 订单/产品/物流/退换货 相关字段 | 仅客服记录字段；不写入 Listing 字段 |

---

## 边界违规处理

1. **检测**：主控 Agent 在每轮事件分发前/后扫描飞书写入记录
2. **清除**：发现越权写入 → 立即撤销该字段值、记录违规日志
3. **重跑**：对违规 Agent 触发"三振出局"计数，清除脏数据后自动重跑
4. **通知**：三次违规 → 熔断该 Agent、通知人工介入

---

## 数据流向约束

```
飞书 Base A 输入字段
       ↓ (仅 Scraper 写入)
00b_Image_PostProcessor 并行
       ↓ (产出图片素材包_JSON)
01_Router 读取 → 生成 SPU_CONTEXT YAML
       ↓ (人工确认 CRITICAL_STOP)
02_SEO_to_Listing 读取 SPU_CONTEXT → 生成三平台初版
       ↓ (人工确认 HUMAN_CONFIRM)
03_Visual 读取初版 + VisualBridge → 生成终版 + 视觉 Prompt + A+
       ↓
06_Dify_Compliance 扫描（终版文案 + 视觉 Prompt + A+）
       ↓ (若有二级风险 → COMPLIANCE_CONFIRM 等待用户"替换")
       ↓ (若一级风险 → CIRCUIT_BREAK 全线暂停)
       ↓
04_Ads 读取初版标题/ST/痛点 → 生成广告方案
       ↓
全案完成
```

---

## 词库访问约束

- **keyword_database.db** — 只读，仅 keyword-grader 可访问
- **risk_keywords.db** — 只读，keyword-grader 扫描时自动调用，**Dify 内部亦复用同库**
- 任何子 Agent 直接读词库 → 视为越权
- 取词统一经 `keyword_request` 事件 → keyword-grader 处理

---

## 人工闸门定义

| 闸门 | 触发事件 | 等待确认 | 超时处理 |
|------|---------|----------|----------|
| **CRITICAL_STOP** | `proposal_ready` | Router 提案后 | 300s 无确认 → 通知用户 |
| **HUMAN_CONFIRM** | `draft_done` | 各平台初版后 | 300s 无确认 → 通知用户 |
| **COMPLIANCE_CONFIRM** | `compliance_check_result` (有二级风险) | Dify 扫描完成 | 300s 无确认 → 通知用户 |
| **ETSY_STAGE** | Etsy 每阶段后 | Etsy 特有 | 300s 无确认 → 通知用户 |

**确认关键词**："确认" / "继续" / "通过" / "OK" / "ok" / "confirm" / "approve" / "替换" / "replace" / "修正" / "fix"

---

## 合规检测节点（Dify 专用）

| 维度 | 定义 |
|------|------|
| **唯一入口** | 所有合规扫描**仅**通过 Dify 应用执行 |
| **三层扫描** | 1) 关键词库扫描 2) 平台专属规则 3) LLM 语义合规 |
| **风险分级** | 一级→熔断 / 二级→需确认替换 / 三级→静默处理 |
| **可写字段** | `合规扫描报告`、`合规状态`、经用户确认后的文案字段（仅二级风险） |
| **禁止** | 绕过 Dify 直接调用 keyword_tool/risk_db；自行判定一级风险"可接受" |

---

## 图片后处理节点（00b_Image_PostProcessor）

| 维度 | 定义 |
|------|------|
| **触发** | `spu_fetched` 事件（Scraper 完成） |
| **并行** | 与 keyword-grader 并行启动，互不阻塞 |
| **输入** | `spu_fetched` 事件载荷（含图片 URL、商品基础信息） |
| **处理** | 下载 → 背景移除 → 尺寸标准化 → 视觉模型生成 ALT → 质检 → 上传 → Base64 |
| **产出** | 写入 Base A 临时字段 `图片素材包_JSON`；发布 `images_processed` 事件 |
| **Router 依赖** | Router 启动需等待 `images_processed` + `keyword_snapshot_ready` 双线就绪 |

---

*本协议由主控 Agent 维护。修改需经用户 (Nicholas) 确认后执行。*