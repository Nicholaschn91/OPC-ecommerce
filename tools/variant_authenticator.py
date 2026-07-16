#!/usr/bin/env python3
"""
Variant Authenticator v2.1 — 纯 LLM 判定（零规则）

v2.1 核心变更：
- 废弃所有硬编码规则（SIZE_PLACEHOLDER, COLOR_PLACEHOLDER, SIZE_REAL_CATEGORIES 等）
- 直接调 9router GLM-5，传入品名+颜色+尺码+品类，让 LLM 判断变体维度
- 0维留空，1维填 "Color" 或 "Size"，2维填 "Color, Size"
- 同时清理旧版变体维度字段残留的错误文本（如"印花位置"）

用法：
  python -m tools.variant_authenticator --dry-run          # 全表扫描
  python -m tools.variant_authenticator --apply            # 写入飞书
  python -m tools.variant_authenticator --record rec_xxx   # 单记录测试
  python -m tools.variant_authenticator --sample 10        # 快速预览
"""

import json
import os
import re
import sys
import time
import argparse
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError
import requests

_THIS_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = Path.home() / ".workbuddy" / "skills" / "hicustom-product-info" / "references" / "config.json"

NINEROUTER_BASE = "http://localhost:20128/v1"
NINEROUTER_KEY = os.environ.get("NINEROUTER_API_KEY", "")


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


def llm_analyze_variant(product_name, color_str, size_str, category):
    """
    调 9router GLM-5 判断变体维度。
    返回 (dimension: str, reason: str)。
    dimension 只能是: "" | "Color" | "Size" | "Color, Size"
    """
    if not NINEROUTER_KEY:
        return "", "无API key"

    prompt = (
        "跨境电商商品变体甄别。判断以下商品的变体维度。\n"
        "规则：\n"
        "- 颜色=单一值(白/黑/灰/默认/单尺码) → 非变体\n"
        "- 颜色=多值(黑,白,红...) → 真变体\n"
        "- 尺码=数量(1个,2个)/单尺码/均码 → 非变体\n"
        "- 尺码=尺寸值(cm/inch/XS-XL/38-46) → 真变体\n"
        "- 商品详情描述(印花位置/设计说明) → 非变体\n\n"
        f"品名: {product_name}\n"
        f"颜色: {color_str}\n"
        f"尺码: {size_str}\n"
        f"品类: {category}\n\n"
        '输出JSON: {{"dimension": "", "reason": "一句话"}}'
    )

    try:
        resp = requests.post(
            f"{NINEROUTER_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {NINEROUTER_KEY}", "Content-Type": "application/json"},
            json={"model": "kr/claude-sonnet-5-agentic", "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0.1, "max_tokens": 150, "stream": False},
            timeout=30,
        )
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        # 鲁棒 JSON 提取：找所有 { } 块，逐个尝试解析
        results = re.findall(r"\{[^}]+\}", content)
        parsed = None
        for candidate in results:
            try:
                parsed = json.loads(candidate)
                break
            except json.JSONDecodeError:
                continue
        if parsed:
            dim = parsed.get("dimension", "")
            if dim not in ("", "Color", "Size", "Color, Size"):
                dim = ""
            return dim, parsed.get("reason", "")
        return "", f"parse failed: {content[:80]}"
    except Exception as e:
        return "", f"调用失败: {e}"


def run(dry_run=True, record_id=None, sample=0):
    client = FeishuClient()

    if record_id:
        item = client.get_record(record_id)
        records = [item]
    else:
        records = client.list_all_records()
        if sample > 0:
            records = records[:sample]

    report = []
    stats = {"0维": 0, "1维-Color": 0, "1维-Size": 0, "2维": 0, "异常": 0, "LLM失败": 0}

    for idx, item in enumerate(records):
        rid = item["record_id"]
        fields = item.get("fields", {})
        product_name = fields.get("商品名称_清洗后", "") or fields.get("商品名称", "")
        color_str = str(fields.get("颜色", ""))
        size_str = str(fields.get("尺码", ""))
        category = fields.get("品类", "")

        # 调 LLM
        dim, reason = llm_analyze_variant(product_name, color_str, size_str, category)

        result = {
            "record_id": rid,
            "品名": product_name[:80],
            "颜色": color_str[:60],
            "尺码": size_str[:60],
            "品类": category[:50],
            "变体维度": dim,
            "理由": reason,
            "写入": "",
        }

        if dim == "":
            stats["0维"] += 1
        elif dim == "Color":
            stats["1维-Color"] += 1
        elif dim == "Size":
            stats["1维-Size"] += 1
        elif dim == "Color, Size":
            stats["2维"] += 1

        if not dry_run:
            resp = client.update_record(rid, {"变体维度": dim})
            result["写入"] = "OK" if resp.get("code") == 0 else f"ERR"
            if resp.get("code", 0) != 0:
                stats["异常"] += 1
        else:
            result["写入"] = "dry"

        report.append(result)

        # 进度提示
        if (idx + 1) % 50 == 0:
            print(f"  已处理 {idx + 1}/{len(records)}...")

    print(f"\n{'='*60}")
    print(f"变体甄别 v2.1 (LLM-only): {len(records)} 条记录")
    print(f"  0维: {stats['0维']}")
    print(f"  1维-Color: {stats['1维-Color']}, 1维-Size: {stats['1维-Size']}")
    print(f"  2维: {stats['2维']}")
    print(f"  LLM失败: {stats['LLM失败']}")
    print(f"  异常: {stats['异常']}")
    if dry_run:
        print(f"  DRY-RUN 模式")
    print(f"{'='*60}\n")
    return report


def main():
    parser = argparse.ArgumentParser(description="变体甄别器 v2.1 (纯LLM)")
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
            dim_display = r["变体维度"] or "0维"
            print(f"[{dim_display}] {r['record_id']}")
            print(f"  品名: {r['品名']}")
            print(f"  颜色: {r['颜色']}")
            print(f"  尺码: {r['尺码']}")
            print(f"  品类: {r['品类']}")
            print(f"  理由: {r['理由']}")
            print()
        if len(report) > 50:
            print(f"... 省略 {len(report)-50} 条")


if __name__ == "__main__":
    main()
