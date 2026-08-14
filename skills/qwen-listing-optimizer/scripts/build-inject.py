#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build-inject.py — 组装「千问 Qwen3.8-Max 终版优化」注入载荷，
产出可直接作为 playwright-qwen MCP `browser_run_code_unsafe` 的 `code` 参数的 .js 片段。

为什么需要它：
  - 提示词 + 数据常 > 13K 字符，无法塞进对话上下文逐字输入；
  - `browser_run_code_unsafe` 的 Node 侧**无 fs / require / fetch**，不能在片段内读文件、写文件、发请求；
  - 解法：把完整注入文本 base64 内联进 .js 片段，agent 读文件→作为 code 参数传入，
    在浏览器内 atob 还原 → insertText 注入 contenteditable 输入框（触发 React 受控更新）。

用法：
  python build-inject.py \
    --prompt qwen3.8-max-listing-optimizer-prompt.md \
    --data wallet-data.txt \
    [--spec base-material-spec.json] \
    [--line "线一全量"] [--mode full|copy] \
    --out _inject_snippet.js

输出：_inject_snippet.js（含完整 base64 载荷），agent 读取其全文作为 browser_run_code_unsafe 的 code。
"""
import argparse
import base64


def read_text(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def strip_frontmatter(md):
    if md.startswith('---'):
        end = md.find('\n---', 3)
        if end != -1:
            return md[end + 4:].lstrip('\n')
    return md


def prompt_body(md):
    """取提示词正文（去掉 YAML frontmatter，从【角色设定】起；找不到则全量）。"""
    md = strip_frontmatter(md)
    i = md.find('【角色设定】')
    if i != -1:
        return md[i:]
    return md


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--prompt', required=True, help='系统提示词 md（qwen3.8-max-listing-optimizer-prompt.md）')
    ap.add_argument('--data', required=True, help='原始 Description + YAML 视觉包 + 联想词/竞品（合并文本）')
    ap.add_argument('--spec', help='00 基材提取产物 JSON（线一全量开视觉时建议提供）')
    ap.add_argument('--line', default='线一全量', help='线别声明：线一全量 / 线二小改 等')
    ap.add_argument('--mode', default='full', choices=['full', 'copy'], help='full=全量含视觉；copy=仅文案')
    ap.add_argument('--out', required=True, help='产出的 .js 片段路径')
    args = ap.parse_args()

    pb = prompt_body(read_text(args.prompt))
    data = read_text(args.data)
    spec = read_text(args.spec) if args.spec else ''

    launch = (
        "【启动指令】\n"
        f"- 优化线别：{args.line}\n"
        f"- 输出模式：{'全量（含 Step4 视觉 Prompt×7）' if args.mode == 'full' else '仅文案（跳过 Step4 视觉）'}\n"
        "请按上述线别与模式，严格按提示词 Step1→5 执行，不暂停、连续输出。\n\n"
    )

    parts = [pb, "\n\n", launch, "\n", data]
    if spec:
        parts += ["\n\n【基材 spec（00 基材提取产物，直接消费，勿重做 alt 提取）】\n", spec]
    full = "".join(parts)

    b64 = base64.b64encode(full.encode('utf-8')).decode('ascii')
    snippet = (
        "async (page) => {\n"
        "  const b64 = \"" + b64 + "\";\n"
        "  const txt = await page.evaluate((b) => {\n"
        "    const bin = atob(b);\n"
        "    const bytes = new Uint8Array(bin.length);\n"
        "    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);\n"
        "    return new TextDecoder('utf-8').decode(bytes);\n"
        "  }, b64);\n"
        "  await page.evaluate(() => {\n"
        "    const el = document.querySelector('[contenteditable=\"true\"], [role=\"textbox\"], textarea');\n"
        "    if (el) el.focus();\n"
        "  });\n"
        "  await page.keyboard.insertText(txt);\n"
        "  return JSON.stringify({ insertedLen: txt.length });\n"
        "}\n"
    )
    with open(args.out, 'w', encoding='utf-8') as f:
        f.write(snippet)
    print(f"wrote {args.out}: snippet {len(snippet)} chars, payload {len(full)} chars ({len(b64)} b64)")


if __name__ == '__main__':
    main()
