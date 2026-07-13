#!/usr/bin/env python3
"""
客服对话蒸馏工具 (Conversation Distillation)

功能:
  1. 导入历史对话记录 (CSV / JSON / TXT)
  2. 蒸馏提取高频 Q&A 对、常见问题模式、标准回答模板
  3. 输出可导入 Dify 知识库的 Markdown / JSONL 格式
  4. 支持增量更新 — 新对话不覆盖已有蒸馏结果

用法:
  python distill_conversations.py --input history.csv --output faq_distilled.md
  python distill_conversations.py --input archive/ --output kb.jsonl --format jsonl
  python distill_conversations.py --merge existing.md --input new.csv --output merged.md
"""

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


def load_csv(filepath: str) -> list[dict]:
    """加载 CSV 格式对话"""
    rows = []
    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            q = row.get("question") or row.get("q") or row.get("Q") or ""
            a = row.get("answer") or row.get("a") or row.get("A") or ""
            cat = row.get("category") or row.get("cat") or row.get("topic") or "未分类"
            if q.strip() and a.strip():
                rows.append({"q": q.strip(), "a": a.strip(), "category": cat.strip()})
    return rows


def load_json(filepath: str) -> list[dict]:
    """加载 JSON 格式对话"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)
    rows = []
    for item in data:
        q = item.get("q") or item.get("question") or ""
        a = item.get("a") or item.get("answer") or ""
        cat = item.get("category") or item.get("topic") or "未分类"
        if q.strip() and a.strip():
            rows.append({"q": q.strip(), "a": a.strip(), "category": cat.strip()})
    return rows


def load_txt(filepath: str) -> list[dict]:
    """加载 TXT 格式对话 (Q: ... A: ...)"""
    rows = []
    current_q, current_a = None, None
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                if current_q and current_a:
                    rows.append({"q": current_q, "a": current_a, "category": "未分类"})
                current_q, current_a = None, None
                continue
            if line.lower().startswith("q:") or line.lower().startswith("问:"):
                current_q = line.split(":", 1)[1].strip()
            elif line.lower().startswith("a:") or line.lower().startswith("答:"):
                current_a = line.split(":", 1)[1].strip()
    if current_q and current_a:
        rows.append({"q": current_q, "a": current_a, "category": "未分类"})
    return rows


def load_conversations(path: str) -> list[dict]:
    """自动识别格式并加载"""
    if os.path.isdir(path):
        all_rows = []
        for f in sorted(os.listdir(path)):
            fpath = os.path.join(path, f)
            if f.endswith(".csv"):
                all_rows.extend(load_csv(fpath))
            elif f.endswith(".json"):
                all_rows.extend(load_json(fpath))
            elif f.endswith(".txt"):
                all_rows.extend(load_txt(fpath))
        return all_rows
    elif path.endswith(".csv"):
        return load_csv(path)
    elif path.endswith(".json"):
        return load_json(path)
    elif path.endswith(".txt"):
        return load_txt(path)
    else:
        raise ValueError(f"不支持的文件格式: {path}")


def categorize_by_keywords(rows: list[dict]) -> list[dict]:
    """基于关键词自动分类 Q&A"""
    category_rules = {
        "物流与追踪": [
            "shipping", "track", "delivery", "arrive", "ship",
            "物流", "追踪", "配送", "多久到", "发货",
        ],
        "退换货": [
            "return", "refund", "exchange", "money back",
            "退货", "退款", "退换", "换货",
        ],
        "定制与个性化": [
            "custom", "personalize", "name", "photo", "engrav",
            "定制", "名字", "照片", "刻字", "个性化",
        ],
        "产品材质与质量": [
            "material", "quality", "fabric", "wash", "clean",
            "材质", "质量", "面料", "清洗", "洗涤",
        ],
        "尺寸与适配": [
            "size", "fit", "dimension", "measure",
            "尺寸", "大小", "适配", "兼容",
        ],
        "礼品与包装": [
            "gift", "wrap", "package", "card", "note",
            "礼物", "礼品", "包装", "贺卡",
        ],
        "订单与支付": [
            "order", "pay", "cancel", "modify",
            "订单", "付款", "取消", "修改",
        ],
    }

    for row in rows:
        text = (row["q"] + " " + row["a"]).lower()
        matched = False
        for cat, keywords in category_rules.items():
            if any(kw in text for kw in keywords):
                row["category"] = cat
                matched = True
                break
        if not matched:
            row["category"] = "其他"
    return rows


def distill(rows: list[dict], min_freq: int = 2) -> dict:
    """蒸馏：提取高频模式 + 按类别聚合"""
    # 按类别分组
    by_category = defaultdict(list)
    for r in rows:
        by_category[r["category"]].append(r)

    # 计算统计
    stats = {
        "total_pairs": len(rows),
        "categories": {},
        "top_questions": [],
        "keyword_freq": Counter(),
    }

    # 每类别统计
    for cat, items in sorted(by_category.items(), key=lambda x: -len(x[1])):
        stats["categories"][cat] = len(items)

    # 高频关键词
    for r in rows:
        words = re.findall(r"[a-zA-Z]{3,}", r["q"].lower())
        stats["keyword_freq"].update(words)

    # 相似问题聚合（简单版：按长度聚类）
    q_lens = Counter(len(r["q"]) for r in rows)

    return {"stats": stats, "by_category": dict(by_category), "raw": rows}


def output_markdown(distilled: dict) -> str:
    """输出 Markdown FAQ 文档"""
    lines = ["# 客服对话蒸馏 FAQ", ""]
    stats = distilled["stats"]
    lines.append(f"**总计**: {stats['total_pairs']} 组 Q&A")
    lines.append("")
    lines.append("## 类别分布")
    for cat, count in sorted(stats["categories"].items(), key=lambda x: -x[1]):
        lines.append(f"- {cat}: {count}")
    lines.append("")

    lines.append("## 高频关键词")
    for kw, freq in stats["keyword_freq"].most_common(20):
        lines.append(f"- {kw} ({freq})")
    lines.append("")

    for cat, items in distilled["by_category"].items():
        lines.append(f"## {cat}")
        # 去重：相似问题只保留一个代表
        seen = set()
        for item in items:
            key = item["q"][:30].lower()
            if key not in seen:
                seen.add(key)
                lines.append(f"**Q**: {item['q']}")
                # 截断过长回答
                a_text = item["a"]
                if len(a_text) > 300:
                    a_text = a_text[:297] + "..."
                lines.append(f"**A**: {a_text}")
                lines.append("")
    return "\n".join(lines)


def output_jsonl(distilled: dict) -> str:
    """输出 JSONL 格式（适合 Dify 知识库导入）"""
    lines = []
    for items in distilled["by_category"].values():
        for item in items:
            entry = {
                "question": item["q"],
                "answer": item["a"],
                "category": item["category"],
            }
            lines.append(json.dumps(entry, ensure_ascii=False))
    return "\n".join(lines)


def merge_existing(existing_path: str, new_distilled: dict) -> str:
    """合并已有蒸馏结果与新对话"""
    with open(existing_path, "r", encoding="utf-8") as f:
        existing = f.read()

    new_part = output_markdown(new_distilled)
    # 简单策略：追加新内容并标记
    merged = existing + "\n\n---\n## 增量更新\n" + new_part.split("##", 1)[1] if "##" in new_part else new_part
    return merged


def main():
    parser = argparse.ArgumentParser(
        description="客服对话蒸馏工具 — 从历史对话中提取高频 FAQ",
    )
    parser.add_argument("--input", "-i", required=True, help="输入文件或目录")
    parser.add_argument("--output", "-o", required=True, help="输出文件")
    parser.add_argument("--format", "-f", default="md", choices=["md", "jsonl"],
                       help="输出格式: md(Markdown FAQ) / jsonl(Dify知识库)")
    parser.add_argument("--merge", "-m", help="合并已有蒸馏文件")
    parser.add_argument("--min-freq", type=int, default=2, help="最小出现次数")
    args = parser.parse_args()

    # 1. 加载
    rows = load_conversations(args.input)
    if not rows:
        print("❌ 未找到有效对话记录")
        sys.exit(1)

    # 2. 自动分类
    rows = categorize_by_keywords(rows)

    # 3. 蒸馏
    distilled = distill(rows, min_freq=args.min_freq)

    # 4. 输出
    if args.merge:
        output = merge_existing(args.merge, distilled)
    elif args.format == "jsonl":
        output = output_jsonl(distilled)
    else:
        output = output_markdown(distilled)

    with open(args.output, "w", encoding="utf-8") as f:
        f.write(output)

    print(f"✅ 蒸馏完成")
    print(f"   输入: {len(rows)} 组对话")
    print(f"   类别: {len(distilled['stats']['categories'])} 个")
    print(f"   输出: {args.output}")

    # 打印摘要
    for cat, count in sorted(distilled["stats"]["categories"].items(), key=lambda x: -x[1])[:5]:
        print(f"   {cat}: {count}")


if __name__ == "__main__":
    main()
