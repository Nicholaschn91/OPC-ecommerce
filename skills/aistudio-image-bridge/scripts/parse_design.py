#!/usr/bin/env python3
"""Parse 设计方案 field text -> list of individual image generation prompts.

Supports TWO producer formats:

  * v5.4 (current, qianwen-design-plan LOCKED v5.4 "纯净输出协议"):
      Option 1: Amazon Exclusive Design - Direction B · Fixed Print Pattern Design
      【Amazon_VisualBridge】
      Prompt:
      Amazon_VisualBridge: A minimalist flat 2D vector design featuring ..., isolated on a solid white background, print-ready flat 2D graphic asset. --ar 1:1 --tile --style raw
      Semantic Tags:
      #Geometric Diamond Pattern | ...
      Core Visual Selling Points:
      ...
      Copywriting Directives:
      ...
    Markers are English: "Option N:", "<Platform>_VisualBridge:" inline prompt
    prefix, English metadata headers (Semantic Tags / Core Visual Selling Points
    / Copywriting Directives).

  * v5.3 (legacy):
      方案 1: Amazon 渠道专属视觉
      【方向B · 固定印花图案设计方案】
      【Amazon_VisualBridge】
      A minimalist geometric seamless repeating pattern ... --ar 1:1 --tile --style raw
      视觉语义标签（中英双语）: ...
      核心视觉卖点: ...
      文案转化指引: ...

The pure-English prompt always precedes the metadata block. We stop collecting
the prompt at the first metadata header (English v5.4 or Chinese v5.3) or any
【...】 marker / blank line boundary.
"""

import re
import sys
import json

# Metadata headers that END a prompt (English v5.4 + Chinese v5.3)
_META_HEADERS_EN = ('Semantic Tags', 'Core Visual Selling Points', 'Copywriting Directives')
_META_HEADERS_ZH = ('视觉语义标签', '核心视觉卖点', '文案转化指引')
_META_HEADERS = _META_HEADERS_EN + _META_HEADERS_ZH

# Option / 方案 marker: "Option 1:" or "方案 1:" — matched ANYWHERE, because real
# v5.4 outputs cram multiple options (and the Chinese+English double announcement
# "方案 1: ...Option 1:") onto a single physical line.
_OPTION_RE = re.compile(r'(?:Option|方案)\s*(\d+)\s*[:：]', re.IGNORECASE)
# Explicit prompt-start prefixes
_PROMPT_START_RE = re.compile(
    r'(?:Prompt\s*[:：]|(?:Amazon|Etsy|eBay)_VisualBridge(?:_Display)?\s*[:：])', re.IGNORECASE)
# 【X_VisualBridge】 marker (v5.3 / some v5.4 variants): prompt follows the marker
_VB_MARKER_RE = re.compile(r'【(?:Amazon|Etsy|eBay)_VisualBridge(?:_Display)?】', re.IGNORECASE)
# Anything that ENDS a prompt: a metadata header or any 【...】 marker
_PROMPT_END_RE = re.compile(
    r'(?:Semantic Tags|Core Visual Selling Points|Copywriting Directives'
    r'|视觉语义标签|核心视觉卖点|文案转化指引|【)', re.IGNORECASE)
# Inline VisualBridge marker (carries platform + optional inline prompt)
_VB_RE = re.compile(r'(Amazon|Etsy|eBay)_VisualBridge(?:_Display)?', re.IGNORECASE)
# Direction (A/B) extractor
_DIR_RE = re.compile(r'Direction\s*([AB])|方向\s*([AB])', re.IGNORECASE)


def _has_cjk(s):
    return any('\u4e00' <= ch <= '\u9fff' for ch in s)


def _platform_from_token(s):
    low = (s or '').lower()
    if 'amazon' in low:
        return 'Amazon'
    if 'etsy' in low:
        return 'Etsy'
    if 'ebay' in low:
        return 'eBay'
    return None


def _is_meta_header(line):
    s = line.strip()
    return any(s.startswith(h) for h in _META_HEADERS)


def _is_prompt_label(line):
    """A standalone 'Prompt:' label line (no real content) -> skip it."""
    s = line.strip().rstrip(':').strip().lower()
    return s == 'prompt'


def _clean_prompt_line(line):
    """Strip leading VB / bare "Prompt:" / legacy 原始设计指令 prefixes.

    Order-independent: a line like "Prompt: Amazon_VisualBridge: <prompt>" must have
    BOTH prefixes removed, so we loop until no known prefix remains."""
    s = line.strip()
    while True:
        m = re.match(r'^(?:Amazon|Etsy|eBay)_VisualBridge(?:_Display)?\s*[:：]\s*', s, re.IGNORECASE)
        if m:
            s = s[m.end():].strip()
            continue
        m = re.match(r'^Prompt\s*[:：]\s*', s, re.IGNORECASE)
        if m:
            s = s[m.end():].strip()
            continue
        m = re.match(r'^原始设计指令\s*[:：]\s*', s)
        if m:
            s = s[m.end():].strip()
            continue
        break
    return s


def _extract_prompt(after):
    """Extract the cleaned prompt from an option's segment (text after 'Option N:').

    Handles three real-world shapes observed in actual qianwen-design-plan output:
      1. Explicit prefix:  "Prompt: Amazon_VisualBridge: <prompt>" / "Amazon_VisualBridge: <prompt>"
      2. Marker-then-bare: "【Amazon_VisualBridge】\\n<prompt>"
      3. Bare line:        first line that is not a 【】 marker, metadata header, or platform token
    The prompt runs until the first metadata header or 【...】 marker.
    """
    # Case 1: explicit "Prompt:" / "<Plat>_VisualBridge:" prefix
    pm = _PROMPT_START_RE.search(after)
    if pm:
        start = pm.end()
    else:
        # Case 2: 【X_VisualBridge】 marker, prompt follows on the next text
        mm = _VB_MARKER_RE.search(after)
        if mm:
            start = mm.end()
        else:
            # Case 3: bare prompt = first plausible line
            start = None
            for ln in after.split('\n'):
                s = ln.strip()
                if not s or s.startswith('【') or _is_meta_header(s):
                    continue
                if _platform_from_token(s):
                    continue  # header line (carries a platform token), not the prompt
                start = after.find(s)
                break
            if start is None:
                return ''
    rest = after[start:]
    me = _PROMPT_END_RE.search(rest)
    if me:
        rest = rest[:me.start()]
    return _clean_prompt_line(rest)


def _split_blocks(text):
    """Split raw text into option blocks. Each block = {header, prompt_head, lines[]}.

    Every 'Option N:' / '方案 N:' start (ANYWHERE in the text) becomes its own block,
    so a single physical line cramming several options still yields one block per option.
    Duplicate announcements of the SAME number on one line (e.g. '方案 1: ...Option 1:')
    are collapsed to a single block.
    """
    raw = list(_OPTION_RE.finditer(text))
    kept = []
    for m in raw:
        num = m.group(1)
        if (kept and kept[-1].group(1) == num
                and not _PROMPT_START_RE.search(text[kept[-1].end():m.start()])):
            continue  # same option announced twice (中文 + English) on one line
        kept.append(m)

    blocks = []
    for i, m in enumerate(kept):
        seg_end = kept[i + 1].start() if i + 1 < len(kept) else len(text)
        after = text[m.end():seg_end]
        prompt = _extract_prompt(after)
        blocks.append({'header': after.strip(), 'prompt_head': prompt, 'lines': []})
    return blocks


def parse_design_text(text):
    """Parse design-plan text into individual prompts.

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

    prompts = []
    for blk in _split_blocks(text):
        header = blk['header'] or ''
        body = blk['lines']

        # --- platform ---
        platform = _platform_from_token(header)
        if not platform:
            for ln in body:
                pm = _VB_RE.search(ln)
                if pm:
                    platform = _platform_from_token(pm.group(1))
                    break
        if not platform:
            for ln in [header] + body:
                m = _OPTION_RE.match(ln.strip())
                if m and _platform_from_token(m.group(2)):
                    platform = _platform_from_token(m.group(2))
                    break
        if not platform:
            continue

        # --- direction (A/B) ---
        direction = None
        dm = _DIR_RE.search(header)
        if dm:
            direction = dm.group(1) or dm.group(2)
        if not direction:
            for ln in body:
                if '方向A' in ln or re.search(r'Direction\s*A', ln, re.IGNORECASE):
                    direction = 'A'
                    break
                if '方向B' in ln or re.search(r'Direction\s*B', ln, re.IGNORECASE):
                    direction = 'B'
                    break
        if not direction:
            direction = 'B'  # default: most plans are 方向B

        # --- prompt body (already extracted + cleaned by _split_blocks) ---
        pt = ' '.join(blk.get('prompt_head', '').split())

        if not (pt and len(pt) >= 30 and pt[0].isascii() and pt[0].isalpha()):
            continue

        if platform == 'Etsy':
            idx = len([p for p in prompts
                       if p['direction'] == direction and p['platform'] == 'Etsy']) + 1
        else:
            idx = 1
        label = f"Dir{direction}_{platform}_{idx}"
        short = f"{direction}-{platform[:3]}-{idx}"
        prompts.append({
            'direction': direction,
            'platform': platform,
            'index': idx,
            'prompt_text': pt,
            'label': label,
            'short_label': short,
        })

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
