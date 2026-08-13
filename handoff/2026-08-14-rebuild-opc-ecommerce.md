# handoff — 清空重建 OPC-ecommerce（整库从零）

- **To**: hermes（SOP owner）
- **From**: home（hermes 的高级外包，仅交付 base）
- **Date**: 2026-08-14
- **交付对象确认**: 用户明确「整库清空从零重建，且因 hermes 主管 SOP，应由 hermes 搭建仓库」→ 本件为**交付物 + 执行授权**，仓库的实际清空与重建由 hermes 执行，home 不替 owner 落 repo。

## 1. 决策（用户 2026-08-14）
- **范围**: 整库清空 OPC-ecommerce（`knowledge-base / shared / tools / skills / config / docs` 等 hermes 实质资产一并清空），从零重建为干净框架。
- **执行者**: hermes（SOP owner）。
- **背景**: 过去三方从未真正同步协同、各自为战；故清空重建比勉强维护旧混乱状态更干净。

## 2. 交付的干净 base（本工作空间）
路径：`C:\Users\nicho\WorkBuddy\2026-06-19-04-50-07\`
已含正确内容（无需再改）：
- `README.md` / `SKILL.md` / `AGENT_BOUNDARIES.md` / `OPERATIONS.md` / `VERSIONING.md`
- `handoff/` / `INCIDENTS/` / `agents/` / `skills/` / `docs/` / `references/`
- 角色模型已正确：hermes 拥有整个 SOP、office 主要负责 skill、home 是 hermes 高级外包交付成品。
- git 通道根因已复盘（`INCIDENTS/2026-08-git-insteadof-fake-success.md`）：全局 insteadOf HTTPS→SSH 劫持死密钥 → 假成功；当前规则已删、https 直连正常。
- canonical 仓库已标注：`https://github.com/Nicholaschn91/OPC-ecommerce.git`。

## 3. 排除项（不纳入本次 base）
- `opc_docs_new/`（office 在旧混乱期起草的草稿，与根框架构成两个真相源）→ **本次重建不纳入**。其独有 handoff 细节是否折叠进 `handoff/`，由 hermes 定夺后退役。

## 4. hermes 执行步骤建议
1. **清空**: 删除 OPC-ecommerce `master` 全部分支内容（整库从零，含 knowledge-base/shared/tools/skills/config/docs）。
2. **重建**: 以本 base 初始化仓库（`git init` 或直接以 base 内容提交）。
3. **推送**: remote 用 `https://github.com/Nicholaschn91/OPC-ecommerce.git`；`gh auth login` + `gh auth setup-git` 走 https token；**推送前 `git config --global --get-regexp insteadof` 必须为空**；推送成功以「远端 HEAD 前进」判定（见 OPERATIONS.md §3）。
4. **回填**: 因选「整库清空」，hermes 原有的 knowledge-base/shared/tools/skills/config/docs 实质资产需由 hermes 重新导入（home 不持有这些资产，无法代填）。
5. **定调**: 重建后由 hermes 定调 SOP 方向与框架骨架版本（home 落笔、hermes 定调，见 AGENT_BOUNDARIES.md）。

## 5. 备注
- 本地工作空间 `2026-06-19-04-50-07` 当前**不是 git 仓库**；hermes 可直接读取上述路径，或复制到 hermes 侧再 init。
- home 已完成交付，等待 hermes 执行清空+重建并回填实质资产。
