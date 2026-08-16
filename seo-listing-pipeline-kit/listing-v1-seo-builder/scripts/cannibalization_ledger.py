#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
cannibalization_ledger.py — 防关键词蚕食账本（本地 JSON，零模型）
==============================================================
目的：同店同类（同 category）SKU 之间，高意图「主词」全局唯一，
      避免互相抢同一搜索词的排名权重。
      思路吸收自 seo-content-team 的 keyword-researcher：
      「每篇一主词 / 无两篇共享主词 / 意图分离」。

设计铁律（对齐 OPC 约束）：
  - 纯本地 JSON，零模型依赖；不碰飞书、不碰 office 词库、不改任何上锁 skill。
  - 数据文件默认落在 skill 包【之外】的用户级数据目录，保持 skill 代码可移植：
        默认：~/.workbuddy/data/opc-seo/cannibalization_ledger.json
        覆盖：环境变量 OPC_SEO_LEDGER 或 gen_v1.py 的 --ledger 参数。
  - 账本是「store-wide 运行态」（跨 SPU、跨会话增长），不属于某个 skill 版本，
    故不放进 skill 包内（不被 git/同步当代码提交，避免更新/重装冲突或被覆盖）。

SHARED（账本贯通终版, 2026-08-16 深夜）:
  - 本文件是初版(listing-v1-seo-builder)与终版(qwen-listing-optimizer)的**单一事实源**，
    置于初版 scripts/ 下；终版 build-inject.py 经相对路径 sys.path 引入，复用同一本账。
  - 终版在「生成前」注入约束块(render_rule_block)、「写飞书前」用 verify 校验，
    与初版 choose_main_word 形成闭环，杜绝两版各说各话导致主词漂移/互抢。

API:
  ledger_path()                 -> 当前账本 JSON 绝对路径
  choose_main_word(cat,spu,words)-> 从有序候选里挑「同类未被其他 SPU 占用」的词作主词并登记
  reset_spu(cat,spu)            -> 撤销某 SPU 在账本中的登记
  dump()                        -> 返回整本账本（便于审计/展示）
  lookup_spu(spu)               -> 跨类目查找某 SPU 的登记 {category, main_word, forced} 或 None
  siblings(category, spu)       -> 同类其他 SPU 已占主词列表 [{spu, main_word}]
  render_rule_block(spu, cat)   -> 生成注入终版提示词的「防蚕食约束」中文文本块
"""

import json
import os
import sys
from datetime import datetime, timezone

# ------------------------- 路径解析（默认 skill 包外）-------------------------
DEFAULT_LEDGER = os.path.join(
    os.path.expanduser("~"), ".workbuddy", "data", "opc-seo",
    "cannibalization_ledger.json",
)


def ledger_path():
    """账本 JSON 路径：环境变量 OPC_SEO_LEDGER 优先，否则默认用户级数据目录（skill 包外）。"""
    return os.environ.get("OPC_SEO_LEDGER", DEFAULT_LEDGER)


def load():
    p = ledger_path()
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"version": 1, "by_category": {}}


def save(data):
    p = ledger_path()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def choose_main_word(category, spu, candidate_words, force=False):
    """同类 SKU 主词唯一化。

    参数:
      category        : 商品类目（同类 = 同 category），空则归 'uncategorized'
      spu             : 当前 SPU 标识
      candidate_words : 有序候选主词列表（通常传 T4 高意图词，首位优先级最高）
    返回 dict:
      assigned 已分配主词 | conflict 是否冲突 | forced 是否被迫占用 | skipped 落选词
    """
    category = (category or "uncategorized").strip()
    candidate_words = [w for w in (candidate_words or []) if w]
    data = load()
    cat = data.setdefault("by_category", {}).setdefault(category, {})

    # 已登记过（同 SPU 重跑）→ 返回既有登记，不重复占用
    if spu in cat:
        rec = cat[spu]
        return {"assigned": rec.get("main_word"), "conflict": False, "reused": True,
                "category": category, "spu": spu}

    used = {rec.get("main_word") for rec in cat.values() if rec.get("main_word")}
    for w in candidate_words:
        if w not in used:
            cat[spu] = {
                "main_word": w,
                "alts": [c for c in candidate_words if c != w],
                "claimed_at": datetime.now(timezone.utc).isoformat(),
            }
            save(data)
            return {"assigned": w, "conflict": False, "category": category, "spu": spu,
                    "skipped": [c for c in candidate_words if c != w]}

    # 全部被占用：强制取第一个并告警（提示人工复核）
    if candidate_words:
        w = candidate_words[0]
        cat[spu] = {
            "main_word": w,
            "alts": candidate_words[1:],
            "claimed_at": datetime.now(timezone.utc).isoformat(),
            "forced": True,
        }
        save(data)
        return {"assigned": w, "conflict": True, "forced": True, "category": category,
                "spu": spu, "taken_by": "ALL_TAKEN"}
    return {"assigned": None, "conflict": True, "category": category, "spu": spu,
            "taken_by": "NO_CANDIDATES"}


def reset_spu(category, spu):
    """撤销某 SPU 在账本中的登记（人工纠错/重跑前清理用）。"""
    data = load()
    cat = data.get("by_category", {}).get(category)
    if cat and spu in cat:
        del cat[spu]
        save(data)
        return True
    return False


def dump():
    """返回整本账本（审计/展示用）。"""
    return load()


def lookup_spu(spu):
    """跨类目查找某 SPU 的登记。返回 {category, main_word, forced} 或 None。
    终版不知道 category 时也能凭 spu 反查（初版已登记过）。"""
    data = load()
    for cat, m in data.get("by_category", {}).items():
        if spu in m:
            rec = m[spu]
            return {"category": cat, "main_word": rec.get("main_word"),
                    "forced": bool(rec.get("forced", False))}
    return None


def siblings(category, spu):
    """同类其他 SPU 已占主词列表（排除自身）。终版注入「避免复用」时用。"""
    data = load()
    cat = data.get("by_category", {}).get(category, {})
    return [{"spu": k, "main_word": v.get("main_word")}
            for k, v in cat.items() if k != spu and v.get("main_word")]


def render_rule_block(spu, category=None):
    """生成注入终版提示词的中文约束块。

    返回 (text, found)：
      - 若账本已登记本 SPU 主词 → 强制要求将其作核心焦点词；
      - 若已知类目 → 列出同类 sibling 已占主词，要求避免作为核心焦点词；
      - 皆无 → 软提示「若同类已有主打词请避免重复」。
    found 供调用方判断是否真的命中了账本（用于日志/告警）。
    """
    reg = lookup_spu(spu)
    cat = category or (reg.get("category") if reg else None)
    lines = ["【防蚕食约束 · STORE UNIQUENESS RULE】"]
    found = False
    if reg and reg.get("main_word"):
        found = True
        lines.append(
            f"· 本商品在店铺主词账本中已登记唯一主词：『{reg['main_word']}』"
            f"（同类目：{reg['category']}）。"
            f"请将其作为【标题】与【Description 前段】的核心焦点词，贯穿始终，"
            f"不可被其他词取代或稀释。"
        )
        if reg.get("forced"):
            lines.append(
                "· ⚠️ 该主词为同类目主词已被占满时的强制分配，存在蚕食风险，"
                "请在不破坏商品真实性的前提下尽量用同义长尾表达缓冲。"
            )
    if cat:
        sibs = siblings(cat, spu)
        if sibs:
            words = "、".join(f"『{s['main_word']}』" for s in sibs)
            lines.append(
                f"· 同类目（{cat}）其他商品已占用主词：{words}。"
                f"请勿将这些词作为本商品的核心焦点词，避免同店商品互抢同一搜索词排名。"
            )
            found = True
    if not found:
        lines.append(
            "·（未检索到本商品的主词账本登记；若本店同类目商品已有主打词，"
            "请主动避免与之重复，保持每条 listing 主词唯一。）"
        )
    return "\n".join(lines), found


if __name__ == "__main__":
    # 简易 CLI：打印账本快照
    d = dump()
    print(json.dumps(d, ensure_ascii=False, indent=2))
