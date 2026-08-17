#!/usr/bin/env python3
"""
AI Studio 完整图片生成流程
用法: python ai_studio_workflow.py <prompt> [--model MODEL] [--output OUTPUT] [--image-only]
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

def run_cli(script_name: str, args: list) -> list:
    """运行 CLI 脚本并返回 MCP 命令"""
    script_path = Path(__file__).parent / script_name
    cmd = [sys.executable, str(script_path)] + args
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running {script_name}: {result.stderr}", file=sys.stderr)
        sys.exit(1)
    return json.loads(result.stdout)

def main():
    parser = argparse.ArgumentParser(description='AI Studio 图片生成流程')
    parser.add_argument('prompt', help='图片生成 prompt')
    parser.add_argument('--model', '-m', default='gemini-3.1-flash-lite-image')
    parser.add_argument('--output', '-o', default='output.png')
    parser.add_argument('--image-only', action='store_true')
    parser.add_argument('--input-image', '-i', help='输入图片（图生图）')
    
    args = parser.parse_args()
    
    all_commands = []
    
    if args.input_image:
        # 图生图流程
        all_commands.extend(run_cli('ai_studio_img2img.py', [
            args.input_image, args.prompt,
            '--output', args.output
        ]))
    else:
        # 文生图流程
        all_commands.extend(run_cli('ai_studio_gen.py', [
            args.prompt,
            '--model', args.model,
            '--output', args.output,
            '--image-only' if args.image_only else ''
        ]))
    
    # 输出合并后的命令
    print(json.dumps(all_commands, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
