#!/usr/bin/env python3
"""
Dify Compliance CLI — 串联完整链路，且与 SKILL.md 里 `python -m skills.dify_compliance.cli` 的调用方式对齐
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import Dict, List, Optional, Any

# 确保能导入本地模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 延性导入飞书模块（避免没装 lark_oapi 时 import 失败）
def _get_feishu_writer():
    try:
        from .feishu_writer import FeishuComplianceWriter
        return FeishuComplianceWriter
    except ImportError as e:
        print(f"[WARN] Feishu writer unavailable: {e}", file=sys.stderr)
        return None

from .client import DifyComplianceClient
from .parser import parse_compliance_report, build_feishu_report_fields


def build_args_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dify Compliance Check CLI")
    parser.add_argument("--spu", required=True, help="SPU ID")
    parser.add_argument("--record", required=True, help="Feishu record ID")
    parser.add_argument("--platforms", default="amazon,etsy,ebay", help="Comma-separated platforms")
    parser.add_argument("--scope", default="visual_final", choices=["draft", "visual_final", "full"])
    parser.add_argument("--copy-file", required=True, help="JSON file with copy_fields")
    parser.add_argument("--no-feishu", action="store_true", help="Skip Feishu writeback (debug mode)")
    parser.add_argument("--output", help="Output JSON file path (default: stdout)")
    parser.add_argument("--base-url", help="Override DIFY_BASE_URL")
    parser.add_argument("--api-key", help="Override DIFY_API_KEY")
    parser.add_argument("--app-type", choices=["workflow", "chatflow"], help="Override DIFY_APP_TYPE")
    return parser


def load_copy_fields(copy_file: str) -> Dict[str, Any]:
    """加载文案字段 JSON 文件"""
    with open(copy_file, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    parser = build_args_parser()
    args = parser.parse_args()

    # 加载文案字段
    copy_fields = load_copy_fields(args.copy_file)

    # 创建客户端
    client = DifyComplianceClient(
        base_url=args.base_url,
        api_key=args.api_key,
        app_type=args.app_type
    )

    # 运行合规检测
    print(f"[CLI] Starting compliance check for SPU {args.spu}...")
    result = client.run_compliance_check(
        spu_id=args.spu,
        feishu_record_id=args.record,
        platforms=args.platforms.split(","),
        copy_fields=copy_fields,
        scan_scope=args.scope
    )

    # 处理结果
    print(f"[CLI] Overall status: {result.overall_status}")
    print(f"[CLI] Summary: {result.summary}")

    # 飞书回写（可选）
    if not args.no_feishu:
        FeishuWriter = _get_feishu_writer()
        if FeishuWriter:
            writer = FeishuWriter()
            writer.write_compliance_result(
                record_id=args.record,
                overall_status=result.overall_status,
                summary=result.summary,
                details=result.details,
                report_markdown=result.report_markdown
            )
        else:
            print("[WARN] Feishu writer unavailable, skipping writeback", file=sys.stderr)
    else:
        print("[CLI] Skipping Feishu writeback (--no-feishu)")

    # 输出结果
    output_data = {
        "overall_status": result.overall_status,
        "summary": result.summary,
        "details": [
            {
                "platform": d.platform,
                "field": d.field,
                "risk_level": d.risk_level,
                "risk_type": d.risk_type,
                "hit_keyword": d.hit_keyword,
                "original_text": d.original_text,
                "suggested_replacement": d.suggested_replacement,
                "platform_rule": d.platform_rule,
                "action_required": d.action_required,
                "location": d.location
            } for d in result.details
        ],
        "report_markdown": result.report_markdown,
        "error": result.error
    }

    output_json = json.dumps(output_data, ensure_ascii=False, indent=2)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        print(f"[CLI] Result saved to {args.output}")
    else:
        print(output_json)

    # 退出码
    if result.overall_status in ("熔断", "FAIL", "ERROR"):
        sys.exit(1)
    sys.exit(0)


def _get_feishu_writer():
    """惰性导入飞书写入器"""
    try:
        from skills.dify_compliance.feishu_writer import FeishuComplianceWriter
        return FeishuComplianceWriter
    except ImportError as e:
        print(f"[WARN] Feishu writer unavailable: {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    import sys
    import json
    import argparse
    from typing import Dict, List, Optional, Any

    # 导入核心模块
    try:
        from skills.dify_compliance.client import DifyComplianceClient
        from skills.dify_compliance.parser import parse_compliance_report, build_feishu_report_fields
    except ImportError as e:
        print(f"[ERROR] Failed to import core modules: {e}", file=sys.stderr)
        sys.exit(1)

    main()