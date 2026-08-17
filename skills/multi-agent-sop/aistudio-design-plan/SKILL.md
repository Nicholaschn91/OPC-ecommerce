# AI Studio 设计方案生成器（aistudio-design-plan，回退通道）

> 🔒 **LOCKED · v1.0 定稿版 · 2026-08-14 · 不要再改**
>
> **傻瓜式说明书** · 半自动协作 v4 · 照抄执行即可，不要修改 SKILL.md
>
> **本 skill 走半自动协作模式**：脚本做最大化窗口 / SI 探针 / 输入 / Run / 监控 / 抓取，**用户只点 Rerun**。

## 1. 这个 skill 做什么

从飞书「商品基础信息」**生成**英文设计方案（v5.4 协议：Option 1 Amazon / Option 2 eBay / Option 3 Etsy + 视觉 Prompt），落盘到 `outputs/` 目录。是 `qianwen-design-plan` 的**回退通道**（千问故障时用）。

**模型**：Google AI Studio 网页端 `gemini-3.1-pro-preview`（用户硬性要求，flash 已被禁用）

## 2. 什么时候用

- 千问主通道跑挂了
- 想用 Gemini 系列出方案
- 收到触发词：「跑 AI Studio」「用 Gemini 设计」「回退通道」

## 3. 半自动铁律（用户 8-14 05:32 最终确认）

> ⚠️ **只点 Rerun**！其他全归脚本。

| 操作 | 脚本 | 用户 |
|---|---|---|
| 最大化窗口 | ✅ | |
| 跳 Playground 新对话 | ✅ | |
| 探针 SI 状态 | ✅（**不写入**） | |
| 切换 System instructions | | ✅（切 POD-印花底稿-v5.4 后**自己关掉**编辑面板）|
| 写入商品内容 | ✅ | |
| Ctrl+Enter Run | ✅ | |
| Ctrl+Enter 没触发（≤1） | 停止等待 | ✅（手动点 Run）|
| 服务端 internal error | 写 `last_error.json` 通知 | ✅（点「Rerun this turn」）|
| 抓取 + 落盘 | ✅ | |

**绝对禁止**：脚本**不**写入 SI 提示词（会跟 localStorage 命名条目重复，TA 得手动删）

## 4. 前置

| 项 | 状态 |
|---|---|
| 用户的 Chrome 跑在 9224 调试端口（与 `browser-aistudio` 同浏览器） | ✅ `chrome --remote-debugging-port=9224` |
| `browser-aistudio` MCP 已连接 | ✅（你已 Trust） |
| AI Studio 已登录 `leiyuzhe007@gmail.com` | ✅ |
| 浏览器已**最大化** | ✅（脚本会通过 CDP `Browser.setWindowBounds` 强制最大化）|
| System instructions 命名 SI `POD-印花底稿-v5.4` | 用户在浏览器里手动切 |

## 5. 固定路径

```bash
NODE="C:/Users/nicho/.workbuddy/binaries/node/versions/22.22.2/node.exe"
PY="C:/Users/nicho/.workbuddy/binaries/python/versions/3.13.12/python.exe"
SKILL="C:/Users/nicho/.workbuddy/skills/multi-agent-sop/aistudio-design-plan"
SCRIPTS="$SKILL/scripts"
VBIO="C:/Users/nicho/.workbuddy/skills/multi-agent-sop/aistudio-visualbridge/scripts/feishu_products_io.py"
```

## 6. 执行步骤（照抄）

### 步骤 1：列待生成记录

```bash
"$PY" "$SCRIPTS/fetch_input.py" --list-empty
```

**预期**：每行 `recXXX | 商品名`，末尾 `共 N 条待生成设计方案`

### 步骤 2：取商品信息 → 落盘

```bash
"$PY" "$SCRIPTS/fetch_input.py" <record_id> -o "$SKILL/dp_run/input_<record_id>.txt"
```

### 步骤 3：（用户）切 SI + 关面板

在浏览器里手动：
1. 打开 System instructions 卡片
2. 下拉选 `POD-印花底稿-v5.4`（或粘贴 v5.4 文本到 SI textarea）
3. **关掉 SI 编辑面板**（按 Escape 或点别处）

### 步骤 4：（脚本）跑半自动

```bash
"$NODE" "$SCRIPTS/half_auto.cjs" --file "$SKILL/dp_run/input_<record_id>.txt"
```

**脚本会自动做**：
1. CDP 最大化窗口
2. 跳 Playground（确保在 `prompts/new_chat`）
3. 探针 SI 状态（**只读**，不写入）
4. 写入主输入框（fetch + UTF-8 decode）
5. Ctrl+Enter Run
6. 监控循环（5s 探针）

### 步骤 5：（用户）Rerun 兜底

**仅当** `outputs/last_error.json` 出现时，**你**在浏览器里点 model 回答区的 **「Rerun this turn」** 按钮（**不是你发送的那条** prompt 气泡，是**模型回答**那一侧的 Rerun 按钮）。

> 提示：日志里 `>>> USER_NOTIFY: 请手动点 "Rerun this turn" <<<` 也会提示你

### 步骤 6：自动落盘

v5.4 答案出现 → 脚本自动抓取 → 落盘到 `outputs/half_auto_<record_id>_<时间戳>.md` → present_files

## 7. 监控文件

| 文件 | 含义 |
|---|---|
| `outputs/si_required.json` | SI 不含 v5.4 时通知你去切 |
| `outputs/last_error.json` | 服务端拒绝，请点 Rerun |
| `outputs/half_auto_<rid>_<时间>.md` | v5.4 答案落盘（成功后）|

## 8. 失败恢复速查

| 现象 | 原因 | 处理 |
|---|---|---|
| `last_error.json` 频繁出现 | 服务端把 CDP 协议层识别成 bot | 这是 Google 服务端限制，**没办法**绕；只能你点 Rerun |
| Ctrl+Enter 没触发 Run（turnCount≤1）| SI 面板没关 / 焦点在别处 | 脚本会写 `si_required.json` 通知你**手动点 Run** |
| SI 面板是空的 | 浏览器 localStorage 有命名 SI 但 UI 不显示 | 手动粘贴 v5.4 文本到 SI textarea，然后自己关面板 |
| 下拉 listbox 是空的 | localStorage 命名 SI 格式问题 | 同上，**手动粘贴** 是最稳的路 |
| 窗口没最大化 | CDP Browser.setWindowBounds 失败 | 自己手动最大化（Win+↑） |

## 9. 检查清单

- [ ] 步骤 1：列到待生成记录数 ≥ 1
- [ ] 步骤 2：`input_<record_id>.txt` 已生成
- [ ] 步骤 3：你在浏览器里切好 SI、关掉面板
- [ ] 步骤 4：脚本跑起来，日志显示 `TURN_CREATED` 或 `USER_NOTIFY`
- [ ] 步骤 5（如需）：点 Rerun
- [ ] 步骤 6：v5.4 答案 .md 落盘

## 10. 已实测记录

- ✅ 2026-08-14：recvoTqydUWs4s（6 片装餐盘垫，方向 B）4430 字符
- ✅ 2026-08-14：recvoVNG78DZLn（圆形 PVC 挂钟，方向 A）6424 字符
- ✅ recvoTp9ggS7qZ（4 片装）本地生成过但未回写飞书

> **结论**：半自动协作稳定可跑，端到端 PASS。完全自动化已被 Google 服务端禁止（任何 CDP 客户端一律 permission denied）。
