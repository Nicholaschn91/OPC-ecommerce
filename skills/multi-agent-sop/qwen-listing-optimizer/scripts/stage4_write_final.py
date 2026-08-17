#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stage4_write_final.py — Stage 4 落库：把终版 clean.md 写进飞书。

三阶段落点（本次补全「终版字段」这一截）：
  ① 初版字段  ← stage1_feishu_sync.py（gen_v1 回写）
  ② 终版字段  ← 本脚本（本平台精修成品，规范化存储）
  ③ SHARED_CONTEXT ← 本脚本（跨平台复用缓冲：把终版 copy 累加进去）
  + keyword_plan ← 本脚本（词策略蓝图，与 product_truth 并列）

飞书写记录要点（已踩坑）：fields 键用 field_name，不是 field_id。

用法：
  python stage4_write_final.py --spu S3-04 --platform etsy --record recvrFHcugir3U \
      --clean _e2e_out/S3-04/clean.md --bundle _e2e_out/S3-04_listing_bundle.json
"""
import os
import re
import sys
import json
import argparse

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MULTI = os.path.dirname(os.path.dirname(SCRIPT_DIR))  # .../multi-agent-sop
BRIDGE = os.path.join(MULTI, "aistudio-image-bridge", "scripts")
sys.path.insert(0, BRIDGE)
import feishu_products_io as F

# 平台 → 终版「描述」字段名（表2 现有；无则只写 SHARED_CONTEXT）
FINAL_DESC_FIELD = {
    "etsy":   "Etsy_Desc_终版",
    "amazon": "Amazon_五点描述_终版",
    "ebay":   "eBay_Bullets_终版",
}


def parse_clean(md, platform):
    """从 clean.md 抽取本平台终版的 标题 / Tags / Description。"""
    # 标题：优化后标题：<可能两行>
    m = re.search(r"优化后标题[:：]\s*\n?(.+?)(?:\n\s*\n|\n\s*-\s|\Z)", md, re.S)
    title = ""
    if m:
        title = re.sub(r"\s+", " ", m.group(1).strip())

    # Tags：编号行 `1.  personalise tote (T4#1 ...)` → 取第一个 ( 前的内容
    tags = []
    for ln in md.splitlines():
        mm = re.match(r"^\s*\d+[\.、]\s+(.+?)\s*\(", ln)
        if mm:
            tags.append(mm.group(1).strip())
    tags = [t for t in tags if t and len(t) <= 30]

    # Description：Step 3 段（纯英文 Description）到 Step 4 或视觉 Prompt 前
    m = re.search(r"Step\s*3[：:].*?(纯英文\s*Description)?(.*?)(?=Step\s*4|视觉\s*Prompt|执行检查清单|基材输出块)", md, re.S | re.I)
    desc = m.group(2).strip() if m else ""

    return title, tags, desc


def build_shared_block(platform, title, tags, desc):
    return (
        f"=== {platform.capitalize()} ===\n"
        f"Title: {title}\n"
        f"Tags: {' | '.join(tags)}\n"
        f"Description:\n{desc}\n"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spu", required=True)
    ap.add_argument("--platform", required=True, choices=list(FINAL_DESC_FIELD))
    ap.add_argument("--record", required=True)
    ap.add_argument("--clean", required=True, help="clean.md 路径")
    ap.add_argument("--bundle", required=True, help="listing_bundle.json 路径")
    args = ap.parse_args()

    md = open(args.clean, encoding="utf-8").read()
    title, tags, desc = parse_clean(md, args.platform)
    print(f"📤 解析终版({args.platform}): 标题 {len(title)}字符 / Tags {len(tags)} / Desc {len(desc)}字符")

    # --- SHARED_CONTEXT 拼接 + 合并（跨平台累加，禁覆盖）---
    etag = build_shared_block(args.platform, title, tags, desc)
    T = F.get_token()
    cur = F.api("GET",
                f"https://open.feishu.cn/open-apis/bitable/v1/apps/{F.APP_TOKEN}/tables/{F.TABLE_ID}/records/{args.record}",
                token=T)
    cur_fields = cur.get("data", {}).get("record", {}).get("fields", {})
    existing = cur_fields.get("SHARED_CONTEXT", "") or ""
    if not existing.strip():
        new_shared = etag
    elif f"=== {args.platform.capitalize()} ===" in existing:
        new_shared = re.sub(
            rf"=== {args.platform.capitalize()} ===.*?(?=\n=== |\Z)",
            etag.rstrip("\n") + "\n", existing, flags=re.S)
    else:
        new_shared = existing.rstrip("\n") + "\n" + etag

    # --- keyword_plan 文本化（T4→T1 + 意图）---
    bun = json.load(open(args.bundle, encoding="utf-8"))
    kp = bun.get("keyword_plan", {})
    intent_map = {}
    for tier in ("T4", "T3", "T2", "T1"):
        for it in kp.get("intent", {}).get(tier, []):
            intent_map[it["kw"]] = it["intent"]
    tier_label = {"T4": "T4 利润尖刀(交易型优先)", "T3": "T3 材质/场景/属性",
                  "T2": "T2 受众/用途", "T1": "T1 风格/长尾红海"}
    kw_lines = [f"source_platform: {kp.get('source_platform')}", ""]
    for tier in ("T4", "T3", "T2", "T1"):
        kw_lines.append(f"{tier} — {tier_label[tier]}:")
        for w in kp.get(tier, []):
            kw_lines.append(f"  - {w} [{intent_map.get(w, '?')}]")
        kw_lines.append("")
    keyword_plan_text = "\n".join(kw_lines).strip()

    # --- 组装写字段：终版字段 + SHARED_CONTEXT + keyword_plan ---
    fields = {
        "SHARED_CONTEXT": new_shared,
        "keyword_plan": keyword_plan_text,
    }
    final_desc_field = FINAL_DESC_FIELD.get(args.platform)
    if final_desc_field and desc:
        fields[final_desc_field] = desc

    print(f"✍️ 将写入字段: {list(fields.keys())}")
    resp = F.api("PUT",
                 f"https://open.feishu.cn/open-apis/bitable/v1/apps/{F.APP_TOKEN}/tables/{F.TABLE_ID}/records/{args.record}",
                 token=T, body={"fields": fields})
    if resp.get("code") != 0:
        print(f"❌ 写失败: code={resp.get('code')} msg={resp.get('msg')}")
        print(resp)
        sys.exit(1)

    # --- 主确认（PUT 响应自带写后 fields，最权威）---
    wf = resp.get("data", {}).get("record", {}).get("fields", {})
    sv = (wf.get("SHARED_CONTEXT") or "").strip()
    kv = (wf.get("keyword_plan") or "").strip()
    fd = (wf.get(final_desc_field) or "").strip() if final_desc_field else "N/A"
    print(f"✅ PUT code=0")
    has_block = f"=== {args.platform.capitalize()} ===" in sv
    print(f"   SHARED_CONTEXT 非空={bool(sv)} (len={len(sv)}); 含[{args.platform.capitalize()}]块={has_block}")
    print(f"   keyword_plan 非空={bool(kv)} (len={len(kv)})")
    if final_desc_field:
        print(f"   {final_desc_field} 非空={bool(fd)} (len={len(fd)})")

    # --- 兜底（列表接口扫描，处理分页）---
    page_token = None
    lf = None
    while True:
        u = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{F.APP_TOKEN}/tables/{F.TABLE_ID}/records?page_size=100"
        if page_token:
            u += f"&page_token={page_token}"
        sc = F.api("GET", u, token=T)
        for it in sc.get("data", {}).get("items", []):
            if it.get("record_id") == args.record:
                lf = it.get("fields", {})
                break
        if lf is not None or not sc.get("data", {}).get("has_more"):
            break
        page_token = sc.get("data", {}).get("page_token")
    if lf is not None:
        print(f"🔎 兜底回验: SHARED_CONTEXT={bool((lf.get('SHARED_CONTEXT') or '').strip())}, "
              f"keyword_plan={bool((lf.get('keyword_plan') or '').strip())}, "
              f"{final_desc_field}={bool((lf.get(final_desc_field) or '').strip()) if final_desc_field else 'N/A'}")
    else:
        print("⚠️ 列表接口分页未扫到（主确认已通过，无需担忧）")


if __name__ == "__main__":
    main()
