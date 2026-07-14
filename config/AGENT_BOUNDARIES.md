# AGENT_BOUNDARIES.md — 核心边界定义（飞书字段权限矩阵）

**全局铁律**：越权即被主控拦截、清除脏数据、重跑。

---

## 飞书字段级写权限矩阵

| Agent | 读权限边界 | 写权限边界（飞书字段级） |
|-------|-----------|------------------------|
| **00_Scraper** | 仅目标商品页面 DOM/API | 仅 Base A 输入字段；**不读飞书其他、不写战略/文案** |
| **00b_Image_PostProcessor** | `spu_fetched` 事件载荷（含图片 URL、商品基础信息） | **仅** Base A 临时字段 `图片素材包_JSON`；**不写战略/文案/终版** |
| **01_Router** | Base A 输入字段 + keyword_tool（由 keyword-grader 代理） | 仅战略字段 / 平台分流 / 赛道选择 / VISUAL_HANDOFF |
| **02_SEO_to_Listing** | 仅 `SPU_CONTEXT` YAML + 平台专属 skill 包 | 仅 Base B **父记录**（Product）+ **子记录**（Listing A/B/C...）初版字段 |
| **03_Visual** | VisualBridge + 初版文案 | 仅 Base B **父/子记录**终版字段 + 视觉 Prompt + A+ Copy/Prompt |
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
02_SEO_to_Listing 读取 SPU_CONTEXT → 生成 Base B 父记录 + 子记录初版
       ↓ (人工确认 HUMAN_CONFIRM)
03_Visual 读取初版 + VisualBridge → 生成父/子记录终版 + 视觉 Prompt + A+
       ↓
06_Dify_Compliance 扫描（父/子记录终版文案 + 视觉 Prompt + A+）
       ↓ (若有二级风险 → COMPLIANCE_CONFIRM 等待用户"替换")
       ↓ (若一级风险 → CIRCUIT_BREAK 全线暂停)
       ↓
04_Ads 读取父/子记录初版标题/ST/痛点 → 生成广告方案
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
| **HUMAN_CONFIRM** | `draft_done` | 父/子记录初版后 | 300s 无确认 → 通知用户 |
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

## Base B 多层级结构（私表·Table B）

### 🔴 变体铁律（最高优先级）

> **每个 Listing 最多 2 个变体维度。超过 2 个维度必须拆分为多个 Listing。**

这是硬上限，由各平台（Amazon、eBay、Etsy）变体系统原生限制，无例外。

### 变体维度定义（0维/1维/2维）

| 维度 | 含义 | 示例 | Listing 策略 |
|------|------|------|--------------|
| **0维** | 单一规格商品，无任何变体关系 | `异形购物袋`（单尺码+白色占位） | 单 listing，无需变体拆分 |
| **1维** | 仅一个属性存在客观变体 | `装饰画`（多尺寸+白色占位） | 1 listing，仅含该维度的子变体 |
| **2维** | 两个属性都存在客观变体 | `T恤`（多颜色+多尺码） | 如总属性＞2，需按 2维/组 拆为多个 listing |

**⚠️ 0维 ≠ 忽略**。0维商品一样要生成 listing（单个 listing 不含变体下拉），只是不需要变体拆分逻辑。

**举例**：一个商品同时具备 6 个变体属性（尺寸、颜色、材质、形状、设计方案、包装数量），按 2 维上限，至少需拆成 **3 个 Listing**。

### 层级结构（6 属性 → 3 Listing × 2 方案）

```
父记录（Product）— 完整商品名                   ← Router 阶段创建
│
├── 方案 A 系列
│   ├── Listing A-尺寸-颜色                     ← SEO 阶段创建
│   │   ├── 尺寸1-颜色1
│   │   ├── 尺寸1-颜色2
│   │   ├── 尺寸2-颜色1
│   │   └── 尺寸2-颜色2
│   │
│   ├── Listing A-材质-形状
│   │   ├── 材质1-形状1
│   │   ├── 材质1-形状2
│   │   ├── 材质2-形状1
│   │   └── 材质2-形状2
│   │
│   └── Listing A-设计方案-包装数量
│       ├── 设计方案1-包装数量1
│       ├── 设计方案1-包装数量2
│       ├── 设计方案2-包装数量1
│       └── 设计方案2-包装数量2
│
└── 方案 B 系列
    ├── Listing B-尺寸-颜色
    │   ├── 尺寸1-颜色1
    │   ├── 尺寸1-颜色2
    │   ├── 尺寸2-颜色1
    │   └── 尺寸2-颜色2
    │
    ├── Listing B-材质-形状
    │   ├── 材质1-形状1
    │   ├── 材质1-形状2
    │   ├── 材质2-形状1
    │   └── 材质2-形状2
    └── Listing B-设计方案-包装数量
        ├── 设计方案1-包装数量1
        ├── 设计方案1-包装数量2
        ├── 设计方案2-包装数量1
        └── 设计方案2-包装数量2
```

### Listing 拆分公式

```
单个方案的 Listing 数 = ceil(变体属性总数 / 2)

示例：
  2 个属性 → 1 个 Listing
  3 个属性 → 2 个 Listing（2+1，单属性 listing 合法但慎用）
  4 个属性 → 2 个 Listing（2+2）
  5 个属性 → 3 个 Listing（2+2+1）
  6 个属性 → 3 个 Listing（2+2+2，如上图）
```

**⚠️ 单属性 Listing**：3 个属性拆成 2+1 时，那个 1 维 listing 仅含单变体属性（如仅"包装数量"），平台技术上允许但 UX 不佳。Router 需评估是否合并到已有 listing 的变体下拉中，或独立成 listing。

### product_name 命名规范

| 层级 | 规则 | 示例 |
|------|------|------|
| **父记录** | 完整商品名 | `Handcrafted Wooden Desk Organizer` |
| **Listing 子记录** | `{父 product_name}-{方案}-{两个变体属性}` | `Handcrafted Wooden Desk Organizer-A-尺寸-颜色` |

### 关键字段规则

| 层级 | 记录类型 | 关键字段 | 承载内容 |
|------|----------|----------|----------|
| **父** | Product | SPU_ID、product_name、Category、Track、图片素材包_JSON | 核心属性、不存文案/变体 |
| **子** | Listing | 父记录引用、方案标识(A/B)、变体属性1、变体属性2、变体维度、变体列表、Amazon/Etsy/eBay 初版/终版/视觉/A+/合规/广告 | 全部平台文案+视觉+合规+广告 |

### 变体属性分配与遍历规则

**Phase 2 — Router**：
1. 从 Base A 读取 `变体维度` 字段（Scraper 解析）
2. 计算属性总数 → ceil(总数/2) → 确定每个方案的 Listing 数量
3. 写入 `proposal_ready` 事件载荷：方案 × Listing 矩阵

**Phase 3 — SEO**：
1. 读取 proposal 中的 Listing 分配方案
2. **在 Base B 父记录下逐一创建子记录**，`product_name` 严格按命名规范
3. 每个子记录写入：`变体属性1`、`变体属性2`、`变体维度`、`变体列表`
4. **确保 `变体维度` 字段准确完整**——这是各 Agent 处理的核心依据

**所有下游 Agent 在操作前必须确认 `变体维度` + `变体属性1/2` + `变体列表`，这是唯一合法上下文。**

### 变体属性枚举（标准化）

| 变体属性 | 标准名称 | 说明 |
|----------|----------|------|
| 尺寸 | Size | S/M/L/XL 或 mm/cm/inch 规格 |
| 颜色 | Color | 标准色名/色号 |
| 材质 | Material | 棉/聚酯/不锈钢/陶瓷等 |
| 形状 | Shape | 圆形/方形/异形等 |
| 设计方案 | Design | 方案 A/B/C 或 主题名称 |
| 包装数量 | Pack Size | 1 Pcs / 2 Pcs / Set / Bundle |

**⚠️ "设计方案"≠ Listing 方案 A/B**。"设计方案"是**变体属性之一**（如花纹A、花纹B），与"方案 A/B"（整体战略定位）是两个维度，不可混淆。

---

## 角色约束（关键误区分清）

| 概念 | 含义 | 作用域 |
|------|------|--------|
| **方案 A / B** | SEO 整体定位方向（A=主流打法，B=差异化打法） | 决定子记录创建策略 |
| **变体属性** | Listing 内的规格差异维度 | 每个 Listing 最多 2 个 |
| **变体列表** | 2 个变体属性的笛卡尔积展开 | 子记录内的 SKU 矩阵 |

---

*本协议由主控 Agent 维护。修改需经用户 (Nicholas) 确认后执行。*