#!/usr/bin/env python3
"""
feishu_io.py — 统一飞书多维表格读写封装

Base A（输入）: ONy9bZ0oFaaiSEsf4ggcs61enRc / tbl75glY29VulRLm
Base B（输出）: RP5ubb66waZnwDsc2MNcchcCnOb / tblLku5v29ExnvtV
"""

import os
import json
import time
from typing import Dict, Any, List, Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError

BASE_A_ID = "ONy9bZ0oFaaiSEsf4ggcs61enRc"
BASE_A_TABLE = "tbl75glY29VulRLm"
BASE_B_ID = "RP5ubb66waZnwDsc2MNcchcCnOb"
BASE_B_TABLE = "tblLku5v29ExnvtV"
FEISHU_API = "https://open.feishu.cn/open-apis"


class FeishuIO:
    """飞书多维表格统一读写器"""

    def __init__(self, base: str = "B"):
        app_id = os.getenv("FEISHU_APP_ID", "cli_a951353ba6b8dbcf")
        app_secret = os.getenv("FEISHU_APP_SECRET", "")
        if not app_secret:
            raise ValueError("FEISHU_APP_SECRET not set in environment")

        self.app_id = app_id
        self.app_secret = app_secret
        self.base = base.upper()
        self.base_id = BASE_A_ID if self.base == "A" else BASE_B_ID
        self.table_id = BASE_A_TABLE if self.base == "A" else BASE_B_TABLE
        self._token = None

    # ── Token ────────────────────────────────────────
    def _get_token(self) -> str:
        if self._token:
            return self._token
        url = f"{FEISHU_API}/auth/v3/tenant_access_token/internal"
        body = json.dumps({"app_id": self.app_id, "app_secret": self.app_secret}).encode()
        req = Request(url, data=body, headers={"Content-Type": "application/json"})
        res = json.loads(urlopen(req).read())
        self._token = res.get("tenant_access_token", "")
        return self._token

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }

    # ── Base CRUD ────────────────────────────────────
    def read_records(self, page_size: int = 100, filter_expr: str = None) -> List[dict]:
        """读取 Base 记录"""
        url = f"{FEISHU_API}/bitable/v1/apps/{self.base_id}/tables/{self.table_id}/records"
        params = {"page_size": page_size}
        if filter_expr:
            params["filter"] = filter_expr

        all_records = []
        while True:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            resp = json.loads(urlopen(Request(f"{url}?{qs}", headers=self._headers())).read())
            items = resp.get("data", {}).get("items", [])
            all_records.extend(items)
            if not resp.get("data", {}).get("has_more"):
                break
            params["page_token"] = resp["data"]["page_token"]

        return all_records

    def create_record(self, fields: dict) -> str:
        """Create a record and return record_id"""
        url = f"{FEISHU_API}/bitable/v1/apps/{self.base_id}/tables/{self.table_id}/records"
        body = json.dumps({"fields": fields}).encode()
        resp = json.loads(urlopen(Request(url, data=body, headers=self._headers())).read())
        return resp["data"]["record"]["record_id"]

    def update_record(self, record_id: str, fields: dict) -> None:
        """Update an existing record"""
        url = f"{FEISHU_API}/bitable/v1/apps/{self.base_id}/tables/{self.table_id}/records/{record_id}"
        body = json.dumps({"fields": fields}).encode()
        urlopen(Request(url, data=body, headers=self._headers(), method="PUT"))

    def search_records(self, field: str, value: Any) -> List[dict]:
        """Search records by field value"""
        url = f"{FEISHU_API}/bitable/v1/apps/{self.base_id}/tables/{self.table_id}/records/search"
        body = json.dumps({
            "field_names": [field],
            "filter": {
                "conjunction": "and",
                "conditions": [{"field_name": field, "operator": "is", "value": [value]}],
            },
        }).encode()
        resp = json.loads(urlopen(Request(url, data=body, headers=self._headers())).read())
        return resp.get("data", {}).get("items", [])

    # ── Base A helpers ─────────────────────────────────
    def read_spurs(self) -> List[dict]:
        """Read all SPU records from Base A"""
        return self._read_records()

    def read_spu_by_id(self, spu_id: str) -> Optional[dict]:
        """Read a single SPU by record_id"""
        url = f"{FEISHU_API}/bitable/v1/apps/{self.base_id}/tables/{self.table_id}/records/{spu_id}"
        try:
            return json.loads(urlopen(Request(url, headers=self._headers())).read())
        except HTTPError:
            return None

    # ── Base B helpers ─────────────────────────────────
    def create_parent_record(self, spu_id: str, product_name: str, fields: dict) -> str:
        """Create a parent record in Base B"""
        merged = fields | {"spu_id": spu_id, "product_name": product_name}
        return self.create_record(merged)

    def create_child_record(self, parent_id: str, variant: dict, fields: dict) -> str:
        """Create a child record under parent"""
        merged = {
            "parent_record_id": parent_id,
            "variant_attr_1": variant.get("variant_attr_1", ""),
            "variant_attr_2": variant.get("variant_attr_2", ""),
            **fields,
        }
        return self.create_record(merged)

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }