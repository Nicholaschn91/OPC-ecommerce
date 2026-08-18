#!/usr/bin/env python3
"""
AI Studio 图片生成 CLI
用法: python ai_studio_gen.py <prompt> [--model MODEL] [--output OUTPUT] [--image-only]
"""

import argparse
import sys
import json
import re

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
        "tool": "mcp__browser-aistudio__browser_navigate",
        "args": {
            "url": f"https://aistudio.google.com/prompts/new_chat?model={args.model}"
        }
    })
    
    # 2. 等待页面加载
    commands.append({
        "tool": "mcp__browser-aistudio__browser_wait_for",
        "args": {"time": 3}
    })
    
    # 3. 切换到 Images only 模式
    if args.image_only:
        commands.append({
            "tool": "mcp__browser-aistudio__browser_evaluate",
            "args": {
                "function": "() => { const btns = document.querySelectorAll('button'); for (const btn of btns) { if (btn.textContent?.includes('Images only')) { btn.click(); return 'Clicked Images only'; } } return 'Not found'; }"
            }
        })
        commands.append({
            "tool": "mcp__browser-aistudio__browser_wait_for",
            "args": {"time": 1}
        })
    
    # 4. 输入 prompt（先剥离 --ar 令牌：Aspect ratio 保持 Auto，不跟提示词比例调）
    clean_prompt = re.sub(r'--ar\s+\S+', '', args.prompt).strip()
    escaped_prompt = clean_prompt.replace('`', '\\`').replace("'", "\\'")
    commands.append({
        "tool": "mcp__browser-aistudio__browser_evaluate",
        "args": {
            "function": f"() => {{ const textarea = document.querySelector('textarea[aria-label=\"Enter a prompt\"]'); if (!textarea) return 'textarea not found'; const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set; nativeInputValueSetter.call(textarea, '{escaped_prompt}'); textarea.dispatchEvent(new Event('input', {{bubbles: true}})); return 'Input set'; }}"
        }
    })
    commands.append({
        "tool": "mcp__browser-aistudio__browser_wait_for",
        "args": {"time": 1}
    })
    
    # 5. 点击 Run
    commands.append({
        "tool": "mcp__browser-aistudio__browser_click",
        "args": {
            "element": "Run button",
            "target": "button:has-text(\"Run\")"
        }
    })
    
    # 6. 等待生成
    commands.append({
        "tool": "mcp__browser-aistudio__browser_wait_for",
        "args": {"time": 20}
    })

    # 7. 错误检测 + Rerun 闭环（agent 按 note 分支执行；2026-08-18 最终修正版）
    # 7a. 检测 internal error（按文本精确匹配，不靠 class），Rerun 按钮在报错 turn 自身
    commands.append({
        "tool": "mcp__browser-aistudio__browser_evaluate",
        "note": "若返回 ERROR_FOUND_RERUN_READY -> 执行下一条(7b)；NO_ERROR -> 跳到下载；其余 -> 停手",
        "args": {
            "function": "() => { const turns=[...document.querySelectorAll('ms-chat-turn')]; for(let i=0;i<turns.length;i++){ if(/an\\s+internal\\s+error\\s+has\\s+occurred/i.test(turns[i].textContent||'')){ const r=[...turns[i].querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'')==='Rerun this turn'||/rerun this turn/i.test(b.textContent||'')); if(r) return 'ERROR_FOUND_RERUN_READY'; return 'ERROR_FOUND_NO_RERUN_BTN'; } } return 'NO_ERROR'; }"
        }
    })
    commands.append({
        "tool": "mcp__browser-aistudio__browser_wait_for",
        "args": {"time": 1}
    })
    # 7b. 点报错 model turn 的 Rerun this turn（仅当 7a 返回 ERROR_FOUND_RERUN_READY 时执行；只点一次）
    # 关键：browser_click 会被 user-turn overlay 拦截，必须用 mousedown+mouseup+click 稳健派发
    commands.append({
        "tool": "mcp__browser-aistudio__browser_evaluate",
        "note": "条件执行：仅当 7a 返回 ERROR_FOUND_RERUN_READY。点击报错 turn 自己的 Rerun，不新建 turn",
        "args": {
            "function": "() => { const turns=[...document.querySelectorAll('ms-chat-turn')]; for(let i=0;i<turns.length;i++){ if(/an\\s+internal\\s+error\\s+has\\s+occurred/i.test(turns[i].textContent||'')){ const r=[...turns[i].querySelectorAll('button')].find(b=>(b.getAttribute('aria-label')||'')==='Rerun this turn'||/rerun this turn/i.test(b.textContent||'')); if(!r) return 'NO_RERUN_BTN'; r.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true,view:window})); r.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,cancelable:true,view:window})); r.click(); return 'RERUN_CLICKED'; } } return 'NO_ERROR_TURN'; }"
        }
    })
    commands.append({
        "tool": "mcp__browser-aistudio__browser_wait_for",
        "args": {"time": 25}
    })
    # 7c. 校验出图（必须验证，不能只信"点中了"）
    commands.append({
        "tool": "mcp__browser-aistudio__browser_evaluate",
        "note": "终态校验：OK_IMAGE=成功；STILL_ERROR=服务端退化窗口停手(不循环/不重发/不查登录态)；其余=停手如实报告",
        "args": {
            "function": "() => { const img=[...document.querySelectorAll('img')].find(i=>(i.getAttribute('alt')||'').startsWith('Generated Image')); if(img) return 'OK_IMAGE'; const turns=[...document.querySelectorAll('ms-chat-turn')]; for(let t of turns) if(/an\\s+internal\\s+error\\s+has\\s+occurred/i.test(t.textContent||'')) return 'STILL_ERROR'; return 'PENDING'; }"
        }
    })

    # 输出 JSON
    print(json.dumps(commands, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
