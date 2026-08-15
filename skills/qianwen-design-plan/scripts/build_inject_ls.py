#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_inject_ls.py — 优化版注入载荷生成器（配合 localStorage 缓存 SI 规范）。

背景：原 build_design_plan_inject.py 把完整的「SI 规范 + 商品信息」打包成 base64
注入，每条记录 ~19KB 的 SI base64 会随 browser_run_code_unsafe 的回显进入上下文，
45 条记录会累积 ~855KB，撑爆上下文。

优化：SI 规范（常量，~7KB 中文）只在首次通过浏览器写入 localStorage['dp_si_const']，
本脚本只生成「短小的注入片段」——内嵌商品信息的 base64（~200B）+ 从 localStorage
读取 SI 并拼接。模型收到的提示词与原来完全一致（SI+商品在同一消息），但每条记录的
回显从 19KB 降到 ~300B。

用法：
  python build_inject_ls.py --data <input_xxx.txt> --out <dp_run/dp_inject_xxx.js> [--mcp-root auto]
"""
import argparse
import base64
import glob
import json
import os
import shutil

MCP_ROOT_GLOB = (
    "C:/Users/nicho/.workbuddy/logs/mcp-runtime/"
    "custom-mcp_playwright-qwen-*/.playwright-mcp"
)

LAUNCH = (
    "请先判定该商品属于【方向A·名字/照片排版布局设计方案】还是【方向B·固定印花图案设计方案】，"
    "再严格按规范「八、输出格式强制规范（含 8.0 纯净输出协议）」输出对应平台的英文 Prompt"
    "（Amazon / eBay / Etsy）。不暂停、连续输出。"
)


def detect_mcp_root():
    cands = [p for p in glob.glob(MCP_ROOT_GLOB) if os.path.isdir(p)]
    return max(cands, key=os.path.getmtime) if cands else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True, help='商品基础信息文本')
    ap.add_argument('--out', required=True, help='产出的 .js 片段路径')
    ap.add_argument('--mcp-root', default='auto',
                    help="拷贝到 MCP 根目录：auto=自动探测｜<路径>｜none=不拷贝")
    a = ap.parse_args()

    data = open(a.data, encoding='utf-8').read().strip()
    pb64 = base64.b64encode(data.encode('utf-8')).decode('ascii')

    snippet = (
        "async (page) => {\n"
        "  const prodB64 = \"" + pb64 + "\";\n"
        "  const launch = " + json.dumps(LAUNCH, ensure_ascii=False) + ";\n"
        "  const siB64 = await page.evaluate(() => localStorage.getItem('dp_si_const'));\n"
        "  if (!siB64) return JSON.stringify({ err: 'NO_SI_CONST' });\n"
        "  const dec = (b) => page.evaluate((x) => {\n"
        "    const bin = atob(x); const bytes = new Uint8Array(bin.length);\n"
        "    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);\n"
        "    return new TextDecoder('utf-8').decode(bytes);\n"
        "  }, b);\n"
        "  const constText = await dec(siB64);\n"
        "  const prodText = await dec(prodB64);\n"
        "  const full = constText + prodText + \"\\n\\n\" + launch;\n"
        "  await page.evaluate(() => {\n"
        "    const el = document.querySelector('[contenteditable=\"true\"], [role=\"textbox\"], textarea');\n"
        "    if (el) el.focus();\n"
        "  });\n"
        "  await page.keyboard.insertText(full);\n"
        "  return JSON.stringify({ insertedLen: full.length });\n"
        "}\n"
    )

    with open(a.out, 'w', encoding='utf-8') as f:
        f.write(snippet)

    mcp_copied = None
    if a.mcp_root != 'none':
        root = None if a.mcp_root == 'auto' else a.mcp_root
        if root is None:
            root = detect_mcp_root()
        if root and os.path.isdir(root):
            dst = os.path.join(root, os.path.basename(a.out))
            shutil.copyfile(a.out, dst)
            mcp_copied = dst

    print(f"wrote {a.out}: product_b64 {len(pb64)} chars (SI read from localStorage)" +
          (f" | copied to {mcp_copied}" if mcp_copied else ""))


if __name__ == '__main__':
    main()
