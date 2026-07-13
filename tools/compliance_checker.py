#!/usr/bin/env python3
"""
跨境电商 Listing 合规审核工具

用法:
  python compliance_checker.py --platform amazon --text "Bullet: Best non-toxic wallet..." 
  python compliance_checker.py --platform ebay --file listing.txt
  python compliance_checker.py --help

依赖: risk_keywords.db (来自 multi-agent-sop)

⚠️  DEPRECATED: 本工具已废弃，仅作为离线兜底/调试用。
生产环境合规审核请使用 Dify 合规智能体 (skills/dify-compliance/)：
  - 三层扫描：关键词库 + 平台规则 + LLM 语义
  - 结构化输出 + 飞书回写 + 事件发布
  - 详见 agents/dify-compliance/AGENT.md
"""

import sqlite3
import json
import sys
import argparse
import os
import re
from pathlib import Path

# ──── Config ──────────────────────────────────────────────
RISK_DB = Path(os.path.expanduser("~/.workbuddy/skills/multi-agent-sop/risk_keywords.db"))

# 字符数门禁
CHAR_LIMITS = {
    "amazon": {
        "title": 80,
        "bullet": 200,
        "html": 2000,
        "search_terms_bytes": 249,
        "faq": 100,
    },
    "ebay": {
        "title": 80,
    },
    "etsy": {
        "title": 140,
        "tag": 20,
        "tags_count": 13,
    },
}

# 禁用极限词库（通用）
BANNED_WORDS = {
    "best": "premium",
    "top": "popular",
    "#1": "top-rated",
    "first": "preferred",
    "perfect": "exquisite",
    "ultimate": "well-crafted",
    "absolute": "reliable",
    "cure": "helps soothe",
    "treat": "support",
    "heal": "designed to relieve",
    "prevent": "helps protect",
    "antibacterial": "easy to clean",
    "antimicrobial": "hygienic",
    "non-toxic": "BPA-free",
    "safe": "meets safety standards",
    "eco-friendly": "sustainably sourced",
    "organic": "organically grown",
}

# Amazon 专项禁用词 + 替换
AMAZON_BANNED = {
    **BANNED_WORDS,
    "mildew-resistant": "hygienic",
    "anti-mold": "breathable",
    "sanitize": "easy-to-clean",
    "pest-repellent": "dust-proof",
    "allergy-free": "fresh",
    "bacteria-resistant": "hygienic",
    "Velcro": "hook and loop tapes",
    "lifetime warranty": "12-month quality support",
    "satisfaction guaranteed": "designed to meet your high standards",
    "free shipping": "ships from US warehouse",
    "best seller": "popular choice",
    "fda approved": "meets FDA compliance standards",
    "medical-grade": "professional-grade",
    "clinical proven": "tested and verified",
    "bpa-free": "food-grade safe materials",
}

# eBay 专项
EBAY_VERO_PATTERN = re.compile(r"\bfor\s+([A-Z][a-zA-Z]*)\b", re.IGNORECASE)
EBAY_FITS_REPLACE = "Fits \\1"

# Etsy 专项
ETSY_IP_BLACKLIST = [
    "Disney", "Mickey", "Minnie", "Frozen", "Star Wars",
    "Marvel", "Avengers", "Spider-Man", "Iron Man",
    "Harry Potter", "Barbie", "Taylor Swift", "Nike",
    "Peppa Pig", "Pinkfong",
]
ETSY_MEDICAL_BLACKLIST = ["cure", "cancer", "treat", "anxiety relief"]
ETSY_BANNED_PRODUCTS = ["ivory", "amber teething necklace"]

# ──── Helpers ─────────────────────────────────────────────
def load_risk_keywords(db_path: Path):
    """从 risk_keywords.db 加载全部风险词"""
    if not db_path.exists():
        print(f"[WARN] 风险词库未找到: {db_path}", file=sys.stderr)
        return []
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("""
        SELECT keyword, alternative, level, platform, risk_type FROM risk_keywords
    """)
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "keyword": r[0],
            "alternative": r[1],
            "level": r[2],
            "platform": r[3],
            "risk_type": r[4],
        }
        for r in rows
    ]

def scan_risk_words(text: str, risk_db: list, platform: str):
    """扫描文本中的风险词"""
    hits = []
    lower_text = text.lower()
    for r in risk_db:
        kw = r["keyword"].lower()
        if kw in lower_text:
            if r["platform"] in ("all", platform):
                hits.append({
                    "keyword": r["keyword"],
                    "alternative": r["alternative"] or "",
                    "level": r["level"],
                    "risk_type": r["risk_type"],
                })
    return hits

def scan_banned_words(text: str, platform: str):
    """扫描禁用极限词"""
    hits = []
    lower_text = text.lower()
    word_dict = AMAZON_BANNED if platform == "amazon" else BANNED_WORDS
    for banned, replacement in word_dict.items():
        pattern = re.compile(r"\b" + re.escape(banned.lower()) + r"\b")
        if pattern.search(lower_text):
            hits.append({"word": banned, "replacement": replacement})
    return hits

# Amazon 专项: 材质空泛词检测
AMAZON_MATERIAL_GENERIC = [
    "high quality material", "premium material", "good quality",
    "fine material", "top material", "best material",
    "quality fabric", "durable material",
]

AMAZON_MATERIAL_DICT = {
    "实木": "durable solid wood construction, resists scratches, warping-resistant",
    "胡桃木": "solid walnut, retains its elegant grain for years",
    "橡木": "solid oak, wear-resistant and sturdy",
    "竹": "sustainably-sourced natural bamboo, splinter-free smooth surface, water-resistant",
    "亚克力": "high-clarity acrylic, shatter-resistant and scratch-proof",
    "304不锈钢": "food-grade 304 stainless steel, rust and corrosion resistant, dishwasher safe",
    "316不锈钢": "food-grade 316 stainless steel, superior corrosion resistance",
    "头层牛皮": "premium genuine leather, wear-and-tear resistant, buttery soft hand feel",
    "真皮": "genuine leather, beautifully retains its silhouette with daily use",
    "硅胶": "food-grade silicone, 100% BPA-free, heat-insulating and non-slip",
    "食品级硅胶": "food-grade silicone material, odorless, dishwasher safe",
    "牛津布": "waterproof and tear-resistant oxford fabric, UV-proof outdoor protection",
    "牛津面料": "reinforced oxford fabric, durable against harsh weather",
}

# Amazon 商标/IP 词（含替换）
AMAZON_IP_BLACKLIST = {
    "Velcro": "hook and loop tapes",
    "Cordura": "heavy-duty tear-resistant nylon",
    "Onesie": "one-piece bodysuit",
    "Frisbee": "flying disc",
    "Lego": "building blocks",
    "GoPro": "action camera mount",
    "Yeti": "insulated tumbler",
}

# Amazon 兼容性品牌（禁止 "For [Brand]" 直描）
AMAZON_COMPAT_BRANDS = [
    "iPhone", "iPad", "MacBook", "AirPods", "MagSafe",
    "Apple Watch", "Samsung Galaxy", "Google Pixel",
]

# ──── Main Functions ──────────────────────────────────────

def check_character_limits(text: str, platform: str):
    """检查字符数 — 支持多字段解析"""
    limits = CHAR_LIMITS.get(platform, {})
    results = []

    if platform == "amazon":
        # 尝试从文本中解析字段: [TITLE]\n... / [BULLET1]\n... / [HTML]\n... / [ST]\n... / [FAQ1]\n...
        fields = {}
        current_field = "mixed"
        for line in text.split("\n"):
            m = re.match(r"^\s*\[(TITLE|BULLET[1-5]|HTML|ST|FAQ[1-5])\]\s*$", line.strip(), re.IGNORECASE)
            if m:
                current_field = m.group(1).upper()
                fields[current_field] = ""
            else:
                fields[current_field] = fields.get(current_field, "") + line + "\n"

        # 检查标题
        if "TITLE" in fields:
            title_len = len(fields["TITLE"].strip())
            results.append({"field": "标题", "current": title_len, "limit": 80, "pass": title_len <= 80})

        # 检查每条 Bullet
        for i in range(1, 6):
            key = f"BULLET{i}"
            if key in fields:
                blen = len(fields[key].strip())
                results.append({"field": f"Bullet {i}", "current": blen, "limit": 200, "pass": blen <= 200})

        # 检查 HTML 描述
        if "HTML" in fields:
            hlen = len(fields["HTML"].strip())
            results.append({"field": "HTML 描述", "current": hlen, "limit": 2000, "pass": hlen <= 2000})

        # 检查 Search Terms
        if "ST" in fields:
            st_bytes = len(fields["ST"].strip().encode("utf-8"))
            results.append({"field": "Search Terms", "current": st_bytes, "limit": 249, "unit": "bytes", "pass": st_bytes < 249})

        # 检查每条 FAQ
        for i in range(1, 6):
            key = f"FAQ{i}"
            if key in fields:
                flen = len(fields[key].strip())
                results.append({"field": f"FAQ {i}", "current": flen, "limit": 100, "pass": flen <= 100})

    if not results:
        # 无结构化标签时，回退到全文简单检查
        title_limit = limits.get("title")
        if title_limit:
            results.append({"field": "全文(len)", "current": len(text), "limit": title_limit, "pass": len(text) <= title_limit})

    return results


def check_amazon_material(text: str):
    """检查材质空泛词"""
    issues = []
    lower_text = text.lower()
    for generic in AMAZON_MATERIAL_GENERIC:
        if generic in lower_text:
            issues.append({
                "rule": "材质空泛词",
                "detail": f"检测到空泛材质描述: '{generic}'",
                "fix": "替换为具体物理翻译，如 'durable solid wood construction, resists scratches'",
            })
            break  # 只报一次
    return issues


def check_amazon_ip(text: str):
    """检查 Amazon 商标/IP 侵权"""
    issues = []
    lower_text = text.lower()
    for banned_ip, replacement in AMAZON_IP_BLACKLIST.items():
        if banned_ip.lower() in lower_text:
            issues.append({
                "rule": "Amazon 商标侵权",
                "detail": f"检测到受保护商标: {banned_ip}",
                "fix": f"替换为 '{replacement}'",
            })
    return issues


def check_amazon_compat(text: str):
    """检查 Amazon 兼容性表述 — 禁止 'For [Brand]'"""
    issues = []
    lower_text = text.lower()
    for brand in AMAZON_COMPAT_BRANDS:
        brand_lower = brand.lower()
        if brand_lower in lower_text:
            for m in re.finditer(rf"for\s+{re.escape(brand_lower)}", lower_text):
                issues.append({
                    "rule": "Amazon 兼容性表述",
                    "detail": f"检测到 'for {brand}' 格式",
                    "fix": f"替换为 'Compatible with {brand}' 或 'Fits {brand}'",
                })
    return issues


def check_ebay_vero(text: str):
    """eBay VeRO 兼容性检查"""
    issues = []
    matches = EBAY_VERO_PATTERN.finditer(text)
    for m in matches:
        start = max(0, m.start() - 20)
        prefix = text[start : m.start()].lower().strip()
        if not any(prefix.endswith(w) for w in ["fits ", "compatible with "]):
            issues.append({
                "rule": "VeRO 兼容性",
                "detail": f"检测到 'For {m.group(1)}' 格式",
                "fix": f"替换为 'Fits {m.group(1)}' 或 'Compatible with {m.group(1)}'",
            })
    return issues


def check_etsy_ip(text: str):
    """Etsy IP 侵权检查"""
    issues = []
    lower_text = text.lower()
    for ip_word in ETSY_IP_BLACKLIST:
        if ip_word.lower() in lower_text:
            issues.append({
                "rule": "Etsy IP 侵权",
                "detail": f"检测到受保护 IP 词: {ip_word}",
                "fix": f"删除或替换 '{ip_word}'",
            })
    for med_word in ETSY_MEDICAL_BLACKLIST:
        if med_word in lower_text:
            issues.append({
                "rule": "Etsy 医疗宣称",
                "detail": f"检测到医疗宣称词: {med_word}",
                "fix": f"替换为 'helps soothe' 或 'designed to support'",
            })
    for prod in ETSY_BANNED_PRODUCTS:
        if prod in lower_text:
            issues.append({
                "rule": "Etsy 违禁品",
                "detail": f"检测到违禁品词: {prod}",
                "fix": "删除该词汇",
            })
    return issues


def run_compliance(text: str, platform: str):
    """执行全维度合规审核"""
    risk_db = load_risk_keywords(RISK_DB)

    report = {
        "platform": platform,
        "overall": "PASS",
        "risk_keywords": [],
        "banned_words": [],
        "platform_violations": [],
        "character_limits": [],
        "summary": "",
    }

    # 1. 风险词扫描
    risk_hits = scan_risk_words(text, risk_db, platform)
    fatal = sum(1 for h in risk_hits if "一级" in h["level"])
    high = sum(1 for h in risk_hits if "二级" in h["level"])
    mid = sum(1 for h in risk_hits if "三级" in h["level"])

    for h in risk_hits:
        report["risk_keywords"].append({
            "keyword": h["keyword"],
            "level": h["level"],
            "replacement": h["alternative"],
            "risk_type": h["risk_type"],
        })

    # 2. 禁用极限词
    banned_hits = scan_banned_words(text, platform)
    for b in banned_hits:
        report["banned_words"].append({
            "word": b["word"],
            "replacement": b["replacement"]
        })

    # 3. 平台专属合规
    if platform == "amazon":
        mat_issues = check_amazon_material(text)
        report["platform_violations"].extend(mat_issues)
        ip_issues = check_amazon_ip(text)
        report["platform_violations"].extend(ip_issues)
        compat_issues = check_amazon_compat(text)
        report["platform_violations"].extend(compat_issues)
        report["character_limits"] = check_character_limits(text, platform)
    elif platform == "ebay":
        vero_issues = check_ebay_vero(text)
        report["platform_violations"].extend(vero_issues)
    elif platform == "etsy":
        etsy_issues = check_etsy_ip(text)
        report["platform_violations"].extend(etsy_issues)

    # 4. 判定
    if fatal_count > 0:
        report["overall"] = "FAIL"
    elif high_count > 0 or mid_count > 0 or banned_hits or report["platform_violations"]:
        report["overall"] = "WARN"
    else:
        report["overall"] = "PASS"

    # 5. 总结
    parts = []
    if fatal_count:
        parts.append(f"🚫 {fatal_count} 个致命风险词")
    if high_count:
        parts.append(f"🟠 {high_count} 个高危风险词")
    if mid_count:
        parts.append(f"🟡 {mid_count} 个中危风险词")
    if banned_hits:
        parts.append(f"📛 {len(banned_hits)} 个禁用极限词")
    if report["platform_violations"]:
        parts.append(f"⚠️ {len(report['platform_violations'])} 项平台违规")
    if not parts:
        parts.append("✅ 全部通过，无违规项")

    report["summary"] = "; ".join(parts)

    return report


def main():
    parser = argparse.ArgumentParser(description="跨境电商 Listing 合规审核工具")
    parser.add_argument("--platform", required=True, choices=["amazon", "etsy", "all"],
                       help="目标平台")
    parser.add_argument("--text", help="Listing 文案文本")
    parser.add_argument("--file", help="Listing 文案文件路径")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    elif args.text:
        text = args.text
    else:
        print("错误: 需要 --text 或 --file 参数", file=sys.stderr)
        sys.exit(1)

    report = run_compliance(text, args.platform)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        # 人类可读输出
        print(f"\n{'='*60}")
        print(f"  🛡️  Listing 合规审核报告")
        print(f"  平台: {report['platform'].upper()}")
        print(f"  判定: {report['overall']}")
        print(f"{'='*60}")

        if report["risk_keywords"]:
            print(f"\n📋 风险词扫描 ({len(report['risk_keywords'])} 条):")
            for r in report["risk_keywords"]:
                icon = {"一级（致命）": "🔴", "二级（高危）": "🟠", "三级（中危）": "🟡"}.get(r["level"], "❓")
                repl = f" → {r['replacement']}" if r["replacement"] else ""
                print(f"  {icon} [{r['level']}] {r['keyword']}{repl}")

        if report["banned_words"]:
            print(f"\n📛 禁用极限词 ({len(report['banned_words'])} 条):")
            for b in report["banned_words"]:
                print(f"  ❌ {b['word']} → {b['replacement']}")

        if report["platform_violations"]:
            print(f"\n⚠️  平台专属违规 ({len(report['platform_violations'])} 条):")
            for v in report["platform_violations"]:
                print(f"  • {v['rule']}: {v['detail']}")
                print(f"    修复: {v['fix']}")

        if report["character_limits"]:
            print(f"\n📏 字符数检查:")
            for c in report["character_limits"]:
                status = "✅" if c["pass"] else "❌"
                unit = c.get("unit", "chars")
                print(f"  {status} {c['field']}: {c['current']}/{c['limit']} {unit}")

        print(f"\n📝 总结: {report['summary']}")
        print()


if __name__ == "__main__":
    main()