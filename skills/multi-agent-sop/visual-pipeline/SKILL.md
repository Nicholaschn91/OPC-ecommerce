---
name: visual-pipeline
description: "[视觉线总入口·三选一] 在 aistudio(文生图·免费·无参考图) / doubao(图生图·Seedream5.0Lite·需垫图) / qwen(图生图·Qwen-Image·需垫图) 三条生图线间做选择，每条线生图后接对应去水印器，落地即无水印原图到 _e2e_out/<spu>/img/。触发词：生成listing图 / 视觉线 / 生图 / 出图 / 三选一 / 图片线 / 配图。⚠️ aistudio 去水印器(aistudio-raw-grabber)待用户给，当前占位用 blob 下载。"
---

# visual-pipeline — 视觉线三选一编排入口

## 定位
视觉线（listing 配图）总入口。文字线（Stage1→4）出 7 段视觉 PROMPT 后，由本 skill 接管生图。本 skill 是**编排层**，不重复实现生图/抓取，只做四件事：
1. **启动时三选一**（线别选择，让用户拍板）
2. **调用对应生图 skill**
3. **调用对应去水印器**
4. **统一落盘** `_e2e_out/<spu>/img/<spu>_P<n>_<role>.png`

> 目标（用户 2026-08-17 明示）：回来的东西**直接是无水印版本**。每条生图线后面紧跟一个"去水印落原图"环节，落地即干净。

## 三维路由（本 skill 只取「线别」一维）

| 线 | 生图类型 | 生图 skill | 去水印器 | 参考图 |
|---|---|---|---|---|
| **A · aistudio** | 文生图（T2I） | `aistudio-image-bridge` | `aistudio-raw-grabber`（**待给·占位**） | **不需要** |
| **B · doubao** | 图生图（I2I） | `doubao-image-mcp`（CLI `doubao_img2img.cjs`） | `doubao-raw-grabber`（已有·只读） | 需要 |
| **C · qwen** | 图生图（I2I） | `qwen-image-mcp`（MCP / CLI `qwen_gen.py`） | **内生**（生图即落无水印） | 需要 |

> ⚠️ **千问线纠偏（已审定）**：`qianwen-image-downloader` 已于 2026-08-08 废弃（违反「浏览器只认 MCP、禁手搓 Playwright」铁律，其全部能力已被 `qwen-image-mcp` 完整覆盖）。千问线的「去水印落图」= `qwen-image-mcp` 本身（Step1–13 生图后直接 curl 下载无水印原图 PNG，连整页 list 收割都内置）。**禁用废弃脚本，走 qwen-image-mcp。**

## 入口：启动时三选一
用户启动视觉线时，用 AskUserQuestion 三选一（标注每条线的生图类型 / 是否需要参考图）：
- **选项 A · aistudio**（文生图 · 无参考图 · 免费）→ 推荐默认（S3-04 类无参考图 full-scene prompt 最契合）
- **选项 B · doubao**（图生图 · Seedream 5.0 Lite · 需垫图）
- **选项 C · qwen**（图生图 · Qwen-Image · 需垫图）

> B/C 是图生图，必须先备好参考图（空白包 / 供应商原图）；A 是文生图，直接吃 PROMPT。选型决定后续是否要先取参考图。

## 线 A · aistudio（文生图）
1. 调 `aistudio-image-bridge` 黄金流程：`navigate .../new_chat?model=gemini-3.1-flash-lite-image` → 清导览 dialog → `tune` 开 Run settings → 切 `Images only`（radio: `imageImages only`）→ 关 settings 面板（否则遮挡 Run）→ `evaluate` 用 `nativeInputValueSetter` 填 PROMPT（negative 转 `Avoid:` 自然语言，因无独立负向字段）→ 点 Run。
2. **internal error → 点 user turn 的 `Rerun this turn` 恢复**（SKILL 铁律，必现，与 2026-08-17 P1 实测一致）。
3. **下载（已知坑·必做）**：触发下载后 Chrome 会弹**「允许」下载确认窗**，必须检测并**点击「允许」**，否则落盘失败（2026-08-17 P3 实测根因）。稳定路径 = mcp 原生 download 捕获 或 图片查看器 Download 按钮；`dataURL a.click()` 偶发被拦，勿依赖。
4. **去水印（待接 aistudio-raw-grabber）**：用户调试中，给后接入抓取无水印原图，替换步骤3的 blob 下载。当前占位 = blob 下载落盘（可能带水印，待替换）。
5. 落盘 `_e2e_out/<spu>/img/<spu>_P<n>_<role>.png`。**每张用独立 new_chat 跑**（同对话连续 Run 时 Rerun 不生效，2026-08-17 P2 实测）。

## 线 B · doubao（图生图）
1. 调 `doubao-image-mcp` CLI：`node scripts/doubao_img2img.cjs --ref <参考图> --prompt <PROMPT.txt> --out <输出> --ratio 1:1 --verify`（模型硬约束 **Seedream 5.0 Lite**，CLI 内置幂等切换；profile 隔离铁律：与 doubao-raw-grabber 不同 profile，勿同时拉 Chrome）。
2. 去水印：`doubao-raw-grabber`（只读）从对话接口抽 `image_ori_raw.url`：`node scripts/doubao-capture.cjs --url <对话URL> --out <dir>`。
3. 落盘同上。

## 线 C · qwen（图生图）
1. 调 `qwen-image-mcp`：CLI `python scripts/qwen_gen.py --prompt "..." --ref <参考图> --ratio 1:1 --out <dir>`（A 路线 CloakBrowser 隐身，避开千问指纹风控 403）；或 MCP 路线 `launch_cloak_qwen.py` + `mcp__browser_qwen__*`。
2. **去水印内生**：生图即下载 `workspace-zb-cdn.qianwen.com` 无水印原图（默认 4 张变体 PNG），无需额外 grabber。
3. `verify-img.py` 预筛 + 人工 spot check。
4. 落盘同上。

## 统一落盘约定
- 目录：`_e2e_out/<spu>/img/`
- 命名：`<spu>_P<n>_<role>.png`（n=1..7 对应 7 段 PROMPT；role 如 hero / detail / lifestyle / capacity / bridesmaid / gift / labrador）
- **飞书回写**（`设计方案图片` 附件字段 fldRroY1VT / 各平台 `Prompt_Img1-7` 字段）：**属飞书写操作，须用户逐条授权**，本 skill 不擅自写。

## 与文字线衔接
- 上游：`qwen-listing-optimizer` 终版产物 `clean.md` 的 Step4 七段 PROMPT（含 NEGATIVE）。
- 输入：逐段 PROMPT +（B/C 线）spec.angles[] 参考图路径。
- 输出：7 张无水印原图 → 人工终核 → 上架资产。

## 已知约束
- aistudio 免费但需 Google 登录态（`browser-aistudio` MCP 自启动 Chrome 复用 `aistudio-google-profile`；`Upgrade to unlock` 横幅是付费 upsell，不阻断免费生图）。
- doubao / qwen 图生图需先有参考图；S3-04 无参考图故默认走 A。
- 真人出镜图（如 P3 lifestyle）将来上 Amazon 需打 `contains-synthetic-performer` 标（生图本身不受影响）。
- `qianwen-image-downloader`（废弃）与 `aistudio-raw-grabber`（待给）均**不在此 skill 直接调用**；前者禁用，后者待接入。
