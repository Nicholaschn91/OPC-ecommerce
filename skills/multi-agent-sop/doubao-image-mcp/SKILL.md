---
name: doubao-image-mcp
description: "[阶段2·图生图·豆包Seedream5.0Lite·首选] 通过 CLI（scripts/doubao_img2img.cjs，用户明确授权的专用 skill，复用独立 profile 豆包登录态）或 browser-doubao MCP 驱动豆包「AI 创作」工作台（doubao.com/chat/create-image），做图生图（⚠️模型硬约束 Seedream 5.0 Lite）并下载无水印原图 + verify-img.py 预筛。阶段 2 首选（用户 2026-08-10 实测一致性优于千问），千问 qwen-image-mcp 为备选。仅用于「线一全量」与「线二全量」两条需垫图线：必传垫图 + 终版 PROMPT 形成约束对。触发词：用豆包出图/豆包图生图/垫图出图。✅ 2026-08-13 home-workbuddy 真跑闭环通过（拟人化 + 识别验证暂停已落盘 CLI）；✅ 已 CLI 化 + 步骤 SKILL 化（2026-08-13 已解锁进入维护态）。⚠️ 模型硬约束 Seedream 5.0 Lite（4.5/4.0/5.0 Pro 一律不用）。"

> 🔒 **LOCKED · v1.0 定稿版 · 2026-08-14 · 不要再改** · 傻瓜式说明书
agent_created: true
---

> 🛠️ **维护声明（2026-08-13 已解锁）**：本 skill 经 home-workbuddy 实测修复（CDN 正则过期 + 拟人化抖动 + 图片识别验证暂停，均已落盘进 `scripts/`）。现处于可维护状态：改动须经实测验证后提交，commit 带上 `[agent: home-workbuddy]` trailer。

# doubao-image-mcp — 豆包 AI 创作图生图（CLI 首选 / MCP 兜底）

## 三维路由定位（本 skill）
> 全链路由「线别 × 模式 × 工具」三个维度决定调用哪个 skill。本 skill 只负责**阶段 2 · 图生图**，且是**首选**。

- **阶段**：阶段 2 · 图生图（垫图 + PROMPT → 出变体原图）
- **线别**：仅「线一全量」与「线二全量」两条**需要垫图**的线（非全量/小改线不进图生图）
- **工具**：豆包 AI 创作（Seedream 5.0 Lite，硬约束），`browser-doubao` MCP
- **定位**：阶段 2 **首选**（用户实测一致性优于千问）；`qwen-image-mcp` 为备选/兜底
- **上游**：`qwen-listing-optimizer` 阶段 1 产出的 7 段 PROMPT + spec 参考图（约束对）
- **触发词**：用豆包出图 / 豆包图生图 / 垫图出图
- **状态**：闭环实测通过（2026-08-13，home-workbuddy 真跑确认；原 `CDN_RE` 正则过期 `/rc_gen_image/` 已修正为 `tos-cn-i-a9rns2rl98/<hash>.png`），可独立完成参考图+PROMPT→出图→下载→预筛

| 维度 | 本 skill 取值 |
|---|---|
| 阶段 | 2（图生图） |
| 线别 | 线一全量 / 线二全量 |
| 模式 | 全量（需垫图） |
| 工具 | 豆包 Seedream 5.0 Lite（首选，⚠️ 硬约束） |

## ⚠️ 模型硬约束（用户 2026-08-10 明示，不可违反）
> **垫图图生图必须且只能是 Seedream 5.0 Lite。**
> 4.5 / 4.0 / 5.0 Pro 一律不用。每次执行 Step 3 都要**先读当前模型值 → 非 5.0 Lite 则切换 → 再读回确认**（幂等，避免重复点错模型）。
> 缘起：用户实测 5.0 Lite 出图一致性最佳；此前误用 4.5 出的 `img1_doubao_gen.jpg` 已作废，正确产物为 `img1_doubao_5.0Lite.jpg`（verify 4/7，R3/R5/R7 为算法局限非质量问题）。
> 切换/确认选择器与幂等代码见 **Step 3**；比例选项清单见 **Step 6**。

## CLI 自动模式（首选）
> **操作已 CLI 化**：`scripts/doubao_img2img.cjs`（Node + Playwright，复用 doubao-raw-grabber 的 `--profile` 浏览器驱动模式 —— 用户明确授权的专用 skill）。
> **弱模型 / 批量出图一律走 CLI**：不依赖对话上下文、不靠人手一步步点，确定性、可重跑、换弱模型同效。

```bash
node scripts/doubao_img2img.cjs \
  --ref "img1_hero_coffee-front_002.jpg" \
  --prompt "img1_PROMPT.txt" \
  --out "gen/img1_doubao_5.0Lite.jpg" \
  --ratio 1:1 \
  --verify
```
- **参数**：`--ref` 参考图 / `--prompt` prompt 文本文件 / `--out` 输出图 / `--ratio` 默认 1:1（可选 自动/9:16/2:3/3:4/1:1/4:3/3:2/16:9）/ `--profile` 登录 profile（默认本 skill 的 `doubao-profile`）/ `--headed` 有头 / `--verify` 出图后跑 verify-img.py / `--report` 报告路径 / `--gen-timeout` 生成超时(ms)。
- **模型硬约束内置**：CLI 启动即幂等切到 **Seedream 5.0 Lite**，非 5.0 Lite 自动切换并读回确认；切不到直接报错退出（绝不降级到 4.5/4.0/5.0 Pro）。
- **完整流程内置**：打开工作台 → 登录校验 → 切模型 → 上传参考图（`input.input-I22ghh` setInputFiles）→ 注入 Prompt（`.tiptap.ProseMirror` insertText）→ 设比例 → 点 `#flow-end-msg-send` → 捕获 `tos-cn-i-a9rns2rl98/<hash>.png` 生成图 CDN URL（全质量 `-image.png` / 预览 `-image-qvalue.png`）→ 下载（fetch + Referer）→ 可选 verify-img.py。
- ⚠️ **profile 隔离铁律**：CLI 与 browser-doubao MCP **共用同一 skill 的 `doubao-profile`**，二者【不要同时】拉起 Chrome。运行 CLI 前请先在连接器管理处停用 browser-doubao MCP（或关掉其占用该 profile 的 Chrome），避免 Chrome 单例锁冲突。登录态已在该 profile 中，无需重新登录。
- 选择器 / 幂等代码细节见下方「手动 / MCP 模式」Step 3 / Step 4 / Step 6 —— CLI 是这些步骤的确定性封装。
- `node scripts/doubao_img2img.cjs --help` 查看完整参数与帮助。

## ⚠️ 本 skill 当前状态（2026-08-13 重测更新，2026-08-10 已上锁）
**闭环实测通过**（2026-08-13 实测带参考图完整链路；此前 `CDN_RE` 正则过期导致 120s 超时 FATAL，已修复）：
- ✅ MCP server `browser-doubao` 已配置并 Trust
- ✅ 登录态已验证（账号 100353，2026-08-13 本机登录）
- ✅ 工作台入口：`https://www.doubao.com/chat/create-image`
- ✅ **参考图上传入口已定位**（见 Step4）
- ✅ 顶层控件：`模型 Seedream 5.0 Lite` / `比例 自动` / `风格` / 发送按钮 `#flow-end-msg-send`
- ✅ 「图像/视频」tab
- ✅ Prompt 注入路径（contenteditable + keyboard.insertText）
- ✅ 出图 CDN 域名：`pX-flow-imagex-sign.byteimg.com`（PNG，全质量 `-image.png` / 预览 `-image-qvalue.png`；下载需带 `Referer: https://www.doubao.com/`，CLI 已内置）
- ✅ 出图后页面跳转到 `chat/{conversationId}` 对话页
- ✅ verify-img.py 预筛通过 4/7（R3/R5/R7 失败为检测算法局限，非出图质量问题）
- ✅ 「比例」弹层选项列表已全取（实测 8 项：自动/9:16/2:3/3:4/1:1/4:3/3:2/16:9，见 Step 6）
- ✅ 模型硬约束 Seedream 5.0 Lite 切换/确认选择器已探明并幂等（见上方「模型硬约束」+ Step 3；2026-08-10 用户明示）
- ✅ **操作已 CLI 化**：`scripts/doubao_img2img.cjs`（Node + Playwright，`--profile` 模式，2026-08-10 用户明示"操作CLI化、步骤SKILL化、并上锁"）
- 🔓 **本 skill 已解锁（2026-08-13）**：可接受经实测验证的修改；每次改动须先跑通再提交，避免回归。
- ❌ 「整页 list 收割」未测过

**使用建议**：
- **首选 CLI 模式**：`node scripts/doubao_img2img.cjs ...`，弱模型 / 批量出图同效、可重跑。
- 本 skill 已可独立完成「参考图 + PROMPT → 豆包图生图 → 下载 → 预筛」完整闭环。
- 默认阶段 2 首选走本 skill；千问 `qwen-image-mcp` 作为备选/兜底。

## 何时使用
- 要在豆包网页端用「AI 创作」做图生图（传参考图 + 文本 prompt → 生成变体）。
- **优先用 CLI**：`node scripts/doubao_img2img.cjs --ref <参考图> --prompt <prompt.txt> --out <输出.jpg> [--ratio 1:1] [--verify]`（确定性、可重跑、弱模型同效，见上方「CLI 自动模式」）。
- 交互调试才用 playwright MCP（`mcp__browser-doubao__*` 工具），不走 playwright-core。
- 下载生成的无水印原图 PNG 到本地目录。
- 「真实使用垫图」模式：从 `qwen-listing-optimizer` 终版产物里抽 7 段 PROMPT，对应上传 7 张参考图，用本技能做闭环出图。

## 与 qwen-image-mcp 的边界（用户 2026-08-10 决策）
- **阶段 2 首选 doubao**（你实测图生图一致性更强）
- **千问作为备选**（保底方案，UI 探明度 100%）
- 两个 skill **共用 verify-img.py**（同一份脚本可对两平台出图做预筛）

## 前置条件（必读）
1. `mcp.json` 必须存在 `browser-doubao` server，`--user-data-dir` 指向 `C:/Users/nicho/.workbuddy/skills/doubao-image-mcp/doubao-profile`。
2. 该 profile 需用户**手动有头登录一次**（同 cdp-profile-h 的初始登录流程）。登录后 cookies 落入 profile。
3. **profile 隔离铁律**：本 profile 与 doubao-raw-grabber 的 `WorkBuddy/2026-08-01-16-56-12/doubao-profile` **不同**，避免抢 Chrome 单例锁。
4. 浏览器用系统 Chrome（`--browser chrome`），版本 ≥ 149。
5. 该 server 必须在 WorkBuddy 连接器管理界面 **Trust** 后才会连上（未 Trust 时 `DeferExecuteTool` 报 "not found in deferred tools index"）。

## 工具清单（来自 playwright MCP，命名同 qwen-image-mcp）
- `mcp__browser-doubao__browser_navigate`
- `mcp__browser-doubao__browser_snapshot`
- `mcp__browser-doubao__browser_find`
- `mcp__browser-doubao__browser_click`
- `mcp__browser-doubao__browser_type`
- `mcp__browser-doubao__browser_file_upload`
- `mcp__browser-doubao__browser_wait_for`
- `mcp__browser-doubao__browser_network_requests`
- `mcp__browser-doubao__browser_evaluate`
- `mcp__browser-doubao__browser_take_screenshot`
- `mcp__browser-doubao__browser_run_code_unsafe`（关键工具，详见下方）
- `mcp__browser-doubao__browser_close`

## 工作台入口
```
https://www.doubao.com/chat/create-image
```
- 标题：`AI 创作`
- 顶部 Tab：**图像**（默认选中） / 视频
- 模型选择器：`Seedream 5.0 Lite`（**硬约束，见上方「模型硬约束」+ Step 3**；进工作台可能已是 5.0 Lite，但仍须读值确认）
- 控件：`比例 自动` / `风格` / `模板` / `Previous slide` / `Next slide`
- 输入框：`textbox` placeholder「描述你想要的图片」

## 手动 / MCP 模式（诊断兜底 · 已锁定）
> 以下为通过 **browser-doubao MCP** 手动驱动豆包的步骤，供**交互调试 / CLI 兜底**使用。日常批量出图请走上方 **CLI 模式**（确定性、可重跑、弱模型同效）。两模式选择器 / 幂等逻辑完全一致，CLI 是这些步骤的封装。

### Step 1 — 打开工作台
```
browser_navigate { url: "https://www.doubao.com/chat/create-image" }
```

### Step 2 — 校验登录态
```
browser_run_code_unsafe { code: "(page) => page.evaluate(() => ({ ...登录态探针... }))" }
```
- 若出现「登录」按钮 → 未登录（profile 失效或登录过期）。**停止**，让用户重新登录。
- 若侧栏出现用户账号标识（如「用户266261」） → 已登录。

### Step 3 — 选模型（⚠️ 硬约束：必须 Seedream 5.0 Lite）
**用户硬性约束（2026-08-10）**：垫图图生图**必须**使用 **Seedream 5.0 Lite**。进工作台可能默认已是 5.0 Lite，但**每次都要先读当前值再决定是否切换**，确保幂等（避免重复点错模型）。

**模型弹层选项（实测，radix `role="menu"`）**：
- `Seedream 5.0 Pro`（升级·专业出图，4倍消耗）
- `Seedream 5.0 Lite`（进阶效果，3倍消耗）← **目标**
- `Seedream 4.5`（日常生成）
- `Seedream 4.0`（基础生图）

**幂等切换代码**（始终用 `browser_run_code_unsafe` 包整段）：
```javascript
// 先 Escape 关弹层 → 点开"模型"按钮 → 读当前值 → 非 5.0 Lite 则切换 → 读回确认
async (page) => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  await page.keyboard.press('Escape'); await sleep(600);
  const modelBtn = page.getByRole('button', { name: /模型|Seedream/ });
  await modelBtn.click(); await sleep(800);
  const cur = await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find(e => /Seedream/.test(e.textContent || ''));
    return b ? b.textContent.trim() : '';
  });
  console.log('MODEL_BEFORE=', cur);
  if (!/5\.0 Lite/.test(cur)) {
    await page.getByRole('menuitem').filter({ hasText: 'Seedream 5.0 Lite' }).click();
    await sleep(800);
  }
  await page.keyboard.press('Escape'); await sleep(400);
  const after = await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find(e => /Seedream/.test(e.textContent || ''));
    return b ? b.textContent.trim() : '';
  });
  console.log('MODEL_AFTER=', after);
}
```
- **选择器要点**：用 `getByRole('menuitem').filter({ hasText: 'Seedream 5.0 Lite' })` **字面匹配**（**不要**用正则 `/Seedream 5\.0 Lite/` —— JS 字符串内 `\\.` 在 Playwright 正则里被双重转义，导致不匹配、超时）。
- **弹层容器**：模型弹层是 radix popper 的 `role="menu"`；读回当前模型值从顶层含"Seedream"文本的 `button` 取。
- 切回确认 `MODEL_AFTER` 含 `5.0 Lite` 才算成功（双向切换 5.0 Lite↔4.5↔5.0 Lite 实测 100% 稳定）。

### Step 4 — 上传参考图（✅ 已定位，2026-08-16 实测）
**入口**：输入框工具栏最左侧的 **"+" 圆形按钮**（SVG path = 加号十字，36×36px）。
**底层机制**：该按钮关联一个隐藏的 `<input type="file" class="input-I22ghh" multiple accept=".jpg,.png,.jpeg,.webp,.apng">`。
**上传方法（推荐，不触发 filechooser modal）**：
```javascript
// 直接用 setInputFiles 喂隐藏 input（绕开 filechooser 弹窗，避免千问式卡死）
await page.setInputFiles('input.input-I22ghh', '/absolute/path/to/reference.jpg');
await page.waitForTimeout(5000); // 等缩略图渲染
```
**验证上传成功**：输入框左侧出现 `blob:` 缩略图（class=`image-Q7dBqW`，52×52px），输入框被下推约 66px。
**注意**：
- 该 input 支持 `multiple=true`，可一次上传多张参考图。
- **不要用** `waitForEvent('filechooser')` + `fc.setFiles()` 方式（千问实测会卡死 filechooser modal）。
- `setInputFiles` 是 Playwright 原生 API，直接操作 hidden input，稳定可靠。

### Step 5 — 填 PROMPT
- `page.locator('textbox[active]').click()` → `page.keyboard.insertText(PROMPT)`（同千问坑：contenteditable/textarea 用 insertText 才触发 React state）
- PROMPT 格式：`PROMPT 全文 + \n\nNegative: <NEGATIVE 列表>`（豆包无独立 negative 字段，并入主 prompt）

### Step 6 — 设比例（幂等，可选；默认"自动"也出 1:1）
如需指定比例（如 1:1），点「比例」按钮 → 弹层（radix popper）→ 点选项。

**比例弹层选项（实测全部 8 个）**：`自动` / `9:16` / `2:3` / `3:4` / `1:1` / `4:3` / `3:2` / `16:9`

**幂等点击代码**（先 `Escape` 关弹层等 800ms 再开，避免连续快点点错）：
```javascript
async (page) => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const ratio = process.env.RATIO || '1:1';  // 传入需选的比例
  await page.keyboard.press('Escape'); await sleep(800);
  const ratioBtn = page.getByRole('button', { name: /比例/ });
  await ratioBtn.click(); await sleep(800);
  await page.locator('[data-radix-popper-content-wrapper]')
            .getByText(ratio, { exact: true }).first().click();
  await sleep(600);
  await page.keyboard.press('Escape'); await sleep(400);
  const after = await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')].find(e => /比例/.test(e.textContent || ''));
    return b ? b.textContent.trim() : '';
  });
  console.log('RATIO_AFTER=', after);
}
```
- **关键点**：比例弹层容器是 `[data-radix-popper-content-wrapper]`（**不是** `role=menuitem`，那是模型弹层）。选项用 `getByText('1:1', { exact: true })` 精确文本节点匹配（文本正则 `^\d{1,2}\s*[:：]\s*\d{1,2}$` 也能扫到全部 8 项）。
- **不要连续快速点击**同一弹层（会状态错乱超时），每步先 `Escape` 关 + 等 800ms 再开。
- 不指定时默认"自动"也可出 1:1 方图（实测），但终版为确定性起见建议显式点 `1:1`。

### Step 7 — 提交生成（✅ 已定位）
- 发送按钮 ID：**`#flow-end-msg-send`**（蓝色圆形按钮，工具栏最右侧，带白色 ↑ 箭头图标）
- 用 `page.click('#flow-end-msg-send')` 精确点击（不要用 class 选择器，页面有 31 个同 class 蓝色按钮）
- 验证：`data-disabled="false"` 且 `data-loading="false"` 时可点击
- 点击后页面跳转到 `chat/{conversationId}` 对话页，标题自动取自 prompt 内容

### Step 8 — 等待生成（✅ 已探明）
```
browser_run_code_unsafe { code: "(page) => { await page.waitForTimeout(25000); ... }" }
```
- **出图 DOM 信号**：生成完成后，对话区出现 `<picture><img src="https://pX-flow-imagex-sign.byteimg.com/tos-cn-i-a9rns2rl98/<hash>.png~tplv-...-image.png">`（全质量）/ `-image-qvalue.png`（预览，320×320）`
- 图片 class=`image-Q7dBqW`，默认显示 151×151（CSS 缩略图），实际分辨率更高
- CDN 域名：`p11-flow-imagex-sign.byteimg.com`（字节跳动图片服务）
- **模型文字确认**：豆包会在图片下方输出一段确认文字（如"已生成 img1 — Hero：Coffee Brown 正面主图。"）
- 生成时间：实测约 20-30 秒（Seedream 5.0 Lite）

### Step 9 — 下载原图（✅ 已验证）
```bash
# CDN URL 直接 curl 下载，需带 Referer / 无防盗链
curl -sL --max-time 90 -H "Referer: https://www.doubao.com/" -o "gen/img1_doubao.png" "https://pX-flow-imagex-sign.byteimg.com/tos-cn-i-a9rns2rl98/{hash}.png~tplv-{params}?{sig_params}"
```
- 格式：PNG（全质量 `-image.png` / 预览 `-image-qvalue.png`；CLI 默认优先全质量）
- 签名参数含 `x-expires`（URL 有效期很长，实测到 2101 年）
- **无需 cookie / 需带 Referer: https://www.doubao.com/**（无水印，AI 生成小标签在左上角，不影响使用）

### Step 10 — verify-img.py 预筛（与 qwen-image-mcp 通用）
```bash
python $SK/../qwen-image-mcp/scripts/verify-img.py \
  --ref <参考图.png> --out <出图1.png> <出图2.png> ... \
  --prompt <PROMPT.txt> --ratio 1.0 --report <报告.json>
```

### Step 11 — 人工 spot check
- 同 qwen-image-mcp。

## 关键陷阱（已实测修正）
1. **~~「参考图」入口未明~~ → 已解决**：工具栏左侧"+"按钮 → 隐藏 input `input-I22ghh` → `setInputFiles()` 直接喂图。**不要用 filechooser 方式**（会卡死）。
2. **比例弹层选项列表已全取（2026-08-10 实测）**：`[data-radix-popper-content-wrapper]` 容器内精确文本匹配 8 项：自动/9:16/2:3/3:4/1:1/4:3/3:2/16:9。点法见 Step 6，每步先 `Escape` 关弹层等 800ms（连续快点点错会超时）。
3. **出图 DOM 信号**：`p11-flow-imagex-sign.byteimg.com` CDN，图片在 `<picture><img class="image-Q7dBqW">` 里。
4. **Seedream 模型安全过滤词**：可能与千问不同（待积累黑名单）。
5. **「风格」按钮 ≠ 参考图按钮**：f2e472 是风格选择器；参考图是独立的"+"按钮（工具栏最左）。
6. **工具索引掉线**：同 qwen-image-mop，navigate/snapshot 后 `browser_click` 等可能掉索引，统一用 `browser_run_code_unsafe` 包整段交互。
7. **发送按钮选择器陷阱**：`button.bg-dbx-text-highlight` 匹配 31 个元素（含所有"做同款"按钮），必须用 **`#flow-end-msg-send`** ID 精确选择。
8. **verify-img.py R3 假阳**：跨品类参考时（参考图=托特包，出图=钱包），HSV cosine 自然低，不等于出图质量差。R7 同理（深色背景大面积暗区被误判为 flat patch）。
9. **⚠️ 生成图 CDN URL 格式已变（2026-08-13 实测修复）**：旧文档/正则写的是 `.../rc_gen_image/...jpeg`，但当前豆包生成图 URL 为 `pX-flow-imagex-sign.byteimg.com/tos-cn-i-a9rns2rl98/<hash>.png~tplv-...-image.png`（全质量）或 `...-image-qvalue.png`（320×320 预览）。**没有 `/rc_gen_image/` 段**——若 CLI `CDN_RE` 仍匹配旧格式会 120s 超时 FATAL。CLI 已修正为正则 `/tos-cn-i-a9rns2rl98\/(?!rc\/icon).+\.(png|jpeg)/` 且优先抓全质量。
10. **⚠️ 豆包有图片识别验证（非滑块）**：生成/加载期间可能弹「点选图片」类验证。CLI 已把**拟人化抖动**（逐字打字、各步随机停顿）和**验证暂停**烘焙进 `scripts/`，弱模型跑命令即生效，无需读本文。运行期若弹验证，CLI 会暂停并提示：在该 profile 目录（`doubao-image-mcp/doubao-profile/`）创建空文件 `VERIFY_DONE.txt` 即续跑（最多等 30 分钟）。分辨率非固定 1024：CLI 按原生 CDN URL 抓取，1:1 出 1024、2048 或其他比例均按真实尺寸落盘（日志打印 `dims=WxH`）。
11. **⚠️ 录完 Prompt → click send 必须确定性等 React state sync（2026-08-13 22:4x 用户实测诊断）**：loc.fill / insert_text 触发 React 受控组件 onChange 后，React 18 batching 异步合并 state。如果紧跟 click send，提交的是**React 旧 state**（空/上轮残留），而 DOM textarea 显示的是新值——典型现象：「前半部分发了、Negative 段停留」。CLI 已加 `reactStateSyncDelay()` 确定性 `page.waitForTimeout(1500)` 在 inject 内 + send 前再补 800ms，不再赌随机延时。integrity check 现在也轮询等 React 把 input event merge（最多 3 秒）。
12. **⚠️ 文生图必须先切到「图像生成」agent（2026-08-13 22:4x 用户实测）**：CLI 默认上传 ref → 跳 chat 会话发图 = 图生图。文生图（`--text2img`）需要在 doubao chat 工作台点底部 agent 切按钮里的「图像生成」才能让 doubao 出图（chat 模式不会出图）。CLI 已加 `trySwitchToImageGenAgent()` 尝试自动切（best-effort：找不到时 warn 不 FATAL，让用户手动切）。
13. **⚠️ 登录态 fail-fast（2026-08-13 22:4x）**：CLI 在 send 前做 `preflightGenContext()` 自检，若发现"游客模式"或找不到 .tiptap.ProseMirror / chat textarea，直接抛含重登步骤的清晰错误，绝不静默继续。profile cookie 过期处理：在该 profile 目录建空文件 `VERIFY_DONE.txt` 不行（那是验证用）；登录态过期必须用户**重登**（headed Chrome 打开 doubao.com → 登 → 任意操作让页面状态变化）。
14. **browser-doubao MCP 自启动（2026-08-17 改为自启动）**：`browser-doubao` MCP 已配置 `--channel chrome --user-data-dir=...doubao-profile --headed`，**自动拉起 Chrome 并复用本目录 `doubao-profile` 登录态，无需手动开浏览器、无需 `--remote-debugging-port`**。本目录 `doubao-profile` 内含登录态，**禁入库**（`.gitignore` 已加 `doubao-profile/` + `**/*-profile/`）。
15. **⚠️ 单 tab 复用（用户 2026-08-13 22:5x 强约束）**：连跑多次出图任务若用 `page.goto(create-image)` / `browser.newPage()` 反复开新 tab，本地 Chrome 内存会涨。修复：CLI 加 `startNewTaskInSameTab()` —— 优先点页内「**新工作任务**」按钮（doubao 页面提示 "新工作任务 Ctrl Shift K"），或发快捷键 Ctrl+Shift+K，兜底才 navigate（**同 tab**）。同时 CDP 模式拿 page 时 `ctxs[0].pages()[0]` 优先复用，绝不自起新 tab。CDP 模式下 ownedBrowser=false 时 finally 不关浏览器——tabs 不会泄漏，由用户手动维护。

## 待补清单（下个版本完整化）
- [x] ~~参考图上传按钮定位~~ → ✅ 2026-08-13 实测（home-workbuddy 真跑）：工具栏"+"按钮 + `input.input-I22ghh` + `setInputFiles()`
- [x] ~~比例弹层完整选项列表~~ → ✅ 2026-08-10 实测：自动/9:16/2:3/3:4/1:1/4:3/3:2/16:9（8 项，见 Step 6）
- [ ] 风格 / 模板 弹层结构
- [x] ~~出图完成 DOM 信号（含 CDN 域名）~~ → ✅ `p11-flow-imagex-sign.byteimg.com` JPEG
- [x] ~~出图 URL 完整下载链路~~ → ✅ 带 Referer 直接下（无需 cookie）
- [ ] 整页 list 收割（与 doubao-raw-grabber 边界：doubao-image-mcp 写操作 / doubao-raw-grabber 只读）
- [x] ~~跑一次端到端出图 + verify-img.py 预筛~~ → ✅ 2026-08-13 真跑闭环通过（home-workbuddy；原正则过期 FATAL 已修复，复测 PASS，出图 1024×1024 全质量）
- [ ] 实测 R5「主体居中」豆包 fail 率 vs 千问 fail 率（本轮豆包 R5=0.64<0.9 fail，千问类似）
- [x] ~~操作 CLI 化（doubao_img2img.cjs）~~ → ✅ 2026-08-10 用户明示"操作CLI化、步骤SKILL化、并上锁"
- [x] ~~步骤 SKILL 化 + 上锁（锁定声明）~~ → ✅ 2026-08-10 审定；2026-08-13 解锁进入维护态（顶部「维护声明」）

## 与锁定技能的关系
- `qwen-image-mcp` 是本 skill 的**备选实现**（阶段 2 fallback）。当豆包 UI 探明度低、或用户指定走千问时使用。
- `qwen-listing-optimizer` 负责**阶段 1 · 视觉方案设计**（输出 7 段 PROMPT 文字），本 skill 接其产出做**阶段 2 · 图生图**。
- `doubao-raw-grabber` 是**只读 skill**（抓无水印原图），与本 skill 严格隔离：
  - doubao-raw-grabber：READ-ONLY，禁止任何写操作
  - doubao-image-mcp：可写（图生图生成 + 上传垫图），但与 doubao-raw-grabber 用**独立 profile**，避免抢单例锁
  - 不在 doubao-raw-grabber 的浏览器会话里做任何写操作
- 全链条：关键词词库 → qwen-listing-optimizer（文案 + 视觉 Prompt） → **本技能首选 / qwen-image-mcp 备选**（图生图 + 下载 + verify-img 预筛） → 人工 spot check → 上架
