# OPC Listing 半自动文案生产线 — SOP 总览（架构 + 工具形态）

> 备份包 v1 · 2026-08-17 · 以 S3-04(etsy) 为已跑通样例
> 本包是「架构 + 工具」形态：**两个协作技能（skill）** 按 SOP 接力，中间有人工 checkpoint。
> 不是扁平脚本堆——技能边界、交接协议、工具归属都保留。

## 一、这是什么
一条半自动跨境电商 Listing 文案生产线，覆盖 Etsy / Amazon / eBay 三平台。
- 「半自动」= 中间有一个**人工 checkpoint**（你拿提示词去免费大模型网页端跑终版），所以无法压成单一 SOP，按**阶段**切分、靠技能接力。
- 目前只覆盖**文字线**；**设计图生成（视觉线）是独立未开工的工作流**。

## 二、多 agent 协作接力图
```
┌─────────────────────────┐
│ 技能A: listing-v1-seo-builder │  (纯规则, 无模型)
│  Stage1 取词 + 初版骨架        │
│  → 产出 bundle + <平台>_v1.md   │
└──────────────┬──────────────┘
               │ 交接: handoff 包(_e2e_out/<spu>/)
               ▼
┌─────────────────────────┐
│ 【人工 checkpoint ①】       │  复制 prompt_to_run.txt → 粘 Qwen3.8-Max 网页端跑
│  你拿提示词去免费模型跑终版    │  → 整段贴回 clean.md
└──────────────┬──────────────┘
               ▼
┌─────────────────────────┐
│ 技能B: qwen-listing-optimizer │
│  Stage2 装配提示词(assemble)  │
│  Stage3 闸门校验(verify-ledger)│
│  Stage4 落库飞书(stage4_write) │
└──────────────┬──────────────┘
               │ 【人工 checkpoint ②: 确认闸门放行】
               │ 【人工 checkpoint ③: 授权写飞书】
               ▼
          表2 三阶段字段回填完成
```

## 三、两个技能的职责边界（工具归属）
| 技能 | 管哪段 | 关键工具 |
|---|---|---|
| `listing-v1-seo-builder/` | Stage1 取词+初版；共用质检滤网 `gate.py`/`gate_soft.py`；防蚕食 `cannibalization_ledger.py` | `scripts/gen_v1.py`、`stage1_feishu_sync.py` |
| `qwen-listing-optimizer/` | Stage2 装配提示词、Stage3 闸门、Stage4 落库；底层规则真源 `qwen3.8-max-listing-optimizer-prompt.md` | `scripts/assemble_handoff.py`、`build-inject.py`、`verify-ledger.py`、`stage4_write_final.py` |
| `_shared/` | 跨技能依赖（不拍平，归属清晰） | `feishu_products_io.py`（落库IO）、`risk_keywords.db`（风险词库） |

## 四、运行入口（看各技能 SKILL.md 拿完整命令）
- **Stage1**：`python listing-v1-seo-builder/scripts/gen_v1.py --spu S3-04 --platform etsy --emit-feishu-field`
- **Stage2 装配**：`python qwen-listing-optimizer/scripts/assemble_handoff.py --spu S3-04 --bundle <bundle>.json --out-dir _e2e_out/S3-04 --mode full` → 人工去网页端跑
- **Stage3 闸门**：`python qwen-listing-optimizer/scripts/verify-ledger.py --spu S3-04 --in _e2e_out/S3-04/clean.md --platform etsy`
- **Stage4 落库**：`python listing-v1-seo-builder/scripts/stage1_feishu_sync.py --spu S3-04 --platform etsy --record <rec>` + `python qwen-listing-optimizer/scripts/stage4_write_final.py --spu S3-04 --platform etsy --record <rec> --clean <clean.md> --bundle <bundle.json>`

## 五、人工接入点（3 个）
1. **跑模型**：Stage2 装配出提示词后，你拿去 Qwen3.8-Max 网页端跑，贴回 `clean.md`。
2. **确认放行**：Stage3 闸门出 `OK` 后，你确认才进 Stage4。
3. **授权写飞书**：Stage4 每次写表2 须经你逐条授权（飞书铁律）。

## 六、当前状态（2026-08-17）
- ✅ 文字线 Stage1–4 已在 S3-04(etsy) 完整跑通验证（见 `sample_S3-04/`）。
- ⚠️ S3-04 终版含模型编造参数（12oz/15"×16"等），因 `product_truth` 无真实 spec；根治待真实数据喂入重跑。
- ⏸️ 视觉线（设计图生成）未开工，明日另议。

## 七、未来演进
接入大模型 API 后，把人工 checkpoint ① 换成 API 调用，即可把两技能合并为单一 SOP，全流程自动化——**架构不动，只是把人工环节换成机器环节**。

---
### 本包与 canonical 的关系
- 运行态（你平时改/跑的）：`~/.workbuddy/skills/multi-agent-sop/{listing-v1-seo-builder, qwen-listing-optimizer}`
- GitHub 镜像：`OPC-ecommerce` 仓库 `skills/multi-agent-sop/`
- 本桌面包：上述架构的**阶段化可读备份**（技能树原样 + 本 SOP 总览），人读友好，可带走。
