# VERSIONING.md — 版本化迭代（铁律③）

> 一切改动版本化。禁止无版本漂移。每个版本是一个可审查、可回滚的单元。

## 1. 版本号方案

采用 **FW-vX.Y.Z**（框架版本）+ 各技能独立版本。

- **FW（框架）版本**：
  - `X` 主版本：协作模型/手册结构重大变更（需三方共识）
  - `Y` 次版本：新增 Agent 能力、新增目录规约、手册增补
  - `Z` 修订：文案修正、小补丁
- **技能版本**：各 `skills/<name>/SKILL.md` 的 frontmatter `version:` 字段独立递增。

## 2. 当前版本

| 项 | 版本 | 状态 |
|----|------|------|
| 框架 FW | **v1.0.0** | 本地，未推送 |
| 推送状态 | — | 网络断开暂推 |

## 3. 迭代纪律

1. 每次改动 = 一个版本单元：改了什么、影响哪些目录、是否跨边界。
2. 改动合入后，**立即推进对应版本号**并写 CHANGELOG。
3. 跨边界改动必须先在 `handoff/` 留痕，由所有者确认。
4. 不允许"顺手改一版没登记"——未登记的改动视为不存在。

## 4. CHANGELOG

### FW-v1.0.0（2026-08-14，本地）
- 清空 OPC-ecommerce master，从零重建。
- 建立框架骨架：README / SKILL / AGENT_BOUNDARIES / OPERATIONS / VERSIONING。
- 建立 agents/ 三份职责定义（hermes / home / office）。
- 建立 handoff/（异步交接区）与 INCIDENTS/（事故库）。
- 明确仓库定位：OPC-ecommerce 是多 Agent 电商运营仓库，不是"框架仓库"。
- 编码历史崩坏根因：禁 force-push、pull-rebase 前置、推送成功须校验远端、单一克隆、凭证卫生。

## 5. 升级检查清单

- [ ] 三方已读本版手册
- [ ] 改动仅限名下目录或已 handoff 确认
- [ ] 版本号已推进、CHANGELOG 已写
- [ ] 无 force-push、无分叉 merge
- [ ] 仓库根无 `.zip` 技能、无嵌套 `skills/skills/`
