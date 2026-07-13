#!/usr/bin/env python3
"""
品类原始词池 — 建表 + 逆向填充 + 增量维护（带品类级语义粗过滤）
-----------------------------------------
用途：保留 erank 品类关键词，经**品类级语义相关性检查**后入库。
同品类新SPU/改款无需重新下载erank CSV，直接从词池取词。

过滤规则（抽屉原则）：关键词拆词 → 至少命中一个品类锚词 or 属性修饰词 → 入池。
全不匹配 → 拒绝（不入池），避免跨品类污染。

用法：
  python build_category_pool.py                      ← 首次建表 + 全量填充
  python build_category_pool.py --upsert <SPU_ID> <CATEGORY> <DATA_MONTH>
                                                     ← 增量插入（process_dual 调用）
"""

import sqlite3, os, sys, csv, io, re
from datetime import datetime

DB = r"C:\\Users\\Administrator.DESKTOP-AHRMISP\\Desktop\\keywords\\erank keywords\\keyword_database.db"

# ═══════════════════════════════════════════════════════
# 三层词库：核心词 + 材质词 + 功能词（每层都有禁止项）
#  核心词 = 平台预置词根（Bat Mat, Shower Mat）→ 禁止完整句子/场景
#  材质词 = 原材料（Diatomaceous Earth, Rubbe）→ 禁止工艺描述
#  功能词 = 功能特征（Non-Slip, Custom）→ 禁止完整短语
# ═══════════════════════════════════════════════════════

CATEGORY_SEEDS = {
    "生活家居": {
        "cores": [
            # 纺织
            "blanket", "throw", "fleece", "plush", "towel", "pillow", "cushion", "curtain",
            "tapestry", "valance", "mat", "rug", "doormat", "bath mat", "shower mat",
            "bedding", "sheet", "pillowcase", "duvet", "quilt", "bedspread",
            "placemat", "runner", "tablecloth", "napkin",
            "oven mitt", "pot holder", "apron",
            # 墙面
            "canvas print", "poster", "painting", "sign", "wall art",
            "switch cover", "outlet cover",
            # 节日/派对
            "christmas stocking", "tree skirt", "ornament", "banner",
            "graduation stole", "sash",
            # 木质/工艺
            "coaster", "piggy bank", "money box", "bottle opener",
            "ring box", "jewelry box", "candle holder", "candy jar",
            "plaque", "photo frame", "lamp", "night light",
            "fridge magnet", "bookmark", "pen", "puzzle", "cross", "clock",
            "wind chime", "license plate", "desk toy", "mouse pad", "desk pad",
            # 收纳
            "storage box", "organizer",
        ],
        "materials": [
            # 纺织材质
            "fleece", "plush", "microfiber", "waffle", "coral", "corduroy",
            "linen", "cotton", "satin", "velvet", "canvas",
            # 硬材
            "wood", "bamboo", "acrylic", "metal", "tin", "iron", "glass", "ceramic",
            "leather", "faux leather", "rubber", "silicon", "vinyl", "plastic",
            "diatomaceous earth", "diatomaceous", "diatom", "stone",
            # 涂层/表面
            "glossy", "matte", "frosted", "brushed",
        ],
        "functions": [
            # 定制
            "custom", "personalized", "monogram", "photo", "engraved", "embroidered",
            # 物理属性
            "non slip", "non-slip", "absorbent", "quick dry", "quick-dry",
            "heat resistant", "oil proof", "waterproof", "washable", "reusable",
            "lightweight", "heavyweight", "oversized", "double sided",
            # 风格
            "rustic", "farmhouse", "boho", "modern", "vintage", "minimalist",
            "decorative", "handmade",
        ],
    },
    "宠物用品": {
        "cores": [
            "collar", "leash", "harness", "bandana", "id tag",
            "bowl", "feeder", "fountain", "bed", "blanket", "mat",
            "toy", "chew toy", "ball", "bone",
            "urn", "memorial", "portrait", "frame", "ornament", "stocking",
            "shirt", "hoodie", "vest", "sweater", "coat", "raincoat",
            "e-collar", "elizabethan collar", "recovery suit",
            "carrier", "crate", "kennel", "house", "hammock",
            "brush", "comb", "nail clipper",
            "poop bag holder",
        ],
        "materials": [
            "wood", "bamboo", "acrylic", "metal", "stainless", "aluminum",
            "leather", "nylon", "mesh", "fleece", "cotton", "canvas",
            "ceramic", "glass", "plastic", "rubber", "silicon",
            "stone", "resin",
        ],
        "functions": [
            "custom", "personalized", "engraved", "embroidered",
            "breathable", "adjustable", "reflective", "waterproof",
            "chew proof", "escape proof", "calming", "traction",
            "memorial", "keepsake",
        ],
    },
    "服饰配件": {
        "cores": [
            "wallet", "purse", "tote bag", "clutch", "crossbody bag", "backpack",
            "keychain", "key ring", "lanyard",
            "watch", "bracelet", "necklace", "pendant", "ring",
            "hat", "cap", "baseball cap", "trucker hat", "beanie", "bucket hat",
            "visor", "snapback", "balaclava",
            "scarf", "bandana", "headband", "neck gaiter",
            "belt", "buckle", "arm sleeve",
        ],
        "materials": [
            "leather", "faux leather", "canvas", "denim", "suede", "nylon",
            "cotton", "wool", "fleece", "acrylic", "mesh",
            "metal", "stainless", "wood", "rubber",
            "faux cashmere", "ice silk",
        ],
        "functions": [
            "custom", "personalized", "monogram", "engraved", "embroidered",
            "rfid", "travel", "slim", "minimalist", "distressed", "vintage",
            "sun protection", "waterproof", "breathable",
        ],
    },
    "工牌配件": {
        "cores": [
            "badge holder", "id holder", "badge reel", "lanyard",
            "name tag", "card holder", "credential holder",
        ],
        "materials": [
            "vinyl", "plastic", "metal", "fabric", "nylon",
        ],
        "functions": [
            "custom", "personalized", "retractable", "breakaway",
            "clear", "clip", "carabiner",
        ],
    },
}

# 三层的全部词项 flat set（供过滤快速匹配）
def _all_seed_terms():
    """按品类汇集 cores + materials + functions 的 flat set"""
    result = {}
    for cat, layers in CATEGORY_SEEDS.items():
        result[cat] = set()
        for layer in ("cores", "materials", "functions"):
            result[cat] |= set(layers[layer])
    return result

# 通用修饰词 — 这三层之外的虚词/量词/语气词
COMMON_MODIFIERS = {
    "for", "and", "the", "a", "an", "in", "on", "of", "with", "to", "by", "or",
    "new", "best", "top", "hot", "cool", "nice", "cute", "funny",
    "gift", "gifts", "idea", "ideas",
}

def _tokenize(keyword):
    """英文关键词拆词 + 基本去复（-s/-es/-ies）"""
    raw = re.split(r'[\s\-/,\.\(\)\[\]&]+', keyword.lower().strip())
    tokens = []
    for t in raw:
        if not t or len(t) < 2:
            continue
        t = t.rstrip("'\"")
        # 简单去复：coasters→coaster, parties→party, boxes→box
        if t.endswith('ies') and len(t) > 3:
            t = t[:-3] + 'y'
        elif t.endswith('ses') and len(t) > 3:
            t = t[:-2]  # boxes→box
        elif t.endswith('s') and not t.endswith('ss') and len(t) > 3:
            t = t[:-1]  # coasters→coaster
        tokens.append(t)
    return tokens


def is_category_relevant(keyword, category):
    """
    三层词库过滤：
    keyword 命中 核心词/材质词/功能词 中任一层 → 入池。
    全不命中 → 拒绝。

    匹配策略：
    - 按空格/连字符拆词 → 逐 token 精确匹配 + 2-gram/3-gram 短语匹配
    - 不去拆粘合词（平台的事）
    - 短词(<4字符)额外做词边界匹配防误杀
    """
    if category not in CATEGORY_SEEDS:
        return True

    terms = _all_seed_terms().get(category, set())
    if not terms:
        return True

    tokens = _tokenize(keyword)
    if not tokens:
        return False

    # 多词短语
    candidates = set(tokens)
    for i in range(len(tokens) - 1):
        candidates.add(f"{tokens[i]} {tokens[i+1]}")
    for i in range(len(tokens) - 2):
        candidates.add(f"{tokens[i]} {tokens[i+1]} {tokens[i+2]}")

    if candidates & terms:
        return True

    # 短词边界匹配
    kw_lower = keyword.lower().strip()
    for t in terms:
        if len(t) < 4 and re.search(r'\b' + re.escape(t.lower()) + r'\b', kw_lower):
            return True

    return False


CREATE_POOL = """
CREATE TABLE IF NOT EXISTS category_keyword_pool (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    keyword TEXT NOT NULL,
    monthly_views REAL DEFAULT 0,
    competition REAL DEFAULT 0,
    supply_demand_ratio REAL DEFAULT 0,
    conversion_rate REAL DEFAULT 0,
    spu_count INTEGER DEFAULT 1,
    source_spus TEXT DEFAULT '',
    data_month TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(category, keyword)
)
"""

CREATE_INDEX = """
CREATE INDEX IF NOT EXISTS idx_pool_category ON category_keyword_pool(category);
CREATE INDEX IF NOT EXISTS idx_pool_keyword ON category_keyword_pool(keyword);
"""


# ═══════════════════════════════════════════════════════
# 全量填充 — 从现有关键词表逆向提取品类级去重词池
# ═══════════════════════════════════════════════════════

def build_full():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # 清空旧池，重建
    cur.execute("DROP TABLE IF EXISTS category_keyword_pool")
    cur.execute(CREATE_POOL)
    cur.executescript(CREATE_INDEX)

    # 从现有关键词表提取，逐条过品类粗滤
    rows = cur.execute("""
        SELECT s.category, LOWER(TRIM(k.keyword)),
               COALESCE(k.monthly_views, 0), COALESCE(k.competition, 0),
               COALESCE(k.supply_demand_ratio, 0), COALESCE(k.conversion_rate, 0),
               k.spu_id, k.data_month
        FROM keywords k
        JOIN spu s ON k.spu_id = s.spu_id
        WHERE s.category IS NOT NULL AND TRIM(k.keyword) != ''
    """).fetchall()

    pool = {}  # (cat, kw) → {views, comp, sdr, cvr, count, spus, month}
    rejected_by_cat = {}

    for cat, kw, views, comp, sdr, cvr, spu, month in rows:
        if not is_category_relevant(kw, cat):
            rejected_by_cat[cat] = rejected_by_cat.get(cat, 0) + 1
            continue

        key = (cat, kw)
        if key not in pool:
            pool[key] = {"views": views, "comp": comp, "sdr": sdr, "cvr": cvr,
                         "count": 0, "spus": set(), "month": month}
        e = pool[key]
        e["views"] = max(e["views"], views)
        e["comp"] = max(e["comp"], comp)
        e["sdr"] = max(e["sdr"], sdr)
        e["cvr"] = max(e["cvr"], cvr)
        e["count"] += 1
        e["spus"].add(spu)
        if month and (not e["month"] or month > e["month"]):
            e["month"] = month

    for (cat, kw), e in pool.items():
        cur.execute("""
            INSERT OR REPLACE INTO category_keyword_pool
                (category, keyword, monthly_views, competition, supply_demand_ratio,
                 conversion_rate, spu_count, source_spus, data_month, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now','localtime'))
        """, (cat, kw, e["views"], e["comp"], e["sdr"], e["cvr"],
              e["count"], ", ".join(sorted(e["spus"])), e["month"]))

    conn.commit()

    # 统计
    for cat, in cur.execute("SELECT DISTINCT category FROM category_keyword_pool ORDER BY category"):
        cnt = cur.execute("SELECT COUNT(*) FROM category_keyword_pool WHERE category=?", (cat,)).fetchone()[0]
        rej = rejected_by_cat.get(cat, 0)
        extra = f" (rejected {rej})" if rej else ""
        print(f"  {cat:10s}  {cnt:5d} unique keywords{extra}")

    total = cur.execute("SELECT COUNT(*) FROM category_keyword_pool").fetchone()[0]
    total_rej = sum(rejected_by_cat.values())
    print(f"\n品类原始词池: {total} unique keywords (rejected {total_rej} irrelevant) across "
          f"{cur.execute('SELECT COUNT(DISTINCT category) FROM category_keyword_pool').fetchone()[0]} categories")
    conn.close()


# ═══════════════════════════════════════════════════════
# 增量插入 — process_dual 处理完一个 SPU 后调用
# ═══════════════════════════════════════════════════════

def upsert_spu(spu_id, category, data_month):
    """将该 SPU 的关键词经品类粗过滤后 upsert 进词池"""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute(CREATE_POOL)

    # 取该 SPU 所有关键词
    rows = cur.execute("""
        SELECT LOWER(TRIM(keyword)),
               COALESCE(monthly_views, 0),
               COALESCE(competition, 0),
               COALESCE(supply_demand_ratio, 0),
               COALESCE(conversion_rate, 0)
        FROM keywords
        WHERE spu_id = ? AND TRIM(keyword) != ''
    """, (spu_id,)).fetchall()

    inserted = 0
    rejected = 0
    rejected_samples = []

    for kw, views, comp, sdr, cvr in rows:
        if not is_category_relevant(kw, category):
            rejected += 1
            if len(rejected_samples) < 5:
                rejected_samples.append(kw)
            continue

        cur.execute("""
            INSERT INTO category_keyword_pool
                (category, keyword, monthly_views, competition, supply_demand_ratio,
                 conversion_rate, spu_count, source_spus, data_month, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, datetime('now','localtime'))
            ON CONFLICT(category, keyword) DO UPDATE SET
                monthly_views    = MAX(category_keyword_pool.monthly_views,    EXCLUDED.monthly_views),
                competition      = MAX(category_keyword_pool.competition,      EXCLUDED.competition),
                supply_demand_ratio = MAX(category_keyword_pool.supply_demand_ratio, EXCLUDED.supply_demand_ratio),
                conversion_rate  = MAX(category_keyword_pool.conversion_rate,  EXCLUDED.conversion_rate),
                spu_count        = category_keyword_pool.spu_count + 1,
                source_spus      = CASE
                    WHEN INSTR(category_keyword_pool.source_spus, EXCLUDED.source_spus) = 0
                    THEN category_keyword_pool.source_spus || ', ' || EXCLUDED.source_spus
                    ELSE category_keyword_pool.source_spus
                END,
                data_month       = MAX(category_keyword_pool.data_month, EXCLUDED.data_month),
                updated_at       = datetime('now','localtime')
        """, (category, kw, views, comp, sdr, cvr, spu_id, data_month, spu_id))
        inserted += 1

    conn.commit()
    conn.close()

    if rejected:
        print(f"[pool filter] {spu_id}: rejected {rejected}/{len(rows)} irrelevant, e.g. {rejected_samples}")

    return inserted


# ═══════════════════════════════════════════════════════
# 品类词池摘要
# ═══════════════════════════════════════════════════════

def summary():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='category_keyword_pool'")
    if not cur.fetchone():
        print("category_keyword_pool 表不存在，请先运行 python build_category_pool.py")
        conn.close()
        return

    print("=== 品类原始词池概况 ===")
    print(f"{'Category':<16} {'Unique':>7} {'Avg Views':>12} {'Avg SPUs':>9}")
    for cat, in cur.execute("SELECT DISTINCT category FROM category_keyword_pool ORDER BY category"):
        stats = cur.execute("""
            SELECT COUNT(*),
                   ROUND(AVG(monthly_views), 0),
                   ROUND(AVG(spu_count), 1)
            FROM category_keyword_pool WHERE category=?
        """, (cat,)).fetchone()
        print(f"{cat:<16} {stats[0]:>7,} {stats[1]:>12,.0f} {stats[2]:>9}")

    total = cur.execute("SELECT COUNT(*) FROM category_keyword_pool").fetchone()[0]
    print(f"\nTotal: {total:,} unique keywords across all categories")
    conn.close()


# ═══════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════

if __name__ == '__main__':
    if len(sys.argv) >= 2 and sys.argv[1] == '--upsert':
        spu_id = sys.argv[2]
        category = sys.argv[3]
        data_month = sys.argv[4] if len(sys.argv) > 4 else datetime.now().strftime("%Y-%m")
        n = upsert_spu(spu_id, category, data_month)
        print(f"[pool] {spu_id} → {category}: {n} keywords upserted")
    elif len(sys.argv) >= 2 and sys.argv[1] == '--summary':
        summary()
    else:
        print("Building category keyword pool from existing data...\n")
        build_full()
        print("\n=== Done. Summary: ===")
        summary()