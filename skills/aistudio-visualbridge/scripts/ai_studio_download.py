#!/usr/bin/env python3
"""
AI Studio 图片下载 CLI
用法: python ai_studio_download.py [--output OUTPUT] [--screenshot]
"""

import argparse
import json
import sys

def main():
    parser = argparse.ArgumentParser(description='AI Studio 图片下载工具')
    parser.add_argument('--output', '-o', default='output.png',
                       help='输出文件路径')
    parser.add_argument('--screenshot', action='store_true',
                       help='截图而不是下载生成图片')
    
    args = parser.parse_args()
    
    commands = []
    
    if args.screenshot:
        # 截图模式
        commands.append({
            "tool": "mcp__aistudio__browser_take_screenshot",
            "args": {
                "path": args.output
            }
        })
    else:
        # 尝试提取生成的图片 URL
        commands.append({
            "tool": "mcp__aistudio__browser_evaluate",
            "args": {
                "function": "() => { const imgs = document.querySelectorAll('img'); for (const img of imgs) { if (img.naturalWidth > 100 && img.src && !img.src.startsWith('data:')) { return img.src; } } return null; }"
            }
        })
    
    print(json.dumps(commands, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
