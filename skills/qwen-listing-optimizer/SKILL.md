---
name: qwen-listing-optimizer
description: "[阶段1·文案+视觉方案·千问Qwen3.8-Max·线一/线二] 真实驱动千问网页端 Qwen3.8-Max 执行 Listing 终版优化（标题/Description/Tags/承诺审批区 + 视觉 Prompt×7）。线一(新上架全量)默认开视觉；线二(在售迭代)默认小改、视觉需用户主动开。触发词：跑终版/优化 listing/批量优化/生成标题描述视觉/新 listing 上架/在售 listing 优化。每条 listing 独立新建对话窗口。需中国大陆出口 IP。终版不接关键词词库（词库由 listing-v1-seo-builder 初版消费）。"
version: v1.0
---

> ⚠️ **版本声明（2026-08-10 MCP 化修订）**：本 skill 原执行层为**手搓 Playwright**（`scripts/optimize-one.js` 等自起 Chromium）。用户于 2026-08-08 立「浏览器控制铁律：只认 MCP、禁手搓 Playwright」，故已**废除手搓脚本**（归档于 `scripts/_deprecated_handrolled_playwright/`），执行层全面改为 **`playwright-qwen` MCP 驱动**。端到端已于 2026-08-10 在国内 IP 环境实测跑通（详见「验证状态」）。

# 千问 Listing 优化器（playwright-qwen MCP 真实执行）

## 核心约定（铁律）
- **真实执行，非模拟**：必须真正驱动千问网页端里的 Qwen3.8-Max 模型本人生成内容，**绝不由本机套用提示词替模型生成**（用户明确不认可"模拟"方式）。
- **每条独立窗口（零污染）**：每优化一个 listing 都新建一个对话窗口，跑完即结束，绝不在同一窗口连续跑多个。无关商品类目、无关全量/文案模式。
- **前置判断**：全量优化才输出 Step4 视觉 Prompt×7；非全量（仅标题 / 仅 Description / 局部调整）跳过视觉。
- **浏览器只认 MCP**：所有网页端操作（导航/点击/填表/截图/抓取/注入）**唯一合法手段是 `playwright-qwen` MCP**，严禁任何 `*.js` 自起 Chromium（见 `scripts/_deprecated_handrolled_playwright/README.md`）。

## 三维路由定位（本 skill）
> 全链路由「线别 × 模式 × 工具」三个维度决定调用哪个 skill。本 skill 只负责**阶段 1**。

- **阶段**：阶段 1 · 文案 + 视觉方案设计（输出 7 段 PROMPT/NEGATIVE 文字，**不直接出图**）
- **线别**：线一（新 listing 上架，默认全量+开视觉）/ 线二（在售迭代，默认小改、视觉需用户主动开）
- **工具**：千问 Qwen3.8-Max（网页端 `qianwen.com`）
- **上游**：可选 `listing-v1-seo-builder`（初版，消费关键词词库产出 SEO 草稿）；终版**不接词库**
- **下游**：阶段 2 图生图 → `doubao-image-mcp`（首选）/ `qwen-image-mcp`（备选），消费本 skill 的 7 段 PROMPT + 参考图形成「约束对」
- **触发词**：用千问跑终版 / 优化 listing / 批量优化 / 生成标题描述视觉 / 新 listing 上架 / 在售 listing 优化
- **不接词库**：终版不取关键词词库，词库仅在 `listing-v1-seo-builder`（初版）消费

| 维度 | 本 skill 取值 |
|---|---|
| 阶段 | 1（视觉方案设计） |
| 线别 | 线一 / 线二 |
| 模式 | 全量（开视觉）/ 仅文案（关视觉，跳过 Step4）/ 局部 |
| 工具 | 千问 Qwen3.8-Max |

## 两条线框架（终版 / 优化，2026-08-04 划定）
> 收到优化任务**先确权属哪条线**，再决定能否接词库 + 改动幅度上限。未声明线别须向用户确认，不得默认按线一大改。

- **线一 · 上架终版（新 listing 首次上架）**
  - 默认**全量 + 开视觉**：标题/Description/Tag/视觉可大改；视觉基于「基材 spec（00 基材提取产出，含供应商有限垫图角度+alt）」做最优选型与写实描述（终版消费 spec，不再自做 alt 提取）。
  - **终版不接词库**（词库已在初版消费，见 `listing-v1-seo-builder` 技能）。
  - 可声明「非全量 / 仅标题 / 仅 Description」跳过视觉（Step4）。
- **线二 · 已上架优化（在售迭代）**
  - 默认**关视觉、仅小改**：修语病、统一材质命名、补 1–2 个高意图词；不重组标题、不重写描述、不引词库长尾。
  - **视觉开关（默认关，用户主动开）**：用户声明"推重新设计视觉"→ 临时切到「全量大改 + 实拍自由垫图」。触发必须用户主动声明，Agent 不得自行判断开视觉。**终版仍不接词库**。

## 固化店铺惯例（Shop Fixed Conventions，2026-08-05 固化）
> 以下为本店 listing **全局固化惯例**，默认自动套用每条 listing，**无需用户重复声明**；写入提示词文件【店铺固化惯例】章节，注入千问时模型自动遵循。
- **可选礼盒**：礼盒作为**可选增值服务**——Description 写"礼盒可选加购/下单加购"，视觉默认不含礼盒，仅当 YAML 明确允许可含一张礼盒变体图。
- **免费手写贺卡（可选）**：Description 提供"免费手写贺卡，下单备注即可"。
- **时效双层级**：整体履约 "2–4 weeks"；纯物流 "8–15 days"。
- **定制商品售后**：非质量问题不退换，请于下单前仔细核对定制信息。
- **Description 视觉化**：断行 + emoji 增强情绪与视觉效果，避免大段纯文字。

## 环境要求（MCP 化）
- **`playwright-qwen` MCP 已连接**（连接器管理处启用，复用 `--user-data-dir = .../qwen-listing-optimizer/cdp-profile-h` 登录态）。
- 登录态：profile 内已登录千问账号（实测 `Qwen1122`）。cookie 过期则经 MCP 浏览器手动登录一次，会话持久化于 profile。
- **中国大陆出口 IP**：qianwen.com 在非大陆地区返回"Qwen 在你所在的地区不可用"，须在国内网络下运行。此限制与"真实店铺一店一IP 代理机制"无关。
- 正确域名：**`qianwen.com`**（无 `www`；`www.qianwen.com` DNS 失败）；**不是 `qwen.com`**（qwen.com 是 Qwen 模型官网，完全不同）。

## CLI 用法（纯文件处理，不涉及浏览器）
1. **组装注入载荷** → 产出 `browser_run_code_unsafe` 片段：
   ```
   python scripts/build-inject.py \
     --prompt qwen3.8-max-listing-optimizer-prompt.md \
     --data <原始Description+YAML视觉包合并文本.txt> \
     [--spec <00基材提取产物.json>] \
     [--line "线一全量"] [--mode full|copy] \
     --out <_inject_snippet.js>
   ```
   - 把「提示词正文（从【角色设定】起）+ 启动指令(线别/模式) + 原始数据 + 基材 spec」拼成完整文本，base64 内联进 `.js` 片段。
   - 解决两难：① 载荷 >13K 字符无法塞进对话上下文；② `browser_run_code_unsafe` 的 Node 侧**无 fs/require/fetch**，不能读文件/写文件/发请求。base64 内联使 agent 读文件全文→作为 `code` 参数传入即可。
2. **清洗抓取结果** → 可交付 md：
   ```
   python scripts/clean-capture.py --in <原始捕获.md> --out <clean.md>
   ```
   - 去深度思考块 + 底部输入栏 chrome，去掉孤立工具栏行，从正式输出标题起、到输入栏前止。
3. **结构化提取**（可选，消费 clean/out md + 源数据 → `data.csv`）：
   ```
   node scripts/extract-clean.js --out <out.md> --source <源数据.txt> --dir <素材目录> [--csv <data.csv>]
   ```
   - 纯文件处理（Node，无浏览器），保留 alt 与 images 1:1。

## 执行流程（playwright-qwen MCP 驱动，逐步）
> 以下 `browser_*` 均为 `playwright-qwen` MCP 工具。每个 listing 都从**新建对话**开始。

1. **导航**：`browser_navigate` → `https://qianwen.com/chat`（无 www）。
2. **验证会话**：`browser_snapshot` 确认①已登录（账号如 `Qwen1122`）②当前模型 = **Qwen3.8-Max**（若不是，点模型选择器切到 Qwen3.8-Max）。
3. **组装载荷**：运行 `build-inject.py`（见上）产出 `_inject_snippet.js`。
4. **注入输入框**（关键）：
   - 读 `_inject_snippet.js` 全文，作为 `browser_run_code_unsafe` 的 `code` 参数执行。
   - 片段在浏览器内 `atob` 还原 → `page.keyboard.insertText(txt)` 注入**输入框**。
   - ⚠️ 千问输入框是 **`contenteditable` DIV（不是 `<textarea>`）**；`insertText` 走 CDP 级粘贴，能触发 React 受控更新使「发送」按钮 enabled。`setter.call`/`dispatchEvent`/`locator.fill` 均无效或超时。
5. **发送**：`browser_click` → `button[aria-label="发送消息"]`（注入后按钮解除 disabled 即可点）。
6. **等待生成**：轮询 `browser_snapshot`/`browser_run_code_unsafe`，直到「停止回答」按钮消失（无头约 30–90s）。
7. **抓取结果**（无 fs/fetch，用 Blob 下载）：
   ```
   browser_run_code_unsafe:
   async (page) => {
     const res = await page.evaluate(() => {
       const h = [...document.querySelectorAll('h1,h2,h3,h4,h5,h6')]
                 .find(e => e.textContent.includes('Etsy Listing 终版优化'));
       if (!h) return { error: 'heading not found' };
       const cands = [];
       let cur = h.parentElement;
       while (cur) { const t = cur.innerText || '';
         if (t.includes('Etsy Listing 终版优化') && t.includes('BASE_MATERIAL')) cands.push(cur);
         cur = cur.parentElement; }
       if (!cands.length) return { error: 'no BASE_MATERIAL container' };
       const text = cands[cands.length-1].innerText;
       const a = document.createElement('a');
       a.href = URL.createObjectURL(new Blob([text], {type:'text/markdown'}));
       a.download = 'out.md'; a.click();
       return { len: text.length };
     });
     if (res.error) return JSON.stringify(res);
     const dl = await page.waitForEvent('download', { timeout: 15000 });
     return JSON.stringify({ len: res.len, path: await dl.path() });
   }
   ```
   - 落盘路径为 MCP 运行时目录，用 Bash `cp` 复制到工作区（如 `Desktop/images/`）。
8. **清洗**：`python scripts/clean-capture.py --in <原始捕获.md> --out <clean.md>`。
9. **结构化（可选）**：`node scripts/extract-clean.js ...` 产 `data.csv`。
10. **证据链保留**：`out.md`（原始捕获）**永不覆盖删除**；`clean.md` 由 `out.md` 生成。

## 关键 gotchas（已实测）
- **输入框是 contenteditable DIV，非 textarea**：`document.querySelector('textarea')` 查不到；注入用 `page.keyboard.insertText`。
- **`browser_run_code_unsafe` 的 Node 侧无 fs/require/fetch**：片段内不能写文件、不能读文件、不能 `fetch` 本地服务（且 qianwen.com 是 HTTPS，会拦截向 HTTP 子资源的混合内容请求）。故大文本**只能 base64 内联进 code 参数**，抓取**只能 Blob 下载 + `download` 事件捕获**。
- **DOM 访问必须进 `page.evaluate`**：`document` 不在 Node 侧作用域。
- **大载荷绕过上下文**：>13K 字符用 `build-inject.py` 产 base64 内联片段，agent 读文件全文作 `code` 参数（已验证 27K+ base64 可用）。
- **每条 listing 独立新建对话窗口**：避免历史消息污染下一条。
- **域名**：`qianwen.com`（无 www）；非 `qwen.com`。

## 已废除（手搓 Playwright）
`scripts/optimize-one.js` / `optimize-batch.js` / `sync-cookies.py` 已移至 `scripts/_deprecated_handrolled_playwright/`，因违反「浏览器控制铁律」禁止使用。现行执行层全部走 MCP（见上）。

## 词库取用标准（已前置到初版）
终版**不接入关键词词库**（词库仅在初版 `listing-v1-seo-builder` 消费）。终版只做 GEO 语义优化 / 美式本土化转译 / 视觉方案 / 承诺审批，**不回原始词库重取词**；发现真实 SEO 缺口则回抛初版重跑。

## 验证状态
- ✅ **2026-08-10 端到端实测跑通**（国内 IP）：qianwen.com/chat 登录态有效 → 切 Qwen3.8-Max → `build-inject.py` 注入 13,956 字符载荷 → 发送 → 真实生成（深度思考 + Step1→5 + 视觉 Prompt×7 + BASE_MATERIAL 块）→ Blob 抓取 → `clean-capture.py` 清洗，产出完整可交付 md。
- ✅ 地域限制已解除（国内 IP）；contenteditable 注入、Blob 抓取两条关键技术点已验证。
- ✅ `build-inject.py` / `clean-capture.py` 已用真实 artifacts 跑通验证。
