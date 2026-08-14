#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean-capture.py — 把「Blob 下载捕获的原始 md」清洗为可交付版本。

原始捕获（经 playwright-qwen MCP 的 download 事件落盘）含：
  顶部页面 chrome + 深度思考块 + 正式输出 + 底部输入框 chrome。

清洗规则：
  - 去除深度思考块（"深度思考已完成" 之前的内容）；
  - 从正式输出标题起（默认 "Etsy Listing 终版优化"）；
  - 截到输入栏标记前（默认 "你好，我是千问"）；
  - 删除孤立的工具栏行（表格 / 复制 / 编辑 等）。

用法：
  python clean-capture.py --in S3-02-qianwen-com-out.md --out S3-02-qianwen-com-out-clean.md
"""
import argparse


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', required=True, help='Blob 下载的原始捕获 md')
    ap.add_argument('--out', required=True, help='清洗后交付 md')
    ap.add_argument('--start', default='Etsy Listing 终版优化', help='正式输出起始标题')
    ap.add_argument('--end', default='你好，我是千问', help='底部输入栏标记，截到此前')
    args = ap.parse_args()

    t = open(args.inp, encoding='utf-8').read()

    # 去深度思考块
    i = t.find('深度思考已完成')
    j = t.find(args.start)
    if i != -1 and j != -1 and i < j:
        t = t[j:]
    elif j != -1:
        t = t[j:]

    # 去底部输入栏 chrome
    k = t.rfind(args.end)
    if k != -1:
        t = t[:k].rstrip() + '\n'

    # 去孤立工具栏行
    skip = {'表格', '下载为表格', '导出为图片', '文本', '编辑', '代码', '复制', '深挖', '重新生成'}
    lines = [ln for ln in t.split('\n') if ln.strip() not in skip]
    clean = '\n'.join(lines).strip() + '\n'
    open(args.out, 'w', encoding='utf-8').write(clean)
    print(f"wrote {args.out}: {len(clean)} chars")


if __name__ == '__main__':
    main()
