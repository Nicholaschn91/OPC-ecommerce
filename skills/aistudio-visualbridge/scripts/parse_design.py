#!/usr/bin/env python3
"""Parse 设计方案 field text → list of individual image generation prompts.

Supports the v5.3 POD design-plan output, which has two observed sub-formats
inside a 【方向B · ...】 block, each 方案 N section carrying one platform prompt:

  Variant 1 (VisualBridge marker):
    方案 1: Amazon 渠道专属视觉
    【方向B · 固定印花图案设计方案】
    【Amazon_VisualBridge】
    A minimalist geometric seamless repeating pattern ... --ar 1:1 --tile --style raw
    视觉语义标签（中英双语）: ...
    核心视觉卖点: ...
    文案转化指引: ...

  Variant 2 (原始设计指令 prefix):
    方案 1: Amazon 渠道专属视觉
    【方向B · 固定印花图案设计方案】
    原始设计指令: A minimalist flat 2D vector design ... --ar 4:3 --style raw
    视觉语义标签（中英双语）: ...
    (or: 原始设计指令: \\n Amazon_VisualBridge: \\n <english prompt>)

The pure-English prompt ALWAYS precedes the Chinese metadata blocks
(视觉语义标签 / 核心视觉卖点 / 文案转化指引). We stop collecting the prompt at
the first metadata header or any CJK line, so metadata is never swallowed.
"""

import re
import sys
import json


_METADATA_HEADERS = ('视觉语义标签', '核心视觉卖点', '文案转化指引')
_SCHEME_RE = re.compile(r'方案\s*\d+\s*[:：]\s*(\w+)')
_VB_RE = re.compile(r'(Amazon|Etsy|eBay)_VisualBridge', re.IGNORECASE)


def _has_cjk(s):
    return any('\u4e00' <= ch <= '\u9fff' for ch in s)


def _platform_from_token(s):
    low = s.lower()
    if 'amazon' in low:
        return 'Amazon'
    if 'etsy' in low:
        return 'Etsy'
    if 'ebay' in low:
        return 'eBay'
    return None


def _is_metadata(line):
    if any(h in line for h in _METADATA_HEADERS):
        return True
    # Metadata lines are Chinese; the prompt is pure English/ASCII.
    return _has_cjk(line)


def parse_design_text(text):
    """Parse VisualBridge design text into individual prompts.

    Returns list of dicts:
      {direction, platform, index, prompt_text, label, short_label}
    """
    # Unescape JSON string if needed
    try:
        decoded = json.loads(text)
        if isinstance(decoded, str):
            text = decoded
    except (json.JSONDecodeError, TypeError):
        pass

    lines = text.split('\n')
    n = len(lines)
    prompts = []
    current_direction = None

    def flush(platform, buf):
        pt = ' '.join(buf).strip()
        if not (pt and len(pt) >= 30 and pt[0].isascii() and pt[0].isalpha()):
            return
        direction = current_direction or 'B'  # v5.3 plans are all 方向B
        if platform == 'Etsy':
            idx = len([p for p in prompts
                       if p['direction'] == direction and p['platform'] == 'Etsy']) + 1
        else:
            idx = 1
        label = f"Dir{direction}_{platform}_{idx}"
        short = f"{direction}-{platform[:3]}-{idx}"
        prompts.append({
            'direction': current_direction,
            'platform': platform,
            'index': idx,
            'prompt_text': pt,
            'label': label,
            'short_label': short,
        })

    last_scheme_platform = None
    i = 0
    while i < n:
        line = lines[i].strip()
        i += 1
        if not line:
            continue

        # direction markers (global)
        if '方向A' in line:
            current_direction = 'A'
            continue
        if '方向B' in line:
            current_direction = 'B'
            continue

        # Platform can come from a 方案 N: <Platform> header ...
        m = _SCHEME_RE.search(line)
        platform = _platform_from_token(m.group(1)) if m else None
        # ... or from an inline VisualBridge marker on this line
        if not platform:
            mvb = _VB_RE.search(line)
            if mvb:
                platform = _platform_from_token(mvb.group(1))
        # ... or fall back to the current 方案 context for a bare 原始设计指令 line
        if not platform and '原始设计指令' in line:
            platform = last_scheme_platform
        if m:
            last_scheme_platform = platform

        if not platform:
            continue

        # Collect the English prompt. Marker lines that PRECEDE the prompt
        # (【方向B】, 【Xxx_VisualBridge】, 原始设计指令:) are skipped, not
        # treated as the prompt end. A blank line may sit between the
        # 【Xxx_VisualBridge】 marker and 原始设计指令:, and the 原始设计指令:
        # line itself may carry the FIRST prompt line inline — capture it here
        # so the lead-in sentence is never dropped.
        buf = []
        if '原始设计指令' in line:
            after = line.split('原始设计指令', 1)[1]
            after = re.split(r'[:：]', after, 1)[-1].strip()
            after = re.sub(r'^\s*[A-Za-z]*_VisualBridge\s*:\s*', '', after).strip()
            if after:
                buf.append(after)
        j = i
        while j < n:
            nl = lines[j].strip()
            if not nl:
                break  # blank line ends the prompt region
            if _SCHEME_RE.search(nl):
                break  # new 方案 section
            if any(h in nl for h in _METADATA_HEADERS):
                break  # metadata header ends the prompt
            if '_VisualBridge' in nl:
                j += 1  # skip marker, prompt may follow
                continue
            if '原始设计指令' in nl:
                after = nl.split('原始设计指令', 1)[1]
                after = re.split(r'[:：]', after, 1)[-1].strip()
                after = re.sub(r'^\s*[A-Za-z]*_VisualBridge\s*:\s*', '', after).strip()
                if after:
                    buf.append(after)
                j += 1
                continue
            if '方向A' in nl or '方向B' in nl:
                current_direction = 'A' if '方向A' in nl else 'B'
                j += 1  # skip direction marker that precedes the prompt
                continue
            # NOTE: do NOT break on arbitrary CJK here — the model sometimes
            # leaks a stray Chinese char inside an otherwise-English prompt
            # (e.g. "with硬朗 edges"). Only the metadata *headers* end the prompt.
            buf.append(nl)
            j += 1
        i = j  # resume scanning after the prompt region

        flush(platform, buf)

    return prompts


def main():
    if len(sys.argv) < 2:
        print("Usage: python parse_design.py <design_file_or_text> [--json]", file=sys.stderr)
        sys.exit(1)

    input_arg = sys.argv[1]
    as_json = '--json' in sys.argv

    # Try reading as file first, fallback to raw text
    try:
        with open(input_arg, 'r', encoding='utf-8') as f:
            text = f.read()
    except (FileNotFoundError, OSError):
        text = input_arg

    prompts = parse_design_text(text)

    if as_json:
        print(json.dumps(prompts, ensure_ascii=False, indent=2))
    else:
        print(f"Total prompts: {len(prompts)}")
        for i, p in enumerate(prompts):
            short = p['prompt_text'][:100] + ('...' if len(p['prompt_text']) > 100 else '')
            print(f"  [{i+1}] {p['label']:20s} | {short}")


if __name__ == '__main__':
    main()
