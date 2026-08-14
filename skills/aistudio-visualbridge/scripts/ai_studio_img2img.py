#!/usr/bin/env python3
"""
AI Studio 图生图 CLI
用法: python ai_studio_img2img.py <input_image> <prompt> [--output OUTPUT]
"""

import argparse
import json
import sys

def main():
    parser = argparse.ArgumentParser(description='AI Studio 图生图工具')
    parser.add_argument('input_image', help='输入图片路径')
    parser.add_argument('prompt', help='图片生成 prompt')
    parser.add_argument('--output', '-o', default='output.png',
                       help='输出文件路径')
    parser.add_argument('--model', '-m', default='gemini-3.1-flash-lite-image',
                       help='模型名称')
    
    args = parser.parse_args()
    
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
    
    # 5. 点击插入图片按钮
    commands.append({
        "tool": "mcp__aistudio__browser_click",
        "args": {
            "element": "Insert image button",
            "target": "button[aria-label=\"Insert images, videos, or files\"]"
        }
    })
    commands.append({
        "tool": "mcp__aistudio__browser_wait_for",
        "args": {"time": 1}
    })
    
    # 6. 点击 Upload files
    commands.append({
        "tool": "mcp__aistudio__browser_click",
        "args": {
            "element": "Upload files menu item",
            "target": "menuitem:has-text(\"Upload files\")"
        }
    })
    
    # 注意: 文件上传需要用户交互，这里仅打开文件选择器
    # 实际上传需要通过浏览器文件选择器手动完成
    
    print(json.dumps(commands, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
