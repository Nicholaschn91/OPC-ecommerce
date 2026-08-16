#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gate.py — OPC listing 闸门模块（对齐 hermes SOP 分层闸门栈）
=============================================================

设计依据：hermes `AGENT_BOUNDARIES.md` V1.5 的质量门禁是「分层、机器可读、
确定性为主」的栈，而非模糊数字打分。本模块把 hermes 的两道确定性闸门
落到初版/终版 standalone 工具里：

  ① 合规熔断（MELTDOWN）：风险词**三级**确定性匹配（数据源 = risk_keywords.db）
     - 一级（致命）→ 必须替换后才可发布（硬阻断 = MELTDOWN）
     - 二级（高危）→ 强制警告、附替代词、需用户确认（闸门 = CRITICAL_STOP）
     - 三级（中危）→ 建议静默替换、不阻断发布（仅备注）
  ② 状态信号（status code）：每个工具收尾吐 OK / CRITICAL_STOP / MELTDOWN / ERROR，
     供 hermes 主控 / 人工桥梁按码路由（与 AGENT_BOUNDARIES 状态码同义）。

匹配语义严格复用 `keyword_cli.risk_check`：
  - 规则筛选：(platform = ? OR platform = 'all')
  - keyword 可逗号分隔，逐词做**大小写无关子串匹配**（in text_lower）

数据落点（隔离式）：
  - 逻辑（本文件）在 skill 包内，可移植；
  - 数据 risk_keywords.db 在 multi-agent-sop 根（hermes 维护的权威风险词库），只读。

API:
  resolve_risk_db(root)            -> risk_keywords.db 绝对路径
  scan_risk(text, platform, db)   -> [hit{level,risk_type,keyword,hit,alternative,consequence,platform}]
  classify_risk(hits)             -> (status, stats)   status ∈ {MELTDOWN, CRITICAL_STOP, OK}
  STATUS / LEVEL_FATAL / LEVEL_HIGH / LEVEL_MEDIUM
"""
import os
import re
import sqlite3

# ---- hermes 状态码（与 AGENT_BOUNDARIES 同义）----
STATUS = {
    "OK":             "OK",              # 执行成功，可进入下一步
    "CRITICAL_STOP":  "CRITICAL_STOP",   # 阶段完成但需人工确认（闸门）
    "MELTDOWN":       "MELTDOWN",        # 合规熔断，禁止发布
    "ERROR":          "ERROR",           # 执行失败
}

LEVEL_FATAL = "一级（致命）"
LEVEL_HIGH  = "二级（高危）"
LEVEL_MEDIUM = "三级（中危）"

# 字符门禁（确定性计数，对齐 compliance_agent_prompt.md §4；gen_v1 BUDGET 已含部分）
CHAR_LIMITS = {
    "amazon": {"title": 75, "bullet": 200, "html": 2000, "st_bytes": 249, "faq": 100},
    "etsy":   {"title": 140, "tag": 20, "tags": 13},
    "ebay":   {"title": 80},
}


def resolve_risk_db(root: str) -> str:
    """multi-agent-sop 根目录下的权威风险词库（hermes 维护，只读）。"""
    return os.path.join(root, "risk_keywords.db")


def _connect(db_path: str):
    if not db_path or not os.path.exists(db_path):
        return None
    try:
        return sqlite3.connect(db_path)
    except Exception:
        return None


def scan_risk(text: str, platform: str = "all", db_path: str = None) -> list:
    """对单段文本做三级风险词确定性匹配。
    返回 hit 列表，每项：
      {level, risk_type, keyword(原始规则词), hit(实际命中子串),
       alternative, consequence, platform(规则所属平台)}
    """
    if not text:
        return []
    conn = _connect(db_path)
    if conn is None:
        return []
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    where, params = [], []
    if platform and platform != "all":
        where.append("(platform = ? OR platform = 'all')")
        params.append(platform)
    else:
        where.append("1=1")
    cur.execute(
        f"SELECT * FROM risk_keywords WHERE {' AND '.join(where)}",
        params,
    )
    rows = cur.fetchall()
    conn.close()

    text_lower = text.lower()
    hits = []
    for r in rows:
        for kw in (r["keyword"] or "").split(","):
            kw_clean = kw.strip().lower()
            if not kw_clean:
                continue
            # 词边界匹配：token 前后不得紧跟字母/数字/下划线/连字符，
            # 避免 "ul" 误中 "ultimate"、"top" 误中 "top-down"、"ce" 误中 "price"。
            # 仍保留大小写无关；短语型 token（如 "ul listed"）按整体匹配。
            pat = re.compile(r'(?<![\w])' + re.escape(kw_clean) + r'(?![\w-])')
            if pat.search(text_lower):
                hits.append({
                    "level": r["level"],
                    "risk_type": r["risk_type"],
                    "keyword": r["keyword"],
                    "hit": kw_clean,
                    "alternative": r["alternative"] or "",
                    "consequence": r["consequence"] or "",
                    "platform": r["platform"],
                })
                break
    return hits


def classify_risk(hits: list):
    """把命中列表归一成 hermes 状态码。
    一级（致命）→ MELTDOWN（硬阻断）
    二级（高危）→ CRITICAL_STOP（需确认闸门）
    三级（中危）→ 不提升状态码（仅备注，静默替换）
    """
    fatal = [h for h in hits if h["level"] == LEVEL_FATAL]
    high = [h for h in hits if h["level"] == LEVEL_HIGH]
    medium = [h for h in hits if h["level"] == LEVEL_MEDIUM]
    if fatal:
        status = STATUS["MELTDOWN"]
    elif high:
        status = STATUS["CRITICAL_STOP"]
    else:
        status = STATUS["OK"]
    stats = {"fatal": len(fatal), "high": len(high), "medium": len(medium),
             "total": len(hits)}
    return status, stats, {"fatal": fatal, "high": high, "medium": medium}


def render_risk_block(hits, stats, prefix: str = "") -> str:
    """渲染风险三级熔断块（markdown 风格，供工具收尾打印）。"""
    if not hits:
        return f"{prefix}✅ 风险词扫描：未发现命中（64 条三级规则已查）"
    L = []
    L.append(f"{prefix}⚠️ 风险词扫描：🔴致命 {stats['fatal']} / 🟠高危 {stats['high']} / 🟡中危 {stats['medium']}")
    for h in hits:
        icon = "🔴" if h["level"] == LEVEL_FATAL else ("🟠" if h["level"] == LEVEL_HIGH else "🟡")
        alt = f" → 替代：`{h['alternative']}`" if h["alternative"] else ""
        L.append(f"{prefix}  {icon} [{h['level']}] {h['risk_type']}: 命中 `{h['hit']}`{alt}")
    return "\n".join(L)


def render_gate(title: str, status: str, checks: list) -> str:
    """渲染统一闸门报告（工具收尾打印，供人工桥梁/主控按码路由）。
    checks: list of (label, ok_bool, detail)
    """
    icon = {"OK": "✅", "CRITICAL_STOP": "🟠", "MELTDOWN": "🔴", "ERROR": "❌"}.get(status, "❓")
    L = [f"\n{'='*52}", f"【闸门 GATE · {icon} {status}】 {title}", f"{'-'*52}"]
    for label, ok, detail in checks:
        L.append(f"  {'✅' if ok else '⛔'} {label}" + (f" — {detail}" if detail else ""))
    L.append(f"{'='*52}")
    return "\n".join(L)
