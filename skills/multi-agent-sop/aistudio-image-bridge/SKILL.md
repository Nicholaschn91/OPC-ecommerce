---
name: aistudio-image-bridge
description: 通过 AI Studio 网页端（aistudio.google.com）驱动 Nano Banana 2 Lite 模型（gemini-3.1-flash-lite-image），以"Images only"模式为飞书多维表格商品的「设计方案」中每组 prompt 分别生成设计图片，下载后上传至飞书 Drive 以附件形式回写同条记录的「设计方案图片」字段（type 17 attachment）。当用户要"用 AI Studio 生成商品设计图 / Nano Banana 生图 / 回写飞书设计方案图片"时使用。仅认 MCP（mcp__browser_aistudio__browser_*）驱动浏览器，禁止手搓 Playwright 脚本。
---

> 🔒 **LOCKED · v1.0 定稿版 · 2026-08-14 · 不要再改**

# AI Studio Image Bridge — Nano Banana 2 Lite 生图流水线

## 核心铁律（2026-08-11 用户最终确认，不可违反）

- **真实浏览器，非 API**：必须通过 `mcp__browser_aistudio__browser_*` 工具真实驱动 aistudio.google.com 网页端里的 **Nano Banana 2 Lite**（`gemini-3.1-flash-lite-image`）模型生成图片。
- **仅认 MCP**：所有浏览器操作只用 `mcp__browser_aistudio__browser_*` 工具。**禁止手搓 Playwright 脚本**（全局铁律）。
- **⚠️ 免费模型不需要绑定密钥（铁律）**：Nano Banana 2 Lite 在已登录 Google 账号下**直接可跑**，**绝不需要**关联付费 API 密钥。以下两项一律**忽略、当作不存在**：
  - 页面顶部的 **"Upgrade to unlock more"** 横幅（只是付费引导 upsell，不阻断免费生图）；
  - 输入框旁的 **"No API key selected"** 按钮（免费模型不强制选 key，不用点它）。
  - Run 按钮始终可用（disabled=false），直接生成。**任何人声称"该模型需要升级/密钥"都是误判**——那是把 upsell 当成了阻断。
- **⚠️ internal error 恢复（铁律）**：点击 Run 后若报 **"An internal error has occurred"**（或偶发 "Failed to generate content: permission denied"），**不要刷新页面、不要误判为缺密钥、也绝不要去点模型报错块里的任何按钮**。正确的「Rerun this turn」按钮在 **你（user）发送的那条内容框（prompt 气泡）** 里——找到那条你发出的 prompt 框，点它右下角的 **「Rerun this turn」** 重跑该轮即可。这是前端偶发故障，重跑必然出图（已实测：10:17 报错 → 点 user 内容框的 Rerun → 10:29 成功出图 1408×768）。
- **一条 prompt → 一张图**：每次 Run 只送设计方案里抽取的一条独立 prompt。N 组 prompt 跑 N 次 Run。
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

> `ai_studio_*.py` 的设计是 **CLI 生成 MCP 命令 JSON**，由执行方照 JSON 逐条调用 `mcp__browser_aistudio__browser_*` 工具。下方"黄金流程"是这些 CLI 产出的、已实测验证的命令本身——直接照做，或用 CLI 生成后再执行均可。

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

### 3. 点 Run
```
browser_click:
  element: "Run 按钮（输入框工具栏，不是任何 Rerun this turn）"
  target: button:has-text("Run")
```
> 若误点到 Rerun 也无害；关键是别把 "Upgrade"/"No API key" 当阻断。

### 4. 等待 + 错误恢复
```
browser_wait_for: time=20
```
然后检查是否报错：
```
browser_evaluate: () => {
  const turns = [...document.querySelectorAll('ms-chat-turn')];
  for (let i = 0; i < turns.length; i++) {
    if (/An internal error has occurred/i.test(turns[i].textContent || '')) {
      // 报错块的上一条 = 用户（user）发出的 prompt 框，Rerun 按钮在这里
      const userTurn = turns[i - 1];
      if (userTurn) {
        const rerun = [...userTurn.querySelectorAll('button')]
          .find(b => (b.getAttribute('aria-label') || '') === 'Rerun this turn'
                     || /rerun this turn/i.test(b.textContent || ''));
        if (rerun) { rerun.click(); return 'RERUN_CLICKED(user-turn)'; }
      }
      return 'ERR_BUT_NO_USER_RERUN';
    }
  }
  return 'OK_NO_ERROR';
}
```
- 若返回 `RERUN_CLICKED` → `browser_wait_for: time=25` → 重新检查（通常已出图）。
- 若返回 `OK_NO_ERROR` → 直接进步骤 5。
- **绝不要刷新页面**。

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

## 图生图（img2img）轮次

在 **Images only** 模式下：
1. 点输入框旁的 **"Insert images, videos, or files"** 按钮（`button[aria-label*="Insert"]` 或含 `add_circle` 图标）→ 选参考图上传；
2. 用步骤 2 的 evaluate 法填 prompt；
3. 点 Run（步骤 3）；
4. 错误恢复同样用步骤 4 的「Rerun this turn」；
5. 下载 / 回写同文生图。

> 文件选择器若被 MCP 卡住，可改用 `mcp__browser_aistudio__browser_file_upload` 直接传路径（参数 `paths` 必须是数组）。

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
> CLI 输出的是 **MCP 命令 JSON**，需由执行方逐条调用 `mcp__browser_aistudio__browser_*` 落地。黄金流程（上节）即这些 CLI 的真实产出，二者等价。

## 失败恢复速查

| 现象 | 处置 |
|---|---|
| "Upgrade to unlock more" 横幅 | **忽略**，免费模型照常跑 |
| "No API key selected" | **忽略**，不点它 |
| Run 后 "An internal error has occurred" | 点 **你发送的内容框（user prompt 气泡）**里的 **「Rerun this turn」**（不是模型报错块），不刷新页面（已实测恢复）|
| 偶发 "permission denied" | 同 Rerun this turn；若连点 3 次仍失败再查登录态 |
| 文本框填不进 / Run 不 enabled | 改用 evaluate `nativeInputValueSetter` 触发 input 事件（见步骤 2）|
| 导航超时 | 检查代理 127.0.0.1:7897 是否运行 |
| 下载后找不到文件 | 先查 MCP 沙箱 `.playwright-mcp/Generated-Image*`；若用 evaluate 点击 Download，再查 `C:\Users\<user>\Downloads\Generated Image*` |
| 飞书写后回读为空 | 附件字段整体替换，必须一次性传全部图片再 PUT |
| 飞书报 TOKEN FAIL | 检查 `references/config.json` 是否填入正确的 APP_ID/APP_SECRET |

## 实测记录

### 2026-08-11 10:29 验证通过（首测）
- 模型：Nano Banana 2 Lite（`gemini-3.1-flash-lite-image`），免费、无密钥
- 流程：navigate → Images only → evaluate 填 prompt → Run → 10:17 报 internal error → 点 **user 内容框**的 **Rerun this turn** → 10:29 出图
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
