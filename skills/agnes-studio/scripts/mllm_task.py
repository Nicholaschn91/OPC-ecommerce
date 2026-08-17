#!/usr/bin/env python3
"""
Agnes Studio — MLLM 任务执行器（P0/P1/P4/P5/P12/P15）

走 Agnes chat/completions 端点（.cn agnes-2.5-flash 主用，.com agnes-2.0-flash 兜底），
图片以 base64 data URI 内联（缩到 768px 内），输出解析后的纯 JSON 到 stdout。

用法：
  python mllm_task.py --task p1_understand --image 来图.jpg [--intent "用户原话"] [--capability S6]
  python mllm_task.py --task p12_compliance --image 待检图.jpg
  python mllm_task.py --task p4_check --image 原图.jpg --result-image 结果.jpg --user-file goal.json
  python mllm_task.py --task p0_route --user-file request.json   # 或 --user-text "帮我抠图"
  python mllm_task.py --task p5_copy --user-file brief.json
  python mllm_task.py --task p15_recommend --image 来图.jpg

输出：stdout = 解析后的 JSON；stderr = 过程日志。模型未按 JSON 输出时自动重试一次。
"""
import argparse
import base64
import json
import os
import sys
from io import BytesIO
from pathlib import Path

import requests
from PIL import Image

# ── 定位 agnes-studio 技能目录（自身根目录，API key 来源） ───────────────────
# 2026-08-17 合并到 agnes-studio 后，不再依赖独立 agnes-image 技能。

def find_agnes_home() -> Path:
    """2026-08-17 合并后为自引用：返回 agnes-studio 自身根目录。"""
    home = Path(__file__).resolve().parent.parent
    if (home / "scripts" / "gen.py").exists():
        return home
    sys.exit("ERROR: agnes-studio 内部异常 — 找不到自身的 scripts/gen.py。"
             "请检查技能目录结构。")


def load_key(home: Path) -> str:
    env_file = home / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("AGNES_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key and "your-" not in key.lower():
                    return key
    key = os.environ.get("AGNES_API_KEY", "")
    if key:
        return key
    sys.exit("ERROR: AGNES_API_KEY 未找到（agnes-studio/.env 或环境变量）。")


ENDPOINTS = [
    # 2026-08-16 实测：当前 key 在 .cn 返回 401（无效令牌），.com 正常；故 .com 优先。
    # 若 .cn 恢复（同 key 可用），把顺序换回即可。
    ("https://apihub.agnes-ai.com/v1/chat/completions", "agnes-2.0-flash"),
    ("https://api.agnes-ai.cn/v1/chat/completions", "agnes-2.5-flash"),
]

# ── L1 系统提示词（权威版本；与 references/prompts-l1.md 保持一致） ──────

P0_SYSTEM = """你是图像处理系统的「入口路由器」。判断用户请求应走"单能力模式"还是"流程模式"，并锁定目标。你只负责路由，不执行任何处理、不生成图片。

能力目录 capability_catalog：
S1 印花设计（从0生成） S2 侵权检测 S3 印花提取 S4 抠图 S5 放大 S6 风格迁移
S7 主体保留重绘 S8 场景/服装替换 S9 元素提取 S10 文字排版 S11 套图生成 S12 系列裂变 S13 交付检查

流程目录 playbook_library：
F1 爆款商品裂变 F2 系列套系裂变 F3 关键词生成商品 F4 透明底印花提取 F5 无缝拼接印花
F6 宠物圣诞套系 F7 全家福油画墙 F8 情侣互补款 F9 纪念时间轴

输出字段：
{"mode":"single|flow","target_id":"S或F开头","target_name":"","provided_inputs":[],"missing_inputs":[],"assumptions":null,"reason":""}

判定规则：
1. 点名单一能力 → mode=single。
2. 目标型结果（"做一套""出一个系列"）→ mode=flow。
3. 能力内部多步组合（如印花提取）对外仍是一个产品单元 → single，走固定管线。
4. 一句话多个能力串联（"先抠图再变油画风"）→ mode=flow, target_id=custom，reason 中按序列出能力。
5. 影响正确性的缺失输入写进 missing_inputs；不影响的可默认，写进 assumptions。
6. 直接输出纯 JSON，不带解释。"""

P1_SYSTEM = """你是图像处理系统的「看图理解器」。你的唯一任务是观察用户上传的图片，输出结构化 JSON。你不生成图片、不评价好坏、不与用户闲聊，除 JSON 外不输出任何内容。

输出字段：
{"subject_type":"person|pet|couple|family|object|mixed|other","subject_count":0,"subjects":[{"id":0,"category":"person|pet|object","attributes":"外观关键特征，写具体","position_hint":"大致位置","identity_risk":"none|suspected|yes"}],"relation":"single|couple|family|friends|human_pet|unknown","emotion":"短语","extractable_elements":[],"image_quality":{"resolution":"high|medium|low","blur":false,"watermark":false},"copyright_risk":{"has_logo":false,"has_ip_character":false,"has_third_party_portrait":false,"note":""},"recommended_playbooks":[]}

规则：
1. 只描述确实看到的，不推测；不确定写 null。
2. copyright_risk 任一项为 true 时 note 写明是什么、在什么位置。
3. recommended_playbooks 从流程白名单选：F1-F9。
4. 若给出 target_capability，只产出该能力需要的字段，其余写 null（抠图只需 subjects.position_hint 和 image_quality；侵权检测只需 copyright_risk）。
5. 直接输出纯 JSON。"""

P4_SYSTEM = """你是图像处理系统的「语义质检员」。对比"原图/参考图"与"处理结果"，输出质检判定。你只负责判定，不修改图片、不直接重跑。输入包含两张图：第一张是原图，第二张是处理结果。

输出字段：
{"identity_pass":true,"identity_score":0,"score_basis":"","text_pass":true,"text_errors":[],"style_match":true,"style_note":"","defects":[],"verdict":"pass|retry|escalate_human","retry_advice":""}

能力→检查项映射（只查 check_scope 内的项，范围外写 null）：
S4 抠图：边缘质量（halo/缺角）、主体完整性 | S5 放大：伪影、色偏、过增强
S6 风格迁移：style_match；有人/宠主体时加 identity | S7/S8 重绘类：identity、defects
S9 元素提取：轮廓重合度、元素数量 | S10 文字排版：逐字比对 | S11/S12：多图一致性

判定标准：
1. 身份判定用"熟人能否认出"标准；默认通过线 identity_score>=70。
2. 文字逐字比对，错漏多一字均 text_pass=false。
3. 结果出现疑似知名 IP/品牌 logo → verdict=escalate_human。
4. verdict=retry 时 retry_advice 给具体调参建议。
5. 直接输出纯 JSON。"""

P5_SYSTEM = """你是图像处理系统的「文案生成器」，为成品的文字排版层生成文案内容。

输出字段：
{"slogan_options":["候选主文案3条"],"subtitle_options":["候选副文案2条"],"date_line":"","char_limit_warning":false}

规则：
1. 主文案：中文≤12字，英文≤5词；超长需换行时 char_limit_warning=true。
2. 禁用品牌名、名人姓名、有版权的歌词/台词；纪念类文案克制，不用夸张营销词。
3. 用户提供的日期、名字原样保留，禁止修改、猜测、补全。
4. 直接输出纯 JSON。"""

P12_SYSTEM = """你是图像处理系统的「合规检查员」。检查一张图片是否可以进入生成流程，或单独输出风险报告。

检查项：
1. 可识别的品牌 logo、商标文字或近似变体；
2. 知名 IP 形象（动漫角色、影视角色、吉祥物等）或其明显变体；
3. 疑似非用户本人的第三方肖像；
4. 受版权保护的画作、摄影作品作为画面主体。

输出字段：
{"verdict":"pass|need_declaration|block","findings":[{"type":"logo|ip_character|third_party_portrait|copyrighted_work","detail":"","position":""}],"required_declaration":""}

规则：
1. 含第三方肖像 → 至少 need_declaration，声明含"本人为肖像权人或已获授权"。
2. 含品牌 logo 或知名 IP → block，提示更换图片。
3. 拿不准按 need_declaration 处理，宁可多问不可漏放。
4. 直接输出纯 JSON。"""

P15_SYSTEM = """你是图像处理系统的「玩法推荐排序器」。观察用户图片，给能力/流程卡片排序。

能力目录：S1-S13（S1 印花设计 S2 侵权检测 S3 印花提取 S4 抠图 S5 放大 S6 风格迁移 S7 主体保留重绘 S8 场景/服装替换 S9 元素提取 S10 文字排版 S11 套图生成 S12 系列裂变 S13 交付检查）
流程目录：F1-F9（F1 爆款商品裂变 F2 系列套系裂变 F3 关键词生成商品 F4 透明底印花提取 F5 无缝拼接印花 F6 宠物圣诞套系 F7 全家福油画墙 F8 情侣互补款 F9 纪念时间轴）

输出字段：
{"ranked_items":[{"item_id":"S或F开头","item_type":"capability|playbook","reason":"一句话理由","confidence":0.0}]}

排序规则：
1. 主体类型匹配优先：宠物图优先宠物玩法，全家福优先多人玩法。
2. 图片质量差时优先推荐对清晰度容忍度高的风格（像素、贴纸卡通）。
3. 推荐理由必须具体到来图内容，禁止通用话术。
4. 先给一句 subject_summary 字段描述图片主体，再给 ranked_items（取 Top5）。
5. 直接输出纯 JSON。"""

TASKS = {
    "p0_route": P0_SYSTEM,
    "p1_understand": P1_SYSTEM,
    "p4_check": P4_SYSTEM,
    "p5_copy": P5_SYSTEM,
    "p12_compliance": P12_SYSTEM,
    "p15_recommend": P15_SYSTEM,
}

# ── 图片编码 ─────────────────────────────────────────────────────────────

def encode_image(path: Path, max_side: int = 768) -> str:
    img = Image.open(path).convert("RGB")
    w, h = img.size
    scale = min(max_side / w, max_side / h, 1.0)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    if scale < 1.0:
        img = img.resize((nw, nh), Image.LANCZOS)
    buf = BytesIO()
    img.save(buf, format="JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    print(f"  图片 {path.name}: {w}x{h} -> {nw}x{nh}", file=sys.stderr)
    return f"data:image/jpeg;base64,{b64}"


def extract_json(text: str):
    """从模型输出中提取 JSON 对象。"""
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None


def call_mllm(key: str, system: str, user_text: str, image_uris: list,
              json_retry: bool = True):
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    content = [{"type": "text", "text": user_text}]
    content += [{"type": "image_url", "image_url": {"url": u}} for u in image_uris]

    for (url, model) in ENDPOINTS:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": content},
            ],
            "max_tokens": 2000,
            "temperature": 0.2,
        }
        print(f"  -> endpoint: {url} (model {model})", file=sys.stderr)
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=120)
        except requests.RequestException as e:
            print(f"  ↳ 网络错误: {e} -> failover", file=sys.stderr)
            continue
        if resp.status_code == 200:
            raw = resp.json()["choices"][0]["message"]["content"]
            parsed = extract_json(raw)
            if parsed is not None:
                return parsed
            if json_retry:
                print("  ↳ 输出非 JSON，追加强约束重试", file=sys.stderr)
                retry_text = user_text + "\n\n（再次强调：只输出一个合法 JSON 对象，不要任何其他文字）"
                result = call_mllm(key, system, retry_text, image_uris, json_retry=False)
                if result is not None:
                    return result
            print(f"  ↳ JSON 解析失败，原始输出: {raw[:300]}", file=sys.stderr)
            continue
        if resp.status_code in (500, 502, 503, 504):
            print(f"  ↳ HTTP {resp.status_code} -> failover", file=sys.stderr)
            continue
        if resp.status_code in (401, 403):
            # 同一把 key 可能在某个端点无效（2026-08-16 实测 .cn 401 / .com 200），
            # 故单端点拒认先 failover；全部端点都拒认才判定配置错误。
            print(f"  ↳ HTTP {resp.status_code} 认证被拒 → failover: {resp.text[:150]}",
                  file=sys.stderr)
            continue
        print(f"  ↳ HTTP {resp.status_code}: {resp.text[:300]}", file=sys.stderr)
        continue
    return None


def main():
    ap = argparse.ArgumentParser(description="Agnes Studio MLLM 任务执行器")
    ap.add_argument("--task", required=True, choices=list(TASKS.keys()))
    ap.add_argument("--image", action="append", default=[],
                    help="图片路径，可重复（按顺序作为输入图）")
    ap.add_argument("--result-image", default=None,
                    help="P4 专用：处理结果图（自动排在原图之后）")
    ap.add_argument("--intent", default=None, help="用户原话（P1/P0 用）")
    ap.add_argument("--capability", default=None,
                    help="P1 用：目标能力ID，触发精简输出")
    ap.add_argument("--user-file", default=None, help="用户输入 JSON 文件")
    ap.add_argument("--user-text", default=None, help="用户输入纯文本")
    ap.add_argument("--out", default=None, help="结果写入文件（默认 stdout）")
    args = ap.parse_args()

    home = find_agnes_home()
    key = load_key(home)
    print(f"[mllm_task] task={args.task} | agnes-studio: {home}", file=sys.stderr)

    # 组装 user 消息
    parts = []
    if args.user_file:
        parts.append(Path(args.user_file).read_text(encoding="utf-8-sig"))
    if args.user_text:
        parts.append(args.user_text)
    if args.intent:
        parts.append(f"用户原话：{args.intent}")
    if args.capability:
        parts.append(f"target_capability: {args.capability}")

    image_uris = [encode_image(Path(p)) for p in args.image]
    if args.result_image:
        image_uris.append(encode_image(Path(args.result_image)))
        parts.append("以上图片顺序：第一张为原图，最后一张为处理结果。")

    user_text = "\n".join(parts) if parts else "请按系统指令处理输入图片。"

    result = call_mllm(key, TASKS[args.task], user_text, image_uris)
    if result is None:
        sys.exit("ERROR: 所有 endpoint 均失败或输出无法解析。")

    out_str = json.dumps(result, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(out_str, encoding="utf-8")
        print(f"  已写入: {args.out}", file=sys.stderr)
    else:
        print(out_str)


if __name__ == "__main__":
    main()
