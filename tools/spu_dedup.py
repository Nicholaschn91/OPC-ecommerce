#!/usr/bin/env python3
"""
SPU Dedup Tool — SPU 去重器

基于清洗后的 product_name（「商品名称_清洗后」）+ 白品ID 进行全表 SPU 去重。

逻辑：
1. 按 product_name_清洗后 标准化 + 白品ID 分组
2. 每组首个记录保留「商品ID」字段不变
3. 同组其他记录的「商品ID」追加到该组首记录的「同款商品ID」字段
4. 同组被合并的记录标记「清洗状态=已去重」
5. 不删记录、不覆盖商品名称、不改动其他字段

安全原则：
- 去重后原记录的「商品ID」清空（避免混淆），被合并记录的「商品ID」移入「同款商品ID」
- 被合并记录标记「清洗状态=已去重」供人工复查

用法：
  python -m tools.spu_dedup --dry-run                  # 输出分组报告
  python -m tools.spu_dedup --apply                    # 执行去重写入
  python -m tools.spu_dedup --record rec_xxx           # 单记录测试
"""

import json
import os
import re
import sys
import time
import argparse
from pathlib import Path
from collections import defaultdict
from urllib.request import Request, urlopen
from urllib.error import HTTPError

_THIS_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = Path.home() / ".workbuddy" / "skills" / "hicustom-product-info" / "references" / "config.json"


def normalize_name(name: str) -> str:
    """标准化商品名称用于去重匹配"""
    # 去括号内容（保留规格信息如尺寸/颜色，但去掉仓库）
    # 去空格、统一小写
    n = name.strip().lower()
    # 去标点
    n = re.sub(r"[，。！？、；：""''（）()【】\[\]《》<>{}…—–\-/\\|@#$%^&*+=~`\s]+", " ", n)
    n = re.sub(r"\s{2,}", " ", n).strip()
    return n


def find_dup_groups(records: list[dict]) -> dict[str, list[dict]]:
    """
    分组：按 (标准化品名, 白品ID) 分组。
    """
    groups = defaultdict(list)
    for item in records:
        fields = item.get("fields", {})
        clean_name = fields.get("商品名称_清洗后", "") or fields.get("商品名称", "")
        blank_id = fields.get("白品ID", "")
        if not clean_name:
            continue
        
        key = f"{normalize_name(clean_name)}||{blank_id}"
        groups[key].append(item)

    # 只保留有重复的组
    duplicates = {k: v for k, v in groups.items() if len(v) > 1}
    return duplicates


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

    def get_record(self, record_id: str) -> dict:
        url = (f"{self.api}/bitable/v1/apps/{self.base_token}"
               f"/tables/{self.table_id}/records/{record_id}")
        req = Request(url, headers=self._headers())
        with urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())["data"]["record"]


def run(dry_run: bool = True, record_id: str = None):
    client = FeishuClient()

    if record_id:
        item = client.get_record(record_id)
        records = [item]
    else:
        records = client.list_all_records()

    dup_groups = find_dup_groups(records)

    print(f"\n{'='*60}")
    print(f"SPU 去重: {len(records)} 条记录")
    print(f"  重复组数: {len(dup_groups)}")
    total_dup = sum(len(v) - 1 for v in dup_groups.values())
    print(f"  可去重记录: {total_dup} 条")
    if dry_run:
        print(f"  ⚠️ DRY-RUN 模式，未写入飞书")
    print(f"{'='*60}")

    report = []

    for key, items in dup_groups.items():
        name_part, blank_part = key.split("||", 1)
        # 首记录为尊（保留）
        primary = items[0]
        primary_rid = primary["record_id"]
        primary_pid = primary["fields"].get("商品ID", "")

        group_report = {
            "标准化品名": name_part,
            "白品ID": blank_part,
            "主记录": primary_rid,
            "主商品ID": primary_pid,
            "合并记录": [],
        }

        # 收集所有被合并的商品ID
        all_ids = [primary_pid] if primary_pid else []
        current_tongkuan = primary["fields"].get("同款商品ID", "")
        existing_ids = [x.strip() for x in current_tongkuan.split(",") if x.strip()] if current_tongkuan else []

        for dup_item in items[1:]:
            dup_rid = dup_item["record_id"]
            dup_pid = dup_item["fields"].get("商品ID", "")
            dup_name = dup_item["fields"].get("商品名称", "")

            if dup_pid and dup_pid not in existing_ids and dup_pid != primary_pid:
                existing_ids.append(dup_pid)
            if dup_pid:
                all_ids.append(dup_pid)

            group_report["合并记录"].append({
                "record_id": dup_rid,
                "商品ID": dup_pid,
                "商品名称": dup_name[:60],
            })

            if not dry_run:
                # 被合并记录：清空商品ID（已合并到主记录），标记去重状态
                client.update_record(dup_rid, {
                    "商品ID": "",
                    "清洗状态": "已去重",
                })

        # 更新主记录的 同款商品ID
        new_tongkuan = ", ".join(existing_ids) if existing_ids else ""
        if not dry_run:
            client.update_record(primary_rid, {"同款商品ID": new_tongkuan})

        group_report["最终同款商品ID"] = new_tongkuan
        report.append(group_report)

        # 打印
        print(f"\n📦 重复组: {name_part[:50]}")
        print(f"  白品ID: {blank_part}")
        print(f"  主记录: {primary_rid} (商品ID={primary_pid})")
        for d in group_report["合并记录"]:
            print(f"  └ 合并: {d['record_id']} (商品ID={d['商品ID']}) → {d['商品名称'][:40]}")
        print(f"  同款商品ID: {new_tongkuan}")

    if not dup_groups:
        print("\n✅ 无重复记录，无需去重")

    return report


def main():
    parser = argparse.ArgumentParser(description="SPU 去重器")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="输出分组报告（默认）")
    mode.add_argument("--apply", action="store_true",
                      help="执行去重写入")
    parser.add_argument("--record", help="单记录 ID 测试")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    dry_run = not args.apply
    report = run(dry_run=dry_run, record_id=args.record)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()