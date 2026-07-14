#!/usr/bin/env python3
"""
Variant Authenticator — 变体甄别器

分析飞书私表「颜色」「尺码」字段内容，判断：
- 是真变体属性，还是平台必填占位（不填不能发布导致的虚假信息）
- 结论写入「变体维度」字段

变体维度规则（铁律）：
- **0 维**：仅单一规格、无任何变体关系 → 「变体维度」留空
- **1 维**：仅一个属性存在客观变体 → 标注属性名（如 "Color" 或 "Size"）
- **2 维**：两个属性都存在客观变体 → 标注两个属性名（如 "Color, Size"）

甄别逻辑（调用 9router/GLM-5 判断）：
- 颜色字段 = "白色"/"黑色" 仅一个值 → 可能是平台占位
- 颜色字段 = "黑, 白, 红, 蓝" 多值 → 可能是真变体（仍需结合品类判定）
- 尺码字段 = "单尺码"/"One Size"/"均码" → 非变体
- 尺码字段 = "S, M, L, XL" → 可能是真变体（仍需结合品类判定）
- 品类 = "装饰画" + 颜色 = "白色" → 白色可能是占位（画只有白色画布）
- 品类 = "T恤" + 颜色 = "黑, 白" → 真变体颜色

安全原则：只写入「变体维度」字段，不覆盖「颜色」「尺码」。

用法：
  python -m tools.variant_authenticator --dry-run          # 全表扫描，输出报告
  python -m tools.variant_authenticator --apply            # 写入飞书
  python -m tools.variant_authenticator --record rec_xxx   # 单记录测试
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

# ── 配置 ──────────────────────────────────────────────

_THIS_DIR = Path(__file__).resolve().parent
_CONFIG_PATH = Path.home() / ".workbuddy" / "skills" / "hicustom-product-info" / "references" / "config.json"

# 9router 配置
NINEROUTER_BASE = "http://localhost:20128/v1"
NINEROUTER_KEY = os.environ.get("NINEROUTER_API_KEY", "")

# ── 变体占位关键词 ────────────────────────────────────

SIZE_PLACEHOLDER = re.compile(
    r"^(单尺码|均码|one\s*size|free\s*size|统一尺码|单一规格|无尺码)$",
    re.IGNORECASE
)

COLOR_PLACEHOLDER_SINGLE = re.compile(
    r"^(白色|黑色|灰色|默认|default|none)$",
    re.IGNORECASE
)

# 品类-颜色白名单：这些品类中「白色」是正常占位（原材料/工艺约束）
WHITE_COLOR_OK_CATEGORIES = [
    "装饰画", "装饰内框画", "装饰画布", "canvas", "无框画",
    "亚克力", "立牌", "钥匙扣", "冰箱贴", "伸缩扣", "笔筒",
    "滑板立牌", "摇摇乐", "PP夹", "手机支架",
    "抱枕", "玩偶", "暖手抱枕", "挂件", "胸针", "鼠标垫",
    "购物袋", "水瓶", "相框", "摆件", "旗", "旗帜",
    "地垫", "毛毯", "法兰绒",
    "毛巾", "浴巾", "卫生间",
]

# 品类-尺寸白名单：这些品类中尺寸是真变体
SIZE_REAL_CATEGORIES = [
    "T恤", "t-shirt", "短袖", "polo", "衬衫", "卫衣",
    "服装", "clothing", "apparel",
    "儿童", "青少年", "kids", "youth",
    "帽子", "cap", "hat",
    "毛毯", "blanket", "地垫", "mat", "rug",
    "装饰画", "canvas", "内框画", "旗帜", "flag",
    "立牌", "亚克力", "抱枕", "暖手抱枕",
]


class FeishuClient:
    """复用飞书 API 封装"""

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


# ── 变体分析 ──────────────────────────────────────────

def analyze_variants(color_str: str, size_str: str, category: str,
                     product_name: str) -> tuple[str, str, list[str]]:
    """
    分析颜色/尺码的真伪，返回 (变体维度, 置信度, 分析理由列表)。

    规则优先（不调 LLM 的情况），再回退到 9router LLM。
    变体维度值：
    - ""          → 0 维
    - "Color"     → 1 维
    - "Size"      → 1 维
    - "Color, Size" → 2 维
    """
    reasons = []

    # ── 标准化输入 ──
    colors = [c.strip() for c in color_str.split(",") if c.strip()]
    sizes = [s.strip() for s in size_str.split(",") if s.strip()]

    color_count = len(colors)
    size_count = len(sizes)

    # ── 尺寸判定 ──
    size_real = False
    if size_count == 0 or not size_str or not size_str.strip():
        reasons.append("尺寸字段为空")
    elif size_count == 1 and SIZE_PLACEHOLDER.match(sizes[0].strip()):
        reasons.append(f"尺寸为占位标识: '{sizes[0]}'")
    elif size_count >= 1:
        # 品类匹配 + 尺寸格式检查
        cat_lower = category.lower() + product_name.lower()
        has_size_cat = any(kw.lower() in cat_lower for kw in SIZE_REAL_CATEGORIES)
        # 尺寸格式检查：含 cm/inch/数字范围/字母尺码(XS-XL)
        has_size_format = any(re.search(r"(\d+|cm|inch|in|\"|\'|xs|s|m|l|xl|xxl|\d*xl)",
                                        s, re.IGNORECASE) for s in sizes)
        if has_size_cat and has_size_format and size_count >= 2:
            size_real = True
            reasons.append(f"尺寸为真变体(SIZE_REAL_CATEGORIES匹配, {size_count}值)")
        elif has_size_format and size_count >= 2:
            size_real = True
            reasons.append(f"尺寸为真变体(数值格式, {size_count}值)")
        elif size_count == 1:
            reasons.append(f"尺寸仅1值 '{sizes[0]}'，0维判定（单一规格）")
        else:
            reasons.append(f"尺寸需LLM辅助判断({size_count}值: {', '.join(sizes[:5])})")

    # ── 颜色判定 ──
    color_real = False
    if color_count == 0 or not color_str or not color_str.strip():
        reasons.append("颜色字段为空")
    elif color_count == 1:
        c0 = colors[0].strip().lower()
        # 单一颜色 + 品类白名单 → 占位
        if COLOR_PLACEHOLDER_SINGLE.match(colors[0]):
            cat_lower = category.lower() + product_name.lower()
            if any(kw.lower() in cat_lower for kw in WHITE_COLOR_OK_CATEGORIES):
                reasons.append(f"颜色为占位(单一'{colors[0]}'+品类白名单)")
            else:
                reasons.append(f"颜色单一'{colors[0]}'，品类不在白名单，0维判定（单一颜色可能是真规格）")
        else:
            reasons.append(f"颜色仅1值 '{colors[0]}'，0维判定（单一规格）")
    elif color_count >= 2:
        # 多个颜色 → 真变体
        color_real = True
        reasons.append(f"颜色为真变体({color_count}值: {', '.join(colors[:5])})")

    # ── 计算变体维度 ──
    if color_real and size_real:
        dimension = "Color, Size"
        confidence = "规则判定"
    elif color_real and not size_real:
        dimension = "Color"
        confidence = "规则判定"
    elif not color_real and size_real:
        dimension = "Size"
        confidence = "规则判定"
    else:
        dimension = ""
        confidence = "规则判定(0维)"

    return dimension, confidence, reasons


# ── LLM 兜底（规则无法判定的情况）──────────────────────

def llm_analyze(color_str: str, size_str: str, category: str,
                product_name: str) -> tuple[str, str]:
    """调用 9router GLM-5 做变体真伪判定"""
    if not NINEROUTER_KEY:
        return "", "无9router key跳过"

    prompt = f"""你是变体属性甄别器。判断商品的颜色/尺码字段内容是真变体还是平台必填占位。

商品名称: {product_name}
品类: {category}
颜色字段内容: {color_str}
尺码字段内容: {size_str}

规则：
- 1688 平台要求不填变体不能发布 → 大量商品填充了虚假的"默认"/"白色"/"单尺码"
- 真颜色变体：品类需要颜色区分（如服装、手机壳），且颜色值 ≥2 个
- 真尺码变体：品类需要尺码区分（如服装），且尺码值 ≥2 个
- 装饰画/亚克力摆件/毛毯/地垫类：颜色=白色是占位（原材料本色），尺码=尺寸是真变体
- 0维：没有任何客观变体关系，单一规格商品

请仅输出以下 JSON 格式，不要多余文字：
{{"dimension": "" | "Color" | "Size" | "Color, Size", "reason": "判断依据简短说明"}}"""

    try:
        resp = requests.post(
            f"{NINEROUTER_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {NINEROUTER_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "kr/glm-5",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.1,
                "max_tokens": 100,
            },
            timeout=30,
        )
        data = resp.json()
        content = data["choices"][0]["message"]["content"].strip()
        # 提取 JSON
        json_match = re.search(r"\{[^}]+\}", content)
        if json_match:
            result = json.loads(json_match.group())
            return result.get("dimension", ""), f"LLM: {result.get('reason', '')}"
        return "", f"LLM parse failed: {content[:100]}"
    except Exception as e:
        return "", f"LLM调用失败: {e}"


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
    stats = {"0维": 0, "1维": 0, "2维": 0, "异常": 0}

    for item in records:
        rid = item["record_id"]
        fields = item.get("fields", {})
        color_str = fields.get("颜色", "")
        size_str = fields.get("尺码", "")
        category = fields.get("品类", "")
        product_name = fields.get("商品名称", "")

        dimension, confidence, reasons = analyze_variants(
            color_str, size_str, category, product_name)

        result = {
            "record_id": rid,
            "颜色": color_str[:60],
            "尺码": size_str[:60],
            "品类": category[:50],
            "变体维度": dimension,
            "置信度": confidence,
            "理由": reasons,
        }

        if dimension == "":
            stats["0维"] += 1
            result["状态"] = "0维（无变体关系）"
        elif "," in dimension:
            stats["2维"] += 1
            result["状态"] = "2维"
        else:
            stats["1维"] += 1
            result["状态"] = "1维"

        if confidence.startswith("LLM") and confidence != "LLM调用失败":
            result["LLM"] = True

        if not dry_run:
            resp = client.update_record(rid, {"变体维度": dimension})
            if resp.get("code") != 0:
                result["写入"] = f"❌ {resp.get('msg')}"
                stats["异常"] += 1
            else:
                result["写入"] = "✅"
        else:
            result["写入"] = "⏭️ dry-run"

        report.append(result)

    print(f"\n{'='*60}")
    print(f"变体甄别汇总: {len(records)} 条记录")
    print(f"  0维（无变体）: {stats['0维']}")
    print(f"  1维（单属性）: {stats['1维']}")
    print(f"  2维（双属性）: {stats['2维']}")
    print(f"  异常: {stats['异常']}")
    if dry_run:
        print(f"  ⚠️ DRY-RUN 模式，未写入飞书")
    print(f"{'='*60}\n")

    return report


def main():
    parser = argparse.ArgumentParser(description="变体甄别器")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True,
                      help="全表扫描，仅输出报告（默认）")
    mode.add_argument("--apply", action="store_true",
                      help="全表分析并写入「变体维度」字段")
    parser.add_argument("--record", help="单记录 ID 测试")
    parser.add_argument("--json", action="store_true", help="JSON 格式输出")
    parser.add_argument("--sample", type=int, default=0,
                        help="仅分析前 N 条（快速测试）")
    args = parser.parse_args()

    dry_run = not args.apply

    if args.sample > 0:
        client = FeishuClient()
        records = client.list_all_records()[:args.sample]
        # hack: 直接快速输出 sample 报告
        print(f"快速采样 {len(records)} 条...")
        for item in records:
            rid = item["record_id"]
            fields = item.get("fields", {})
            dim, conf, reasons = analyze_variants(
                fields.get("颜色", ""), fields.get("尺码", ""),
                fields.get("品类", ""), fields.get("商品名称", ""))
            print(f"[{dim or '0维'}] {rid}")
            print(f"  颜色: {fields.get('颜色','')[:60]}")
            print(f"  尺码: {fields.get('尺码','')[:60]}")
            print(f"  品类: {fields.get('品类','')[:60]}")
            print(f"  理由: {'; '.join(reasons)}")
            print()
        return

    report = run(dry_run=dry_run, record_id=args.record)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for r in report[:30]:
            print(f"[{r['状态']}] {r['record_id']}")
            print(f"  颜色: {r['颜色']}")
            print(f"  尺码: {r['尺码']}")
            print(f"  品类: {r['品类']}")
            for reason in r["理由"]:
                print(f"  理由: {reason}")
            print(f"  写入: {r['写入']}")
            print()
        if len(report) > 30:
            print(f"... 省略 {len(report)-30} 条（用 --json 看全部）")


if __name__ == "__main__":
    main()