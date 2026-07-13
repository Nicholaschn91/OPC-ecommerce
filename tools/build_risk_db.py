#!/usr/bin/env python3
"""
Build Risk Database — 从 Excel 风险词表构建 SQLite 风险词库

用法:
  python build_risk_db.py --excel "跨境电商风险词词库.xlsx" --output risk_keywords.db
  python build_risk_db.py --excel "新增风险词.xlsx" --merge risk_keywords.db  # 增量更新
  python build_risk_db.py --stats risk_keywords.db  # 统计
"""

import sqlite3
import sys
import argparse
import os
import pandas as pd
from pathlib import Path

def create_schema(conn):
    """创建数据库表结构"""
    cur = conn.cursor()
    
    # 风险词主表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS risk_keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL,
            alternative TEXT,
            level TEXT NOT NULL,          -- 一级（致命）/二级（高危）/三级（中危）
            platform TEXT NOT NULL,       -- amazon/etsy/ebay/all
            risk_type TEXT NOT NULL,      -- 法律/平台/宣传/医疗/敏感/格式/认证
            consequence TEXT,             -- 违规后果
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime')),
            UNIQUE(keyword, platform)
        )
    """)
    
    # 合规检查清单表
    cur.execute("""
        CREATE TABLE IF NOT EXISTS risk_checklist (
            seq INTEGER PRIMARY KEY,
            category TEXT NOT NULL,       -- 侵权合规/宣传合规/医疗健康/平台规则/敏感内容/格式合规/认证合规
            check_item TEXT NOT NULL
        )
    """)
    
    # 索引
    cur.execute("CREATE INDEX IF NOT EXISTS idx_risk_keyword ON risk_keywords(keyword)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_risk_platform ON risk_keywords(platform)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_risk_level ON risk_keywords(level)")
    
    conn.commit()

def import_excel(excel_path: str, conn, merge: bool = False):
    """从 Excel 导入风险词"""
    if not os.path.exists(excel_path):
        print(f"Error: File not found: {excel_path}")
        return 0
    
    # 读取 Excel，支持多 sheet
    xls = pd.ExcelFile(excel_path)
    
    # 查找风险词库 sheet
    target_sheet = None
    for sheet in xls.sheet_names:
        if '风险' in sheet or 'risk' in sheet.lower() or 'keyword' in sheet.lower():
            target_sheet = sheet
            break
    
    if not target_sheet:
        target_sheet = xls.sheet_names[0]
    
    print(f"Reading sheet: {target_sheet}")
    df = pd.read_excel(xls, sheet_name=target_sheet)
    
    # 标准化列名
    col_map = {}
    for col in df.columns:
        col_lower = str(col).strip().lower()
        if '关键词' in col_lower or 'keyword' in col_lower:
            col_map[col] = 'keyword'
        elif '替代' in col_lower or 'alternative' in col_lower or 'replacement' in col_lower:
            col_map[col] = 'alternative'
        elif '等级' in col_lower or 'level' in col_lower or '风险等级' in col_lower:
            col_map[col] = 'level'
        elif '平台' in col_lower or 'platform' in col_lower:
            col_map[col] = 'platform'
        elif '类型' in col_lower or 'type' in col_lower or '风险类型' in col_lower:
            col_map[col] = 'risk_type'
        elif '后果' in col_lower or 'consequence' in col_lower:
            col_map[col] = 'consequence'
    
    df.rename(columns=col_map, inplace=True)
    
    # 检查必需列
    required = ['keyword', 'level', 'platform', 'risk_type']
    for req in required:
        if req not in df.columns:
            print(f"Error: Required column '{req}' not found. Available: {list(df.columns)}")
            return 0
    
    # 清洗数据
    df['keyword'] = df['keyword'].astype(str).str.strip()
    df['alternative'] = df['alternative'].astype(str).str.strip().replace('nan', '')
    df['level'] = df['level'].astype(str).str.strip()
    df['platform'] = df['platform'].astype(str).str.strip().str.lower()
    df['risk_type'] = df['risk_type'].astype(str).str.strip()
    df['consequence'] = df['consequence'].astype(str).str.strip().replace('nan', '')
    
    # 过滤空行
    df = df[df['keyword'] != '']
    df = df[df['keyword'] != 'nan']
    
    print(f"Parsed {len(df)} rows")
    
    # 写入数据库
    cur = conn.cursor()
    inserted = 0
    updated = 0
    skipped = 0
    
    for _, row in df.iterrows():
        try:
            if merge:
                # UPSERT
                cur.execute("""
                    INSERT INTO risk_keywords (keyword, alternative, level, platform, risk_type, consequence, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, datetime('now','localtime'))
                    ON CONFLICT(keyword, platform) DO UPDATE SET
                        alternative = EXCLUDED.alternative,
                        level = EXCLUDED.level,
                        risk_type = EXCLUDED.risk_type,
                        consequence = EXCLUDED.consequence,
                        updated_at = datetime('now','localtime')
                """, (row['keyword'], row['alternative'], row['level'], row['platform'], 
                      row['risk_type'], row['consequence']))
                if cur.rowcount > 0:
                    inserted += 1
            else:
                # 仅插入
                cur.execute("""
                    INSERT OR IGNORE INTO risk_keywords (keyword, alternative, level, platform, risk_type, consequence)
                    VALUES (?, ?, ?, ?, ?, ?)
                """, (row['keyword'], row['alternative'], row['level'], row['platform'], 
                      row['risk_type'], row['consequence']))
                if cur.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1
        except Exception as e:
            print(f"  Warning: Failed to insert '{row['keyword']}': {e}")
    
    conn.commit()
    print(f"Imported: {inserted} inserted, {skipped} skipped")
    return inserted

def import_checklist(excel_path: str, conn):
    """导入合规检查清单"""
    try:
        xls = pd.ExcelFile(excel_path)
        checklist_sheet = None
        for sheet in xls.sheet_names:
            if '清单' in sheet or 'checklist' in sheet.lower():
                checklist_sheet = sheet
                break
        
        if not checklist_sheet:
            print("No checklist sheet found, skipping")
            return
        
        df = pd.read_excel(xls, sheet_name=checklist_sheet)
        print(f"Reading checklist from: {checklist_sheet}")
        
        # 查找列
        cat_col = item_col = None
        for col in df.columns:
            col_lower = str(col).strip().lower()
            if '分类' in col_lower or 'category' in col_lower:
                cat_col = col
            elif '项目' in col_lower or 'item' in col_lower or '检查' in col_lower:
                item_col = col
        
        if not cat_col or not item_col:
            print("Could not identify checklist columns")
            return
        
        cur = conn.cursor()
        cur.execute("DELETE FROM risk_checklist")
        
        for i, (_, row) in enumerate(df.iterrows(), 1):
            cat = str(row[cat_col]).strip()
            item = str(row[item_col]).strip()
            if cat and item and cat != 'nan' and item != 'nan':
                cur.execute("INSERT INTO risk_checklist (seq, category, check_item) VALUES (?, ?, ?)",
                           (i, cat, item))
        
        conn.commit()
        print(f"Imported {i} checklist items")
        
    except Exception as e:
        print(f"Checklist import error: {e}")

def show_stats(db_path: str):
    """显示数据库统计"""
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    
    # 风险词统计
    total = cur.execute("SELECT COUNT(*) FROM risk_keywords").fetchone()[0]
    print(f"\n=== Risk Keywords: {total} total ===")
    
    for level in ['一级（致命）', '二级（高危）', '三级（中危）', 'fatal', 'high', 'medium']:
        cnt = cur.execute("SELECT COUNT(*) FROM risk_keywords WHERE level=?", (level,)).fetchone()[0]
        if cnt:
            print(f"  {level}: {cnt}")
    
    for platform in ['amazon', 'etsy', 'ebay', 'all']:
        cnt = cur.execute("SELECT COUNT(*) FROM risk_keywords WHERE platform=?", (platform,)).fetchone()[0]
        if cnt:
            print(f"  Platform {platform}: {cnt}")
    
    # 检查清单统计
    cl_total = cur.execute("SELECT COUNT(*) FROM risk_checklist").fetchone()[0]
    print(f"\n=== Checklist: {cl_total} items ===")
    for cat, in cur.execute("SELECT DISTINCT category FROM risk_checklist ORDER BY category"):
        cnt = cur.execute("SELECT COUNT(*) FROM risk_checklist WHERE category=?", (cat,)).fetchone()[0]
        print(f"  {cat}: {cnt}")
    
    conn.close()

def main():
    parser = argparse.ArgumentParser(description="Build Risk Database from Excel")
    parser.add_argument("--excel", help="Excel file path")
    parser.add_argument("--output", default="risk_keywords.db", help="Output DB file")
    parser.add_argument("--merge", action="store_true", help="Merge/update existing DB")
    parser.add_argument("--stats", help="Show stats for DB file")
    args = parser.parse_args()
    
    if args.stats:
        show_stats(args.stats)
        return
    
    if not args.excel:
        parser.error("--excel required unless --stats used")
    
    conn = sqlite3.connect(args.output)
    create_schema(conn)
    
    import_excel(args.excel, conn, merge=args.merge)
    import_checklist(args.excel, conn)
    
    show_stats(args.output)
    conn.close()
    print(f"\nDone. Database saved to: {args.output}")

if __name__ == "__main__":
    main()