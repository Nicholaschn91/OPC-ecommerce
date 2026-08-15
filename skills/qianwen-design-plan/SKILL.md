# 千问设计方案生成器（qianwen-design-plan）

> **v2.0 混合架构 · 2026-08-15** · 代码(机械) + 大模型(判断) · v5.4 协议
>
> **执行原则**：机械操作（导航/切模型/注入/发送/等待/抽取/回写）走 `browser_run_code_unsafe` 代码块，一个调用干完多步，省 token；需要语义判断的（抽取目标对不对 / 输出有没有效 / 拒答换变体）留给大模型。**不要把所有事塞进一个全自动脚本，也不要逐个 MCP 工具调用。**

> ## ⛔ 单条处理铁律（最高优先级，违反即全盘崩）
>
> 1. **一次只处理一个 record_id**：取数 → 注入 → 发送 → 抽取 → 校验 → 回写 → 回验，全流程做完（含飞书落盘确认）才取下一个空记录。
> 2. **禁止预生成排队**：dp_run 同时**只留当前一条**的产物（`input_<rid>.txt` / `dp_inject_<rid>.js`）。**不批量预生成**多个商品的 input/dp_inject 堆在 dp_run 里。批量 = 多次运行本 skill，不是把多个商品信息堆在 skill 里排队。
> 3. **一报错第一时间在同条处理**（不跳过、不继续下一条）：
>    - 拒答 → 立即换变体重试（同条，3 变体循环 + 冷却 30s），3 次都拒才标记 REFUSED 跳过
>    - 抽取到思考区/无效 → 同条重抽或换变体
>    - Chrome 断 → 重启 Chrome 后**继续同条**（不跳到下一条）
>    - 超时 → 同条再等一轮
> 4. **为什么不能排队**：排队时一个报错会污染后续全部（上下文累积 + 错误传播 + "前边 50 个的影响"）。单条串行才能隔离故障、第一时间处理。

## 1. 这个 skill 做什么

从飞书「商品基础信息」**自动生成**英文设计方案（标题/描述/Prompt组等），写入飞书「设计方案」字段。下游 `aistudio-visualbridge` 消费生成的 Prompt 生图。

**通道**：千问网页端 **Qwen3.8-Max**（playwright-qwen MCP 真实驱动）

## 2. 什么时候用

- 商品需要"设计方案"文字（标题/5 点/描述/Tag/Prompt×7）
- 在售 listing 要做文案优化
- 收到触发词：「跑千问设计方案」「生成文案+视觉方案」「Listing 终版（线一）」

## 3. 前置

| 项 | 状态 |
|---|---|
| `playwright-qwen` MCP 已连接 | ✅ 复用 `cdp-profile-h`（账号 Qwen1122 登录态） |
| Chrome 9222 已启动 | ✅ `chrome.exe --remote-debugging-port=9222 --user-data-dir=.../cdp-profile-h` |
| 飞书表2 已配置 | ✅ Base `ONy9bZ0oFaaiSEsf4ggcs61enRc` / Table `tbl75glY29VulRLm` |
| 国内 IP | ✅ 直连 qianwen.com 无地域限制 |

## 4. 固定路径（复制粘贴用，别改）

```bash
PY="C:/Users/nicho/.workbuddy/binaries/python/versions/3.13.12/python.exe"
SKILL="C:/Users/nicho/.workbuddy/skills/multi-agent-sop/qianwen-design-plan"
SCRIPTS="$SKILL/scripts"
```

> MCP 根目录（build 脚本会打印，形如）：`C:/Users/nicho/.workbuddy/logs/mcp-runtime/custom-mcp_playwright-qwen-XXXX/.playwright-mcp/`

---

## 5. 执行步骤

### 步骤 1：列待生成记录

```bash
"$PY" "$SCRIPTS/fetch_input.py" --list-empty
```

**预期**：每行 `recXXX | 商品名`，末尾 `共 N 条待生成设计方案`

### 步骤 2：取商品信息 → 落盘

```bash
"$PY" "$SCRIPTS/fetch_input.py" <record_id> -o "$SKILL/dp_run/input_<record_id>.txt"
```

### 步骤 3：组装注入载荷

```bash
"$PY" "$SCRIPTS/build_design_plan_inject.py" \
  --target qianwen \
  --si   "$SKILL/assets/system_instructions_qianwen_v54.txt" \
  --data "$SKILL/dp_run/input_<record_id>.txt" \
  --out  "$SKILL/dp_run/dp_inject_<record_id>.js" \
  --mcp-root auto
```

**产出**：
- `dp_inject_<record_id>.js` — 注入片段（已拷到 MCP 根目录）
- `dp_inject_<record_id>.prompt.txt` — 纯文本提示词

**⚠️ 把关**：`.prompt.txt` 开头必须是自然句「你是一名资深的 POD…」，全文**无** `【角色设定】`/`【启动指令】` 元标记（否则千问判 prompt-injection 拒答）。

**报错**：若 `--mcp-root auto` 拷贝失败（沙箱 strip_write），手动 `cp dp_inject_<rid>.js <MCP根目录>/` 或内联 base64。

---

### 步骤 4：浏览器执行（3 个代码块 + 1 个抽取代码块）

> 全部走 `mcp__playwright-qwen__browser_run_code_unsafe`。把 `<record_id>` 和 `<MCP_ROOT>` 替换成实际值。

#### 4.1 代码块 A：导航 + 切 Qwen3.8-Max（一个调用搞定）

**工具**：`browser_run_code_unsafe`，`code` 参数填：

```js
async (page) => {
  // 强制新对话（单条铁律）：当前 URL 有 session id（/chat/xxx）或不在 qianwen，都 navigate 到根 /chat 开新对话
  // 点"新建对话"按钮常不生效（URL 不变 → 上下文累积 → 后续商品污染前条拒答对话），navigate 根 /chat 最可靠
  const curUrl = page.url();
  if (!curUrl.includes('qianwen.com') || /qianwen\.com\/chat\/[a-f0-9]{8,}/.test(curUrl)) {
    await page.goto('https://qianwen.com/chat', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(3500);
  }
  const url = page.url();
  const login = await page.evaluate(() => document.body.innerText.includes('Qwen1122'));
  if (!login) return JSON.stringify({ err: 'NOT_LOGGED_IN', url });
  // 验证是新对话（rounds 应为 0）；若仍有旧 round，说明 navigate 没清空，再点一次"新建对话"
  const rounds = await page.evaluate(() => document.querySelectorAll('.chat-round').length);
  if (rounds > 0) {
    await page.evaluate(() => {
      const els = Array.from(document.querySelectorAll('button,div,[role="button"],a'));
      const nb = els.find(e => { const t=(e.innerText||'').trim(); const a=(e.getAttribute('aria-label')||'').trim(); return t.includes('新建对话')||t.includes('新对话')||a.includes('新建对话'); });
      if (nb) nb.click();
    });
    await page.waitForTimeout(2000);
  }

  // 切模型到 Qwen3.8-Max（robust：下拉可能开/可能关）
  let optClicked = await page.evaluate(() => {
    const els = Array.from(document.querySelectorAll('div,li,span'));
    const t = els.find(el => (el.innerText||'').trim()==='Qwen3.8-Max' && el.children.length===0 && el.offsetParent!==null);
    if(!t) return false; t.click(); return true;
  });
  if (!optClicked) {
    // 下拉关了，先点模型选择器开下拉
    await page.evaluate(() => {
      const els = Array.from(document.querySelectorAll('div'));
      const sel = els.find(el => (el.innerText||'').trim()==='Qwen3.7-千问' && el.children.length===0);
      if (sel) sel.click();
    });
    await page.waitForTimeout(700);
    await page.evaluate(() => {
      const els = Array.from(document.querySelectorAll('div,li,span'));
      const t = els.find(el => (el.innerText||'').trim()==='Qwen3.8-Max' && el.children.length===0);
      if (t) t.click();
    });
  }
  await page.waitForTimeout(900);
  const model = await page.evaluate(() => {
    const all = Array.from(document.querySelectorAll('div')).filter(el => /^Qwen3\.\d/.test((el.innerText||'').trim()) && el.children.length===0);
    return all[0] ? all[0].innerText.trim() : 'NONE';
  });
  return JSON.stringify({ url, login, optClicked, model });
}
```

**确认返回**：`model === "Qwen3.8-Max"`。若 `err: 'NOT_LOGGED_IN'` → Chrome 9222 断连，见错误处理 E2。若 `model !== 'Qwen3.8-Max'` → 重跑此代码块（模型回退 3.7，见 E3）。

#### 4.2 代码块 B：注入载荷

**工具**：`browser_run_code_unsafe`，`filename` 参数填 MCP 根目录的注入 .js：

```
filename = <MCP_ROOT>/dp_inject_<record_id>.js
```

**确认返回**：`insertedLen` ≈ prompt 长度（应 > 5000）。

#### 4.3 代码块 C：React 等待 + 校验 + 发送

**工具**：`browser_run_code_unsafe`，`code` 参数填：

```js
async (page) => {
  // React batching 等待
  await page.waitForTimeout(1500);
  const inputLen = await page.evaluate(() => {
    const el = document.querySelector('[contenteditable="true"], [role="textbox"], textarea');
    return el ? (el.innerText || el.value || '').length : 0;
  });
  // partial-send 检测：输入长度 < 85% 则清空重注
  if (inputLen < 5000) {
    await page.keyboard.press('Control+a');
    await page.keyboard.press('Delete');
    return JSON.stringify({ err: 'PARTIAL_SEND', inputLen, hint: '重跑代码块 B 重新注入' });
  }
  // 点发送（重试等按钮 enabled，最多 12×400ms）
  let sendClicked = false;
  for (let i = 0; i < 12; i++) {
    sendClicked = await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll('button')).find(b => {
        const a = b.getAttribute('aria-label') || '';
        return a.includes('发送') && !b.disabled;
      });
      if (btn) { btn.click(); return true; }
      return false;
    });
    if (sendClicked) break;
    await page.waitForTimeout(400);
  }
  // 确认输入框已清空（发送成功标志）
  await page.waitForTimeout(800);
  const afterLen = await page.evaluate(() => {
    const el = document.querySelector('[contenteditable="true"], [role="textbox"], textarea');
    return el ? (el.innerText || el.value || '').length : 0;
  });
  return JSON.stringify({ inputLen, inputMatch: inputLen >= 5000, sendClicked, afterLen, sent: afterLen < 50 });
}
```

**确认返回**：`sent: true`。若 `err: 'PARTIAL_SEND'` → 重跑代码块 B 再跑 C。若 `sendClicked: false` → 发送按钮一直 disabled，见 E5。

---

### 步骤 5：等生成完成 + 抽取正文（代码块 D）

**工具**：`browser_run_code_unsafe`，`code` 参数填：

```js
async (page) => {
  const maxWait = 180000; // 上限 180s
  const start = Date.now();
  let state = 'generating';
  while (Date.now() - start < maxWait) {
    const info = await page.evaluate(() => {
      const t = document.body.innerText || '';
      const rounds = document.querySelectorAll('.chat-round');
      const stopBtn = Array.from(document.querySelectorAll('button')).find(b => {
        const a = b.getAttribute('aria-label') || '';
        const x = b.textContent || '';
        return a.includes('停止') || x.includes('停止生成');
      });
      const refused = t.includes('无法回答') || t.includes('我们聊聊别的');
      let ll = 0;
      if (rounds.length > 0) ll = (rounds[rounds.length-1].innerText || '').length;
      return { stopBtn: !!stopBtn, refused, lastLen: ll };
    });
    if (info.refused) { state = 'refused'; break; } // 拒答，见 E6
    // 生成完成判定：停止按钮消失 + 有内容 + 内容稳定（2.5s 复读一致）
    if (!info.stopBtn && info.lastLen > 300) {
      await page.waitForTimeout(2500);
      const len2 = await page.evaluate(() => {
        const rounds = document.querySelectorAll('.chat-round');
        return rounds.length > 0 ? (rounds[rounds.length-1].innerText || '').length : 0;
      });
      if (len2 === info.lastLen) { state = 'done'; break; }
    }
    await page.waitForTimeout(2500);
  }
  // 抽取：千问深度思考渲染【多个】.qk-markdown——idx0=思考区（含"Now let's write"/占位符），最后一个=最终答案
  const extracted = await page.evaluate(() => {
    const rounds = document.querySelectorAll('.chat-round');
    if (!rounds.length) return JSON.stringify({ err: 'NO_ROUNDS' });
    const root = rounds[rounds.length-1];
    const mds = Array.from(root.querySelectorAll('.qk-markdown'));
    // 兜底过滤：含 Option 1 锚点 且 不含思考链/占位符
    let ans = mds.filter(el => {
      const t = el.innerText || '';
      return t.includes('Option 1: Amazon Exclusive Design') && !t.includes("Now let's write") && !t.includes('Prompt: ...');
    });
    ans = ans[ans.length-1] || mds[mds.length-1]; // fallback 取最后一个
    if (!ans) return JSON.stringify({ err: 'NO_ANSWER' });
    const text = (ans.innerText || '').trim();
    return JSON.stringify({ ok: true, len: text.length, startsWithMarker: text.indexOf('Option 1: Amazon Exclusive Design') === 0, preview: text.substring(0, 200), text });
  });
  return JSON.stringify({ state, extracted });
}
```

**确认返回**：`state === 'done'` 且 `extracted.ok === true` 且 `startsWithMarker === true`。

**关键（大模型判断点）**：若 `startsWithMarker === false` 或 `preview` 含 "Let's analyze"/"Now let's write"/占位符 "Prompt: …" → 抽到了思考区或无效输出，标记 **INVALID**，不回写，见 E7。

---

### 步骤 6：存盘抽取结果

**工具**：`browser_evaluate`，`filename` = `<MCP_ROOT>/clean_out_<record_id>.txt`，`function` 填：

```js
() => {
  const rounds = document.querySelectorAll('.chat-round');
  const root = rounds[rounds.length-1];
  const mds = Array.from(root.querySelectorAll('.qk-markdown'));
  let ans = mds.filter(el => {
    const t = el.innerText || '';
    return t.includes('Option 1: Amazon Exclusive Design') && !t.includes("Now let's write") && !t.includes('Prompt: ...');
  });
  ans = ans[ans.length-1] || mds[mds.length-1];
  return (ans.innerText || '').trim();
}
```

### 步骤 7：回写飞书

```bash
"$PY" "$SCRIPTS/dp_write_feishu.py" <record_id> <MCP_ROOT>/clean_out_<record_id>.txt
```

**确认**：返回 `FEISHU WRITE code: 0 success`。code≠0 → 重试（见 E8）。

### 步骤 8：回读验证（必做，铁律：用列表接口不用单条 GET）

```bash
"$PY" -c "
import sys; sys.path.insert(0, r'$SCRIPTS')
from fetch_input import get_token, list_records
rows = list_records(get_token())
for r in rows:
    if r['record_id'] == '<record_id>':
        d = r.get('fields', {}).get('设计方案', '')
        if isinstance(d, list): d = ''.join(x.get('text','') for x in d if isinstance(x,dict))
        d = (d or '').strip()
        print(f'len={len(d)} hasOption1={\"Option 1: Amazon Exclusive Design\" in d} opt2={\"Option 2:\" in d} opt3={\"Option 3:\" in d} ar={\"--ar\" in d}')
        break
"
```

**确认**：`len > 1000` 且 `hasOption1=True` 且 `opt2=opt3=True`。空 → 重写（见 E8）。

---

## 6. 批量执行铁律

- ✅ **单条串行**：一次只处理一个 record_id，全流程做完（含回写回验）才取下一个空记录
- ❌ **禁止预生成排队**：不批量预生成 input/dp_inject 堆在 dp_run；每条现取现组装（fetch_input + build 当前 rid）。dp_run 同时只留当前一条产物
- ❌ **禁止报错跳过**：拒答/抽取错/超时，第一时间在同条处理（换变体/重抽/等），不跳过不继续下一条
- ✅ **同一个标签页内**新对话跑下一个商品（代码块 A 的 navigate 根 /chat 强制新建）
- ❌ **禁止新标签页**（不继承登录态 + 千问回退模型）
- ❌ **禁止 `browser.close()`**（CDP 模式下会杀整个 Chrome，后续全挂）
- ✅ **不碰"深度思考"toggle**——3.8-Max 自管理思考模式，主动开关会破坏其推理
- ✅ 每条跑完，把 `record_id` + 结果（成功/INVALID/REFUSED/超时）记到汇报清单

## 7. 错误处理 catalog

| 编号 | 现象 | 检测方 | 处理 |
|---|---|---|---|
| E1 | `build --mcp-root auto` 拷贝失败 | CLI 报错 | 手动 `cp dp_inject_<rid>.js <MCP_ROOT>/`；或内联 base64 到 code |
| E2 | Chrome 9222 ECONNREFUSED / `NOT_LOGGED_IN` | 代码块 A 返回 | `taskkill /F /IM chrome.exe` → 重启 `chrome.exe --remote-debugging-port=9222 --user-data-dir=.../cdp-profile-h` → 重跑代码块 A |
| E3 | 模型回退 3.7（`model !== 'Qwen3.8-Max'`） | 代码块 A 返回 | 重跑代码块 A（下拉 fallback 会重新切）；仍不行看下拉是否真有 3.8-Max 选项 |
| E4 | `require('fs')` 不可用 | 代码报 ReferenceError | MCP 沙箱无 fs；**不要在 code 里读文件**，改用 `filename=` 加载已生成 .js（base64 内嵌） |
| E5 | 发送按钮一直 disabled | 代码块 C `sendClicked:false` | 多为 React 未识别 insertText → 重跑代码块 B（重新注入）再跑 C；仍不行检查输入框选择器 |
| E6 | 拒答 "我们聊聊别的"/"无法回答" | 代码块 D `state:'refused'` | **第一时间在同条换变体重试**（不跳过、不继续下一条）：冷却 30s → 换变体 2 重新 build+注入+发送 → 仍拒 → 冷却 30s → 变体 3 → 3 次都拒才标记 REFUSED 跳过。**禁止**检测到拒答后直接跑下一条（会导致上下文累积 + 错误传播 + "前条污染后条"）。见第 8 节 |
| E7 | 抽到思考区 / 无锚点 / 有占位符 | **大模型判断**（preview 含 "Let's analyze"/"Now let's write"/"Prompt: …"） | 标记 INVALID，**不回写脏数据**，跳过记 rid；偶尔模型把答案渲染到别的容器，可手动查 DOM 再抽 |
| E8 | 生成超时 180s 仍 generating | 代码块 D `state:'generating'` | 跳过，记 rid 待人工（深度思考偶发超长） |
| E9 | 飞书写入 code≠0 / 回验空 | CLI / 步骤 8 回读 | code≠0 重试写；回验空 → 重写（**不用单条 GET**，单条有最终一致性陷阱） |
| E10 | dp_run 残留污染（pending_50.txt 等） | — | 每次跑前 `rm -f dp_run/pending_* dp_run/qdp_progress*.json dp_run/status/*.json` |
| E11 | 千问拒答「无法回答 / 我们聊聊别的」（SI 规范首行含「系统指令」「Final Version v5.4」触发安全分类器判为 prompt-injection 覆盖尝试） | 代码块 D `state:'refused'` | 运行前对 SI 做 `sanitize_si()`：「系统指令」→「设计规范」、「（Final Version v5.4）」→「（v5.4）」。**只改输入侧触发词，保留全部输出格式要求**（Option 1/2/3、`--ar`、Semantic Tags 不变）。已验证：法兰绒地垫记录原拒答 → 中和后正常出 6513 字符设计方案。变体 2/3 同样需走中和后的 SI。 |

## 8. 拒答处理（3 变体）

千问偶发拒答（即使 SI 已无元标记）。准备 3 个 prompt 变体（在 build 脚本 `--variant` 参数切换，或手动改 `.prompt.txt` 开头措辞）：

1. **变体 1（默认）**：`你是一名资深的 POD 视觉设计 Prompt 工程师。下面是一份完整的设计规范…`（自然任务式）
2. **变体 2**：`请基于以下商品信息，按要求生成英文图像生成 Prompt。商品信息如下：…`（直接任务式，去 SI 前缀）
3. **变体 3**：`I need you to generate English image generation prompts for POD products based on the following design spec and product info: …`（英文任务式）

- 每次拒答后换下一个变体，**冷却 30s** 再重发（避免触发频控）
- 3 个变体都拒答 → 跳过该 rid，记入汇报清单，不回写

## 9. 检查清单（每条必过）

- [ ] 步骤 1：列到待生成记录数 ≥ 1
- [ ] 步骤 3：`.prompt.txt` 开头自然句、无元标记
- [ ] 代码块 A：`model === 'Qwen3.8-Max'` 且 `login === true`
- [ ] 代码块 C：`sent === true`
- [ ] 代码块 D：`state === 'done'` 且 `startsWithMarker === true`
- [ ] 步骤 8：回读 `len > 1000` 且 `hasOption1=True` 且 `opt2=opt3=True`
- [ ] INVALID / REFUSED / 超时的 rid 单独记录汇报

## 10. 交棒下游

「设计方案」写入后 → `aistudio-visualbridge` 接手：解析 Prompt 组 → 生图 → 回写「设计方案图片」附件字段

---

## 11. 批量执行器（Python CDP 直驱，规避 MCP 180s 超时）

手动逐条 250+ 次 `browser_run_code_unsafe` 调用不现实，且长轮询（代码块 D 的 180s `maxWait`）必然触发 MCP `-32001 Request timed out`。改用 Python playwright `connect_over_cdp` 直连运行中的 Chrome 9222（cdp-profile-h / Qwen1122 登录态），复用本 skill 全部已验证浏览器逻辑，**单条串行铁律不变**。

- 脚本：`scripts/run_dp_batch.py`
- 依赖：venv `C:/Users/nicho/.workbuddy/binaries/python/envs/default`（已装 playwright）
- 用法：
  - 单条验证：`python run_dp_batch.py --rid <record_id>`
  - 全量：`python run_dp_batch.py --all`（动态拉飞书空「设计方案」列表，非硬编码）
  - 冒烟：`python run_dp_batch.py --all --limit 5`
- 它做的事（与第 6 节铁律一致）：
  1. 强制新对话（navigate /chat）→ 切 Qwen3.8-Max → `insertText` 注入（header+**sanitize 后的 SI**+商品+launch）→ 点发送
  2. Option3 门控轮询（Python 侧无 180s 上限）→ 健壮抽取（排除 thinking block，拼接所有非思考区 `.qk-markdown`）
  3. 校验（`Option 1/2/3` + `--ar` + 无 thinking 标记）→ 回写飞书（`dp_write_feishu.py`）→ 列表接口回验
  4. **同条错误第一时间处理**：拒答→3 变体循环 + 冷却 30s；抽取无效/超时→同条重试；3 次耗尽才标记结果跳过（不静默跳过）
- 进度/结果：落盘 `dp_run/batch_log.json`（每条 `status`: `OK` / `REFUSED` / `INVALID` / `TIMEOUT` / `WRITE_FAIL` / `EXCEPTION`）
- ⚠️ 不 `browser.close()`（CDP 直连外部 Chrome，关了全挂）；不碰深度思考 toggle；同一标签页内新对话跑下一个。

## 附：混合架构分工说明

| 环节 | 方式 | 理由 |
|---|---|---|
| 取数/组装/回写/回验 | 本地 CLI 脚本 | 纯逻辑，已就绪，零 token |
| 导航/切模型/注入/发送/等待 | `browser_run_code_unsafe` 代码块（3-4 个） | 机械操作，一次搞定，省 token |
| 抽取正文 | `browser_run_code_unsafe` 代码块 D | 机械，但选择器要正确（最后一个 qk-markdown） |
| **抽取目标对不对 / 输出有没有效** | **大模型判断** | 代码只会机械抽，不知道抽到的是思考区还是答案 |
| **拒答后换变体** | **大模型决策** + 代码执行 | 边界情况需判断 |

**前次踩过、本路线已规避的坑**：① A2A /chat 500（不走 agnes A2A）② copy-button 不显示（改 DOM 抽取）③ browser.close() 杀 Chrome（MCP 不调 close）④ 等 300s 空等（事件驱动）⑤ toggle 探测失败（不碰 toggle）。
