#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stage1_feishu_sync.py — Stage 1 落库：把 gen_v1 产出的初版(v1)回写飞书「初版」字段。

设计：gen_v1 只负责本地生成（scripts/output/<spu>_<platform>_v1.md），本脚本负责把
那份 v1 同步进飞书初版字段（Etsy_标题_初版 / Etsy_Tags_初版 / Etsy_Desc_初版 等），
覆盖该记录上可能存在的旧流水线遗留草稿（用户已授权「清遗留」）。

飞书写记录要点（已踩坑）：fields 键用 field_name，不是 field_id。

用法：
  python stage1_feishu_sync.py --spu S3-04 --platform etsy --record recvrFHcugir3U
  （--v1-md 可指定 gen_v1 输出路径，默认 scripts/output/<spu>_<platform>_v1.md）
"""
import os
import re
import sys
import argparse

# 复用 aistudio-visualbridge 的飞书 IO（凭证已配好）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MULTI = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # .../multi-agent-sop
BRIDGE = os.path.join(MULTI, "aistudio-visualbridge", "scripts")
sys.path.insert(0, BRIDGE)
import feishu_products_io as F

# 平台 → 初版字段名映射（表2 现有字段）
V1_FIELDS = {
    "etsy":   {"title": "Etsy_标题_初版", "tags": "Etsy_Tags_初版", "desc": "Etsy_Desc_初版"},
    "amazon": {"title": "Amazon_标题_初版", "tags": None, "desc": "Amazon_五点描述_初版"},
    "ebay":   {"title": "eBay_标题矩阵_初版", "tags": None, "desc": "eBay_Bullets_初版"},
}


def parse_v1_md(path):
    """从 gen_v1 输出的 v1 md 解析出 title / tags / desc。"""
    txt = open(path, encoding="utf-8").read()
    out = {"title": "", "tags": "", "desc": ""}

    # 标题： **标题_初版**（137/140）\n<一行标题>
    m = re.search(r"\*\*标题_初版\*\*\s*（[^）]*）\s*\n(.+)", txt)
    if m:
        out["title"] = m.group(1).strip()

    # Tags： **Tags_初版**（6/13）\n<用 | 分隔>
    m = re.search(r"\*\*Tags_初版\*\*\s*（[^）]*）\s*\n(.+)", txt)
    if m:
        out["tags"] = m.group(1).strip()

    # Desc： **Desc_初版**（...）\n<多行，到下一个 ** 段或文件尾>
    m = re.search(r"\*\*Desc_初版\*\*\s*（[^）]*）\s*\n(.*?)(?:\n\*\*[A-Za-z0-9])", txt, re.DOTALL)
    if m:
        out["desc"] = m.group(1).strip()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spu", required=True)
    ap.add_argument("--platform", required=True, choices=list(V1_FIELDS))
    ap.add_argument("--record", required=True, help="飞书记录 record_id")
    ap.add_argument("--v1-md", default=None, help="gen_v1 输出 md 路径（默认 scripts/output/<spu>_<platform>_v1.md）")
    args = ap.parse_args()

    here = os.path.dirname(os.path.abspath(__file__))
    default_md = os.path.join(here, "output", f"{args.spu}_{args.platform}_v1.md")
    v1md = args.v1_md or default_md
    if not os.path.exists(v1md):
        print(f"❌ 找不到 v1 md: {v1md}（请先跑 gen_v1 生成初版）")
        sys.exit(1)

    v1 = parse_v1_md(v1md)
    print(f"📤 解析 v1（{args.platform}）: 标题 {len(v1['title'])}字符 / Tags {len(v1['tags'])}字符 / Desc {len(v1['desc'])}字符")

    fmap = V1_FIELDS[args.platform]
    fields = {}
    if v1["title"]:
        fields[fmap["title"]] = v1["title"]
    if fmap["tags"] and v1["tags"]:
        fields[fmap["tags"]] = v1["tags"]
    if v1["desc"]:
        fields[fmap["desc"]] = v1["desc"]

    T = F.get_token()
    # 写初版字段（覆盖遗留草稿）
    r = F.api("PUT",
              f"https://open.feishu.cn/open-apis/bitable/v1/apps/{F.APP_TOKEN}/tables/{F.TABLE_ID}/records/{args.record}",
              token=T, body={"fields": fields})
    if r.get("code") != 0:
        print(f"❌ 写初版字段失败: code={r.get('code')} msg={r.get('msg')}")
        print(r)
        sys.exit(1)
    print(f"✅ 初版字段已回写（覆盖遗留）: {list(fields.keys())}")

    # 写后回验（列表接口扫描，铁律#8）
    scan = F.api("GET",
                 f"https://open.feishu.cn/open-apis/bitable/v1/apps/{F.APP_TOKEN}/tables/{F.TABLE_ID}/records?page_size=100",
                 token=T)
    items = scan.get("data", {}).get("items", [])
    tgt = [it for it in items if it.get("record_id") == args.record]
    if tgt:
        f = tgt[0].get("fields", {})
        for fname in fields:
            ok = bool((f.get(fname) or "").strip())
            print(f"   🔎 回验 {fname}: {'非空 ✅' if ok else '空 ❌'}")
    else:
        print("   ⚠️ 列表接口未扫到该记录（分页），PUT 响应已确认 code=0 即视为成功")


if __name__ == "__main__":
    main()
