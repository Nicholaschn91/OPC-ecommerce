#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify-ledger.py — 终版写飞书前的统一闸门（对齐 hermes 分层闸门栈）

作用：终版 Qwen3.8-Max 产出 clean.md 后、回写飞书前，做一次收口自检：
  1. 【防蚕食】本商品在账本中已登记的唯一主词，是否仍出现在【标题】中（防终版漂移丢掉主词）；
     同类 sibling 已占主词，是否抢占了【标题前 40 字符】高权重区（防同店互抢）。
  2. 【合规熔断】对 full text 做三级风险词确定性扫描（risk_keywords.db）：
     一级（致命）→ MELTDOWN（硬阻断，禁止发布）；二级（高危）→ CRITICAL_STOP（需确认）。
  3. 【回读校验】对各期望字段做"非空存在性"检查（对齐 hermes 铁律#8 字段级回读）。

吐 hermes 状态码 OK / CRITICAL_STOP / MELTDOWN，供人工桥梁/主控按码路由。
非致命（不修改任何文件）：只打印告警并返回非 0 供 agent 决策是否打回重跑。
标题提取为启发式；若已知确切标题请用 --title 直接传入以提高准确度。

依赖：
  - 初版 scripts/cannibalization_ledger.py（单一事实源，经相对路径引入）
  - 初版 scripts/gate.py（hermes 状态码 + 三级熔断扫描，经相对路径引入）
用法：
  python verify-ledger.py --spu S3-04 --in clean.md --platform amazon [--title "确切标题"] [--ledger path]
"""
import argparse
import os
import re
import sys


def read_text(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def redact_non_copy(md):
    """剔除非顾客文案区，仅保留真实上架文案供风险扫描：
      - 视觉 Prompt（Step 4）是给生图模型的指令，非上架文案；
      - BASE_MATERIAL 是商品元数据（含 forbidden_words 禁用词清单），非违规文案。
    二者若纳入扫描会造成上下文误报（如 genuine 命中 forbidden_words 清单）。"""
    m4 = re.search(r'Step\s*4\b.*?(?=Step\s*5\b)', md, re.IGNORECASE | re.DOTALL)
    if m4:
        md = md[:m4.start()] + md[m4.end():]
    mb = re.search(r'BASE_MATERIAL\b.*$', md, re.IGNORECASE | re.DOTALL)
    if mb:
        md = md[:mb.start()]
    return md


def heuristic_title(md, spu):
    """从 clean.md 启发式抽取标题候选（仅用于告警，不保证 100% 命中）。"""
    # 优先：显式标记行 "标题" / "Title" : xxx
    m = re.search(r'(?:标题|Title)\s*[:：]\s*(.+)', md, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"').strip("'")
    # 次选：Step 1 区段内第一条像标题的行
    seg = md
    s1 = re.search(r'Step\s*1', md, re.IGNORECASE)
    s2 = re.search(r'Step\s*2', md, re.IGNORECASE)
    if s1:
        start = s1.end()
        end = s2.start() if s2 else start + 1200
        seg = md[start:end]
    for line in seg.splitlines():
        line = line.strip().lstrip('>').strip()
        if 8 <= len(line) <= 200 and not line.startswith(('·', '-', '*', '#', '|')):
            # 去掉常见前缀
            line = re.sub(r'^[\d\.\)\s]+', '', line)
            if len(line) >= 8:
                return line
    return ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--spu', required=True, help='商品 SPU（须与账本登记一致）')
    ap.add_argument('--in', dest='inp', required=True, help='终版 clean.md 路径')
    ap.add_argument('--platform', default='amazon', choices=['amazon', 'etsy', 'ebay'],
                    help='目标平台（决定三级熔断扫描与回读字段口径）')
    ap.add_argument('--title', default=None, help='确切标题（可选，传入则跳过启发式抽取）')
    ap.add_argument('--category', default=None, help='商品类目（可选，账本未登记时辅助）')
    ap.add_argument('--ledger', default=None, help='账本 JSON 路径（默认 ~/.workbuddy/data/opc-seo/...）')
    args = ap.parse_args()

    if args.ledger:
        os.environ["OPC_SEO_LEDGER"] = os.path.abspath(args.ledger)

    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # multi-agent-sop
    LEDGER_SKILL = os.path.join(ROOT, "listing-v1-seo-builder", "scripts")
    if LEDGER_SKILL not in sys.path:
        sys.path.insert(0, LEDGER_SKILL)
    try:
        import cannibalization_ledger as cl
        import gate as gate
        import gate_soft as gate_soft
    except Exception as e:
        print(f"🔴 无法引入模块（{type(e).__name__}: {e}），跳过校验")
        sys.exit(2)

    reg = cl.lookup_spu(args.spu)
    cat = args.category or (reg.get("category") if reg else None)
    if not reg and not cat:
        print("🟡 账本未登记本 SPU 且无类目，无可校验对象，跳过")
        sys.exit(0)

    md = read_text(args.inp)
    title = args.title if args.title else heuristic_title(md, args.spu)
    if not title:
        print("🟡 未能从 clean.md 抽取到标题，跳过校验（可改用 --title 传入）")
        sys.exit(0)
    print(f"🔎 校验标题（启发式）: {title}")

    # 扫描域限定到顾客文案（剔除视觉 Prompt 与 BASE_MATERIAL 元数据，防上下文误报）
    scan_text = redact_non_copy(md)

    problems = []
    # 检查 1：已登记主词是否仍在标题
    if reg and reg.get("main_word"):
        mw = reg["main_word"].lower()
        if mw not in title.lower():
            problems.append(
                f"🔴 已登记唯一主词『{reg['main_word']}』未出现在标题中——终版可能已漂移，"
                f"请确认是否仍以其为核心焦点词。")
        else:
            print(f"✅ 已登记主词『{reg['main_word']}』仍出现在标题中")

    # 检查 2：同类 sibling 已占词是否抢占标题高权重区（前 40 字符）
    if cat:
        sibs = cl.siblings(cat, args.spu)
        head = title[:40].lower()
        for s in sibs:
            w = (s.get("main_word") or "").lower()
            if not w:
                continue
            if w in head:
                problems.append(
                    f"🔴 同类 sibling 已占主词『{s['main_word']}』出现在标题前 40 字符高权重区——"
                    f"存在同店互抢风险，建议替换为本商品唯一主词或同义长尾。")
            elif w in title.lower():
                problems.append(
                    f"🟡 同类 sibling 已占主词『{s['main_word']}』出现在标题中（非高权重区）——"
                    f"建议核查是否作为核心焦点词使用。")

    # 检查 3：合规熔断（三级风险词确定性扫描，对齐 hermes；扫描域已限定顾客文案）
    risk_db = gate.resolve_risk_db(ROOT)
    risk_hits = gate.scan_risk(scan_text, args.platform, risk_db)
    risk_status, risk_stats, _ = gate.classify_risk(risk_hits)
    if risk_status == gate.STATUS["MELTDOWN"]:
        for h in risk_hits:
            if h["level"] == gate.LEVEL_FATAL:
                problems.append(
                    f"🔴 致命风险词『{h['hit']}』（{h['risk_type']}）命中——必须替换为合规替代词"
                    f"{('：'+h['alternative']) if h['alternative'] else ''}后才可发布")
    elif risk_status == gate.STATUS["CRITICAL_STOP"]:
        for h in risk_hits:
            if h["level"] == gate.LEVEL_HIGH:
                problems.append(
                    f"🟠 高危风险词『{h['hit']}』（{h['risk_type']}）命中——需用户确认，"
                    f"建议替换{('：'+h['alternative']) if h['alternative'] else ''}")

    # 检查 3.5：两层滤网·第二层（软判定兜底，不阻断）
    # 终版由 Qwen3.8-Max 生成，软违规（过度优化/AI痕迹/灰区）硬规则枚举不完；
    # 此处跑轻量确定性代理，只出 review 信号，最终由人/LLM 按 SOFT_RUBRIC 终审。
    soft = gate_soft.soft_heuristics(md)
    print("\n" + gate_soft.render_soft_block(soft))
    if soft:
        print("  📌 软层提醒：终版 Qwen 应已按 SOFT_RUBRIC 自检；上述为启发式兜底信号，非定论，请人工终审。")

    # 检查 4：回读校验（字段级存在性，对齐 hermes 铁律#8）
    field_rules = {
        "amazon": [("标题", r'(?:标题|Title)\s*[:：]'), ("五点/Bullets", r'(?:五点|Bullet|·\s)'),
                   ("ST/Search Terms", r'(?:Search Terms|ST|搜索词)'), ("Description", r'(?:Description|描述)')],
        "etsy":   [("标题", r'(?:标题|Title)\s*[:：]'), ("Tags", r'(?:Tags|标签)'), ("Description", r'(?:Description|描述)')],
        "ebay":   [("标题矩阵", r'(?:标题矩阵|Title\s*\d)'), ("Bullets", r'(?:Bullets|要点)'),
                   ("DescHTML", r'(?:DescHTML|描述)'), ("VeRO", r'VeRO')],
    }
    missing = []
    for label, pat in field_rules.get(args.platform, []):
        if label == "标题":
            # 兼容 "Step 1：标题优化方案" 格式：显式标题标签或确切标题串出现即视为存在
            present = re.search(pat, md, re.IGNORECASE) or (args.title and args.title in md)
        else:
            present = re.search(pat, md, re.IGNORECASE)
        if not present:
            missing.append(label)
    if missing:
        problems.append(f"🟡 回读：以下期望字段未在 clean.md 检出（可能命名差异，需人工确认）：{', '.join(missing)}")

    # ---- 归总 hermes 状态码 ----
    if risk_status == gate.STATUS["MELTDOWN"] or any(p.startswith("🔴") for p in problems):
        final = gate.STATUS["MELTDOWN"]
    elif risk_status == gate.STATUS["CRITICAL_STOP"] or any(p.startswith("🟠") for p in problems) or missing:
        final = gate.STATUS["CRITICAL_STOP"]
    else:
        final = gate.STATUS["OK"]

    checks = [
        ("防蚕食主词唯一", not any(p.startswith(("🔴", "🟠")) for p in problems[:2]) and not missing,
         f"主词={reg.get('main_word') if reg else '未登记'}"),
        ("合规熔断（三级）", risk_status == gate.STATUS["OK"],
         f"🔴{risk_stats['fatal']}/🟠{risk_stats['high']}/🟡{risk_stats['medium']}（平台={args.platform}）"),
        ("回读字段完整性", not missing, "全部期望字段检出" if not missing else f"缺：{', '.join(missing)}"),
    ]
    print(gate.render_gate(f"verify-ledger {args.spu}/{args.platform}", final, checks))
    if risk_hits:
        print(gate.render_risk_block(risk_hits, risk_stats, "  "))

    if problems:
        print("\n".join(problems))
        print("\n⚠️ 终版写飞书前发现闸门问题，建议打回重跑或人工修正后再写飞书。")
        sys.exit(2 if final == gate.STATUS["MELTDOWN"] else 1)
    print("✅ 终版闸门通过（防蚕食 + 合规三级 + 字段回读 均无阻断）")
    sys.exit(0)


if __name__ == '__main__':
    main()
