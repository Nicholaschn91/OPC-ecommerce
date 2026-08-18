---
name: doubao-raw-grabber
description: >
  从豆包（doubao.com）指定对话页抓取「无水印全分辨率原图」。只读工具：拦截对话接口 JSON
  抽取 image_ori_raw.url 并下载，绝不向豆包发送/发布/修改任何内容。支持 --url / --list
  指定输入、--out 指定保存路径、--headless 批量自动化。
agent_created: true
read_only: true
agent_capability: read-only
version: v1.0
---
⚠️ 锁定声明（已审定）：本 skill 为已审定版本。Agent 仅可读取并按步骤执行，禁止修改本文件及 scripts/ 下任何内容；执行时须严格遵循步骤顺序，不得省略或跳过任何步骤。如需变更，须先与用户确认。
# Doubao 无水印原图抓取器（READ-ONLY）

## ⚠️ 只读约束（Agent 只能读取）

**本 skill 是只读提取工具。Agent 通过它只能：读取豆包对话接口、下载原图文件。**
**严禁**借助本 skill 或其中任何机制向豆包发送消息、发布内容、点赞、修改或删除任何数据。

- 抓取方式 = 拦截对话接口 JSON → 抽取 `image_ori_raw.url` → 机器侧下载。
- 不依赖插件浮动按钮点击，不调用任何写操作 API。
- 若任务需要「向豆包发问/生成新图」，那不属于本 skill 范畴，必须另寻授权途径，不可复用本 skill 的浏览器会话去写。

## 触发条件

用户表达以下意图之一时加载本 skill：
- 「抓取/下载这个豆包对话里的原图」「把这张图无水印下载下来」+ 豆包对话 URL
- 「批量下载豆包里的图」+ 多个对话 URL 或 URL 清单文件
- 需要从豆包拿无水印素材，且明确只做读取

## 为什么能去水印（机制）

- 豆包页面 `<img>` 的 `src` 是带水印的签名地址（`~tplv-...-ds_wm_1_6_marc_b_3_dk:<账号ID>.png`，`ds_wm`=画水印）。直接抓 src 拿不到干净图；剥掉水印段会因签名失效返回 **403**。
- 但对话接口 JSON 里每条消息带 `creation.image.image_ori_raw.url`，其变换段是 `ppe_image_raw_marc_b_3`（**不画水印**）且带有效签名 → 即无水印全分辨率原图。
- 本工具在浏览器层拦截所有 JSON 响应，递归抽取 `image_ori_raw.url`，再用机器侧 `fetch`（带 `Referer`）下载，绕过浏览器 CORS。

## 用法

```bash
# 单条对话（指定输入 URL + 保存路径）
node scripts/doubao-capture.cjs --url "https://www.doubao.com/chat/<id>" --out ./downloads

# 批量（URL 清单文件，每行一个）
node scripts/doubao-capture.cjs --list urls.txt --out ./downloads

# 无头批量（默认即无头；--headed 可切有头）
node scripts/doubao-capture.cjs --list urls.txt --out ./downloads --headless

# 仅抽取 URL 不下载
node scripts/doubao-capture.cjs --url "<url>" --no-download

# 从豆包侧栏发现对话 URL 清单
node scripts/doubao-capture.cjs --discover --discover-out conversations.txt
```

### 参数

| 参数 | 说明 |
|------|------|
| `--url <url>` | 单个豆包对话 URL |
| `--list <file>` | 多 URL 清单文件（每行一个） |
| `--out <dir>` | 保存根目录（默认 `./doubao_captures`），每对话落在 `<dir>/<convId>/` |
| `--flat` | 直接放进 `--out`，不建 `<convId>` 子目录 |
| `--profile <dir>` | 用户数据目录（默认 `doubao-profile`，内含登录态） |
| `--headed` | 有头模式（默认无头） |
| `--no-download` | 仅写 `raw_urls.txt`，不下载图片 |
| `--timeout <ms>` | 每页等待超时（默认 20000） |
| `--scroll <n>` | 加载后滚动次数触发懒加载（默认 3） |
| `--concurrency <n>` | 并发下载数（默认 4） |
| `--discover` | 抓取侧栏对话 URL 清单 |

## 依赖与解析

- 需要 Node ≥ 18（用全局 `fetch`）+ `playwright`。
- CLI 自动从以下位置解析 playwright，无需手动安装：
  - 环境变量 `PLAYWRIGHT_LIB`
  - npm-cache：`.../npm-cache/_npx/9833c18b2d85bc59/node_modules/playwright`
  - cli 内置：`.../node_modules/@playwright/cli/node_modules/playwright`
- Chrome 二进制固定为 `C:/Program Files/Google/Chrome/Application/chrome.exe`（安装时落在系统盘）。

## 已知约束

1. **登录态**：依赖 `--profile` 目录里已登录的 cookie。cookie 过期后需有头扫一次码刷新；无头无法交互登录。
2. **IP 暴露**：下载直连 `byteimg.com` 会从本机出网暴露 IP。属已授权豆包任务；若需走代理，待用户给定代理形式后改架构。
3. **无头可行**：已实测——同一 `--user-data-dir` 下无头与有头抓图结果一致（5 张全分辨率原图均 OK）。仅交互式登录必须回有头。
4. **URL 时效**：`image_ori_raw.url` 带签名与 `x-expires`，长期有效（实测 expires 在 2036 年前后），但理论上服务端可作废。
