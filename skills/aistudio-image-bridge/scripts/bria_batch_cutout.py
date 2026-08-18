#!/usr/bin/env python3
"""批量 BRIA-RMBG-2.0 抠图：扫描 base 目录下各方向子目录的干净原图，
逐个跑 remove_background 生成透明 PNG（默认 *_bria.png），并汇总 metadata。

用法：
  python bria_batch_cutout.py --base path1_out --mode pod_print
  python bria_batch_cutout.py --base path1_out --summary summary.json --hf-token hf_xxx

输出：每个 <Dir>/<network_0_*.jpg> 旁生成 <network_0_*>_bria.png + 同名 _bria_meta.json；
      若 --summary 指定，额外写一份汇总 JSON。
"""
import argparse
import sys
import os
import json
import glob


def main():
    ap = argparse.ArgumentParser(description="批量 BRIA-RMBG-2.0 抠图")
    ap.add_argument("--base", default="path1_out",
                    help="含各方向子目录的基目录（默认 path1_out）")
    ap.add_argument("--mode", default="pod_print",
                    choices=["pod_print", "product", "portrait"],
                    help="抠图模式（默认 pod_print=POD印花/图形锐边）")
    ap.add_argument("--suffix", default="_bria", help="输出 PNG 后缀（默认 _bria）")
    ap.add_argument("--summary", default=None, help="把汇总 metadata 写到该 JSON")
    ap.add_argument("--hf-token", default=None,
                    help="HuggingFace read token（gated 仓库必需；也可设 env HF_TOKEN）")
    ap.add_argument("--device", default=None, help="cpu / cuda（默认自动）")
    args = ap.parse_args()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import bria_rmbg_cutout as core

    # 依赖自检
    if core._need_deps():
        sys.exit(2)

    base = args.base
    if not os.path.isdir(base):
        sys.stderr.write(f"base 目录不存在: {base}\n")
        sys.exit(3)

    # 收集所有待处理原图：每个子目录取第一张 network_0_*.jpg
    jobs = []
    for d in sorted(glob.glob(os.path.join(base, "*"))):
        if not os.path.isdir(d):
            continue
            # 跳过非图产物子目录（retry/diag 等）
        name = os.path.basename(d.rstrip("/\\"))
        if any(k in name for k in ("_retry", "_diag", "_tmp")):
            continue
        imgs = sorted(glob.glob(os.path.join(d, "network_0_*.jpg")))
        imgs += sorted(glob.glob(os.path.join(d, "network_0_*.png")))
        if not imgs:
            continue
        jobs.append((name, imgs[0]))

    if not jobs:
        sys.stderr.write("未找到任何 network_0_*.jpg 原图\n")
        sys.exit(4)

    print(f"找到 {len(jobs)} 个方向待抠图：")
    for name, img in jobs:
        print(f"  - {name}: {os.path.basename(img)}")

    results = []
    ok = 0
    for name, img in jobs:
        out = os.path.splitext(img)[0] + args.suffix + ".png"
        meta_out = os.path.splitext(img)[0] + args.suffix + "_meta.json"
        try:
            out_path, meta = core.remove_background(
                img, mode=args.mode, out=out, meta_out=meta_out,
                device=args.device, token=args.hf_token,
            )
            passed = meta["quality"]["passed"]
            status = meta["status"]
            print(f"[{'OK' if passed else 'WARN'}] {name}: {status} "
                  f"fg={meta['quality']['foreground_ratio']:.3f} "
                  f"score={meta['quality']['score']} -> {os.path.basename(out_path)}")
            results.append({"dir": name, "input": img, "output": out_path,
                            "meta": meta, "error": None})
            if passed:
                ok += 1
        except Exception as e:
            err = repr(e)
            print(f"[FAIL] {name}: {err[:160]}")
            results.append({"dir": name, "input": img, "output": None,
                            "meta": None, "error": err})

    print(f"\n汇总：{ok}/{len(jobs)} 通过质检；"
          f"{len(jobs) - ok} 待人工复核/失败")
    if args.summary:
        with open(args.summary, "w", encoding="utf-8") as f:
            json.dump({"mode": args.mode, "total": len(jobs), "passed": ok,
                       "results": results}, f, ensure_ascii=False, indent=2)
        print(f"汇总已写: {args.summary}")


if __name__ == "__main__":
    main()
