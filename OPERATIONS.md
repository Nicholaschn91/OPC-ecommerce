# OPERATIONS.md — 协同操作协议（铁律②）

> 本文件是**唯一正确**的 git 协同操作手册。任何 Agent 改仓库前必须先读本文件。
> 过去的崩坏（历史被强推改写、多克隆分叉、假成功）全部源于违反本文件。

## 1. 单一真相源

- **每台机器只保留 1 份克隆**，remote 统一指向 canonical 仓库 `https://github.com/Nicholaschn91/OPC-ecommerce.git`。
  > 用户确认：**OPC-ecommerce 是唯一 canonical 仓库**；旧的 `multi-agent-sop-github` 本地副本已过期、不再维护，删除即可。
- 发现重复克隆（如 `multi-agent-sop-github`、`xxx/.qclaw/.../multi-agent-sop` 等多份）→ 立即删到只剩 1 份。
- **凭证卫生（git 通道铁律）**：
  - 用 `gh auth login`（设备流）+ `gh auth setup-git`，让 git 通过 gh token 走 **https**；
  - **禁止**在 remote URL 里硬编码 token（旧 `ghp_fjC...` 已死，会静默失败）；
  - **禁止**用 `git@github.com` SSH（本机无 SSH 密钥，会断）；
  - **禁止**全局 `insteadOf` 改写规则：它会把 https 静默拐成 ssh（或反之），造成"假成功"。
    推送前自检：`git config --global --get-regexp insteadof` 应**为空**；若残留 `git@github.com:` 开头或任何改写 `https://github.com` 的规则，立即
    `git config --global --unset '<对应 key>'`。详见 INCIDENTS/2026-08-git-insteadof-fake-success.md。

## 2. 标准推送流程（每次都照做）

```bash
# 1) 切到唯一克隆
cd <唯一克隆路径>

# 2) 改前必拉，用 rebase 避免分叉节点
git pull --rebase origin master

# 3) 只改自己名下目录（见 AGENT_BOUNDARIES.md）
# ... 编辑 ...

# 4) 提交（message 写清影响范围）
git add <具体文件>
git commit -m "feat(scope): 一句话说明"

# 5) 推送
git push origin master
```

## 3. "推送成功"的正确判定（关键！）

**不要把本地 `git push` 的 exit code 当成功。** 必须校验远端：

```bash
BEFORE=$(git rev-parse origin/master)     # 推送前记录
git push origin master
sleep 2
AFTER=$(git ls-remote origin master | awk '{print $1}')
if [ "$BEFORE" = "$AFTER" ]; then
  echo "❌ 推送未生效（远端 HEAD 未前进）— 检查是否被拒/推错分支"
else
  echo "✅ 推送成功，远端已前进"
fi
```

> 历史上 office 报"推送成功"但 GitHub 零提交，根因是 git 全局 `insteadOf` 把 https 拐成 ssh、ssh key 失效（详见 INCIDENTS/2026-08-git-insteadof-fake-success.md）；
> 只盯本地 exit code 也会掩盖问题。两者都要防。
> 若 push 被拒（non-fast-forward / unrelated history），说明**本地历史与远端脱节** →
> 先 `git fetch origin`，再 `git rebase origin/master`，解决冲突后重推。**绝不 force。**

## 4. 永久禁令

- ❌ `git push --force` 到主干（清仓重置须三方书面共识 + 全员 `reset --hard` + 写 INCIDENTS 复盘）。
- ❌ `git merge` 制造分叉节点（用 `pull --rebase`）。
- ❌ 盲 `git add .` 把 `.workbuddy/`、密钥、二进制一股脑提交。
- ❌ 多 Agent 同时改同一二进制 DB 且不先同步。

## 5. 分叉/失联处理

1. `git fetch origin` → `git pull --rebase origin master`。
2. rebase 冲突：只在**自己文件**上解决，别人文件 `git checkout --theirs`。
3. 误 `merge` 造成树损坏：立即 `git merge --abort`，从备份 bundle 还原，**不硬推**。
4. 重大操作前：`git bundle create backup.bundle --all`。

## 6. 收尾

- 推送后在本文件或 `VERSIONING.md` 留痕。
- 发现新坑 → 写 `INCIDENTS/<日期>-<主题>.md`，并在本文件第 7 节追加一条禁令。
