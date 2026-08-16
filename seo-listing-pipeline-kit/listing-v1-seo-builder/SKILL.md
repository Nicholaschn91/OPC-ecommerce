---
name: listing-v1-seo-builder
description: >
  Listing 初版（v1）SEO 骨架生成器 CLI，覆盖 Etsy / Amazon / eBay 三平台。初版唯一使命 =
  用关键词词库保证 SEO 覆盖完整（高意图词必进 + 长尾要铺），产出可直接交接给终版的草稿。
  初版不可直接上架。触发词："初版" / "v1" / "SEO骨架" / "上架前草稿" / "生成初版" / "Etsy初版" /
  "Amazon初版" / "eBay初版"。本 skill 已 CLI 化：scripts/gen_v1.py（纯规则、零模型依赖、可重跑），
  弱模型加载即知调用。
agent_created: true
---

# Listing 初版（v1）SEO 骨架生成器 — 三平台（CLI 化）

## 一句话定位
**初版 = SEO 覆盖骨架，不是上架稿。** 只解决「可发现性」：把关键词词库完整铺进各平台有限字段槽位。
语言为占位骨架（不打磨语气/转化）——这些交给终版。初版产出后单向交接终版，终版禁止回词库重取词。

## 角色边界（用户锁定 2026-08-08；2026-08-16 追加）
- **只做「商品信息 + 关键词 SEO」的初版 listing**。不碰视觉、不做终版转化精修。
- **初版注意力四要素**：商品信息真实性 → SEO 覆盖有效性 → 平台内容短聚焦 → 输出格式与字符数限制。
  不追求三平台一次出完；一次只聚焦一个平台，保证真实性与 SEO 效果不被长上下文稀释。
- **温度 0.5 的 LLM 创作留待 v2**：当前 `scripts/gen_v1.py` 为纯规则填词（最稳、零模型依赖）。
  `llm_client` 接口已预留，选定 LLM 后端（百炼 qwen / Gemini）后即接创作。
- **飞书初版表 = per-platform `_初版` 列**（Etsy 标题/Tags/Desc；Amazon 标题/五点/ST/HTML/FAQ；
  eBay 标题矩阵/Bullets/ItemSpecs/DescHTML/VeRO），见 `references/<platform>-v1.md`。

## 调用（CLI，必走此路径）
```bash
# 本地产出（md + 自动校验），不碰飞书
python scripts/gen_v1.py --spu <SPU> --platform <etsy|amazon|ebay> --format md --out ./output

# 输出 JSON 数据包（便于程序消费 / 回写）
python scripts/gen_v1.py --spu S3-04 --platform etsy --format json --out ./output

# 顺带回写飞书 Base A（断连安全跳过，不影响本地产出）
python scripts/gen_v1.py --spu S3-04 --platform etsy --write-feishu

# 仅校验不落盘
python scripts/gen_v1.py --spu S3-04 --platform etsy --dry-run
```
- 取词引擎 `keyword_tool.py` 被 `gen_v1.py` 内部调用（`--coverage --platform amazon --format json`），**不重写**。
  **默认按 Amazon 标准取词**：Amazon 每个变体都有 Search Terms，对精准有效关键词的需求量最大；Etsy/eBay 生成时同样复用 Amazon 取词结果，再按各自平台规则落位。
- 否定词封杀取 `keyword_tiers.tier='T5'`（SOP 铁律），独立校验器保证无泄露。
- 每次运行顺带写出 `{out}/{SPU}_listing_bundle.json`（商品真实信息 + 取词计划 + 视觉调性占位），供后续生成其他平台时直接读取，避免重复取词/漂移。

## 核心铁律
1. **单任务单平台**：一次只生成一个平台的初版。多平台通过 `listing_bundle.json` 串联，避免长上下文稀释商品真实性与 SEO 效果。
2. **统一按 Amazon 标准取词**：无论目标平台是 Etsy/eBay/Amazon，内部都调用 `keyword_tool.py --coverage --platform amazon`。Amazon Search Terms 每个变体都有，对精准有效关键词的需求量最大，因此按 Amazon 口径取出的词池足够覆盖其他平台。
3. **覆盖优先于精排**：高意图必进 + 长尾要铺；但铺词不得牺牲商品真实性（禁止为凑字数编造参数/场景）。
4. **平台字段预算（硬天花板 + 生成目标）**：
   - Etsy：标题硬天花板 140，生成目标 **80–90 字符**；Tags=13（每≤20）。
   - Amazon：标题 **≤75 字符**（2026-08 新政）；ST<249B；五点×5。
   - eBay：标题≤80。
5. T5 否定词全文封杀：取词后独立校验，任何字段含 T5 即报错退出（exit 2）。
6. 初版不可直接上架：验收 = SEO 覆盖完整 + 槽位合规 + T5 干净 + 商品信息真实。
7. **防蚕食账本（同类 SKU 主词唯一化）**：取词后、填槽前，调用 `scripts/cannibalization_ledger.py`
   把本 SPU 的高意图主词（T4 首位）登记进本地账本；若同类（同 category）已被其他 SPU 占用，
   则顺延到下一个未占用的 T4 并提到 T4 首位，让 `build_*` 自然采用唯一主词。
   - **数据落点（隔离式）**：账本逻辑 `cannibalization_ledger.py` 在 skill 包内；
     账本**数据文件** `cannibalization_ledger.json` 默认在 skill 包**外**的用户级目录
     `~/.workbuddy/data/opc-seo/`，可用环境变量 `OPC_SEO_LEDGER` 或 `--ledger` 参数覆盖路径。
   - 纯本地、零模型、不碰飞书、不碰 office 词库。
   - **账本是初版与终版共用的单一事实源（2026-08-16 深夜贯通）**：本文件即账本逻辑所在地，
     终版 `qwen-listing-optimizer` 经相对路径 `sys.path` 引入同一模块——
     生成前 `build-inject.py --spu` 调 `render_rule_block()` 注入「本商品已分配唯一主词 + 同类 sibling 已占词（避免复用）」约束，
     写飞书前 `verify-ledger.py` 校验主词未被漂移/互抢。初版登记 → 终版注入 → 终版校验，闭环防同店互抢。

8. **hermes 分层闸门（吐状态码 + 三级熔断，2026-08-16 对齐 hermes SOP）**：`gen_v1.py` 收尾不再只判"校验通过/失败"，
   而是按 hermes `AGENT_BOUNDARIES.md` V1.5 的分层闸门栈收口，统一吐 **状态码**：`OK` / `CRITICAL_STOP` / `MELTDOWN`（对齐主控路由）。
   - 复用共享模块 `scripts/gate.py`（状态码常量 + `scan_risk` 三级确定性匹配 + `classify_risk` 归一成状态码 +
     `render_gate`/`render_risk_block` 渲染报告）。
   - **合规熔断数据源** = `multi-agent-sop/risk_keywords.db`（hermes 维护的权威风险词库，64 条三级：一级15/二级24/三级25，platform 分 all/amazon/etsy）；
     匹配语义严格对齐 `keyword_cli.risk_check`（platform=目标 OR 'all'，keyword 逗号分隔逐词大小写无关子串匹配）。
   - **归总规则**：① T5 否定词泄露 或 一级（致命）命中 → `MELTDOWN`（硬阻断，exit 2，禁止发布）；
     ② 二级（高危）命中 或 字符超限 或 防蚕食冲突 → `CRITICAL_STOP`（闸门，需人工确认，exit 0/1）；
     ③ 其余（含三级中危仅备注、不阻断）→ `OK`。
   - 终版侧 `verify-ledger.py` 同样经 `gate.py` 收口：防蚕食 + 三级熔断 + **字段级回读**（对齐 hermes 铁律#8 逐字段非空）。
   - **两层滤网（2026-08-16 深夜定稿）**：本条铁律 = **第一层（硬/有限）**——只覆盖平台**明确给出**且能**枚举完**的违规（risk_keywords.db 三级 + 字符 + T5 + 防蚕食账本）。**第二层（软/兜底）** = `scripts/gate_soft.py`：`SOFT_RUBRIC`（给真人桥梁 / 终版 Qwen3.8-Max 的软检查清单）+ `soft_heuristics()`（无模型时的轻量确定性代理：关键词密度/重复短语/夸张词/AI痕迹/句长）。软层只出 🟡/🟠 review 信号，**绝不改退出码**——把"人/LLM 应再看一眼"的候选抛出来，由人工桥梁终审。两层串联：硬层权威可阻断，软层兜底不枚举完的灰区。
   - **设计口径**：对齐 hermes 的"分层、机器可读、确定性为主"的闸门栈，**不另立模糊数字打分门**（那套是从 seo-content-team 博客评分搬来的、对本店 listing 反而不合适）。

9. **意图分层（SEO 吸收 A，2026-08-16 深夜）**：取词结果按**购买意图**打标签（`classify_intent`：transactional 高购买 / commercial 中商业 / informational 低信息），T4 余下部分按意图重排，**transactional 优先进标题/首句高权重区**。意图分布随收尾打印，并附进 bundle 的 `keyword_plan.intent`（供终版/飞书消费）。仅作软优先级信号，不影响硬校验。

10. **bundle 飞书字段化（2026-08-16 深夜）**：每次运行产出的 `{out}/{SPU}_listing_bundle.json` 即「初版↔终版数据流」单一载体——商品真实信息 + 取词计划（含意图标签）+ 已生成平台记录。加 `--emit-feishu-field` 可直接打印**字段就绪 payload**（bundle 整体作为单字段值，整段粘贴写入）。建议落点 = 表2 `SHARED_CONTEXT`（已有共享字段，父记录级）或新增长文本字段 `listing_bundle`；**实际写入飞书仍须逐条授权（铁律不动）**。这把"出版/终版 bundle 数据流"收敛为"飞书多一个字段"，不引入额外管道。

## 三平台字段产出（纯规则映射，详见 references/）
| 平台 | 初版字段 | 取词 tier 落位（来自 Amazon 标准 coverage plan） |
|---|---|---|
| Etsy | 标题_初版（80–90 字符） / Tags_初版(×13) / Desc_初版(6段) | T4×3→标题前40+首Tag；T3×12→剩余Tags；标题中后段少量补位 |
| Amazon | 标题_初版（≤75） / 五点_初版 / ST_初版 / HTML_初版 / FAQ_初版 | T4→标题前40+五点#1；T3→五点#2/3；T2→五点#4/5；T1→ST |
| eBay | 标题矩阵_初版(×3, ≤80) / ItemSpecs_初版 / Bullets / DescHTML / VeRO | T2→标题最前；T3→标题中+ItemSpecs；T4→ItemSpecs捡漏；T1→标题尾 |

## 稳定保证
- 温度固定（v2 接入 LLM 时=0.5）；结构化输出；关键词作不可篡改常量。
- **槽位校验器独立于任何模型** —— 弱模型/换 SPU 同效，不会破坏 SEO 覆盖。
- CLI 参数化、可重跑 → 不依赖对话上下文，任何模型加载本 skill 即知调用。

## 微调指引
- 调某平台骨架/槽位/语气 → 只改 `references/<platform>-v1.md`（映射规则源）。
- 调取词覆盖计划（各 tier top / 排序）→ 改 `keyword_tool.py` 的 `PLATFORM_PLANS`（全局）。
- 飞书字段名对齐 → 改 `scripts/feishu_write.py` 的 `FIELD_MAP`。

## 文件结构
```
listing-v1-seo-builder/
├── SKILL.md            # 本文件（调用入口）
├── scripts/
│   ├── gen_v1.py       # 主 CLI：取词→填槽位→校验→输出/回写/bundle
│   └── feishu_write.py # 飞书 Base A 回写（--write-feishu 触发，断连安全跳过）
└── references/
    ├── etsy-v1.md / amazon-v1.md / ebay-v1.md   # 槽位规则 + 验收（CLI 读取源）
    └── keyword-coverage.md
```
- 中间产物：`{out}/{SPU}_listing_bundle.json` 在首次生成某平台时自动落盘，后续平台生成可直接 `--load-bundle` 读取，避免重复取词与商品理解漂移。

## 交接契约（单向 + 反馈环）
- 初版草稿 → 终版唯一输入源之一（另一个=商品基础信息+基材）。
- SEO 覆盖是「已满足约束」，终版可保留/自然改写初版词，但**不得回原始词库再加词**。
- 终版发现真实 SEO 缺口（漏高意图词）→ 不静默补，回抛初版重跑。
