#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean-capture.py — 把「Blob 下载捕获的原始 md」清洗为可交付版本。

原始捕获（经 browser-qwen MCP 的 download 事件落盘）含：
  顶部页面 chrome + 深度思考块 + 正式输出 + 底部输入框 chrome。

清洗规则（2026-08-15 修订 · 兼容线一/线二输出）：
  - 去除深度思考块：起点取 START 候选的【最后】一次出现，思考块里复述的标记位置更早，
    会被自动跳过（旧版 find_first 误抓思考块标记，把思考垃圾带进交付物）；
  - 候选标记不依赖单一固定标题（线一 "Etsy Listing 终版优化" / 线二 "原始素材摘要" 等）；
  - 截到输入栏标记前（候选："你好，我是千问" 等；无命中则保留到文末，确保 BASE_MATERIAL 不被误切）；
  - 删除孤立的工具栏行（表格 / 复制 / 编辑 等）。

用法：
  python clean-capture.py --in S3-02-qianwen-com-out.md --out S3-02-qianwen-com-out-clean.md
  # 可选额外标记（追加进候选，不覆盖默认候选）：
  #   --start "自定义起始标题"   --end "自定义结束标记"
"""
import argparse


# 候选标记（按出现优先级；find_first 取最早命中者）
# 注意：BASE_MATERIAL 仅作结尾结构化块、绝不进起始候选——模型常在开头复述规则短语
# "BASE_MATERIAL block." 导致起点过早过切。
START_CANDIDATES = [
    'Etsy Listing 终版优化',     # 线一（可能带 🚀 / 输出 等前后缀）
    '原始素材摘要',              # 线二正式回答首行（也可能带 📋 前缀）
    '📋 原始素材摘要',
    '🚀 Etsy Listing 终版优化输出',
]
END_CANDIDATES = [
    '你好，我是千问',
    '满意就来和我聊天吧',
    '给我发消息',
    '发送消息',
]
# 孤立工具栏/UI 行（千问渲染出的非内容行）
SKIP_LINES = {
    '表格', '下载为表格', '导出为图片', '文本', '编辑', '代码', '复制',
    '深挖', '重新生成', '导出', '分享',
    # 代码块语言标签（千问把 ```json 渲染成独立 "json" / "python" 行）
    'json', 'python', 'markdown',
}


def _is_gutter(line):
    """代码块行号槽：整行就是纯数字（如 "1" / "12"）。"""
    s = line.strip()
    return s.isdigit()


def find_first(text, candidates):
    """返回候选标记中最早出现的位置；均未命中返回 -1。"""
    best = -1
    for c in candidates:
        p = text.find(c)
        if p != -1 and (best == -1 or p < best):
            best = p
    return best


def find_last(text, candidates):
    """返回候选标记中【最后】出现的位置；均未命中返回 -1。

    用于定位真实回答起点：思考块里若复述了 START 标记（如
    "📋 原始素材摘要 (mandatory)"），其位置一定早于正式回答，
    取最后出现即可整段跳过思考块，无需单独切思考标记行。
    """
    best = -1
    for c in candidates:
        p = text.rfind(c)
        if p != -1 and (best == -1 or p > best):
            best = p
    return best


# 确定性锚记对（2026-08-15 强化版）：提示词注入的包裹边界。
# 按优先级顺序尝试：第一对命中即采用；均未命中则交由候选探测兜底。
# 新锚记更显眼（3 个 `#` + 大写 BEGIN/END），置于提示词顶部，模型更易遵循；
# 旧锚记保留为向后兼容（历史 raw 捕获可能含之）。
ANCHOR_PAIRS = [
    ('###QWEN_OPT_BEGIN###', '###QWEN_OPT_END###'),   # 2026-08-15 强化版（当前默认）
    ('<<<QWEN_OPT_START>>>', '<<<QWEN_OPT_END>>>'),   # 历史版本（向后兼容）
]


def strip_echo_markers(text, open_m, close_m, max_gap=500):
    """整段删除「inline echo」成对锚记，保留文件首尾的真实包裹对。

    **踩坑实录（2026-08-15 犬类大 listing 跑通后）**：Qwen3.8-Max 在「执行检查清单」节里
    会复述锚记完整性，形如：
        "锚记完整性：首行 ###QWEN_OPT_BEGIN###，末行 ###QWEN_OPT_END### ..."
    两个 marker 在**同一行内**距离极近，且 echo 中间文本本身也含 marker 字面
    ("...首行 ###QWEN_OPT_BEGIN### 末行 ###QWEN_OPT_END###...")——若只剥 marker 而保留
    中间文本，extract_by_anchor 的 rfind/find 仍会命中 echo 中间残留的 literal，
    抓错成对、提取为空。

    **算法**：栈深度配对 + inline 判定 + 整段删除。
      1) 收集所有 marker 位置；
      2) 按位置栈配对（begin 入栈，end 出栈配对栈顶 begin）；
      3) 配对 span < max_gap **且**两个 marker 间无换行 → 视为 inline echo；
      4) **整段删除** echo 区域（begin marker + 中间文本 + end marker），不留 marker 字面残留，
         后续 extract_by_anchor 干净提取外层真实包裹对。

    Args:
        text: 含 anchor marker 的全文
        open_m: BEGIN 标记
        close_m: END 标记
        max_gap: 视为 inline echo 的最大 span（默认 500 字符）

    Returns:
        (剥除 echo 区段后的文本, 剥除的 echo 对数)
    """
    # 找所有 marker 位置（一次扫描，按位置排序：先出现的先入栈，无论是 B 还是 E）
    spans = []  # (pos, kind)
    i = 0
    while True:
        b = text.find(open_m, i)
        e = text.find(close_m, i)
        if b < 0 and e < 0:
            break
        if e < 0 or (b >= 0 and b < e):
            spans.append((b, 'B'))
            i = b + len(open_m)
        else:
            spans.append((e, 'E'))
            i = e + len(close_m)

    # 栈配对（同一位置可能既有 begin 也有 end？用反序 + 栈正确处理）
    stack = []
    pairs = []  # (begin_pos, end_pos_end_exclusive)
    for pos, kind in spans:
        if kind == 'B':
            stack.append((pos,))
        else:
            if stack:
                bpos = stack.pop()[0]
                pairs.append((bpos, pos + len(close_m)))  # end_exclusive

    # 仅削 inline echo（无换行 + span<max_gap）。倒序剥以保索引稳定。
    echos = []
    for bpos, epos_excl in pairs:
        between = text[bpos + len(open_m):epos_excl - len(close_m)]
        span = epos_excl - len(close_m) - bpos
        if '\n' not in between and span < max_gap:
            echos.append((bpos, epos_excl))
    echos.sort(key=lambda x: x[0], reverse=True)

    out = text
    for bpos, epos_excl in echos:
        # 整段删除 echo 区
        out = out[:bpos] + out[epos_excl:]
    return out, len(echos)


def extract_by_anchor(text):
    """主路径：用提示词注入的确定性锚记截取终版正文。

    按 ANCHOR_PAIRS 优先级逐对尝试：
      1) 先剥「同段紧邻 echo 对」（见 strip_echo_markers），消除 Qwen 在清单节里复述
         锚记造成的嵌套干扰（2026-08-15 犬类 listing 踩坑）；
      2) 起点取 rfind（提示词示例里的旧对更靠前，必须跳过；模型真正包裹回答的那对
         在更后位置）；
      3) 终点取该起点之后的 find。

    起止对均命中则返回两者之间的内容；任一未命中则继续尝试下一对；
    所有对均未命中则返回 (None, 0)，交由候选探测兜底（兼容历史无锚记产物）。
    即便被模型包进代码围栏，字面匹配仍成立（rfind 仍能找到）。

    Returns:
        (body 文本, anchor 是否命中 [True/None], 本次剥除的 echo 对数)
    """
    for start_marker, end_marker in ANCHOR_PAIRS:
        cleaned, echo_cnt = strip_echo_markers(text, start_marker, end_marker)
        s = cleaned.rfind(start_marker)
        if s == -1:
            continue
        e = cleaned.find(end_marker, s + len(start_marker))
        if e == -1:
            continue
        return cleaned[s + len(start_marker):e], True, echo_cnt
    return None, False, 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', required=True, help='Blob 下载的原始捕获 md')
    ap.add_argument('--out', required=True, help='清洗后交付 md')
    ap.add_argument('--start', default=None, help='额外起始标题（追加进 START 候选，仅锚记缺失时生效）')
    ap.add_argument('--end', default=None, help='额外结束标记（追加进 END 候选，仅锚记缺失时生效）')
    args = ap.parse_args()

    t = open(args.inp, encoding='utf-8').read()

    # 主路径：确定性锚记（提示词已注入，2026-08-15 新增）。
    # 命中即作为唯一边界，彻底规避思考块污染 / BASE_MATERIAL 误起点 / find 歧义。
    # 自动跳过 Qwen 在清单节里复述的 echo 对（仅剥间距 < 80 的成对 marker）。
    anchored_body, anchored_ok, echo_stripped = extract_by_anchor(t)
    if anchored_ok:
        body = anchored_body
    else:
        # 兜底：历史无锚记产物（100337/100324/100330 等），走候选探测。
        # 真实回答起点：取 START 候选的【最后】一次出现，自动跳过思考块。
        starts = list(START_CANDIDATES)
        if args.start:
            starts = [args.start] + starts
        si = find_last(t, starts)
        if si == -1:
            ti = find_first(t, ['深度思考已完成', '思考过程', 'Thinking'])
            if ti != -1:
                nl = t.find('\n', ti)
                t = t[nl + 1:] if nl != -1 else t[ti + len('深度思考已完成'):]
            body = t
        else:
            body = t[si:]
        # 去底部输入栏 chrome
        ends = list(END_CANDIDATES)
        if args.end:
            ends = [args.end] + ends
        ei = find_first(body, ends)
        if ei != -1:
            body = body[:ei].rstrip() + '\n'

    # 去孤立工具栏行 + 代码块行号槽
    lines = [ln for ln in body.split('\n')
             if ln.strip() not in SKIP_LINES and not _is_gutter(ln)]
    clean = '\n'.join(lines).strip() + '\n'
    open(args.out, 'w', encoding='utf-8').write(clean)
    tag = f"[anchor, echo-stripped={echo_stripped}]" if anchored_ok else "[fallback: no anchor]"
    print(f"wrote {args.out}: {len(clean)} chars  {tag}")


if __name__ == '__main__':
    main()
