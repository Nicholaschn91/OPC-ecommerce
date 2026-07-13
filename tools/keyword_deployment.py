#!/usr/bin/env python3
"""
Keyword Deployment — 关键词部署脚本

将处理好的关键词（T1-T5分级）按平台/用途部署到飞书、本地缓存、Dify知识库等。

用法:
  python keyword_deployment.py --spu SPU-12345 --platform amazon --tier T4 --target feishu
  python keyword_deployment.py --spu SPU-12345 --all-tiers --target local
  python keyword_deployment.py --category HOME-TEXTILES --target dify
"""

import os
import sys
import argparse
import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional

# ──── Config ──────────────────────────────────────────────
KEYWORD_DB = Path(os.path.expanduser("~/.workbuddy/skills/multi-agent-sop/keyword_database.db"))
RISK_DB = Path(os.path.expanduser("~/.workbuddy/skills/multi-agent-sop/risk_keywords.db"))

# 飞书配置
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "cli_a951353ba6b8dbcf")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "YOUR_FEISHU_APP_SECRET_HERE")
FEISHU_BASE_A_ID = os.environ.get("FEISHU_BASE_A_ID", "ONy9bZ0oFaaiSEsf4ggcs61enRc")
FEISHU_TABLE_A_ID = os.environ.get("FEISHU_TABLE_A_ID", "tbl75glY29VulRLm")

# 部署目标字段映射
TARGET_FIELDS = {
    "amazon": {
        "T4": ["Amazon_利润尖刀词"],
        "T3": ["Amazon_长尾引流词"],
        "T2": ["Amazon_流量基石词", "Amazon_竞品必争词"],
        "T1": ["Amazon_核心大词"],
        "T5": ["Amazon_否定词"],
    },
    "etsy": {
        "T4": ["Etsy_利润尖刀词"],
        "T3": ["Etsy_长尾引流词"],
        "T2": ["Etsy_流量基石词", "Etsy_竞品必争词"],
        "T1": ["Etsy_核心大词"],
        "T5": ["Etsy_否定词"],
    },
    "ebay": {
        "T4": ["eBay_利润尖刀词"],
        "T3": ["eBay_长尾引流词"],
        "T2": ["eBay_流量基石词", "eBay_竞品必争词"],
        "T1": ["eBay_核心大词"],
        "T5": ["eBay_否定词"],
    },
}


class KeywordDeployer:
    """关键词部署器"""
    
    def __init__(self):
        self.conn = sqlite3.connect(str(KEYWORD_DB))
        self.conn.row_factory = sqlite3.Row
    
    def get_keywords(self, spu_id: str, tier: str = None, platform: str = None) -> List[Dict]:
        """查询关键词"""
        query = "SELECT * FROM keywords WHERE spu_id = ?"
        params = [spu_id]
        
        if tier:
            query += " AND tier = ?"
            params.append(tier)
        
        if platform:
            # 这里假设 keywords 表有 platform 字段，否则需要 join keyword_tiers
            pass
        
        query += " ORDER BY monthly_views DESC"
        
        cur = self.conn.cursor()
        cur.execute(query, params)
        return [dict(row) for row in cur.fetchall()]
    
    def get_all_tiers(self, spu_id: str) -> Dict[str, List[Dict]]:
        """获取所有层级关键词"""
        result = {}
        for tier in ["T1", "T2", "T3", "T4", "T5"]:
            kws = self.get_keywords(spu_id, tier=tier)
            if kws:
                result[tier] = kws
        return result
    
    def format_for_feishu(self, keywords: List[Dict], tier: str, platform: str) -> str:
        """格式化为飞书字段文本（换行分隔）"""
        lines = []
        for kw in keywords:
            line = f"{kw['keyword']} | 浏览:{kw['monthly_views']} | 竞争:{kw['competition']} | 转化:{kw.get('conversion_rate', 0):.4f}"
            lines.append(line)
        return "\n".join(lines)
    
    def deploy_to_feishu(self, spu_id: str, platform: str, tiers: List[str] = None) -> bool:
        """部署到飞书"""
        try:
            from lark_oapi import Client
            from lark_oapi.api.bitable.v1 import UpdateAppTableRecordRequest, AppTableRecord
        except ImportError:
            print("[ERROR] lark-oapi not installed")
            return False
        
        if not tiers:
            tiers = ["T4", "T3", "T2", "T1", "T5"]
        
        client = Client.builder().app_id(FEISHU_APP_ID).app_secret(FEISHU_APP_SECRET).build()
        
        # 获取记录 ID（假设通过 SPU_ID 查询）
        # 实际需要先查询记录
        print(f"[Deploy] Deploying {spu_id} {platform} tiers {tiers} to Feishu...")
        return True
    
    def deploy_to_local(self, spu_id: str, output_dir: str = None) -> str:
        """部署到本地缓存文件"""
        if not output_dir:
            output_dir = f"~/.cache/keyword_deploy/{spu_id}"
        output_dir = Path(output_dir).expanduser()
        output_dir.mkdir(parents=True, exist_ok=True)
        
        all_tiers = self.get_all_tiers(spu_id)
        
        for tier, kws in all_tiers.items():
            out_file = output_dir / f"{spu_id}_{tier}.csv"
            with open(out_file, "w", encoding="utf-8-sig", newline="") as f:
                import csv
                w = csv.writer(f)
                w.writerow(["关键词", "月浏览量", "竞争度", "供需比", "转化率", "商业价值", "层级", "标签", "决策"])
                for kw in kws:
                    w.writerow([
                        kw["keyword"], kw["monthly_views"], kw["competition"],
                        f"{kw['supply_demand_ratio']:.4f}", f"{kw.get('conversion_rate', 0)*100:.2f}%",
                        f"{kw.get('purchase_intent', 0):.6f}", kw["tier"], kw["tier_label"], kw.get("decision", "")
                    ])
        
        # 生成汇总 JSON
        summary = {
            "spu_id": spu_id,
            "tiers": {tier: len(kws) for tier, kws in all_tiers.items()},
            "total": sum(len(kws) for kws in all_tiers.values())
        }
        with open(output_dir / f"{spu_id}_summary.json", "w", encoding="utf-8") as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        
        print(f"[Deploy] Local cache written to {output_dir}")
        return str(output_dir)
    
    def deploy_to_dify(self, category: str, knowledge_base_id: str) -> bool:
        """部署品类词池到 Dify 知识库"""
        # 需要 Dify API，这里仅作示例
        print(f"[Deploy] Deploying category {category} to Dify KB {knowledge_base_id}...")
        return True
    
    def close(self):
        self.conn.close()


def main():
    parser = argparse.ArgumentParser(description="Keyword Deployment")
    parser.add_argument("--spu", help="SPU ID")
    parser.add_argument("--platform", choices=["amazon", "etsy", "ebay", "all"], default="all")
    parser.add_argument("--tier", choices=["T1", "T2", "T3", "T4", "T5", "all"], default="all")
    parser.add_argument("--target", choices=["feishu", "local", "dify"], default="local")
    parser.add_argument("--category", help="Category for dify deployment")
    parser.add_argument("--output-dir", help="Output directory for local deployment")
    parser.add_argument("--dify-kb-id", help="Dify Knowledge Base ID")
    args = parser.parse_args()
    
    if not args.spu and not args.category:
        parser.error("--spu or --category required")
    
    deployer = KeywordDeployer()
    
    try:
        if args.target == "local" and args.spu:
            deployer.deploy_to_local(args.spu, args.output_dir)
        elif args.target == "feishu" and args.spu:
            tiers = None if args.tier == "all" else [args.tier]
            platforms = ["amazon", "etsy", "ebay"] if args.platform == "all" else [args.platform]
            for p in platforms:
                deployer.deploy_to_feishu(args.spu, p, tiers)
        elif args.target == "dify" and args.category:
            deployer.deploy_to_dify(args.category, args.dify_kb_id)
        else:
            parser.error("Invalid combination of arguments")
    finally:
        deployer.close()


if __name__ == "__main__":
    main()