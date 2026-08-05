"""
Dify Compliance Parser — 结果解析、风险分级映射、飞书字段映射
"""

import json
import re
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, asdict


@dataclass
class RiskDetail:
    """单条风险详情"""
    platform: str
    field: str
    risk_level: str  # fatal / high / medium
    risk_type: str
    hit_keyword: str
    original_text: str
    suggested_replacement: str
    platform_rule: str
    action_required: str  # circuit_break / user_confirm_replace / silent_fix
    location: str = ""  # 标题 / Bullet2 / 描述 等


@dataclass
class ComplianceReport:
    """完整合规报告"""
    spu_id: str
    feishu_record_id: str
    overall_status: str  # 通过 / 需修正 / 熔断 / ERROR
    summary: Dict[str, int]  # fatal, high, medium
    details: List[RiskDetail]
    report_markdown: str


# ──── 风险等级映射 ────────────────────────────────────────
RISK_LEVEL_MAP = {
    "一级（致命）": "fatal",
    "二级（高危）": "high",
    "三级（中危）": "medium",
    "fatal": "fatal",
    "high": "high",
    "medium": "medium",
    "critical": "fatal",
}

ACTION_MAP = {
    "circuit_break": "circuit_break",
    "user_confirm_replace": "user_confirm_replace",
    "silent_fix": "silent_fix",
    "熔断": "circuit_break",
    "需用户确认替换": "user_confirm_replace",
    "静默替换": "silent_fix",
}


def parse_dify_output(outputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    解析 Dify 输出为标准结构
    支持两种格式：
    1. 标准结构化 JSON（workflow.run 输出）
    2. chat-messages 的 answer 字段包含的 JSON 字符串
    """
    # 已经是标准结构
    if all(k in outputs for k in ("overall_status", "summary", "details")):
        return outputs

    # 尝试从 answer 字段解析
    if "answer" in outputs:
        try:
            import json
            return json.loads(outputs["answer"])
        except json.JSONDecodeError:
            pass

    # 兜底：构造最小结构
    return {
        "overall_status": outputs.get("overall_status", "ERROR"),
        "summary": outputs.get("summary", {"fatal": 0, "high": 0, "medium": 0}),
        "details": outputs.get("details", []),
        "report_markdown": outputs.get("report_markdown", "")
    }


def normalize_risk_level(level: str) -> str:
    """标准化风险等级"""
    return RISK_LEVEL_MAP.get(level, level)


def normalize_action(action: str) -> str:
    """标准化处理动作"""
    return ACTION_MAP.get(action, action)


def parse_detail(detail: Dict[str, Any], platform: str) -> Dict[str, Any]:
    """
    解析单条 detail 为标准结构
    """
    risk_level = normalize_risk_level(detail.get("risk_level", detail.get("level", "")))
    action = normalize_action(detail.get("action_required", ""))

    return {
        "platform": platform,
        "field": detail.get("field", detail.get("field_name", "")),
        "risk_level": risk_level,
        "risk_type": detail.get("risk_type", detail.get("type", "")),
        "hit_keyword": detail.get("hit_keyword", detail.get("keyword", "")),
        "original_text": detail.get("original_text", detail.get("original", "")),
        "suggested_replacement": detail.get("suggested_replacement", detail.get("replacement", detail.get("fix", ""))),
        "platform_rule": detail.get("platform_rule", detail.get("rule", "")),
        "action_required": action,
        "location": detail.get("location", detail.get("field_location", "")),
    }


def parse_compliance_report(raw_outputs: Dict[str, Any],
                             spu_id: str,
                             feishu_record_id: str) -> Dict[str, Any]:
    """
    将 Dify 原始输出转换为标准合规报告结构
    """
    outputs = parse_dify_output(raw_outputs)

    overall = outputs.get("overall_status", "ERROR")
    summary = outputs.get("summary", {"fatal": 0, "high": 0, "medium": 0})
    details_raw = outputs.get("details", [])
    report_md = outputs.get("report_markdown", "")

    # 标准化 details
    details = []
    for d in details_raw:
        platform = d.get("platform", "unknown")
        details.append(parse_detail(d, platform))

    return {
        "overall_status": overall,
        "summary": summary,
        "details": details,
        "report_markdown": report_md
    }


def build_feishu_report_fields(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    构建飞书字段写入载荷
    """
    overall = report["overall_status"]
    summary = report["summary"]
    details = report["details"]
    report_md = report["report_markdown"]

    # 状态映射
    status_map = {
        "通过": "通过",
        "PASS": "通过",
        "需修正": "需修正",
        "WARN": "需修正",
        "熔断": "熔断",
        "FAIL": "熔断",
        "ERROR": "需修正",
    }

    # 构建明细表格
    if details:
        md_lines = ["| 平台 | 字段 | 风险等级 | 违规类型 | 命中词 | 原文摘要 | 替换建议 | 处理动作 |",
                    "|------|------|----------|----------|--------|----------|----------|----------|"]
        for d in details:
            orig = d.get('original_text', '')[:50]
            repl = d.get('suggested_replacement', '')
            md_lines.append(
                f"| {d.get('platform', '')} | {d.get('field', '')} | {d.get('risk_level', '')} | "
                f"{d.get('risk_type', '')} | {d.get('hit_keyword', '')} | {orig}... | "
                f"{repl} | {d.get('action_required', '')} |"
            )
        details_table = "\n".join(md_lines)
    else:
        details_table = "无违规项 ✅"

    # 完整报告
    full_report = f"""## 合规扫描报告

**整体判定**: {status_map.get(overall, overall)}
**统计**: 🚫 致命 {summary.get('fatal', 0)} | 🟠 高危 {summary.get('high', 0)} | 🟡 中危 {summary.get('medium', 0)}

---

### 违规明细
{details_table}

---

### 处理建议
- 🚫 **致命项**: 必须修正后才能发布，触发熔断
- 🟠 **高危项**: 需人工确认替换建议后回写
- 🟡 **中危项**: 建议静默替换，不阻塞流程

{report_md}
"""

    return {
        "合规扫描报告": full_report,
        "合规状态": status_map.get(overall, overall),
    }


# ──── CLI 测试 ────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    # 测试用例
    test_outputs = {
        "overall_status": "需修正",
        "summary": {"fatal": 0, "high": 2, "medium": 5},
        "details": [
            {
                "platform": "amazon",
                "field": "amazon_bullets",
                "risk_level": "二级（高危）",
                "risk_type": "夸大宣传",
                "hit_keyword": "lifetime guarantee",
                "original_text": "Offers a lifetime guarantee on all parts",
                "suggested_replacement": "Offers a long-lasting warranty on all parts",
                "platform_rule": "Amazon 绝对化用语红线（FTC 指引）",
                "action_required": "user_confirm_replace",
                "location": "Bullet 3"
            }
        ],
        "report_markdown": "## 审核总结..."
    }

    result = parse_compliance_report(test_outputs, "SPU-12345", "rec_xxxxx")
    print(json.dumps(result, ensure_ascii=False, indent=2))