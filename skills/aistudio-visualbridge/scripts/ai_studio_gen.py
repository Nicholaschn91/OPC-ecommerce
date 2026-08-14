#!/usr/bin/env python3
"""
AI Studio 图片生成 CLI
用法: python ai_studio_gen.py <prompt> [--model MODEL] [--output OUTPUT] [--image-only]
"""

import argparse
import sys
import json

def main():
    parser = argparse.ArgumentParser(description='AI Studio 图片生成工具')
    parser.add_argument('prompt', help='图片生成 prompt')
    parser.add_argument('--model', '-m', default='gemini-3.1-flash-lite-image',
                       help='模型名称 (默认: gemini-3.1-flash-lite-image)')
    parser.add_argument('--output', '-o', default='output.png',
                       help='输出文件路径')
    parser.add_argument('--image-only', action='store_true',
                       help='使用 Images only 模式')
    parser.add_argument('--input-image', '-i',
                       help='输入图片路径（图生图，需要手动上传）')
    parser.add_argument('--system-prompt',
                       help='系统提示词文件路径')
    
    args = parser.parse_args()
    
    # 输出 MCP 命令
    commands = []
    
    # 1. 导航到 AI Studio
    commands.append({
        "tool": "mcp__aistudio__browser_navigate",
        "args": {
            "url": f"https://aistudio.google.com/prompts/new_chat?model={args.model}"
        }
    })
    
    # 2. 等待页面加载
    commands.append({
        "tool": "mcp__aistudio__browser_wait_for",
        "args": {"time": 3}
    })
    
    # 3. 切换到 Images only 模式
    if args.image_only:
        commands.append({
            "tool": "mcp__aistudio__browser_evaluate",
            "args": {
                "function": "() => { const btns = document.querySelectorAll('button'); for (const btn of btns) { if (btn.textContent?.includes('Images only')) { btn.click(); return 'Clicked Images only'; } } return 'Not found'; }"
            }
        })
        commands.append({
            "tool": "mcp__aistudio__browser_wait_for",
            "args": {"time": 1}
        })
    
    # 4. 输入 prompt
    escaped_prompt = args.prompt.replace('`', '\\`').replace("'", "\\'")
    commands.append({
        "tool": "mcp__aistudio__browser_evaluate",
        "args": {
            "function": f"() => {{ const textarea = document.querySelector('textarea[aria-label=\"Enter a prompt\"]'); if (!textarea) return 'textarea not found'; const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set; nativeInputValueSetter.call(textarea, '{escaped_prompt}'); textarea.dispatchEvent(new Event('input', {{bubbles: true}})); return 'Input set'; }}"
        }
    })
    commands.append({
        "tool": "mcp__aistudio__browser_wait_for",
        "args": {"time": 1}
    })
    
    # 5. 点击 Run
    commands.append({
        "tool": "mcp__aistudio__browser_click",
        "args": {
            "element": "Run button",
            "target": "button:has-text(\"Run\")"
        }
    })
    
    # 6. 等待生成
    commands.append({
        "tool": "mcp__aistudio__browser_wait_for",
        "args": {"time": 20}
    })

    # 7. 检查是否出现错误，如果是则添加 Rerun this turn 恢复逻辑
    # 检测 error 标记
    commands.append({
        "tool": "mcp__aistudio__browser_evaluate",
        "args": {
            "function": "() => { const errors = document.querySelectorAll('[class*=error], [class*=internal-error]'); if (errors.length > 0) return 'ERROR_DETECTED'; return 'OK'; }"
        }
    })
    commands.append({
        "tool": "mcp__aistudio__browser_wait_for",
        "args": {"time": 1}
    })

    # 输出 JSON
    print(json.dumps(commands, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
