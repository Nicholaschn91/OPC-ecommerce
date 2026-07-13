"""
Feishu Writer — 合规扫描结果回写飞书多维表格
"""

import os
import json
from typing import Dict, Any, List, Optional


class FeishuComplianceWriter:
    """飞书合规扫描结果写入器"""

    def __init__(self, app_id: str = None, app_secret: str = None,
                 base_id: str = None, table_id: str = None):
        self.app_id = app_id or os.environ.get("FEISHU_APP_ID", "cli_a951353ba6b8dbcf")
        self.app_secret = app_secret or os.environ.get("FEISHU_APP_SECRET", "YOUR_FEISHU_APP_SECRET_HERE")
        self.base_id = base_id or os.environ.get("FEISHU_BASE_ID", "ONy9bZ0oFaaiSEsf4ggcs61enRc")
        self.table_id = table_id or os.environ.get("FEISHU_TABLE_ID", "tbl75glY29VulRLm")

        # 延迟导入 lark_oapi
        self._client = None

    @property
    def client(self):
        if self._client is None:
            try:
                from lark_oapi import Client
                self._client = Client.builder() \
                    .app_id(self.app_id) \
                    .app_secret(self.app_secret) \
                    .build()
            except ImportError as e:
                raise ImportError("lark-oapi not installed. Run: pip install lark-oapi") from e
        return self._client

    def write_compliance_result(self,
                                record_id: str,
                                overall_status: str,
                                summary: Dict[str, int],
                                details: List[Dict[str, Any]],
                                report_markdown: str) -> bool:
        """
        将合规扫描结果写入飞书记录

        Args:
            record_id: 飞书记录 ID
            overall_status: 整体状态 (通过 / 需修正 / 熔断)
            summary: 统计摘要 {fatal, high, medium}
            details: 违规明细列表
            report_markdown: 完整报告 Markdown

        Returns:
            是否写入成功
        """
        try:
            # 构建字段载荷
            fields = self._build_fields(overall_status, summary, details, report_markdown)

            # 更新记录
            from lark_oapi.api.bitable.v1 import UpdateAppTableRecordRequest, AppTableRecord

            request = UpdateAppTableRecordRequest.builder() \
                .app_token(self.base_id) \
                .table_id(self.table_id) \
                .record_id(record_id) \
                .request_body(AppTableRecord.builder().fields(fields).build()) \
                .build()

            response = self.client.bitable.v1.app_table_record.update(request)

            if not response.success():
                print(f"[Feishu] Write failed: {response.code} - {response.msg}")
                return False

            print(f"[Feishu] Compliance result written to record {record_id}")
            return True

        except Exception as e:
            print(f"[Feishu] Write error: {e}")
            return False

    def _build_fields(self, overall_status: str, summary: Dict[str, int],
                      details: List[Dict[str, Any]], report_markdown: str) -> Dict[str, Any]:
        """构建飞书字段映射"""

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

**整体判定**: {status_map.get(overall_status, overall_status)}
**统计**: 🚫 致命 {summary.get('fatal', 0)} | 🟠 高危 {summary.get('high', 0)} | 🟡 中危 {summary.get('medium', 0)}

---

### 违规明细
{details_table}

---

### 处理建议
- 🚫 **致命项**: 必须修正后才能发布，触发熔断
- 🟠 **高危项**: 需人工确认替换建议后回写
- 🟡 **中危项**: 建议静默替换，不阻塞流程

{report_markdown}
"""

        return {
            "合规扫描报告": full_report,
            "合规状态": status_map.get(overall_status, overall_status),
        }


# ──── CLI 测试 ────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    # 测试用例
    test_record = "rec_test123"
    writer = FeishuComplianceWriter()

    # 模拟数据
    overall = "需修正"
    summary = {"fatal": 0, "high": 2, "medium": 5}
    details = [
        {
            "platform": "amazon",
            "field": "amazon_bullets",
            "risk_level": "high",
            "risk_type": "夸大宣传",
            "hit_keyword": "lifetime guarantee",
            "original_text": "Offers a lifetime guarantee on all parts",
            "suggested_replacement": "Offers a long-lasting warranty on all parts",
            "platform_rule": "Amazon 绝对化用语红线（FTC 指引）",
            "action_required": "user_confirm_replace",
        }
    ]
    report_md = "## 审核总结..."

    # 只打印构建的字段，不实际写入
    fields = writer._build_fields(overall, {"fatal": 0, "high": 2, "medium": 5},
                                  [{"platform": "amazon", "field": "amazon_bullets", "risk_level": "high",
                                    "risk_type": "夸大宣传", "hit_keyword": "lifetime guarantee",
                                    "original_text": "Offers a lifetime guarantee on all parts",
                                    "suggested_replacement": "Offers a long-lasting warranty on all parts",
                                    "platform_rule": "Amazon 绝对化用语红线（FTC 指引）",
                                    "action_required": "user_confirm_replace"}],
                                  "## 审核总结...")
    print(json.dumps(fields, ensure_ascii=False, indent=2))