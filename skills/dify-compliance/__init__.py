# Dify Compliance Skill Package

"""
Dify Compliance Skill Package

核心功能:
- 组装 Dify API 所需的完整输入载荷
- 调用 Dify Workflow/Chatflow API（阻塞模式）
- 解析结构化输出 → 飞书字段回写 + 事件发布
- 处理三级风险的差异化动作
"""

from .client import DifyComplianceClient
from .parser import parse_compliance_report, build_feishu_report_fields, parse_dify_output
from .feishu_writer import FeishuComplianceWriter

__all__ = [
    "DifyComplianceClient",
    "parse_compliance_report",
    "build_feishu_report_fields",
    "parse_dify_output",
    "FeishuComplianceWriter",
]

__version__ = "1.0.0"