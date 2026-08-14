# 千问设计方案生成器（qianwen-design-plan）

> 🔒 **LOCKED · v1.0 定稿版 · 2026-08-14 · 不要再改** · v5.4 协议
>
> **傻瓜式说明书** · 照抄执行即可，不要修改 SKILL.md

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
| 飞书表2 已配置 | ✅ Base `ONy9bZ0oFaaiSEsf4ggcs61enRc` / Table `tbl75glY29VulRLm` |
| 国内 IP | ✅ 直连 qianwen.com 无地域限制 |

## 4. 固定路径（复制粘贴用，别改）

```bash
PY="C:/Users/nicho/.workbuddy/binaries/python/versions/3.13.12/python.exe"
SKILL="C:/Users/nicho/.workbuddy/skills/multi-agent-sop/qianwen-design-plan"
SCRIPTS="$SKILL/scripts"
```

## 5. 执行步骤（照抄）

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
- `dp_inject_<record_id>.prompt.txt` — 纯文本提示词（**人工把关**）

**⚠️ 把关**：打开 `.prompt.txt`，确认：
- ✅ 开头是自然句「你是一名资深的 POD…」
- ✅ 全文**无** `【角色设定】` / `【启动指令】` 元标记（千问会判为 prompt-injection 拒答）

### 步骤 4：千问网页端执行（MCP 剧本）

> 每个 `browser_*` 工具都是 `mcp__playwright-qwen__browser_*`

#### 4.1 开新窗口 + 确认登录

```
browser_navigate  url=https://qianwen.com/chat
browser_snapshot
```

**确认**：页面含 `Qwen1122`（已登录），模型默认 `Qwen3.7-千问`

#### 4.2 切模型到 Qwen3.8-Max

```
browser_click  target=<模型选择器元素>      # 显示 "Qwen3.7-千问" 的那块
browser_evaluate  function=() => { const els=Array.from(document.querySelectorAll('div,li')); const t=els.find(el=>(el.innerText||'').trim()==='Qwen3.8-Max'&&el.children.length<=1); if(!t)return 'NOT_FOUND'; t.click(); return 'CLICKED'; }
browser_evaluate  function=() => { const all=Array.from(document.querySelectorAll('div')).filter(el=>/^Qwen3\.\d/.test((el.innerText||'').trim())&&el.children.length===0); return all[0]?all[0].innerText.trim():'NONE'; }
```

**确认**：第二个 evaluate 返回 `Qwen3.8-Max`

#### 4.3 注入载荷

```
browser_run_code_unsafe  filename=<MCP根目录>/dp_inject_<record_id>.js
```

> MCP 根目录 = `build_design_plan_inject.py` 自动打印的路径（形如 `C:/Users/nicho/.workbuddy/logs/mcp-runtime/custom-mcp_playwright-qwen-XXXX/.playwright-mcp/...`）

#### 4.4 发送 + 等待

```
browser_click  target=<发送按钮>           # aria-label 含 "发送"
browser_wait_for  time=60
browser_evaluate  function=() => { const t=document.body.innerText; return JSON.stringify({refused:t.includes('无法回答')||t.includes('我们聊聊别的'), generating:t.includes('正在思考')}); }
```

**确认 `refused:false`**

#### 4.5 抓取纯净设计正文

> v5.4 协议保证模型输出即纯英文结构化正文，**复制即得，无须清洗**

```
browser_evaluate  filename=<MCP根目录>/clean_out_<record_id>.txt  function=() => {
  const rounds=document.querySelectorAll('.chat-round');
  const root=rounds[rounds.length-1];
  if(!root) return 'NO_ROOT';
  const md=root.querySelector('[class*="qk-md"]') || root;
  return (md.innerText||'').trim();
}
```

### 步骤 5：回写飞书

```bash
"$PY" "$SCRIPTS/dp_write_feishu.py" <record_id> <MCP根目录>/clean_out_<record_id>.txt
```

### 步骤 6：回读验证（必做）

```bash
"$PY" "C:/Users/nicho/.workbuddy/skills/multi-agent-sop/aistudio-visualbridge/scripts/feishu_products_io.py" show <record_id>
```

**确认**：回读 `设计方案` 字段含刚生成的英文文本

## 6. 批量执行铁律

- ✅ **同一个标签页内**点「新对话」跑下一个商品
- ❌ **禁止新标签页**（新标签不继承登录态 + 千问会回退模型）

## 7. 失败恢复速查

| 现象 | 原因 | 处理 |
|---|---|---|
| 拒答「我们聊聊别的吧」 | SI 残留 `【角色设定】` 元标记 | 重做步骤 3（自然任务式包装）|
| 正文混入中文/SI 回显 | 用 `document.body.innerText` 整页抓取 | 改用**复制按钮**或步骤 4.5 的 evaluate |
| `File access denied` | `.js` 路径不在 MCP 根目录 | 用 `--mcp-root auto` 自动拷贝 |
| 发送按钮 disabled | React 未识别 insertText | 重试 `browser_run_code_unsafe`；仍不行看输入框真实选择器 |
| 模型回到 3.7 | 新开 `/chat` 窗口默认 3.7 | 每次开新窗口都重做步骤 4.2 |

## 8. 检查清单

- [ ] 步骤 1：列到待生成记录数 ≥ 1
- [ ] 步骤 2：`input_<record_id>.txt` 已生成
- [ ] 步骤 3：`.prompt.txt` 开头是自然句、**无**元标记
- [ ] 步骤 4.2：模型确认 = `Qwen3.8-Max`
- [ ] 步骤 4.4：`refused:false`
- [ ] 步骤 5：CLI 返回成功
- [ ] 步骤 6：回读飞书 `设计方案` 字段非空

## 9. 交棒下游

「设计方案」写入后 → `aistudio-visualbridge` 接手：解析 Prompt 组 → 生图 → 回写「设计方案图片」附件字段
