# 2026-08-14-OPC-ecommerce 清空重建 force-push 复盘

## 事故概述
用户决策「整库清空从零重建 OPC-ecommerce master」，由 home 交付 base，hermes 执行本地清空重建并 force-push 到远端 master。

## 原因
- 旧 master 历史被三方各自修改，真相源混乱
- home 先 force-push 了骨架版 0a0e9df（套了"multi-agent-sop 框架"外壳）
- hermes 收到用户授权后，以本机 WorkBuddy base 重建完整框架，本地 commit 7e2c0de
- 因远端已有 0a0e9df，pull-rebase 会导致分叉，故走 force-push

## 教训
1. **force-push 是高风险操作**：只有用户明确授权 + 历史已保全（backup tag）时才能用
2. **多 Agent 同时操作同一仓库的后果**：home 已 force-push 了骨架版，hermes 再 force-push 覆盖，两版都非用户原始意图
3. **应先用 `git pull --rebase` 融合**：若远端只有骨架差异，应先 fetch + rebase 再 push

## 处理结果
- 备份 tag `backup-before-rebuild-20260814` 指向旧 HEAD b7da998（已推远端）
- 远端 master 已前进到 7e2c0de（hermes 重建版）
- 仓库结构清晰：agents/ 三份职责、handoff/、INCIDENTS/、skills/ 待回填

## 后续
- 用户验收新版本后，再逐步回填 skills/ 实质资产
- 所有变更走 `git pull --rebase` 通道，禁 force-push
