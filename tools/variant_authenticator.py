#!/usr/bin/env python3
"""
Variant Authenticator v2.0
"""
import json, os, re, sys, time, argparse, sqlite3
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

try:
    import requests
except ImportError:
    requests = None

_THIS_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = Path.home() / ".workbuddy" / "skills" / "hicustom-product-info" / "references" / "config.json"

_KW_DB_CANDIDATES = [
    os.environ.get("KEYWORD_DB_PATH"),
    str(Path.home() / ".workbuddy" / "skills" / "multi-agent-sop" / "keyword_database.db"),
    str(Path.home() / ".workbuddy" / "skills" / "multi-agent-sop" / "tools" / "keyword_database.db"),
]
KW_DB_PATH = next((p for p in _KW_DB_CANDIDATES if p and os.path.exists(p)), None)

NINEROUTER_BASE = "http://localhost:20128/v1"
NINEROUTER_KEY = os.environ.get("NINEROUTER_API_KEY", "")

SIZE_PLACEHOLDER = re.compile(r"^(单尺码|均码|one\s*size|free\s*size|统一尺码|单一规格|无尺码|default)$", re.IGNORECASE)
COLOR_PLACEHOLDER_SINGLE = re.compile(r"^(白色|黑色|灰色|默认|default|none|透明|无色)$", re.IGNORECASE)

WHITE_COLOR_OK_CATEGORIES = [
    "装饰画", "装饰内框画", "装饰画布", "canvas", "无框画", "铁皮画", "挂毯",
    "亚克力", "立牌", "钥匙扣", "冰箱贴", "伸缩扣", "笔筒",
    "滑板立牌", "摇摇乐", "PP夹", "手机支架",
    "抱枕", "玩偶", "暖手抱枕", "挂件", "胸针", "鼠标垫",
    "购物袋", "水瓶", "相框", "摆件", "旗", "旗帜",
    "地垫", "毛毯", "法兰绒", "毯子", "毛巾", "浴巾", "卫生间",
    "存钱罐", "挂牌", "标牌", "车牌", "书签", "圆珠笔",
    "十字架", "挂钟", "风铃", "开瓶器", "杯垫", "烛台",
    "糖果罐", "收纳罐", "骨灰盒", "种植盆", "吊坠", "项链",
    "绶带", "鲁班锁", "小木人", "拼图", "夜灯",
]

SIZE_REAL_CATEGORIES = [
    "T恤", "t-shirt", "短袖", "polo", "衬衫", "卫衣",
    "服装", "clothing", "apparel", "儿童", "青少年", "kids", "youth",
    "帽子", "cap", "hat", "毛毯", "blanket", "地垫", "mat", "rug", "毯子",
    "装饰画", "canvas", "内框画", "旗帜", "flag", "无框画", "铁皮画", "挂毯",
    "立牌", "亚克力", "抱枕", "暖手抱枕",
]

SIZE_FORMAT_PATTERNS = [
    re.compile(r"\d+\s*(?:cm|mm|inch|in\b|\"|\')", re.IGNORECASE),
    re.compile(r"\d+\s*x\s*\d+", re.IGNORECASE),
    re.compile(r"^(xs|s|m|l|xl|xxl|XXXL|\d*xl)$", re.IGNORECASE),
    re.compile(r"^(3[0-9]|4[0-9]|5[0-9])$"),
    re.compile(r"^(twin|full|queen|king|cal\s*king|single|double)$", re.IGNORECASE),
    re.compile(r"^(one\s*size|free\s*size|均码|单尺码)$", re.IGNORECASE),
]

CATEGORY_MAPPING = {
    "家居装饰>装饰画": "生活家居", "家居装饰>毛毯": "生活家居",
    "家居装饰>地垫": "生活家居", "家居装饰>旗帜": "生活家居",
    "家居装饰>卫浴纺织品": "生活家居", "家居装饰>卫浴套装": "生活家居",
    "摆件>钥匙扣": "生活家居", "摆件>冰箱贴": "生活家居",
    "摆件>亚克力立牌": "生活家居", "摆件>伸缩扣": "工牌配件",
    "摆件>笔筒": "生活家居", "摆件>摇摇乐": "生活家居",
    "摆件>PP夹": "生活家居", "摆件>手机支架": "生活家居",
    "摆件>装饰摆件": "生活家居", "摆件>鼠标垫": "生活家居",
    "玩偶抱枕": "生活家居", "家居>杯垫": "生活家居",
    "家居>相框": "生活家居", "家居>存钱罐": "生活家居",
    "家居>标牌": "生活家居", "家居>车牌装饰": "生活家居",
    "家居>挂钟": "生活家居", "家居>风铃": "生活家居",
    "家居>开瓶器": "生活家居", "家居>收纳罐": "生活家居",
    "家居>烛台": "生活家居", "宠物用品": "宠物用品",
    "首饰": "服饰配件", "服饰配件>包袋": "服饰配件",
    "服装": "服饰配件", "服装>帽子": "服饰配件",
    "文具>书签": "生活家居", "文具>笔": "生活家居",
    "硅藻泥制品": "生活家居", "其他": "生活家居",
}


def load_keyword_db_categories():
    if not KW_DB_PATH:
        return {}
    try:
        conn = sqlite3.connect(KW_DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT spu_id, spu_name, category FROM spu")
        rows = cursor.fetchall()
        conn.close()
        return {r["spu_id"]: {"name": r["spu_name"], "category": r["category"]} for r in rows}
    except Exception:
        return {}


def match_size_format(s):
    s = s.strip()
    if SIZE_PLACEHOLDER.match(s):
        return False
    for pat in SIZE_FORMAT_PATTERNS:
        if pat.search(s):
            return True
    return False


class FeishuClient:
    def __init__(self):
        with open(_CONFIG_PATH) as f:
            cfg = json.load(f)["feishu"]
        self.app_id = cfg["app_id"]
        self.app_secret = cfg["app_secret"]
        self.base_token = cfg["base_token"]
        self.table_id = cfg["table_id"]
        self.api = "https://open.feishu.cn/open-apis"
        self._token = None
        self._token_ts = 0

    @property
    def token(self):
        if self._token and time.time() - self._token_ts < 7000:
            return self._token
        url = f"{self.api}/auth/v3/tenant_access_token/internal"
        req = Request(url, data=json.dumps({
            "app_id": self.app_id, "app_secret": self.app_secret,
        }).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        self._token = data["tenant_access_token"]
        self._token_ts = time.time()
        return self._token

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json; charset=utf-8"}

    def list_all_records(self):
        records = []
        page_token = ""
        while True:
            url = (f"{self.api}/bitable/v1/apps/{self.base_token}"
                   f"/tables/{self.table_id}/records?page_size=100"
                   + (f"&page_token={page_token}" if page_token else ""))
            req = Request(url, headers=self._headers())
            with urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
            items = data.get("data", {}).get("items", [])
            records.extend(items)
            if not data.get("data", {}).get("has_more"):
                break
            page_token = data["data"]["page_token"]
        return records

    def get_record(self, record_id):
        url = (f"{self.api}/bitable/v1/apps/{self.base_token}"
               f"/tables/{self.table_id}/records/{record_id}")
        req = Request(url, headers=self._headers())
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())["data"]["record"]

    def update_record(self, record_id, fields):
        url = (f"{self.api}/bitable/v1/apps/{self.base_token}"
               f"/tables/{self.table_id}/records/{record_id}")
        req = Request(url, data=json.dumps({"fields": fields}).encode(),
                      headers=self._headers(), method="PUT")
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())


def analyze_variants(color_str, size_str, category, product_name, use_llm_fallback=True):
    reasons = []
    need_llm = False
    colors = [c.strip() for c in color_str.split(",") if c.strip()]
    sizes = [s.strip() for s in size_str.split(",") if s.strip()]
    color_count = len(colors)
    size_count = len(sizes)
    cat_lower = (category + product_name).lower()

    size_real = False
    if size_count == 0 or not size_str.strip():
        reasons.append("尺寸字段为空")
    elif size_count == 1 and SIZE_PLACEHOLDER.match(sizes[0].strip()):
        reasons.append("尺寸占位: " + sizes[0])
    elif size_count == 1:
        if match_size_format(sizes[0]):
            reasons.append("尺寸仅1值 " + sizes[0] + " 格式有效, 0维")
        else:
            reasons.append("尺寸仅1值 " + sizes[0] + ", 0维")
    elif size_count >= 2:
        has_size_cat = any(kw.lower() in cat_lower for kw in SIZE_REAL_CATEGORIES)
        has_size_format = any(match_size_format(s) for s in sizes)
        if has_size_cat and has_size_format:
            size_real = True
            reasons.append("尺寸真变体(品类匹配, " + str(size_count) + "值)")
        elif has_size_format:
            size_real = True
            reasons.append("尺寸真变体(格式匹配, " + str(size_count) + "值)")
        else:
            reasons.append("尺寸_" + str(size_count) + "值格式不匹配, 需LLM")
            need_llm = True

    color_real = False
    if color_count == 0 or not color_str.strip():
        reasons.append("颜色字段为空")
    elif color_count == 1:
        if COLOR_PLACEHOLDER_SINGLE.match(colors[0]):
            if any(kw.lower() in cat_lower for kw in WHITE_COLOR_OK_CATEGORIES):
                reasons.append("颜色占位(" + colors[0] + "+白名单)")
            else:
                reasons.append("颜色单一" + colors[0] + "不在白名单, 需LLM")
                need_llm = True
        else:
            reasons.append("颜色仅1值 " + colors[0] + ", 0维")
    elif color_count >= 2:
        color_real = True
        reasons.append("颜色真变体(" + str(color_count) + "值)")

    if color_real and size_real:
        return "Color, Size", "规则判定", reasons
    elif color_real and not size_real and not need_llm:
        return "Color", "规则判定", reasons
    elif not color_real and size_real and not need_llm:
        return "Size", "规则判定", reasons
    elif not color_real and not size_real and not need_llm:
        return "", "规则判定(0维)", reasons

    if need_llm and use_llm_fallback:
        llm_dim, llm_reason = llm_analyze(color_str, size_str, category, product_name)
        if llm_dim:
            reasons.append("LLM兜底: " + llm_reason)
            return llm_dim, "LLM判定", reasons
        else:
            reasons.append("LLM失败: " + llm_reason)
            if color_real:
                return "Color", "规则+LLM失败", reasons
            elif size_real:
                return "Size", "规则+LLM失败", reasons
            return "", "规则+LLM失败(0维)", reasons
    else:
        if color_real:
            return "Color", "规则判定", reasons
        elif size_real:
            return "Size", "规则判定", reasons
        return "", "规则判定(0维)", reasons


def llm_analyze(color_str, size_str, category, product_name):
    if not NINEROUTER_KEY or requests is None:
        return "", "无9router key或requests库"
    prompt = (
        "你是变体属性甄别器。判断商品颜色/尺码字段是真变体还是平台必填占位。\n"
        "商品名称: " + product_name + "\n"
        "品类: " + category + "\n"
        "颜色字段: " + color_str + "\n"
        "尺码字段: " + size_str + "\n"
        "规则:\n"
        "- 1688平台不填变体不能发布, 大量商品填充虚假默认/白色/单尺码\n"
        "- 真颜色变体: 品类需要颜色区分(如服装), 颜色值>=2\n"
        "- 真尺码变体: 品类需要尺码区分, 尺码值>=2\n"
        "- 装饰画/亚克力/毛毯/地垫: 颜色=白色是占位, 尺码=尺寸是真变体\n"
        "- 0维: 没有客观变体关系, 单一规格商品\n"
        '仅输出JSON: {"dimension": "" | "Color" | "Size" | "Color, Size", "reason": "简短说明"}'
    )
    try:
        resp = requests.post(
            f"{NINEROUTER_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {NINEROUTER_KEY}", "Content-Type": "application/json"},
            json={"model": "kr/glm-5", "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.1, "max_tokens": 100},
            timeout=30,
        )
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        json_match = re.search(r"\{[^}]+\}", content)
        if json_match:
            result = json.loads(json_match.group())
            return result.get("dimension", ""), "LLM: " + result.get("reason", "")
        return "", "parse failed: " + content[:80]
    except Exception as e:
        return "", "调用失败: " + str(e)


def aggregate_supplier_variants(records):
    rid_map = {r["record_id"]: r for r in records}
    groups = {}
    for r in records:
        fields = r.get("fields", {})
        tongkuan = fields.get("同款商品ID", "")
        if tongkuan:
            dup_ids = [x.strip() for x in tongkuan.split(",") if x.strip()]
            groups[r["record_id"]] = dup_ids

    result = {}
    for primary_rid, dup_rids in groups.items():
        all_rids = [primary_rid] + [rid for rid in dup_rids if rid in rid_map]
        best_rid = primary_rid
        best_count = -1
        for rid in all_rids:
            rec = rid_map.get(rid)
            if not rec:
                continue
            fields = rec.get("fields", {})
            colors = [c.strip() for c in str(fields.get("颜色", "")).split(",") if c.strip()]
            sizes = [s.strip() for s in str(fields.get("尺码", "")).split(",") if s.strip()]
            count = len(colors) + len(sizes)
            if count > best_count:
                best_count = count
                best_rid = rid
        for rid in all_rids:
            result[rid] = {"is_primary": (rid == best_rid), "supplier_count": len(all_rids), "primary_rid": best_rid}
    return result


def run(dry_run=True, record_id=None, sample=0):
    client = FeishuClient()
    if record_id:
        item = client.get_record(record_id)
        records = [item]
    else:
        records = client.list_all_records()
        if sample > 0:
            records = records[:sample]

    supplier_info = aggregate_supplier_variants(records)
    report = []
    stats = {"0维": 0, "1维": 0, "2维": 0, "异常": 0, "LLM调用": 0}
    kw_cats = load_keyword_db_categories()

    for item in records:
        rid = item["record_id"]
        fields = item.get("fields", {})
        color_str = str(fields.get("颜色", ""))
        size_str = str(fields.get("尺码", ""))
        clean_name = fields.get("商品名称_清洗后", "") or fields.get("商品名称", "")
        rg_raw = fields.get("品类_推荐归组", "")
        rec_group = ""
        if rg_raw:
            try:
                rg = json.loads(rg_raw) if isinstance(rg_raw, str) else rg_raw
                rec_group = rg.get("group", "")
            except Exception:
                rec_group = str(rg_raw)
        category = rec_group or fields.get("品类", "")
        kw_cat = CATEGORY_MAPPING.get(rec_group, "生活家居")

        dim, conf, reasons = analyze_variants(color_str, size_str, category, clean_name, use_llm_fallback=True)
        sup = supplier_info.get(rid, {})
        is_primary = sup.get("is_primary", True)
        sup_count = sup.get("supplier_count", 1)

        result = {
            "record_id": rid, "品名_清洗后": clean_name[:60],
            "颜色": color_str[:60], "尺码": size_str[:60],
            "归组": rec_group[:40], "词库品类": kw_cat,
            "变体维度": dim, "置信度": conf, "理由": reasons,
            "多供应商": ("主" if is_primary else "从") + "(" + str(sup_count) + "供)" if sup_count > 1 else "单供",
            "写入": "",
        }

        if dim == "":
            stats["0维"] += 1
        elif "," in dim:
            stats["2维"] += 1
        else:
            stats["1维"] += 1
        if conf == "LLM判定":
            stats["LLM调用"] += 1

        if not dry_run:
            resp = client.update_record(rid, {"变体维度": dim})
            if resp.get("code") == 0:
                result["写入"] = "OK"
            else:
                result["写入"] = "ERR"
                stats["异常"] += 1
        else:
            result["写入"] = "dry"

        report.append(result)

    print("\n" + "=" * 55)
    print("变体甄别 v2.0: " + str(len(records)) + " 条记录")
    print("  0维: " + str(stats["0维"]) + ", 1维: " + str(stats["1维"]) + ", 2维: " + str(stats["2维"]))
    print("  LLM调用: " + str(stats["LLM调用"]) + ", 异常: " + str(stats["异常"]))
    print("  词库: " + ("已加载" if kw_cats else "未找到"))
    if dry_run:
        print("  DRY-RUN")
    print("=" * 55 + "\n")
    return report


def main():
    parser = argparse.ArgumentParser(description="变体甄别器 v2.0")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True)
    mode.add_argument("--apply", action="store_true")
    parser.add_argument("--record", help="单记录ID")
    parser.add_argument("--sample", type=int, default=0, help="仅前N条")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    dry_run = not args.apply
    report = run(dry_run=dry_run, record_id=args.record, sample=args.sample)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for r in report[:50]:
            print("[" + (r["变体维度"] or "0维") + "] " + r["record_id"] + " " + r["多供应商"])
            print("  品名: " + r["品名_清洗后"])
            print("  颜色: " + r["颜色"])
            print("  尺码: " + r["尺码"])
            print("  归组: " + r["归组"] + " -> " + r["词库品类"])
            print("  置信: " + r["置信度"] + " | " + "; ".join(r["理由"]))
            print()
        if len(report) > 50:
            print("... 省略 " + str(len(report) - 50) + " 条")


if __name__ == "__main__":
    main()
