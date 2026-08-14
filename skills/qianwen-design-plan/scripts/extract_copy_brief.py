#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_copy_brief.py — 从 v5.3 设计方案提取 Listing 文案创作基材。

v5.3 设计方案有两个消费路径：
  Path A → 生图：aistudio-visualbridge 的 parse_design.py 取「原始设计指令」段落（纯 prompt）
  Path B → 文案：本脚本取「视觉语义标签」「核心视觉卖点」「文案转化指引」三块，
                    与商品基础信息合并后发给大模型，生成标题/Description/Tags。

解析 v5.3 输出格式：
  方案 1: Amazon 渠道专属视觉
  【方向A · ...】
  原始设计指令: <MJ/SD prompt>
  视觉语义标签（中英双语）: #English1 #中文1 | #English2 #中文2 | ...
  核心视觉卖点:
  1. <视觉特征> + <消费者利益>
  2. ...
  文案转化指引: 
  - 强调: "<keyword1>", "<keyword2>"
  - 避免: "<negative1>", "<negative2>"
  - 推荐句式: "<template with [placeholder]>"

用法：
  PY="C:/Users/nicho/.workbuddy/binaries/python/envs/default/Scripts/python.exe"
  "$PY" extract_copy_brief.py <design_file_or_text> -o brief.json --text
"""

import json
import re
import sys
import os


def unescape_json(text):
    """Unescape JSON-encoded string if needed (Feishu stores text as JSON string)."""
    try:
        decoded = json.loads(text)
        if isinstance(decoded, str):
            return decoded
    except (json.JSONDecodeError, TypeError):
        pass
    return text


def parse_design_for_copy(text):
    """Parse v5.3 design plan text → list of per-platform copywriting briefs.

    Robust to both v5.3 sub-formats observed in real model output:
      Variant 1: 方案 N: ... / 【方向B】 / 【Amazon_VisualBridge】 / <EN prompt> / 视觉语义标签 ...
      Variant 2: 方案 N: ... / 【方向B】 / 原始设计指令: <EN prompt> / 视觉语义标签 ...
    """

    text = unescape_json(text)
    lines = text.split('\n')
    n = len(lines)

    # Split into per-方案 sections by their platform headers.
    boundaries = []
    for idx, line in enumerate(lines):
        if re.match(r'方案\s*\d+\s*:\s*(Amazon|eBay|Etsy)\s*渠道', line, re.IGNORECASE):
            boundaries.append(idx)
    boundaries.append(n)  # sentinel

    platforms = []
    for b_i, start in enumerate(boundaries[:-1]):
        end = boundaries[b_i + 1]
        blk = _parse_one_section(lines[start:end])
        if blk:
            platforms.append(blk)
    return platforms


_META_HEADERS = ('视觉语义标签', '核心视觉卖点', '文案转化指引')


def _parse_one_section(section):
    """Parse a single 方案 section (list of lines) into a brief dict."""
    if not section:
        return None
    m = re.match(r'方案\s*(\d+)\s*:\s*(Amazon|eBay|Etsy)', section[0].strip(), re.IGNORECASE)
    if not m:
        return None
    blk = {
        'index':           int(m.group(1)),
        'platform':        m.group(2).capitalize(),
        'direction':       None,
        'prompt':          '',
        'visual_tags':     [],
        'selling_points':  [],
        'copy_guide':      {'emphasize': [], 'avoid': [], 'template': ''},
        'direction_name':  '',
    }
    for bl in section:
        dm = re.match(r'【(方向\w)\s*[·•]\s*(.+)】', bl.strip())
        if dm:
            blk['direction'] = dm.group(1)
            blk['direction_name'] = dm.group(2)
            break
    blk['prompt'] = _extract_prompt(section)
    blk['visual_tags'] = _extract_tags(section)
    blk['selling_points'] = _extract_points(section)
    blk['copy_guide'] = _extract_guide(section)
    return blk


def _extract_prompt(section):
    """Collect the pure-English image prompt: after 【Xxx_VisualBridge】 or
    原始设计指令:, stopping at the first metadata header / trailing blank.
    Robust to the blank-line-then-原始设计指令 variant and to a redundant
    '<Platform>_VisualBridge:' echo the model sometimes re-emits inside the value.
    """
    parts = []
    started = False
    for bl in section:
        bs = bl.strip()
        if not bs:
            # Only break on blank once we've actually collected prompt text.
            if started and parts:
                break
            continue
        if any(h in bs for h in _META_HEADERS):
            break
        if '原始设计指令' in bs:
            after = bs.split('原始设计指令', 1)[1]
            after = re.split(r'[:：]', after, 1)[-1].strip()
            # strip a redundant "<Platform>_VisualBridge:" echo, if present
            after = re.sub(r'^\s*[A-Za-z]*_VisualBridge\s*:\s*', '', after).strip()
            if after:
                parts.append(after)
            started = True
            continue
        if '_VisualBridge' in bs:
            started = True
            continue
        if started:
            parts.append(bs)
    return ' '.join(parts).strip()


def _extract_tags(section):
    """Parse visual semantic tags. Model output uses two variants (both seen in real data):
      #English #中文      (Chinese also prefixed)          — rarer
      #English 中文       (only English prefixed)          — dominant
    Tags are separated by '|' and may span multiple lines after the 视觉语义标签 header.
    The Chinese part is captured even when it has no leading '#'.
    """
    in_block = False
    raw = []
    for bl in section:
        bs = bl.strip()
        if '视觉语义标签' in bs:
            in_block = True
            rest = re.sub(r'^.*视觉语义标签.*?[:：]?\s*', '', bs).strip()
            if rest:
                raw.append(rest)
            continue
        if in_block:
            if any(h in bs for h in ('核心视觉卖点', '文案转化指引')):
                break
            if not bs:
                if raw:
                    break
                continue
            raw.append(bs)
    joined = ' '.join(raw)
    tags = []
    for seg in joined.split('|'):
        seg = seg.strip()
        if not seg:
            continue
        # #English (lazy) + whitespace + optional '#' + CJK text to end
        m = re.match(r'#\s*(.+?)\s+#?\s*([\u4e00-\u9fff].*)$', seg)
        if m:
            tags.append({'en': m.group(1).strip(), 'zh': m.group(2).strip()})
    return tags


def _extract_points(section):
    """Parse 核心视觉卖点 lines into feature/benefit (numbered or 'x + y')."""
    in_block = False
    points = []
    for bl in section:
        bs = bl.strip()
        if '核心视觉卖点' in bs:
            in_block = True
            continue
        if in_block:
            if any(h in bs for h in ('视觉语义标签', '文案转化指引')):
                break
            if not bs:
                if points:
                    break
                continue
            content = re.sub(r'^\d+\.\s*', '', bs)
            if '+' in content:
                f, b = content.split('+', 1)
                points.append({'feature': f.strip(), 'benefit': b.strip()})
            else:
                points.append({'feature': content, 'benefit': ''})
    return points


def _extract_guide(section):
    """Parse 文案转化指引: 强调 / 避免 / 推荐句式 (with or without leading '- ')."""
    guide = {'emphasize': [], 'avoid': [], 'template': ''}
    in_block = False
    for bl in section:
        bs = bl.strip()
        if '文案转化指引' in bs:
            in_block = True
            continue
        if in_block:
            if any(h in bs for h in ('视觉语义标签', '核心视觉卖点')):
                break
            if not bs:
                if guide['emphasize'] or guide['avoid'] or guide['template']:
                    break
                continue
            if re.match(r'-?\s*强调\s*[:：]', bs):
                guide['emphasize'] = _extract_quoted_words(bs)
            elif re.match(r'-?\s*避免\s*[:：]', bs):
                guide['avoid'] = _extract_quoted_words(bs)
            elif re.match(r'-?\s*推荐句式\s*[:：]', bs):
                tmpl = re.sub(r'^-?\s*推荐句式\s*[:：]\s*', '', bs).strip().strip('"')
                guide['template'] = tmpl
    return guide


def _extract_quoted_words(line):
    """Extract double-quoted words from a line."""
    return re.findall(r'"([^"]+)"', line)


# ── Output formatters ──

def format_text_brief(platforms):
    """Render human-readable copywriting brief."""
    out = []
    out.append("=" * 60)
    out.append("Listing 文案基材提取结果")
    out.append("=" * 60)
    out.append("")

    for p in platforms:
        plat = p.get('platform', '?')
        direction = p.get('direction', '?')
        out.append(f"▼ {plat} 渠道 | {direction}")
        out.append("")

        if p.get('visual_tags'):
            out.append("  【视觉语义标签】")
            for t in p['visual_tags']:
                out.append(f"    #{t['en']} #{t['zh']}")
            out.append("")

        if p.get('selling_points'):
            out.append("  【核心视觉卖点】")
            for sp in p['selling_points']:
                benefit = f" → {sp['benefit']}" if sp['benefit'] else ""
                out.append(f"    {sp['feature']}{benefit}")
            out.append("")

        cg = p.get('copy_guide', {})
        if cg.get('emphasize') or cg.get('avoid') or cg.get('template'):
            out.append("  【文案转化指引】")
            if cg.get('emphasize'):
                out.append(f"    强调: {', '.join(cg['emphasize'])}")
            if cg.get('avoid'):
                out.append(f"    避免: {', '.join(cg['avoid'])}")
            if cg.get('template'):
                out.append(f'    句式: "{cg["template"]}"')
            out.append("")

        out.append("-" * 40)
        out.append("")

    out.append(f"共 {len(platforms)} 个平台 | 可合并商品基础信息一起发给文案模型")
    return '\n'.join(out)


def main():
    if len(sys.argv) < 2:
        print("Usage: extract_copy_brief.py <design_file> [-o output.json] [--text]", file=sys.stderr)
        print("  从 v5.3 设计方案提取文案创作基材", file=sys.stderr)
        print("  -o <path>  输出 JSON", file=sys.stderr)
        print("  --text     同时打印可读文本（默认若未指定 -o 则打印）", file=sys.stderr)
        sys.exit(1)

    input_arg = sys.argv[1]
    out_json = None
    out_text = False

    args = sys.argv[2:]
    j = 0
    while j < len(args):
        if args[j] == '-o' and j + 1 < len(args):
            out_json = args[j + 1]
            j += 2
        elif args[j] == '--text':
            out_text = True
            j += 1
        else:
            j += 1

    # Read input
    try:
        with open(input_arg, 'r', encoding='utf-8') as f:
            raw = f.read()
    except (FileNotFoundError, OSError):
        raw = input_arg

    platforms = parse_design_for_copy(raw)

    if out_json:
        with open(out_json, 'w', encoding='utf-8') as f:
            json.dump(platforms, f, ensure_ascii=False, indent=2)
        print(f"Wrote {len(platforms)} platform blocks → {out_json}")

    if out_text or not out_json:
        print(format_text_brief(platforms))


if __name__ == '__main__':
    main()
