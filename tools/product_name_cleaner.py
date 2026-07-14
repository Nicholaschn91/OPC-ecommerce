#!/usr/bin/env python3
"""
Product Name Cleaner — 商品名称清洗器

清洗 HiCustom/1688 采集的商品名称中的无效内容：
- 仓库/工厂地址后缀：「（美国XXX仓/工厂）」
- HTML/unicode 残留
- 冗余空格/制表符
- 价格/库存混入

安全原则：只写入新字段「商品名称_清洗后」，不覆盖原始「商品名称」。

用法：
  python -m tools.product_name_cleaner --dry-run          # 全表扫描，输出清洗报告
  python -m tools.product_name_cleaner --apply            # 写入飞书
  python -m tools.product_name_cleaner --record rec_xxx   # 单记录测试
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

# ── 路径处理（兼容 msys bash + 真实 Windows 路径） ──
_THIS_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = Path.home() / ".workbuddy" / "skills" / "hicustom-product-info" / "references" / "config.json"

# ── 清洗规则 ──────────────────────────────────────────

# 仓库地址后缀模式（匹配末尾括号含 "仓"/"工厂" 的嵌套/单层括号）
WAREHOUSE_SUFFIX = re.compile(
    r"\s*[（(]\s*"               # 开括号 + 可选空格
    r"[^)）]*?"                   # 括号内容（非贪婪）
    r"(?:仓|工厂|仓库|warehouse|factory)"
    r"[^)）]*?"
    r"[)）]"                      # 闭括号
    r"\s*$",                      # 必须在末尾
    re.IGNORECASE
)

# 清洗后可能残留的孤括号（配对修复）
UNPAIRED_PAREN = re.compile(r"([（(][^)）]*)$")  # 行尾有开括号但无闭括号 = 被截断的残留

# 多余的模式
CLEAN_PATTERNS = [
    (re.compile(r"<[^>]+>"), ""),                          # HTML 标签
    (re.compile(r"&#?\w+;"), ""),                          # HTML 实体
    (re.compile(r"\\u[0-9a-fA-F]{4}"), ""),               # Unicode 转义
    (re.compile(r"\$\d+(\.\d{2})?"), ""),                  # 价格混入
    (re.compile(r"\bprice\b", re.IGNORECASE), ""),         # "price" 关键字
    (re.compile(r"[“\"'']"), ""),                          # 多余引号
    (re.compile(r"\s+"), " "),                             # 多空格归一
]

# 最小有效长度
MIN_NAME_LENGTH = 3

# 标记为「无效名称」的关键词
INVALID_MARKERS = [
    "请您提供", "需要总结", "无法识别", "未提取到",
    "Please provide", "Unknown product",
]


def clean_product_name(raw: str) -> tuple[str, list[str]]:
    """
    清洗商品名称，返回 (清洗后, 变更说明列表)。

    清洗步骤：
    1. 去仓库后缀（含嵌套括号处理："画布2:3（竖款）（美国仓库）" → "画布2:3（竖款）"）
    2. 去 HTML/unicode/价格混入
    3. 空格归一
    4. 质量校验
    """
    if not raw or len(raw.strip()) == 0:
        return "", ["空名称"]

    cleaned = raw.strip()
    changes = []

    # Step 1: 去仓库地址后缀（正则已精确匹配到仓库括号的开括号位置）
    while True:
        match = WAREHOUSE_SUFFIX.search(cleaned)
        if not match:
            break
        before_removed = cleaned[match.start():]
        cleaned = cleaned[:match.start()].strip()
        
        # 提取被移除括号的内容
        inner = before_removed.strip()
        while inner and inner[0] in "（()）":
            inner = inner[1:].strip()
        while inner and inner[-1] in "）()）":
            inner = inner[:-1].strip()
        changes.append(f"去仓库后缀: {inner}")

    # Step 1b: 修复残留孤括号
    match = UNPAIRED_PAREN.search(cleaned)
    if match:
        cleaned = cleaned[:match.start()].rstrip(" -/")
        changes.append("去残留孤括号")

    # Step 2: HTML/unicode/价格
    for pattern, replacement in CLEAN_PATTERNS:
        before = cleaned
        cleaned = pattern.sub(replacement, cleaned).strip()
        if cleaned != before:
            changes.append("去除HTML/特殊字符残留")

    # Step 3: 尾随 - / 清理
    cleaned = cleaned.rstrip(" -/—（）()")
    cleaned = re.sub(r"\s{2,}", " ", cleaned)

    # Step 4: 质量校验
    for marker in INVALID_MARKERS:
        if marker in cleaned:
            return "", [f"无效名称: 含关键词 '{marker}'"]

    if len(cleaned) < MIN_NAME_LENGTH:
        return "", [f"清洗后过短 ({len(cleaned)}字符)"]

    return cleaned, changes


# ── 飞书 API 封装 ─────────────────────────────────────

class FeishuClient:
    """复用 hicustom-product-info 同款飞书封装（token 缓存、upsert）"""

    def __init__(self):
        if not _CONFIG_PATH.exists():
            raise FileNotFoundError(f"飞书配置文件不存在: {_CONFIG_PATH}")
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
        """分页获取全表记录"""
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
        """部分更新记录字段（不覆盖其他字段）"""
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
        # 单记录模式
        url = (f"{client.api}/bitable/v1/apps/{client.base_token}"
               f"/tables/{client.table_id}/records/{record_id}")
        req = Request(url, headers=client._headers())
        with urlopen(req, timeout=30) as resp:
            item = json.loads(resp.read().decode())["data"]["record"]
        records = [item]
    else:
        records = client.list_all_records()

    report = []
    write_count = 0
    skip_count = 0
    error_count = 0

    for item in records:
        rid = item["record_id"]
        fields = item.get("fields", {})
        raw_name = fields.get("商品名称", "")

        cleaned, changes = clean_product_name(raw_name)

        result = {
            "record_id": rid,
            "原始": raw_name[:80],
            "清洗后": cleaned[:80],
            "变更": changes,
        }

        if not cleaned:
            result["状态"] = "⚠️ 清洗后无效"
            error_count += 1
        elif cleaned == raw_name.strip():
            result["状态"] = "✓ 无需清洗"
            skip_count += 1
        else:
            result["状态"] = "✅ 已清洗"
            write_count += 1
            if not dry_run:
                resp = client.update_record(rid, {"商品名称_清洗后": cleaned})
                if resp.get("code") != 0:
                    result["写入"] = f"❌ {resp.get('msg')}"
                    error_count += 1
                else:
                    result["写入"] = "✅ 已写入"

        report.append(result)

    # 汇总
    print(f"\n{'='*60}")
    print(f"清洗汇总: {len(records)} 条记录")
    print(f"  需清洗: {write_count}")
    print(f"  无需清洗: {skip_count}")
    print(f"  异常: {error_count}")
    if dry_run:
        print(f"  ⚠️ DRY-RUN 模式，未写入飞书")
    print(f"{'='*60}\n")

    return report


def main():
    parser = argparse.ArgumentParser(description="商品名称清洗器")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="全表扫描，仅输出报告（默认）")
    mode.add_argument("--apply", action="store_true",
                      help="全表清洗并写入「商品名称_清洗后」字段")
    parser.add_argument("--record", help="单记录 ID 测试")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    args = parser.parse_args()

    # 默认 dry-run（除非显式 --apply）
    dry_run = not args.apply

    report = run(dry_run=dry_run, record_id=args.record)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for r in report:
            status = r.get("状态", "?")
            print(f"[{status}] {r['record_id']}")
            print(f"  原始:   {r['原始']}")
            if r['清洗后'] != r['原始']:
                print(f"  清洗后: {r['清洗后']}")
            for c in r.get('变更', []):
                print(f"  原因:   {c}")


if __name__ == "__main__":
    main()