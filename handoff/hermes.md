# handoff — home-hermes 侧交接日志

**身份声明**：本仓库（`OPC_ecommerce`）由 **home-hermes** 维护。
home-hermes 与 home-workbuddy（`multi-agent-sop` 仓库）运行于 **同一台物理设备**（`C:\Users\nicho`）。

## 双 Agent 共存约定

| 角色 | 仓库 | 职责 |
|------|------|------|
| **home-hermes** | `Nicholaschn91/OPC-ecommerce` | 数据清洗工具链、变体甄别、SPU去重、品类归行、Router/SEO/Visual/Ads/Compliance Agent 实现、Hermes 配置 |
| **home-workbuddy** | `multi-agent-sop`（本地 `~/.workbuddy/skills/multi-agent-sop/`） | 关键词治理、keyword-grader、风险词库、品类词池、HiCustom/1688 采集器、飞书同步、GLM-5.2 NIM 调用 |

## 跨 Agent 交接协议

与 home-workbuddy 约定的 handoff 机制（由 WorkBuddy 的 `handoff/coord.md` 定义）：
- 各自维护自己的 handoff 文件，不交叉写入
- 本仓库的 `config/AGENT_BOUNDARIES.md` 和 WorkBuddy 的 `AGENT_BOUNDARIES.md` 保持同步口径
- 字段命名、事件名、闸门规则先在本仓库 `handoff/` 更新，再同步到 WorkBuddy 侧

## 版本维护口径

- **本仓库版本号**：跟随 `config/event-routing.yaml` 的 `version` 字段
- **变更通知**：涉及跨 Agent 影响的变更，在此文件追加记录
- **对方需注意的事项**：下方列出

---

## 2026-07-14 22:00 — 初始化交接 + 四件清洗工具落盘

- **身份声明**：home-hermes 认领本仓库维护权；home-hermes 与 home-workbuddy 运行于同一设备（`C:\Users\nicho`）
- **新增工具**：
  - `tools/product_name_cleaner.py` — 商品名称清洗器（去仓库后缀/HTML残留）
  - `tools/variant_authenticator.py` — 变体甄别器（0维/1维/2维判定，9router LLM 兜底）
  - `tools/category_row_sorter.py` — 品类归行器（基于品名独立推断品类）
  - `tools/spu_dedup.py` — SPU 去重器（品名+白品ID全表去重）
- **变体铁律已固化**：`AGENT_BOUNDARIES.md` 新增变体铁律（最高优先级）、角色区分表
- **对方需注意**：
  - 清洗工具链完成前，Router/SEO 阶段不能直接消费 Base A 原始数据
  - 推荐执行顺序：`product_name_cleaner --apply` → `variant_authenticator --apply` → `category_row_sorter --apply` → `spu_dedup --apply`