---
name: qwen-listing-optimizer
description: "[阶段1·文案+视觉方案·千问Qwen3.8-Max·线一/线二] 真实驱动千问网页端 Qwen3.8-Max 执行 Listing 终版优化（标题/Description/Tags/承诺审批区 + 视觉 Prompt×7）。线一(新上架全量)默认开视觉；线二(在售迭代)默认小改、视觉需用户主动开。触发词：跑终版/优化 listing/批量优化/生成标题描述视觉/新 listing 上架/在售 listing 优化。每条 listing 独立新建对话窗口。需中国大陆出口 IP。终版不接关键词词库（词库由 listing-v1-seo-builder 初版消费）。"
---

> 🔒 **LOCKED · v1.0 定稿版 · 2026-08-14** · 原为弱模型测试时的防改坏保护壳；**2026-08-16 深夜用户解除锁定（深度优化阶段，用真能力），现已可编辑**。本次仅追加「防蚕食账本贯通」（build-inject.py 接初版账本 + verify-ledger.py 校验），不破坏原有实测流程。

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
- **上游**：可选 `listing-v1-seo-builder`（初版，消费关键词词库产出 SEO 草稿）；终版**不接关键词词库**（词库仅在初版消费），但**贯通防蚕食账本**（见下「防蚕食账本贯通」）
- **下游**：阶段 2 图生图 → `doubao-image-mcp`（首选）/ `qwen-image-mcp`（备选），消费本 skill 的 7 段 PROMPT + 参考图形成「约束对」
- **触发词**：用千问跑终版 / 优化 listing / 批量优化 / 生成标题描述视觉 / 新 listing 上架 / 在售 listing 优化
- **不接关键词词库**：终版不取关键词词库，词库仅在 `listing-v1-seo-builder`（初版）消费；但终版**贯通防蚕食账本**（共享初版账本，生成前注入唯一主词约束，写飞书前校验）

## 人工交接区（human-in-the-loop 手动路径落点）
> 半自动流程里，终版优化有一环是「人拿提示词去 Qwen3.8-Max **网页端**跑、再把输出贴回」（区别于 `build-inject.py` 经 `playwright-qwen` MCP 的自动注入路径）。这一步的产物**必须有固定落点**，不能每次临时找文件、手动拼装。

**固定落点 = `_e2e_out/<spu>/`**，由 `scripts/assemble_handoff.py` 一键生成「开箱即用」交接包（在 workspace 根目录执行）：

```bash
python scripts/assemble_handoff.py --spu S3-04
# 可选: --bundle <listing_bundle.json>  --out-dir <dir>  --line 线一全量  --mode full|copy
```

生成内容：
| 文件 | 用途 |
|---|---|
| `prompt_to_run.txt` | 完整提示词纯文本 —— **全选复制 → 粘 Qwen3.8-Max 网页端 → 发送** |
| `HANDOFF.md` | 人工步骤卡（复制 → 发送 → 贴回 clean.md → 告 agent 跑校验） |
| `clean.md` | 占位，把 Qwen 输出整段贴到首行注释之下，保存 |
| `listing_bundle.json` | 拷贝 Stage1 产物，供参考 |
| `<spu>_etsy_v1.md` | 拷贝初版草稿，供参考 |

人工跑完贴回 `clean.md` 后，agent 用 `scripts/verify-ledger.py` 跑闸门（防蚕食唯一性 + 三级熔断 + 字段回读 + 软层 review），无 `MELTDOWN`/`CRITICAL_STOP` 再进 Stage 4 写飞书（逐条授权）。

> 自动路径（`playwright-qwen` MCP 注入）不走本目录，由 `build-inject.py` 产出 `.js` 片段；两条路径**共用同一套装配顺序 + 防蚕食账本约束 + 软层自检清单**，仅落点不同。

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
  - **终版不接关键词词库**（词库已在初版消费，见 `listing-v1-seo-builder` 技能）；但**贯通防蚕食账本**（初版已为本 SPU 分配唯一主词，终版须沿用，见下「防蚕食账本贯通」）。
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
    [--spu <SPU>] [--category <类目>] [--ledger <账本路径>] \
    --out <_inject_snippet.js>
  # --spu 触发「防蚕食账本贯通」：向账本查询本商品已分配唯一主词 + 同类 sibling 已占词，
  # 生成「【防蚕蚀约束】」块注入提示词（详见下节）。
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
2. **验证并切换模型（关键·必做）**：`browser_snapshot` 确认①已登录（账号如 `Qwen1122`）②当前模型 = **Qwen3.8-Max**。
   - ⚠️ **新建对话后模型必重置回 `Qwen3.7-千问`**：每次点「新建对话」都会掉回旧模型，**每个 listing 新建窗口后必须重切 Qwen3.8-Max**（2026-08-14 实测踩坑：漏切会跑去跑成 Qwen3.7）。
   - **切换器是 `div/span` 文本节点**，`page.evaluate(el=>el.click())` / `dispatchEvent` 均不触发 React 下拉（事件委托拦截原生点击）。**必须用 Playwright locator 真实鼠标事件**：`page.getByText('Qwen3.7-千问',{exact:true}).click()` → 下拉展开 → 点 `Qwen3.8-Max` 才切得动。
3. **组装载荷**：运行 `build-inject.py`（见上）产出 `_inject_snippet.js`。
4. **注入输入框**（关键）：
   - 读 `_inject_snippet.js` 全文，作为 `browser_run_code_unsafe` 的 `code` 参数执行。
   - 片段在浏览器内 `atob` 还原 → `page.keyboard.insertText(txt)` 注入**输入框**。
   - ⚠️ 千问**对话页**输入框是 **`contenteditable` DIV（不是 `<textarea>`）**；`insertText` 走 CDP 级粘贴，能触发 React 受控更新使「发送」按钮 enabled。`setter.call`/`dispatchEvent`/`locator.fill` 均无效或超时。
   - 📌 **页面差异（勿跨页混用）**：千问**生图页**（见 `qwen-image-mcp`，2026-08-13 已验证）在 `contenteditable` 上用 `locator.fill` + 1500ms React sync 有效，与本 skill 对话页结论相反——两个页面的 React 实现不同，本 skill 对话页仍按实测用 `insertText`，不要改成 `fill`。
5. **发送**：`browser_click` → `button[aria-label="发送消息"]`（注入后按钮解除 disabled 即可点）。
6. **等待生成**：轮询 `browser_snapshot`/`browser_run_code_unsafe`，直到「停止回答」按钮消失（无头约 30–90s）。
7. **抓取结果**（无 fs/require/fetch，三种方式按可靠性排序）：
   - **方式 A（首选·最稳）：`page.evaluate` 取 innerText 直接作为 run_code 返回值**。MCP 把文本作为工具结果返回（实测 16K+ 字符稳定），agent 再落盘（剪贴板→PowerShell `Set-Content` 或 Write 工具）。不依赖 Downloads，无落盘失败风险。
     ```js
     async (page) => {
       const text = await page.evaluate(() => {
         let el = document.querySelector('.last-message-item .message-select-wrapper-answer');
         if (!el) el = [...document.querySelectorAll('[class*="message-select-wrapper-answer"]')]
                       .find(e => e.innerText.includes('BASE_MATERIAL'));
         return el ? el.innerText : null;
       });
       return { ok: !!text, len: text ? text.length : 0, text: text || '' };
     }
     ```
   - **方式 B（备用·落 Chrome Downloads）**：Blob 下载 + `a.click()`，文件落 **Chrome 默认 Downloads 目录**（非 MCP 沙箱）。⚠️ 实测**仅首次下载必落盘，连续第二次起 Chrome 会吞掉下载**（疑似下载拦截/去重），故不作为首选；若用，须先确认落盘再 `cp`。文件名带唯一后缀避免重名。
   - **方式 C（剪贴板，需先聚焦）**：`page.evaluate` 内 `navigator.clipboard.writeText(text)`（须先 `window.focus()` + `document.body.focus()`，否则报 "Document is not focused"），再用 PowerShell `Get-Clipboard -Raw | Set-Content -Encoding UTF8` 落盘。已实测可用。
   - ⚠️ **选择器铁律（2026-08-14 实测修正）**：**不要靠 heading 找 "Etsy Listing 终版优化"**——本 skill 的模型输出并不含该标题（直接以「深度思考已完成」+ 规划独白开头，结构化段用 "Step 1 / Step 2 / ..."），旧 heading 选择器会漏抓。正确命中 = `.last-message-item .message-select-wrapper-answer`（fallback 用 `[class*="message-select-wrapper-answer"]` 且 `innerText.includes('BASE_MATERIAL')`）。
8. **清洗**：`python scripts/clean-capture.py --in <原始捕获.md> --out <clean.md>`。（默认 `--start='Etsy Listing 终版优化'`、`--end='你好，我是千问'` 两个标记均不匹配本 skill 实际输出，故**默认仅去 UI 工具栏行（表格/编辑/文本/复制等），保留规划独白**；如需从首个正式段起，加 `--start "📋 原始素材摘要"` 丢弃「深度思考已完成」前的 preamble。）
9. **结构化（可选）**：`node scripts/extract-clean.js ...` 产 `data.csv`。
10. **证据链保留**：`out.md`（原始捕获）**永不覆盖删除**；`clean.md` 由 `out.md` 生成。

## 关键 gotchas（已实测）
- **输入框是 contenteditable DIV，非 textarea**：`document.querySelector('textarea')` 查不到；注入用 `page.keyboard.insertText`。
- **`browser_run_code_unsafe` 的 Node 侧无 fs/require/fetch**：片段内不能写文件、不能读文件、不能 `fetch` 本地服务（且 qianwen.com 是 HTTPS，会拦截向 HTTP 子资源的混合内容请求）。故大文本**只能 base64 内联进 code 参数**，抓取**只能 Blob 下载 + `download` 事件捕获**。
- **DOM 访问必须进 `page.evaluate`**：`document` 不在 Node 侧作用域。
- **大载荷绕过上下文**：>13K 字符用 `build-inject.py` 产 base64 内联片段，agent 读文件全文作 `code` 参数（已验证 27K+ base64 可用）。
- **每条 listing 独立新建对话窗口**：避免历史消息污染下一条。
- **域名**：`qianwen.com`（无 www）；非 `qwen.com`。
- **Qwen3.8-Max 输出约 16K 字符上限（2026-08-14 实测）**：长 listing（线一全量 + Step4 视觉 Prompt×7）真实生成会在 ~16K 字符处**被截断**（本次实测停在 img3 负向提示，img4-inf / img5-7 / BASE_MATERIAL JSON 块未实际产出）。模型会先输出完整规划独白（含 "BASE_MATERIAL JSON块" 字样）但正文没写完。**缓解**：① 视觉 Prompt 改在第二个对话窗口单独生成；② 用「仅文案」模式先出标题/Description/Tags，视觉另开窗口；③ 拆成多轮。干净产物以 `clean.md` 已有段为准，缺失段需补跑。

## 已废除（手搓 Playwright）
`scripts/optimize-one.js` / `optimize-batch.js` / `sync-cookies.py` 已移至 `scripts/_deprecated_handrolled_playwright/`，因违反「浏览器控制铁律」禁止使用。现行执行层全部走 MCP（见上）。

## 词库取用标准（已前置到初版）
终版**不接入关键词词库**（词库仅在初版 `listing-v1-seo-builder` 消费）。终版只做 GEO 语义优化 / 美式本土化转译 / 视觉方案 / 承诺审批，**不回原始词库重取词**；发现真实 SEO 缺口则回抛初版重跑。

> **与防蚕食账本的关系（重要，勿混）**：不接「关键词词库」≠ 不守「主词唯一性」。防蚕食账本是**店铺级运行态**（跨 SKU 全局唯一主词），由初版 `choose_main_word` 在取词时登记；终版须**贯通**该账本——生成前由 `build-inject.py --spu` 注入「本商品已分配唯一主词 + 同类 sibling 已占词（避免复用）」约束，写飞书前由 `verify-ledger.py` 校验主词未被漂移/互抢。详见下节。

## 防蚕食账本贯通（2026-08-16 深夜，深度优化）
> 与初版 `listing-v1-seo-builder` 共用**同一本账**（`~/.workbuddy/data/opc-seo/cannibalization_ledger.json`，可用 `OPC_SEO_LEDGER` 覆盖）。初版取词时 `choose_main_word` 登记每 SPU 的唯一主词；终版须沿用，不可漂移或被同类已占词互抢。账本是增强（非硬依赖）：读取失败仅告警、不阻断生成。

**生成前约束（build-inject.py）**：
- 组装注入载荷时加 `--spu <SPU>`（必要时 `--category` / `--ledger`），脚本经相对路径引入初版 `cannibalization_ledger.py`，调用 `render_rule_block(spu, cat)` 生成「【防蚕食约束】」中文块，注入提示词（置于启动指令之后、原始数据之前）。
- 约束块内容：①本商品已登记唯一主词→强制作标题/Description 前段核心焦点词；②同类 sibling 已占主词→禁止作为本商品核心焦点词；③皆无→软提示避免重复。
- 读取失败不阻断生成（仅告警）。

**写飞书前校验（verify-ledger.py，可选但推荐）**：
- 终版 clean.md 产出后、回写飞书前运行：`python scripts/verify-ledger.py --spu <SPU> --in <clean.md> [--title "确切标题"]`。
- 启发式抽取标题，检查：①已登记主词是否仍在标题；②同类 sibling 已占词是否抢占标题前 40 字符高权重区。
- 非致命：打印 🔴/🟡 告警并返非 0，供 agent 决策打回重跑；不修改文件。已知确切标题用 `--title` 提高准确度。

**闭环**：初版登记 → 终版生成前注入 → 终版写飞书前校验 → 三道保险杜绝主词漂移/同店互抢。

## 两层滤网·第二层（软判定兜底，2026-08-16 深夜，深度优化）
对齐 hermes 闸门栈的「分层、确定性为主」思路，但承认硬规则**有限**（只覆盖平台明确给出且能枚举完的违规）。软违规（过度优化/关键词堆砌/平台政策灰区/承诺无依据/AI痕迹/意图错配）硬规则必然漏判，故补第二层兜底：
- **软层模块** = 初版 `scripts/gate_soft.py`（与终版 `verify-ledger.py` 经相对路径共用，单一事实源）：
  - `SOFT_RUBRIC`：6 维软检查清单（自然度/堆砌/灰区/承诺/AI痕迹/意图匹配），**建议注入 Qwen3.8-Max 提示词**作为生成前自检（`build-inject.py` 可通过 `gate_soft.soft_rubric_text()` 拼接进载荷）。
  - `soft_heuristics(text)`：无模型时的轻量确定性代理（关键词密度/重复 bigram/夸张词/AI痕迹/句长），只出 🟡/🟠 review 信号，**绝不改退出码**。
- **终版写飞书前**：`verify-ledger.py` 在硬层（防蚕食+三级熔断+字段回读）之外，额外跑 `soft_heuristics` 并打印软层段，提示「最终由人/LLM 按 SOFT_RUBRIC 终审」——软层永不阻断，硬层（gate.py 的 MELTDOWN/CRITICAL_STOP）才是权威闸门。
- **两层关系**：硬层权威可阻断（exit 码），软层兜底不枚举完的灰区。两层串联，而非互相替代。

## 验证状态
- ✅ **2026-08-10 端到端实测跑通**（国内 IP）：qianwen.com/chat 登录态有效 → 切 Qwen3.8-Max → `build-inject.py` 注入 13,956 字符载荷 → 发送 → 真实生成（深度思考 + Step1→5 + 视觉 Prompt×7 + BASE_MATERIAL 块）→ Blob 抓取 → `clean-capture.py` 清洗，产出完整可交付 md。
- ✅ 地域限制已解除（国内 IP）；contenteditable 注入、Blob 抓取两条关键技术点已验证。
- ✅ `build-inject.py` / `clean-capture.py` 已用真实 artifacts 跑通验证。
- ✅ **2026-08-14 二次实测复核（home-workbuddy，国内 IP）**：按「挨个实测剩余 skill」计划独立复跑端到端——`build-inject.py` 注入 10,178 字符载荷（base64 内联）→ contenteditable `insertText` 注入生效（发送按钮 enabled）→ 切 Qwen3.8-Max（发现「新建对话必重置」+ 须 `getByText().click()` 真实点击）→ 真实生成（深度思考 + Step1 标题126字符 / Step2 承诺审批区6条 / Step3 纯英文 Description / Step4 视觉 Prompt×7 规划）→ 精准选择器 `.last-message-item .message-select-wrapper-answer` 抓取（16,391 字符）→ `clean-capture.py` 清洗出 `clean2.md`。**本次修正**：① 抓取弃用 heading 选择器（模型无该标题），改 reply 块 class；② Blob 下载仅首次落盘，改 `page.evaluate` 返回值 / 剪贴板落盘；③ 新增「Qwen3.8-Max ~16K 字符截断」限制与缓解方案。已加 🔒 LOCKED 上锁并推 OPC-ecommerce canonical。
