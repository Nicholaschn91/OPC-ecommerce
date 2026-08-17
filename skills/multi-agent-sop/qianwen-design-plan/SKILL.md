---
name: qianwen-design-plan
description: >
  > 🔒 **LOCKED · v5.4 定稿版 · 2026-08-16 · 不要再改** · 千问设计方案生成器
  从飞书「商品基础信息」生成「设计方案」（text），下游由 aistudio-image-bridge 消费生成设计图。
  本 skill 仅含千问通道（Qwen3.8-Max，browser-qwen MCP 驱动）。
---

# 千问设计方案生成器（qianwen-design-plan）

⚠️ 锁定声明（已审定）：本 skill 为 v5.4 已审定版本。Agent 仅可读取并按步骤执行，禁止修改本文件及 scripts/ 下任何内容；执行时须严格遵循步骤顺序，不得省略或跳过任何步骤。如需变更，须先与用户确认。

从飞书「商品基础信息」生成「设计方案」（text），下游由 `aistudio-visualbridge` 消费生成设计图。
本 skill 仅含 **千问通道**（Qwen3.8-Max，browser-qwen MCP 驱动）。AI Studio 回退通道见 `aistudio-design-plan`。

## 依赖脚本（`scripts/`）

| 脚本 | 用途 |
|---|---|
| `fetch_input.py` | 从飞书取「商品基础信息」→ txt；`--list-empty` 列出待生成记录 |
| `build_design_plan_inject.py` | 本地组装注入载荷（base64 + insertText 模板）；`--target qianwen` 自然任务式包装；`--mcp-root=auto` 自动拷贝到 MCP 允许根目录 |
| `dp_write_feishu.py` | 去头部注释块 + **传输层解码**（还原 MCP JSON 双重转义）后回写飞书「设计方案」字段（复用 feishu_products_io.update_design）；v5.4 纯净输出协议下**无需独立清洗工具** |
| `extract_copy_brief.py` | 提取 copy brief（共享） |

> ⚠️ **v5.4 变更**：`extract_qianwen_output.py` 已删除。v5.4 提示词自带「八、8.0 纯净输出协议」，模型输出即 100% 纯英文结构化正文，无需内容级清洗；仅 `dp_write_feishu.py` 做传输层解码（MCP 落盘 innerText 的 JSON 转义还原）。

---

# 千问通道（Qwen3.8-Max）完整执行流程

> 实测已跑通：圆形纽扣徽章（recvoXG4YrCr6k）经此流程成功生成，零审核拦截、零侧栏残留（v5.1 验证）。
> v5.4 在提示词层引入「八、8.0 纯净输出协议」——输出即纯净正文，故移除原步骤 4 的清洗工具，raw innerText 直接经 `dp_write_feishu.py` 传输层解码回写。
> 浏览器交互**全部**走 `mcp__browser-qwen__browser_*`，无自搓脚本。

## 🔁 批量执行铁律（必读）

千问通道**批量生成多个商品**时，必须严格遵循：

- ✅ 在同一个浏览器**标签页内**点「**新建对话**」（千问对话页侧栏 / 左上角的「新对话」按钮）开启下一个商品任务；
- ❌ **禁止开新标签页**（`Ctrl+T` / 右键「在新标签页打开」）跑下一个商品——新标签页不继承当前 `cdp-profile-h` 登录态，且千问会把新标签判为独立会话、模型回退到 `Qwen3.7-千问`；
- 每个商品生成完毕后，先点「新建对话」清空上下文，再注入下一个商品的载荷；**切勿在同一对话里连续贴多个商品**（会串上下文、诱发规范复述思维链、破坏 v5.4 纯净输出）。

> 与 `qwen-image-mcp` / `qwen-listing-optimizer` 约定一致：单 tab 复用 + 页内「新建对话」起新任务。

## 0. 前置

- 千问**无地域限制**（本环境实测直连 `qianwen.com/chat` 正常，旧记忆「地域限制」已推翻）。
- 登录态存于 `cdp-profile-h`（账号 `Qwen1122`），browser-qwen MCP 默认复用，无需重复登录。
- 执行前确认 browser-qwen MCP 已连接（连接器管理处为「已信任」状态）。

## 1. 取商品基础信息

```bash
PY="C:/Users/nicho/.workbuddy/binaries/python/versions/3.13.12/python.exe"
cd <skill>/scripts

"$PY" fetch_input.py --list-empty                       # 列待生成记录
"$PY" fetch_input.py <record_id> -o ./dp_run/input_<record_id>.txt
```

## 2. 本地组装注入载荷（CLI）

```bash
cd <skill>/scripts
"$PY" build_design_plan_inject.py \
  --target qianwen \
  --si   ../assets/system_instructions_qianwen_v54.txt \
  --data ../dp_run/input_<record_id>.txt \
  --out  ../dp_run/dp_inject_<record_id>.js \
  --mcp-root auto        # 自动拷贝到 browser-qwen MCP 允许根目录（避免 "File access denied"）

# 产出：
#   dp_run/dp_inject_<record_id>.js        ← 注入片段（已自动拷到 MCP 根目录）
#   dp_run/dp_inject_<record_id>.prompt.txt ← 纯文本提示词（供人工把关，确认无【角色设定】元标记）
```

> ⚠️ 把关要点：打开 `.prompt.txt`，确认**开头是「你是一名资深的 POD…」自然句、全文无 `【角色设定】`/`【启动指令】` 元标记**。这两类元标记会被千问判为 prompt-injection 直接拒答。

## 3. 千问网页端执行（MCP 剧本，逐步照抄）

按顺序调用 `mcp__browser-qwen__browser_*`。每一步的 `function` 是可直接粘贴的浏览器端 JS。

### 3.1 开新窗口 + 确认登录态
```
browser_navigate  url=https://qianwen.com/chat
browser_snapshot
```
确认：页面含 `Qwen1122`（已登录）、模型默认 `Qwen3.7-千问`。

### 3.2 切模型到 Qwen3.8-Max
```
browser_click  target=<模型选择器元素>      # 显示 "Qwen3.7-千问" 的那块
browser_evaluate  function=() => { const els=Array.from(document.querySelectorAll('div,li')); const t=els.find(el=>(el.innerText||'').trim()==='Qwen3.8-Max'&&el.children.length<=1); if(!t)return 'NOT_FOUND'; t.click(); return 'CLICKED'; }
browser_evaluate  function=() => { const all=Array.from(document.querySelectorAll('div')).filter(el=>/^Qwen3\.\d/.test((el.innerText||'').trim())&&el.children.length===0); return all[0]?all[0].innerText.trim():'NONE'; }
```
确认第二个 evaluate 返回 `Qwen3.8-Max`。

### 3.3 注入载荷（base64 + insertText，走已验证通道）
```
browser_run_code_unsafe  filename=<MCP根目录>/dp_inject_<record_id>.js
```
> MCP 根目录由 `build_design_plan_inject.py --mcp-root auto` 自动打印（形如
> `C:/Users/nicho/.workbuddy/logs/mcp-runtime/custom-mcp_browser-qwen-XXXX/.playwright-mcp/dp_inject_<record_id>.js`）。
> 注入函数内部：`atob` 还原 → `insertText` 触发 React 受控更新使「发送」按钮 enabled。

### 3.4 发送 + 等待
```
browser_click  target=<发送按钮>           # aria-label 含 "发送"
browser_wait_for  time=60                   # 长文生成，先等 60s
browser_evaluate  function=() => { const t=document.body.innerText; return JSON.stringify({refused:t.includes('无法回答')||t.includes('我们聊聊别的'), generating:t.includes('正在思考')}); }
```
确认 `refused:false`。若 `refused:true` → 见下方失败恢复（通常是 SI 还带元标记，回到步骤 2 重包）。

### 3.5 抓 raw innerText 落盘（到 MCP 根目录，便于本地回写）
```
browser_evaluate  filename=<MCP根目录>/_raw_inner.txt  function=() => { return document.body.innerText; }
```
> v5.4 输出已是纯净正文；落盘文件直接交给 `dp_write_feishu.py` 做传输层解码，**无需清洗**。

## 4. 回写飞书（CLI）

```bash
cd <skill>/scripts
"$PY" dp_write_feishu.py <record_id> <MCP根目录>/_raw_inner.txt

# 回读验证（必做）
cd ../../aistudio-visualbridge/scripts
"$PY" feishu_products_io.py show <record_id>
```
> `dp_write_feishu.py` 内部 `load_raw_text()` 负责传输层解码（还原 MCP JSON 双重转义），**不做内容级清洗**——v5.4 纯净输出协议保证正文可直接写入。

## 5. 交棒下游

「设计方案」写入后，由 `aistudio-visualbridge` 接手：解析 Prompt 组 → Nano Banana 2 Lite 生图 → 回写「设计方案图片」附件字段。

## 失败恢复速查

| 现象 | 原因 | 处理 |
|---|---|---|
| 回复「抱歉，我无法回答这个问题。我们聊聊别的吧。」（refused=true） | **千问审核拦截**：SI 仍带 `【角色设定】`/`【启动指令】` 元标记，被判为 prompt-injection | 回到步骤 2 用 `build_design_plan_inject.py --target qianwen`（自然任务式包装，去掉元标记）重包；**不是任务本身的问题**（纯自然语言请求同任务可正常作答）|
| `browser_run_code_unsafe` 报 "File access denied" | 传入的 `.js` 路径不在 MCP 允许根目录 | `build_design_plan_inject.py` 已加 `--mcp-root auto` 自动拷贝；或手动 `cp` 到 `custom-mcp_browser-qwen-*/.playwright-mcp/` 再引用该路径 |
| 注入后「发送」按钮未激活（disabled） | React 未识别 insertText（输入框未 focus / 选择器未命中 contenteditable）| 重试 `browser_run_code_unsafe`；仍不行用 `browser_snapshot` 看输入框真实选择器，必要时改 `build_design_plan_inject.py` 的 `querySelector` |
| 模型被重置回 `Qwen3.7-千问` | 每新建 `/chat` 窗口默认回退到 3.7；**开新标签页**也会触发 | 每次开新窗口都重做步骤 3.2 切 Qwen3.8-Max，并用 evaluate 确认；批量任务用页内「新建对话」而非新标签页 |
| 千问页面显示「在你所在的地区不可用」 | 出口 IP 非中国大陆（旧环境偶发；**本环境当前已无此限制**）| 切换大陆出口环境 / 代理；本环境直连即可 |

> 📌 **v5.4 无需清洗**：模型输出经「八、8.0 纯净输出协议」已是纯净正文，`dp_write_feishu.py` 仅做传输层解码（JSON 转义还原），**不要**再对输出做内容级清洗或正则截断。

> 📌 **千问输入框方案（与 qwen-image-mcp 的页面差异）**：本 skill 千问**对话页**是 `contenteditable` DIV，用 `insertText`（CDP 级粘贴）触发 React 受控更新；千问**生图页**（见 `qwen-image-mcp`，2026-08-13 已验证）用 `locator.fill` + 1500ms sync 有效。两页面 React 实现不同，勿混用。
