---
name: qianwen-image-downloader
description: >

> 🔒 **LOCKED · v1.0 定稿版 · 2026-08-14 · 不要再改** · 傻瓜式说明书
  从通义千问 / 千问（qianwen.com、tongyi.aliyun.com）对话页抓取 AI 生成图的「无水印原图」并批量下载到本地。
  触发场景：用户想下载千问/通义生成的干净原图、问"千问图片能不能去水印下载"、要把 AI 生图批量存到本地、
  或需要自动化地在千问里生成图并导出。提供一套分步 CLI（open/generate/list/download/close/run），
  起有头或无头浏览器、注入图片 URL 嗅探、自动过滤水印图、落地原图。
  注意：仅针对阿里千问/通义，不跨站；本机直连千问不受 IP 铁律限制（IP 铁律只针对 Etsy）。
version: v1.0
---
⚠️ 锁定声明（已审定）：本 skill 为已审定版本。Agent 仅可读取并按步骤执行，禁止修改本文件及 scripts/ 下任何内容；执行时须严格遵循步骤顺序，不得省略或跳过任何步骤。如需变更，须先与用户确认。

⚠️ **已废弃（2026-08-08）**：本技能走 playwright-core 脚本路线，违反「浏览器控制铁律：只认 MCP、禁止手搓 Playwright」。其全部能力——无水印原图抓取、图生图、整页 list 收割——已由 `qwen-image-mcp`（MCP 路线）完整覆盖。本文件仅保留作审定参考，**请勿再运行其 scripts/ 下脚本**；如需千问出图/下载，改用 `qwen-image-mcp`。
# 千问/通义 无水印原图抓取

## 背景（实测结论，确定而非推测）

千问在生成图片时，**接口同时返回两类地址**：
- **无水印原图**（约 458/466 实测）：来自
  - `gw.alicdn.com/...-0-tps-1024-1024.jpg`（阿里图床原图，带尺寸、无处理参数）
  - `yes-file.uc.cn/file/...png`（UC 网盘原图，无扩展名、无水印参数）
- **带水印展示图**（约 8/466 实测）：来自
  - `quark-aistudio-cdn.quark.cn/...?auth_key=...&x-oss-process=image/format,webp/resize,s_800`

所以**真能下载到无水印原图**，不是只换显示。嗅探脚本专抓前者、自动过滤后者（按 URL 是否含 `watermark / wm / thumb / x-oss-process / compress` 等子串判定）。

## 依赖安装（首次使用）

CLI 依赖 `playwright-core`，且需要一份 Chromium 二进制（本机已在 `~/.agent-browser/browsers/` 下有一份，脚本会自动探测）。

```bash
cd <skill目录>/scripts
npm install playwright-core
```

若没有 Chromium，用 agent-browser 或 playwright 自带的 chromium 也行，路径通过 `QW_CHROME` 指定。

## 快速开始（两种模式）

### 模式 A：有头 + 手动登录（推荐首次）
```bash
# 1. 起浏览器窗口（弹桌面），手动登录千问、手动生成图
node qw-img.js open

# 2. 另开终端，列出抓到的无水印原图
node qw-img.js list

# 3. 下载全部到 ./qianwen-dl
node qw-img.js download

# 4. 关浏览器
node qw-img.js close
```

### 模式 B：一键 run（依赖已登录的持久 profile）
首次用模式 A 登录一次后，登录态缓存在 `./cdp-profile`，之后可全自动：

**文生图：**
```bash
node qw-img.js run --prompt "画一只赛博朋克风格的猫" --out ./my-imgs
```

**图生图（指定底图）：**
```bash
node qw-img.js run --prompt "把这张图改成赛博朋克风格" --img ./base.png --out ./my-imgs
```

该命令会：open（无头，复用已登录 profile）→ 进入 AI生图 模式 → 上传参考图（如有 `--img`）→ 发送 prompt → 等图生成 → 列出 → 下载 → 关闭。

## 命令详解

| 命令 | 作用 | 关键选项 |
|---|---|---|
| `open` | 起浏览器 + 注入嗅探 + 打开千问页 | `--headless`、`--timeout N`（有头保持分钟，默认20） |
| `generate "<文本>"` | 在输入框发送生图 prompt（需浏览器在运行） | `--img PATH`（图生图，指定底图路径） |
| `list` | 读取并列出无水印原图 URL | `--json [f]` 写出 JSON、`--limit N` |
| `download` | 下载全部无水印原图到本地 | `--out DIR`（默认 `./qianwen-dl`） |
| `close` | 关闭浏览器 | — |
| `run --prompt "..."` | 一键全流程 | `--headless`、`--out`、`--json`、`--no-download`、**`--img PATH`（图生图）** |

## 环境变量

| 变量 | 默认 | 说明 |
|---|---|---|
| `QW_CHROME` | 自动探测 `~/.agent-browser/browsers/chrome-*` | Chrome 可执行路径 |
| `QW_PROXY` | `http://127.0.0.1:7897` | 代理地址（与浏览器一致）；设 `QW_NO_PROXY` 关闭（download 用 curl 也会走该代理） |
| `QW_URL` | `https://www.qianwen.com/chat` | 目标页（千问对话页会重定向到 qianwen.com/chat） |
| `QW_PROFILE` | `./cdp-profile` | 登录态缓存目录，首次手动登录后自动复用 |

## 原理

- `qianwen-sniff.js` 注入页面：劫持 `fetch`/`XHR`（扫描 JSON 响应里的图片 URL）+ 周期扫描 DOM `<img>`，所有图片 URL 存入 `window.__qw`，标注 `watermark` 与 `img`。
- `qw-img.js` 用 Playwright 起浏览器（持久 profile）并通过 CDP `9222` 端口连接已运行实例，读取 `window.__qw` 做分类与下载。
- 下载用 `curl`（自动走 `QW_PROXY`），规避跨域/鉴权问题；图片 CDN 一般直连可用，若失败设 `HTTPS_PROXY` 或保持 `QW_PROXY` 默认即可。

## 注意事项

1. **不能跨站**：这是千问专属工具。豆包（doubao）、Midjourney、DALL·E 等站结构不同，需另行适配。
2. **千问仅对「对话直接生成的图」返回无水印原图**；二次编辑（局部重绘/变清晰）可能不含原图字段，下载下来的仍可能有水印。
3. **图生图流程**：`--img` 会自动进入 AI生图 模式 → 点「参考图」→ 通过 file chooser / input 上传底图 → 发 prompt。若千问改版「参考图」按钮选择器失效，需在 `uploadReferenceImage` 调整。
4. **generate 的输入框选择器**（`textarea` / `contenteditable` / `[role="textbox"]`）若千问改版失效，需在 `doGenerate` 里调整选择器。
5. 浏览器窗口走本机本地代理（默认 `127.0.0.1:7897`），不触达 Etsy，不违反 IP 铁律。
6. `open` 有头模式会保持窗口到 `--timeout` 或手动 `close`；CDP 端口固定 `9222`，同一时间只跑一个实例。
7. **登录态过期**：profile 中的 Cookies 一般可用数天；过期后 `run --headless` 会撞登录墙，需重新跑一次 `open`（有头）手动扫码登录。
