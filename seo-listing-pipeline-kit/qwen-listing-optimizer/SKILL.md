---
name: qwen-listing-optimizer
description: "[阶段1·文案+视觉方案·千问Qwen3.8-Max·线一/线二] 真实驱动千问网页端 Qwen3.8-Max 执行 Listing 终版优化（标题/Description/Tags/承诺审批区 + 视觉 Prompt×7）。线一(新上架全量)默认开视觉；线二(在售迭代)默认小改、视觉需用户主动开。触发词：跑终版/优化 listing/批量优化/生成标题描述视觉/新 listing 上架/在售 listing 优化；路线专用触发词：线一全量 / 线二小改 / 仅文案 / 开视觉 / 重做视觉（命中则直接解析线别+模式，无需点选；未命中任何路线触发词则执行前强制 Step 0 点选）。每条 listing 独立新建对话窗口。需中国大陆出口 IP。终版不接关键词词库（词库由 listing-v1-seo-builder 初版消费）。"
---

> ⚠️ **版本声明（2026-08-10 MCP 化修订）**：本 skill 原执行层为**手搓 Playwright**（`scripts/optimize-one.js` 等自起 Chromium）。用户于 2026-08-08 立「浏览器控制铁律：只认 MCP、禁手搓 Playwright」，故已**废除手搓脚本**（归档于 `scripts/_deprecated_handrolled_playwright/`），执行层全面改为 **`playwright-qwen` MCP 驱动**。端到端已于 2026-08-10 在国内 IP 环境实测跑通（详见「验证状态」）。

> 📦 **v2 融合声明（2026-08-17）**：本版 = office-workbuddy 已落地增强（模型铁律·禁止降级 / Step 0 路线等级强制点选 / Step 1.5 严禁代码点新建对话 / Step 6.5 截断根因更正 / `switch-qwen38max.js` 确定性切模型 / `mcp.json` 加 `--headed` / `clean-capture.py` 锚记路径 + `strip_echo_markers`）**＋** home-workbuddy 验证过的独有架构（人工交接双路径 `assemble_handoff` 落点 / 防蚕食账本贯通 `build-inject --spu` + `verify-ledger` / 两层滤网软层兜底 / Stage 4 写飞书逐条授权），三方无损合并。v1 基线（home 验证版）不动；本目录为融合产物。

# 千问 Listing 优化器（playwright-qwen MCP 真实执行）

## 核心约定（铁律）
- **真实执行，非模拟**：必须真正驱动千问网页端里的 Qwen3.8-Max 模型本人生成内容，**绝不由本机套用提示词替模型生成**（用户明确不认可"模拟"方式）。
- **模型铁律（禁止降级）**：本 skill 强制使用 **Qwen3.8-Max 或更高**（如后续有 Qwen3.9 / 4.x-Max 亦可用）。**严禁**使用 `Qwen3.7-千问` / `Qwen3.7-Max` / `Qwen3.6-Flash` 等任何低版本——低版本输出质量不满足 Listing 终版要求，且曾实测因此产出错误 deliverable（100163 首跑误跑在 Qwen3.7-千问，已作废重跑）。Agent 必须在注入前 **DOM-核验徽标含 `Qwen3.8-Max`**，降级一律拒绝执行。
- **每条独立窗口（零污染）**：每优化一个 listing 都新建一个对话窗口，跑完即结束，绝不在同一窗口连续跑多个。无关商品类目、无关全量/文案模式。
- **前置判断**：全量优化才输出 Step4 视觉 Prompt×7；非全量（仅标题 / 仅 Description / 局部调整）跳过视觉。
- **浏览器只认 MCP**：所有网页端操作（导航/点击/填表/截图/抓取/注入）**唯一合法手段是 `playwright-qwen` MCP**，严禁任何 `*.js` 自起 Chromium（见 `scripts/_deprecated_handrolled_playwright/README.md`）。

## 三维路由定位（本 skill）
> 全链路由「线别 × 模式 × 工具」三个维度决定调用哪个 skill。本 skill 只负责**阶段 1**。

- **阶段**：阶段 1 · 文案 + 视觉方案设计（输出 7 段 PROMPT/NEGATIVE 文字，**不直接出图**）
- **线别**：线一（新 listing 上架，默认全量+开视觉）/ 线二（在售迭代，默认小改、视觉需用户主动开）
- **工具**：千问 Qwen3.8-Max（网页端 `qianwen.com`）
- **上游**：可选 `listing-v1-seo-builder`（初版，消费关键词词库产出 SEO 草稿）；终版**不接词库**，但**贯通防蚕食账本**（共享初版账本，生成前注入唯一主词约束，写飞书前校验，见下「防蚕食账本贯通」）
- **下游**：阶段 2 图生图 → `doubao-image-mcp`（首选）/ `qwen-image-mcp`（备选），消费本 skill 的 7 段 PROMPT + 参考图形成「约束对」
- **触发词（泛）**：用千问跑终版 / 优化 listing / 批量优化 / 生成标题描述视觉 / 新 listing 上架 / 在售 listing 优化
- **不接词库**：终版不取关键词词库，词库仅在 `listing-v1-seo-builder`（初版）消费

### 路线/等级专用触发词与强制点选（2026-08-15 固化）
> 一句话 `@skill 优化 XXX` 容易默认错线别，故建立**显式触发词 + 兜底强制点选**双保险。Agent 收到任务先扫描指令是否命中下表触发词；命中则直接解析，未命中则 **Step 0 必弹 AskUserQuestion**，不得默认按线一大改。

| 用户指令中的触发词 | 解析 → 线别 | 模式（`--mode`） | 视觉 |
|---|---|---|---|
| `线一全量` / `新上架全量` / `上架终版` / `开视觉全量` | 线一 | full（全量） | 开 |
| `线二小改` / `在售迭代` / `已上架优化` / `小改` | 线二 | copy（仅文案） | 关 |
| `仅文案` / `关视觉` / `跳过视觉` | 沿用已声明线别（未声明按线二） | copy | 关 |
| `开视觉` / `重做视觉` / `重设计视觉` | 沿用已声明线别 | full | 开 |

- **强制点选规则**：用户指令**未命中任何上表触发词**（如只说"优化 100337"），Agent 必须在导航前用 `AskUserQuestion` 弹两问——①路线（线一·新上架全量 / 线二·在售迭代）②视觉开关（开视觉 / 关视觉·仅文案），拿到明确答复后才进 Step 1。**禁止默认线一、禁止先跑后问**。
- `build-inject.py` 的 `--line` 取自由串（原样写进启动指令，规范值 `线一全量` / `线二小改`），`--mode full|copy` 控制视觉开关。

| 维度 | 本 skill 取值 |
|---|---|
| 阶段 | 1（视觉方案设计） |
| 线别 | 线一 / 线二 |
| 模式 | 全量（开视觉）/ 仅文案（关视觉，跳过 Step4）/ 局部 |
| 工具 | 千问 Qwen3.8-Max |

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

## 两条线框架（终版 / 优化，2026-08-04 划定）
> 收到优化任务**先确权属哪条线**，再决定能否接词库 + 改动幅度上限。**硬规则（2026-08-15）**：未命中路线触发词时，必须执行 **Step 0 强制点选**（`AskUserQuestion` 弹路线 + 视觉开关），**绝不允许默认按线一大改**，也不允许"先跑后问"。

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
- **`playwright-qwen` MCP 已连接且为「有头」模式**（连接器管理处启用；`mcp.json` playwright-qwen 条目 `args` 须加 `--headed`）。登录态复用 `PLAYWRIGHT_MCP_CDP_PROFILE` 环境变量指向的 `cdp-profile-h` 个人资料（本机 = `C:/Users/nicho/.workbuddy/chrome-profiles/cdp-profile-h`，已在 mcp.json 配好）。无头实例须重启连接器切换为有头，否则 Step 6「有头实时观测」无法落地。
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
  # 生成「【防蚕蚀约束】」块注入提示词（详见下节「防蚕食账本贯通」）。
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
> 以下 `browser_*` 均为 `playwright-qwen` MCP 工具。每个 listing 都从**新建对话**开始——**「新建对话」必须由人工点击按钮完成（见 Step 1.5），严禁用代码脚本自动点击**。

0. **路线/等级前置点选（强制）**：扫描用户指令是否命中「路线/等级专用触发词」（见上表）。
   - 命中 → 直接解析 `--line` / `--mode`，跳过本步。
   - 未命中 → **必须用 `AskUserQuestion` 弹两问**：①路线（线一·新上架全量 / 线二·在售迭代）②视觉开关（开视觉 / 关视觉·仅文案）。拿到明确答复后再进 Step 1。**禁止默认线一、禁止先跑后问**。
1. **导航**：`browser_navigate` → `https://qianwen.com/chat`（无 www）。
1.5. **新建对话（【人工操作】·严禁代码自动化）**：在千问界面**手动点击「新建对话」按钮**，开启一个全新空白对话窗口（满足"每条 listing 独立窗口·零污染"）。
   - ⛔ **此步禁止用代码脚本点击**：脚本自动点「新建对话」极大概率在**上一任务输出尚未结束**时就切走窗口，导致正在生成的回答被截断、抓取落空。务必由人工在确认上一条已彻底停稳后再点。
   - ✅ 允许的是**写指引**（即本段文字），不是写点击代码。本 skill 唯一允许"代码固定"的浏览器动作是 Step 2 的「切 Qwen3.8-Max」（`switch-qwen38max.js`）；其余浏览器交互（新建对话、发送、观测、抓取）均走人工 / MCP 工具，Agent 不得自搓点击脚本。
2. **验证会话（模型铁律·硬门禁）**：①确认已登录（账号如 `Qwen1122`）；②**用 DOM 读取模型徽标文本并断言其含 `Qwen3.8-Max`（或更高版本号）**——绝不可"点了就假设切成功"。若徽标是 `Qwen3.7-千问` / `Qwen3.7-Max` / `Qwen3.6-Flash` 等**任何低于 3.8-Max 的模型，一律视为降级、严禁注入**，必须点模型选择器切到 `Qwen3.8-Max`（描述"新模型 最新 Max 旗舰模型"），切完**再次读徽标确认**才允许进 Step 3。注入前（Step 4 之前）还需再读一次徽标做最终确认。
   - **确定性切模型（代码固定·2026-08-15 用户点名）**：用 `scripts/switch-qwen38max.js`（`browser_run_code_unsafe` 执行；须先 `cp` 进 MCP 允许根目录）做**确定性切换+核验**——脚本自动读徽标、若非 3.8-Max 则点开选择器点 `Qwen3.8-Max` 选项、再读徽标断言并返回 `{ok,switched,before,after}`。**不要再靠手点赌成功**；本脚本是用户明确"可以用代码固定"的步骤。
3. **组装载荷**：运行 `build-inject.py`（见上）产出 `_inject_snippet.js`。
4. **注入输入框**（关键）：
   - 读 `_inject_snippet.js` 全文，作为 `browser_run_code_unsafe` 的 `code` 参数执行。
   - 片段在浏览器内 `atob` 还原 → `page.keyboard.insertText(txt)` 注入**输入框**。
   - ⚠️ 千问输入框是 **`contenteditable` DIV（不是 `<textarea>`）**；`insertText` 走 CDP 级粘贴，能触发 React 受控更新使「发送」按钮 enabled。`setter.call`/`dispatchEvent`/`locator.fill` 均无效或超时。
5. **发送**：`browser_click` → `button[aria-label="发送消息"]`（注入后按钮解除 disabled 即可点）。
6. **等待生成（有头实时观测，强制）**：有头浏览器下**肉眼 / `browser_snapshot` 主动轮询**实时 DOM，直到「停止回答」按钮消失**且回答气泡长度两次轮询一致（确认已停止流式输出）**。Qwen3.8-Max 开深度思考后输出极长（实测 50K+ 字符，含思考块 + Step1→5 + 视觉 Prompt×7），有头模式约 60–180s。**严禁无头+事后读文件式等待**——必须在生成进行中就能看到进度，发现异常（如提前停、卡死）立即干预。**截断自检**：BASE_MATERIAL 是输出最末段，若在观测中发现回答在 Step5/清单后、BASE_MATERIAL 未完成即停止增长，说明触发了输出长度上限，须按 Step 6.5 处理（见下）。
6.5. **输出截断应急（BASE_MATERIAL 被切 / 触发输出长度上限）**：
   - **现象**（有头实时观测即可当场发现）：回答在 Step5 清单之后、`BASE_MATERIAL` JSON 未完成（缺收尾 `]`/`}`）即停止增长，「停止回答」消失但结构残缺。
   - **根因（已更正·2026-08-15）**：所谓"Qwen3.8-Max 硬 token 上限截断"**未经证实**——100163 首跑实为**抓早了**：未等气泡长度稳定即抓取，误判"截断"后人为续写、制造了多轮重叠。真实情形应为输出仍在流式增长，抓到的是半截。故**首要纪律是 Step 6 的"长度两次轮询一致再抓"**，绝不在增长中抓取；只有确认气泡长度稳定（两次轮询一致）且结构确实残缺（缺收尾 `]`/`}`），才判定为截断并按下方解法续写。**禁止把"模型有硬输出上限"当既定事实写死**（此前误写，已纠正）。
   - **解法（按优先级）**：
     1. **同窗口续写（最轻量）**：在原对话发「请继续输出完整 `BASE_MATERIAL` 并闭合 JSON（specs / shipping / 其余字段）」——模型基于上下文补全尾部，无需重跑。
     2. **重跑 + 收紧冗长（最完整）**：在提示词【Step4】明确「模块说明 / 移动端检查 各限 1 行或标注可选」，或在【基材输出块】前加「务必完整闭合 BASE_MATERIAL JSON，临近长度上限时优先压缩视觉 Prompt 的模块说明，保住 BASE_MATERIAL」；重跑前先确认有头实例在跑。
     3. **禁止伪造**：缺失字段**绝不由 Agent 臆造补写**（准确性铁律），只能续写 / 重跑取回真实内容。
7. **抓取结果**（无 fs/fetch，用 Blob 下载）：
   ```
   browser_run_code_unsafe（**结构法 · 2026-08-15 验证可用**，旧版按 h1-h6 标题定位会落空——Qwen3.8-Max 输出不含 heading 标签，且模型头是「🚀 Etsy Listing 终版优化输出」纯文本）:
   ```js
   async (page) => {
     const res = await page.evaluate(() => {
       const depth = (el) => { let d=0,c=el; while(c){d++;c=c.parentElement;} return d; };
       // 1) 取【最深】含 BASE_MATERIAL 的元素（.find 按文档序会命中最外层 body，务必取最深）
       const els = [...document.querySelectorAll('*')].filter(el => el.innerText && el.innerText.includes('BASE_MATERIAL'));
       let baseEl=null, maxD=-1;
       for (const el of els){ const d=depth(el); if(d>maxD){maxD=d;baseEl=el;} }
       if(!baseEl) return {error:'base not found'};
       // 2) 向上回溯到不含注入提示词（【角色设定】）的回答气泡；一旦父容器含【角色设定】即停止（那是装两条消息的共享容器）
       let cur=baseEl, answerBubble=null;
       while(cur && cur!==document.body){
         const t=cur.innerText||'';
         if(!t.includes('【角色设定】')) answerBubble=cur; else break;
         cur=cur.parentElement;
       }
       if(!answerBubble) return {error:'no answer bubble'};
       const text=answerBubble.innerText;
       const a=document.createElement('a');
       a.href=URL.createObjectURL(new Blob([text],{type:'text/markdown'}));
       a.download='out.md'; a.click();
       return {len:text.length};
     });
     if(res.error) return JSON.stringify(res);
     const dl=await page.waitForEvent('download',{timeout:15000});
     return JSON.stringify({len:res.len, path:await dl.path()});
   }
   ```
   - **必须先等生成完全结束再抓**：Qwen3.8-Max 开深度思考后输出极长（实测 50K+ 字符，含思考块 + Step1→5 + 视觉 Prompt×7）。`停止回答` 按钮可能未出现而仍在流式输出——务必**轮询回答气泡长度两次一致**后再抓（单次 MCP 调用被 30s 上限截断，用 `page.waitForTimeout` 分段等待）。
   - 落盘路径为 MCP 运行时目录，用 Bash `cp` 复制到工作区（如 `Desktop/images/`）。
8. **清洗**：`python scripts/clean-capture.py --in <原始捕获.md> --out <clean.md>`。脚本现已按**候选标记自动探测**起止（线一 `Etsy Listing 终版优化` / 线二 `原始素材摘要` 等），不再依赖单一固定标题，线一/线二输出均无需临时扩展清洗。
9. **结构化（可选）**：`node scripts/extract-clean.js ...` 产 `data.csv`。
10. **证据链保留**：`out.md`（原始捕获）**永不覆盖删除**；`clean.md` 由 `out.md` 生成。

## 关键 gotchas（已实测）
- **输入框是 contenteditable DIV，非 textarea**：`document.querySelector('textarea')` 查不到；注入用 `page.keyboard.insertText`。
- **`browser_run_code_unsafe` 的 Node 侧无 fs/require/fetch**：片段内不能写文件、不能读文件、不能 `fetch` 本地服务（且 qianwen.com 是 HTTPS，会拦截向 HTTP 子资源的混合内容请求）。故大文本**只能 base64 内联进 code 参数**，抓取**只能 Blob 下载 + `download` 事件捕获**。
- **DOM 访问必须进 `page.evaluate`**：`document` 不在 Node 侧作用域。
- **大载荷绕过上下文**：>13K 字符用 `build-inject.py` 产 base64 内联片段，agent 读文件全文作 `code` 参数（已验证 27K+ base64 可用）。
- **MCP 文件根限制（2026-08-15 实测）**：`browser_run_code_unsafe` 的 `filename` 参数仅允许落在 MCP 允许根目录（如 `C:\Users\...\ .workbuddy\logs\mcp-runtime\custom-mcp_playwright-qwen-*\`），工作区/桌面路径会报 `File access denied`。`build-inject.py` 产出的 `_inject_snippet.js` 需先 `cp` 进允许根目录再传 `filename`，或直接把文件全文作为 `code` 参数内联。
- **每条 listing 独立新建对话窗口**：避免历史消息污染下一条。
- **域名**：`qianwen.com`（无 www）；非 `qwen.com`。

## 已废除（手搓 Playwright）
`scripts/optimize-one.js` / `optimize-batch.js` / `sync-cookies.py` 已移至 `scripts/_deprecated_handrolled_playwright/`，因违反「浏览器控制铁律」禁止使用。现行执行层全部走 MCP（见上）。

## 词库取用标准（已前置到初版）
终版**不接入关键词词库**（词库仅在初版 `listing-v1-seo-builder` 消费）。终版只做 GEO 语义优化 / 美式本土化转译 / 视觉方案 / 承诺审批，**不回原始词库重取词**；发现真实 SEO 缺口则回抛初版重跑。

> **与防蚕食账本的关系（重要，勿混）**：不接「关键词词库」≠ 不守「主词唯一性」。防蚕食账本是**店铺级运行态**（跨 SKU 全局唯一主词），由初版 `choose_main_word` 在取词时登记；终版须**贯通**该账本——生成前由 `build-inject.py --spu` 注入「本商品已分配唯一主词 + 同类 sibling 已占词（避免复用）」约束，写飞书前由 `verify-ledger.py` 校验主词未被漂移/互抢。详见下节。

## 防蚕食账本贯通（home-workbuddy 深度优化）
> 与初版 `listing-v1-seo-builder` 共用**同一本账**（`~/.workbuddy/data/opc-seo/cannibalization_ledger.json`，可用 `OPC_SEO_LEDGER` 覆盖）。初版取词时 `choose_main_word` 登记每 SPU 的唯一主词；终版须沿用，不可漂移或被同类已占词互抢。账本是增强（非硬依赖）：读取失败仅告警、不阻断生成。

**生成前约束（build-inject.py）**：
- 组装注入载荷时加 `--spu <SPU>`（必要时 `--category` / `--ledger`），脚本经相对路径引入初版 `cannibalization_ledger.py`，调用 `render_rule_block(spu, cat)` 生成「【防蚕蚀约束】」中文块，注入提示词（置于启动指令之后、原始数据之前）。
- 约束块内容：①本商品已登记唯一主词→强制作标题/Description 前段核心焦点词；②同类 sibling 已占主词→禁止作为本商品核心焦点词；③皆无→软提示避免重复。
- 读取失败不阻断生成（仅告警）。

**写飞书前校验（verify-ledger.py，可选但推荐）**：
- 终版 clean.md 产出后、回写飞书前运行：`python scripts/verify-ledger.py --spu <SPU> --in <clean.md> [--title "确切标题"]`。
- 启发式抽取标题，检查：①已登记主词是否仍在标题；②同类 sibling 已占词是否抢占标题前 40 字符高权重区。
- 非致命：打印 🔴/🟡 告警并返非 0，供 agent 决策打回重跑；不修改文件。已知确切标题用 `--title` 提高准确度。

**闭环**：初版登记 → 终版生成前注入 → 终版写飞书前校验 → 三道保险杜绝主词漂移/同店互抢。

## 两层滤网·第二层（软判定兜底，home-workbuddy 深度优化）
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
- ✅ **2026-08-15 全链路复跑成功**（线一全量·木质照片项链）：切换 Qwen3.8-Max → `build-inject.py`（15.8K 载荷）→ `cp` 进 MCP 允许根目录 → `filename` 注入 contenteditable → 真实生成（深度思考 ~50K 字符，含 Step1→5 + 视觉 Prompt×7 + BASE_MATERIAL）→ **等长度稳定后**结构法抓取 → `clean-capture.py` 清洗产出完整可交付 md。旧版「按 h1-h6 标题定位」抓取脚本已确认为失效（模型输出无 heading 标签），改为「最深 BASE_MATERIAL 元素向上回溯回答气泡」结构法，见 Step 7。
- ✅ **2026-08-15 第二次固化（路线/等级选择机制）**：新增「路线专用触发词 + 兜底强制点选」——`线一全量 / 线二小改 / 仅文案 / 开视觉 / 重做视觉` 命中即解析、未命中则 Step 0 必弹 `AskUserQuestion`（路线+视觉两问），杜绝默认错线别；同步把 `clean-capture.py` 起止标记从单一固定标题改为候选自动探测，兼容线一/线二输出（实测线二·定制酒壶 100324 复跑验证：模型正确跳过 Step4 视觉，清洗无需临时兜底）。
- ⚠️ **2026-08-15 复核纠正（模型降级事故）**：100163「九动物」重做首跑**实际跑在 Qwen3.7-千问**（Step 2 的"切后再次读徽标确认"未执行，误以为切到 3.8-Max），deliverable `listing_optimized.md` 已作废。根因 = 未 DOM 核验徽标。已新增「模型铁律·硬门禁」（核心约定 + Step 2），要求注入前 DOM-核验徽标含 `Qwen3.8-Max`、降级一律拒绝。100163 将于同日在 **Qwen3.8-Max** 重跑（先听完用户第三条补充指令再执行）。
- ✅ **2026-08-14 二次实测复核（home-workbuddy，国内 IP）**：独立复跑端到端——`build-inject.py` 注入 10,178 字符载荷（base64 内联）→ contenteditable `insertText` 注入生效（发送按钮 enabled）→ 切 Qwen3.8-Max（发现「新建对话必重置」+ 须 `getByText().click()` 真实点击）→ 真实生成（深度思考 + Step1 标题126字符 / Step2 承诺审批区6条 / Step3 纯英文 Description / Step4 视觉 Prompt×7 规划）→ 精准选择器 `.last-message-item .message-select-wrapper-answer` 抓取（16,391 字符）→ `clean-capture.py` 清洗出 `clean2.md`。**本次修正**：① 抓取弃用 heading 选择器（模型无该标题），改 reply 块 class；② Blob 下载仅首次落盘，改 `page.evaluate` 返回值 / 剪贴板落盘；③ 新增「Qwen3.8-Max ~16K 字符截断」限制与缓解方案。
