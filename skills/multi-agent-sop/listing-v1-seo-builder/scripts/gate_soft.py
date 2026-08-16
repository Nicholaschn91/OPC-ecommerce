#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gate_soft.py — OPC listing 两层滤网 · 第二层（软判定 / 兜底）
============================================================

设计依据（对齐用户 2026-08-16 深夜决策）：
  hermes 的硬闸门（risk_keywords.db 三级 + 字符门禁 + T5 + 防蚕食账本）是「有限」的——
  它只覆盖平台**明确给出**且我能**枚举完**的违规。平台政策灰区、过度优化、
  关键词堆砌、AI 痕迹、承诺无依据、意图错配等**枚举不完**的软违规，硬规则必然漏判。

  → 因此补「第二层滤网 = 软判定兜底」：
      ① SOFT_RUBRIC：给真人桥梁 / 终版 Qwen3.8-Max 的软检查清单（LLM 应用层）；
      ② soft_heuristics()：无模型时的**轻量确定性代理**信号（不阻断，仅 review）。

两层关系：
  - 硬层（gate.py）= 权威、确定性、可阻断（MELTDOWN/CRITICAL_STOP exit 码）；
  - 软层（本文件）= 兜底、启发式、信号级（只出 🟡/🟠 review，绝不改退出码）。
  - 软层命中 ≠ 违规定论；它把「人/LLM 应再看一眼」的候选抛出来，由人工桥梁终审。
  - 这是「硬的有限，软的兜底」——两层串联，而非互相替代。

SOFT_RUBRIC 用于：
  - 初版 gen_v1 收尾打印「软检查提示」，提示人去 web 模型跑时带着这份清单；
  - 终版 build-inject.py 可经 soft_rubric_text() 注入 Qwen3.8-Max 提示词（生成前自检）。

API:
  SOFT_RUBRIC                 -> 软层检查清单（list[str]，markdown 行）
  soft_rubric_text()          -> 拼接成可注入提示词的字符串
  soft_heuristics(text)       -> [signal{dim,sev,detail}]  轻量确定性代理（无模型兜底）
  render_soft_block(signals)  -> markdown 渲染（供工具收尾打印）
"""
import re

# ---- 软层检查清单（给 LLM / 人的兜底维度）----
# 这些维度硬规则枚举不完，交给"会读语义的层"判断。
SOFT_RUBRIC = [
    "自然度/可读性：文案是否像真人母语写就？有无机械堆砌、句子长短无变化、模板化句式。",
    "过度优化/关键词堆砌：核心词是否在不自然位置机械重复？密度是否过高触发平台降权。",
    "平台政策灰区：是否踩了未进风险库、但平台明确禁止的灰区（缺货/预购误导、虚假 urgency、刷评暗示）。",
    "承诺/功效背书：医疗、效果、保质期、材质等主张有无依据？是否构成无依据夸大（即便未命中硬词）。",
    "AI 痕迹：是否过度模板化、缺少品牌口吻、满篇 elevate/perfect/seamlessly 等 AI 高频词。",
    "意图匹配：文案是否匹配搜索意图（高购买意图词应落在标题/首句高权重区，而非埋在描述）。",
]

# 软层确定性代理用的轻量词典（兜底信号，非定论）
_OVERCLAIM_WORDS = ["best", "top", "100%", "perfect", "ultimate", "number one", "#1",
                    "free shipping", "guaranteed", "amazing", "incredible", "must-have"]
_AI_TELL_WORDS = ["elevate", "seamlessly", "unlock", "transform", "effortless",
                  "curated", "bespoke", "timeless", "elevate your", "designed to",
                  "perfectly", "stunning", "exceptional"]
# 高购买意图信号（用于意图分层时的软校验参考，非阻塞）
_TXINTENT_WORDS = ["custom", "personalized", "personalise", "gift", "for her", "for him",
                   "make your own", "design your own", "create your own", "diy", "order"]


def soft_rubric_text() -> str:
    """拼接软层清单为可注入提示词的字符串。"""
    return "【软层自检清单（兜底·非硬阻断）】\n" + "\n".join(f"- {r}" for r in SOFT_RUBRIC)


def soft_heuristics(text: str) -> list:
    """轻量确定性代理（无模型时的兜底信号）。
    仅产出 review 信号，绝不阻断。返回 signal 列表：
      {dim, sev('review'|'flag'), detail}
    """
    if not text:
        return []
    signals = []
    low = text.lower()
    words = re.findall(r"[a-z0-9#%]+", low)
    n = len(words)
    if n == 0:
        return signals

    # 1) 关键词密度代理：SEO 词（custom/personalized/gift 等）重复占比
    tx_hits = sum(1 for w in words if w in _TXINTENT_WORDS)
    if n >= 20 and tx_hits / n > 0.10:
        signals.append({
            "dim": "过度优化/堆砌", "sev": "flag",
            "detail": f"高意图词占全文 {tx_hits/n*100:.0f}%（>10%），疑似机械堆砌，建议分散自然化",
        })

    # 2) 重复 bigram（2 词短语重复 >=3 次）→ 堆砌
    bigrams = [f"{words[i]} {words[i+1]}" for i in range(len(words) - 1)]
    from collections import Counter
    bg = Counter(bigrams)
    repeats = [b for b, c in bg.items() if c >= 3 and len(b.split()) == 2]
    if repeats:
        signals.append({
            "dim": "重复短语", "sev": "flag",
            "detail": f"短语重复≥3次: {', '.join(repeats[:3])} — 疑似关键词堆砌",
        })

    # 3) 夸张/无依据主张词
    oc = [w for w in _OVERCLAIM_WORDS if w in low]
    if len(oc) >= 2:
        signals.append({
            "dim": "夸张/无依据主张", "sev": "review",
            "detail": f"出现 {len(oc)} 个夸张词（{', '.join(oc[:4])}），软层建议核查是否构成无依据夸大",
        })

    # 4) AI 痕迹代理
    ai = [w for w in _AI_TELL_WORDS if w in low]
    if len(ai) >= 2:
        signals.append({
            "dim": "AI 痕迹", "sev": "review",
            "detail": f"出现 {len(ai)} 个 AI 高频词（{', '.join(ai[:4])}），软层建议加入品牌口吻、去模板化",
        })

    # 5) 句子长度极端（可读性代理）
    sents = [s for s in re.split(r"[.!?。！？]", text) if s.strip()]
    if sents:
        avg = sum(len(s.split()) for s in sents) / len(sents)
        if avg > 32:
            signals.append({
                "dim": "可读性", "sev": "review",
                "detail": f"平均句长 {avg:.0f} 词（偏长），软层建议拆分短句提升可读性",
            })

    return signals


def render_soft_block(signals: list) -> str:
    """渲染软层段（review 信号，非阻断）。"""
    if not signals:
        return "  ✅ 软层兜底：轻量代理未触发明显信号（最终仍由人/LLM 按 SOFT_RUBRIC 终审）"
    L = [f"  🟡 软层兜底（review 信号，不阻断；最终由人/LLM 按 SOFT_RUBRIC 终审）："]
    for s in signals:
        icon = "🟠" if s["sev"] == "flag" else "🟡"
        L.append(f"    {icon} [{s['dim']}] {s['detail']}")
    return "\n".join(L)
