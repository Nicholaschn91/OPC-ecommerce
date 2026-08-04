#!/usr/bin/env python3
"""
SOP Runner — 多阶段 Listing 生成流水线

用法：
  python sop-runner.py start --spu-id S001              # Phase 1 开始
  python sop-runner.py confirm --phase 2 --spu-id S001  # Phase 2 人工确认
  python sop-runner.py status --spu-id S001             # 查看当前阶段
  python sop-runner.py resume --spu-id S001             # 恢复中断流程
  python sop-runner.py list                             # 列出所有进行中的 SPU
"""

import argparse
import sqlite3
import json
import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List

# 路径配置
BASE_DIR = Path(__file__).parent.parent
TOOLS_DIR = BASE_DIR / "tools"
DB_DIR = BASE_DIR / "shared" / "databases"
STATE_DIR = BASE_DIR / "state"
SKILLS_DIR = BASE_DIR / "skills"

# 闸门配置
GATE_RULES = {
    2: {
        "name": "CRITICAL_STOP",
        "timeout": 300,
        "confirm_keywords": ["确认", "继续", "通过", "OK", "ok", "confirm", "approve"]
    },
    3: {
        "name": "HUMAN_CONFIRM",
        "timeout": 300,
        "confirm_keywords": ["确认", "继续", "通过", "OK", "ok", "confirm", "approve"]
    },
    5: {
        "name": "COMPLIANCE_CONFIRM",
        "timeout": 300,
        "confirm_keywords": ["确认", "继续", "通过", "OK", "ok", "confirm", "approve", "替换", "replace", "修正", "fix"]
    }
}

def get_state_db():
    """获取 state 数据库连接"""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    state_db = STATE_DIR / "sop_state.db"
    conn = sqlite3.connect(state_db)
    cursor = conn.cursor()
    
    # 创建表（如果不存在）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS spu_states (
            spu_id TEXT PRIMARY KEY,
            current_phase INTEGER DEFAULT 1,
            status TEXT DEFAULT 'pending',
            state JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gate_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            spu_id TEXT,
            phase INTEGER,
            event_type TEXT,
            payload JSON,
            confirmed_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn

def start_spu(spu_id: str, spu_name: str, category: str = "生活家居"):
    """Phase 1: 启动新的 SPU 处理流程"""
    conn = get_state_db()
    cursor = conn.cursor()
    
    # 检查是否已存在
    cursor.execute("SELECT status FROM spu_states WHERE spu_id = ?", (spu_id,))
    if cursor.fetchone():
        print(f"错误: SPU {spu_id} 已存在，请使用 resume 命令")
        conn.close()
        return
    
    # 创建新记录
    cursor.execute("""
        INSERT INTO spu_states (spu_id, current_phase, status, state)
        VALUES (?, 1, 'pending', ?)
    """, (spu_id, json.dumps({
        "spu_name": spu_name,
        "category": category,
        "start_time": datetime.now().isoformat()
    })))
    conn.commit()
    conn.close()
    
    print(f"✅ SPU {spu_id} ({spu_name}) 已创建，进入 Phase 1")
    print(f"   正在启动双线并行基材准备...")
    
    # TODO: 调用 scraper skill 和 keyword-grader skill
    # runner.call_skill("scraper", {"spu_id": spu_id, ...})
    # runner.call_skill("keyword-grader", {"spu_id": spu_id, ...})

def confirm_phase(spu_id: str, phase: int, confirmation: str):
    """确认闸门（Phase 2/3/5）"""
    conn = get_state_db()
    cursor = conn.cursor()
    
    # 检查 SPU 是否存在
    cursor.execute("SELECT current_phase, status FROM spu_states WHERE spu_id = ?", (spu_id,))
    row = cursor.fetchone()
    if not row:
        print(f"错误: SPU {spu_id} 不存在")
        conn.close()
        return
    
    current_phase, status = row
    
    # 验证阶段
    if phase != current_phase:
        print(f"错误: 当前阶段是 {current_phase}，请确认阶段 {phase}")
        conn.close()
        return
    
    # 检查闸门配置
    if phase not in GATE_RULES:
        print(f"错误: Phase {phase} 没有配置闸门")
        conn.close()
        return
    
    gate = GATE_RULES[phase]
    
    # 验证确认词
    if confirmation not in gate["confirm_keywords"]:
        print(f"错误: 无效的确认词 '{confirmation}'")
        print(f"允许的确认词: {', '.join(gate['confirm_keywords'])}")
        conn.close()
        return
    
    # 记录确认事件
    cursor.execute("""
        INSERT INTO gate_events (spu_id, phase, event_type, payload, confirmed_at)
        VALUES (?, ?, ?, ?, ?)
    """, (spu_id, phase, "confirmation", json.dumps({"text": confirmation}), datetime.now().isoformat()))
    
    # 更新状态
    next_phase = phase + 1
    cursor.execute("""
        UPDATE spu_states 
        SET current_phase = ?, 
            status = ?,
            updated_at = ?
        WHERE spu_id = ?
    """, (next_phase, 'processing', datetime.now().isoformat(), spu_id))
    conn.commit()
    conn.close()
    
    print(f"✅ Phase {phase} 已确认，进入 Phase {next_phase}")
    print(f"   闸门: {gate['name']}")

def get_status(spu_id: str):
    """查询 SPU 状态"""
    conn = get_state_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT spu_id, current_phase, status, state, created_at, updated_at
        FROM spu_states WHERE spu_id = ?
    """, (spu_id,))
    row = cursor.fetchone()
    conn.close()
    
    if not row:
        print(f"错误: SPU {spu_id} 不存在")
        return
    
    spu_id, phase, status, state_json, created_at, updated_at = row
    state = json.loads(state_json) if state_json else {}
    
    print(f"=== SPU {spu_id} 状态 ===")
    print(f"名称: {state.get('spu_name', 'N/A')}")
    print(f"品类: {state.get('category', 'N/A')}")
    print(f"当前阶段: Phase {phase}")
    print(f"状态: {status}")
    print(f"创建时间: {created_at}")
    print(f"更新时间: {updated_at}")
    
    # 显示闸门信息
    if phase in GATE_RULES:
        gate = GATE_RULES[phase]
        print(f"\n⚠️ 当前闸门: {gate['name']}")
        print(f"   超时: {gate['timeout']}秒")
        print(f"   确认词: {', '.join(gate['confirm_keywords'])}")

def list_spus():
    """列出所有 SPU"""
    conn = get_state_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT spu_id, current_phase, status, state, updated_at
        FROM spu_states ORDER BY updated_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print("暂无进行中的 SPU")
        return
    
    print(f"{'SPU ID':<15} {'阶段':<8} {'状态':<15} {'更新时间':<20}")
    print("-" * 60)
    for row in rows:
        spu_id, phase, status, state_json, updated_at = row
        state = json.loads(state_json) if state_json else {}
        name = state.get('spu_name', 'N/A')[:20]
        print(f"{spu_id:<15} {phase:<8} {status:<15} {updated_at:<20} {name}")

def resume_spu(spu_id: str):
    """恢复中断的 SPU 流程"""
    get_status(spu_id)
    print(f"\n请使用 confirm 命令继续确认闸门，或使用 start 重新初始化")

def main():
    parser = argparse.ArgumentParser(description="SOP Runner — 多阶段 Listing 生成流水线")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # start 命令
    start_parser = subparsers.add_parser("start", help="启动新的 SPU 处理流程")
    start_parser.add_argument("--spu-id", required=True, help="SPU ID")
    start_parser.add_argument("--spu-name", required=True, help="SPU 名称")
    start_parser.add_argument("--category", default="生活家居", help="品类（默认：生活家居）")
    
    # confirm 命令
    confirm_parser = subparsers.add_parser("confirm", help="确认闸门")
    confirm_parser.add_argument("--spu-id", required=True, help="SPU ID")
    confirm_parser.add_argument("--phase", type=int, required=True, help="阶段号")
    confirm_parser.add_argument("--confirmation", required=True, help="确认词")
    
    # status 命令
    status_parser = subparsers.add_parser("status", help="查询 SPU 状态")
    status_parser.add_argument("--spu-id", required=True, help="SPU ID")
    
    # list 命令
    subparsers.add_parser("list", help="列出所有 SPU")
    
    # resume 命令
    resume_parser = subparsers.add_parser("resume", help="恢复中断的 SPU")
    resume_parser.add_argument("--spu-id", required=True, help="SPU ID")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 路由到对应函数
    commands = {
        "start": lambda args: start_spu(args.spu_id, args.spu_name, args.category),
        "confirm": lambda args: confirm_phase(args.spu_id, args.phase, args.confirmation),
        "status": lambda args: get_status(args.spu_id),
        "list": lambda args: list_spus(),
        "resume": lambda args: resume_spu(args.spu_id)
    }
    
    cmd_func = commands.get(args.command)
    if cmd_func:
        cmd_func(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
