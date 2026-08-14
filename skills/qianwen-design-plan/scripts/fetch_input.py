#!/usr/bin/env python3
"""
fetch_input.py — 从飞书商品表取「商品基础信息」，落盘为 aistudio_design_plan.cjs 的 --input

复用 aistudio-visualbridge/scripts/feishu_products_io.py 的鉴权与读取逻辑，不重复实现。

用法:
  python fetch_input.py <record_id> [-o 输出.txt]
  python fetch_input.py --list-empty        # 列出「商品基础信息」有值但「设计方案」为空的记录
"""
import os
import sys
import argparse

_VB = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "..", "aistudio-visualbridge", "scripts",
)
sys.path.insert(0, os.path.abspath(_VB))

try:
    from feishu_products_io import get_token, get_record, list_records  # noqa: E402
except Exception as e:  # pragma: no cover
    print(f"错误：无法加载 feishu_products_io（{_VB}）: {e}", file=sys.stderr)
    sys.exit(2)

SRC_FIELD = "商品基础信息"
DST_FIELD = "设计方案"


def _flatten(v):
    """飞书文本字段可能是 str / list[dict{text}] / None。"""
    if v is None:
        return ""
    if isinstance(v, str):
        return v
    if isinstance(v, list):
        return "".join(
            x.get("text", "") if isinstance(x, dict) else str(x) for x in v
        )
    return str(v)


def main():
    ap = argparse.ArgumentParser(description="取飞书「商品基础信息」→ 文本文件")
    ap.add_argument("record_id", nargs="?", help="飞书 record_id")
    ap.add_argument("-o", "--out", help="输出文件路径（默认 stdout）")
    ap.add_argument(
        "--list-empty",
        action="store_true",
        help="列出有基础信息但设计方案为空的记录",
    )
    a = ap.parse_args()

    token = get_token()

    if a.list_empty:
        rows = list_records(token)
        n = 0
        for it in rows:
            f = it.get("fields", {})
            if _flatten(f.get(SRC_FIELD)).strip() and not _flatten(f.get(DST_FIELD)).strip():
                print(f"{it.get('record_id')} | {_flatten(f.get('商品名称')) or '(no name)'}")
                n += 1
        print(f"\n共 {n} 条待生成设计方案", file=sys.stderr)
        return

    if not a.record_id:
        ap.error("需要 record_id（或使用 --list-empty）")

    fields = get_record(token, a.record_id).get("fields", {})
    text = _flatten(fields.get(SRC_FIELD)).strip()
    if not text:
        print(f"错误：记录 {a.record_id} 的「{SRC_FIELD}」为空。", file=sys.stderr)
        sys.exit(1)

    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        with open(a.out, "w", encoding="utf-8") as fh:
            fh.write(text)
        print(f"{a.out} ({len(text)} 字符)")
    else:
        sys.stdout.write(text)


if __name__ == "__main__":
    main()
