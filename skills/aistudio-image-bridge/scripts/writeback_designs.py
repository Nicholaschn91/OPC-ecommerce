#!/usr/bin/env python3
"""
批量回写：原始干净图 + BRIA 抠图 一并写入飞书「设计方案图片」字段。

输入映射文件 (JSON)，支持两种格式：
  # 字典 {方向: record_id}
  {
    "DirA_Amazon_1": "recXXXX",
    "DirA_Etsy_1": "recYYYY"
  }
  # 或数组 [{dir, record_id}]
  [{"dir":"DirA_Amazon_1","record_id":"recXXXX"}, ...]

对每条设计：
  1. 定位 path1_out/<dir>/network_0_*.jpg 原图；
  2. 若缺 <stem>_bria.png 则调用 bria_rmbg_cutout 生成透明 PNG；
  3. 将 [原图, 抠图] 一并写回该 record 的「设计方案图片」。

依赖：
  - BRIA-RMBG-2.0 已安装（见 bria_rmbg_cutout.py；未装会在生成抠图时报错退出）
  - 飞书凭证在 references/config.json（不入库）

Usage:
  python writeback_designs.py --map mapping.json
  python writeback_designs.py --map mapping.json             # 默认合并已有图片
  python writeback_designs.py --map mapping.json --overwrite  # 显式覆盖（清空该记录已有图片）
  python writeback_designs.py --map mapping.json --skip-cutout --base path1_out  # 假设抠图已生成
"""
import argparse
import sys
import os
import json
import glob

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import write_image_attachment as W


def find_original(base, d):
    hits = sorted(glob.glob(os.path.join(base, d, "network_0_*.jpg")))
    return hits[0] if hits else None


def main():
    ap = argparse.ArgumentParser(description="原始图+BRIA抠图 一并回写飞书")
    ap.add_argument("--map", required=True,
                    help="JSON 映射 {dir: record_id} 或 [{dir, record_id}]")
    ap.add_argument("--base", default="path1_out",
                    help="原图根目录 (默认 path1_out)")
    ap.add_argument("--merge", action="store_true", default=True,
                    help="合并已有图片而非覆盖（默认开启）")
    ap.add_argument("--overwrite", dest="merge", action="store_false",
                    help="显式覆盖：清空该记录已有图片后写入")
    ap.add_argument("--skip-cutout", action="store_true",
                    help="假设抠图已存在，不再生成")
    args = ap.parse_args()

    with open(args.map, encoding="utf-8") as f:
        raw = json.load(f)
    if isinstance(raw, list):
        mapping = {e["dir"]: e["record_id"] for e in raw}
    else:
        mapping = raw

    need_cutout = not args.skip_cutout
    if need_cutout:
        try:
            import bria_rmbg_cutout  # noqa: F401
        except Exception as e:
            sys.stderr.write(f"无法导入 bria_rmbg_cutout（BRIA 未安装？）: {e}\n")
            sys.exit(2)

    token = W.get_token()
    ok = 0
    for d, rid in mapping.items():
        orig = find_original(args.base, d)
        if not orig:
            sys.stderr.write(f"[SKIP] {d}: 未找到原图 network_0_*.jpg\n")
            continue
        cut = os.path.join(
            os.path.dirname(orig),
            os.path.splitext(os.path.basename(orig))[0] + "_bria.png",
        )
        if need_cutout and not os.path.exists(cut):
            print(f"[cutout] {d}: 生成 {cut}")
            try:
                import bria_rmbg_cutout as B
                B.remove_background(orig, mode="pod_print", out=cut)
            except Exception as e:
                sys.stderr.write(f"[SKIP] {d}: BRIA 抠图失败 {e}\n")
                continue
        if not os.path.exists(cut):
            sys.stderr.write(f"[SKIP] {d}: 抠图缺失 {cut}\n")
            continue

        # 上传两张（原图 + 抠图）
        tokens = []
        for p in (orig, cut):
            try:
                tokens.append(W.upload_image_to_drive(token, p))
            except Exception as e:
                sys.stderr.write(f"  上传失败 {os.path.basename(p)}: {e}\n")
        if not tokens:
            continue
        if args.merge:
            existing = W.verify_attachments(token, rid)
            if existing:
                tokens = [a["file_token"] for a in existing if a.get("file_token")] + tokens
        W.write_attachments(token, rid, tokens)
        # 列表接口回验（飞书铁律：避免单条 GET 最终一致性陷阱）
        att = W.verify_attachments(token, rid)
        if att:
            print(f"[OK] {d} -> {rid}: {len(att)} 张 (原图 + BRIA 抠图)")
            ok += 1
        else:
            sys.stderr.write(f"[VERIFY FAIL] {d} -> {rid}\n")
    print(f"\n完成：{ok}/{len(mapping)} 条回写成功")


if __name__ == "__main__":
    main()
