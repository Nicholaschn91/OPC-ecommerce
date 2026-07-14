# OPC_ecommerce — 项目维护手册

**身份**：home-hermes（本仓库 `Nicholaschn91/OPC-ecommerce`）
**设备**：`C:\Users\nicho`（与 home-workbuddy 共居）

---

## 维护权边界

| 领域 | 主导 | 说明 |
|------|------|------|
| **SOP 流程** | **home-hermes** | `docs/SOP.md`、`config/event-routing.yaml`、`config/AGENT_BOUNDARIES.md` — 流水线定义、闸门逻辑、字段权限矩阵 |
| **Agent 定义文件** | **home-hermes** | `agents/*/AGENT.md` — Router/SEO/Visual/Ads/Compliance/Scraper/Keyword-Grader |
| **数据清洗工具链** | **home-hermes** | `tools/product_name_cleaner.py`、`variant_authenticator.py`、`category_row_sorter.py`、`spu_dedup.py` |
| **Hermes 配置** | **home-hermes** | `~/.hermes/config.yaml`、`~/.hermes/.env`、9router 连接 |
| **Agnes 生图/生视频** | **home-hermes** | `tools/agnes_client.py`、`skills/agnes-media/` |
| **图片后处理管道** | **home-hermes** | `skills/image-*-*/` — 背景移除/尺寸/ALT/上传 |
| **关键词治理** | home-workbuddy | `keyword-grader`、`keyword_database.db`、`risk_keywords.db`、T1-T5 分级 |
| **HiCustom/1688 采集** | home-workbuddy | `hicustom-product-info/`、`1688-shopkeeper/` — 采集+飞书同步 |
| **GLM-5.2 语义层** | home-workbuddy | `glm52-caller/`、`glm52-nim/` — 关键词污染审查/聚类/意图分析 |
| **Tabbit 上传** | home-workbuddy | `tabbit-upload/` |

---

## home-workbuddy 当前领先项（暂不接管）

以下领域 WorkBuddy 在工具成熟度上暂时领先，等它们的工具链推进到特定阶段时，home-hermes 再接手：

| 领先项 | 领先原因 | 何时交接 |
|--------|----------|----------|
| HiCustom 采集器 | `extract_product.py` + `sync_to_feishu.py` 已跑通数百条商品采集 | 等 WorkBuddy 把采集质量稳定后，home-hermes 接手 Router 阶段的消费 |
| 1688 采集器 | AK 已配置，`1688-shopkeeper/` 脚本就绪 | 同上，等采集数据质量达标 |
| keyword_database.db | 5.6M 词库由 WorkBuddy 构建 | 只读消费，不接管构建 |
| GLM-5.2 NIM | WorkBuddy 封装了 NVIDIA NIM 调用 | 等 9router GLM-5 验证稳定后，考虑替换 |
| Tabbit 上传 | 浏览器自动化上传 | RPZ 限额策略等 WorkBuddy 调试完 |

---

## GitHub 作为通告渠道

**home-workbuddy 通过 GitHub** (`Nicholaschn91/multi-agent-sop`?? ——身份声明)

来自 home-hermes 的重要通知，会写在本仓库的 commit message 或 `handoff/hermes.md` 中：

- **工具链推进**：数据清洗工具何时从 dry-run 切换到 --apply
- **SOP 版本变更**：流水线阶段、闸门规则、字段矩阵的重大调整
- **Agent 定义变更**：Router/SEO/Visual 等 Agent 的边界重新划定
- **事件 schema 变更**：`event-routing.yaml` 的版本号递增

---

## 流程概览（SOP v2.0，home-hermes 最终裁决）

```
采集阶段 (WorkBuddy 主导)
  HiCustom/1688 Scraper → 飞书 Base A 输入字段
                            ↓
数据清洗 (home-hermes 主导)      ← 当前建设重点
  product_name_cleaner → variant_authenticator → category_row_sorter → spu_dedup
                            ↓
Router 阶段 (home-hermes)
  生成 SPU_CONTEXT → 变体拆分方案 → Base B 父记录 → CRITICAL_STOP
                            ↓
SEO 阶段
  Base B 子记录创建（方案A/B × 变体属性组）→ 初版文案 → HUMAN_CONFIRM
                            ↓
Visual 阶段
  终版生成 + 视觉 Prompt + A+ → visual_final
                            ↓
Dify 合规检测
  风险分级 → COMPLIANCE_CONFIRM
                            ↓
Ads 广告方案 → 全案完成
```

---

## 下一步优先级

1. **完成数据清洗工具** → `--apply` 写入飞书 → 父记录干净
2. **Router Agent 实战** → 消费清洗后的父记录 → 生成第一份 `proposal_ready`
3. **SEO Agent 实战** → 按变体拆分方案创建子记录
4. **通知 WorkBuddy** → 清洗完成后的新数据格式，供 keyword-grader 消费