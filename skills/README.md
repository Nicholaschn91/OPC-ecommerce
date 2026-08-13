# skills/ — 技能源码目录（布局规约）

> 本目录存放所有技能。布局错误会导致"能同步但不能被 WorkBuddy 加载"。

## 铁律（对应 INCIDENTS/2026-08-13 的复盘）

1. **摊平存放**：每个技能直接放在 `skills/<skill-name>/SKILL.md`。
   - ✅ `skills/hicustom-product-info/SKILL.md`
   - ❌ `skills/skills/hicustom-product-info/SKILL.md`（多套一层，不发现）
2. **禁止 `.zip`**：不要把技能打成 `verified-skills-xxxx.zip` 丢仓库根或本目录——不会被自动解压、不会加载。要分发就展开成目录。
3. **每个技能前台 matter**：`SKILL.md` 顶部 `name` / `description` 必填，否则加载失败。
4. **密钥不入库**：token/密钥放 `references/config.json`（本地、不提交），或走环境变量。

## 新增技能流程

1. `skills/<your-name>/` 下建 `SKILL.md`。
2. 在 `VERSIONING.md` 登记版本（frontmatter `version:` 字段）。
3. 仅在 AGENT_BOUNDARIES.md 划给你的目录下建；跨边界先 handoff。
