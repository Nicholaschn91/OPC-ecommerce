#!/usr/bin/env python3
"""
Category Row Sorter — 品类归行器

基于清洗后的 product_name（优先读「商品名称_清洗后」，回退到「商品名称」）
对全表进行品类推断和分组排序。

不依赖飞书「品类」字段（烂数据），改为从 product_name 独立推断品类。
结果写入「品类_推荐归组」字段（JSON: {"group": "品类组名", "order": 排序号, "reason": "推断依据"}）。

用法：
  python -m tools.category_row_sorter --dry-run            # 全表扫描 + 推断，输出报告
  python -m tools.category_row_sorter --apply              # 写入「品类_推荐归组」
  python -m tools.category_row_sorter --record rec_xxx     # 单记录测试
"""

import json
import os
import re
import sys
import time
import argparse
from pathlib import Path
from collections import Counter
from urllib.request import Request, urlopen
from urllib.error import HTTPError

# ── 配置 ──────────────────────────────────────────────

_THIS_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = Path.home() / ".workbuddy" / "skills" / "hicustom-product-info" / "references" / "config.json"

# ── 品类推断关键词表 ──────────────────────────────────

CATEGORY_KEYWORDS = [
    # 服装类
    ("T恤|t-?shirt|短袖|polo|shirt|卫衣|hoodie|sweatshirt|长袖|衬衫|上衣|服装|clothing|apparel",
     "服装"),
    ("帽子|cap|hat|棒球帽|鸭舌帽|渔夫帽|beanie", "服装>帽子"),
    ("包|bag|tote|wallet|pouch|背包|手提包|购物袋|收纳包", "服饰配件>包袋"),

    # 家居装饰
    ("装饰画|canvas|内框画|无框画|wall art|poster|挂画|铁皮画|art print", "家居装饰>装饰画"),
    ("毛毯|blanket|throw|法兰绒|fleece", "家居装饰>毛毯"),
    ("地垫|mat|rug|door mat|防滑垫|浴室垫", "家居装饰>地垫"),
    ("旗帜|flag|garden flag|旗子", "家居装饰>旗帜"),
    ("毛巾|towel|浴巾|washcloth", "家居装饰>卫浴纺织品"),
    ("卫生间|浴室|bathroom|四件套|卫浴套", "家居装饰>卫浴套装"),

    # 亚克力/异形摆件
    ("钥匙扣|keychain|key ring", "摆件>钥匙扣"),
    ("冰箱贴|magnet|fridge", "摆件>冰箱贴"),
    ("立牌|standee|stand|acrylic stand|滑板立牌", "摆件>亚克力立牌"),
    ("伸缩扣|retractable|badge|id holder|工牌|card holder", "摆件>伸缩扣"),
    ("笔筒|pen holder|stationary holder", "摆件>笔筒"),
    ("摇摇乐|wobbler|shaker", "摆件>摇摇乐"),
    ("PP夹|pp夹|clip|夹子|文件夹", "摆件>PP夹"),
    ("手机支架|phone holder|phone stand|气囊支架|airbag", "摆件>手机支架"),
    ("摆件|ornament|装饰|decoration|figurine|挂件|charm|pendant|胸针|pin", "摆件>装饰摆件"),
    ("鼠标垫|mouse pad|desk mat|桌垫", "摆件>鼠标垫"),

    # 抱枕/玩偶
    ("抱枕|pillow|cushion|plush|玩偶|doll|暖手抱枕|立体抱枕|长条形玩偶", "玩偶抱枕"),

    # 硅藻泥
    ("硅藻泥|diatomite|diatomaceous|diatom", "硅藻泥制品"),

    # 办公/文具
    ("书签|bookmark", "文具>书签"),
    ("笔|pen|圆珠笔|ballpoint|gel pen", "文具>笔"),

    # 其它
    ("拼图|puzzle|jigsaw", "玩具>拼图"),
    ("杯垫|coaster", "家居>杯垫"),
    ("杯|mug|cup|tumbler|水瓶|water bottle", "家居>杯具"),
    ("戒指|ring|戒指盒|ring box|jewelry|首饰", "首饰"),
    ("烛台|candle holder", "家居>烛台"),
    ("相框|frame|照片框|photo frame", "家居>相框"),
    ("夜灯|light|灯|lamp|night light", "家居>灯具"),
    ("存钱罐|piggy bank|coin bank|储蓄罐", "家居>存钱罐"),
    ("十字架|cross|宗教|crucifix", "家居>宗教用品"),
    ("挂钟|clock|钟", "家居>挂钟"),
    ("风铃|wind chime", "家居>风铃"),
    ("车牌|license plate|plate", "家居>车牌装饰"),
    ("标牌|sign|signage|plaque|挂牌|门牌", "家居>标牌"),
    ("开瓶器|opener|bottle opener", "家居>开瓶器"),
    ("糖果罐|candy jar|cookie jar|storage jar|收纳罐", "家居>收纳罐"),
    ("宠物|pet|dog|cat|骨灰|ashes|memorial|纪念", "宠物用品"),
    ("口红|lipstick|makeup|彩妆|化妆", "化妆用品"),
]

# 品类权重（用于排序，"服装"类排最前）
CATEGORY_SORT_ORDER = {
    "服装": 10, "服装>帽子": 11, "服饰配件>包袋": 12,
    "家居装饰>装饰画": 20, "家居装饰>毛毯": 21, "家居装饰>地垫": 22,
    "家居装饰>旗帜": 23, "家居装饰>卫浴纺织品": 24, "家居装饰>卫浴套装": 25,
    "摆件>钥匙扣": 30, "摆件>冰箱贴": 31, "摆件>亚克力立牌": 32,
    "摆件>伸缩扣": 33, "摆件>笔筒": 34, "摆件>摇摇乐": 35,
    "摆件>PP夹": 36, "摆件>手机支架": 37, "摆件>装饰摆件": 38,
    "摆件>鼠标垫": 39,
    "玩偶抱枕": 40, "硅藻泥制品": 50,
    "文具>书签": 60, "文具>笔": 61,
    "玩具>拼图": 70, "家居>杯垫": 80, "家居>杯具": 81,
    "首饰": 90, "家居>烛台": 100, "家居>相框": 101,
    "家居>灯具": 102, "家居>存钱罐": 103, "家居>宗教用品": 104,
    "家居>挂钟": 105, "家居>风铃": 106, "家居>车牌装饰": 107,
    "家居>标牌": 108, "家居>开瓶器": 109, "家居>收纳罐": 110,
    "宠物用品": 120, "化妆用品": 130,
    "其他": 999,
}


def infer_category(clean_name: str) -> tuple[str, str]:
    """
    从清洗后的 product_name 推断品类。
    返回 (品类组名, 匹配依据)。
    """
    if not clean_name:
        return "其他", "名称为空"

    text_lower = clean_name.lower().replace("-", " ").replace("/", " ")

    for pattern, category in CATEGORY_KEYWORDS:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return category, f"关键词匹配: {pattern.split('|')[0]}"

    return "其他", f"无匹配关键词"


# ── 飞书 API ──────────────────────────────────────────

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
    def token(self) -> str:
        if self._token and time.time() - self._token_ts < 7000:
            return self._token
        url = f"{self.api}/auth/v3/tenant_access_token/internal"
        req = Request(url, data=json.dumps({
            "app_id": self.app_id,
            "app_secret": self.app_secret,
        }).encode(), headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        self._token = data["tenant_access_token"]
        self._token_ts = time.time()
        return self._token

    def _headers(self):
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json; charset=utf-8"}

    def list_all_records(self) -> list[dict]:
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

    def update_record(self, record_id: str, fields: dict) -> dict:
        url = (f"{self.api}/bitable/v1/apps/{self.base_token}"
               f"/tables/{self.table_id}/records/{record_id}")
        req = Request(url, data=json.dumps({"fields": fields}).encode(),
                      headers=self._headers(), method="PUT")
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())


# ── 主流程 ────────────────────────────────────────────

def run(dry_run: bool = True, record_id: str = None):
    client = FeishuClient()

    if record_id:
        url = (f"{client.api}/bitable/v1/apps/{client.base_token}"
               f"/tables/{client.table_id}/records/{record_id}")
        req = Request(url, headers=client._headers())
        with urlopen(req, timeout=30) as resp:
            item = json.loads(resp.read().decode())["data"]["record"]
        records = [item]
    else:
        records = client.list_all_records()

    report = []
    groups = Counter()

    for idx, item in enumerate(records):
        rid = item["record_id"]
        fields = item.get("fields", {})
        # 优先读清洗后的名称
        clean_name = fields.get("商品名称_清洗后", "") or fields.get("商品名称", "")
        raw_name = fields.get("商品名称", "")
        old_cat = fields.get("品类", "")

        group, reason = infer_category(clean_name)
        sort_order = CATEGORY_SORT_ORDER.get(group, 999)

        groups[group] += 1

        result = {
            "record_id": rid,
            "品名_清洗后": clean_name[:80],
            "品名_原始": raw_name[:80],
            "旧品类字段": old_cat[:60],
            "推断品类": group,
            "推断依据": reason,
            "排序号": sort_order,
        }

        if not dry_run:
            field_value = json.dumps({
                "group": group,
                "order": sort_order,
                "reason": reason,
            }, ensure_ascii=False)
            resp = client.update_record(rid, {"品类_推荐归组": field_value})
            result["写入"] = "✅" if resp.get("code") == 0 else f"❌ {resp.get('msg')}"
        else:
            result["写入"] = "⏭️ dry-run"

        report.append(result)

    # 汇总
    print(f"\n{'='*60}")
    print(f"品类归行汇总: {len(records)} 条记录")
    print(f"  品类组数: {len(groups)}")
    for group, count in groups.most_common():
        order = CATEGORY_SORT_ORDER.get(group, 999)
        print(f"    [{order:3d}] {group:20s} → {count} 条")
    if dry_run:
        print(f"  ⚠️ DRY-RUN 模式，未写入飞书")
    print(f"{'='*60}\n")

    return report


def main():
    parser = argparse.ArgumentParser(description="品类归行器")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="全表扫描 + 推断，仅输出报告（默认）")
    mode.add_argument("--apply", action="store_true",
                      help="全表推断并写入「品类_推荐归组」字段")
    parser.add_argument("--record", help="单记录 ID 测试")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--sample", type=int, help="仅分析前 N 条（快速测试）")
    args = parser.parse_args()

    dry_run = not args.apply

    if args.sample:
        client = FeishuClient()
        all_recs = client.list_all_records()
        records = all_recs[:args.sample]
        for item in records:
            rid = item["record_id"]
            fields = item.get("fields", {})
            clean = fields.get("商品名称_清洗后", "") or fields.get("商品名称", "")
            group, reason = infer_category(clean)
            order = CATEGORY_SORT_ORDER.get(group, 999)
            print(f"[{group}] {rid}: {clean[:60]}")
            print(f"  依据: {reason}  排序: {order}")
        return

    report = run(dry_run=dry_run, record_id=args.record)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()