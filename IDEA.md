---

## 产品愿景：你的 AI 跨境电商全案生成引擎（Local-First OPC）

这是一款以**本地 Agent 运行时 + 本地词库**为底座、「一人公司（OPC）」模式的跨境 listing 生成应用。由**主控 Agent（Boss）**指挥 N 个具备**独立边界**的"数字员工（子 Agent）"，在保障**合规底线与数据主权**的前提下，为你打造一个**极简交互、复杂后台、优雅降级**的 listing 全案生成闭环。

用户只需在飞书多维表格里维护商品基础信息、在对话里说一句"生成 listing"，后台 N 个 Agent 就像一支真实团队一样**异步协作、自动流转、出错自愈**——但最终每一稿都经过你的人工闸门确认，绝不让 AI 幻觉直接落到线上。

---

## 一、本地环境下的最优通信机制建议

对于我们的 SOP，同样**摒弃复杂的分布式微服务架构**（gRPC、Kafka、远程消息队列等）。我们的"本地"包含：① 本地运行的子 Agent（hermes/WorkBuddy 进程内上下文 / 独立 Agent 进程），② 本地 SQLite 词库（`keyword_database.db` / `risk_keywords.db`），③ 飞书云表格作为持久化共享状态中心。最友好的通信机制如下：

### 首选方案：本地事件总线（Local Event Bus / 事件驱动）**[建议]**

- **机制**：采用发布/订阅（pub/sub）模式。**主控 Agent 作为事件路由器**，子 Agent 订阅自己关心的阶段事件，而非被主控显式"挨个唤醒"。
- **推荐事件名（对应我们流水线）**：
  - `spu_fetched`（采集完成，00_Scraper 发布）
  - `proposal_ready`（Router 战略提案产出，01_Router 发布，附 `CRITICAL_STOP` 闸门）
  - `draft_done`（某平台初版文案完成，02_SEO / 05_Etsy / 06_eBay 发布）
  - `visual_final`（终版+视觉 Prompt 完成，03_Visual 发布）
  - `risk_hit`（合规扫描命中致命级，任意 Agent 发布 → 触发熔断）
  - `keyword_request`（子 Agent 向 keyword-grader 请求取词）
- **本地实现**：
  - 轻量：单进程内 `asyncio.Queue`（主控与子 Agent 同进程时）；
  - 跨进程：本地嵌入式中间件（ZeroMQ / NATS），或**文件系统即队列**（每个事件写一个 JSON 落本地 `events/` 目录，订阅方轮询/监听）。
- **优势**：完全解耦——子 Agent 只需监听事件，无需知道主控与其他 Agent 的存在；内存级/本地磁盘通信，延迟极低；新增 Agent 只需订阅新事件，不改动既有调用链。
- **与人工闸门兼容**：`proposal_ready` / `draft_done` 等事件在**等待用户"确认"期间挂起**，确认后由主控重新派发，事件总线天然支持这种"暂停-恢复"。

### 备选方案：本地共享存储（Shared State / File System as a Queue）**[现状为主]**

- **机制**：将任务状态持久化到**飞书多维表格**（我们的权威共享状态中心）+ 本地 SQLite（`keyword_database.db` 只读词库、`keyword_clusters.db` 聚类结果）。
- **优势**：**天然具备持久化与跨设备能力**。子 Agent 崩溃重启后，可从飞书"内容状态"字段（`待确认 → 初版已完成 → 全案完成`）与本地快照恢复未完成任务，非常适合我们的场景。
- **现状说明**：我们当前**实际就是以飞书表格为共享状态中心**——每个 Agent 严格按 `AGENT_BOUNDARIES.md` 的"飞书写权限矩阵"读写各自字段，这本身就是"共享存储"模式，且已支持断点续传。

### 通信协议：轻量 JSON / YAML，避免过度设计 **[现状]**

- **跨 Agent 主数据流**：`SPU_CONTEXT` 采用 **YAML**（结构化、人类可读、易于人工复核战略提案）。
- **工具/API 载荷**：`keyword_tool.py` 取词、`--risk-check` 扫词返回 **JSON**；飞书 API 交互亦为 JSON。
- **不引入 Protobuf**：我们的消息结构相对固定、需要人工可读，YAML/JSON 足够，避免序列化层的过度工程。

---

## 二、本地 SOP 的安全与容错设计补足

在本地环境中，安全主要防范**合规事故与数据越权**，容错主要防范**单点卡死与脏数据扩散**。我们已有的 `AGENT_BOUNDARIES.md` 已覆盖大部分，下面按参考文结构补齐对照。

### 安全设计（Security）

**① 最小权限原则（Least Privilege）**[现状]**

每个子 Agent 拥有**独立的飞书字段级写权限**，绝不越权。映射参考文的"沙箱隔离"：

| Agent | 读权限边界 | 写权限边界（飞书字段级） |
|---|---|---|
| 00_HiCustom_Scraper | 仅目标商品页面 DOM/API | 仅 Base A 输入字段；**不读飞书其他、不写战略/文案** |
| 01_Router | Base A 输入字段 + keyword_tool | 仅战略字段 / 平台 / 赛道 / VISUAL_HANDOFF |
| 02_SEO | 仅 `SPU_CONTEXT` YAML | 仅 Amazon 初版字段 |
| 03_Visual | 仅 VisualBridge + 初版 | 仅 Amazon 终版 + 视觉 Prompt + A+ |
| 04_Ads | 仅初版标题/ST/痛点 | 仅广告方案 |
| 05_Etsy / 06_eBay | 仅 `SPU_CONTEXT` YAML | 仅本平台初版/终版字段 |
| keyword-grader | 仅 `keyword_database.db`（只读） | 仅主控确认后的品类/分级字段 |

> 越权即被主控拦截、清除脏数据、重跑（见 `AGENT_BOUNDARIES.md` 边界违规处理）。

**② 敏感数据隔离**[建议强化]

- **凭据隔离（现状已做）**：飞书 App ID/Secret、NVIDIA_API_KEY、HiCustom 会话态均存于**环境变量 / `.env`**，且 `.gitignore` 已屏蔽 `.env`，**绝不入仓库**。
- **PII 隔离（建议）**：商品数据本身多为公开售卖信息，少有个人敏感数据；但若未来接入用户级经营数据（利润、私域客户），建议对对应字段做**本地加密存储**（如 SQLCipher 或字段级加密），并在飞书侧仅保留脱敏视图。

**③ 主控审批 / 确认机制（Human-in-the-Loop）**[现状，且是铁律]

- **确认门禁**（`AGENT_BOUNDARIES` 全局铁律 #5）：修改 Skill / Agent / 配置**必须用户确认**后执行。
- **CRITICAL STOP**：Router 提案后、各平台初版后、Etsy 每阶段后，**必须等待用户"确认"**才能继续。
- **合规熔断**（铁律 #2）：触碰法律/平台红线立即中止，一级风险词命中→直接熔断禁止输出。**这是防止 AI 幻觉导致合规灾难的核心闸门。**

### 容错设计（Fault Tolerance）

**① 优雅降级与重试（Retry & Fallback）**[现状部分 + 建议补强]

- **三振出局**（铁律 #1）：任何任务连续失败 3 次 → 立即中断、输出错误详情、等待人工介入，**禁止无限重试**。
- **语义层降级**（现状）：百炼 qwen 不可用时回退 Hy3（thinking）；我们新封装的 GLM-5.2（NVIDIA NIM）作为语义层第二选择，同样走"不可用时回退"策略。
- **建议补强——主控超时兜底**：当某子 Agent（如 02_SEO 长文案生成）因复杂计算/外部 API 卡死时，主控应有**超时机制（Timeout）**。超时后自动降级为该 SPU 的"上一检查点快照重跑"或"基础模板兜底"，确保当次 listing 任务不整体挂死。

**② 独立进程 / 线程隔离**[现状缺口，建议演进]

- **参考文要求**：子 Agent 必须在独立线程/进程中运行，任一崩溃不影响全局，主控捕获异常并自动重启。
- **我们现状**：子 Agent 目前以**上下文提示词**形式运行于单一 WorkBuddy 会话（主控加载 `agents/*.md` 后顺序执行），并非独立隔离进程。**隔离性较弱**——若会话级上下文污染或主控自身异常，会影响整条流水线。
- **建议演进**：将每个子 Agent 封装为**独立 Agent 进程/隔离运行时**（如 WorkBuddy 的 subagent / 独立 skill 调用），主控通过事件总线与其通信；任一 Agent 崩溃，主控捕获异常、清除其半完成状态、自动重启该 Agent，不波及全局。

**③ 任务幂等性（Idempotency）**[现状已做]

- **关键词冻结快照**（`listing_kw_snapshot` 表）：初版文案取词后 `--freeze` 锁定，重发指令不会产生重复取词。
- **部署追踪**（`keyword_deployments` 表）：每个实际使用的关键词单独 log，复盘时 `report/unused/replace` 可对照，原记录保留为历史。
- **确定性计算**：T1-T5 分级由 `process_dual.py` 确定性算出，keyword-grader 只解释不评分——**同词两次结果一致**，天然幂等，不依赖 LLM 概率输出。

---

## 三、完整版：本地多 Agent SOP 架构设计文档

### 本地通信与协同机制

- **通信架构**：采用**本地异步事件总线（Local Event Bus）**（见第一节，当前为"主控显式唤醒 + 飞书状态中心"过渡态，建议演进为 pub/sub）。主控 Agent 作为事件路由器，子 Agent 通过订阅阶段事件（`spu_fetched` / `proposal_ready` / `draft_done` / `visual_final` / `risk_hit`）进行异步协作。
- **状态同步**：以**飞书多维表格为持久化共享状态中心** + **本地 SQLite 为只读词库**。所有 Agent 通过读写各自字段 / 取词接口来同步进度，**天然支持断点续传与崩溃恢复**（飞书"内容状态"字段即为检查点）。

### OPC 架构设计与子 Agent 分工

**🧠 主控大脑（Orchestrator / Boss）**
- **职责**：全局意图识别、SOP 编排、超时监控与异常兜底、合规门禁。
- **安全控制**：拦截高危指令（一级风险词 / 合规红线）执行 Human-in-the-Loop 确认；监控各子 Agent 健康状态，异常节点自动重启（演进方向）。
- **对应**：主控 Agent（WorkBuddy / Senior Developer）。

**📡 采集 Agent（Scraper Agent）**
- **独立边界**：专注多源商品页解析，沙箱隔离，**不读飞书其他字段、不生成文案**。
- **对应功能**：00_HiCustom_Scraper。
- **工作流**：解析 HiCustom 页面 DOM/API → 写入飞书 Base A → 发布 `spu_fetched` 事件。具备回读校验（幂等，防止脏录入）。

**🔀 路由 / 战略 Agent（Router Agent）**
- **独立边界**：专注战略提案与平台分流，**不写任何文案 / 不碰终版字段**。
- **对应功能**：01_Router。
- **工作流**：读飞书输入 → 生成 `SPU_CONTEXT` YAML → 发布 `proposal_ready`（带 `CRITICAL_STOP` 人工闸门）。

**✍️ 文案 Agent（SEO / Copy Agent）**
- **独立边界**：专注基于 `SPU_CONTEXT` 的文案创作，不读飞书基础字段、不直接调词库（统一经 keyword-grader）。
- **对应功能**：02_SEO（Amazon）/ 05_Etsy / 06_eBay_Writer。
- **工作流**：监听 `proposal_ready` → 生成初版 → 冻结关键词快照(`--freeze`) → 发布 `draft_done`（带人工闸门）。

**🎨 视觉 Agent（Visual Agent）**
- **独立边界**：专注视觉 Prompt 与 A+ 生成，**不修改 ST（保持初版不变）**、不碰物理接触暗示。
- **对应功能**：03_Visual。
- **工作流**：监听 `draft_done` → 生成终版 + 视觉 Prompt(Img1~7) + A+ Copy/Prompt(01~10) → 发布 `visual_final`。

**💰 广告 Agent（Ads Agent）**
- **独立边界**：专注 PPC 方案，**只读初版标题/ST/痛点**。
- **对应功能**：04_Ads。
- **工作流**：监听 `draft_done` → 生成广告方案 → 写入 `Amazon_广告方案`。

**🏷️ 关键词治理 Agent（Keyword Agent）**
- **独立边界**：**唯一关键词处理入口**，不自行评分（评分交由 `process_dual.py` 确定性计算）。
- **对应功能**：keyword-grader Skill。
- **工作流**：监听 `keyword_request` → 取词 / T1-T5 分级解释 / 深度整理 → 回传结构化结果。语义层（污染审查 / 聚类 / 意图）可委托 GLM-5.2（NVIDIA NIM）或百炼 qwen，不可用时回退 Hy3。

### 架构核心优势

- **合规底线与数据主权**：飞书字段级写权限矩阵 + 最小权限沙箱 + 人工 CRITICAL STOP 闸门 + 风险词三级熔断，从机制层面杜绝越权写入与合规事故；本地词库 + 凭据隔离（`.env` 不入仓）保障数据不出域。
- **高可用与自愈**：事件总线 + 飞书状态中心，任一子 Agent 崩溃均可被主控重启（演进方向），任务不丢失；三振出局 + 超时兜底 + 语义层回退，保障每次 listing 任务都能收敛交付。
- **极简交互，复杂后台**：用户只需在飞书维护商品信息、在对话里说一句"生成 listing"；后台 N 个 Agent 像真实团队一样异步协作、自动流转、优雅降级——创意发散交给模型，确定性计算交给代码，人工只把控关键闸门。

### 当前差距与演进路线（诚实标注）

| 维度 | 参考文要求 | 我们现状 | 演进动作 |
|---|---|---|---|
| 进程隔离 | 子 Agent 独立进程/线程 | 同一 WorkBuddy 会话内上下文执行 | 将子 Agent 封装为独立 Agent 进程/隔离运行时，主控捕获异常自动重启 |
| 通信解耦 | 真 pub/sub 事件总线 | 主控显式顺序唤醒 + 飞书状态 | 引入本地事件总线（asyncio.Queue / 文件队列），保留 CRITICAL_STOP 闸门 |
| 超时兜底 | 主控 Timeout + 降级策略 | 有三振出局，缺统一超时 | 主控层加任务级超时，超时→检查点重跑/基础模板兜底 |
| 语义层韧性 | 多模型可替换 | 百炼→Hy3 回退 + GLM-5.2 新接入 | 明确各语义模型的 SLA 与优先级，固化回退链 |

---

*本文为「本地 OPC 架构」参考内容在 `multi-agent-sop` 上的适配版。涉及 Agent 边界的修改仍需经用户（Nicholas）确认后执行，并同步推送 GitHub `multi-agent-sop` 仓库（遵循 `AGENT_BOUNDARIES.md` 确认门禁）。*
