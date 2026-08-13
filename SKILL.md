---
name: opc-ecommerce
description: OPC-ecommerce 多 Agent 电商运营系统 — hermes 拥有 SOP / home 外包交付 / office 技能主力。触发：SOP 维护、Agent 分工、推送规约、版本迭代。
---

# OPC-ecommerce — 多 Agent 电商运营系统

你是参与本系统的 Agent 之一，按**所有权向上交付**而非平级协同。动手前，**先按顺序读**：

1. `README.md` — 仓库总览
2. `AGENT_BOUNDARIES.md` — 你拥有哪块，不能碰哪块
3. `OPERATIONS.md` — 推送 / 拉取 / 冲突处理的唯一正确操作
4. `VERSIONING.md` — 改动如何版本化

## 你做改动时的硬约束

- **只改 AGENT_BOUNDARIES.md 划定给你名下**的目录。跨目录依赖走 `handoff/`。
- 改前必 `git pull --rebase origin master`；改完立即 commit + push。
- **推送成功 = 校验远端 HEAD 比推送前前进了**，不要只看本地 exit code。
- 永远不要 `git push --force` 到主干。
- 任何技能必须摊平在 `skills/<name>/SKILL.md`，不要嵌套 `skills/skills/`。

## 异常时

先去 `INCIDENTS/` 看有没有同类复盘；没有就写一条，再修。不要静默绕过。
