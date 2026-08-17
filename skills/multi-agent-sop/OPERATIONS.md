# multi-agent-sop 多人维护操作手册

> 本文件是仓库的**唯一协作契约**。任何 Agent / 协作者动工前必须先读这一份。
> 本手册随仓库 clean-reset（根提交 `<root>`）一并生效。

## 0. 核心原则

**单一主干 `master` ＋ 明确所有权 ＋ 推送前必 `pull --rebase`。**

- 不制造长期分叉分支；
- 不盲 `git merge`（会制造分叉节点、引发互相覆盖）；
- 不碰他人所有权目录；
- 二进制 DB 由工具侧**一人独占**维护。

> 上次协作崩坏的根因不是"谁写错了"，而是：① 没有协作契约；② 二进制 `keyword_database.db` 被两边并发改、Git 无法自动合并。本手册专门堵这两点。

## 1. 角色与所有权边界

| 角色 | 定位 | 独占目录 / 文件 |
|------|------|----------------|
| **hermes** | SOP 权威：路由 / 关键词策略 / SKILL 定义 / 视觉管线 | `SKILL.md`, `agents/`, `references/`, `keyword-grader/`, `handoff/`, `docs/`, `INCIDENTS/`, `knowledge-base/`, `logistics/`, `archive/`，以及所有 SOP·视觉 skill：`aistudio-design-plan`, `aistudio-image-bridge`, `qwen-listing-optimizer`, `listing-v1-seo-builder`, `hicustom-product-info`, `hicustom-synthesis`, `qwen-image-mcp`, `doubao-image-mcp`, `qianwen-image-downloader`, `doubao-raw-grabber`, `glm52-caller`, `glm52-nim` |
| **home-workbuddy / office-workbuddy** | hermes 的外包工具团队（**当前执行实例 = office-workbuddy**）：数据管道 / CLI / 采集 / DB | `tools/`, `keyword-source/`, `pipeline/`, `keyword_database.db`，以及入库（`process_dual.py` 等）/ 出库（`keyword_tool.py` 等）脚本 |

**铁律**：只改自己所有权内的目录。跨所有权改动 → 先在 `handoff/` 或 issue 协商，达成共识再动。

## 2. 分支模型：单一主干

- **唯一长期分支 = `master`**。禁止 `feat/*`、`*-retier`、`master-sync-*` 等长期分支。
- 临时分支仅用于本地试验，**24 小时内必须 rebase 回 master 并删除**。
- 推送前一律：
  ```bash
  git pull --rebase origin master
  git push origin master
  ```
  禁止 `git merge`（制造分叉节点 → 互相覆盖）。

## 3. 数据资产规则（最关键的防冲突项）

`keyword_database.db` 是二进制单文件，Git **无法**自动合并。这是上次协作崩坏的唯一技术根因。

- **独占权**：`keyword_database.db` 由 **home-workbuddy / office-workbuddy** 独占维护；hermes 只读，不写。
- **改前必拉**：任何改 DB 的操作，第一步 `git pull --rebase` 拿最新版本，绝不在陈旧副本上改。
- **改完即推**：DB 变更后**立即** commit + push，缩短他人基于旧版本编辑的窗口。
- **提交注明**：DB 相关 commit message 必须写明影响范围（如「重排 SPU S3-16/S7-07 西柚词」），方便他人判断是否需先同步。
- 禁止把 DB 放进会并发编辑的临时分支。

## 4. 提交规范

- 每条 commit 带身份标签：`[agent: home-workbuddy]` / `[agent: hermes]` / `[agent: office-workbuddy]`。
- 消息写「做了什么 + 影响范围」，不写废话。

## 5. 禁止事项（违反即回滚）

1. ❌ `git push --force` 到 master（仅「全员同意的清仓重置」例外）。
2. ❌ 删除 / 改写他人所有权目录。
3. ❌ 盲 `git merge`（制造分叉）。
4. ❌ 多 Agent 同时改同一二进制 DB 且不先同步。
5. ❌ 长期分叉分支堆积（>24h 未合回）。

## 6. 冲突自救

- 发现分叉：先 `git fetch` → `git pull --rebase`；rebase 冲突只在自己文件上解决。
- 误 `merge` 造成树损坏：立即 `git merge --abort`，从 `*.bundle` 备份还原，**不要硬推**。
- 重大操作前：`git bundle create backup.bundle --all`。

## 7. 新协作者 onboarding

1. 读本手册 → 2. `git clone` → 确认自己所有权目录 → 3. 只在自己目录工作，推送前 rebase。

---

*本手册由 office-workbuddy 在 clean-reset 时起草，hermes 复核所有权边界后生效。*
