---
name: aistudio-image-bridge
description: 通过 AI Studio 网页端（aistudio.google.com）驱动 Nano Banana 2 Lite 模型（gemini-3.1-flash-lite-image），以"Images only"模式为飞书多维表格商品的「设计方案」中每组 prompt 分别生成设计图片，下载后上传至飞书 Drive 以附件形式回写同条记录的「设计方案图片」字段（type 17 attachment）。当用户要"用 AI Studio 生成商品设计图 / Nano Banana 生图 / 回写飞书设计方案图片"时使用。仅认 MCP（mcp__browser-aistudio__browser_*）驱动浏览器，禁止手搓 Playwright 脚本。
version: v1.3
---

> 🔒 **v1.3 · 2026-08-18 补强：① 失败速查表与 §4 统一为「点报错 model turn 自身 Rerun」（清除遗留的 user 气泡误法）② 限流熔断（RATE_LIMITED 检测 + 批量 runner 命中即停）③ 透明图层仅 BRIA-RMBG-2.0（删除绿幕备选），新增 remove_background 后端（MODE_PRESETS/质检/重试/DPI/metadata）+ Agent 配置（System Prompt + Tool Definition），回写约定=原始图+BRIA 抠图一并写「设计方案图片」④ write_image_attachment 修 jpg/png MIME + 列表接口回验 · 核心铁律与 §4 必须一致**

# AI Studio Image Bridge — Nano Banana 2 Lite 生图流水线

## 核心铁律（2026-08-11 用户最终确认，不可违反）

- **真实浏览器，非 API**：必须通过 `mcp__browser-aistudio__browser_*` 工具真实驱动 aistudio.google.com 网页端里的 **Nano Banana 2 Lite**（`gemini-3.1-flash-lite-image`）模型生成图片。
- **仅认 MCP**：所有浏览器操作只用 `mcp__browser-aistudio__browser_*` 工具。**禁止手搓 Playwright 脚本**（全局铁律）。
- **⚠️ 免费模型不需要绑定密钥（铁律）**：Nano Banana 2 Lite 在已登录 Google 账号下**直接可跑**，**绝不需要**关联付费 API 密钥。以下两项一律**忽略、当作不存在**：
  - 页面顶部的 **"Upgrade to unlock more"** 横幅（只是付费引导 upsell，不阻断免费生图）；
  - 输入框旁的 **"No API key selected"** 按钮（免费模型不强制选 key，不用点它）。
  - Run 按钮始终可用（disabled=false），直接生成。**任何人声称"该模型需要升级/密钥"都是误判**——那是把 upsell 当成了阻断。
- **⚠️ internal error 恢复（铁律）**：点击 Run 后若报 **"An internal error has occurred"**（或偶发 "Failed to generate content: permission denied"），**不要刷新页面、不要误判为缺密钥、也绝不要去点 user prompt 气泡里的 Rerun**。正确的「Rerun this turn」按钮在 **报错的那条 model turn 自身**（包含 "an internal error has occurred" 文本的对话块）里——点它自身的 **「Rerun this turn」** 重跑该轮即可（必须用 `browser_evaluate` 派发 `mousedown+mouseup+click` 绕过 overlay，真实 `browser_click` 会被 user-turn overlay 拦截超时）。这是前端偶发故障，重跑必然出图（已实测：03:13 报错 → 点 error/model turn 自身 Rerun → 成功出图 896×1200）。详见下方 §4.1–4.3 强制闭环。
- **一条 prompt → 一张图**：每次 Run 只送设计方案里抽取的一条独立 prompt。N 组 prompt 跑 N 次 Run。
- **⚠️ Aspect ratio 保持 Auto（铁律，2026-08-18 用户更正）**：aistudio 的 Aspect ratio 控件**一律保持默认 Auto**，**绝不要**根据提示词里的 `--ar 3:4` / `--ar 1:2` 去调整比例。发送 prompt 前必须**剥离** `--ar` 令牌（否则模型会被文本指令带偏到非 Auto 比例）。输出尺寸由 aistudio Auto 决定，不由 prompt 里的比例控制。
- **下载时机**：图片生成后对话自动存盘（URL 从 `new_chat` → `prompts/XXX`），存盘后点图片 → 查看器 → Download。落盘位置取决于点击方式（见步骤 6）。
- **飞书回写**：下载到本地后通过飞书 Drive API 上传为附件，拿 file_token 写回「设计方案图片」字段（type 17）。飞书凭证从 `references/config.json` 读取（**不入库**，见 `.gitignore`），本地需自备。
- **写后回读验证**：飞书 `update` 返回 `code:0` 不代表字段真写入，每条写完必须 `get_record` 回读确认。

## 环境 / 凭证

| 项 | 值 |
|---|---|
| MCP | `browser-aistudio`（复用 `aistudio-google-profile`，含已登录 Google 账号 `leiyuzhe007@gmail.com`（Nicholas Lei））|
| AI Studio URL | `https://aistudio.google.com/prompts/new_chat?model=gemini-3.1-flash-lite-image` |
| 模型 | Nano Banana 2 Lite（`gemini-3.1-flash-lite-image`），**免费、非 paid、不绑密钥** |
| 输出模式 | **Images only**（必须切，默认是 Images & text）|
| 飞书 Base | `APP_TOKEN=ONy9bZ0oFaaiSEsf4ggcs61enRc` / `TABLE_ID=tbl75glY29VulRLm` |
| 飞书凭证 | `APP_ID` / `APP_SECRET` 存于 `references/config.json`（gitignored，复制 `config.example.json` 填入）|
| 源字段 | `设计方案`（text）|
| 目标字段 | `设计方案图片`（**attachment** type 17, field_id=`fldRroY1VT`）|
| 下载落盘位置 | ① `browser_click` 原生点击 Download → 落 MCP 沙箱 `.../custom-mcp_aistudio-<hash>/.playwright-mcp/`；② `browser_evaluate` 合成点击 Download → 落 Chrome 默认下载目录 `C:\Users\<user>\Downloads\Generated Image*.png`（本次实测即此路径）|

## ⚠️ self-run 就绪前置（一次性，之后全自动）
- 本 skill 的 `browser-aistudio` 已是**自启动**模式（`mcp.json`：`--browser chrome --user-data-dir=...aistudio-google-profile`，即 Playwright MCP 默认有头）：连接器 Trust 后，调用即由 WorkBuddy 自动拉起 Chrome，**无需手动开浏览器、无需 `--cdp-endpoint`**。
- 但首次跑通需你**一次性**在 `aistudio-google-profile` 里登录 Google（aistudio.google.com 免费模型需已登录账号）：手动有头开一次 Chrome 进 aistudio.google.com 登录，profile 存好 cookie 后，后续自启动复用即免登录。
- aistudio.google.com 国内需代理：确认本机 `127.0.0.1:7897` 代理在跑（self-start Chrome 走该 profile 已存的代理设置）。代理没起 → 导航超时。
- 满足以上，生图→下载闭环全自动（见实测记录 2026-08-14）。

## 依赖脚本（`scripts/`）

| 脚本 | 用途 |
|---|---|
| `parse_design.py` | 解析「设计方案」文本 → 提取每条独立 prompt（block 收集模式）|
| `feishu_products_io.py` | 飞书 CLI：get_record / list_records（凭证读 config.json）|
| `write_image_attachment.py` | 上传图片到飞书 Drive（`medias/upload_all`）→ 写附件字段 + 回读验证（凭证读 config.json）|
| `upload_to_feishu.py` | 同上（备用封装，凭证读 config.json）|
| `ai_studio_gen.py` | **生图 CLI**：输出"一轮生图"的 MCP 命令序列（导航→切 Images only→填 prompt→Run→错误检测）|
| `ai_studio_img2img.py` | **图生图 CLI**：在 Images only 模式下输出上传参考图 + prompt 的 MCP 命令序列 |
| `ai_studio_download.py` | **下载 CLI**：输出点击图片→Download 的 MCP 命令序列 |
| `ai_studio_workflow.py` | 编排：串联 gen/img2img → download，输出完整命令序列 |

> `ai_studio_*.py` 的设计是 **CLI 生成 MCP 命令 JSON**，由执行方照 JSON 逐条调用 `mcp__browser-aistudio__browser_*` 工具。下方"黄金流程"是这些 CLI 产出的、已实测验证的命令本身——直接照做，或用 CLI 生成后再执行均可。

## ⚠️ Rerun 闭环状态机（已修：验证出图、不重发、不查登录态）

> 2026-08-18 用户定向修正：此前失败根因 = ① error 信号被忽略、② Rerun 点击未验证生效、③ 用"连点 3 次仍失败再查登录态"逃避真 bug。下方为唯一权威闭环。

生图轮次里，Run 之后的恢复**不是可选步骤，是强制闭环**：

```
Run
  └─ 4.0 wait 20s
       └─ 4.1 detect "an internal error has occurred"（按文本）
            ├─ NO_ERROR ───────────────► 步骤 5（已出图）
            ├─ ERROR_FOUND_RERUN_READY ─► 4.3 点报错 model turn 自身「Rerun this turn」(一次)
            │                             └─ wait 25s ─► 4.4 校验出图
            │                                  ├─ OK_IMAGE ─► 步骤 5
            │                                  └─ STILL_ERROR / PENDING ─► 停手，如实报告
            └─ ERROR_FOUND_NO_RERUN_BTN / NO_USER_TURN ─► 停手（不重发、不查登录态）
```

**三条不可违反**：
1. Rerun 只点**报错 model turn 自身**那一个（不是 user 内容框），绝不新建 turn、绝不重复发送 prompt。
2. 点完必须 4.4 校验"是否真出图"——只看 `RERUN_CLICKED` 字符串 = 自欺。
3. 任何未达 `OK_IMAGE` 的终态都**停手如实报告**，绝不循环重试、绝不查登录态当借口、绝不宣布假成功。

## 一条生图轮次（已实测验证的黄金流程）

> 以下 ref 会变动，统一用**稳定选择器**（Playwright locator / evaluate），不要用 ref。

### 0. 导航到 Nano Banana 2 Lite
```
browser_navigate:
  url = "https://aistudio.google.com/prompts/new_chat?model=gemini-3.1-flash-lite-image"
```
导航后若弹出导览对话框 / cookie 通知栏，用 evaluate 清掉（不要手点错按钮）：
```
browser_evaluate: () => {
  document.querySelector('dialog[role="dialog"]')?.remove();
  document.querySelector('#glue-cookie-notification-bar-1')?.remove();
  return 'cleared';
}
```

### 1. 切到「Images only」模式（必做）
```
browser_evaluate: () => {
  const btn = [...document.querySelectorAll('button')].find(b => (b.textContent||'').includes('Images only'));
  if (btn) { btn.click(); return 'Images only ON'; }
  return 'NOT FOUND';
}
```

### 2. 填 prompt（用 evaluate nativeInputValueSetter 最稳）
> ⚠️ `browser_type` 在该 React 文本框上经常填不进（placeholder 不消失、Run 不 enabled）。**实测可靠做法是用 evaluate 触发 React 的 input 事件**：
```
browser_evaluate: () => {
  const ta = document.querySelector('textarea[aria-label="Enter a prompt"]');
  if (!ta) return 'textarea not found';
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
  setter.call(ta, '此处放设计方案里的【一条】英文 prompt');
  ta.dispatchEvent(new Event('input', { bubbles: true }));
  return 'Input set: ' + ta.value;
}
```
填完后 `browser_snapshot` 确认 Run 按钮 enabled（不再 `disabled`）。
> ⚠️ **发送前剥离 `--ar` 令牌**：prompt 文本若含 `--ar 3:4` / `--ar 1:2` 之类比例指令，粘贴前**删除**，Aspect ratio 控件保持 Auto（见上方铁律）。

### 3. 点 Run
```
browser_click:
  element: "Run 按钮（输入框工具栏，不是任何 Rerun this turn）"
  target: button:has-text("Run")
```
> 若误点到 Rerun 也无害；关键是别把 "Upgrade"/"No API key" 当阻断。

### 4. 等待 + 错误恢复（Rerun 闭环：发送 → 检查 → 若 error 点 Rerun → 校验出图）

> **这是 agent 执行的 if 闭环，不是一次性命令。每一步都要读上一步的真实返回再决定，绝不凭"点中了"自我安慰。**

**4.0 等待生成**
```
browser_wait_for: time=20
```

**4.1 检测报错（按文本精确匹配，不靠 class）**
```
browser_evaluate: () => {
  const turns = [...document.querySelectorAll('ms-chat-turn')];
  for (let i = 0; i < turns.length; i++) {
    if (/an\s+internal\s+error\s+has\s+occurred/i.test(turns[i].textContent || '')) {
      // Rerun 按钮在包含报错的 model turn 自身，不在 user prompt turn
      const rerun = [...turns[i].querySelectorAll('button')]
        .find(b => (b.getAttribute('aria-label') || '') === 'Rerun this turn'
                   || /rerun this turn/i.test(b.textContent || ''));
      if (rerun) return 'ERROR_FOUND_RERUN_READY';
      return 'ERROR_FOUND_NO_RERUN_BTN';
    }
  }
  return 'NO_ERROR';
}
```

**4.2 分支决策（agent 读 4.1 返回值）**
- `NO_ERROR` → 直接进步骤 5（已出图）。
- `ERROR_FOUND_RERUN_READY` → 执行 **4.3 点 Rerun**。
- `ERROR_FOUND_NO_RERUN_BTN` → **停手**：报告"报错 turn 内未找到 Rerun 按钮"，**绝不重发 prompt、绝不查登录态**。

**4.3 点报错 model turn 的「Rerun this turn」（实测可用的那个；不新建 turn，只点一次）**
```
browser_evaluate: () => {
  const turns = [...document.querySelectorAll('ms-chat-turn')];
  for (let i = 0; i < turns.length; i++) {
    if (/an\s+internal\s+error\s+has\s+occurred/i.test(turns[i].textContent || '')) {
      const rerun = [...turns[i].querySelectorAll('button')]
        .find(b => (b.getAttribute('aria-label') || '') === 'Rerun this turn'
                   || /rerun this turn/i.test(b.textContent || ''));
      if (!rerun) return 'NO_RERUN_BTN';
      // 关键：真实 browser_click 会被 user-turn 的 overlay 拦截 pointer events 而超时，
      // 必须用 mousedown+mouseup+click 稳健派发绕过 overlay 触发 Angular 事件
      rerun.dispatchEvent(new MouseEvent('mousedown', {bubbles:true, cancelable:true, view:window}));
      rerun.dispatchEvent(new MouseEvent('mouseup', {bubbles:true, cancelable:true, view:window}));
      rerun.click();
      return 'RERUN_CLICKED';
    }
  }
  return 'NO_ERROR_TURN';
}
```
```
browser_wait_for: time=25
```

**4.4 校验出图（必须验证"是否真的重新开始生成 / 出图"，不能只信"点中了"）**
```
browser_evaluate: () => {
  const img = [...document.querySelectorAll('img')].find(i => (i.getAttribute('alt')||'').startsWith('Generated Image'));
  if (img) return 'OK_IMAGE';
  const turns = [...document.querySelectorAll('ms-chat-turn')];
  for (let t of turns) if (/an\s+internal\s+error\s+has\s+occurred/i.test(t.textContent || '')) return 'STILL_ERROR';
  return 'PENDING';
}
```

**4.5 终态决策**
- `OK_IMAGE` → 成功，进步骤 5。
- `STILL_ERROR` → 报告"Rerun 已点但服务端仍报 internal error（退化窗口），停手"；**不循环、不重发、不查登录态**。
- `PENDING` / `NO_RERUN_BTN` / `NO_USER_TURN` → 停手，如实报告。

> ⚠️ **铁律**：Rerun 只点一次（正确的那一个）。点完必须走 4.4 校验。无论结果如何，**绝不重复发送 prompt、绝不查登录态当借口、绝不在未验证出图时宣布成功、绝不要刷新页面**。

### 5. 校验出图
```
browser_evaluate: () => {
  const img = [...document.querySelectorAll('img')].find(i => (i.getAttribute('alt')||'').startsWith('Generated Image'));
  return img ? { ok: true, name: img.alt } : { ok: false };
}
```
出图标志：Model 块出现 `img[alt^="Generated Image ..."]`，且块内有 "Good response"/"Bad response" 反馈按钮。

### 6. 下载到本地
```
browser_click:
  element: "Generated Image（打开查看器）"
  target: img[alt^="Generated Image"]
# 查看器打开后
browser_click:
  element: "Download"
  target: button:has-text("Download")
```
> ⚠️ **落盘路径取决于点击方式**（实测结论，2026-08-14）：
> - **`browser_click` 原生点击** Download → 文件被 Playwright 捕获，落到 **MCP 沙箱** `.../custom-mcp_aistudio-<hash>/.playwright-mcp/Generated-Image-<时间戳>.png`。
> - **`browser_evaluate` 合成点击** Download（如 `btn.click()`）→ Playwright 不捕获下载事件，文件落到 **Chrome 默认下载目录** `C:\Users\<user>\Downloads\Generated Image*.png`（本次实测即此路径）。
> 两步都可行，但步骤 7 复制源要对应选对目录。

### 7. 复制到工作区
```bash
# 情形 A：browser_click 原生下载 → MCP 沙箱
SANDBOX="C:/Users/nicho/.workbuddy/logs/mcp-runtime/custom-mcp_aistudio-<hash>/.playwright-mcp"
cp "$SANDBOX/Generated-Image-*.png" ./<record_id>_<label>.png

# 情形 B：evaluate 合成点击下载 → Chrome 默认 Downloads
cp "/c/Users/nicho/Downloads/Generated Image*.png" ./<record_id>_<label>.png
```

### 8. 回写飞书（附件）
```bash
python scripts/write_image_attachment.py <record_id> ./<record_id>_<label>.png
# 内部：upload_all → file_token → PUT 附件字段 → get_record 回读验证
```
> ⚠️ 附件字段每次 PUT 会**整体替换**，必须一次性传入该记录的所有图片。
> ⚠️ 飞书凭证须在 `references/config.json` 中自备（见 `.gitignore`，不入库）。

## Path 1：CDP 抓无水印原图（2026-08-18 实测可用）

**背景**：aistudio 网页下载 / DOM `<img>` src 都是**带水印的显示版**（实际是 `data:image/png;base64,...`，约 1-2MB，SHA 与 DOM 一致）。真正的**干净原图**是生成后页面内部 `blob:https://aistudio.google.com/...` 的 `image/*` 响应，格式通常是 **JPEG**，体积更小（约 300-700KB）。

脚本：`scripts/path1_clean_grab.py`

**前置**（必须用真实 Chrome，不能是 Playwright MCP 拉起）：
```powershell
"C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9333 `
  --remote-allow-origins=* `
  --user-data-dir="C:\Users\nicho\.workbuddy\chrome-profiles\aistudio-headed-profile" `
  --proxy-server="http://127.0.0.1:7897"
```

**运行**：
```bash
python scripts/path1_clean_grab.py --prompt-file prompt.txt --out ./out
```

**脚本做的事**：
1. 连 9333，找到/新建 aistudio 标签页；
2. 启用 `Network` 域，从点击 **Run** 开始拦截所有 `image/*` 响应；
3. 在**同一标签页**里完成 Images only → 填 prompt（自动剥离 `--ar`）→ Run → 检测 internal error → 点报错 turn 的 Rerun → 校验出图 → 点 Download；
4. 把捕获到的 `image/*` 字节按 URL 落盘；
5. 同时抓 DOM `<img>` 做 SHA 对比，确认哪个是干净原图。

**识别干净原图**：
- `blob:https://aistudio.google.com/...` → **JPEG，300-700KB → 干净原图**；
- `https://www.gstatic.com/aistudio/watermark/watermark_v4.png` → 水印叠加图层本身（1.5KB，忽略）；
- `data:image/png;base64,...` → 带水印的显示版（1-2MB，SHA 与 DOM `<img>` 一致）。

**注意**：该脚本不依赖 `browser-aistudio` MCP，而是直接走 CDP WebSocket；它只负责生图+抓干净字节，飞书回写仍用 `scripts/write_image_attachment.py`。

**限流熔断（2026-08-18 补强）**：脚本每轮轮询与 Rerun 前都会用 `RATECHECK` 扫描整个 `document.body` 文本，命中 `rate limit / too many requests / try again later` 即判定 `RATE_LIMITED`，立即中止轮询与空耗重试、`exit(10)`。批量 runner（`run_ab_clean.py`）见到 `exit(10)` 或 stdout 含 `RATE_LIMITED` 会**立即停止整批**——因为免费额度是账户级时间窗限额，同窗口内后续 prompt 必败，继续跑只是浪费。限流恢复只能等窗口重置，无法靠重试绕过。DIAG 也改为抓取 `body.innerText`，确保限流横幅（位于 `ms-chat-turn` 之外）能落进日志，不再"看不见"而误判为静默失败。

## 透明图层 / 抠图：BRIA-RMBG-2.0（唯一路径，2026-08-18 用户拍板）

**关键事实**：Nano Banana 2 Lite（`gemini-3.1-flash-lite-image`）**无法直出透明 PNG**——Google 图像模型全家族都只输出 flat RGB、无 alpha 通道（prompt 写"transparent background"也只给白/黑/棋盘格不透明像素）。因此透明图层走**后端抠图**：Path 1 取干净原图（JPEG）→ `bria_rmbg_cutout.py`（BRIA-RMBG-2.0）抠出 alpha → 透明 PNG。

**Path B 绿幕已删除**（2026-08-18 用户确认不必要）：`greenscreen_to_transparent.py` 与 `path1_clean_grab.py --transparent` 一并移除。

**依赖（用户负责安装）**：`pip install torch torchvision pillow transformers numpy` + RMBG-2.0 权重（首次运行自动下载，约 500MB；国内 `HF_ENDPOINT=https://hf-mirror.com` 加速）。脚本对缺失依赖会给出明确安装提示并 `exit(2)`，不静默失败。

**后端实现**（`scripts/bria_rmbg_cutout.py`）已覆盖以下「Prompt 无法解决、必须由代码保证」的点：

> ⚠️ **运行前置（易踩坑，2026-08-18 实测）**：
> 1. `briaai/RMBG-2.0` 是 **GATED 仓库**——首次运行前必须 `huggingface-cli login`（先在 https://huggingface.co/briaai/RMBG-2.0 点 Agree 接受许可）或设 `HF_TOKEN`，否则 `401 Unauthorized` 下不到权重。
> 2. numpy 二进制必须一致：若 `D:/anaconda/python.exe` 同时加载 anaconda 的 numpy1.x（绑 pandas/pyarrow/sklearn）与用户站的 numpy2.x（torch/transformers），会 `numpy.dtype size changed` 崩溃。修法：把 `scikit-learn pandas pyarrow` 也 `--user` 重装到用户站（同 numpy2 ABI）。验证命令见 `bria_rmbg_cutout.py` 顶部依赖段。
- `MODE_PRESETS`：pod_print/product/portrait 各自绑定 RMBG-2.0 + 最优 matting 参数（POD 锐边 / 商品柔边 / 人像发丝）。
- 质量自检 + 阈值：`_qc()` 用前景占比与边缘一致性打分，<0.6 判不合格。
- 重试 / 降级 / 兜底：最多 3 次，逐次加大锐度 + 中值滤波清理；全失败标记 `partial` 并带 warning。
- DPI 校正 + 尺寸归一化：`>2048` 边缩放防 OOM，输入 DPI 写回输出 PNG 保证打印物理尺寸正确。
- 结构化 metadata：返回 `status / quality / attempts / warning` 等，供 Agent 读懂结果状态。

**CLI（契约对齐 Agent Tool Definition）**：
```bash
python scripts/bria_rmbg_cutout.py --image-url clean.jpg --mode pod_print --out clean_cut.png
python scripts/bria_rmbg_cutout.py --image-url clean.jpg --mode product --keep-shadow true
python scripts/bria_rmbg_cutout.py --image-url clean.jpg --mode pod_print --matting-strength 1.0 --meta meta.json
```

**FastAPI 服务化**（`scripts/bria_rmbg_server.py`，v1.0 新增）：把同一套已验证内核包成 HTTP 服务，供 Agent 以 Function Calling 方式远程调用 `/remove_background`。

- 复用 `bria_rmbg_cutout.py` 的 `remove_background()` 内核（matting/QC/重试/DPI/metadata 全在内核里，server 不重写逻辑 → 不会重蹈「pipeline 误传 matting 参数 / matting_strength 未生效 / keep_shadow 未用」的坑）。
- 输入支持三种来源：`http(s)` URL / `data:image/...;base64,...` / 本地路径；输出返回 PNG `base64` + 结构化 `metadata`。
- 启动：`D:/anaconda/python.exe -m uvicorn bria_rmbg_server:app --host 127.0.0.1 --port 8123`（需 fastapi+uvicorn，已装 0.136.1 / 0.46.0）。
- 端点：`POST /remove_background`（body 同 Tool Definition：`image_url, mode, keep_shadow, matting_strength, out?`）、`GET /health`。
- 注意：`bria_rmbg_server.py` 与 `bria_rmbg_cutout.py` 必须**同目录**，server 启动时会 `import bria_rmbg_cutout` 并 `warmup()` 预加载模型到缓存。

### Agent 配置（复制到 Agent 系统提示词 / 工具列表）

以下两段为 Agent 侧配置，确保 Agent「正确调用工具」；抠图效果由上方后端代码保证。

**① System Prompt（复制到 Agent 的系统提示词中）**

```
你是一个专业的图像处理助手，擅长根据用户需求调用抠图工具并交付高质量结果。

抠图工具使用规范（必须严格遵守）
调用 remove_background 时，mode 只能从 [pod_print, product, portrait] 中选择，禁止自创或省略
当用户意图不明确（如只说"帮我抠个图"）时，必须先追问图片用途再调用工具
工具返回 warning 字段非空时，必须如实转达给用户，不得隐瞒、美化或忽略
对同一张图片最多重试 3 次，超出后明确建议用户人工处理
不向用户暴露模型名称、参数名、质检分数、metadata 等内部实现细节
阴影保留规则：用户提到"白底图""纯净背景""去阴影"时 keep_shadow=false；提到"场景图""自然展示""保留投影"时 keep_shadow=true；未提及时默认 false
交付结果时，用自然语言简要说明处理结果（如"已完成抠图，边缘已做抗锯齿处理"），不输出技术术语
```

**② Tool Definition（注册到 Agent 的工具列表中）**

```json
{
  "name": "remove_background",
  "description": "专业抠图工具。必须根据用户意图选择mode：pod_print用于POD印花、徽章、Logo、矢量图形、贴纸设计稿；product用于电商商品主体、产品展示图；portrait仅用于人像发丝级精细抠图。",
  "parameters": {
    "type": "object",
    "required": ["image_url", "mode"],
    "properties": {
      "image_url": {
        "type": "string",
        "description": "待处理图片的URL或路径"
      },
      "mode": {
        "type": "string",
        "enum": ["pod_print", "product", "portrait"],
        "description": "pod_print=POD印花/图形; product=商品主体; portrait=人像"
      },
      "keep_shadow": {
        "type": "boolean",
        "default": false,
        "description": "仅product模式有效。是否保留商品自然投影"
      },
      "matting_strength": {
        "type": "number",
        "minimum": 0.0,
        "maximum": 1.0,
        "default": 0.8,
        "description": "边缘柔化强度。pod_print建议0.9-1.0；product建议0.5-0.7"
      }
    }
  }
}
```

**回写铁律（用户 2026-08-18 拍板「从哪里取用就回写哪一行 + 合并」）**：
1. **按来源行回写**：每一张设计图的来源 record_id（即生成该图所依据的表 2 记录）必须随取用/生成环节被记录，回写时**原路写回该 record_id 的「设计方案图片」**，绝不串写到其他行。
2. **默认合并**：原图 + BRIA 抠图**追加**到该记录已有图片之后，不清空已有内容；仅显式 `--overwrite` 才覆盖。

> 注：表 2 是「一记录 = 一商品(SKU)，内含全平台字段」的扁平结构，**无「设计方向/平台」独立维度**；故回写目标行不能从表 2 自动反推，必须由取用侧显式提供 `{方向: record_id}` 映射（见 `writeback_designs.py --map`）。

**飞书回写约定（用户 2026-08-18 拍板）**：每条设计方案回写时，**原始干净图 + BRIA 抠图一并**写入「设计方案图片」字段。用 `writeback_designs.py` 批量（传入 `{方向: record_id}` 映射），或直接：
```bash
python scripts/write_image_attachment.py <record_id> <original.jpg> <cutout_bria.png>
```
回写后按飞书铁律用**列表接口**回验（非单条 GET，避免最终一致性陷阱）。**默认合并**（`writeback_designs.py` 不加 `--overwrite` 即追加），仅 `--overwrite` 才清空已有图片后写入。

## 图生图（img2img）轮次

在 **Images only** 模式下：
1. 点输入框旁的 **"Insert images, videos, or files"** 按钮（`button[aria-label*="Insert"]` 或含 `add_circle` 图标）→ 选参考图上传；
2. 用步骤 2 的 evaluate 法填 prompt；
3. 点 Run（步骤 3）；
4. 错误恢复同样用步骤 4 的「Rerun this turn」；
5. 下载 / 回写同文生图。

> 文件选择器若被 MCP 卡住，可改用 `mcp__browser-aistudio__browser_file_upload` 直接传路径（参数 `paths` 必须是数组）。

## CLI 工作流（批量生产模式）

```bash
# 1) 解析该记录设计方案 → prompt 列表
python scripts/parse_design.py <design_text_or_file> --json

# 2) 对每条 prompt 生成 MCP 命令序列（文生图）
python scripts/ai_studio_gen.py "<一条 prompt>" --image-only

# 3) 图生图（如需参考图）
python scripts/ai_studio_img2img.py <ref_img.png> "<一条 prompt>"

# 4) 生成+下载一条龙（输出完整命令序列，照 JSON 逐条调 MCP）
python scripts/ai_studio_workflow.py "<一条 prompt>" --image-only

# 5) 下载命令（点图→Download）
python scripts/ai_studio_download.py

# 6) 回写飞书
python scripts/write_image_attachment.py <record_id> ./<record_id>_*.png
```
> CLI 输出的是 **MCP 命令 JSON**，需由执行方逐条调用 `mcp__browser-aistudio__browser_*` 落地。黄金流程（上节）即这些 CLI 的真实产出，二者等价。

## 失败恢复速查

| 现象 | 处置 |
|---|---|
| "Upgrade to unlock more" 横幅 | **忽略**，免费模型照常跑 |
| "No API key selected" | **忽略**，不点它 |
| Run 后 "An internal error has occurred" | 点 **报错的那条 model turn 自身**里的 **「Rerun this turn」**（不是 user 内容框），用 `browser_evaluate` 派发 `mousedown+mouseup+click` 绕过 overlay，不刷新页面（已实测恢复）|
| 偶发 "permission denied" | 同 internal error：点 **报错 model turn 自身**的「Rerun this turn」，**绝不重复发送 prompt、绝不查登录态当借口** |
| 文本框填不进 / Run 不 enabled | 改用 evaluate `nativeInputValueSetter` 触发 input 事件（见步骤 2）|
| 导航超时 | 检查代理 127.0.0.1:7897 是否运行 |
| Run 后 "You've reached your rate limit / Too many requests" | **免费额度限流**：`path1_clean_grab.py` 检测到 `RATE_LIMITED` 会立即中止轮询与空耗重试并 `exit(10)`；批量 runner 命中即**熔断整批**（不再继续烧后续 prompt）。这是账户级时间窗限额，**等窗口重置后重试单条**，连点必败 |
| 下载后找不到文件 | 先查 MCP 沙箱 `.playwright-mcp/Generated-Image*`；若用 evaluate 点击 Download，再查 `C:\Users\<user>\Downloads\Generated Image*` |
| 飞书写后回读为空 | 附件字段整体替换，必须一次性传全部图片再 PUT |
| 飞书报 TOKEN FAIL | 检查 `references/config.json` 是否填入正确的 APP_ID/APP_SECRET |

## 实测记录

### 2026-08-11 10:29 验证通过（首测）
- 模型：Nano Banana 2 Lite（`gemini-3.1-flash-lite-image`），免费、无密钥
- 流程：navigate → Images only → evaluate 填 prompt → Run → 10:17 报 internal error → 点 **报错 model turn 自身**的 **Rerun this turn** → 10:29 出图
- 产物：`Generated Image August 11, 2026 - 10_29AM.png`，**1408×768，874KB**
- 结论：免费模型 + Rerun 恢复 = 稳定可用，闭环成立

### 2026-08-14 13:00 复测通过（MCP 驱动全链路，本次上锁依据）
- 环境：`browser-aistudio` MCP 连接器（**自启动** Chrome，复用 `aistudio-google-profile` 登录态，登录账号 `leiyuzhe007@gmail.com`）
- 流程：navigate（URL 带 `?model=gemini-3.1-flash-lite-image`）→ 清弹窗 → 切 **Images only** → evaluate 填英文 prompt（橙色虎斑猫+蓝围巾贴纸）→ 点 Run
- **首轮直接出图，未报 internal error，无需 Rerun**（比 08-11 更顺，确认该账号/该 profile 下 MCP 自动驱动不被 Google 服务端拦截）
- 产物：`Generated Image August 14, 2026 - 1_00PM.png`，**1408×768，1.35MB**（已落 `C:\Users\nicho\Downloads\` 并复制到工作区核对，真图为证）
- 下载方式实测：用 `browser_evaluate` 合成点击 Download → 文件落 **Chrome 默认 Downloads 目录**（非 MCP 沙箱），已在步骤 6/7 注明两种路径
- 未做项：飞书真实回写（需目标 record_id 授权），但脚本链路（upload_all→file_token→PUT 附件→回读）在 08-11 已验证；本次仅修正了硬编码飞书密钥（抽到 `references/config.json`，gitignored）
- 结论：生图→下载闭环在 MCP 驱动下稳定可用；推 GitHub 前已消除密钥泄露风险
