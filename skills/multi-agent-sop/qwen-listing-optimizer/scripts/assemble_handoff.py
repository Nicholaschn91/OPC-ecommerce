#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
assemble_handoff.py — 人工交接区（human-in-the-loop 手动路径）产出器。

半自动流程里，终版优化有一步是「人拿提示词去 Qwen3.8-Max 网页端跑、再把输出贴回」。
本脚本把这一步需要的全部物料，落到**固定落点** `_e2e_out/<spu>/`，免去每次临时找文件、手动拼装：

  <spu>/
    prompt_to_run.txt   # 完整提示词纯文本 —— 全选复制 → 粘 Qwen3.8-Max 网页端 → 发送
    HANDOFF.md          # 人工步骤卡（复制 → 发送 → 贴回 clean.md → 告 agent 跑校验）
    clean.md            # 占位：把 Qwen 输出整段贴到首行注释之下
    listing_bundle.json # 拷贝 Stage1 产物，供参考
    <spu>_etsy_v1.md    # 拷贝初版草稿，供参考

手工路径与自动路径（build-inject.py 产 .js 片段经 browser-qwen 注入）共用同一套
装配顺序 + 防蚕食账本约束 + 软层自检清单；本脚本只负责把「人要跑的那一份」落到固定位置。

用法（在 workspace 根目录执行）：
  python assemble_handoff.py --spu S3-04
  python assemble_handoff.py --spu S3-04 --bundle _e2e_out/S3-04_listing_bundle.json --out-dir _e2e_out/S3-04
"""
import argparse
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # multi-agent-sop
SKILL = os.path.join(ROOT, "qwen-listing-optimizer")
LEDGER_SKILL = os.path.join(ROOT, "listing-v1-seo-builder", "scripts")
PROMPT_MD = os.path.join(SKILL, "qwen3.8-max-listing-optimizer-prompt.md")


def read_text(p):
    with open(p, encoding="utf-8") as f:
        return f.read()


def strip_frontmatter(md):
    if md.startswith("---"):
        end = md.find("\n---", 3)
        if end != -1:
            return md[end + 4:].lstrip("\n")
    return md


def prompt_body(md):
    md = strip_frontmatter(md)
    i = md.find("【角色设定】")
    return md[i:] if i != -1 else md


def find_first(paths):
    for p in paths:
        if p and os.path.exists(p):
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spu", required=True, help="商品 SPU，如 S3-04")
    ap.add_argument("--bundle", default=None, help="Stage1 产物 listing_bundle.json（默认按 <spu>_listing_bundle.json 在工作区找）")
    ap.add_argument("--prompt", default=PROMPT_MD, help="终版提示词 md")
    ap.add_argument("--out-dir", default=None, help="交接包输出目录（默认 ./_e2e_out/<spu>）")
    ap.add_argument("--ledger", default=None, help="防蚕食账本 JSON 路径（默认 ~/.workbuddy/data/opc-seo/...）")
    ap.add_argument("--line", default="线一全量", help="线别声明")
    ap.add_argument("--mode", default="full", choices=["full", "copy"], help="full=含视觉；copy=仅文案")
    args = ap.parse_args()

    if args.ledger:
        os.environ["OPC_SEO_LEDGER"] = os.path.abspath(args.ledger)

    work = os.getcwd()
    out_dir = args.out_dir or os.path.join(work, "_e2e_out", args.spu)
    os.makedirs(out_dir, exist_ok=True)

    bundle = args.bundle or find_first([
        os.path.join(work, "_e2e_out", f"{args.spu}_listing_bundle.json"),
        os.path.join(work, f"{args.spu}_listing_bundle.json"),
    ])
    if not bundle or not os.path.exists(bundle):
        print(f"⚠️ 未找到 Stage1 bundle（--bundle 或默认路径均无），仅产出提示词框架")
        bundle = None
    v1 = find_first([
        os.path.join(work, "_e2e_out", f"{args.spu}_etsy_v1.md"),
        os.path.join(LEDGER_SKILL, "output", f"{args.spu}_etsy_v1.md"),
    ])

    if LEDGER_SKILL not in sys.path:
        sys.path.insert(0, LEDGER_SKILL)

    pb = prompt_body(read_text(args.prompt))
    data = read_text(bundle) if bundle else "（未提供 listing_bundle，请附上初版结构化产物）"

    launch = (
        "【启动指令】\n"
        f"- 优化线别：{args.line}\n"
        f"- 输出模式：{'全量（含 Step4 视觉 Prompt×7）' if args.mode == 'full' else '仅文案（跳过 Step4 视觉）'}\n"
        "请按上述线别与模式，严格按提示词 Step1→5 执行，不暂停、连续输出。\n\n"
    )

    rule_block = ""
    try:
        import cannibalization_ledger as cl
        rule_block, found = cl.render_rule_block(args.spu, None)
        print(f"🛡️ 防蚕食约束块命中账本={found}: {args.spu}")
    except Exception as e:
        print(f"⚠️ 账本读取失败（跳过注入）: {type(e).__name__}: {e}")

    soft_block = ""
    try:
        import gate_soft as gate_soft
        soft_block = gate_soft.soft_rubric_text()
        print("🟡 SOFT_RUBRIC 已生成")
    except Exception as e:
        print(f"⚠️ 软层读取失败（跳过注入）: {type(e).__name__}: {e}")

    parts = [pb, "\n\n", launch]
    if rule_block:
        parts += ["\n", rule_block, "\n"]
    parts += [
        "\n",
        "【初版结构化产物 listing_bundle（%s）—— 即本次优化要消费的草稿与词表，替代「原始 Description + YAML 视觉包」作为输入】\n" % args.spu,
        data,
    ]
    if soft_block:
        parts += ["\n\n", soft_block, "\n"]
    full = "".join(parts)

    # 1) 纯文本提示词（人直接复制）
    prompt_path = os.path.join(out_dir, "prompt_to_run.txt")
    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(full)

    # 2) 人工步骤卡
    handoff_path = os.path.join(out_dir, "HANDOFF.md")
    handoff = (
        f"# 人工交接卡 · {args.spu} 终版优化（Qwen3.8-Max 网页端）\n\n"
        "本目录是半自动流程里「人跑模型」这一步的固定落点。\n\n"
        "## 你要做的 4 步\n"
        "1. 打开同目录 `prompt_to_run.txt`，**全选复制全部内容**。\n"
        "2. 打开 Qwen3.8-Max 网页端（qianwen.com / tongyi.aliyun.com），把内容**粘贴进对话框 → 发送**。\n"
        "3. 模型会连续输出 Step1→5 + 末尾 `BASE_MATERIAL` 块。把**从「Step 1」到 `BASE_MATERIAL` 结束的整段**复制。\n"
        "4. 回到本目录，打开 `clean.md`，**贴到首行注释之下**，保存。然后告诉 agent：「跑 S3-04 校验」。\n\n"
        "## agent 接下来会做\n"
        "- 用 `verify-ledger.py` 跑闸门（防蚕食唯一性 + 三级熔断 + 字段回读 + 软层 review）。\n"
        "- 无 MELTDOWN/CRITICAL_STOP 后，按 SHARED_CONTEXT append/merge 语义写飞书（须你逐条授权）。\n\n"
        "## 参考物料\n"
        "- `listing_bundle.json`：Stage1 产物（词策略蓝图）。\n"
        f"- `{args.spu}_etsy_v1.md`：初版草稿（若存在）。\n"
        "- 自动路径（browser-qwen 注入）不走本目录，由 build-inject.py 产出 .js 片段。\n"
    )
    with open(handoff_path, "w", encoding="utf-8") as f:
        f.write(handoff)

    # 3) clean.md 占位
    clean_path = os.path.join(out_dir, "clean.md")
    if not os.path.exists(clean_path):
        with open(clean_path, "w", encoding="utf-8") as f:
            f.write(
                "<!-- 把 Qwen3.8-Max 的完整输出（Step 1 → Step 5 + BASE_MATERIAL 块）整段贴到本行之下，然后保存并告知 agent 跑校验 -->\n"
            )

    # 4) 拷贝参考物料
    if bundle:
        try:
            shutil.copy(bundle, os.path.join(out_dir, os.path.basename(bundle)))
        except Exception as e:
            print(f"⚠️ 拷贝 bundle 失败: {e}")
    if v1:
        try:
            shutil.copy(v1, os.path.join(out_dir, os.path.basename(v1)))
        except Exception as e:
            print(f"⚠️ 拷贝 v1 失败: {e}")

    print(f"✅ 交接包已生成于: {out_dir}")
    print(f"   - prompt_to_run.txt ({len(full)} 字符)")
    print(f"   - HANDOFF.md")
    print(f"   - clean.md (占位，待贴回)")


if __name__ == "__main__":
    main()
