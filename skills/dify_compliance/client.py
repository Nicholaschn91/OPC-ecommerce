#!/usr/bin/env python3
"""
Dify Compliance Client — 封装 Dify API 调用、载荷组装、结果解析
"""

import os
import json
import time
import requests
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

# ──── Config ──────────────────────────────────────────────
DIFY_API_KEY = os.environ.get("DIFY_API_KEY")
DIFY_BASE_URL = os.environ.get("DIFY_BASE_URL", "https://api.dify.ai")
DIFY_WORKFLOW_ID = os.environ.get("DIFY_WORKFLOW_ID")
DIFY_APP_TYPE = os.environ.get("DIFY_APP_TYPE", "chatflow")  # workflow / chatflow

if not DIFY_API_KEY:
    print("[WARN] DIFY_API_KEY not set in environment")

HEADERS = {
    "Authorization": f"Bearer {DIFY_API_KEY}",
    "Content-Type": "application/json"
}


@dataclass
class ComplianceResult:
    """结构化合规结果"""
    overall_status: str  # 通过 / 需修正 / 熔断 / ERROR
    summary: Dict[str, int]  # fatal, high, medium
    details: List[Dict[str, Any]]
    report_markdown: str
    error: Optional[str] = None


class DifyComplianceClient:
    """Dify 合规检测客户端"""

    def __init__(
        self,
        base_url: str = None,
        api_key: str = None,
        workflow_id: str = None,
        app_type: str = None
    ):
        self.base_url = base_url or DIFY_BASE_URL
        self.api_key = api_key or DIFY_API_KEY
        self.workflow_id = workflow_id or DIFY_WORKFLOW_ID
        self.app_type = app_type or DIFY_APP_TYPE
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def _build_endpoint(self) -> str:
        """构建 API 端点"""
        if self.app_type == "workflow" and self.workflow_id:
            return f"{self.base_url}/v1/workflows/run"
        else:
            return f"{self.base_url}/v1/chat-messages"

    def _build_payload(self, inputs: Dict[str, Any], user: str = "boss-agent") -> Dict[str, Any]:
        """构建请求载荷"""
        if self.app_type == "workflow" and self.workflow_id:
            return {
                "inputs": inputs,
                "response_mode": "blocking",
                "user": user,
                "workflow_id": self.workflow_id
            }
        else:
            return {
                "inputs": inputs,
                "response_mode": "blocking",
                "user": user
            }

    def _parse_response(self, resp_data: Dict[str, Any]) -> ComplianceResult:
        """解析 Dify 响应为结构化结果"""
        # 兼容 workflow.run 和 chat-messages 两种响应格式
        if "data" in resp_data and "outputs" in resp_data["data"]:
            # workflow.run 格式
            outputs = resp_data["data"]["outputs"]
        elif "answer" in resp_data:
            # chat-messages 格式，answer 可能是 JSON 字符串
            try:
                import json
                outputs = json.loads(resp_data["answer"])
            except json.JSONDecodeError:
                return ComplianceResult(
                    overall_status="ERROR",
                    summary={"fatal": 0, "high": 0, "medium": 0},
                    details=[],
                    report_markdown="",
                    error=f"Dify answer not valid JSON: {resp_data['answer'][:200]}"
                )
        else:
            return ComplianceResult(
                overall_status="ERROR",
                summary={"fatal": 0, "high": 0, "medium": 0},
                details=[],
                report_markdown="",
                error=f"Unexpected Dify response format: {list(resp_data.keys())}"
            )

        # 解析结构化输出
        try:
            overall_status = outputs.get("overall_status", "ERROR")
            summary = outputs.get("summary", {"fatal": 0, "high": 0, "medium": 0})
            details = outputs.get("details", [])
            report_md = outputs.get("report_markdown", "")

            return ComplianceResult(
                overall_status=overall_status,
                summary=summary,
                details=details,
                report_markdown=report_md
            )
        except Exception as e:
            return ComplianceResult(
                overall_status="ERROR",
                summary={"fatal": 0, "high": 0, "medium": 0},
                details=[],
                report_markdown="",
                error=f"Failed to parse Dify outputs: {e}"
            )

    def _call_with_retry(self, endpoint: str, payload: Dict[str, Any],
                         max_retries: int = 3, timeout: int = 60) -> Dict[str, Any]:
        """带重试的 HTTP 调用"""
        last_error = None

        for attempt in range(max_retries):
            try:
                resp = requests.post(
                    endpoint,
                    headers=self.headers,
                    json=payload,
                    timeout=timeout
                )

                if resp.status_code == 429:
                    # 429 退避
                    wait_time = 10 * (attempt + 1)
                    print(f"[Dify] 429 Rate limited, waiting {wait_time}s... (attempt {attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                    continue

                if resp.status_code >= 500:
                    # 5xx 重试
                    wait_time = 5 * (attempt + 1)
                    print(f"[Dify] {resp.status_code} Server error, waiting {wait_time}s... (attempt {attempt+1}/{max_retries})")
                    time.sleep(wait_time)
                    continue

                resp.raise_for_status()
                return resp.json()

            except requests.Timeout:
                last_error = "Request timeout"
                print(f"[Dify] Timeout (attempt {attempt+1}/{max_retries})")
            except requests.RequestException as e:
                last_error = str(e)
                print(f"[Dify] Request error: {e} (attempt {attempt+1}/{max_retries})")

        raise RuntimeError(f"Dify API call failed after {max_retries} attempts: {last_error}")

    def run_compliance_check(self,
                             spu_id: str,
                             feishu_record_id: str,
                             platforms: List[str],
                             copy_fields: Dict[str, Any],
                             visual_prompts: Optional[Dict[str, Any]] = None,
                             aplus_content: Optional[Dict[str, Any]] = None,
                             scan_scope: str = "visual_final") -> ComplianceResult:
        """
        运行合规检测

        Args:
            spu_id: SPU ID
            feishu_record_id: 飞书记录 ID
            platforms: 目标平台列表
            copy_fields: 各平台文案字段
            visual_prompts: 视觉 Prompts (可选)
            aplus_content: A+ 内容 (可选)
            scan_scope: 扫描范围 (draft / visual_final / full)

        Returns:
            ComplianceResult
        """

        # 组装 Dify 输入变量
        inputs = self._build_dify_inputs(
            spu_id=spu_id,
            platforms=platforms,
            copy_fields=copy_fields,
            visual_prompts=visual_prompts or {},
            aplus_content=aplus_content or {},
            scan_scope=scan_scope
        )

        endpoint = self._build_endpoint()
        payload = self._build_payload(inputs)

        print(f"[Dify] Calling {endpoint} for SPU {spu_id}...")
        resp_data = self._call_with_retry(endpoint, payload)

        return self._parse_response(resp_data)

    def _build_dify_inputs(self,
                           spu_id: str,
                           platforms: List[str],
                           copy_fields: Dict[str, Any],
                           visual_prompts: Dict[str, Any],
                           aplus_content: Dict[str, Any],
                           scan_scope: str) -> Dict[str, Any]:
        """构建 Dify 输入变量映射（对应 Dify 应用的输入变量）"""
        inputs = {
            "spu_id": spu_id,
            "platforms": platforms,
            "scan_scope": scan_scope,
        }

        # Amazon 字段
        if "amazon" in copy_fields:
            af = copy_fields["amazon"]
            inputs.update({
                "amazon_title": af.get("title", ""),
                "amazon_bullets": "\n".join(af.get("bullets", [])),
                "amazon_description": af.get("description", ""),
                "amazon_st": af.get("search_terms", ""),
                "amazon_faq": "\n".join([f"Q: {q}\nA: {a}" for q, a in af.get("faq", [])]),
            })

        # Etsy 字段
        if "etsy" in copy_fields:
            ef = copy_fields["etsy"]
            inputs.update({
                "etsy_title": ef.get("title", ""),
                "etsy_tags": ", ".join(ef.get("tags", [])),
                "etsy_description": ef.get("description", ""),
            })

        # eBay 字段
        if "ebay" in copy_fields:
            eb = copy_fields["ebay"]
            inputs.update({
                "ebay_title_matrix": "\n".join(eb.get("title_matrix", [])),
                "ebay_bullets": "\n".join(eb.get("bullets", [])),
                "ebay_item_specifics": json.dumps(eb.get("item_specifics", {}), ensure_ascii=False),
                "ebay_desc_html": eb.get("desc_html", ""),
            })

        # 视觉 Prompts
        if visual_prompts:
            for platform, prompts in visual_prompts.items():
                key = f"visual_prompts_{platform}"
                if isinstance(prompts, dict):
                    inputs[key] = "\n\n".join([f"Img{i+1}: {v}" for i, v in enumerate(prompts.values())])
                else:
                    inputs[key] = str(prompts)

        # A+ 内容
        if aplus_content:
            inputs["aplus_copy"] = "\n\n".join([f"Copy{i+1}: {v}" for i, v in enumerate(aplus_content.get("copy", {}).values())])
            inputs["aplus_prompt"] = "\n\n".join([f"Prompt{i+1}: {v}" for i, v in enumerate(aplus_content.get("prompt", {}).values())])

        return inputs


# ──── CLI ──────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Dify Compliance Check CLI")
    parser.add_argument("--spu", required=True, help="SPU ID")
    parser.add_argument("--record", required=True, help="Feishu record ID")
    parser.add_argument("--platforms", default="amazon,etsy,ebay", help="Comma-separated platforms")
    parser.add_argument("--scope", default="visual_final", choices=["draft", "visual_final", "full"])
    parser.add_argument("--copy-file", help="JSON file with copy_fields")
    args = parser.parse_args()

    if not args.copy_file:
        print("Error: --copy-file required")
        exit(1)

    with open(args.copy_file, "r", encoding="utf-8") as f:
        copy_fields = json.load(f)

    client = DifyComplianceClient()
    result = client.run_compliance_check(
        spu_id=args.spu,
        feishu_record_id=args.record,
        platforms=args.platforms.split(","),
        copy_fields=copy_fields,
        scan_scope=args.scope
    )

    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))