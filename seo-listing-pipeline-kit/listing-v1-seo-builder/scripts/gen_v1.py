#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gen_v1.py — Listing 初版（v1）纯规则 SEO 骨架生成器 CLI
=====================================================

角色边界（用户锁定 2026-08-08）：
  - 只做「商品信息 + 关键词 SEO」的初版 listing
  - 温度 0.5 的 LLM 创作留待 v2（llm_client 接口已预留，本版不调用）
  - 本版 = 纯规则填词 + 独立校验，零模型依赖 → 最稳

依赖（不重写引擎）：
  - keyword_tool.py  --coverage --format json   （取词引擎，复用）
  - keyword_database.db                          （SPU 商品信息 + T5 否定词）

输出：
  - 本地 {out}/{SPU}_{platform}_v1.md  +  .json
  - 可选 --write-feishu：回写飞书 Base A 的 {Platform}_*_初版 等（断连安全跳过）

用法：
  python gen_v1.py --spu S3-04 --platform etsy --format md --out ./output
  python gen_v1.py --spu S3-04 --platform etsy --write-feishu
"""
import argparse
import json
import os
import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone

# ---- 路径解析（scripts/ 在 listing-v1-seo-builder/scripts/）----
HERE = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(HERE)                       # listing-v1-seo-builder
ROOT = os.path.dirname(SKILL_ROOT)                      # multi-agent-sop
DB_PATH = os.path.join(ROOT, "keyword_database.db")
KT = os.path.join(ROOT, "keyword_tool.py")
PY = sys.executable
sys.path.insert(0, HERE)  # 允许 import 同目录模块（cannibalization_ledger / gate / feishu_write）
import gate as gate  # hermes 分层闸门：状态码 + 三级熔断扫描
import gate_soft as gate_soft  # 两层滤网·第二层（软判定兜底，不阻断）

# ---- 平台槽位硬预算（天花板 + 生成目标）----
BUDGET = {
    # etsy 标题硬上限 140，与终版提示词(标题 140 字符限制)一致；title_target 亦对齐 140，
    # 保证初版骨架与终版优化共用同一字符预算（用户要求两版字符要求差不多）。
    "etsy":   {"title": 140, "title_target": 140, "tags": 13, "tag_len": 20},
    "amazon": {"title": 75, "st_bytes": 249},
    "ebay":   {"title": 80},
}


# ---------------------------------------------------------------------------
# 取词（复用 keyword_tool.py 引擎，不重写；默认按 Amazon 标准取词）
# ---------------------------------------------------------------------------
def coverage(spu: str, keyword_platform: str = "amazon") -> dict:
    """调 keyword_tool.py --coverage --format json，按 _source_tier 分组。
    默认 keyword_platform='amazon'：Amazon Search Terms 每个变体都有，所需精准有效关键词量最大，
    取出的词池足够覆盖 Etsy/eBay/Amazon 三平台。
    """
    try:
        r = subprocess.run(
            [PY, KT, "--spu", spu, "--coverage", "--platform", keyword_platform, "--format", "json"],
            capture_output=True, text=True, cwd=ROOT, timeout=60,
        )
        rows = json.loads(r.stdout)
    except Exception:
        rows = []
    groups = defaultdict(list)
    for row in rows:
        tier = row.get("_source_tier") or row.get("tier")
        groups[tier].append(row.get("keyword"))
    return groups


def negatives(spu: str) -> list:
    """取 T5 否定词（SOP 铁律：T5 全文封杀）。源 = keyword_tiers.tier='T5'。"""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute(
            """SELECT k.keyword FROM keywords k
               JOIN keyword_tiers t ON k.id = t.keyword_id
               WHERE k.spu_id = ? AND t.tier = 'T5'""",
            (spu,),
        )
        neg = [r[0] for r in cur.fetchall()]
        con.close()
        return neg
    except Exception:
        return []


def spu_info(spu: str):
    """读商品基础信息（用于 Desc 骨架占位）。"""
    try:
        con = sqlite3.connect(DB_PATH)
        cur = con.cursor()
        cur.execute("SELECT spu_name, category, material FROM spu WHERE spu_id = ?", (spu,))
        r = cur.fetchone()
        con.close()
        if r:
            return (r[0] or spu, r[1] or "", r[2] or "")
    except Exception:
        pass
    return (spu, "", "")


# ---------------------------------------------------------------------------
# T5 否定词剔除（取词阶段即封杀，SOP 铁律第4条）
# ---------------------------------------------------------------------------
def _universal_neg_roots(neg: list) -> set:
    """从 T5 否定词派生『泛礼物词族』封杀根：凡 T5 含 gift/gifts token，
    则该 token 成为本 SPU 的通用封杀根（SOP 铁律：泛礼物词稀释『人名/照片定制』意图，全封杀）。
    不误伤 photo 等正词。"""
    import re
    roots = set()
    for n in neg:
        for tok in re.findall(r"[a-z]+", (n or "").lower()):
            if tok in ("gift", "gifts"):
                roots.add(tok)
    return roots


def filter_neg(groups: dict, neg: list) -> dict:
    """剔除 T5 否定词（双层封杀）：
      (1) 整短语匹配：含任意完整 T5 短语即剔除；
      (2) 泛礼物词根封杀：含 gift/gifts 词根的变体（复数/换序/重组）也剔除——
          解决 T5 只列具体短语、而同义礼物词散落 T1–T4 导致的漏杀。
    """
    exact = [n.lower() for n in neg if n]
    roots = _universal_neg_roots(neg)
    out = defaultdict(list)
    for tier, kws in groups.items():
        for kw in kws:
            kl = kw.lower()
            if any(e in kl for e in exact):
                continue
            if any(r in kl for r in roots):
                continue
            out[tier].append(kw)
    return out


# ---------------------------------------------------------------------------
# 意图分层（SEO 吸收 A：给取词打购买意图标签，标题优先吃高意图词）
# ---------------------------------------------------------------------------
_INTENT_TX = ("custom", "personalized", "personalise", "gift", "for her", "for him",
              "make your own", "design your own", "create your own", "diy", "order", "buy")
_INTENT_COM = ("best", "unique", "top", "ideas", "trendy", "popular", "quality",
               "premium", "handmade", "design", "style", "aesthetic", "cute", "cool")


def classify_intent(word: str) -> str:
    """购买意图分层（marketplace 口径）：
      transactional 高购买意图 → commercial 中商业调研 → informational 低信息。
    仅作软优先级信号，不影响硬校验。"""
    w = (word or "").lower()
    if any(t in w for t in _INTENT_TX):
        return "transactional"
    if any(t in w for t in _INTENT_COM):
        return "commercial"
    return "informational"


def rank_by_intent(t4: list) -> list:
    """T4 按意图重排：transactional 优先进标题/首句高权重区，其次 commercial，最后 informational。"""
    order = {"transactional": 0, "commercial": 1, "informational": 2}
    return sorted(t4, key=lambda k: order[classify_intent(k)])


def intent_distribution(groups: dict) -> dict:
    """统计各 tier 的意图分布，供收尾打印。"""
    dist = {}
    for tier, kws in groups.items():
        c = {"transactional": 0, "commercial": 0, "informational": 0}
        for k in kws:
            c[classify_intent(k)] += 1
        dist[tier] = c
    return dist


# ---------------------------------------------------------------------------
# 平台填充（纯规则，按 references/<p>-v1.md 映射）
# ---------------------------------------------------------------------------
def build_etsy(groups, info):
    T4 = groups.get("T4", [])
    T3 = groups.get("T3", [])
    T2 = groups.get("T2", [])
    T1 = groups.get("T1", [])
    name, cat, mat = info

    # 标题：前 40 权重最高（T4 前 3 + 核心品类），剩余在 80-90 目标内补位，硬上限 140
    head = " ".join(T4[:3])
    title = f"{head} {name}".strip()
    target = BUDGET["etsy"]["title_target"]
    ceiling = BUDGET["etsy"]["title"]
    # 如果 T4+name 已超过目标，截断到目标（很少发生）；否则补位但不超过目标
    if len(title) > target:
        title = title[:target].rsplit(" ", 1)[0].strip()
    else:
        for kw in T3 + T2[:2] + T1[:2]:
            cand = f"{title} {kw}"
            if len(cand) <= target:
                title = cand
            else:
                break
    title = title[:ceiling].strip()  # 最终保险：硬上限 140

    # Tags：固定 13，首 Tag=T4#1，其余 T3 补满，每词 ≤20
    tags = []
    if T4:
        tags.append(T4[0][:BUDGET["etsy"]["tag_len"]])
    for kw in T3:
        if len(tags) >= BUDGET["etsy"]["tags"]:
            break
        tags.append(kw[:BUDGET["etsy"]["tag_len"]])
    tags = tags[:BUDGET["etsy"]["tags"]]

    # Description 骨架（6 段占位，不打磨语气）
    desc = [
        f"1. 是什么：{name}（{mat or cat}）",
        f"2. 怎么用：{T3[0] if T3 else ''}",
        f"3. 场景：{T3[1] if len(T3) > 1 else ''}",
        f"4. 材质：{mat or (T4[0] if T4 else '')}",
        f"5. 礼赠：{T3[2] if len(T3) > 2 else ''}",
        "6. 物流售后：待终版按固化惯例填（2–4 weeks / 8–15 days）",
    ]
    return {"title": title, "tags": tags, "desc": desc}


def build_amazon(groups, info):
    T4 = groups.get("T4", [])
    T3 = groups.get("T3", [])
    T2 = groups.get("T2", [])
    T1 = groups.get("T1", [])
    name, cat, mat = info

    # 标题 <75（2026-08 Amazon 新政）：按转化价值优先级贪心填词，不硬截断。
    # 顺序：核心品类名 → T4 高转化 → T2 参数 → T1 红海尾；到 75 字符停，避免砍掉品类名。
    candidates = [name] + T4[:3] + T2[:2] + T1[:2]
    title = ""
    for kw in candidates:
        cand = (title + " " + kw) if title else kw
        if len(cand) < BUDGET["amazon"]["title"]:
            title = cand
        else:
            break

    # 五点（占位，词落位）
    bullets = [
        f"• {T4[0] if T4 else name} — {mat or cat} 材质参数",
        f"• {T3[0] if T3 else ''} 场景适用",
        f"• {T3[1] if len(T3) > 1 else ''} 场景适用",
        f"• {T2[0] if T2 else ''} 参数背书",
        f"• {T2[1] if len(T2) > 1 else ''} 参数背书",
    ]

    # ST <249 字节（T1 为主，空格分隔不重复）
    st = " ".join(dict.fromkeys(T1[:10]))
    while len(st.encode("utf-8")) > BUDGET["amazon"]["st_bytes"] and st:
        st = st.rsplit(" ", 1)[0]

    return {
        "title": title,
        "bullets": bullets,
        "st": st,
        "html": "SEO 占位骨架，终版精修",
        "faq": "SEO 占位骨架，终版精修",
    }


def build_ebay(groups, info):
    T2 = groups.get("T2", [])
    T3 = groups.get("T3", [])
    T4 = groups.get("T4", [])
    T1 = groups.get("T1", [])
    name, cat, mat = info

    # 标题矩阵 ≤80 ×3（不同角度/受众）
    def mk(extra):
        t = " ".join(T2[:2] + [name] + T3[:2] + (extra or []))
        return t[:BUDGET["ebay"]["title"]] if len(t) > BUDGET["ebay"]["title"] else t

    titles = [mk([]), mk([T3[2]] if len(T3) > 2 else []), mk([T4[0]] if T4 else [])]
    titles = [t for t in titles if t]

    itemspecs = {
        "Brand": "定制",
        "Material": T2[0] if T2 else (mat or ""),
        "Type": T3[0] if T3 else "",
        "Style": T4[0] if T4 else "",
    }
    return {
        "titles": titles,
        "itemspecs": itemspecs,
        "bullets": "SEO 占位骨架，终版精修",
        "deschtml": "SEO 占位骨架，终版精修",
        "vero": "VeRO 扫描占位，终版精修",
    }


# ---------------------------------------------------------------------------
# 校验（独立，不依赖任何模型）
# ---------------------------------------------------------------------------
def scan_fields(out: dict, platform: str, risk_db: str) -> list:
    """对生成结果的每个字段做三级风险词确定性扫描（对齐 hermes 合规熔断）。
    返回带 field 标签的 hit 列表，供 classify_risk 归一成状态码。"""
    hits = []
    def scan(label, text):
        for h in gate.scan_risk(text or "", platform, risk_db):
            h2 = dict(h); h2["field"] = label
            hits.append(h2)
    if platform == "etsy":
        scan("title", out.get("title", ""))
        scan("tags", " ".join(out.get("tags", [])))
        scan("desc", "\n".join(out.get("desc", [])))
    elif platform == "amazon":
        scan("title", out.get("title", ""))
        scan("bullets", "\n".join(out.get("bullets", [])))
        scan("st", out.get("st", ""))
        scan("html", out.get("html", ""))
        scan("faq", out.get("faq", ""))
    else:  # ebay
        scan("titles", " | ".join(out.get("titles", [])))
        scan("itemspecs", " ".join(f"{k}={v}" for k, v in out.get("itemspecs", {}).items()))
        scan("bullets", str(out.get("bullets", "")))
        scan("deschtml", str(out.get("deschtml", "")))
        scan("vero", str(out.get("vero", "")))
    return hits


def validate(out: dict, neg: list, platform: str):
    issues = []
    blob = json.dumps(out, ensure_ascii=False).lower()
    for n in neg:
        if n and n.lower() in blob:
            issues.append(f"T5 否定词泄露: {n}")
    b = BUDGET[platform]
    if len(out.get("title", "")) >= b.get("title", 10**9):
        issues.append(f"标题超长（需 <{b['title']}字符，当前{len(out.get('title',''))}）")
    if platform == "etsy":
        if len(out.get("tags", [])) > b["tags"]:
            issues.append(f"Tags 超 {b['tags']} 个")
        for t in out.get("tags", []):
            if len(t) > b["tag_len"]:
                issues.append(f"Tag 超 {b['tag_len']} 字符: {t}")
    if platform == "amazon":
        if len(out.get("st", "").encode("utf-8")) > b["st_bytes"]:
            issues.append(f"ST 超 {b['st_bytes']} 字节")
    return issues


# ---------------------------------------------------------------------------
# 输出
# ---------------------------------------------------------------------------
def render_md(spu, platform, out, neg, issues):
    L = []
    L.append(f"# {spu} · {platform.upper()} 初版 Listing（v1 · SEO 骨架）\n")
    L.append("> ⚠️ 本稿为 SEO 骨架，待终版精修后上架。不可直接上架。\n")
    if platform == "etsy":
        L.append(f"**标题_初版**（{len(out['title'])}/{BUDGET['etsy']['title']}）\n{out['title']}\n")
        L.append(f"**Tags_初版**（{len(out['tags'])}/{BUDGET['etsy']['tags']}）")
        L.append(" | ".join(out["tags"]) + "\n")
        L.append("**Desc_初版**（6 段骨架）\n" + "\n".join(out["desc"]) + "\n")
    elif platform == "amazon":
        L.append(f"**标题_初版**（{len(out['title'])}/{BUDGET['amazon']['title']}）\n{out['title']}\n")
        L.append("**五点_初版**\n" + "\n".join(out["bullets"]) + "\n")
        L.append(f"**ST_初版**（{len(out['st'].encode('utf-8'))}/{BUDGET['amazon']['st_bytes']}B）\n{out['st']}\n")
        L.append(f"**HTML_初版**：{out['html']}\n**FAQ_初版**：{out['faq']}\n")
    else:
        L.append("**标题矩阵_初版**")
        for i, t in enumerate(out["titles"], 1):
            L.append(f"  Title {i}（{len(t)}/{BUDGET['ebay']['title']}）: {t}")
        L.append("")
        L.append("**ItemSpecs_初版**")
        for k, v in out["itemspecs"].items():
            L.append(f"  {k}={v}")
        L.append(f"\n**Bullets_初版**：{out['bullets']}\n**DescHTML_初版**：{out['deschtml']}\n**VeRO_初版**：{out['vero']}\n")
    L.append(f"**T5 否定词封杀**：{len(neg)} 个已排除" + (" ⚠️ 有泄露！" if any('泄露' in i for i in issues) else " ✅ 干净") + "\n")
    L.append("**校验**：" + ("✅ 通过" if not issues else "❌ " + "；".join(issues)) + "\n")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 中间产物 bundle（跨平台复用，避免重复取词与商品理解漂移）
# ---------------------------------------------------------------------------
def bundle_path(out_dir: str, spu: str) -> str:
    return os.path.join(out_dir, f"{spu}_listing_bundle.json")


def make_bundle_payload(spu: str, info, groups: dict, platform: str, existing: dict) -> dict:
    """构造 bundle 中间产物 payload（供落盘 / 飞书字段复用同一份）。"""
    name, cat, mat = info
    # 意图分层：把每个 tier 的词打购买意图标签，附进 bundle（供终版/飞书消费）
    intent_plan = {}
    for tier in ("T4", "T3", "T2", "T1"):
        intent_plan[tier] = [{"kw": k, "intent": classify_intent(k)} for k in groups.get(tier, [])]
    return {
        "spu": spu,
        "product_truth": {"name": name, "category": cat, "material": mat},
        "keyword_plan": {
            "source_platform": "amazon",
            "T4": groups.get("T4", []),
            "T3": groups.get("T3", []),
            "T2": groups.get("T2", []),
            "T1": groups.get("T1", []),
            "intent": intent_plan,
        },
        "visual_tone": existing.get("visual_tone"),
        "generated_platforms": list(dict.fromkeys(existing.get("generated_platforms", []) + [platform])),
        "created_at": existing.get("created_at") or datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def save_bundle(out_dir: str, spu: str, info, groups: dict, platform: str):
    """首次生成某平台时落盘中间产物；后续平台追加 generated_platforms。"""
    bp = bundle_path(out_dir, spu)
    existing = {}
    if os.path.exists(bp):
        try:
            with open(bp, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            pass
    payload = make_bundle_payload(spu, info, groups, platform, existing)
    with open(bp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"  ✅ 已写 bundle {bp}")


def load_bundle(out_dir: str, spu: str) -> dict:
    """--load-bundle 时读取已存关键词计划，跳过取词。"""
    bp = bundle_path(out_dir, spu)
    with open(bp, "r", encoding="utf-8") as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="Listing 初版（v1）纯规则 SEO 骨架生成器")
    ap.add_argument("--spu", required=True, help="SPU ID，如 S3-04")
    ap.add_argument("--platform", required=True, choices=["etsy", "amazon", "ebay"])
    ap.add_argument("--keyword-platform", default="amazon", choices=["amazon", "etsy", "ebay"],
                    help="取词口径（默认 amazon，因 Amazon ST 每个变体都有，所需精准词量最大）")
    ap.add_argument("--load-bundle", action="store_true",
                    help="读取已存在的 {out}/{SPU}_listing_bundle.json 词计划，跳过取词")
    ap.add_argument("--format", default="md", choices=["md", "json"])
    ap.add_argument("--out", default="output", help="本地产出目录")
    ap.add_argument("--ledger", default=None,
                    help="防蚕食账本 JSON 路径（默认 ~/.workbuddy/data/opc-seo/...，可用 OPC_SEO_LEDGER 覆盖）")
    ap.add_argument("--write-feishu", action="store_true", help="回写飞书 Base A（断连安全跳过）")
    ap.add_argument("--emit-feishu-field", action="store_true",
                    help="打印「飞书字段就绪 payload」（bundle 整体作为单字段值，供直接粘贴写入）")
    ap.add_argument("--dry-run", action="store_true", help="仅校验不落盘（默认落盘）")
    args = ap.parse_args()

    # 账本路径：--ledger 优先写入环境变量，供 cannibalization_ledger 读取
    if args.ledger:
        os.environ["OPC_SEO_LEDGER"] = os.path.abspath(args.ledger)

    print(f"▶ gen_v1: spu={args.spu} platform={args.platform}")

    # 取词：默认按 Amazon 标准；若 bundle 存在则可直接复用
    if args.load_bundle:
        bundle = load_bundle(args.out, args.spu)
        plan = bundle["keyword_plan"]
        groups = {
            "T4": plan.get("T4", []),
            "T3": plan.get("T3", []),
            "T2": plan.get("T2", []),
            "T1": plan.get("T1", []),
        }
        info = (
            bundle["product_truth"].get("name", args.spu),
            bundle["product_truth"].get("category", ""),
            bundle["product_truth"].get("material", ""),
        )
        print(f"  📦 已加载 bundle，跳过取词（来源={plan.get('source_platform','unknown')}）")
    else:
        groups = coverage(args.spu, args.keyword_platform)
        info = spu_info(args.spu)

    neg = negatives(args.spu)
    groups = filter_neg(groups, neg)   # 取词阶段即剔除 T5 根（SOP 铁律）

    # ---- 防蚕食账本：同类 SKU 主词唯一化（seo-content-team 思路吸收）----
    # 在取词/填槽前，把本 SPU 的高意图主词（T4 首位）登记到账本；
    # 若同类已被其他 SPU 占用，则顺延到下一个未占用 T4，并提到 T4 首位让 build_* 自然采用。
    import cannibalization_ledger as cl
    cat = (info[1] or "uncategorized").strip()
    t4 = groups.get("T4", [])
    led_conflict = False
    led_assigned = t4[0] if t4 else ""
    if t4:
        led = cl.choose_main_word(cat, args.spu, t4)
        led_assigned = led.get("assigned") or t4[0]
        if led_assigned and led_assigned != t4[0]:
            groups["T4"] = [led_assigned] + [w for w in t4 if w != led_assigned]
        led_conflict = bool(led.get("conflict"))
        if led_conflict:
            print(f"  ⚠️ 防蚕食冲突：主词「{led_assigned}」同类({cat})已被占满，"
                  f"已强制分配并告警——请人工复核或换主词")
        elif led.get("reused"):
            print(f"  🛡️ 防蚕食：主词「{led_assigned}」沿用既有登记（同类={cat}）")
        else:
            print(f"  🛡️ 防蚕食：主词「{led_assigned}」已登记（同类={cat}），同类唯一 ✅")

    # 意图分层：T4 首词保持防蚕食主词，余下按购买意图重排（transactional 优先进标题）
    t4_all = groups.get("T4", [])
    if len(t4_all) > 1:
        groups["T4"] = [t4_all[0]] + rank_by_intent(t4_all[1:])

    builders = {"etsy": build_etsy, "amazon": build_amazon, "ebay": build_ebay}
    out = builders[args.platform](groups, info)
    issues = validate(out, neg, args.platform)

    # 本地产出
    if not args.dry_run:
        os.makedirs(args.out, exist_ok=True)
        base = os.path.join(args.out, f"{args.spu}_{args.platform}_v1")
        if args.format == "json":
            payload = {
                "spu": args.spu, "platform": args.platform,
                "fields": out, "negatives_count": len(neg),
                "validation": issues, "note": "SEO 骨架，待终版精修",
            }
            with open(base + ".json", "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            print(f"  ✅ 已写 {base}.json")
        else:
            with open(base + ".md", "w", encoding="utf-8") as f:
                f.write(render_md(args.spu, args.platform, out, neg, issues))
            print(f"  ✅ 已写 {base}.md")
        # 中间产物 bundle：商品真实信息 + 词计划 + 已生成平台记录
        save_bundle(args.out, args.spu, info, groups, args.platform)

    # 飞书回写（可选，断连安全跳过）
    if args.write_feishu:
        sys.path.insert(0, HERE)
        try:
            import feishu_write
            feishu_write.write_v1(args.spu, args.platform, out, neg)
            print("  ✅ 飞书回写成功")
        except Exception as e:
            print(f"  ⚠️ 飞书回写跳过（连接/配置不可用，本地产出不受影响）: {type(e).__name__}: {e}")

    # 汇总
    print(f"  词数: T4={len(groups.get('T4',[]))} T3={len(groups.get('T3',[]))} "
          f"T2={len(groups.get('T2',[]))} T1={len(groups.get('T1',[]))} | T5否定={len(neg)}")
    idist = intent_distribution(groups)
    print(f"  意图分层(T4): "
          f"高购买={idist.get('T4',{}).get('transactional',0)} "
          f"商业={idist.get('T4',{}).get('commercial',0)} "
          f"信息={idist.get('T4',{}).get('informational',0)} "
          f"（标题已按高意图优先进位）")

    # ---- hermes 分层闸门：吐状态码 + 三级熔断 ----
    risk_db = gate.resolve_risk_db(ROOT)
    risk_hits = scan_fields(out, args.platform, risk_db)
    risk_status, risk_stats, _ = gate.classify_risk(risk_hits)

    # 各检查项归类（对齐 hermes 闸门栈）
    t5_ok = not any("T5 否定词泄露" in i for i in issues)
    char_issues = [i for i in issues if ("超长" in i) or ("Tags 超" in i) or ("Tag 超" in i) or ("ST 超" in i)]
    char_ok = not char_issues
    cannib_ok = not led_conflict

    # 归总状态码：一级/T5泄露 → MELTDOWN（硬阻断）；二级/字符超限 → CRITICAL_STOP（需确认）；否则 OK
    if (not t5_ok) or risk_status == gate.STATUS["MELTDOWN"]:
        final = gate.STATUS["MELTDOWN"]
    elif (not char_ok) or risk_status == gate.STATUS["CRITICAL_STOP"] or (not cannib_ok):
        final = gate.STATUS["CRITICAL_STOP"]
    else:
        final = gate.STATUS["OK"]

    checks = [
        ("T5 否定词封杀", t5_ok, f"{len(neg)} 个已排除" if t5_ok else "有泄露！"),
        ("字符门禁", char_ok, "" if char_ok else "；".join(char_issues)),
        ("风险词三级熔断", risk_status == gate.STATUS["OK"],
         f"🔴{risk_stats['fatal']}/🟠{risk_stats['high']}/🟡{risk_stats['medium']}（平台={args.platform}）"),
        ("防蚕食主词唯一", cannib_ok, f"主词={led_assigned}" if cannib_ok else "同类冲突，需人工复核"),
    ]
    print(gate.render_gate(f"gen_v1 {args.spu}/{args.platform}", final, checks))
    if risk_hits:
        print(gate.render_risk_block(risk_hits, risk_stats, "  "))

    # ---- 两层滤网·第二层（软判定兜底，不阻断）----
    # 无模型时的轻量确定性代理；完整语义判定交给人/终版 Qwen 按 SOFT_RUBRIC 终审。
    full_blob = json.dumps(out, ensure_ascii=False)
    soft = gate_soft.soft_heuristics(full_blob)
    print("\n" + gate_soft.render_soft_block(soft))

    # ---- 飞书字段就绪 payload（bundle 整体作为单字段值，直接粘贴写入）----
    if args.emit_feishu_field:
        bp = bundle_path(args.out, args.spu)
        existing = {}
        if os.path.exists(bp):
            try:
                with open(bp, "r", encoding="utf-8") as f:
                    existing = json.load(f)
            except Exception:
                pass
        payload = make_bundle_payload(args.spu, info, groups, args.platform, existing)
        raw = json.dumps(payload, ensure_ascii=False, indent=2)
        print(f"\n📋 飞书字段就绪 payload（建议落点：表2 `SHARED_CONTEXT` 或新增长文本字段 `listing_bundle`）：")
        print(f"   字段值（整段粘贴，写入须你逐条授权）：\n{raw}")

    # 退出码：MELTDOWN → 2（硬阻断，禁止发布）；其余 → 0（CRITICAL_STOP 由人工桥梁按闸门确认）
    sys.exit(2 if final == gate.STATUS["MELTDOWN"] else 0)


if __name__ == "__main__":
    main()
